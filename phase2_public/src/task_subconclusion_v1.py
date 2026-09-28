"""Caller-locked, source-bound observation route; never a legal verdict.

Use only when the caller explicitly provides the claim list and source excerpts.
This route supplements the legal review; it cannot certify bid responsiveness or
the completeness of an unverified document package.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any


VERSION = "task-subconclusion-v1"
MODES = {"document_visibility"}
STATES = {"observed", "pending_verification"}
CLAIM_TYPES = {"narrative_visibility", "chart_visibility"}
SOURCE_KINDS = {"text", "chart_ocr"}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def build_contract(issue_id: str, mode: str, required_claims: list[dict[str, str]],
                   sources: list[dict[str, str]]) -> dict[str, Any]:
    if mode not in MODES or not issue_id or not required_claims or not sources:
        raise ValueError("task_contract_incomplete_or_mode_unsupported")
    if any(not isinstance(row, dict) for row in required_claims + sources):
        raise ValueError("task_claim_or_source_binding_invalid")
    ids = [row.get("claim_id") for row in required_claims]
    source_ids = [row.get("source_id") for row in sources]
    if (any(not isinstance(value, str) or not value for value in ids + source_ids)
            or len(set(ids)) != len(ids) or len(set(source_ids)) != len(source_ids)
            or any(row.get("claim_type") not in CLAIM_TYPES for row in required_claims)
            or any(not all(isinstance(row.get(key), str) and row[key]
                           for key in ("source_id", "document_id", "locator", "text"))
                   or row.get("source_kind") not in SOURCE_KINDS
                   for row in sources)):
        raise ValueError("task_claim_or_source_binding_invalid")
    base = {"version": VERSION, "issue_id": issue_id, "mode": mode,
            "required_claims": deepcopy(required_claims), "sources": deepcopy(sources)}
    return {**base, "contract_sha256": _digest(base)}


def prompt_addendum() -> str:
    return """
The caller-locked task_subconclusion_contract_v1 is an observation/comparison
task, not a legal conclusion. Return JSON with exactly issue_id,
contract_sha256 and subconclusions. Each required claim appears once, with
claim_id, status (observed | pending_verification), source_refs and explanation.
For observed, cite an exact source_id, locator and quote substring from the
supplied source text. For pending_verification, explain the specific missing
readability/coverage and do not claim absence. Never turn a visible narrative
into proof that an unreadable chart exists, is absent, or is compliant. Never
write legal conclusion_type, risk_category, or automatic bid rejection.
"""


def apply_task_gate(raw: Any, contract: dict[str, Any], *, finish_reason: str = "stop",
                    transport_ok: bool = True) -> dict[str, Any]:
    original = deepcopy(raw)
    errors: list[str] = []
    base = {key: contract.get(key) for key in
            ("version", "issue_id", "mode", "required_claims", "sources")}
    if (contract.get("version") != VERSION or _digest(base) != contract.get("contract_sha256")
            or contract.get("mode") not in MODES):
        errors.append("caller_contract_invalid")
    if finish_reason != "stop" or not transport_ok:
        errors.append("transport_or_truncation_failure")
    if not isinstance(raw, dict) or set(raw) != {"issue_id", "contract_sha256", "subconclusions"}:
        errors.append("root_schema_invalid")
        rows = []
    else:
        if raw["issue_id"] != contract.get("issue_id") or raw["contract_sha256"] != contract.get("contract_sha256"):
            errors.append("issue_or_contract_binding_mismatch")
        rows = raw.get("subconclusions")
        if not isinstance(rows, list):
            errors.append("subconclusions_not_list")
            rows = []
    claims = {row.get("claim_id"): row for row in (contract.get("required_claims") or []) if isinstance(row, dict)}
    sources = {row.get("source_id"): row for row in (contract.get("sources") or []) if isinstance(row, dict)}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"claim_id", "status", "source_refs", "explanation"}:
            errors.append(f"subconclusions[{index}].schema_invalid")
            continue
        claim_id = row["claim_id"]
        if claim_id not in claims or claim_id in seen:
            errors.append(f"subconclusions[{index}].claim_binding_invalid")
        seen.add(claim_id)
        if row["status"] not in STATES or not isinstance(row["explanation"], str) or not row["explanation"].strip():
            errors.append(f"subconclusions[{index}].status_or_explanation_invalid")
        refs = row["source_refs"]
        if not isinstance(refs, list):
            errors.append(f"subconclusions[{index}].source_refs_invalid")
            continue
        if row["status"] == "observed" and not refs:
            errors.append(f"subconclusions[{index}].observation_without_source")
        if row["status"] == "pending_verification" and refs:
            errors.append(f"subconclusions[{index}].pending_cannot_claim_observed_source")
        for ref in refs:
            if not isinstance(ref, dict) or set(ref) != {"source_id", "locator", "quote"}:
                errors.append(f"subconclusions[{index}].source_ref_schema_invalid")
                continue
            source = sources.get(ref["source_id"])
            if (not source or ref["locator"] != source["locator"]
                    or not isinstance(ref["quote"], str) or not ref["quote"].strip()
                    or ref["quote"] not in source["text"]):
                errors.append(f"subconclusions[{index}].source_quote_not_in_input")
            if (row["status"] == "observed"
                    and claims.get(claim_id, {}).get("claim_type") == "chart_visibility"
                    and source and source.get("source_kind") != "chart_ocr"):
                errors.append(f"subconclusions[{index}].chart_not_verified_by_chart_source")
    if seen != set(claims):
        errors.append("required_subconclusions_incomplete")
    if errors:
        return {"status": "blocked", "blocked": True, "failure_class": "task_protocol_failure",
                "errors": errors, "raw_response": original, "legal_conclusion_available": False,
                "response": {"task_completion": "not_assessed_due_to_processing_hold",
                             "subconclusions": [], "legal_conclusion_type": None}}
    states = {row["status"] for row in rows}
    completion = ("observed_within_supplied_scope" if states == {"observed"}
                  else "not_assessed_requires_review" if states == {"pending_verification"}
                  else "partially_observed_requires_review")
    return {"status": "review_required", "blocked": False, "errors": [],
            "raw_response": original, "legal_conclusion_available": False,
            "response": {"issue_id": contract["issue_id"], "mode": contract["mode"],
                         "task_completion": completion, "subconclusions": deepcopy(rows),
                         "pending_claim_ids": [row["claim_id"] for row in rows
                                               if row["status"] == "pending_verification"],
                         "legal_conclusion_type": None, "human_review_required": True,
                         "boundary": "Observed text is not complete package or legal compliance."}}
