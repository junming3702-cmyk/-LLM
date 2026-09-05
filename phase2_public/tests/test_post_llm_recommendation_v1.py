#!/usr/bin/env python3
"""Regression checks for deterministic human-review recommendations."""

from copy import deepcopy
from llm_abstention_gate import _default_substantive_recommendation, _unsupported_article_refs


def main() -> int:
    finding = {
        "conclusion_type": "requires_human_legal_review",
        "risk_category": "potential_non_compliance",
        "reasoning_conclusion": "保证金有效期表述与法规要求可能不一致。",
        "recommended_human_action": "不得直接作出废标或否决投标决定。",
        "document_excerpt": "保证金有效期60日，投标有效期90日。",
        "document_location": "第4.1条",
        "legal_evidence": [
            {
                "chunk_id": "x",
                "law": "中华人民共和国招标投标法实施条例",
                "article": "第二十六条",
                "source_locator": "第二十六条",
                # Actual saved-corpus quote, with explicit fixture admission.
                "legal_quote": "[paragraph 52] 第二十六条 招标人在招标文件中要求投标人提交投标保证金的，投标保证金不得超过招标项目估算价的2%。投标保证金有效期应当与投标有效期一致。\n[paragraph 53] 依法必须进行招标的项目的境内投标单位，以现金或者支票形式提交的投标保证金应当从其基本账户转出。\n[paragraph 54] 招标人不得挪用投标保证金。",
                "normative_level": "Level 2",
                "source_role": "primary_candidate",
                "retrieval_admission": "high_trust",
                "verification_status": "verified",
                "applicability_status": "matched",
                "legal_evidence_eligibility": "independent_candidate",
                "citation_ready": True,
                "independent_legal_evidence": True,
                "independent_evidence": True,
            }
        ],
    }
    recommendation = _default_substantive_recommendation(finding)
    text = recommendation["substantive_conclusion"]
    assert "第二十六条 第二十六条" not in text
    assert "否决投标、拒收投标" not in text
    assert "第二十六条" in text
    assert len(recommendation["supporting_legal_evidence"]) == 1
    for mutation in (
        {"legal_quote": ""},
        {"independent_evidence": None},
        {"retrieval_admission": None},
        {"verification_status": "pending_human_verification"},
        {"applicability_status": "mismatch"},
        {"normative_level": "Level 4", "applicability_status": "blocked_missing_jurisdiction_context"},
    ):
        deficient = deepcopy(finding)
        deficient["legal_evidence"][0].update(mutation)
        deficient["assistant_recommendation"] = {
            "substantive_conclusion": "违反第二十六条。",
            "recommended_handling": "按第二十六条处理。",
        }
        negative = _default_substantive_recommendation(deficient)
        assert "第二十六条" not in negative["substantive_conclusion"], mutation
        assert negative["supporting_legal_evidence"] == [], mutation
        assert _unsupported_article_refs("违反第二十六条", deficient["legal_evidence"]) == {"第二十六条"}
    print("post-LLM recommendation fixtures: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
