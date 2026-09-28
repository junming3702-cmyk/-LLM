"""One-case controlled online check of a missing Level-2 retrieval handoff.

This is a development diagnostic, not an independent QX30 evaluation. The
original QX-U01 inference input, prompt and model settings are bound by hash.
The only source-input change is an answer-free query expansion and one
locally retrieved Level-2 article. Historical results are not rewritten.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hierarchy_cascade_retriever import StrictHierarchyHybridRetriever  # noqa: E402
from retrieval_task_query_v1 import expand_document_acquisition_queries  # noqa: E402
from task_gap_protocol_v1 import attach_audit, prompt_addendum  # noqa: E402
from qx30_task_gap_v12_controlled import (  # noqa: E402
    gate_state, load_compact_contract, one_model_call, reconcile,
)
from llm_abstention_gate import apply_gate, processing_hold  # noqa: E402


ARTICLE_16_CHUNK = "d1a045e563eba90b8893"
OFFICIAL_LEVEL2 = "https://fgw.beijing.gov.cn/fgwzwgk/2024zcwj/flfggz/fg/xzfg/202004/t20200421_3728866.htm"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_once(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def add_level2_candidate(original: dict, candidate: dict, queries: list[str],
                         original_ids: list[str], expanded_ids: list[str]) -> dict:
    runtime = deepcopy(original)
    if runtime.get("issue_id") != "QX-U01":
        raise ValueError("wrong_issue_for_targeted_retest")
    if (runtime.get("project_context") or {}).get("reference_or_award_materials_included") is not False:
        raise ValueError("award_material_not_excluded")
    if candidate.get("chunk_id") != ARTICLE_16_CHUNK or candidate.get("normative_level") != "Level 2":
        raise ValueError("wrong_target_article")
    if candidate.get("article") != "第十六条" or "发售期不得少于5日" not in candidate.get("legal_quote", ""):
        raise ValueError("article_text_not_verified_in_candidate")
    if ARTICLE_16_CHUNK in original_ids or ARTICLE_16_CHUNK not in expanded_ids:
        raise ValueError("targeted_retrieval_change_not_observed")
    if any(row.get("chunk_id") == ARTICLE_16_CHUNK for row in runtime["retrieved_legal_evidence"]):
        raise ValueError("article_already_in_original_inference_input")
    candidate = deepcopy(candidate)
    candidate["source_url"] = OFFICIAL_LEVEL2
    candidate["applicability_status"] = "national_regulation_temporally_verified_2019_to_2022"
    candidate["applicability_basis"] = "Official 2019 revised text; article 16 addresses the sale period for tender documents."
    runtime["retrieved_legal_evidence"].append(candidate)
    runtime["retrieval_queries"] = queries
    runtime["targeted_retrieval_addendum_v13"] = {
        "scope": "QX-U01_only", "source": "local_Level2_corpus_chunk",
        "historical_hierarchy_audit_unchanged": True,
        "original_level2_top5_ids": original_ids,
        "expanded_level2_top5_ids": expanded_ids,
        "added_chunk_id": ARTICLE_16_CHUNK,
        "official_version_url": OFFICIAL_LEVEL2,
        "causal_note": "Evidence delivery changed; this does not establish a gate-only improvement or independent accuracy.",
    }
    return attach_audit(runtime)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v11-pointer", required=True, type=Path)
    parser.add_argument("--v12-binding", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--base-prompt", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--offline-only", action="store_true")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("new_output_directory_required; preserve previous run")

    pointer = read(args.v11_pointer)
    source_path = Path(pointer["source_path"])
    historical = read(source_path)
    original_user_content = historical["final_llm_response"]["request_body"]["messages"][1]["content"]
    original = json.loads(original_user_content)
    # The saved post-run runtime includes an external-recheck audit not sent
    # in the original final request. Compare only the other locked fields.
    stored = historical["runtime_input"]
    allowed_post_run_fields = {"external_retrieval_audit", "external_sources_used"}
    if (set(original) != set(stored) or any(
            original[key] != stored[key] for key in original
            if key not in allowed_post_run_fields)):
        raise ValueError("sent_input_and_stored_runtime_differ_outside_external_audit")
    if original.get("issue_id") != "QX-U01":
        raise ValueError("historical_identity_drift")
    locked_question = original["review_task_contract_v2"]["question_verbatim"]
    queries, expansion = expand_document_acquisition_queries(locked_question, original["retrieval_queries"])
    if not expansion["matched"] or expansion["contains_answer_or_statute_id"]:
        raise ValueError("answer_free_query_expansion_failed")
    retriever = StrictHierarchyHybridRetriever(
        corpus_file=args.corpus, embedding_model=args.embedding_model)
    original_top = retriever.retrieve_many(original["retrieval_queries"], level="Level 2", top_k=5)
    expanded_top = retriever.retrieve_many(queries, level="Level 2", top_k=5)
    target = next((row for row in expanded_top if row.get("chunk_id") == ARTICLE_16_CHUNK), None)
    if target is None:
        raise ValueError("target_not_in_expanded_level2_top5")
    audited = add_level2_candidate(original, target, queries,
                                   [row["chunk_id"] for row in original_top],
                                   [row["chunk_id"] for row in expanded_top])

    base = args.base_prompt.read_text(encoding="utf-8")
    effective = base + load_compact_contract(Path(__file__).resolve().parents[1] / "src" /
                                             "run_hierarchy_gated_llm_smoke.py") + prompt_addendum()
    previous_binding = read(args.v12_binding)
    if (sha(base.encode("utf-8")) != previous_binding["base_prompt_sha256"]
            or sha(effective.encode("utf-8")) != previous_binding["effective_prompt_sha256"]):
        raise ValueError("prompt_drift_from_frozen_v12")
    original_hash = sha(original_user_content.encode("utf-8"))
    if original_hash != pointer["input_sha256"]:
        raise ValueError("original_input_hash_drift")
    if "REF-QX-" in json.dumps(audited, ensure_ascii=False):
        raise ValueError("reference_answer_leakage_marker")
    binding = {
        "design": "QX-U01-targeted-Level2-evidence-delivery-formative-v13",
        "original_input_sha256": original_hash,
        "augmented_input_sha256": sha(json.dumps(audited, ensure_ascii=False, sort_keys=True).encode("utf-8")),
        "source_result_sha256": sha(source_path.read_bytes()),
        "corpus_sha256": retriever.corpus_sha256,
        "effective_prompt_sha256": sha(effective.encode("utf-8")),
        "model": "deepseek-v4-flash", "temperature": 0.1,
        "reasoning_effort": "low", "max_tokens": 16384,
        "reference_or_award_materials_sent": False,
        "retrieval_addendum": audited["targeted_retrieval_addendum_v13"],
        "query_expansion": expansion,
        "not_independent_accuracy": True,
    }
    write_once(args.out / "binding.json", binding)
    if args.offline_only:
        print(json.dumps({"binding": str(args.out / "binding.json"),
                          "article16_retrieved": True, "model_call_count": 0}, ensure_ascii=False))
        return
    if not args.env_file.is_file():
        raise ValueError("environment_file_missing")
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=args.env_file, override=False)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise ValueError("deepseek_key_unavailable")
    response = one_model_call(api_key, effective, audited)
    if response.get("ok") is False:
        gate = processing_hold(response.get("selected_text", ""), audited,
                               "llm_transport_or_http_failure_not_legal_u", failure_class="transport_failure")
    elif response.get("finish_reason") == "length":
        gate = processing_hold(response.get("selected_text", ""), audited,
                               "llm_output_truncated_not_legal_u", failure_class="truncated_output")
    elif not isinstance(response.get("parsed"), dict):
        gate = processing_hold(response.get("selected_text", ""), audited,
                               "llm_final_json_unparseable_not_legal_u", failure_class="invalid_json")
    else:
        gate = apply_gate(response["parsed"], audited)
    gate = reconcile(gate, audited)
    cited_ids = {str(law.get("chunk_id")) for finding in
                 ((gate.get("response") or {}).get("findings") or [])
                 for law in finding.get("legal_evidence", []) if isinstance(law, dict)}
    forbidden_stale = {"0708ceb43ccf18c323b2", "b43221a19bc5c4996abc", "2f1c6fbdaa4e8489b42b"}
    result = {
        "issue_id": "QX-U01", "response": response, "gate": gate,
        "gate_state": gate_state(gate),
        "article16_cited": ARTICLE_16_CHUNK in cited_ids,
        "stale_l3_article_cited": bool(forbidden_stale & cited_ids),
        "source_version_boundary": "Original lower-level evidence was not modified in this one-factor Level-2 delivery check.",
    }
    write_once(args.out / "result.json", result)
    print(json.dumps({"result": str(args.out / "result.json"), "gate": result["gate_state"],
                      "article16_cited": result["article16_cited"],
                      "stale_l3_article_cited": result["stale_l3_article_cited"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
