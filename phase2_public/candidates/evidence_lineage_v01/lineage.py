"""Read-only, stage-specific evidence provenance for one frozen or new run.

Never infer retrieval failure from a missing final citation. Historical records
may lack a stage; unknown is an output state, not a reason to fill the gap.
All reference targets are diagnostic-only and must never enter model messages.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

VERSION = "evidence-lineage-v0.1-candidate"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _rows(value: Any) -> list[dict[str, Any]]:
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def final_request_context(result: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Read the actual last user message, never the mutable runtime copy."""
    final = result.get("final_llm_response") or {}
    request = final.get("request_body") or {}
    messages = _rows(request.get("messages"))
    users = [m for m in messages if m.get("role") == "user"]
    if not users or not isinstance(users[-1].get("content"), str):
        return None, "missing_frozen_final_request"
    try:
        payload = json.loads(users[-1]["content"])
    except (ValueError, TypeError):
        return None, "unparseable_frozen_final_request"
    if not isinstance(payload, dict) or not isinstance(payload.get("retrieved_legal_evidence"), list):
        return None, "final_request_missing_evidence_packet"
    return payload, "verified_from_frozen_request"


def retrieval_states(result: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], str]]:
    candidates: dict[str, dict[str, Any]] = {}
    searched: dict[tuple[str, str], str] = {}
    for level in _rows(result.get("cascade_execution_audit")):
        level_name = _text(level.get("level"))
        for phase in _rows(level.get("phases")):
            phase_name = _text(phase.get("phase"))
            key = (level_name, phase_name)
            searched[key] = _text(phase.get("retrieval_status")) or "unknown"
            selected = set((phase.get("decision") or {}).get("selected_chunk_ids") or [])
            for row in _rows(phase.get("candidates")):
                cid = _text(row.get("chunk_id"))
                if cid:
                    candidates[cid] = {"level": level_name, "phase": phase_name,
                                       "rank": row.get("rank_within_level_phase"), "selected": cid in selected,
                                       "candidate_quote_sha256": hashlib.sha256(_text(row.get("legal_quote")).encode("utf-8")).hexdigest()}
        # A Level-4 discovery-only search is not a successful admissibility search.
        if level.get("discovery_only_candidates"):
            searched[(level_name, "primary")] = _text(level.get("retrieval_status")) or "unknown"
            for row in _rows(level.get("discovery_only_candidates")):
                cid = _text(row.get("chunk_id"))
                if cid:
                    candidates[cid] = {"level": level_name, "phase": "primary", "rank": row.get("rank_within_level_phase"),
                                       "selected": False, "discovery_only": True,
                                       "candidate_quote_sha256": hashlib.sha256(_text(row.get("legal_quote")).encode("utf-8")).hexdigest()}
    return candidates, searched


def _output_citations(result: dict[str, Any]) -> tuple[set[str], set[str]]:
    def collect(response: Any) -> set[str]:
        ids: set[str] = set()
        if not isinstance(response, dict):
            return ids
        for finding in _rows(response.get("findings")):
            ids.update(_text(e.get("chunk_id")) for e in _rows(finding.get("legal_evidence")) if e.get("chunk_id"))
        for check in _rows(response.get("completed_checks")):
            ids.update(_text(x) for x in check.get("legal_chunk_ids", []) if _text(x))
        return ids
    raw = (result.get("final_llm_response") or {}).get("parsed")
    gated = (result.get("post_llm_gate") or {}).get("response")
    return collect(raw), collect(gated)


