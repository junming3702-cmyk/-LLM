"""Deterministic, answer-free query expansion for tender-document issue dates.

No statute number, minimum number of days, or model/gold answer is injected.
The caller must still retrieve, check applicability, and compare source text.
"""

from __future__ import annotations

import re


def expand_document_acquisition_queries(question: str, queries: list[str]) -> tuple[list[str], dict]:
    cleaned = list(dict.fromkeys(str(q).strip() for q in queries if str(q).strip()))
    # The locked question may say only “文件”; the issue-level retrieval query
    # can supply the document type without supplying any answer or article id.
    task_terms = " ".join([question, *cleaned])
    matched = bool(
        "招标文件" in task_terms
        and re.search(r"获取|领取|发售", question)
        and re.search(r"期限|期间|最短|不少于|天数", question)
    )
    additions = ["招标文件 发售期 最短期限", "招标文件 获取期 发售期限"] if matched else []
    expanded = list(dict.fromkeys(cleaned + additions))
    return expanded, {
        "rule_id": "document_acquisition_duration_synonyms_v1",
        "matched": matched,
        "added_queries": [q for q in additions if q not in cleaned],
        "contains_answer_or_statute_id": False,
    }
