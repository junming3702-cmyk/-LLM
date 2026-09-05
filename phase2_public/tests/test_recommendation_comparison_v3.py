"""Offline checks for the active Stage 3 recommendation-comparison contract."""

from __future__ import annotations

from pathlib import Path
import sys


TEST_DIR = Path(__file__).resolve().parent
SRC_DIR = TEST_DIR.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from conclusion_contract_v2 import (  # noqa: E402
    INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM,
    REQUIRES_HUMAN_LEGAL_CONFIRM,
    REQUIRES_HUMAN_LEGAL_REVIEW,
)
from llm_abstention_gate import (  # noqa: E402
    _default_substantive_recommendation,
    _unsupported_article_refs,
)


def _finding(conclusion: str = REQUIRES_HUMAN_LEGAL_REVIEW) -> dict:
    return {
        "issue_id": "SYN-COMPARE-I01",
        "finding_id": "F001",
        "document_location": "第3.2条",
        "document_excerpt": "招标文件发售期为3个自然日。",
        "conclusion_type": conclusion,
        "risk_category": "potential_non_compliance",
        "reasoning_conclusion": "合同约定发售期为3日，法规最低要求为5日，期限少2日。",
        "recommended_human_action": "建议人工核验项目适用范围、发售起止日期和实际执行记录后处理。",
        "fact_law_comparison": {
            "supporting_chunk_id": "law-16",
            "difference_summary": "合同约定发售期为3日，法规最低要求为5日，期限少2日。",
            "legal_requirement": "模型自行改写的法规要求。",
        },
        "runtime_bounded_review": {"eligible": False},
        "confirmation_validation": {"trusted": False},
        "legal_evidence": [
            {
                "chunk_id": "law-16",
                "law": "中华人民共和国招标投标法实施条例",
                "article": "第十六条",
                "source_locator": "第十六条",
                "legal_quote": (
                    "第十六条 招标人应当按照招标公告规定的时间、地点发售招标文件。"
                    "资格预审文件或者招标文件的发售期不得少于5日。"
                ),
                "source_version": "2019-03-02",
                "normative_level": "Level 2",
                "normative_type": "administrative_regulation",
                "source_role": "primary_source",
                "legal_evidence_eligibility": "independent_candidate",
                "independent_legal_evidence": True,
                "independent_evidence": True,
                "applicability_status": "matched",
                "retrieval_admission": "high_trust",
                "verification_status": "locator_gate_passed",
            }
        ],
    }


def test_potential_risk_uses_four_part_structure_and_qualified_language() -> None:
    recommendation = _default_substantive_recommendation(_finding())
    text = recommendation["substantive_conclusion"]
    comparison = recommendation["fact_law_comparison"]
    assert recommendation["recommendation_contract_version"] == "v3"
    assert "（第3.2条）“招标文件发售期为3个自然日。”" in text
    assert "《中华人民共和国招标投标法实施条例》 第十六条" in text
    assert "发售期不得少于5日" in text
    assert "期限少2日" in text
    assert "可能不符合" in text
    assert "模型自行改写的法规要求" not in text
    assert comparison["comparison_status"] == "pending_human_legal_review"
    assert comparison["comparison_source"] == "model_structured_comparison_pending_human_review"
    assert recommendation["recommended_handling"].startswith("建议人工核验")


def test_confirmed_risk_uses_definite_language_only_with_trusted_validation() -> None:
    finding = _finding(REQUIRES_HUMAN_LEGAL_CONFIRM)
    finding["confirmation_validation"] = {"trusted": True}
    recommendation = _default_substantive_recommendation(finding)
    text = recommendation["substantive_conclusion"]
    assert "不符合以下法规要求" in text
    assert "可能不符合" not in text
    assert recommendation["fact_law_comparison"]["comparison_status"] == (
        "runtime_validated_requires_human_legal_confirm"
    )


def test_missing_difference_cannot_be_rendered_as_non_compliance() -> None:
    finding = _finding()
    finding["fact_law_comparison"] = {}
    finding["reasoning_conclusion"] = ""
    recommendation = _default_substantive_recommendation(finding)
    text = recommendation["substantive_conclusion"]
    assert "不能表述为不符合" in text
    assert "可能不符合以下法规要求" not in text
    assert recommendation["fact_law_comparison"]["comparison_status"] == "incomplete_or_not_applicable"


def test_abstention_does_not_manufacture_a_difference() -> None:
    finding = _finding(INSUFFICIENT_INFORMATION_NEEDS_HUMAN_CONFIRM)
    finding["reasoning_conclusion"] = "缺少决定性的项目适用范围。"
    recommendation = _default_substantive_recommendation(finding)
    assert recommendation["substantive_conclusion"] == finding["reasoning_conclusion"]
    assert "可能不符合" not in recommendation["substantive_conclusion"]


def test_arabic_and_chinese_article_numbers_are_equivalent() -> None:
    evidence = _finding()["legal_evidence"]
    assert _unsupported_article_refs("依据该条例第16条进行核对。", evidence) == set()
    assert _unsupported_article_refs("另称第17条。", evidence) == {"第17条"}


def main() -> int:
    tests = [
        test_potential_risk_uses_four_part_structure_and_qualified_language,
        test_confirmed_risk_uses_definite_language_only_with_trusted_validation,
        test_missing_difference_cannot_be_rendered_as_non_compliance,
        test_abstention_does_not_manufacture_a_difference,
        test_arabic_and_chinese_article_numbers_are_equivalent,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