def _parse_status(chunk: dict[str, Any], extracted: list[dict[str, Any]] | None) -> dict[str, Any]:
    if extracted is None:
        return {"status": "unknown", "reason": "extraction_snapshot_not_supplied"}
    matches = [r for r in extracted if r.get("source_id") == chunk.get("source_id")
               and r.get("article") == chunk.get("article")
               and _text(r.get("file_hash")).lower() == _text(chunk.get("file_hash")).lower()
               and _text(chunk.get("text")) and _text(chunk.get("text")) in _text(r.get("text"))]
    if not matches:
        return {"status": "not_verified", "reason": "no_exact_extracted_record_for_chunk"}
    return {"status": "verified", "reason": "exact_text_in_extracted_record_with_matching_source_hash",
            "extract_record_count": len(matches),
            "locators": sorted({_text(r.get("source_locator")) for r in matches if r.get("source_locator")})}


def _original_status(chunk: dict[str, Any], source: dict[str, Any] | None, source_root: Path | None) -> dict[str, Any]:
    if source is None:
        return {"status": "unknown", "reason": "source_not_in_catalog_snapshot"}
    if _text(source.get("file_hash")).lower() != _text(chunk.get("file_hash")).lower():
        return {"status": "identity_conflict", "reason": "catalog_index_file_hash_mismatch"}
    if source_root is None:
        return {"status": "catalog_only", "reason": "original_file_not_verified"}
    path_text = _text(source.get("local_file"))
    if not path_text:
        return {"status": "unknown", "reason": "source_path_missing"}
    root = source_root.resolve()
    path = Path(path_text).resolve()
    if not path.is_relative_to(root):
        return {"status": "unknown", "reason": "source_path_outside_declared_root"}
    if not path.is_file():
        return {"status": "unknown", "reason": "original_file_unavailable"}
    match = sha256(path) == _text(chunk.get("file_hash")).lower()
    return {"status": "verified" if match else "identity_conflict",
            "reason": "original_file_hash_match" if match else "original_file_hash_mismatch"}


def _admission(packet: dict[str, Any] | None) -> dict[str, Any]:
    if packet is None:
        return {"status": "not_reached"}
    if packet.get("applicability_status") == "inapplicable":
        return {"status": "inapplicable", "reason": "upstream_scope_or_geography"}
    if packet.get("temporal_status") == "invalid":
        return {"status": "inapplicable", "reason": "upstream_temporal_invalid"}
    if packet.get("applicability_status") != "applicable" or packet.get("temporal_status") != "valid":
        return {"status": "unknown", "reason": "applicability_or_temporal_not_confirmed"}
    if packet.get("citation_ready") is not True or packet.get("independent_legal_evidence") is not True:
        return {"status": "not_independent", "reason": "source_role_or_citation_not_admitted"}
    return {"status": "admitted_from_upstream_metadata", "semantic_correctness_verified": False}


def _decisive_gap(result: dict[str, Any], chunk_id: str, claim_id: str = "") -> dict[str, Any]:
    """A declared comparison gap is diagnostic, not an independently verified fact."""
    gate = result.get("post_llm_gate") or {}
    if gate.get("status") in ("blocked", "invalid", "failed"):
        return {"status": "unusable_protocol_or_gate_result"}
    gated = gate.get("response") or {}
    if not isinstance(gated, dict):
        return {"status": "unknown"}
    checks = [c for c in _rows(gated.get("completed_checks")) if chunk_id in c.get("legal_chunk_ids", [])]
    claims = {cid for c in checks for cid in c.get("claim_ids", [])}
    if claim_id:
        claims.add(claim_id)
    gaps = [g for g in _rows(gated.get("gaps")) if g.get("task_relation") == "decisive_for_claim"
            and bool(set(g.get("affected_claim_ids", [])) & claims)]
    if gaps:
        return {"status": "model_declared_decisive_gap", "gap_ids": [g.get("gap_id") for g in gaps],
                "independently_verified": False}
    return {"status": "not_demonstrated", "reason": "no_bound_decisive_gap_in_final_protocol"}


