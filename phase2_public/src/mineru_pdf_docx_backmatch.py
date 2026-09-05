#!/usr/bin/env python
"""Evaluate MinerU output from a derived PDF against the original DOCX map.

The formatted PDF is a parsing aid, not a new source. Matching is therefore
performed against the original DOCX baseline locator map, with the chunk's
known original-page scope retained as an audit field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))
from mineru_source_locator_adapter import (  # noqa: E402
    RELIABLE_MAPPING_METHODS,
    RELIABLE_MAPPING_THRESHOLD,
    block_gate_reason,
    build_index,
    critical_tokens,
    load_baseline_locators,
    locate_block,
    normalize_text,
    parse_mineru_blocks,
    scoped_locators,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-locator-map", required=True, type=Path)
    parser.add_argument("--baseline-document-id", required=True)
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--mineru-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--baseline-quality-status", default="needs_human_review")
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    baseline_locators = load_baseline_locators(args.baseline_locator_map)
    split_manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    api_manifest = json.loads((args.mineru_root / "mineru_api_chunked_manifest.json").read_text(encoding="utf-8"))
    by_name = {str(row["chunk_name"]): row for row in api_manifest["records"]}

    all_blocks: list[dict[str, Any]] = []
    chunk_reports: list[dict[str, Any]] = []
    adapted_parts = [
        "# MinerU formatted-PDF branch with original DOCX locators",
        "",
        "<!-- The formatted PDF is a derived parsing aid; original DOCX remains source authority. -->",
        "",
    ]

    for chunk in split_manifest["chunks"]:
        name = str(chunk["chunk_name"])
        record = by_name.get(name, {})
        if record.get("state") != "done":
            chunk_reports.append({"chunk_name": name, "state": record.get("state", "missing"), "error_message": record.get("error_message")})
            continue
        markdown_path = Path(str(record["markdown_path"]))
        markdown = markdown_path.read_text(encoding="utf-8")
        page_scope = set(range(int(chunk["original_page_start"]), int(chunk["original_page_end"]) + 1))
        # The original DOCX baseline uses document-order paragraph locators,
        # not physical page numbers. Do not discard all rows by applying a PDF
        # page filter to a locator map that has no page_number field.
        has_page_numbers = any(row.get("page_number") is not None for row in baseline_locators)
        scoped = scoped_locators(baseline_locators, page_scope) if has_page_numbers else baseline_locators
        index = build_index(scoped)
        blocks = parse_mineru_blocks(markdown)
        for block in blocks:
            block["chunk_name"] = name
            block["original_page_start"] = chunk["original_page_start"]
            block["original_page_end"] = chunk["original_page_end"]
            block["mapping"] = locate_block(block, scoped, index, args.baseline_document_id, None, False)
            block["gate_block_reason"] = block_gate_reason(block)
            all_blocks.append(block)

        text_blocks = [block for block in blocks if block["normalized_text"]]
        method_counts: dict[str, int] = {}
        for block in text_blocks:
            method = block["mapping"]["mapping_method"]
            method_counts[method] = method_counts.get(method, 0) + 1
        reliable = sum(method_counts.get(method, 0) for method in RELIABLE_MAPPING_METHODS)
        linked = sum(1 for block in text_blocks if block["mapping"].get("source_locators"))
        count = len(text_blocks)
        chunk_text = "\n".join(block["text"] for block in text_blocks)
        chunk_baseline_text = "\n".join(row.get("text", "") for row in scoped)
        missing = sorted(critical_tokens(chunk_baseline_text) - critical_tokens(chunk_text))
        chunk_report = {
            "chunk_name": name,
            "original_page_start": chunk["original_page_start"],
            "original_page_end": chunk["original_page_end"],
            "baseline_page_scope_applied": has_page_numbers,
            "state": "done",
            "mineru_markdown": str(markdown_path),
            "text_block_count": count,
            "mapping_method_counts": method_counts,
            "reliable_backmatch_block_count": reliable,
            "backmatch_coverage": round(reliable / count, 4) if count else 0.0,
            "linked_block_count": linked,
            "linked_coverage": round(linked / count, 4) if count else 0.0,
            "critical_tokens_missing": missing,
            "blocked_block_count": sum(bool(block.get("gate_block_reason")) for block in blocks),
            "quality_status": "needs_human_review",
        }
        chunk_reports.append(chunk_report)
        adapted_parts.append(f"## {name} — original pages {chunk['original_page_start']}-{chunk['original_page_end']}")
        adapted_parts.append("")
        for block in blocks:
            mapping = block["mapping"]
            comment = {
                "mineru_block_id": block["mineru_block_id"],
                "chunk_name": name,
                "original_page_scope": [chunk["original_page_start"], chunk["original_page_end"]],
                "mapping_method": mapping["mapping_method"],
                "confidence": mapping["confidence"],
                "source_locators": [row.get("source_locator", "") for row in mapping["source_locators"]],
            }
            if block.get("gate_block_reason"):
                comment["gate_block_reason"] = block["gate_block_reason"]
            adapted_parts.append(f"<!-- mineru_pdf_source_locator: {json.dumps(comment, ensure_ascii=False)} -->")
            adapted_parts.append(block["raw_text"])
            adapted_parts.append("")

    text_blocks = [block for block in all_blocks if block["normalized_text"]]
    method_counts: dict[str, int] = {}
    for block in text_blocks:
        method = block["mapping"]["mapping_method"]
        method_counts[method] = method_counts.get(method, 0) + 1
    reliable = sum(method_counts.get(method, 0) for method in RELIABLE_MAPPING_METHODS)
    linked = sum(1 for block in text_blocks if block["mapping"].get("source_locators"))
    count = len(text_blocks)
    backmatch = round(reliable / count, 4) if count else 0.0
    linked_cov = round(linked / count, 4) if count else 0.0
    baseline_text = "\n".join(row.get("text", "") for row in baseline_locators)
    mineru_text = "\n".join(block["text"] for block in text_blocks)
    missing = sorted(critical_tokens(baseline_text) - critical_tokens(mineru_text))
    extra = sorted(critical_tokens(mineru_text) - critical_tokens(baseline_text))
    blocked = [block for block in all_blocks if block.get("gate_block_reason")]
    gate = {
        "branch": "DOCX -> formatted PDF -> MinerU API -> original DOCX locator backmatch",
        "original_source_file": split_manifest["source_file"],
        "original_source_sha256": split_manifest["source_sha256"],
        "baseline_locator_map": str(args.baseline_locator_map),
        "baseline_document_id": args.baseline_document_id,
        "baseline_quality_status": args.baseline_quality_status,
        "baseline_has_physical_page_numbers": any(row.get("page_number") is not None for row in baseline_locators),
        "text_block_count": count,
        "mapping_method_counts": method_counts,
        "reliable_backmatch_block_count": reliable,
        "backmatch_coverage": backmatch,
        "linked_block_count": linked,
        "linked_coverage": linked_cov,
        "backmatch_coverage_threshold": RELIABLE_MAPPING_THRESHOLD,
        "critical_tokens_missing": missing,
        "critical_tokens_extra": extra,
        "blocked_block_count": len(blocked),
        "quality_gate": "needs_human_review",
        "rag_eligible": False,
        "gate_reasons": [
            "Derived PDF is a cross-parser aid, not a replacement source",
            "MinerU API does not expose exact physical page boundaries for every block",
        ],
    }
    if backmatch < RELIABLE_MAPPING_THRESHOLD:
        gate["gate_reasons"].append(f"Backmatch coverage {backmatch:.1%} is below the {RELIABLE_MAPPING_THRESHOLD:.0%} threshold")
    if missing:
        gate["gate_reasons"].append("Critical tokens are missing from the derived-PDF MinerU output")
    if blocked:
        gate["gate_reasons"].append("One or more blocks remain unmapped or structurally ambiguous")

    locator_path = args.output_root / "mineru_pdf_original_docx_locator_map.jsonl"
    locator_lines = []
    for block in all_blocks:
        mapping = block["mapping"]
        locator_lines.append(json.dumps({
            "document_id": args.baseline_document_id,
            "derived_chunk": block["chunk_name"],
            "original_page_scope": [block["original_page_start"], block["original_page_end"]],
            "mineru_block_id": block["mineru_block_id"],
            "block_type": block["block_type"],
            "text": block["text"],
            "text_hash": sha256_text(block["text"]),
            "mapping_method": mapping["mapping_method"],
            "confidence": mapping["confidence"],
            "source_location_status": mapping["source_location_status"],
            "source_locators": mapping["source_locators"],
            "gate_block_reason": block.get("gate_block_reason"),
        }, ensure_ascii=False))
    locator_path.write_text("\n".join(locator_lines) + ("\n" if locator_lines else ""), encoding="utf-8")
    blocked_path = args.output_root / "mineru_pdf_gate_block_log.jsonl"
    blocked_path.write_text("\n".join(json.dumps({
        "derived_chunk": block["chunk_name"],
        "original_page_scope": [block["original_page_start"], block["original_page_end"]],
        "mineru_block_id": block["mineru_block_id"],
        "block_type": block["block_type"],
        "text_excerpt": block["text"][:300],
        "mapping_method": block["mapping"]["mapping_method"],
        "confidence": block["mapping"]["confidence"],
        "gate_block_reason": block["gate_block_reason"],
        "source_locators": block["mapping"]["source_locators"],
    }, ensure_ascii=False) for block in blocked) + ("\n" if blocked else ""), encoding="utf-8")
    gate["locator_map_path"] = str(locator_path)
    gate["blocked_block_log_path"] = str(blocked_path)
    gate["chunk_reports"] = chunk_reports
    (args.output_root / "mineru_pdf_quality_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output_root / "mineru_pdf_adapted.md").write_text("\n".join(adapted_parts), encoding="utf-8")
    print(json.dumps({"quality_gate": str(args.output_root / 'mineru_pdf_quality_gate.json'), "backmatch_coverage": backmatch, "linked_coverage": linked_cov, "text_blocks": count, "blocked": len(blocked)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
