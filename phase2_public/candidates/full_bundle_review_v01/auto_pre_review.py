"""Automated *preliminary* review dispatcher for a declared tender/bid bundle.

Planning and summary modes are offline. Online mode is fail-closed: it needs an
exact-label approval list and a positive per-run issue cap. It never interprets
an unpaired tender requirement as a missing bid response, and never equates a
machine first-pass finding with human legal sign-off or whole-file coverage.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable

from assemble import assemble
from bundle_review import require_manifest, source_record
from pair_reasoner import PROMPT as PAIR_PROMPT
from pair_reasoner import run_online as run_pair_online


RISK = {"potential_risk", "requires_human_legal_review", "requires_human_legal_confirm"}
NO_SUPPORTED_ISSUE = {"no_supported_issue_found_within_review_scope", "valid_needs_human_confirm"}
ABSTAIN = {"insufficient_information_needs_human_confirm", "insufficient_information",
           "not_supported_by_current_corpus"}
RUNNABLE_TASKS = {"tender_clause_legality", "bid_standalone_legality", "bid_responsiveness"}
SENSITIVE_NUMBER = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|\d{17}[\dXx]|\d{12,19})(?!\d)")
SENSITIVE_PATTERNS = {
    "numeric_identifier": SENSITIVE_NUMBER,
    "email_address": re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I),
    "person_named_field": re.compile(
        r"(?:联系人|法定代表人|委托代理人|授权代表|项目经理|姓名|身份证号)\s*[:：]?\s*[\u4e00-\u9fff]{2,4}"
    ),
    "named_organization": re.compile(
        r"[\u4e00-\u9fffA-Za-z0-9（）()·\-]{2,60}(?:有限公司|有限责任公司|集团公司|工程公司|中学|小学|大学|医院)"
    ),
    "contact_address_or_account": re.compile(r"通讯地址|联系地址|住址|办公地址|银行账号|开户行|收款账号|账户名称"),
    "web_address": re.compile(r"https?://\S+", re.I),
}


def privacy_risk_codes(label: dict[str, Any]) -> list[str]:
    """Conservative screen over all free-text fields sent to the runners.

    This catches common identifiers but does not certify de-identification:
    the exact excerpts still require review before any real-world batch.
    Opaque document hashes and block IDs are excluded to avoid false positives
    from long numeric runs inside SHA-256 values.
    """
    bundle = label.get("bundle_evidence") or {}
    text_fields: list[Any] = [label.get("project_id"), label.get("document_excerpt"),
                              label.get("retrieval_queries"), label.get("runtime_project_context")]
    for source in [bundle.get("primary"), bundle.get("paired_bid_source"),
                   *(row.get("source") for row in bundle.get("alternatives") or [] if isinstance(row, dict))]:
        if isinstance(source, dict):
            text_fields.append(source.get("quote"))
    text_fields.extend(row.get("page_locator_limitation") for row in bundle.get("coverage") or []
                       if isinstance(row, dict))
    text = json.dumps(text_fields, ensure_ascii=False)
    return [code for code, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for data in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(data)
    return checksum.hexdigest()


def plan(bundle_dir: Path, source_manifest: Path | None = None) -> dict[str, Any]:
    intake = read_json(bundle_dir / "bundle_intake.json")
    issues = read_json(bundle_dir / "candidates.json")
    coverage = read_json(bundle_dir / "coverage.json")
    manifest = require_manifest(source_manifest) if source_manifest else None
    if manifest:
        declared = {d["document_key"]: d for d in manifest["documents"]}
        received = {d["document_key"]: d for d in intake["documents"]}
        if manifest["project_id"] != intake["project_id"] or set(declared) != set(received):
            raise ValueError("source_manifest_bundle_identity_mismatch")
        for key, row in received.items():
            if (declared[key]["role"] != row["document_type"]
                    or file_sha256(Path(declared[key]["resolved_path"])) != row["source_file_hash"]):
                raise ValueError("source_manifest_document_hash_mismatch")
    parsed_sources = {}
    for document in intake["documents"]:
        for block in read_jsonl(Path(document["locator_map_path"])):
            if str(block.get("text", "")).strip():
                source = source_record(document, block)
                key = (source["document_key"], source["source_locator"], source["block_id"])
                if key in parsed_sources:
                    raise ValueError("duplicate_parsed_source_locator")
                parsed_sources[key] = source

    def require_parsed_source(source: dict[str, Any]) -> None:
        key = (source.get("document_key"), source.get("source_locator"), source.get("block_id"))
        if parsed_sources.get(key) != source:
            raise ValueError("candidate_source_not_in_locator_map")

    labels = read_jsonl(bundle_dir / "candidate_labels.jsonl")
    coverage_summary = [{"document_key": d["document_key"], "quality_status": d["quality_status"],
                         "unreadable_or_empty_physical_pages": d["unreadable_or_empty_physical_pages"],
                         "unselected_block_count": len(d["not_selected_for_semantic_review_block_ids"]),
                         "page_locator_limitation": d["page_locator_limitation"]}
                        for d in coverage["documents"]]
    by_id = {row["issue_id"]: row for row in labels}
    if len(by_id) != len(labels):
        raise ValueError("duplicate_candidate_label_id")
    seen: set[str] = set()
    rows = []
    for issue in issues:
        issue_id, task = issue["issue_id"], issue["task"]
        if issue_id in seen or task not in RUNNABLE_TASKS:
            raise ValueError("duplicate_or_unknown_candidate")
        seen.add(issue_id)
        label = by_id.get(issue_id)
        if label is None and task != "bid_responsiveness":
            raise ValueError("missing_legal_label")
        source = issue["primary_source"]
        pair = issue.get("pairing") or {}
        matches = pair.get("candidate_matches") or []
        require_parsed_source(source)
        for match in matches:
            require_parsed_source(match["source"])
        paired = matches[0]["source"] if task == "bid_responsiveness" and pair.get("status") == "provisional_match_needs_verification" else None
        expected_excerpt = source["quote"] if not paired else "招标要求：" + source["quote"] + "\n投标响应：" + paired["quote"]
        expected_queries = [source["quote"]] + ([paired["quote"]] if paired else [])
        if label is not None:
            evidence = label.get("bundle_evidence") or {}
            expected_evidence = {"task": task, "primary": source, "paired_bid_source": paired,
                                 "pairing_status": pair.get("status"),
                                 "alternatives": matches if not paired else [],
                                 "documents_received": [d["document_id"] for d in intake["documents"]],
                                 "coverage": coverage_summary}
            if (label.get("review_task_kind") != task
                    or label.get("project_id") != intake["project_id"]
                    or label.get("document_id") != source["document_id"]
                    or label.get("document_location") != source["source_locator"]
                    or label.get("document_excerpt") != expected_excerpt
                    or label.get("retrieval_queries") != expected_queries
                    or evidence != expected_evidence):
                raise ValueError("candidate_label_source_mismatch")
            if manifest:
                expected_context = dict(manifest.get("project_context") or {})
                expected_context.setdefault("project_type", manifest["project_type"])
                expected_context.setdefault("project_location", manifest.get("project_location") or {})
                if label.get("runtime_project_context") != expected_context:
                    raise ValueError("candidate_label_project_context_mismatch")
        if task == "bid_responsiveness":
            status = pair.get("status")
            if (label is None) != (status != "provisional_match_needs_verification"):
                raise ValueError("pair_eligibility_label_mismatch")
        else:
            status = None
        rows.append({"issue_id": issue_id, "task": task,
                     "machine_route": "pair_reasoner" if label and task == "bid_responsiveness" else
                                      "strict_legal_cascade" if label else "pairing_unresolved",
                     "pairing_status": status,
                     "source_locator": issue["primary_source"]["source_locator"],
                     "label_sha256": digest(label) if label else None})
    if set(by_id) != seen & set(by_id):
        raise ValueError("orphan_candidate_label")
    route_counts = dict(Counter(row["machine_route"] for row in rows))
    return {"project_id": intake["project_id"],
            "source_manifest_sha256": file_sha256(source_manifest) if source_manifest else None,
            "candidate_labels_sha256": hashlib.sha256((bundle_dir / "candidate_labels.jsonl").read_bytes()).hexdigest(),
            "candidates_sha256": hashlib.sha256((bundle_dir / "candidates.json").read_bytes()).hexdigest(),
            "source_documents": [{"document_key": d["document_key"], "source_file_hash": d["source_file_hash"]}
                                 for d in intake["documents"]],
            "candidate_count": len(rows), "route_counts": route_counts,
            "coverage_warning_count": sum(bool(d.get("unreadable_or_empty_physical_pages"))
                                          or d.get("quality_status") != "pass" for d in coverage["documents"]),
            "scope_note": "Candidate routes are not legal verdicts; unpaired is not bid non-response.",
            "items": rows}


def validate_approval(plan_data: dict[str, Any], approval: dict[str, Any], max_issues: int) -> list[str]:
    if max_issues < 1:
        raise ValueError("positive_max_issues_required")
    if (approval.get("project_id") != plan_data["project_id"]
            or approval.get("candidate_labels_sha256") != plan_data["candidate_labels_sha256"]
            or approval.get("source_manifest_sha256") != plan_data["source_manifest_sha256"]):
        raise ValueError("approval_bundle_fingerprint_mismatch")
    entries = approval.get("approved")
    if not isinstance(entries, list) or not entries or len(entries) > max_issues:
        raise ValueError("approval_list_missing_or_exceeds_issue_cap")
    planned = {row["issue_id"]: row for row in plan_data["items"]}
    chosen: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("approval_entry_not_object")
        issue_id = entry.get("issue_id")
        row = planned.get(issue_id)
        if (row is None or row["machine_route"] == "pairing_unresolved"
                or row["label_sha256"] != entry.get("label_sha256") or issue_id in chosen):
            raise ValueError("approval_issue_or_exact_label_mismatch")
        chosen.append(issue_id)
    return chosen


def propose_pilot(bundle_dir: Path, plan_data: dict[str, Any], targets: dict[str, int],
                  existing_core: Path | None = None, existing_pair: Path | None = None,
                  selected_ids: list[str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Spread a small *privacy-screened* smoke sample across three tasks.

    This is a throughput/format pilot, not random sampling or an accuracy set.
    An operator must still inspect the exact excerpts before online execution.
    """
    labels = {r["issue_id"]: r for r in read_jsonl(bundle_dir / "candidate_labels.jsonl")}
    routes = {r["issue_id"]: r for r in plan_data["items"]}
    allowed_tasks = {"tender_clause_legality", "bid_standalone_legality", "bid_responsiveness"}
    if set(targets) != allowed_tasks or any(not isinstance(v, int) or v < 1 for v in targets.values()):
        raise ValueError("positive_target_required_for_each_review_task")
    if selected_ids is not None and (len(selected_ids) != sum(targets.values())
                                     or len(set(selected_ids)) != len(selected_ids)
                                     or any(not isinstance(x, str) for x in selected_ids)):
        raise ValueError("curated_pilot_ids_must_be_unique_and_match_target_total")
    already_run = set()
    for directory in (existing_core, existing_pair):
        if directory:
            already_run.update(p.stem for p in directory.glob("*.json") if p.stem in routes)
    approval_rows = []
    audit = {"selection_purpose": "throughput_and_format_smoke_not_accuracy",
             "selection_method": "curated_ids_then_privacy_screen" if selected_ids is not None else "page_spread_then_privacy_screen",
             "already_run_excluded": len(already_run), "targets": targets, "screened_out": {},
             "selected_ids_by_task": {}}
    for task, target in targets.items():
        pool = []
        reasons = Counter()
        for row in plan_data["items"]:
            if row["task"] != task or row["machine_route"] == "pairing_unresolved" or row["issue_id"] in already_run:
                continue
            label = labels[row["issue_id"]]
            privacy = privacy_risk_codes(label)
            source = label["bundle_evidence"]["primary"]
            excerpt = label["document_excerpt"]
            if privacy:
                reasons.update(privacy)
            elif source.get("quote_truncated") or not source.get("source_locator"):
                reasons.update(["source_locator_not_complete"])
            elif not 8 <= len(excerpt) <= 800:
                reasons.update(["excerpt_length_outside_pilot"])
            else:
                page = source.get("page_number")
                pool.append((page if isinstance(page, int) else 10**9, row["issue_id"], row))
        pool.sort()
        if len(pool) < target:
            raise ValueError(f"too_few_privacy_screened_pilot_items:{task}")
        safe = {issue_id: row for _, issue_id, row in pool}
        if selected_ids is not None:
            selected = [issue_id for issue_id in selected_ids if routes.get(issue_id, {}).get("task") == task]
            if len(selected) != target or any(issue_id not in safe for issue_id in selected):
                raise ValueError(f"curated_pilot_item_failed_privacy_or_route_check:{task}")
        else:
            used_excerpts = set()
            selected = []
            for index in range(target):
                center = (2 * index + 1) * len(pool) // (2 * target)
                offsets = sorted(range(len(pool)), key=lambda i: (abs(i - center), i))
                for offset in offsets:
                    _, issue_id, _ = pool[offset]
                    excerpt = labels[issue_id]["document_excerpt"]
                    if issue_id not in selected and excerpt not in used_excerpts:
                        selected.append(issue_id)
                        used_excerpts.add(excerpt)
                        break
                else:
                    raise ValueError(f"not_enough_distinct_pilot_excerpts:{task}")
        for issue_id in selected:
            approval_rows.append({"issue_id": issue_id, "label_sha256": safe[issue_id]["label_sha256"]})
        audit["screened_out"][task] = dict(reasons)
        audit["selected_ids_by_task"][task] = selected
    if selected_ids is not None and set(selected_ids) != {row["issue_id"] for row in approval_rows}:
        raise ValueError("curated_pilot_contains_unknown_or_unrouted_issue")
    approval = {"project_id": plan_data["project_id"],
                "candidate_labels_sha256": plan_data["candidate_labels_sha256"],
                "source_manifest_sha256": plan_data["source_manifest_sha256"],
                "approved": approval_rows,
                "privacy_review_complete": False,
                "purpose": "bounded_preliminary_review_smoke_not_whole_bundle_or_accuracy"}
    return approval, audit


