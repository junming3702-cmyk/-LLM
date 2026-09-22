"""Candidate one-round material interface; no LLM fabrication or legal admission.

Request strategies are separate from the common material-return interface. This
module cannot infer that an unseen attachment is missing, create verified facts,
change the law corpus, or manufacture claim_confirmation_validation.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from experiment_integrity import digest, validate_runtime

ALLOWED_KINDS = {"project_fact", "specified_attachment"}
REQUEST_FIELDS = {"request_id", "issue_id", "finding_id", "missing_element",
                  "material_id", "kind", "reason", "expected_review_action"}


@dataclass(frozen=True)
class Budget:
    max_requests: int = 3
    max_returned_characters: int = 6000
    max_rounds: int = 1

    def __post_init__(self):
        if not 1 <= self.max_requests <= 3 or self.max_rounds != 1 or self.max_returned_characters < 1:
            raise ValueError("candidate experiment allows one round and at most three requests")


def bind_requests(gated_response, proposals):
    """Validate explicit proposals against existing gaps, without inventing them.

    A reviewable structured gap inventory must be supplied by the existing output
    adapter. Free-text advice with no unambiguous binding stays unresolved.
    """
    findings = {f.get("finding_id"): f for f in gated_response.get("findings", []) if isinstance(f, dict)}
    accepted, invalid = [], []
    request_ids = set()
    for request in proposals:
        try:
            if not isinstance(request, dict):
                raise ValueError("request_not_object")
            validate_runtime(request)
            if set(request) != REQUEST_FIELDS or not all(isinstance(v, str) and v.strip() for v in request.values()):
                raise ValueError("incomplete_structured_request")
            if request["request_id"] in request_ids:
                raise ValueError("duplicate_request_id")
            request_ids.add(request["request_id"])
            if request["kind"] not in ALLOWED_KINDS:
                raise ValueError("not_a_supplementable_project_fact_or_attachment")
            finding = findings.get(request["finding_id"], {})
            if finding.get("issue_id") != request["issue_id"]:
                raise ValueError("finding_issue_binding_mismatch")
            coverage = finding.get("legal_element_coverage") or {}
            gaps = [key for key, state in coverage.items() if state == "missing"]
            extra_gaps = finding.get("evidence_gaps", [])
            if isinstance(extra_gaps, list):
                gaps.extend(gap for gap in extra_gaps if isinstance(gap, str))
            if request["missing_element"] not in gaps:
                raise ValueError("missing_element_not_in_existing_review")
            accepted.append(deepcopy(request))
        except (ValueError, TypeError) as exc:
            invalid.append({"request_id": request.get("request_id") if isinstance(request, dict) else None,
                            "status": "invalid_request", "reason": str(exc)})
    return {"requests": accepted, "invalid_requests": invalid,
            "unresolved_free_text_advice": "requires_explicit_binding_not_automatically_interpreted"}


def return_materials(requests, registry, *, budget=Budget()):
    """Execution-only registry; hidden source mapping is never passed to the LLM.

    An entry must explicitly authorize its issue and missing element, carry the
    exact material text, its hash and source locator. This verifies packet
    integrity, not legal correctness. Over-budget material is not truncated.
    """
    events, returned = [], []
    seen_ids, characters = set(), 0
    for index, request in enumerate(requests):
        event = {"request_id": request.get("request_id"), "status": "not_returned"}
        material = registry.get(request.get("material_id"), {})
        reason = None
        if index >= budget.max_requests:
            reason = "request_budget_exceeded"
        elif request.get("material_id") in seen_ids:
            reason = "duplicate_material_request"
        elif request.get("kind") not in ALLOWED_KINDS:
            reason = "unsupported_request_kind"
        elif not material:
            reason = "material_unavailable"
        elif request.get("issue_id") not in material.get("allowed_issue_ids", []):
            reason = "material_not_authorized_for_issue"
        elif request.get("missing_element") not in material.get("allowed_missing_elements", []):
            reason = "material_not_bound_to_requested_element"
        elif material.get("release_status") != "owner_verified_for_experiment":
            reason = "material_requires_owner_verification"
        elif not material.get("source_locator") or not isinstance(material.get("text"), str) or not material["text"]:
            reason = "material_text_or_locator_missing"
        elif digest(material["text"]) != material.get("text_hash"):
            reason = "material_hash_mismatch"
        elif characters + len(material["text"]) > budget.max_returned_characters:
            reason = "material_budget_exceeded_no_truncation"
        if reason:
            event["reason"] = reason
        else:
            seen_ids.add(request["material_id"])
            characters += len(material["text"])
            packet = {"material_id": request["material_id"], "issue_id": request["issue_id"],
                      "missing_element": request["missing_element"],
                      "source_locator": material["source_locator"], "text": material["text"],
                      "text_hash": material["text_hash"]}
            returned.append(packet)
            event.update(status="returned", material_hash=packet["text_hash"])
        events.append(event)
    return {"materials": returned, "events": events, "returned_characters": characters}


def review_once(runtime, initial_result, returned, reviewer, *, prior_rounds=0):
    if prior_rounds != 0:
        raise ValueError("one_rereview_only")
    if not returned.get("materials"):
        return {"rereview_called": False, "initial_result": deepcopy(initial_result),
                "final_result": deepcopy(initial_result), "events": returned.get("events", [])}
    updated = deepcopy(runtime)
    evidence_hash = digest(updated.get("retrieved_legal_evidence", []))
    # Material may contain untrusted prose, never system instructions or evidence
    # verification records. Do not change existing project facts automatically.
    for material in returned["materials"]:
        validate_runtime(material)
        if material.get("issue_id") != runtime.get("issue_id") or digest(material.get("text")) != material.get("text_hash"):
            raise ValueError("returned_material_binding_failure")
    updated["supplemental_project_materials"] = deepcopy(returned["materials"])
    updated["clarification_history"] = [{"round": 1, "returned_material_hash": digest(returned["materials"])}]
    result = reviewer(updated)
    if digest(updated.get("retrieved_legal_evidence", [])) != evidence_hash:
        raise RuntimeError("reviewer_mutated_fixed_evidence")
    return {"rereview_called": True, "rounds": 1, "initial_result": deepcopy(initial_result),
            "final_result": result, "events": returned.get("events", []),
            "workflow_status": "requires_human_second_review",
            "boundary": "Original supported findings retained for comparison; conflicting revisions need human review."}
