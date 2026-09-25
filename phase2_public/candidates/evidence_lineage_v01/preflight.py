"""Opt-in pre-inference guard: lock task and evidence packet before any API call."""

from __future__ import annotations

import json
import hashlib
from copy import deepcopy
import re
from typing import Any

from task_scope import audit_task


def capture_selected_from_retrieval(audit_levels: list[dict[str, Any]], task: dict[str, Any]) -> dict[str, Any]:
    """Capture issue-specific selected candidates *before* final packaging.

    This must be called with the actual completed retrieval audit, not a
    reconstruction from the final LLM context. A digest detects later edits;
    it is not a signature or proof that retrieval itself was correct.
    """
    canonical = json.dumps(audit_levels, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    task_canonical = json.dumps(task, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    selected: dict[str, dict[str, Any]] = {}
    for level in audit_levels:
        if not isinstance(level, dict):
            raise ValueError("invalid_retrieval_level")
        for row in level.get("discovery_only_candidates", []):
            if not isinstance(row, dict):
                raise ValueError("invalid_discovery_candidate")
            cid = row.get("chunk_id")
            if not isinstance(cid, str) or not cid or not isinstance(row.get("legal_quote"), str):
                raise ValueError("invalid_discovery_candidate")
            if not re.fullmatch(r"[0-9a-fA-F]{64}", str(row.get("file_hash") or "")):
                raise ValueError("discovery_candidate_without_source_hash")
            selected[cid] = {"chunk_id": cid, "legal_quote": row["legal_quote"],
                             "file_hash": row["file_hash"], "packet_role": "discovery_only_not_independent_basis"}
        for phase in level.get("phases", []):
            if not isinstance(phase, dict):
                raise ValueError("invalid_retrieval_phase")
            decision = phase.get("decision") or {}
            ids = set(decision.get("selected_chunk_ids") or [])
            rows = {r.get("chunk_id"): r for r in phase.get("candidates", []) if isinstance(r, dict)}
            if not ids <= set(rows):
                raise ValueError("selected_chunk_not_in_retrieval_candidates")
            if ids and phase.get("retrieval_status") not in ("completed", "completed_with_candidates"):
                raise ValueError("selected_chunk_from_incomplete_search")
            if ids and phase.get("triage_status") not in (None, "completed"):
                raise ValueError("selected_chunk_from_failed_triage")
            for cid in ids:
                row = rows[cid]
                if not isinstance(row.get("legal_quote"), str) or not row["legal_quote"]:
                    raise ValueError("selected_chunk_without_exact_quote")
                if not re.fullmatch(r"[0-9a-fA-F]{64}", str(row.get("file_hash") or "")):
                    raise ValueError("selected_chunk_without_source_hash")
                selected[cid] = {"chunk_id": cid, "legal_quote": row["legal_quote"],
                                 "file_hash": row.get("file_hash"), "packet_role": "triage_selected_candidate"}
    return {"origin": "captured_from_completed_retrieval_before_final_packet",
            "retrieval_audit_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "task_sha256": hashlib.sha256(task_canonical.encode("utf-8")).hexdigest(),
            "retrieval_audit": deepcopy(audit_levels),
            "selected_chunks": [selected[k] for k in sorted(selected)]}


def audit_preflight(task: dict[str, Any], final_user_content: str,
                    selected_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Check what will actually be sent; do not repair or enlarge the packet.

    selected_chunks are the frozen output of issue-specific retrieval/triage.
    This does not decide whether a legal source is substantively applicable.
    """
    scope = audit_task(task)
    errors = list(scope["issues"])
    try:
        packet = json.loads(final_user_content)
    except (TypeError, ValueError):
        packet = None
        errors.append("unparseable_final_user_content")
    if not isinstance(packet, dict):
        packet = {}
    actual_task = packet.get("task")
    if actual_task is None:
        errors.append("locked_task_absent_from_final_request")
    elif actual_task != task:
        errors.append("locked_task_changed_in_final_request")
    evidence = packet.get("laws", packet.get("retrieved_legal_evidence"))
    if not isinstance(evidence, list):
        evidence = []
        errors.append("final_evidence_packet_missing")
    by_id = {}
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("chunk_id"), str):
            errors.append("invalid_final_evidence_item")
            continue
        if item["chunk_id"] in by_id:
            errors.append("duplicate_final_chunk_id")
        by_id[item["chunk_id"]] = item
    selected_ids = set()
    for selected in selected_chunks:
        if not isinstance(selected, dict) or not isinstance(selected.get("chunk_id"), str):
            errors.append("invalid_selected_chunk")
            continue
        cid = selected["chunk_id"]
        selected_ids.add(cid)
        actual = by_id.get(cid)
        if actual is None:
            errors.append(f"selected_chunk_lost_before_final_request:{cid}")
        selected_text = selected.get("legal_quote", selected.get("text"))
        actual_text = actual.get("legal_quote", actual.get("text")) if actual else None
        if actual is not None and isinstance(selected_text, str) and actual_text != selected_text:
            errors.append(f"selected_chunk_text_changed:{cid}")
        selected_hash = selected.get("file_hash", selected.get("source_sha256"))
        actual_hash = actual.get("file_hash", actual.get("source_sha256")) if actual else None
        if actual is not None and selected_hash and str(selected_hash).lower() != str(actual_hash or "").lower():
            errors.append(f"selected_chunk_source_hash_changed:{cid}")
    extra = set(by_id) - selected_ids
    if extra:
        errors.extend(f"unselected_law_in_final_request:{cid}" for cid in sorted(extra))
    return {"status": "blocked_before_inference" if errors else "ready_for_inference",
            "errors": sorted(set(errors)), "task_audit": scope,
            "selected_chunk_count": len(selected_ids), "final_chunk_count": len(by_id),
            "model_called": False, "legal_applicability_verified": False}