def result_bound_to_label(result: dict[str, Any], label: dict[str, Any]) -> None:
    runtime = result.get("runtime_input") or {}
    if (result.get("issue_id") != label["issue_id"]
            or runtime.get("review_task_kind") != label["review_task_kind"]
            or runtime.get("bundle_evidence") != label["bundle_evidence"]
            or (runtime.get("contract_evidence") or {}).get("document_excerpt") != label["document_excerpt"]
            or (runtime.get("review_scope") or {}).get("documents_received")
            != label["bundle_evidence"]["documents_received"]):
        raise ValueError("result_not_bound_to_approved_label")
    gate = result.get("post_llm_gate")
    if not isinstance(gate, dict) or not isinstance(gate.get("response"), dict):
        raise ValueError("result_without_gate")
    if (gate.get("status") not in {"passed", "corrected", "review_required", "blocked"}
            or not isinstance(gate.get("blocked"), bool)
            or (gate["status"] == "blocked") != gate["blocked"]):
        raise ValueError("invalid_gate_status_or_block_flag")
    findings = gate["response"].get("findings")
    if (not isinstance(findings, list) or not findings
            or any(not isinstance(f, dict) or f.get("issue_id") != label["issue_id"] for f in findings)):
        raise ValueError("gated_finding_issue_binding_mismatch")