def trace_result(result: dict[str, Any], corpus: list[dict[str, Any]], catalog: dict[str, Any] | None,
                 extracted: list[dict[str, Any]] | None, targets: list[str | dict[str, Any]],
                 *, source_root: Path | None = None) -> dict[str, Any]:
    """Produce a no-text diagnostic ledger keyed by exact chunk ID.

    Corpus membership is relative to the supplied index snapshot, not to all
    laws. A missing target can only be called absent from *this* corpus when
    the supplied corpus snapshot is declared complete by the caller.
    """
    by_id = {row["chunk_id"]: row for row in corpus if isinstance(row, dict) and _text(row.get("chunk_id"))}
    if len(by_id) != len(corpus):
        raise ValueError("duplicate_or_invalid_corpus_chunk_id")
    catalog_sources = {s["source_id"]: s for s in _rows((catalog or {}).get("sources")) if _text(s.get("source_id"))}
    candidates, searches = retrieval_states(result)
    request, request_status = final_request_context(result)
    packet_rows = _rows((request or {}).get("retrieved_legal_evidence"))
    packet_by_id = {r["chunk_id"]: r for r in packet_rows if _text(r.get("chunk_id"))}
    duplicate_packet_ids = len(packet_by_id) != len(packet_rows)
    raw_ids, gated_ids = _output_citations(result)
    traces = []
    seen_targets: set[str] = set()
    for item in targets:
        target = item if isinstance(item, str) else _text(item.get("chunk_id"))
        source_id = _text(item.get("source_id")) if isinstance(item, dict) else ""
        article = _text(item.get("article")) if isinstance(item, dict) else ""
        claim_id = _text(item.get("claim_id")) if isinstance(item, dict) else ""
        if not _text(target) and not source_id:
            raise ValueError("empty_target_chunk_id")
        target_key = target or f"{source_id}::{article}"
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        if not target and source_id:
            matching = [r for r in corpus if r.get("source_id") == source_id and
                        (not article or _text(r.get("article")) == article)]
            if matching:
                # Source/article is a selector only. Pass explicit IDs to audit
                # every part of a multi-chunk article.
                target = matching[0]["chunk_id"]
            else:
                source_status = ("present_in_catalog" if source_id in catalog_sources else
                                 "absent_from_supplied_catalog" if catalog is not None else "catalog_unavailable")
                traces.append({"target_source_id": source_id, "target_article": article,
                               "source_library": {"status": source_status},
                               "index": {"status": "absent_in_supplied_snapshot"},
                               "first_break": ("source_not_in_local_library_snapshot" if source_status == "absent_from_supplied_catalog"
                                               else "source_present_but_article_not_indexed" if source_status == "present_in_catalog"
                                               else "library_presence_unknown"),
                               "limits": ["catalog_snapshot_is_not_all_applicable_law"]})
                continue
        chunk = by_id.get(target)
        if chunk is None:
            traces.append({"chunk_id": target, "first_break": "not_in_supplied_index_snapshot",
                           "index": {"status": "absent_in_supplied_snapshot"},
                           "source_library": {"status": "unknown_without_source_id"},
                           "limits": ["not_proof_absent_from_all_law_sources"]})
            continue
        source = catalog_sources.get(chunk.get("source_id"))
        original = _original_status(chunk, source, source_root)
        parsed = _parse_status(chunk, extracted)
        phase = "supplement" if chunk.get("corpus_partition") in ("supplement", "warning") else "primary"
        key = (_text(chunk.get("normative_level")), phase)
        candidate = candidates.get(target)
        candidate_identity = ("unknown" if candidate is None else
                              "matched" if candidate["candidate_quote_sha256"] == hashlib.sha256(_text(chunk.get("text")).encode("utf-8")).hexdigest()
                              else "conflict")
        search_state = searches.get(key, "not_executed")
        packet = packet_by_id.get(target)
        packet_status = "unknown" if request is None else "present" if packet else "absent"
        if packet and (_text(packet.get("legal_quote")) != _text(chunk.get("text"))
                       or _text(packet.get("file_hash")).lower() != _text(chunk.get("file_hash")).lower()):
            packet_status = "identity_conflict"
        admission = _admission(packet if packet_status == "present" else None)
        comparison = _decisive_gap(result, target, claim_id)
        if candidate is None:
            retrieval_status = "not_retrieved" if search_state in ("completed", "completed_no_hit", "completed_with_candidates") else "not_searched_or_failed"
        else:
            retrieval_status = "discovery_only" if candidate.get("discovery_only") else "retrieved"
        citation = {"raw_output": target in raw_ids, "gated_output": target in gated_ids,
                    "output_validation_status": _text((result.get("post_llm_gate") or {}).get("status")) or "unknown"}
        if original["status"] == "identity_conflict" or packet_status == "identity_conflict" or candidate_identity == "conflict":
            break_at = "source_or_packet_identity_conflict"
        elif parsed["status"] == "not_verified":
            break_at = "parse_to_index_not_verified"
        elif retrieval_status == "not_retrieved":
            break_at = "indexed_not_retrieved"
        elif retrieval_status == "not_searched_or_failed":
            break_at = "indexed_but_search_not_completed"
        elif candidate is not None and candidate.get("discovery_only") and packet_status == "present":
            break_at = "discovery_only_delivered_not_independent_basis"
        elif candidate is not None and not candidate.get("selected") and packet_status == "present":
            break_at = "unselected_candidate_in_final_request"
        elif candidate is not None and not candidate.get("selected"):
            break_at = "retrieved_not_selected_for_final_packet"
        elif packet_status == "absent":
            break_at = "selected_but_missing_from_final_request"
        elif packet_status == "unknown":
            break_at = "final_request_unavailable"
        elif admission["status"] == "inapplicable":
            break_at = "in_final_request_but_inapplicable"
        elif admission["status"] != "admitted_from_upstream_metadata":
            break_at = "in_final_request_but_not_admitted"
        elif comparison["status"] == "model_declared_decisive_gap":
            break_at = "admitted_evidence_but_decisive_comparison_gap_declared"
        elif not citation["gated_output"]:
            break_at = "admitted_but_not_cited_in_gated_output_not_necessarily_error"
        else:
            break_at = "cited_with_upstream_admission_metadata_only"
        traces.append({"chunk_id": target, "source_id": chunk.get("source_id"), "article": chunk.get("article"),
                       "normative_level": chunk.get("normative_level"), "source_library": original,
                       "parse": parsed, "index": {"status": "present", "corpus_sha256": None},
                       "retrieval": {"status": retrieval_status, "search_status": search_state,
                                     "candidate_identity": candidate_identity, "candidate": candidate},
                       "final_input": {"status": packet_status, "request_status": request_status},
                       "applicability_admission": admission, "output_citation": citation,
                       "comparison_completion": comparison, "first_break": break_at})
    runtime_contract = (result.get("runtime_input") or {}).get("contract_evidence") or {}
    sent_contract = (request or {}).get("contract_evidence") or {}
    contract_trace = {"document_id": runtime_contract.get("document_id"),
                      "original_document": "unknown_without_original_file_manifest",
                      "parse_and_locator": "unknown_without_ingestor_record",
                      "final_input": "unavailable" if request is None else
                      "same_as_runtime_snapshot" if sent_contract == runtime_contract else "runtime_snapshot_changed_before_final_request",
                      "excerpt_sha256": hashlib.sha256(_text(sent_contract.get("document_excerpt")).encode("utf-8")).hexdigest()
                      if request is not None else None}
    return {"version": VERSION, "run_id": result.get("issue_id"),
            "source_corpus_sha256": None, "source_catalog_present": catalog is not None,
            "extraction_snapshot_present": extracted is not None,
            "request_status": request_status, "duplicate_final_packet_ids": duplicate_packet_ids,
            "target_origin": "diagnostic_only_never_model_input", "target_count": len(traces),
            "contract_input_trace": contract_trace, "traces": traces, "model_calls": 0, "external_retrieval_calls": 0,
            "historical_result_modified": False, "legal_accuracy_claim": None}
