"""Source-bound tender/bid text comparison, with no legal verdict.

The caller locks the two source excerpts and the exact pairs to compare.
Neither a model answer nor an award result can create or validate those pairs.
This route is deliberately narrower than full bid responsiveness.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re


VERSION = "task-text-comparison-v1"
MODES = {"decimal", "literal_normalized"}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def build_contract(issue_id: str, question: str, tender: dict, bid: dict,
                   checks: list[dict]) -> dict:
    if not issue_id or not question.strip() or not checks:
        raise ValueError("locked_text_comparison_incomplete")
    sources = {"tender": tender, "bid": bid}
    for name, source in sources.items():
        if not isinstance(source, dict) or any(not isinstance(source.get(key), str) or not source[key]
                                               for key in ("source_id", "locator", "text")):
            raise ValueError(f"{name}_source_unbound")
    names: set[str] = set()
    for check in checks:
        if (not isinstance(check, dict) or set(check) != {"field", "mode", "tender_quote", "bid_quote",
                                                          "tender_start", "bid_start"}
                or check["mode"] not in MODES or not check["field"] or check["field"] in names
                or not check["tender_quote"] or not check["bid_quote"]):
            raise ValueError("comparison_check_invalid")
        names.add(check["field"])
        if (not isinstance(check["tender_start"], int) or check["tender_start"] < 0
                or not isinstance(check["bid_start"], int) or check["bid_start"] < 0
                or tender["text"][check["tender_start"]:check["tender_start"] + len(check["tender_quote"])]
                != check["tender_quote"]
                or bid["text"][check["bid_start"]:check["bid_start"] + len(check["bid_quote"])]
                != check["bid_quote"]):
            raise ValueError("comparison_quote_not_in_locked_source")
    base = {"version": VERSION, "issue_id": issue_id, "question": question,
            "sources": deepcopy(sources), "checks": deepcopy(checks)}
    return {**base, "contract_sha256": _digest(base)}


def _normal(value: str, mode: str) -> str | Decimal:
    if mode == "decimal":
        compact = re.sub(r"\s+", "", value)
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(?:平方米|㎡|%|元)?", compact)
        if not match:
            raise ValueError("decimal_quote_contains_other_content")
        try:
            return Decimal(match.group(1))
        except InvalidOperation as exc:
            raise ValueError("invalid_decimal") from exc
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE)


def compare(contract: dict) -> dict:
    """Run and check the locked comparisons; a mismatch is a review item, not law U."""
    raw = deepcopy(contract)
    base = {key: contract.get(key) for key in ("version", "issue_id", "question", "sources", "checks")}
    if contract.get("version") != VERSION or contract.get("contract_sha256") != _digest(base):
        return {"blocked": True, "failure_class": "task_contract_binding_failure",
                "raw_contract": raw, "legal_conclusion_available": False}
    try:
        verified = build_contract(contract["issue_id"], contract["question"],
                                  contract["sources"]["tender"], contract["sources"]["bid"],
                                  contract["checks"])
        if verified["contract_sha256"] != contract["contract_sha256"]:
            raise ValueError("comparison_contract_hash_mismatch")
        observations = []
        for check in contract["checks"]:
            tender_value = _normal(check["tender_quote"], check["mode"])
            bid_value = _normal(check["bid_quote"], check["mode"])
            observations.append({
                "field": check["field"], "status": "matched" if tender_value == bid_value else "different",
                "tender_source_id": contract["sources"]["tender"]["source_id"],
                "tender_locator": contract["sources"]["tender"]["locator"],
                "tender_quote": check["tender_quote"],
                "tender_start": check["tender_start"],
                "bid_source_id": contract["sources"]["bid"]["source_id"],
                "bid_locator": contract["sources"]["bid"]["locator"],
                "bid_quote": check["bid_quote"],
                "bid_start": check["bid_start"],
            })
    except (KeyError, TypeError, ValueError) as exc:
        return {"blocked": True, "failure_class": "source_or_check_protocol_failure",
                "reason": str(exc), "raw_contract": raw, "legal_conclusion_available": False}
    all_match = all(item["status"] == "matched" for item in observations)
    return {"blocked": False, "status": "review_required", "legal_conclusion_available": False,
            "response": {"issue_id": contract["issue_id"], "mode": "text_response_comparison",
                         "task_completion": ("observed_within_supplied_scope" if all_match
                                             else "observed_difference_requires_review"),
                         "observations": observations, "legal_conclusion_type": None,
                         "human_review_required": True,
                         "boundary": "Only locked text pairs were compared; no drawing, full-bid or legal conclusion."}}


def route_task(task: dict, excerpt: str) -> dict:
    """Conservative pre-inference route; does not rewrite the question."""
    question = str(task.get("question_verbatim") or "")
    textual_question = bool(re.search(r"文字|表述", question) and re.search(r"回应|一致|相符", question))
    legal_question = bool(re.search(r"合法|合规|法定|违反|违法|废标|实质性响应", question))
    two_sources = "[TENDER-" in excerpt and ("[TECH-" in excerpt or "[BID-" in excerpt)
    eligible = (task.get("declared_task_type") == "document_response" and textual_question
                and not legal_question and two_sources)
    return {"route": "text_response_comparison" if eligible else "legal_or_other_task",
            "rule_id": "explicit_two_source_text_question_v1", "question_unchanged": True,
            "why": {"text_question": textual_question, "legal_question": legal_question,
                    "two_sources": two_sources}}
