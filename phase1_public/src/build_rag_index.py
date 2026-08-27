"""Build a deterministic, citation-preserving RAG corpus index.

This step creates canonical chunks and a lightweight lexical postings index.
It deliberately does not create embeddings or make legal applicability
decisions. Each chunk keeps its source hierarchy, role, locator and file hash
so a later LLM can only cite evidence that can be traced back to a local file.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT / "law_extracted"
OUT = ROOT / "rag_index"
OUT.mkdir(parents=True, exist_ok=True)

MAX_CHARS = 1600
OVERLAP = 200


def stable_id(*parts: str, length: int = 20) -> str:
    payload = "|".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Malformed JSON in {path}:{line_no}: {exc}") from exc


def split_text(text: str) -> list[str]:
    text = text.strip()
    if len(text) <= MAX_CHARS:
        return [text] if text else []
    parts = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHARS, len(text))
        if end < len(text):
            boundary = max(text.rfind("。", start, end), text.rfind("；", start, end), text.rfind("\n", start, end))
            if boundary > start + MAX_CHARS // 2:
                end = boundary + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - OVERLAP, start + 1)
    return [part for part in parts if part]


def evidence_policy(record: dict) -> tuple[str, str, int, bool]:
    role = record.get("source_role")
    level = record.get("normative_level")
    if role == "superseded_legacy_duplicate":
        return "excluded", "superseded_duplicate", 0, True
    if record.get("status") == "UNSUPPORTED_LEGACY_DOC":
        return "excluded", "unsupported_legacy_doc", 0, True
    # The DOCX copy is only a title/header; the ODT sibling is the usable copy.
    if record.get("character_count", 0) < 500 and "房屋建筑和市政基础设施工程施工招标投标管理办法" in record.get("title", ""):
        return "excluded", "incomplete_text_duplicate", 0, True
    if role == "practice_material_only":
        return "warning", "non_normative_practice_material", 30, True
    if role == "verification_pending":
        return "warning", "source_verification_pending", 30, True
    if role == "supplementary_document":
        return "supplement", "technical_supplement_to_e_tendering_rule", 45, True
    if role == "verification_copy":
        return "verification", "official_verification_copy", 55, True
    level_weight = {"Level 1": 100, "Level 2": 90, "Level 3": 80, "Level 4": 70}.get(level, 20)
    return "primary", "local_four_level_candidate", level_weight, False


def lexical_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.update(run[i : i + 2] for i in range(max(0, len(run) - 1)))
    terms.update(token.lower() for token in re.findall(r"[A-Za-z0-9_]{2,}", text))
    return terms


def main() -> None:
    for old in OUT.glob("*.jsonl"):
        old.unlink()
    for old in (OUT / "lexical_postings.json").parent.glob("lexical_postings.json"):
        old.unlink()

    chunks = []
    excluded = []
    postings: dict[str, set[str]] = defaultdict(set)
    source_summary = []

    files = sorted(EXTRACTED.glob("*.jsonl"))
    for path in files:
        if path.name == "extraction_manifest.jsonl":
            continue
        records = list(read_jsonl(path))
        if not records:
            continue
        first = records[0]
        partition, reason, weight, requires_review = evidence_policy(first)
        source_info = {
            "source_id": first.get("source_id"),
            "title": first.get("title"),
            "local_file": first.get("local_file"),
            "normative_level": first.get("normative_level"),
            "normative_type": first.get("normative_type"),
            "source_role": first.get("source_role"),
            "parent_source_title": first.get("parent_source_title"),
            "file_hash": first.get("file_hash"),
            "extraction_status": first.get("status"),
            "extraction_method": first.get("extraction_method"),
            "partition": partition,
            "decision_reason": reason,
            "index_eligibility": "excluded" if partition == "excluded" else "candidate",
        }
        source_summary.append(source_info)
        if partition == "excluded":
            excluded.append(source_info)
            continue

        for record in records:
            text = record.get("text", "").strip()
            for part_no, part in enumerate(split_text(text), start=1):
                chunk_id = stable_id(record["source_id"], record.get("article", ""), str(part_no), part)
                item = {
                    "chunk_id": chunk_id,
                    "source_id": record.get("source_id"),
                    "title": record.get("title"),
                    "normative_level": record.get("normative_level"),
                    "normative_type": record.get("normative_type"),
                    "source_role": record.get("source_role"),
                    "parent_source_title": record.get("parent_source_title"),
                    "article": record.get("article"),
                    "source_locator": record.get("source_locator"),
                    "chunk_part": part_no,
                    "text": part,
                    "local_file": record.get("local_file"),
                    "file_hash": record.get("file_hash"),
                    "extraction_status": record.get("status"),
                    "extraction_method": record.get("extraction_method"),
                    "corpus_partition": partition,
                    "evidence_weight": weight,
                    "requires_human_review": requires_review,
                    "citation_ready": record.get("source_role") != "practice_material_only",
                    "independent_legal_evidence": record.get("source_role") != "practice_material_only",
                    "legal_evidence_eligibility": "supplement_only" if record.get("source_role") == "practice_material_only" else "role_dependent",
                    "citation_mode": "contextual_only" if record.get("source_role") == "practice_material_only" else "verbatim_source_citation",
                    "jurisdiction_note": "湖北应用实务背景；不得直接推广至其他辖区" if record.get("source_role") == "practice_material_only" else "",
                    "embedding_status": "not_generated",
                }
                chunks.append(item)
                for term in lexical_terms(part):
                    postings[term].add(chunk_id)

    chunks_path = OUT / "corpus_chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as fh:
        for item in chunks:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    postings_path = OUT / "lexical_postings.json"
    with postings_path.open("w", encoding="utf-8") as fh:
        json.dump({term: sorted(ids) for term, ids in sorted(postings.items())}, fh, ensure_ascii=False, indent=2)

    catalog = {
        "index_version": "rag_corpus_index_v1",
        "build_date": str(date.today()),
        "source_root": "law_sources",
        "extracted_root": str(EXTRACTED),
        "output_root": str(OUT),
        "chunking": {"max_chars": MAX_CHARS, "overlap_chars": OVERLAP, "unit": "article_or_source_block"},
        "index_type": "citation_preserving_lexical_baseline",
        "embedding_status": "not_generated",
        "retrieval_architecture": "local_four_level_primary_then_verified_external_fallback",
        "external_fallback_policy": "external_results_require_human_confirmation",
        "counts": {
            "source_files_seen": len(source_summary),
            "sources_indexed": sum(item["index_eligibility"] == "candidate" for item in source_summary),
            "sources_excluded": len(excluded),
            "chunks_indexed": len(chunks),
            "terms_indexed": len(postings),
        },
        "sources": source_summary,
        "excluded_sources": excluded,
        "artifacts": {
            "chunks": str(chunks_path),
            "lexical_postings": str(postings_path),
        },
        "limitations": [
            "No vector embeddings are generated in this deterministic phase.",
            "Mechanical article segmentation is not legal interpretation.",
            "Verification-pending and supplementary partitions must not be presented as the same authority as primary laws.",
        ],
    }
    with (OUT / "index_catalog.json").open("w", encoding="utf-8") as fh:
        json.dump(catalog, fh, ensure_ascii=False, indent=2)

    with (OUT / "excluded_sources.jsonl").open("w", encoding="utf-8") as fh:
        for item in excluded:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
