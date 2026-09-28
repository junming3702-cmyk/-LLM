"""Private-input, zero-API formative check for the approved QX30 repair.

Reads prior frozen inference inputs and v12 results; writes only a new local
run directory. No gold, award, expert scores, or raw contract excerpts are
written to public source control. This is not an independent accuracy test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from hierarchy_cascade_retriever import StrictHierarchyHybridRetriever  # noqa: E402
from retrieval_task_query_v1 import expand_document_acquisition_queries  # noqa: E402
from task_text_comparison_v1 import build_contract, compare, route_task  # noqa: E402


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_source(v11_dir: Path, uid: str) -> tuple[dict, Path]:
    reference = read(v11_dir / f"{uid}.json")
    path = Path(reference["source_path"])
    original = read(path)
    if original["issue_id"] != uid:
        raise ValueError(f"frozen_source_id_mismatch:{uid}")
    return original, path


def split_sources(excerpt: str) -> tuple[dict, dict]:
    markers = list(re.finditer(r"(?m)^\[(TENDER|TECH|BID)-([^\]]+)\]\s*\n?", excerpt))
    if len(markers) != 2 or markers[0].group(1) != "TENDER" or markers[1].group(1) not in {"TECH", "BID"}:
        raise ValueError("exact_tender_and_bid_text_sources_required")
    sources = []
    for index, marker in enumerate(markers):
        stop = markers[index + 1].start() if index + 1 < len(markers) else len(excerpt)
        sources.append({"source_id": marker.group(0).strip(),
                        "locator": marker.group(0).strip().strip("[]"),
                        "text": excerpt[marker.end():stop].strip()})
    return sources[0], sources[1]


def scale_checks(tender: dict, bid: dict) -> tuple[list[dict], list[str]]:
    def numeric_after_scale(text: str) -> list[re.Match[str]]:
        start = text.find("建设规模")
        if start < 0:
            raise ValueError("building_scale_heading_missing")
        return list(re.finditer(r"\d+(?:\.\d+)?", text[start + len("建设规模"):]))

    tender_start = tender["text"].find("建设规模") + len("建设规模")
    bid_start = bid["text"].find("建设规模") + len("建设规模")
    left = numeric_after_scale(tender["text"])
    right = numeric_after_scale(bid["text"])
    if len(left) != len(right) or not left:
        raise ValueError("building_scale_numeric_claims_not_pairable")
    checks = [{"field": f"scale_number_{index:02d}", "mode": "decimal",
               "tender_quote": a.group(), "bid_quote": b.group(),
               "tender_start": tender_start + a.start(), "bid_start": bid_start + b.start()}
              for index, (a, b) in enumerate(zip(left, right, strict=True), start=1)]
    keywords = ("宿舍楼", "浴室", "开水间", "供电", "给排水", "消防")
    missing = [word for word in keywords if word not in tender["text"] or word not in bid["text"]]
    for word in keywords:
        if word in missing:
            continue
        checks.append({"field": f"scale_term_{word}", "mode": "literal_normalized",
                       "tender_quote": word, "bid_quote": word,
                       "tender_start": tender["text"].find(word), "bid_start": bid["text"].find(word)})
    return checks, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v11-dir", type=Path, required=True)
    parser.add_argument("--v12-dir", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--embedding-model", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("output_dir_already_exists; keep prior run immutable")
    before, before_path = frozen_source(args.v11_dir, "QX-U01")
    original_queries = before["runtime_input"]["retrieval_queries"]
    question = before["runtime_input"]["review_task_contract_v2"]["question_verbatim"]
    queries, expansion_audit = expand_document_acquisition_queries(question, original_queries)
    retriever = StrictHierarchyHybridRetriever(corpus_file=args.corpus,
                                               embedding_model=args.embedding_model,
                                               as_of_date="2022-06-21")
    original = retriever.retrieve_many(original_queries, level="Level 2", top_k=5)
    expanded = retriever.retrieve_many(queries, level="Level 2", top_k=5)
    target = "d1a045e563eba90b8893"
    retrieval = {"original_top5": [row["chunk_id"] for row in original],
                 "expanded_top5": [row["chunk_id"] for row in expanded],
                 "target_article16_in_corpus": any(row["chunk_id"] == target for row in retriever.corpus),
                 "target_article16_original_top5": any(row["chunk_id"] == target for row in original),
                 "target_article16_expanded_top5": any(row["chunk_id"] == target for row in expanded),
                 "expansion_audit": expansion_audit}

    u28, u28_path = frozen_source(args.v11_dir, "QX-U28")
    runtime = u28["runtime_input"]
    task = runtime["review_task_contract_v2"]
    excerpt = runtime["contract_evidence"]["document_excerpt"]
    route = route_task(task, excerpt)
    if route["route"] != "text_response_comparison":
        raise ValueError("qx_u28_not_routed_to_text_comparison")
    tender, bid = split_sources(excerpt)
    checks, missing_terms = scale_checks(tender, bid)
    contract = build_contract("QX-U28", task["question_verbatim"], tender, bid, checks)
    comparison = compare(contract)
    if missing_terms or comparison["blocked"]:
        raise ValueError("source_bound_scale_checks_incomplete")
    comparison_summary = {
        "route": route, "task_completion": comparison["response"]["task_completion"],
        "legal_conclusion_available": comparison["legal_conclusion_available"],
        "match_count": sum(row["status"] == "matched" for row in comparison["response"]["observations"]),
        "check_count": len(checks), "tender_locator": tender["locator"], "bid_locator": bid["locator"],
        "missing_terms": missing_terms, "model_call_count": 0,
    }

    risks = {}
    for uid in ("QX-U12", "QX-U23", "QX-U25", "QX-U26"):
        path = args.v12_dir / "online_candidate" / f"{uid}.json"
        saved = read(path)
        delivered = ((saved.get("gate") or {}).get("response") or {}).get("findings") or []
        risks[uid] = {"unchanged_v12_result_sha256": hash_file(path),
                      "delivered_risk": (saved.get("gate") or {}).get("blocked") is False and
                      len(delivered) == 1 and delivered[0].get("conclusion_type") == "requires_human_legal_review",
                      "human_review_status": delivered[0].get("human_review_status") if delivered else None}
    if not all(row["delivered_risk"] for row in risks.values()):
        raise ValueError("approved_risk_regression_failed")
    # A processing hold is not a legal U or an N. These five cases need
    # different recoveries, recorded without changing their frozen findings.
    followup_plan = {
        "QX-U08": ("applicable_specialist_rule", "Verify the source governing the specific manager qualification and its project applicability."),
        "QX-U13": ("specific_tender_condition", "Verify the operative tender condition and any authoritative rule for the certificate-unit mismatch."),
        "QX-U19": ("external_notice_validity", "Independently verify the cited Guizhou extension notice, its temporal scope, and certificate coverage."),
        "QX-U20": ("ocr_date_mapping", "Recover the unreadable permit expiry and start/end-field mapping before time coverage is judged."),
        "QX-U21": ("decisive_estimate_base", "Find the legally required project-estimate base; neither total investment nor bid ceiling is an automatic substitute."),
    }
    other_holds = {}
    for uid, (cause, next_check) in followup_plan.items():
        path = args.v12_dir / "online_candidate" / f"{uid}.json"
        saved = read(path)
        gate = saved.get("gate") or {}
        if gate.get("blocked") is not True or gate.get("failure_class") != "unverified_decisive_gap":
            raise ValueError(f"historical_hold_drift:{uid}")
        other_holds[uid] = {
            "unchanged_v12_result_sha256": hash_file(path),
            "frozen_failure_class": gate["failure_class"],
            "typed_cause": cause,
            "next_check": next_check,
            "auto_N_permitted": False,
            "independent_legal_U_issued": False,
        }
    output = {"design": "QX30-v13-approved-repair-offline-formative",
              "no_api_calls": True, "no_award_or_expert_as_answer": True,
              "not_independent_holdout": True,
              "input_hashes": {"U01": hash_file(before_path), "U28": hash_file(u28_path),
                               "corpus": hash_file(args.corpus)},
              "version_audit": retriever.source_version_audit,
              "U01_level2_retrieval": retrieval, "U28_source_bound_comparison": comparison_summary,
              "approved_risk_regression": risks,
              "remaining_hold_diagnostics": other_holds}
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "offline_report.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "U28_text_pair_review.json").write_text(
        json.dumps({"contract": contract, "comparison": comparison,
                    "scope_note": "13 selected numeric/term pairs only; this is not whole-text, legal, or final bid responsiveness clearance."},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output_dir / "offline_report.json"),
                      "article16_retrieved": retrieval["target_article16_expanded_top5"],
                      "u28": comparison_summary["task_completion"],
                      "approved_risks_retained": len(risks)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
