"""Candidate runner for a DeepSeek V4 Flash v9 reasoning validation.

Runtime requests contain only the contract excerpt, project-context status,
and hybrid-retrieved evidence. Gold labels are loaded only to obtain the
input excerpt and issue identifier; gold legal-basis fields and gold answers
are never placed in the request. Every response is passed through the
deterministic post-LLM gate before it is written as a final result.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from llm_abstention_gate import apply_gate
from llm_response_parser_v1 import channel_diagnostic_snapshot, select_final_response
from run_deepseek_llm_reasoning_smoke import load_api_key, sha256_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = PROJECT_ROOT
PROMPT_FILE = MODEL_ROOT / "prompts" / "system_prompt_final.md"
DENSE_RESULT = MODEL_ROOT / "runs" / "embedding_hybrid_v1" / "dense_comparison_v1.json"
CORPUS_FILE = MODEL_ROOT / "data" / "rag" / "corpus_chunks_public_sample.jsonl"
LABELS_FILE = MODEL_ROOT / "data" / "gold" / "contract_review_final_synthetic_gold_v1.jsonl"
PROJECT_CONTEXT_FILE = MODEL_ROOT / "examples" / "project_context_template.json"
OUT_DIR = MODEL_ROOT / "runs" / "llm_reasoning_batch_v5_v9_deepseek_v4_flash_candidate"
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL_NAME = "deepseek-v4-flash"
REQUEST_TIMEOUT = 120
TOP_K = 5
PARSER_FILE = Path(__file__).with_name("llm_response_parser_v1.py")


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _local_scope_from_title(title: str) -> str:
    for marker in ("四川省", "北京市", "上海市", "广东省", "浙江省", "江苏省"):
        if marker in title:
            return marker
    return "unknown"


def applicability_metadata(chunk: dict, context: dict) -> dict:
    """Derive v5 applicability metadata without using gold labels."""

    level = chunk.get("normative_level")
    if level != "Level 4":
        return {
            "scope_classification": "national_general" if level in {"Level 1", "Level 2", "Level 3"} else "unknown",
            "geographic_scope": "全国",
            "project_type_scope": "general_procurement_or_construction",
            "applicability_status": "matched",
            "applicability_basis": f"runtime normative level {level}",
            "evidence_support_confidence": "high" if level == "Level 1" else "medium",
            "applicability_confidence": "medium",
        }

    location = context.get("project_location") or {}
    location_confirmed = (
        location.get("human_confirmation") == "confirmed"
        and any(location.get(key) for key in ("province", "city", "county"))
    )
    project_type_confirmed = bool(context.get("project_type"))
    local_scope = _local_scope_from_title(chunk.get("title", ""))
    if not location_confirmed:
        status = "missing_location"
        basis = "project location is not human-confirmed"
        applicability_confidence = "insufficient_information"
    elif not project_type_confirmed:
        status = "missing_project_type"
        basis = "project type is not confirmed"
        applicability_confidence = "insufficient_information"
    else:
        status = "matched"
        basis = "location and project type supplied by runtime context"
        applicability_confidence = "medium"
    return {
        "scope_classification": "local_regional",
        "geographic_scope": local_scope,
        "project_type_scope": "construction_or_building_related",
        "applicability_status": status,
        "applicability_basis": basis,
        "evidence_support_confidence": "medium",
        "applicability_confidence": applicability_confidence,
    }


def build_evidence(case: dict, corpus: dict[str, dict], context: dict) -> list[dict]:
    evidence = []
    for ranked in case["hybrid_bm25_dense_embedding"]["top_k"][:TOP_K]:
        chunk = corpus[ranked["chunk_id"]]
        practice_material = (
            chunk.get("source_role") == "practice_material_only"
            or chunk.get("legal_evidence_eligibility") == "supplement_only"
        )
        applicability = applicability_metadata(chunk, context)
        evidence.append(
            {
                "rank": ranked["rank"],
                "chunk_id": chunk["chunk_id"],
                "law": chunk["title"],
                "article": chunk["article"],
                "source_locator": chunk["source_locator"],
                "normative_level": chunk["normative_level"],
                "normative_type": chunk["normative_type"],
                "source_role": chunk["source_role"],
                "parent_source_title": chunk.get("parent_source_title"),
                "corpus_partition": chunk["corpus_partition"],
                "evidence_weight": chunk["evidence_weight"],
                "requires_human_review": chunk["requires_human_review"],
                "citation_ready": chunk.get("citation_ready", not practice_material),
                "independent_legal_evidence": chunk.get("independent_legal_evidence", not practice_material),
                "legal_evidence_eligibility": chunk.get(
                    "legal_evidence_eligibility",
                    "supplement_only" if practice_material else "independent_candidate",
                ),
                "citation_mode": chunk.get(
                    "citation_mode",
                    "contextual_only" if practice_material else "verbatim_source_citation",
                ),
                "jurisdiction_note": chunk.get("jurisdiction_note", ""),
                **applicability,
                "retrieval_scores": {
                    key: ranked[key]
                    for key in (
                        "hybrid_score",
                        "bm25_normalized",
                        "dense_cosine",
                        "authority_score",
                    )
                    if key in ranked
                },
                "legal_quote": chunk["text"],
            }
        )
    return evidence


def build_runtime_input(label: dict, case: dict, corpus: dict[str, dict], context_template: dict) -> dict:
    context = json.loads(json.dumps(context_template, ensure_ascii=False))
    context["project_id"] = label["project_id"]
    location = context.setdefault("project_location", {})
    jurisdiction_status = "confirmed" if location.get("human_confirmation") == "confirmed" else "uncertain"
    return {
            "run_id": f"llm-reasoning-batch-v5-v9-deepseek-v4-flash-{label['issue_id']}",
        "project_id": label["project_id"],
        "issue_id": label["issue_id"],
        "review_scope": {
            "documents_received": [label["document_id"]],
            "documents_not_received_or_missing": ["project location confirmation", "project type confirmation"],
            "jurisdiction_status": jurisdiction_status,
            "retrieval_mode": "local_only",
        },
        "project_context": context,
        "contract_evidence": {
            "document_id": label["document_id"],
            "document_location": label["document_location"],
            "document_excerpt": label["document_excerpt"],
        },
            "retrieved_legal_evidence": build_evidence(case, corpus, context),
        "runtime_constraints": {
            "external_retrieval_called": False,
            "human_review_called": False,
            "gold_labels_available_to_runtime": False,
            "instruction": "按照 system prompt 输出严格 JSON；只能依据给定合同证据、项目上下文和法规 evidence，不能补充未提供的法律知识。",
        },
    }


def call_model(
    api_key: str, system_prompt: str, runtime_input: dict
) -> tuple[int, bool, dict | str, dict | None, str, dict]:
    body = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(runtime_input, ensure_ascii=False, indent=2)},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    payload = response.json()
    choice = payload.get("choices", [{}])[0] if response.ok else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    selected = select_final_response(message)
    diagnostics = {
        "selection_rule": selected["selection_rule"],
        "reasoning_content": channel_diagnostic_snapshot(selected["reasoning_content"]),
        "content": channel_diagnostic_snapshot(selected["content"]),
        "selected_parse_method": selected["selected_parse_method"],
        "selected_response_text": selected["selected_text"],
        "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
        "usage": payload.get("usage"),
    }
    if not response.ok:
        return response.status_code, False, payload, None, "none", diagnostics
    parsed = selected["parsed"]
    selected_text = selected["selected_text"]
    response_channel = selected["selected_channel"]
    raw_response: dict | str = parsed if parsed is not None else selected_text
    return response.status_code, True, raw_response, parsed, response_channel, diagnostics


def main() -> None:
    api_key = load_api_key()
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    dense = json.loads(DENSE_RESULT.read_text(encoding="utf-8"))
    labels = load_jsonl(LABELS_FILE)
    corpus = {row["chunk_id"]: row for row in load_jsonl(CORPUS_FILE)}
    context_template = json.loads(PROJECT_CONTEXT_FILE.read_text(encoding="utf-8"))
    labels_by_issue = {row["issue_id"]: row for row in labels}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUT_DIR / "llm_batch_results.jsonl"
    manifest_path = OUT_DIR / "llm_batch_manifest.json"
    summary_path = OUT_DIR / "llm_batch_summary.md"
    summaries = []

    with results_path.open("w", encoding="utf-8") as handle:
        for index, case in enumerate(dense["cases"], start=1):
            label = labels_by_issue[case["issue_id"]]
            runtime_input = build_runtime_input(label, case, corpus, context_template)
            status_code = None
            request_ok = False
            response_json_valid = False
            raw_response: dict | str = ""
            parsed_response = None
            response_channel = "none"
            response_channel_diagnostics = {}
            response_schema_compatible = False
            error = None
            try:
                (
                    status_code,
                    request_ok,
                    raw_response,
                    parsed_response,
                    response_channel,
                    response_channel_diagnostics,
                ) = call_model(api_key, system_prompt, runtime_input)
                response_json_valid = parsed_response is not None
                selected_diagnostics = response_channel_diagnostics.get(response_channel, {})
                response_schema_compatible = selected_diagnostics.get("schema_compatible", False)
                gate = apply_gate(parsed_response, runtime_input)
            except Exception as exc:  # keep the batch auditable and continue to the next issue
                error = f"{type(exc).__name__}: {exc}"
                gate = apply_gate(None, runtime_input)

            record = {
                "run_id": runtime_input["run_id"],
                "issue_id": label["issue_id"],
                "project_id": label["project_id"],
                "batch_index": index,
                "request_status_code": status_code,
                "request_ok": request_ok,
                "response_json_valid": response_json_valid,
                "response_schema_compatible": response_schema_compatible if request_ok else False,
                "response_channel": response_channel,
                "response_channel_diagnostics": response_channel_diagnostics,
                "selected_parse_method": response_channel_diagnostics.get("selected_parse_method", "none"),
                "selected_response_text": response_channel_diagnostics.get("selected_response_text", ""),
                "finish_reason": response_channel_diagnostics.get("finish_reason"),
                "usage": response_channel_diagnostics.get("usage"),
                "raw_response": raw_response,
                "gated_response": gate["response"],
                "gate": {
                    "status": gate["status"],
                    "blocked": gate["blocked"],
                    "actions": gate["actions"],
                },
                "error": error,
                "audit": {
                    "system_prompt_file": str(PROMPT_FILE),
                    "system_prompt_sha256": sha256_text(system_prompt),
                    "response_parser_file": str(PARSER_FILE),
                    "response_parser_sha256": sha256_text(PARSER_FILE.read_text(encoding="utf-8")),
                    "response_selection_rule": "reasoning_content_if_present_and_JSON_parseable_else_content",
                    "json_repair_policy": "conservative; no heuristic repair of malformed quotes, commas, or missing fields",
                    "retrieval_mode": "hybrid_bm25_dense_embedding",
                    "retrieved_count": len(runtime_input["retrieved_legal_evidence"]),
                    "external_retrieval_called": False,
                    "human_review_called": False,
                    "gold_labels_available_to_runtime": False,
                },
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            summaries.append(record)
            print(json.dumps({
                "index": index,
                "issue_id": label["issue_id"],
                "request_ok": request_ok,
                "json_valid": response_json_valid,
                "gate_status": gate["status"],
            }, ensure_ascii=False))
            time.sleep(0.25)

    gate_counts: dict[str, int] = {}
    conclusion_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    response_channel_counts: dict[str, int] = {}
    parse_method_counts: dict[str, int] = {}
    channel_parse_status_counts: dict[str, dict[str, int]] = {
        "reasoning_content": {},
        "content": {},
    }
    for row in summaries:
        gate_status = row["gate"]["status"]
        gate_counts[gate_status] = gate_counts.get(gate_status, 0) + 1
        for finding in row["gated_response"].get("findings", []):
            conclusion = finding.get("conclusion_type", "missing")
            confidence = finding.get("confidence_assessment", "missing")
            conclusion_counts[conclusion] = conclusion_counts.get(conclusion, 0) + 1
            confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1
        channel = row.get("response_channel", "none")
        response_channel_counts[channel] = response_channel_counts.get(channel, 0) + 1
        parse_method = row.get("selected_parse_method", "none")
        parse_method_counts[parse_method] = parse_method_counts.get(parse_method, 0) + 1
        diagnostics = row.get("response_channel_diagnostics", {})
        for channel_name in ("reasoning_content", "content"):
            status = diagnostics.get(channel_name, {}).get("status", "not_recorded")
            bucket = channel_parse_status_counts[channel_name]
            bucket[status] = bucket.get(status, 0) + 1

    manifest = {
        "run_id": "llm-reasoning-batch-v5-v9-deepseek-v4-flash-candidate",
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": MODEL_NAME,
        "api_endpoint": API_URL,
        "system_prompt_file": str(PROMPT_FILE),
        "system_prompt_sha256": sha256_text(system_prompt),
        "response_parser_file": str(PARSER_FILE),
        "response_parser_sha256": sha256_text(PARSER_FILE.read_text(encoding="utf-8")),
        "rows_requested": len(dense["cases"]),
        "rows_written": len(summaries),
        "requests_ok": sum(row["request_ok"] for row in summaries),
        "json_responses_valid": sum(row["response_json_valid"] for row in summaries),
        "gate_status_counts": gate_counts,
        "conclusion_type_counts": conclusion_counts,
        "confidence_counts": confidence_counts,
        "response_channel_counts": response_channel_counts,
        "selected_parse_method_counts": parse_method_counts,
        "channel_parse_status_counts": channel_parse_status_counts,
        "response_selection_rule": "reasoning_content_if_present_and_JSON_parseable_else_content",
        "json_extraction_methods": [
            "strict_json",
            "markdown_fence",
            "balanced_json_extraction",
        ],
        "json_repair_policy": "conservative; no heuristic repair of malformed quotes, commas, or missing fields",
        "external_retrieval_called": False,
        "human_review_called": False,
        "gold_labels_available_to_runtime": False,
        "gold_fields_excluded_from_runtime": True,
        "results_file": str(results_path),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# LLM reasoning candidate v5 — v9 + DeepSeek V4 Flash",
        "",
        f"- Model: `{MODEL_NAME}`",
        f"- Requested rows: {manifest['rows_requested']}",
        f"- Written rows: {manifest['rows_written']}",
        f"- Successful API responses: {manifest['requests_ok']}",
        f"- Valid JSON responses: {manifest['json_responses_valid']}",
        f"- Gate status: `{json.dumps(gate_counts, ensure_ascii=False)}`",
        f"- Conclusion types after gate: `{json.dumps(conclusion_counts, ensure_ascii=False)}`",
        f"- Confidence after gate: `{json.dumps(confidence_counts, ensure_ascii=False)}`",
        f"- Response channels: `{json.dumps(response_channel_counts, ensure_ascii=False)}`",
        f"- Selected parse methods: `{json.dumps(parse_method_counts, ensure_ascii=False)}`",
        f"- Channel parse statuses: `{json.dumps(channel_parse_status_counts, ensure_ascii=False)}`",
        "- Response selection: reasoning_content when response-shaped JSON is parseable; otherwise content",
        "- JSON normalization: BOM/outer whitespace/fence/surrounding prose extraction only; malformed JSON is not heuristically repaired",
        "- External retrieval: not called",
        "- Human review: not called; outputs remain review-required states",
        "- Gold labels/answers: excluded from runtime requests",
        "",
        "The JSONL file preserves raw model output and the deterministic gated response separately.",
    ]
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"rows_written": len(summaries), "manifest": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
