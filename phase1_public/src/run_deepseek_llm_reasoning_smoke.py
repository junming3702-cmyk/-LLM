"""Run one evidence-grounded DeepSeek reasoning smoke test.

This runner deliberately uses one approved synthetic issue only. It loads the
API key from the user-provided env file without writing or printing the key,
uses the final system prompt, and supplies only the contract excerpt plus the
hybrid-retrieved evidence. Gold legal-basis IDs, gold statements, risk labels,
and reviewer answers are excluded from the runtime request.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from llm_abstention_gate import apply_gate


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = PROJECT_ROOT
ENV_FILE = PROJECT_ROOT / ".env"
PROMPT_FILE = MODEL_ROOT / "prompts" / "system_prompt_final.md"
DENSE_RESULT = MODEL_ROOT / "runs" / "embedding_hybrid_v1" / "dense_comparison_v1.json"
CORPUS_FILE = MODEL_ROOT / "data" / "rag" / "corpus_chunks_public_sample.jsonl"
LABELS_FILE = MODEL_ROOT / "data" / "gold" / "contract_review_final_synthetic_gold_v1.jsonl"
OUT_DIR = MODEL_ROOT / "runs" / "llm_reasoning_smoke_v1"
API_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL_NAME = "deepseek-chat"


def load_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_api_key() -> str:
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"Environment file not found: {ENV_FILE}")
    load_dotenv(dotenv_path=ENV_FILE, override=False)
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY was not loaded from the supplied env file")
    return key


def build_runtime_package() -> tuple[str, dict]:
    system_prompt = PROMPT_FILE.read_text(encoding="utf-8")
    dense = json.loads(DENSE_RESULT.read_text(encoding="utf-8"))
    corpus = {row["chunk_id"]: row for row in load_jsonl(CORPUS_FILE)}
    labels = load_jsonl(LABELS_FILE)

    case = dense["cases"][0]
    label = next(row for row in labels if row["issue_id"] == case["issue_id"])
    retrieved_evidence = []
    for ranked in case["hybrid_bm25_dense_embedding"]["top_k"][:5]:
        chunk = corpus[ranked["chunk_id"]]
        practice_material = (
            chunk.get("source_role") == "practice_material_only"
            or chunk.get("legal_evidence_eligibility") == "supplement_only"
        )
        retrieved_evidence.append(
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
                "citation_ready": chunk.get("citation_ready"),
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

    runtime_input = {
        "run_id": "llm-reasoning-smoke-v1",
        "project_id": label["project_id"],
        "issue_id": label["issue_id"],
        "review_scope": {
            "documents_received": [label["document_id"]],
            "documents_not_received_or_missing": [],
            "jurisdiction_status": "uncertain",
            "retrieval_mode": "local_only",
        },
        "contract_evidence": {
            "document_id": label["document_id"],
            "document_location": label["document_location"],
            "document_excerpt": label["document_excerpt"],
        },
        "retrieved_legal_evidence": retrieved_evidence,
        "runtime_constraints": {
            "external_retrieval_called": False,
            "human_review_called": False,
            "gold_labels_available_to_runtime": False,
            "instruction": "按照 system prompt 输出严格 JSON；只能依据给定合同证据和法规 evidence，不能补充未提供的法律知识。",
        },
    }
    user_content = json.dumps(runtime_input, ensure_ascii=False, indent=2)
    audit = {
        "issue_id": label["issue_id"],
        "system_prompt_file": str(PROMPT_FILE),
        "system_prompt_sha256": sha256_text(system_prompt),
        "corpus_file": str(CORPUS_FILE),
        "retrieval_result_file": str(DENSE_RESULT),
        "retrieval_mode": "hybrid_bm25_dense_embedding",
        "retrieved_count": len(retrieved_evidence),
        "gold_fields_excluded": [
            "risk_category",
            "risk_severity",
            "legal_basis_chunk_ids",
            "legal_basis_locators",
            "gold_risk_statement",
            "evidence_boundary",
            "recommended_human_action",
            "hit_gold",
        ],
        "external_retrieval_called": False,
        "human_review_called": False,
    }
    return system_prompt, {"runtime_input": runtime_input, "user_content": user_content, "audit": audit}


def main() -> None:
    api_key = load_api_key()
    system_prompt, package = build_runtime_package()
    request_body = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": package["user_content"]},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }

    response = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=request_body,
        timeout=120,
    )
    response_payload = response.json()
    answer_text = ""
    parsed_answer = None
    if response.ok:
        answer_text = response_payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        try:
            parsed_answer = json.loads(answer_text)
        except json.JSONDecodeError:
            parsed_answer = None

    gate_result = apply_gate(parsed_answer, package["runtime_input"])

    result = {
        "run_id": "llm-reasoning-smoke-v1",
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "api_endpoint": API_URL,
        "model": MODEL_NAME,
        "request_status_code": response.status_code,
        "request_ok": response.ok,
        "response_json_valid": parsed_answer is not None,
        "raw_response": parsed_answer if parsed_answer is not None else answer_text,
        "response": gate_result["response"],
        "gate": {
            "status": gate_result["status"],
            "blocked": gate_result["blocked"],
            "actions": gate_result["actions"],
        },
        "api_error": None if response.ok else response_payload,
        "audit": package["audit"],
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "runtime_input_package.json").write_text(
        json.dumps(package["runtime_input"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "llm_smoke_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "request_ok": response.ok,
        "status_code": response.status_code,
        "response_json_valid": parsed_answer is not None,
        "output": str(OUT_DIR / "llm_smoke_result.json"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
