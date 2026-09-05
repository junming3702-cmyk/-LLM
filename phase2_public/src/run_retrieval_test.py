"""Run a small BM25 and hierarchy-aware retrieval sanity check.

Queries are built only from synthetic contract excerpts. Gold legal chunk IDs
are used for evaluation, not query construction. No LLM, embedding API or
external retrieval is called.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("MODEL_PHASE_ROOT", PACKAGE_ROOT)).expanduser().resolve()
CORPUS = Path(os.environ.get("RAG_CORPUS_FILE", ROOT / "data" / "rag" / "corpus_chunks.jsonl")).expanduser().resolve()
LABELS = Path(os.environ.get("GOLD_LABELS_FILE", ROOT / "data" / "gold" / "contract_review_final_synthetic_gold_v1.jsonl")).expanduser().resolve()
OUT = Path(os.environ.get("RETRIEVAL_OUTPUT_DIR", ROOT / ".local_runs" / "retrieval")).expanduser().resolve()
OUT.mkdir(parents=True, exist_ok=True)
TOP_K = 10
BM25_K1 = 1.2
BM25_B = 0.75
AUTHORITY_POLICY = {
    "primary": {"Level 1": 1.00, "Level 2": 0.95, "Level 3": 0.90, "Level 4": 0.85},
    "verification": 0.60,
    "supplement": 0.45,
    "warning": 0.25,
    "other": 0.10,
}


def lexical_terms(text: str) -> list[str]:
    terms: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.extend(run[i : i + 2] for i in range(max(0, len(run) - 1)))
    terms.extend(token.lower() for token in re.findall(r"[A-Za-z0-9_]{2,}", text))
    return terms


def authority_score(chunk: dict) -> float:
    partition = chunk.get("corpus_partition")
    if partition == "primary":
        return AUTHORITY_POLICY["primary"].get(chunk.get("normative_level"), 0.70)
    return AUTHORITY_POLICY.get(partition, AUTHORITY_POLICY["other"])


def load_data():
    chunks = []
    with CORPUS.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                chunks.append(json.loads(line))
    labels = []
    with LABELS.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                labels.append(json.loads(line))
    return chunks, labels


def build_index(chunks: list[dict]):
    token_counts = []
    document_frequency: Counter[str] = Counter()
    postings: dict[str, set[int]] = defaultdict(set)
    for idx, chunk in enumerate(chunks):
        counts = Counter(lexical_terms(chunk["text"]))
        token_counts.append(counts)
        for term in counts:
            document_frequency[term] += 1
            postings[term].add(idx)
    n_docs = len(chunks)
    idf = {term: math.log((n_docs + 1) / (df + 1)) + 1 for term, df in document_frequency.items()}
    avg_len = sum(sum(counts.values()) for counts in token_counts) / max(1, n_docs)
    return token_counts, idf, postings, avg_len


def bm25_rank(query: str, chunks: list[dict], token_counts, idf, avg_len):
    query_terms = Counter(lexical_terms(query))
    k1 = BM25_K1
    b = BM25_B
    scored = []
    for idx, chunk in enumerate(chunks):
        counts = token_counts[idx]
        doc_len = sum(counts.values())
        score = 0.0
        for term, qtf in query_terms.items():
            tf = counts.get(term, 0)
            if not tf:
                continue
            denom = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
            score += idf.get(term, 0.0) * ((tf * (k1 + 1)) / denom) * min(qtf, 2)
        scored.append((score, idx))
    return sorted(scored, key=lambda item: (-item[0], chunks[item[1]]["chunk_id"]))


def hierarchy_rank(lexical_scored, chunks):
    max_score = max((score for score, _ in lexical_scored), default=1.0) or 1.0
    reranked = []
    for score, idx in lexical_scored:
        authority = authority_score(chunks[idx])
        normalized = score / max_score
        # Relevance remains dominant; authority only breaks close matches.
        rerank_score = 0.85 * normalized + 0.15 * authority
        reranked.append((rerank_score, score, idx, authority))
    return sorted(reranked, key=lambda item: (-item[0], chunks[item[2]]["chunk_id"]))


def result_item(rank, chunk, score, lexical_score, authority, gold_ids):
    return {
        "rank": rank,
        "chunk_id": chunk["chunk_id"],
        "hit_gold": chunk["chunk_id"] in gold_ids,
        "title": chunk["title"],
        "article": chunk["article"],
        "source_locator": chunk["source_locator"],
        "normative_level": chunk["normative_level"],
        "corpus_partition": chunk["corpus_partition"],
        "bm25_score": round(lexical_score, 6),
        "authority_score": round(authority, 6),
        "final_score": round(score, 6),
        "text_preview": chunk["text"][:220],
    }


def evaluate_case(ranked_items, gold_ids):
    if not gold_ids:
        return {"supported_case": False, "gold_ids": [], "first_gold_rank": None, "requires_abstention": True}
    ranks = [item["rank"] for item in ranked_items if item["chunk_id"] in gold_ids]
    first = min(ranks) if ranks else None
    return {
        "supported_case": True,
        "gold_ids": sorted(gold_ids),
        "first_gold_rank": first,
        "mrr": round(1 / first, 6) if first else 0.0,
        "recall_at_1": bool(first and first <= 1),
        "recall_at_3": bool(first and first <= 3),
        "recall_at_5": bool(first and first <= 5),
        "recall_at_10": bool(first and first <= 10),
        "requires_abstention": False,
    }


def summarize(cases, mode):
    supported = [case[mode]["evaluation"] for case in cases if case[mode]["evaluation"]["supported_case"]]
    unsupported = [case[mode]["evaluation"] for case in cases if not case[mode]["evaluation"]["supported_case"]]
    count = len(supported)
    return {
        "mode": mode,
        "supported_cases": count,
        "unsupported_cases_requiring_abstention": len(unsupported),
        "recall_at_1": round(sum(x["recall_at_1"] for x in supported) / max(1, count), 6),
        "recall_at_3": round(sum(x["recall_at_3"] for x in supported) / max(1, count), 6),
        "recall_at_5": round(sum(x["recall_at_5"] for x in supported) / max(1, count), 6),
        "recall_at_10": round(sum(x["recall_at_10"] for x in supported) / max(1, count), 6),
        "mrr": round(sum(x["mrr"] for x in supported) / max(1, count), 6),
        "evidence_hit_rate_at_5": round(sum(x["recall_at_5"] for x in supported) / max(1, count), 6),
    }


def main() -> None:
    chunks, labels = load_data()
    token_counts, idf, _postings, avg_len = build_index(chunks)
    cases = []
    for label in labels:
        query = label["document_excerpt"]
        lexical_scored = bm25_rank(query, chunks, token_counts, idf, avg_len)
        hierarchy_scored = hierarchy_rank(lexical_scored, chunks)
        gold_ids = set(label["legal_basis_chunk_ids"])
        lexical_items = [
            result_item(rank, chunks[idx], score, score, authority_score(chunks[idx]), gold_ids)
            for rank, (score, idx) in enumerate(lexical_scored[:TOP_K], start=1)
        ]
        hierarchy_items = [
            result_item(rank, chunks[idx], final, lexical, authority, gold_ids)
            for rank, (final, lexical, idx, authority) in enumerate(hierarchy_scored[:TOP_K], start=1)
        ]
        cases.append({
            "issue_id": label["issue_id"],
            "sample_id": label["sample_id"],
            "query": query,
            "gold_evidence_boundary": label["evidence_boundary"],
            "gold_legal_basis_chunk_ids": sorted(gold_ids),
            "lexical_bm25": {"top_k": lexical_items, "evaluation": evaluate_case(lexical_items, gold_ids)},
            "hierarchy_aware_bm25": {"top_k": hierarchy_items, "evaluation": evaluate_case(hierarchy_items, gold_ids)},
        })

    output = {
        "test_version": "retrieval_sanity_check_v1",
        "test_date": str(date.today()),
        "corpus": str(CORPUS),
        "labels": str(LABELS),
        "query_policy": "document_excerpt_only; gold legal basis is evaluation-only",
        "top_k": TOP_K,
        "modes": ["lexical_bm25", "hierarchy_aware_bm25"],
        "parameters": {
            "bm25_k1": BM25_K1,
            "bm25_b": BM25_B,
            "hierarchy_mix": {"lexical_relevance": 0.85, "authority_score": 0.15},
            "authority_policy": AUTHORITY_POLICY,
        },
        "cases": cases,
        "summaries": [summarize(cases, "lexical_bm25"), summarize(cases, "hierarchy_aware_bm25")],
        "limitations": [
            "Only three synthetic findings are used; this is a pipeline sanity check, not a general evaluation.",
            "No embeddings, LLM reasoning, external fallback or human adjudication loop is tested here.",
            "The authority score is a transparent deterministic proxy; applicability, temporal validity and legal effect still require verification.",
        ],
    }
    with (OUT / "retrieval_sanity_check_v1.json").open("w", encoding="utf-8") as fh:
        json.dump(output, fh, ensure_ascii=False, indent=2)

    with (OUT / "retrieval_sanity_check_v1.md").open("w", encoding="utf-8") as fh:
        fh.write("# RAG retrieval sanity check v1\n\n")
        fh.write("本测试只使用 synthetic contract excerpt 构造 query，gold 法规 chunk 仅用于评估，不参与 query 构造。\n\n")
        fh.write("## Summary\n\n| Mode | Supported cases | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Evidence hit rate@5 | Unsupported cases requiring abstention |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for summary in output["summaries"]:
            fh.write("| {mode} | {supported_cases} | {recall_at_1:.3f} | {recall_at_3:.3f} | {recall_at_5:.3f} | {recall_at_10:.3f} | {mrr:.3f} | {evidence_hit_rate_at_5:.3f} | {unsupported_cases_requiring_abstention} |\n".format(**summary))
        fh.write("\n## Case-level results\n\n")
        for case in cases:
            fh.write(f"### {case['issue_id']}\n\n")
            fh.write(f"- Query: {case['query']}\n")
            fh.write(f"- Gold boundary: `{case['gold_evidence_boundary']}`\n")
            fh.write(f"- Gold chunk IDs: `{', '.join(case['gold_legal_basis_chunk_ids']) or 'none'}`\n\n")
            for mode in ("lexical_bm25", "hierarchy_aware_bm25"):
                ev = case[mode]["evaluation"]
                fh.write(f"**{mode}**: first gold rank `{ev['first_gold_rank']}`, MRR `{ev.get('mrr', 'n/a')}`, Recall@5 `{ev.get('recall_at_5', 'n/a')}`, abstention required `{ev['requires_abstention']}`\n\n")
                for item in case[mode]["top_k"][:5]:
                    hit = "✅ gold" if item["hit_gold"] else ""
                    fh.write(f"- #{item['rank']} {hit} `{item['chunk_id']}` — {item['title']} / {item['article']} / {item['corpus_partition']} — {item['text_preview']}\n")
                fh.write("\n")
        fh.write("## Interpretation boundary\n\n")
        fh.write("Three synthetic cases are sufficient only to verify that the pipeline runs and that cited chunk IDs can be found. They do not support claims about model accuracy. The unsupported case must remain a human-review/abstention case even if retrieval returns superficially similar legal text.\n")


if __name__ == "__main__":
    main()
