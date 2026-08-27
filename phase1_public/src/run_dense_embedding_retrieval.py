"""Run the approved local dense-embedding and hybrid retrieval comparison.

The script uses a local Chinese sentence-embedding model and the same 60-row
final synthetic gold set / 678-chunk local corpus used by the sparse baselines.
It does not call any external legal-information website, LLM or human-review
loop. The model download, if the model is not cached, is a model dependency
operation rather than legal evidence retrieval.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_embedding_hybrid_retrieval import (  # noqa: E402
    AUTHORITY_POLICY,
    BM25_WEIGHT,
    CORPUS,
    LABELS,
    OUT_DIR,
    TOP_K,
    VECTOR_WEIGHT,
    authority_score,
    bm25_rank,
    build_index,
    evaluate,
    item,
    load_jsonl,
    summarise,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = os.environ.get("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
MODEL_CACHE = ROOT / "embedding_models"


def dense_hybrid_rank(
    lexical_scored: list[tuple[float, int]],
    dense_scores: np.ndarray,
    chunks: list[dict],
) -> list[tuple[float, int, float, float, float]]:
    lexical_by_idx = {idx: score for score, idx in lexical_scored}
    max_lexical = max(lexical_by_idx.values(), default=1.0) or 1.0
    rows = []
    for idx in range(len(chunks)):
        lexical_norm = lexical_by_idx[idx] / max_lexical
        dense_score = max(0.0, float(dense_scores[idx]))
        base = BM25_WEIGHT * lexical_norm + VECTOR_WEIGHT * dense_score
        authority = authority_score(chunks[idx])
        final = 0.85 * base + 0.15 * authority
        rows.append((final, idx, lexical_norm, dense_score, authority))
    return sorted(rows, key=lambda x: (-x[0], chunks[x[1]]["chunk_id"]))


def run() -> None:
    chunks = load_jsonl(CORPUS)
    labels = load_jsonl(LABELS)
    token_counts, idf, _postings, avg_len = build_index(chunks)
    model = SentenceTransformer(MODEL_NAME, cache_folder=str(MODEL_CACHE), device="cpu")
    corpus_embeddings = model.encode(
        [chunk["text"] for chunk in chunks],
        batch_size=16,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    query_embeddings = model.encode(
        [label["document_excerpt"] for label in labels],
        batch_size=16,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    cases = []
    for label, query_embedding in zip(labels, query_embeddings):
        query = label["document_excerpt"]
        gold_ids = set(label["legal_basis_chunk_ids"])
        lexical_scored = bm25_rank(query, chunks, token_counts, idf, avg_len)
        dense_scores = corpus_embeddings @ query_embedding
        dense_scored = sorted(
            ((float(score), idx) for idx, score in enumerate(dense_scores)),
            key=lambda x: (-x[0], chunks[x[1]]["chunk_id"]),
        )
        hybrid_scored = dense_hybrid_rank(lexical_scored, dense_scores, chunks)

        lexical_items = [
            item(rank, chunks[idx], score, gold_ids, bm25_score=score)
            for rank, (score, idx) in enumerate(lexical_scored[:TOP_K], start=1)
        ]
        dense_items = [
            item(rank, chunks[idx], score, gold_ids, dense_cosine=score)
            for rank, (score, idx) in enumerate(dense_scored[:TOP_K], start=1)
        ]
        hybrid_items = [
            item(
                rank,
                chunks[idx],
                final,
                gold_ids,
                hybrid_score=final,
                bm25_normalized=lexical_norm,
                dense_cosine=dense_score,
                authority_score=authority,
            )
            for rank, (final, idx, lexical_norm, dense_score, authority) in enumerate(hybrid_scored[:TOP_K], start=1)
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
                "dense_embedding": {"top_k": dense_items, "evaluation": evaluate(dense_items, gold_ids)},
                "hybrid_bm25_dense_embedding": {"top_k": hybrid_items, "evaluation": evaluate(hybrid_items, gold_ids)},
            }
        )

    output = {
        "test_version": "dense_embedding_hybrid_retrieval_comparison_v1",
        "test_date": str(date.today()),
        "corpus": str(CORPUS),
        "labels": str(LABELS),
        "rows": len(labels),
        "corpus_chunks": len(chunks),
        "query_policy": "document_excerpt_only; gold legal basis is evaluation-only",
        "top_k": TOP_K,
        "embedding_model": {
            "name": MODEL_NAME,
            "cache_folder": str(MODEL_CACHE),
            "dimension": int(corpus_embeddings.shape[1]),
            "normalized_embeddings": True,
            "device": "cpu",
        },
        "modes": ["lexical_bm25", "dense_embedding", "hybrid_bm25_dense_embedding"],
        "parameters": {
            "bm25_weight": BM25_WEIGHT,
            "dense_weight": VECTOR_WEIGHT,
            "hierarchy_mix": {"hybrid_relevance": 0.85, "authority_score": 0.15},
            "authority_policy": AUTHORITY_POLICY,
        },
        "external_retrieval": {"called": False, "sources": [], "note": "Local corpus only."},
        "human_review": {"called": False, "note": "Gold labels are evaluation inputs, not runtime adjudication."},
        "cases": cases,
        "summaries": [
            summarise(cases, "lexical_bm25"),
            summarise(cases, "dense_embedding"),
            summarise(cases, "hybrid_bm25_dense_embedding"),
        ],
        "limitations": [
            "The final set is synthetic and not a real procurement case dataset.",
            "The eight rows with empty legal_basis_chunk_ids remain abstention cases; retrieval scores do not establish a legal basis.",
            "The dense model comparison is a retrieval experiment, not a legal conclusion or LLM reasoning evaluation.",
            "External fallback, NPC database verification, CECN verification, LLM reasoning and human review are not part of this run.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / "dense_comparison_v1.json").open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    with (OUT_DIR / "dense_comparison_v1.md").open("w", encoding="utf-8") as handle:
        handle.write("# Dense embedding / hybrid retrieval comparison v1\n\n")
        handle.write(f"本次运行使用60条 final synthetic gold issues、678个本地法规chunks和模型 `{MODEL_NAME}`（维度 {corpus_embeddings.shape[1]}）。\n\n")
        handle.write("## Summary\n\n")
        handle.write("| Mode | Supported cases | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Unsupported/abstention cases |\n|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for summary in output["summaries"]:
            handle.write("| {mode} | {supported_cases} | {recall_at_1:.3f} | {recall_at_3:.3f} | {recall_at_5:.3f} | {recall_at_10:.3f} | {mrr:.3f} | {unsupported_cases_requiring_abstention} |\n".format(**summary))
        handle.write("\n## Interpretation boundary\n\n")
        handle.write("本报告比较本地 BM25、dense embedding 和带法规层级权重的 hybrid ranking。外部检索未调用，人工审查闭环未调用；gold evidence 只用于离线评价。\n")


if __name__ == "__main__":
    run()
