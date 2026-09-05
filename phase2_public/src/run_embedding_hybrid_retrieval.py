"""Compare local BM25 with a deterministic vector proxy and hybrid ranking.

This stage is deliberately honest about runtime availability:

* ``lexical_bm25`` is the existing sparse lexical baseline.
* ``char_tfidf_vector_proxy`` is a reproducible character n-gram TF-IDF vector
  baseline implemented with NumPy. It is not a neural embedding model.
* ``hybrid_bm25_char_tfidf_proxy`` combines the two local scores.
* A neural embedding result is marked unavailable unless the optional
  sentence-transformers runtime and a local model are supplied separately.

No external website, LLM or human adjudication loop is called by this script.
The final synthetic gold set is used only for retrieval evaluation; gold legal
chunk IDs are never used to construct a query.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_retrieval_test import (  # noqa: E402
    AUTHORITY_POLICY,
    authority_score,
    bm25_rank,
    build_index,
    lexical_terms,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("MODEL_PHASE_ROOT", PACKAGE_ROOT)).expanduser().resolve()
CORPUS = Path(os.environ.get("RAG_CORPUS_FILE", ROOT / "data" / "rag" / "corpus_chunks.jsonl")).expanduser().resolve()
LABELS = Path(os.environ.get("GOLD_LABELS_FILE", ROOT / "data" / "gold" / "contract_review_final_synthetic_gold_v1.jsonl")).expanduser().resolve()
OUT_DIR = Path(os.environ.get("RETRIEVAL_OUTPUT_DIR", ROOT / ".local_runs" / "retrieval" / "embedding_hybrid_v1")).expanduser().resolve()
TOP_K = 10
VECTOR_WEIGHT = 0.40
BM25_WEIGHT = 0.60


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def vector_features(text: str) -> list[str]:
    """Create stable mixed Chinese character n-grams and ASCII token features."""

    features: list[str] = []
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        for n in (2, 3, 4):
            features.extend(f"c{n}:{run[i:i+n]}" for i in range(max(0, len(run) - n + 1)))
    features.extend(f"w:{token.lower()}" for token in re.findall(r"[A-Za-z0-9_]{2,}", text))
    return features


def build_tfidf_vectors(texts: list[str]) -> tuple[np.ndarray, dict[str, int], dict[str, float]]:
    counts: list[Counter[str]] = []
    document_frequency: Counter[str] = Counter()
    for text in texts:
        current = Counter(vector_features(text))
        counts.append(current)
        document_frequency.update(current.keys())

    vocabulary = {term: idx for idx, term in enumerate(sorted(document_frequency))}
    n_docs = len(texts)
    idf_by_term = {
        term: math.log((n_docs + 1) / (document_frequency[term] + 1)) + 1.0
        for term in vocabulary
    }
    matrix = np.zeros((n_docs, len(vocabulary)), dtype=np.float32)
    for row, current in enumerate(counts):
        for term, frequency in current.items():
            col = vocabulary[term]
            matrix[row, col] = (1.0 + math.log(frequency)) * idf_by_term[term]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.maximum(norms, 1e-12)
    return matrix, vocabulary, idf_by_term


def vector_query(
    query: str,
    vocabulary: dict[str, int],
    idf_by_term: dict[str, float],
    n_features: int,
) -> np.ndarray:
    current = Counter(vector_features(query))
    vector = np.zeros(n_features, dtype=np.float32)
    for term, frequency in current.items():
        if term in vocabulary:
            # Apply the corpus-fitted IDF to the query as well. IDF is never
            # re-estimated from a single query.
            vector[vocabulary[term]] = (1.0 + math.log(frequency)) * idf_by_term[term]
    norm = np.linalg.norm(vector)
    return vector / max(float(norm), 1e-12)


def rank_vector(
    query: str,
    matrix: np.ndarray,
    vocabulary: dict[str, int],
    idf_by_term: dict[str, float],
) -> list[tuple[float, int]]:
    vector = vector_query(query, vocabulary, idf_by_term, matrix.shape[1])
    scores = matrix @ vector
    return sorted(((float(score), idx) for idx, score in enumerate(scores)), key=lambda x: (-x[0], idx_key(x[1])))


def idx_key(idx: int) -> str:
    return str(idx)


def rank_hybrid(
    lexical_scored: list[tuple[float, int]],
    vector_scored: list[tuple[float, int]],
    chunks: list[dict],
) -> list[tuple[float, int, float, float, float]]:
    lexical_by_idx = {idx: score for score, idx in lexical_scored}
    vector_by_idx = {idx: score for score, idx in vector_scored}
    max_lexical = max(lexical_by_idx.values(), default=1.0) or 1.0
    hybrid = []
    for idx in range(len(chunks)):
        lexical_norm = lexical_by_idx[idx] / max_lexical
        vector_score = max(0.0, vector_by_idx[idx])
        base = BM25_WEIGHT * lexical_norm + VECTOR_WEIGHT * vector_score
        authority = authority_score(chunks[idx])
        final = 0.85 * base + 0.15 * authority
        hybrid.append((final, idx, lexical_norm, vector_score, authority))
    return sorted(hybrid, key=lambda x: (-x[0], chunks[x[1]]["chunk_id"]))


def evaluate(ranked_items: list[dict], gold_ids: set[str]) -> dict:
    if not gold_ids:
        return {
            "supported_case": False,
            "gold_ids": [],
            "first_gold_rank": None,
            "mrr": 0.0,
            "recall_at_1": None,
            "recall_at_3": None,
            "recall_at_5": None,
            "recall_at_10": None,
            "requires_abstention": True,
        }
    ranks = [item["rank"] for item in ranked_items if item["chunk_id"] in gold_ids]
    first = min(ranks) if ranks else None
    return {
        "supported_case": True,
        "gold_ids": sorted(gold_ids),
        "first_gold_rank": first,
        "mrr": round(1.0 / first, 6) if first else 0.0,
        "recall_at_1": bool(first and first <= 1),
        "recall_at_3": bool(first and first <= 3),
        "recall_at_5": bool(first and first <= 5),
        "recall_at_10": bool(first and first <= 10),
        "requires_abstention": False,
    }


def summarise(cases: list[dict], mode: str) -> dict:
    evaluations = [case[mode]["evaluation"] for case in cases]
    supported = [item for item in evaluations if item["supported_case"]]
    return {
        "mode": mode,
        "supported_cases": len(supported),
        "unsupported_cases_requiring_abstention": sum(not item["supported_case"] for item in evaluations),
        "recall_at_1": round(sum(item["recall_at_1"] for item in supported) / max(1, len(supported)), 6),
        "recall_at_3": round(sum(item["recall_at_3"] for item in supported) / max(1, len(supported)), 6),
        "recall_at_5": round(sum(item["recall_at_5"] for item in supported) / max(1, len(supported)), 6),
        "recall_at_10": round(sum(item["recall_at_10"] for item in supported) / max(1, len(supported)), 6),
        "mrr": round(sum(item["mrr"] for item in supported) / max(1, len(supported)), 6),
    }


def item(rank: int, chunk: dict, score: float, gold_ids: set[str], **scores) -> dict:
    return {
        "rank": rank,
        "chunk_id": chunk["chunk_id"],
        "hit_gold": chunk["chunk_id"] in gold_ids,
        "title": chunk["title"],
        "article": chunk["article"],
        "source_locator": chunk["source_locator"],
        "normative_level": chunk["normative_level"],
        "corpus_partition": chunk["corpus_partition"],
        "score": round(float(score), 6),
        **{key: round(float(value), 6) for key, value in scores.items()},
        "text_preview": chunk["text"][:220],
    }


def run() -> None:
    chunks = load_jsonl(CORPUS)
    labels = load_jsonl(LABELS)
    token_counts, idf, _postings, avg_len = build_index(chunks)
    matrix, vocabulary, idf_by_term = build_tfidf_vectors([chunk["text"] for chunk in chunks])
    cases = []

    for label in labels:
        query = label["document_excerpt"]
        gold_ids = set(label["legal_basis_chunk_ids"])
        lexical_scored = bm25_rank(query, chunks, token_counts, idf, avg_len)
        vector_scored = rank_vector(query, matrix, vocabulary, idf_by_term)
        hybrid_scored = rank_hybrid(lexical_scored, vector_scored, chunks)

        lexical_items = [
            item(rank, chunks[idx], score, gold_ids, bm25_score=score)
            for rank, (score, idx) in enumerate(lexical_scored[:TOP_K], start=1)
        ]
        vector_items = [
            item(rank, chunks[idx], score, gold_ids, vector_cosine=score)
            for rank, (score, idx) in enumerate(vector_scored[:TOP_K], start=1)
        ]
        hybrid_items = [
            item(
                rank,
                chunks[idx],
                final,
                gold_ids,
                hybrid_score=final,
                bm25_normalized=lexical_norm,
                vector_cosine=vector_score,
                authority_score=authority,
            )
            for rank, (final, idx, lexical_norm, vector_score, authority) in enumerate(hybrid_scored[:TOP_K], start=1)
        ]
        cases.append(
            {
                "issue_id": label["issue_id"],
                "sample_id": label["sample_id"],
                "risk_category": label["risk_category"],
                "evidence_boundary": label["evidence_boundary"],
                "query": query,
                "gold_legal_basis_chunk_ids": sorted(gold_ids),
                "lexical_bm25": {"top_k": lexical_items, "evaluation": evaluate(lexical_items, gold_ids)},
                "char_tfidf_vector_proxy": {"top_k": vector_items, "evaluation": evaluate(vector_items, gold_ids)},
                "hybrid_bm25_char_tfidf_proxy": {"top_k": hybrid_items, "evaluation": evaluate(hybrid_items, gold_ids)},
            }
        )

    sentence_transformers_available = importlib.util.find_spec("sentence_transformers") is not None
    output = {
        "test_version": "embedding_hybrid_retrieval_comparison_v1",
        "test_date": str(date.today()),
        "corpus": str(CORPUS),
        "labels": str(LABELS),
        "rows": len(labels),
        "corpus_chunks": len(chunks),
        "query_policy": "document_excerpt_only; gold legal basis is evaluation-only",
        "top_k": TOP_K,
        "modes": ["lexical_bm25", "char_tfidf_vector_proxy", "hybrid_bm25_char_tfidf_proxy"],
        "parameters": {
            "bm25_weight": BM25_WEIGHT,
            "vector_weight": VECTOR_WEIGHT,
            "hierarchy_mix": {"hybrid_relevance": 0.85, "authority_score": 0.15},
            "authority_policy": AUTHORITY_POLICY,
            "vector_features": "Chinese character n-grams 2-4 plus ASCII token features",
        },
        "neural_embedding_status": {
            "available_runtime": sentence_transformers_available,
            "status": "not_run_missing_runtime_or_local_model",
            "note": "The TF-IDF vector proxy must not be described as a neural embedding result.",
        },
        "external_retrieval": {"called": False, "sources": [], "note": "Local corpus only."},
        "human_review": {"called": False, "note": "Gold labels are evaluation inputs, not runtime adjudication."},
        "cases": cases,
        "summaries": [
            summarise(cases, "lexical_bm25"),
            summarise(cases, "char_tfidf_vector_proxy"),
            summarise(cases, "hybrid_bm25_char_tfidf_proxy"),
        ],
        "limitations": [
            "The final set is synthetic and not a real procurement case dataset.",
            "The 16 insufficient-information rows and seven not-supported-by-current-corpus rows remain abstention cases; this script does not learn an abstention threshold.",
            "The vector mode is a deterministic sparse TF-IDF proxy, not neural embedding retrieval.",
            "External fallback, NPC database verification, CECN verification, LLM reasoning and human review are not part of this run.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "comparison_v1.json").open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    with (OUT_DIR / "comparison_v1.md").open("w", encoding="utf-8") as handle:
        handle.write("# Embedding / hybrid retrieval comparison v1\n\n")
        handle.write("本次运行使用60条 final synthetic gold issues和678个本地法规chunks。\n\n")
        handle.write("注意：当前环境没有可用的 neural embedding runtime/model；因此 `char_tfidf_vector_proxy` 仅是可复现的稀疏向量代理，不得表述为神经 embedding 结果。\n\n")
        handle.write("## Summary\n\n")
        handle.write("| Mode | Supported cases | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Unsupported/abstention cases |\n|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for summary in output["summaries"]:
            handle.write("| {mode} | {supported_cases} | {recall_at_1:.3f} | {recall_at_3:.3f} | {recall_at_5:.3f} | {recall_at_10:.3f} | {mrr:.3f} | {unsupported_cases_requiring_abstention} |\n".format(**summary))
        handle.write("\n## Interpretation boundary\n\n")
        handle.write("本报告只比较本地 lexical baseline 与稀疏向量代理/混合排序。外部检索未调用，人工审查闭环未调用；gold evidence 只用于离线评价。\n")


if __name__ == "__main__":
    run()
