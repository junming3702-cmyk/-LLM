"""Strict Level 1 -> Level 4 hybrid retrieval for Phase 2.

This module fixes the runtime mismatch between the approved prompt and the
older global hybrid benchmark.  It never mixes normative levels before the
caller has completed the state decision for the current level.  The caller
(normally ``run_hierarchy_gated_llm_smoke.py``) is responsible for asking the
LLM to classify the current level as one of the approved cascade states.

Gold labels are deliberately absent from this module.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sentence_transformers import SentenceTransformer

from run_embedding_hybrid_retrieval import BM25_WEIGHT, VECTOR_WEIGHT
from run_retrieval_test import bm25_rank, build_index


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ.get("MODEL_PHASE_ROOT", PACKAGE_ROOT)).expanduser().resolve()
CORPUS_FILE = Path(os.environ.get("RAG_CORPUS_FILE", MODEL_ROOT / "data" / "rag" / "corpus_chunks.jsonl")).expanduser().resolve()
MODEL_CACHE = Path(os.environ.get("EMBEDDING_MODEL_CACHE", MODEL_ROOT / ".local_cache" / "embedding_models")).expanduser().resolve()
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
LEVEL_ORDER = ("Level 1", "Level 2", "Level 3", "Level 4")

PRIMARY_PARTITIONS = {"primary", "verification"}
SUPPLEMENT_PARTITIONS = {"supplement", "warning"}
SUPPLEMENT_ROLES = {"supplementary_document", "practice_material_only"}


def resolve_local_embedding_model(model_name: str, cache_root: Path = MODEL_CACHE) -> Path:
    """Resolve a SentenceTransformers model without any network fallback.

    Phase 2 records the canonical model id in manifests, while loading the
    already-cached snapshot by path.  A missing local snapshot fails closed so
    that an offline reproducibility run cannot silently download or substitute
    a model.
    """

    explicit = Path(model_name)
    if explicit.exists():
        return explicit.resolve()
    model_dir = cache_root / f"models--{model_name.replace('/', '--')}" / "snapshots"
    candidates = sorted(
        path for path in model_dir.glob("*")
        if path.is_dir() and (path / "modules.json").exists()
    )
    if not candidates:
        raise FileNotFoundError(
            f"No local SentenceTransformers snapshot for {model_name!r} under {model_dir}. "
            "Phase 2 forbids network fallback."
        )
    return candidates[-1].resolve()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_phase(chunk: dict[str, Any]) -> str:
    """Return the within-level retrieval phase without changing authority."""

    if (
        chunk.get("corpus_partition") in SUPPLEMENT_PARTITIONS
        or chunk.get("source_role") in SUPPLEMENT_ROLES
        or chunk.get("legal_evidence_eligibility") == "supplement_only"
    ):
        return "supplement"
    return "primary"


def level4_context_status(project_context: dict[str, Any]) -> dict[str, Any]:
    """Apply the approved Level-4 location and project-type precondition."""

    location = project_context.get("project_location") or {}
    location_value = next(
        (str(location.get(key)).strip() for key in ("province", "city", "county") if location.get(key)),
        "",
    )
    location_confirmed = bool(location_value) and location.get("human_confirmation") == "confirmed"
    project_type = str(project_context.get("project_type") or "").strip()
    if not location_confirmed:
        return {
            "status": "blocked_missing_jurisdiction_context",
            "location_confirmed": False,
            "project_type_confirmed": bool(project_type),
            "reason": "Level 4 cannot become usable evidence without a confirmed project location.",
        }
    if not project_type:
        return {
            "status": "blocked_missing_project_type",
            "location_confirmed": True,
            "project_type_confirmed": False,
            "reason": "Level 4 cannot become usable evidence without a confirmed project type.",
        }
    return {
        "status": "eligible_for_applicability_check",
        "location_confirmed": True,
        "project_type_confirmed": True,
        "reason": "Location and project type are present; each retrieved source still requires scope matching.",
    }


@dataclass(frozen=True)
class RankedCandidate:
    chunk: dict[str, Any]
    hybrid_score: float
    bm25_normalized: float
    dense_cosine: float

    def as_dict(self, rank: int) -> dict[str, Any]:
        row = self.chunk
        practice_only = (
            row.get("source_role") == "practice_material_only"
            or row.get("legal_evidence_eligibility") == "supplement_only"
        )
        return {
            "rank_within_level_phase": rank,
            "chunk_id": row.get("chunk_id"),
            "law": row.get("title"),
            "article": row.get("article"),
            "source_locator": row.get("source_locator"),
            "normative_level": row.get("normative_level"),
            "normative_type": row.get("normative_type"),
            "source_role": row.get("source_role"),
            "corpus_partition": row.get("corpus_partition"),
            "citation_ready": bool(row.get("citation_ready", not practice_only)),
            "independent_legal_evidence": bool(row.get("independent_legal_evidence", not practice_only)),
            "legal_evidence_eligibility": row.get(
                "legal_evidence_eligibility",
                "supplement_only" if practice_only else "independent_candidate",
            ),
            "requires_human_review": bool(row.get("requires_human_review", False)),
            "retrieval_scores": {
                "hybrid_score": round(self.hybrid_score, 6),
                "bm25_normalized": round(self.bm25_normalized, 6),
                "dense_cosine": round(self.dense_cosine, 6),
            },
            "legal_quote": row.get("text", ""),
        }


class StrictHierarchyHybridRetriever:
    """Hybrid retriever whose public API can only query one level at a time."""

    def __init__(
        self,
        corpus_file: Path = CORPUS_FILE,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        device: str = "cpu",
    ) -> None:
        self.corpus_file = Path(corpus_file)
        self.corpus = load_jsonl(self.corpus_file)
        self.corpus_sha256 = sha256_file(self.corpus_file)
        self.embedding_model_name = embedding_model
        self.embedding_model_source = resolve_local_embedding_model(embedding_model)
        self.model = SentenceTransformer(
            str(self.embedding_model_source),
            device=device,
            local_files_only=True,
        )
        self.embeddings = self.model.encode(
            [row.get("text", "") for row in self.corpus],
            batch_size=16,
            show_progress_bar=False,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        self.level_phase_indices: dict[tuple[str, str], list[int]] = {}
        for idx, row in enumerate(self.corpus):
            level = row.get("normative_level")
            if level in LEVEL_ORDER:
                self.level_phase_indices.setdefault((level, source_phase(row)), []).append(idx)

    def counts(self) -> dict[str, dict[str, int]]:
        return {
            level: {
                phase: len(self.level_phase_indices.get((level, phase), []))
                for phase in ("primary", "supplement")
            }
            for level in LEVEL_ORDER
        }

    def retrieve(
        self,
        query: str,
        *,
        level: str,
        phase: str = "primary",
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if level not in LEVEL_ORDER:
            raise ValueError(f"Unsupported normative level: {level}")
        if phase not in {"primary", "supplement"}:
            raise ValueError(f"Unsupported within-level phase: {phase}")
        indices = self.level_phase_indices.get((level, phase), [])
        if not indices:
            return []
        subset = [self.corpus[idx] for idx in indices]
        token_counts, idf, _postings, avg_len = build_index(subset)
        lexical = bm25_rank(query, subset, token_counts, idf, avg_len)
        lexical_by_local_idx = {idx: score for score, idx in lexical}
        max_lexical = max(lexical_by_local_idx.values(), default=1.0) or 1.0
        query_embedding = self.model.encode(
            [query], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )[0]
        dense = self.embeddings[indices] @ query_embedding
        ranked: list[RankedCandidate] = []
        for local_idx, corpus_idx in enumerate(indices):
            lexical_norm = lexical_by_local_idx.get(local_idx, 0.0) / max_lexical
            dense_score = max(0.0, float(dense[local_idx]))
            hybrid = BM25_WEIGHT * lexical_norm + VECTOR_WEIGHT * dense_score
            ranked.append(
                RankedCandidate(
                    chunk=self.corpus[corpus_idx],
                    hybrid_score=hybrid,
                    bm25_normalized=lexical_norm,
                    dense_cosine=dense_score,
                )
            )
        ranked.sort(key=lambda item: (-item.hybrid_score, str(item.chunk.get("chunk_id", ""))))
        return [item.as_dict(rank) for rank, item in enumerate(ranked[:top_k], start=1)]

    def retrieve_many(
        self,
        queries: list[str],
        *,
        level: str,
        phase: str = "primary",
        top_k: int = 5,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """Fuse issue-level retrieval queries without mixing authority levels.

        Reciprocal-rank fusion is applied only within one normative level and
        one source phase. The legal hierarchy remains owned by the caller.
        """

        cleaned = [str(query).strip() for query in queries if str(query).strip()]
        if not cleaned:
            return []
        merged: dict[str, dict[str, Any]] = {}
        for query_index, query in enumerate(cleaned, start=1):
            for row in self.retrieve(query, level=level, phase=phase, top_k=top_k):
                chunk_id = str(row.get("chunk_id"))
                rank = int(row.get("rank_within_level_phase") or top_k)
                record = merged.setdefault(
                    chunk_id,
                    {
                        "row": row,
                        "rrf_score": 0.0,
                        "best_hybrid_score": float(row.get("retrieval_scores", {}).get("hybrid_score", 0.0)),
                        "query_hits": [],
                    },
                )
                record["rrf_score"] += 1.0 / (rrf_k + rank)
                record["best_hybrid_score"] = max(
                    record["best_hybrid_score"],
                    float(row.get("retrieval_scores", {}).get("hybrid_score", 0.0)),
                )
                record["query_hits"].append(
                    {"query_index": query_index, "query": query, "rank": rank}
                )
        ordered = sorted(
            merged.values(),
            key=lambda item: (
                -item["rrf_score"],
                -item["best_hybrid_score"],
                str(item["row"].get("chunk_id", "")),
            ),
        )[:top_k]
        output: list[dict[str, Any]] = []
        for rank, item in enumerate(ordered, start=1):
            row = dict(item["row"])
            row["rank_within_level_phase"] = rank
            scores = dict(row.get("retrieval_scores") or {})
            scores.update(
                {
                    "rrf_score": round(item["rrf_score"], 8),
                    "best_hybrid_score": round(item["best_hybrid_score"], 6),
                    "query_count": len(cleaned),
                }
            )
            row["retrieval_scores"] = scores
            row["query_hits"] = item["query_hits"]
            output.append(row)
        return output

    def assert_no_cross_level_mix(self, candidates: Iterable[dict[str, Any]], expected_level: str) -> None:
        wrong = [row.get("chunk_id") for row in candidates if row.get("normative_level") != expected_level]
        if wrong:
            raise AssertionError(f"Cross-level candidates detected for {expected_level}: {wrong}")
