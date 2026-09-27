"""Offline V1 scope/rule-probe audit for an unchanged full-bundle run.

This is a development router, not a legal conclusion or a recall estimator.
It never rewrites the frozen bundle, its candidate labels, or the legal prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


TOPIC_TERMS = {
    "clarification_or_amendment": ("澄清", "修改招标文件", "补遗", "延长投标截止"),
    "bid_security": ("投标保证金", "保证金有效期", "担保形式"),
    "bid_validity": ("投标有效期",),
    "qualification": ("资格条件", "资质", "资格审查", "营业执照", "安全生产许可证"),
    "bid_ceiling": ("最高投标限价", "最高限价"),
    "evaluation_or_rejection": ("评标标准", "评标办法", "否决其投标", "废标处理"),
    "bid_deadline": ("投标截止", "提交投标文件的截止"),
    "collusion_or_false_qualification": ("串通投标", "以他人名义投标", "弄虚作假"),
}
TENDER_REQUIREMENT = re.compile(
    r"投标人.{0,30}(?:应|须|必须|不得|提供|提交|附)|"
    r"(?:计划工期|投标有效期|投标保证金|投标报价不得|最高投标限价)|"
    r"(?:应附|须附).{0,30}(?:资质|资格|业绩|证书)"
)
TEMPLATE_OR_RECITATION = re.compile(
    r"^(?:备注|注[：:]|第三条|第六条)|本表后应附|"
    r"不同投标人的投标文件异常一致|属于以他人名义投标|"
    r"禁止串通投标|不得串通投标"
)
FORM_BLANK = re.compile(r"_{2,}|（大写）[:：]?\s*_+|人民币.{0,12}____")
INSURANCE = re.compile(r"保险合同|保险事故|保险金额|保险单")
TECHNICAL_PRICING = re.compile(r"工程量清单|综合单价|计价定额|报价依据|赶工费|施工方案")
ACTUAL_BID_ASSERTION = re.compile(r"我方|本公司|本投标人|本项目已|投标人已")
DIRECT_BID_FACT = re.compile(r"已提交|已提供|已缴纳|已使用|实际使用|以.{0,12}资质.{0,12}投标")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def topics(text: str) -> list[str]:
    return [name for name, terms in TOPIC_TERMS.items() if any(t in text for t in terms)]


def classify(issue: dict[str, Any]) -> dict[str, Any]:
    """Conservative *routing* only; no finding, missing-document claim or law admission."""
    task = issue["task"]
    source = issue["primary_source"]
    quote = str(source.get("quote") or "").strip()
    found = topics(quote)
    decision = "scope_uncertain"
    reason = "no_verified_atomic_rule_or_material_requirement"
    if task == "tender_clause_legality":
        if found and not (TECHNICAL_PRICING.search(quote) and not
                          any(t in found for t in ("bid_ceiling", "qualification", "bid_security"))):
            decision, reason = "legal_compliance", "tender_rule_topic_probe_not_legal_verdict"
        elif TECHNICAL_PRICING.search(quote):
            decision, reason = "auxiliary_nonlegal_not_reviewed", "technical_or_pricing_without_legal_bridge"
    elif task == "bid_standalone_legality":
        if source.get("document_key") == "TECH" and not found:
            decision, reason = "auxiliary_nonlegal_not_reviewed", "technical_bid_without_legal_predicate"
        elif INSURANCE.search(quote):
            decision, reason = "auxiliary_nonlegal_not_reviewed", "insurance_terms_not_bidder_conduct"
        elif TEMPLATE_OR_RECITATION.search(quote) or FORM_BLANK.search(quote):
            decision, reason = "auxiliary_nonlegal_not_reviewed", "template_or_rule_recitation_not_bidder_fact"
        elif TECHNICAL_PRICING.search(quote) and not found:
            decision, reason = "auxiliary_nonlegal_not_reviewed", "technical_or_pricing_without_legal_bridge"
        elif "若我方中标" in quote and not DIRECT_BID_FACT.search(quote):
            decision, reason = "auxiliary_nonlegal_not_reviewed", "future_performance_not_current_bid_fact"
        elif found and ACTUAL_BID_ASSERTION.search(quote) and DIRECT_BID_FACT.search(quote):
            decision, reason = "legal_compliance", "candidate_current_bid_fact_requires_evidence_check"
    elif task == "bid_responsiveness":
        pair = issue.get("pairing") or {}
        matches = pair.get("candidate_matches") or []
        if FORM_BLANK.search(quote):
            decision, reason = "auxiliary_nonlegal_not_reviewed", "unfilled_tender_form_not_requirement"
        elif not TENDER_REQUIREMENT.search(quote):
            reason = "tender_block_not_a_clear_bid_requirement"
        elif pair.get("status") != "provisional_match_needs_verification" or not matches:
            reason = "pair_not_verified_missing_is_not_nonresponse"
        else:
            response = str((matches[0].get("source") or {}).get("quote") or "")
            score = float(matches[0].get("score") or 0)
            if FORM_BLANK.search(response) or TEMPLATE_OR_RECITATION.search(response):
                reason = "paired_bid_text_is_template_not_actual_submission"
            elif score < 0.55:
                reason = "weak_textual_pair_requires_matching_review"
            else:
                decision, reason = "material_bid_response", "two_located_texts_for_bounded_comparison"
    else:
        raise ValueError(f"unknown_task:{task}")
    return {"issue_id": issue["issue_id"], "task": task,
            "document_key": source.get("document_key"), "source_block_id": source.get("block_id"),
            "page_number": source.get("page_number"), "scope": decision,
            "reason": reason, "topic_probes": found,
            "not_a_legal_or_responsiveness_finding": True}


def rule_probe_inventory(corpus_path: Path, province: str) -> dict[str, Any]:
    """Locate possible primary-law passages for topics; applicability stays unverified."""
    rows = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    eligible = [r for r in rows if r.get("corpus_partition") == "primary"
                and r.get("normative_level") in {"Level 1", "Level 2", "Level 3", "Level 4"}]
    if province != "四川省":
        eligible = [r for r in eligible if r.get("normative_level") != "Level 4"]
    level_order = {"Level 1": 1, "Level 2": 2, "Level 3": 3, "Level 4": 4}
    inventory = {}
    for topic, terms in TOPIC_TERMS.items():
        hits = []
        for row in eligible:
            text = str(row.get("text") or "")
            score = sum(text.count(term) for term in terms)
            if score:
                hits.append((level_order[row["normative_level"]], -score, row))
        hits.sort(key=lambda x: (x[0], x[1], x[2].get("chunk_id", "")))
        inventory[topic] = [{"chunk_id": r.get("chunk_id"), "title": r.get("title"),
                             "article": r.get("article"), "normative_level": r.get("normative_level"),
                             "source_locator": r.get("source_locator"),
                             "applicability": "unverified_candidate_only"}
                            for _, _, r in hits[:4]]
    return {"source_sha256": sha256(corpus_path), "source_partition": "primary_only",
            "project_province": province, "level4_filter": "province_match_only",
            "rule_probes_are_not_atomic_rules_or_admitted_evidence": True,
            "topics": inventory}


def audit(bundle_dir: Path, selected_ids: list[str], corpus_path: Path, province: str) -> dict[str, Any]:
    intake = json.loads((bundle_dir / "bundle_intake.json").read_text(encoding="utf-8"))
    if not isinstance(selected_ids, list) or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("unique_selected_ids_required")
    issues = json.loads((bundle_dir / "candidates.json").read_text(encoding="utf-8"))
    decisions = [classify(issue) for issue in issues]
    by_id = {row["issue_id"]: row for row in decisions}
    if any(i not in by_id for i in selected_ids):
        raise ValueError("selected_id_not_in_frozen_bundle")
    return {"project_id": intake["project_id"],
            "candidates_sha256": sha256(bundle_dir / "candidates.json"),
            "candidate_labels_sha256": sha256(bundle_dir / "candidate_labels.jsonl"),
            "selected_ids_sha256": hashlib.sha256(json.dumps(selected_ids).encode()).hexdigest(),
            "addenda_status": (intake.get("addenda_inventory") or {}).get("status", "unverified"),
            "scope_is_offline_development_screen_not_recall_or_accuracy": True,
            "counts_by_scope": dict(Counter(row["scope"] for row in decisions)),
            "counts_by_task_and_scope": dict(Counter(f'{row["task"]}:{row["scope"]}' for row in decisions)),
            "selected": [by_id[i] for i in selected_ids],
            "selected_runnable_ids": [i for i in selected_ids if by_id[i]["scope"] in
                                      {"legal_compliance", "material_bid_response"}],
            "selected_needs_scope_review_ids": [i for i in selected_ids if by_id[i]["scope"] == "scope_uncertain"],
            "rule_probe_inventory": rule_probe_inventory(corpus_path, province),
            "all_decisions": decisions}


def scoped_approval(base: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if (base.get("project_id") != report["project_id"]
            or base.get("candidate_labels_sha256") != report["candidate_labels_sha256"]):
        raise ValueError("approval_scope_input_mismatch")
    by_id = {row["issue_id"]: row for row in base.get("approved", [])}
    selected = report["selected_runnable_ids"]
    if any(issue_id not in by_id for issue_id in selected):
        raise ValueError("runnable_issue_not_in_original_pilot")
    return {"project_id": base["project_id"],
            "candidate_labels_sha256": base["candidate_labels_sha256"],
            "source_manifest_sha256": base["source_manifest_sha256"],
            "approved": [by_id[issue_id] for issue_id in selected],
            "privacy_review_complete": False,
            "purpose": "V1_scope_screened_development_smoke_not_accuracy",
            "scope_audit_sha256": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument("--selected-ids", type=Path, required=True)
    parser.add_argument("--law-corpus", type=Path, required=True)
    parser.add_argument("--province", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-approval", type=Path)
    parser.add_argument("--scoped-approval-output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refuse_to_overwrite_scope_audit")
    ids = json.loads(args.selected_ids.read_text(encoding="utf-8"))
    result = audit(args.bundle_output, ids, args.law_corpus, args.province)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.base_approval or args.scoped_approval_output:
        if not args.base_approval or not args.scoped_approval_output:
            raise ValueError("base_and_scoped_approval_paths_required_together")
        if args.scoped_approval_output.exists():
            raise FileExistsError("refuse_to_overwrite_scoped_approval")
        base = json.loads(args.base_approval.read_text(encoding="utf-8"))
        derived = scoped_approval(base, result)
        derived["scope_audit_sha256"] = sha256(args.output)
        args.scoped_approval_output.write_text(
            json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "counts": result["counts_by_scope"],
                      "selected_runnable": result["selected_runnable_ids"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
