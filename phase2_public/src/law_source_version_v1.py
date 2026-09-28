"""Fail-closed, 2022-only correction of a stale departmental-regulation source.

The Phase-1 ODT contains the pre-2018 article numbering. Historical corpus
files and results are never rewritten. This overlay retires the whole old
source from *new* 2022 candidate retrieval, then admits only three articles
checked against the cited official revised text. It does not claim to be a
complete replacement of that departmental regulation.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path


OLD_SOURCE_ID = "cd95ceed64ab"
CHECKED_START = date(2022, 1, 1)
CHECKED_END = date(2022, 12, 31)
DEFAULT_SNAPSHOT = (Path(__file__).resolve().parents[1] / "data" / "law"
                    / "qx2022_targeted_l3_articles_v1.json")


def versioned_2022_corpus(rows: list[dict], *, as_of_date: str,
                          snapshot_path: Path = DEFAULT_SNAPSHOT) -> tuple[list[dict], dict]:
    """Return a fresh corpus and provenance audit; never mutate input rows.

    Dates outside the explicitly verified 2022 window are rejected instead
    of silently treating the three excerpts as a current full regulation.
    """

    event_date = date.fromisoformat(as_of_date)
    if not CHECKED_START <= event_date <= CHECKED_END:
        raise ValueError("targeted_departmental_version_not_verified_for_date")
    snapshot_path = Path(snapshot_path)
    payload_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(payload_bytes)
    checked = snapshot.get("checked_articles_only")
    if not isinstance(checked, list) or len(checked) != 3:
        raise ValueError("targeted_source_snapshot_incomplete")
    if len({item["article"] for item in checked}) != len(checked):
        raise ValueError("duplicate_checked_article")
    retired = [row for row in rows if row.get("source_id") == OLD_SOURCE_ID]
    if not retired:
        raise ValueError("stale_source_not_present_in_corpus")
    retired_ids = {row.get("chunk_id") for row in retired}
    if any(item["supersedes_chunk_id"] not in retired_ids for item in checked):
        raise ValueError("checked_article_old_chunk_not_present")
    source_hash = hashlib.sha256(payload_bytes).hexdigest()
    corrected: list[dict] = []
    for item in checked:
        digest = hashlib.sha256(
            (source_hash + item["article"] + item["text"]).encode("utf-8")
        ).hexdigest()
        corrected.append({
            "chunk_id": digest[:20],
            "source_id": "qx2022-targeted-l3-v1",
            "title": snapshot["source_title"] + "（2022适用条款摘录）",
            "normative_level": "Level 3",
            "normative_type": "departmental_regulation",
            "source_role": "primary_candidate",
            "article": item["article"],
            "source_locator": item["article"],
            "chunk_part": 1,
            "text": item["text"],
            "local_file": str(snapshot_path.resolve()),
            "file_hash": source_hash,
            "source_version": snapshot["source_version"],
            "source_url": snapshot["official_text_url"],
            "source_excerpt_sha256": hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
            "supersedes_chunk_id": item["supersedes_chunk_id"],
            "version_audit_boundary": snapshot["boundary"],
            "extraction_status": "VERIFIED_EXCERPT",
            "extraction_method": "official_text_manual_crosscheck",
            "corpus_partition": "primary",
            "evidence_weight": 80,
            "requires_human_review": True,
            "citation_ready": True,
            "independent_legal_evidence": True,
            "legal_evidence_eligibility": "independent_candidate",
        })
    output = [deepcopy(row) for row in rows if row.get("source_id") != OLD_SOURCE_ID]
    output.extend(corrected)
    audit = {
        "as_of_date": as_of_date,
        "old_source_id": OLD_SOURCE_ID,
        "retired_chunk_ids": sorted(str(row.get("chunk_id")) for row in retired),
        "corrected_chunk_ids": [row["chunk_id"] for row in corrected],
        "snapshot_sha256": source_hash,
        "official_text_url": snapshot["official_text_url"],
        "official_2019_amendment_url": snapshot["official_2019_amendment_url"],
        "coverage_boundary": snapshot["boundary"],
    }
    return output, audit