def execute_approved(bundle_dir: Path, output_dir: Path, approval: dict[str, Any], max_issues: int,
                     legal_executor: Callable[[dict[str, Any]], dict[str, Any]],
                     pair_executor: Callable[[dict[str, Any]], dict[str, Any]],
                     run_settings: dict[str, Any] | None = None,
                     source_manifest: Path | None = None) -> dict[str, Any]:
    if source_manifest is None:
        raise ValueError("online_dispatch_requires_original_source_manifest")
    if approval.get("privacy_review_complete") is not True:
        raise ValueError("exact_excerpt_privacy_review_required_before_online")
    plan_data = plan(bundle_dir, source_manifest)
    chosen = validate_approval(plan_data, approval, max_issues)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError("refuse_to_overwrite_existing_batch")
    labels = {row["issue_id"]: row for row in read_jsonl(bundle_dir / "candidate_labels.jsonl")}
    if (file_sha256(bundle_dir / "candidate_labels.jsonl") != plan_data["candidate_labels_sha256"]
            or file_sha256(source_manifest) != plan_data["source_manifest_sha256"]):
        raise ValueError("approved_inputs_changed_before_dispatch")
    (output_dir / "legal").mkdir(parents=True, exist_ok=True)
    (output_dir / "pair").mkdir(parents=True, exist_ok=True)
    audit = {"project_id": plan_data["project_id"], "candidate_labels_sha256": plan_data["candidate_labels_sha256"],
             "approved_count": len(chosen), "max_issues": max_issues,
             "provider_request_count_not_capped_by_max_issues": True, "completed": [], "failed": [],
             "run_settings": run_settings or {},
             "no_unapproved_api_calls": True, "not_a_whole_bundle_review": len(chosen) < plan_data["candidate_count"]}
    for issue_id in chosen:
        label = labels[issue_id]
        route = "pair" if label["review_task_kind"] == "bid_responsiveness" else "legal"
        target = output_dir / route / f"{issue_id}.json"
        result = None
        privacy_codes: list[str] = []
        try:
            # The legal runtime also transmits bundle_evidence, including
            # coverage and alternate source text. Screen the *entire* label.
            privacy_codes = privacy_risk_codes(label)
            if privacy_codes:
                raise ValueError("sensitive_content_detected_before_transmission")
            result = pair_executor(label) if route == "pair" else legal_executor(label)
            result_bound_to_label(result, label)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            audit["completed"].append({"issue_id": issue_id, "route": route,
                                       "gate_status": result["post_llm_gate"].get("status"),
                                       "result_sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
        except Exception as exc:
            if result is not None:
                quarantine = output_dir / route / f"{issue_id}.quarantine.json"
                quarantine.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            # No excerpt, provider payload or secret enters this compact log.
            known = {"sensitive_content_detected_before_transmission", "result_not_bound_to_approved_label",
                     "result_without_gate", "invalid_gate_status_or_block_flag",
                     "gated_finding_issue_binding_mismatch"}
            failure = {"issue_id": issue_id, "route": route,
                       "failure_code": str(exc) if str(exc) in known else type(exc).__name__}
            if privacy_codes:
                failure["privacy_risk_codes"] = privacy_codes
            audit["failed"].append(failure)
        (output_dir / "batch_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                                                      encoding="utf-8")
    assembled = assemble(bundle_dir, core_dir=output_dir / "legal", pair_dir=output_dir / "pair")
    assembled_path = output_dir / "review_assembled.private.json"
    assembled_path.write_text(json.dumps(assembled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = summarize_assembled(assembled)
    summary_path = output_dir / "machine_preliminary_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit["assembled_review_sha256"] = file_sha256(assembled_path)
    audit["machine_summary_sha256"] = file_sha256(summary_path)
    (output_dir / "batch_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
    return audit


def classify(row: dict[str, Any]) -> dict[str, Any]:
    gate = row.get("risk_response_gated_unmodified")
    core_status = row["core_status"]
    if core_status == "not_eligible_unpaired":
        status = "pairing_unresolved_not_a_nonresponse_finding"
    elif gate is None:
        status = "eligible_but_not_run"
    elif gate.get("blocked") or core_status == "blocked":
        status = "machine_output_blocked"
    else:
        findings = (gate.get("response") or {}).get("findings") or []
        types = {f.get("conclusion_type") for f in findings if isinstance(f, dict)}
        if not types:
            status = "machine_output_unclassified"
        elif types <= RISK:
            status = "preliminary_risk_for_human_confirmation"
        elif types <= NO_SUPPORTED_ISSUE:
            status = "no_supported_issue_within_reviewed_scope"
        elif types <= ABSTAIN:
            status = "machine_abstained_with_reason"
        else:
            status = "mixed_or_unclassified_subconclusions"
    assessable = status in {"preliminary_risk_for_human_confirmation",
                            "no_supported_issue_within_reviewed_scope",
                            "machine_abstained_with_reason", "mixed_or_unclassified_subconclusions"}
    findings = (row["presentation_response"].get("findings") or []) if assessable else []
    return {"issue_id": row["issue_id"], "task": row["task"],
            "machine_processing_status": status, "gate_status": core_status,
            "conclusion_types": [f.get("conclusion_type") for f in
                                 (row["presentation_response"].get("findings") or []) if isinstance(f, dict)],
            "preliminary_findings": [{key: f.get(key) for key in (
                "conclusion_type", "document_excerpt", "document_location", "risk_category",
                "legal_evidence", "evidence_boundary", "assistant_recommendation")}
                for f in findings if isinstance(f, dict)],
            "human_signoff_status": "not_signed_off"}


def summarize_assembled(assembled: dict[str, Any]) -> dict[str, Any]:
    items = [classify(row) for row in assembled["records"]]
    counts = dict(Counter(row["machine_processing_status"] for row in items))
    coverage = assembled["coverage"]["documents"]
    gaps = {d["document_key"]: d.get("unreadable_or_empty_physical_pages", []) for d in coverage
            if d.get("unreadable_or_empty_physical_pages")}
    unselected = {d["document_key"]: len(d.get("not_selected_for_semantic_review_block_ids") or []) for d in coverage}
    eligible_unrun = counts.get("eligible_but_not_run", 0)
    unresolved = counts.get("pairing_unresolved_not_a_nonresponse_finding", 0)
    blocked = (counts.get("machine_output_blocked", 0) + counts.get("machine_output_unclassified", 0)
               + counts.get("mixed_or_unclassified_subconclusions", 0))
    return {"project_id": assembled["project_id"], "candidate_count": len(items),
            "machine_status_counts": counts,
            "processable_candidate_execution_complete": eligible_unrun == 0 and blocked == 0,
            "whole_bundle_preliminary_review_complete": False,
            "whole_bundle_completion_barriers": {
                "eligible_not_run": eligible_unrun, "unresolved_pairing": unresolved,
                "blocked_or_unclassified": blocked, "page_text_gaps": gaps,
                "parsed_blocks_not_selected_for_review": unselected,
                "addenda_status": (assembled.get("addenda_inventory") or {}).get("status", "not_verified")},
            "no_independent_accuracy_claim": True,
            "human_signoff_separate_from_machine_status": True,
            "items": items}


def summarize(bundle_dir: Path, core_dir: Path | None = None, pair_dir: Path | None = None) -> dict[str, Any]:
    return summarize_assembled(assemble(bundle_dir, core_dir=core_dir, pair_dir=pair_dir))


def online_executors(*, final_max_tokens: int, triage_max_tokens: int, pair_max_tokens: int,
                     top_k: int, run_id: str, enable_external_fallback: bool,
                     external_manifest: Path | None) -> tuple[Callable, Callable, dict[str, Any]]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    from run_deepseek_llm_reasoning_smoke import load_api_key  # noqa: PLC0415
    from run_hierarchy_gated_llm_smoke import (  # noqa: PLC0415
        PROMPT_FILE, StrictHierarchyHybridRetriever, ExternalFallbackStateMachine,
        build_external_provider, load_external_manifest, run_case,
    )
    api_key = load_api_key()
    retriever = StrictHierarchyHybridRetriever()
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    entries = load_external_manifest(external_manifest) if enable_external_fallback and external_manifest else []
    if enable_external_fallback and not entries:
        raise ValueError("external_fallback_requires_nonempty_allowlisted_manifest")
    provider = build_external_provider("manifest_http", entries, 20.0) if enable_external_fallback else None
    fallback = ExternalFallbackStateMachine(enabled=enable_external_fallback, provider=provider,
                                            manifest_entries=entries)

    def legal(label: dict[str, Any]) -> dict[str, Any]:
        return run_case(api_key=api_key, retriever=retriever, final_prompt=prompt, context_template={}, label=label,
                        top_k=top_k, final_max_tokens=final_max_tokens, triage_max_tokens=triage_max_tokens,
                        compact_final_output=False, experiment_run_id=run_id, external_fallback=fallback)

    def pair(label: dict[str, Any]) -> dict[str, Any]:
        return run_pair_online(label, api_key, pair_max_tokens)

    provenance = {"legal_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                  "pair_prompt_sha256": hashlib.sha256(PAIR_PROMPT.encode("utf-8")).hexdigest(),
                  "law_corpus_sha256": retriever.corpus_sha256,
                  "embedding_model": retriever.embedding_model_name,
                  "external_manifest_sha256": file_sha256(external_manifest) if enable_external_fallback else None}
    return legal, pair, provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path,
                        help="Required for online calls: rebind original source hashes and project context")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("plan", "summarize", "propose-pilot", "execute-online"), default="plan")
    parser.add_argument("--core-results", type=Path)
    parser.add_argument("--pair-results", type=Path)
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--max-issues", type=int, default=0,
                        help="Maximum approved issues, not a cap on internal model/API requests")
    parser.add_argument("--pilot-tender", type=int, default=8)
    parser.add_argument("--pilot-bid", type=int, default=8)
    parser.add_argument("--pilot-pair", type=int, default=4)
    parser.add_argument("--pilot-ids-file", type=Path,
                        help="Private JSON array of exact issue IDs for a curated bounded pilot")
    parser.add_argument("--final-max-tokens", type=int, default=16384)
    parser.add_argument("--triage-max-tokens", type=int, default=2048)
    parser.add_argument("--pair-max-tokens", type=int, default=2048)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--run-id", default="automatic-preliminary-bundle-review")
    parser.add_argument("--enable-external-fallback", action="store_true")
    parser.add_argument("--external-manifest", type=Path)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    if args.mode == "plan":
        result = plan(args.bundle_output, args.source_manifest)
        path = args.output_root / "automation_plan.json"
    elif args.mode == "propose-pilot":
        if not args.source_manifest:
            parser.error("pilot proposal requires --source-manifest")
        planned = plan(args.bundle_output, args.source_manifest)
        targets = {"tender_clause_legality": args.pilot_tender,
                   "bid_standalone_legality": args.pilot_bid,
                   "bid_responsiveness": args.pilot_pair}
        selected_ids = read_json(args.pilot_ids_file) if args.pilot_ids_file else None
        if selected_ids is not None and not isinstance(selected_ids, list):
            parser.error("--pilot-ids-file must contain a JSON array of issue IDs")
        approval, audit = propose_pilot(args.bundle_output, planned, targets,
                                        args.core_results, args.pair_results, selected_ids)
        if args.max_issues < 1 or sum(targets.values()) > args.max_issues:
            parser.error("pilot target total must not exceed positive --max-issues")
        validate_approval(planned, approval, args.max_issues)
        approval_path = args.output_root / "pilot_approval_candidate.private.json"
        audit_path = args.output_root / "pilot_selection_audit.json"
        if approval_path.exists() or audit_path.exists():
            raise FileExistsError("refuse_to_overwrite_existing_pilot_proposal")
        approval_path.write_text(json.dumps(approval, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"approval_candidate": str(approval_path), "count": len(approval["approved"]),
                          "manual_privacy_review_required": True}, ensure_ascii=False))
        return 0
    elif args.mode == "summarize":
        result = summarize(args.bundle_output, args.core_results, args.pair_results)
        path = args.output_root / "machine_preliminary_summary.json"
    else:
        if not args.approval_file or not args.source_manifest:
            parser.error("online processing requires --source-manifest, --approval-file and --max-issues")
        if min(args.final_max_tokens, args.triage_max_tokens, args.pair_max_tokens, args.top_k) < 1:
            parser.error("online token and retrieval limits must be positive")
        if args.output_root.exists() and any(args.output_root.iterdir()):
            raise FileExistsError("refuse_to_overwrite_existing_batch")
        planned = plan(args.bundle_output, args.source_manifest)
        approval = read_json(args.approval_file)
        validate_approval(planned, approval, args.max_issues)
        if approval.get("privacy_review_complete") is not True:
            raise ValueError("exact_excerpt_privacy_review_required_before_online")
        legal, pair, provenance = online_executors(final_max_tokens=args.final_max_tokens,
                                                    triage_max_tokens=args.triage_max_tokens,
                                                    pair_max_tokens=args.pair_max_tokens, top_k=args.top_k,
                                                    run_id=args.run_id, enable_external_fallback=args.enable_external_fallback,
                                                    external_manifest=args.external_manifest)
        settings = {"model": "deepseek-v4-flash", "legal_final_max_tokens": args.final_max_tokens,
                    "legal_triage_max_tokens": args.triage_max_tokens,
                    "pair_max_tokens": args.pair_max_tokens, "pair_thinking_mode": "disabled",
                    "legal_thinking_mode": "enabled", "external_fallback_enabled": args.enable_external_fallback,
                    "run_id": args.run_id, **provenance}
        result = execute_approved(args.bundle_output, args.output_root, approval, args.max_issues,
                                  legal, pair, settings, args.source_manifest)
        path = args.output_root / "batch_audit.json"
        print(json.dumps({"output": str(path), "completed": len(result["completed"]),
                          "failed": len(result["failed"])}, ensure_ascii=False))
        return 0
    if path.exists():
        raise FileExistsError("refuse_to_overwrite_existing_plan_or_summary")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "candidate_count": result["candidate_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
