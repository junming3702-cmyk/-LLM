"""Replay the caller-locked QX-U30 two-claim guard without a model/API call.

This is a protocol demonstration on a *previously used* input, not an
independent accuracy or recall evaluation. The original result is read-only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from task_subconclusion_v1 import apply_task_gate, build_contract  # noqa: E402


def replay(prior: dict, *, issue_id: str, body_locator: str, index_locator: str) -> dict:
    if prior.get("issue_id") != issue_id:
        raise ValueError("issue_identity_mismatch")
    runtime = prior.get("runtime_input") or {}
    contract = runtime.get("review_task_contract_v2") or {}
    question = contract.get("question_verbatim") or ""
    if contract.get("declared_task_type") != "document_completeness":
        raise ValueError("not_a_document_completeness_task")
    excerpt = (runtime.get("contract_evidence") or {}).get("document_excerpt") or ""
    sections = {name: text.strip() for name, text in re.findall(
        r"\[([A-Z]+-p\d+-b\d+)\]\s*\n(.*?)(?=\n\s*\[[A-Z]+-p\d+-b\d+\]|\Z)",
        excerpt, flags=re.S)}
    body = sections.get(body_locator)
    index = sections.get(index_locator)
    if not body or not index or "进度计划" not in body:
        raise ValueError("body_or_index_source_not_recoverable")
    claims = [{"claim_id": "progress_body", "claim_type": "narrative_visibility"},
              {"claim_id": "progress_chart", "claim_type": "chart_visibility"}]
    sources = [
        {"source_id": body_locator, "document_id": "TECH", "locator": body_locator,
         "source_kind": "text", "text": body},
        {"source_id": index_locator, "document_id": "TECH", "locator": index_locator,
         "source_kind": "text", "text": index},
    ]
    locked = build_contract(issue_id, "document_visibility", claims, sources)
    quote = body[:min(64, len(body))].strip()
    if not quote:
        raise ValueError("body_quote_not_in_original_input")
    candidate = {"issue_id": issue_id, "contract_sha256": locked["contract_sha256"],
                 "subconclusions": [
                     {"claim_id": "progress_body", "status": "observed",
                      "source_refs": [{"source_id": body_locator, "locator": body_locator,
                                       "quote": quote}],
                      "explanation": "正文提及编制施工总进度计划；仅证实该文字可见。"},
                     {"claim_id": "progress_chart", "status": "pending_verification",
                      "source_refs": [],
                      "explanation": "目录标题不证明横道图/网络图已被读到；需核对相应图表页。"},
                 ]}
    return {"prior_issue_id": prior["issue_id"], "input_question": question,
            "prior_result_unchanged": True, "offline_only": True,
            "task_contract": locked, "candidate": candidate,
            "task_gate": apply_task_gate(candidate, locked)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--issue-id", required=True)
    parser.add_argument("--body-locator", required=True)
    parser.add_argument("--index-locator", required=True)
    args = parser.parse_args()
    if args.prior.resolve() == args.out.resolve() or args.out.exists():
        raise ValueError("output_must_be_a_new_separate_file")
    output = replay(json.loads(args.prior.read_text(encoding="utf-8")),
                    issue_id=args.issue_id, body_locator=args.body_locator,
                    index_locator=args.index_locator)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["task_gate"]["status"],
                      "task_completion": output["task_gate"]["response"]["task_completion"],
                      "pending_claim_ids": output["task_gate"]["response"]["pending_claim_ids"],
                      "out": str(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
