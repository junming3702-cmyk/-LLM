"""Offline bundle intake, candidate discovery and tender-to-bid pairing.

No provider calls, legal opinions or bid-disqualification decisions occur here.
This is a development candidate, not an independent validation result.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
import sys
from pathlib import Path
from typing import Any


PUBLIC_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PUBLIC_ROOT / "src"))
from document_ingestor import safe_doc_id, sha256_file, write_document_outputs  # noqa: E402


ROLES = {"tender", "final_bid"}
TASKS = {"tender_clause_legality", "bid_responsiveness", "bid_standalone_legality"}
TENDER_CUES = re.compile(r"应当|必须|不得|应|须|需(?:要|提供|提交)|资格|资质|保证金|投标|报价|工期|质量|评分|评标|截止|响应|承诺|证明")
BID_CUES = re.compile(r"承诺|响应|保证|报价|工期|质量|资质|资格|业绩|保证金|提供|提交|符合|偏离|声明|不得")
DOC_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
CLAUSE_NUMBER = re.compile(r"(?<!\d)(?:第[一二三四五六七八九十百]+条|\d+(?:\.\d+){1,4})(?!\d)")


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not str(manifest.get("project_id", "")).strip():
        raise ValueError("project_id_required")
    if manifest.get("project_type") != "construction_project":
        raise ValueError("construction_project_type_required")
    docs = manifest.get("documents")
    if not isinstance(docs, list) or len(docs) < 2:
        raise ValueError("tender_and_final_bid_documents_required")
    keys, paths, roles = set(), set(), set()
    for item in docs:
        if not isinstance(item, dict) or item.get("role") not in ROLES:
            raise ValueError("only_explicit_tender_and_final_bid_roles_allowed")
        key = item.get("document_key")
        if not isinstance(key, str) or not DOC_KEY.fullmatch(key) or key in keys:
            raise ValueError("unique_safe_document_key_required")
        source = (path.parent / str(item.get("path", ""))).resolve()
        if not source.is_file() or source.suffix.lower() not in {".pdf", ".docx"} or source in paths:
            raise ValueError(f"unique_existing_pdf_or_docx_required:{key}")
        if item["role"] == "final_bid" and item.get("declared_final_submitted") is not True:
            raise ValueError(f"final_bid_submission_declaration_required:{key}")
        if item["role"] == "tender" and item.get("declared_issued") is not True:
            raise ValueError(f"issued_tender_declaration_required:{key}")
        item["resolved_path"] = str(source)
        keys.add(key)
        paths.add(source)
        roles.add(item["role"])
    if roles != ROLES:
        raise ValueError("both_tender_and_final_bid_roles_required")
    return manifest


def intake(manifest: dict[str, Any], output_root: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for declared in manifest["documents"]:
        row = (intake_verified_pagewise_cache(declared, manifest["project_id"], output_root / "parsed")
               if declared.get("verified_pagewise_cache") else write_document_outputs(
                   source=Path(declared["resolved_path"]),
                   output_root=output_root / "parsed",
                   project_id=manifest["project_id"],
                   source_status=declared.get("source_status", "unknown"),
                   document_type=declared["role"],
               ))
        if row["source_file_hash"] in seen_hashes:
            raise ValueError("duplicate_document_content_in_bundle")
        seen_hashes.add(row["source_file_hash"])
        quality = json.loads(Path(row["quality_report_path"]).read_text(encoding="utf-8"))
        locators = read_jsonl(Path(row["locator_map_path"]))
        # The baseline DOCX parser emits separate table-cell locators, so its
        # table parent is display-only. Cached MinerU pagewise tables contain
        # the *only* table text and must remain reviewable as a whole block.
        keep_table_parents = row["extraction_method"] == "verified_cached_mineru_pagewise"
        blocks = [r for r in locators if str(r.get("text", "")).strip()
                  and (keep_table_parents or r.get("block_type") != "table")]
        documents.append({
            **row,
            "document_key": declared["document_key"],
            "role": declared["role"],
            "declared_final_submitted": declared.get("declared_final_submitted") is True,
            "declared_issued": declared.get("declared_issued") is True,
            "extraction_quality": quality,
            "blocks": blocks,
        })
    return documents


def intake_verified_pagewise_cache(declared: dict[str, Any], project_id: str, output_root: Path) -> dict[str, Any]:
    """Reuse prior pagewise OCR only when it is bound to the unchanged source PDF.

    This verifies provenance and structural page/locator coverage, *not* the
    semantic accuracy of OCR or the completeness of a submitted bid package.
    """
    source = Path(declared["resolved_path"])
    cache = declared["verified_pagewise_cache"]
    if source.suffix.lower() != ".pdf" or not isinstance(cache, dict):
        raise ValueError("verified_pagewise_cache_requires_pdf_and_object")
    source_hash = sha256_file(source)
    if source_hash != str(cache.get("source_sha256", "")).lower():
        raise ValueError(f"cached_source_hash_mismatch:{declared['document_key']}")
    blocks_path = Path(cache["pagewise_blocks_path"])
    preflight_path = Path(cache["preflight_path"])
    if (sha256_file(blocks_path) != str(cache.get("blocks_sha256", "")).lower()
            or sha256_file(preflight_path) != str(cache.get("preflight_sha256", "")).lower()):
        raise ValueError(f"cached_artifact_hash_mismatch:{declared['document_key']}")
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    page_count = preflight.get("enumerated_page_count")
    if (preflight.get("sha256") != source_hash or not isinstance(page_count, int) or page_count < 1
            or preflight.get("verdict") not in {"PASS", "UNAVAILABLE"}):
        raise ValueError(f"cached_preflight_not_usable:{declared['document_key']}")
    alias = cache["document_alias"]
    raw_blocks = json.loads(blocks_path.read_text(encoding="utf-8"))
    blocks = [r for r in raw_blocks if r.get("document_id") == alias]
    if not blocks:
        raise ValueError(f"cached_document_missing:{alias}")
    doc_id = safe_doc_id(source_hash)
    document_dir = output_root / doc_id
    document_dir.mkdir(parents=True, exist_ok=True)
    locators = []
    by_page: dict[int, list[dict[str, Any]]] = {p: [] for p in range(1, page_count + 1)}
    seen_ids: set[str] = set()
    for block in blocks:
        page = block.get("page")
        block_id = block.get("block_id")
        if (block.get("source_sha256") != source_hash or not isinstance(page, int)
                or page not in by_page or not isinstance(block_id, str) or block_id in seen_ids):
            raise ValueError(f"cached_locator_integrity_failed:{alias}")
        seen_ids.add(block_id)
        by_page[page].append(block)
        content = str(block.get("text") or "").strip()
        if not content:
            continue
        locators.append({
            "block_id": block_id, "block_type": block.get("type", "text"), "text": content,
            "source_locator": block_id, "page_number": page,
            "extraction_method": "verified_cached_mineru_pagewise",
            "bbox_points": block.get("bbox_points"),
            "native_locator_valid": block.get("native_locator_valid") is True,
        })
    ledger_path = document_dir / "page_ledger.jsonl"
    missing_pages = []
    with ledger_path.open("w", encoding="utf-8", newline="\n") as handle:
        for page, page_blocks in by_page.items():
            usable = sum(bool(str(b.get("text") or "").strip()) and b.get("native_locator_valid") is True
                         for b in page_blocks)
            failures = []
            if not page_blocks:
                failures.append("no_extracted_blocks")
            elif not usable:
                failures.append("no_text_block_with_native_locator")
            if failures:
                missing_pages.append(page)
            handle.write(json.dumps({"page": page, "block_count": len(page_blocks),
                                     "usable_text_locator_count": usable, "failures": failures}, ensure_ascii=False) + "\n")
    locator_path = document_dir / "document_locator_map.jsonl"
    with locator_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in locators:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    quality_status = "pass" if preflight["verdict"] == "PASS" and not missing_pages else "needs_human_review"
    quality = {
        "document_id": doc_id, "project_id": project_id, "source_file": str(source),
        "source_file_hash": source_hash, "source_status": declared.get("source_status", "unknown"),
        "document_type": declared["role"], "file_format": "pdf",
        "extraction_method": "verified_cached_mineru_pagewise", "quality_status": quality_status,
        "page_count": page_count, "empty_pages": missing_pages, "block_count": len(locators),
        "character_count": sum(len(r["text"]) for r in locators),
        "preflight_verdict": preflight["verdict"], "preflight_warnings": preflight.get("warnings", []),
        "page_ledger_path": str(ledger_path), "source_of_truth": "original_file",
        "ocr_semantic_accuracy_verified": False, "submitted_bundle_completeness_verified": False,
        "cached_blocks_sha256": cache["blocks_sha256"], "cached_preflight_sha256": cache["preflight_sha256"],
    }
    quality_path = document_dir / "document_extraction_quality.json"
    quality_path.write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "project_id": project_id, "document_id": doc_id, "source_file": str(source),
        "source_file_hash": source_hash, "source_status": declared.get("source_status", "unknown"),
        "document_type": declared["role"], "file_format": "pdf", "extraction_method": quality["extraction_method"],
        "markdown_path": str(cache.get("pagewise_markdown_path", "")), "locator_map_path": str(locator_path),
        "quality_report_path": str(quality_path), "block_count": len(locators),
        "character_count": quality["character_count"], "quality_status": quality_status,
        "warnings": ";".join(preflight.get("warnings", [])), "processed_at": "reused_verified_cache",
    }


def source_record(doc: dict[str, Any], block: dict[str, Any]) -> dict[str, Any]:
    text = block["text"]
    return {
        "document_key": doc["document_key"], "document_id": doc["document_id"],
        "document_sha256": doc["source_file_hash"], "block_id": block["block_id"],
        "quote": text[:4000], "quote_truncated": len(text) > 4000,
        "source_locator": block["source_locator"], "page_number": block.get("page_number"),
        "physical_page_available": isinstance(block.get("page_number"), int),
        "extraction_method": block.get("extraction_method"),
        "block_type": block.get("block_type"),
        "table_structure_unverified": block.get("block_type") == "table"
        and block.get("extraction_method") == "verified_cached_mineru_pagewise",
    }


def candidate_id(task: str, source: dict[str, Any]) -> str:
    return task[:3].upper() + "-" + digest([task, source["document_sha256"], source["block_id"]])[:12]


def grams(text: str) -> set[str]:
    cleaned = re.sub(r"\s+", "", text.lower())
    return {cleaned[i:i + 2] for i in range(max(0, len(cleaned) - 1)) if cleaned[i:i + 2].strip()}


def pair_score(requirement: str, response: str) -> float:
    a, b = grams(requirement), grams(response)
    if not a or not b:
        return 0.0
    overlap = len(a & b) / max(1, len(a | b))
    req_refs = set(CLAUSE_NUMBER.findall(requirement))
    bid_refs = set(CLAUSE_NUMBER.findall(response))
    # A shared section number is only a tie-breaker after sufficient textual
    # alignment. Otherwise two unrelated sections called 3.2.1 can create a
    # spurious non-response finding downstream.
    if overlap >= 0.18 and req_refs and req_refs & bid_refs:
        overlap += 0.35
    return round(min(overlap, 1.0), 4)


def find_pair(requirement: dict[str, Any], bid_blocks: list[dict[str, Any]],
              bid_signatures: list[tuple[set[str], set[str]]] | None = None) -> dict[str, Any]:
    if bid_signatures is None:
        bid_signatures = [(grams(row["quote"]), set(CLAUSE_NUMBER.findall(row["quote"]))) for row in bid_blocks]
    if len(bid_signatures) != len(bid_blocks):
        raise ValueError("bid_signature_length_mismatch")
    req_grams = grams(requirement["quote"])
    req_refs = set(CLAUSE_NUMBER.findall(requirement["quote"]))

    def scored():
        for row, (other_grams, other_refs) in zip(bid_blocks, bid_signatures):
            if not req_grams or not other_grams:
                score = 0.0
            else:
                shared = len(req_grams & other_grams)
                score = shared / max(1, len(req_grams) + len(other_grams) - shared)
                if score >= 0.18 and req_refs and req_refs & other_refs:
                    score += 0.35
                score = round(min(score, 1.0), 4)
            yield score, row

    ranked = heapq.nsmallest(2, scored(), key=lambda x: (-x[0], x[1]["document_key"], x[1]["block_id"]))
    if not ranked or ranked[0][0] < 0.18:
        return {"status": "not_found_in_reviewed_text", "candidate_matches": [], "top_score": ranked[0][0] if ranked else 0.0}
    top = ranked[:2]
    ambiguous = len(top) > 1 and top[1][0] >= 0.18 and top[0][0] - top[1][0] < 0.08
    return {
        "status": "ambiguous_needs_human_matching" if ambiguous else "provisional_match_needs_verification",
        "candidate_matches": [{"score": score, "source": row} for score, row in top if score >= 0.18],
        "top_score": top[0][0],
    }


def discover(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bid_blocks = [source_record(doc, block) for doc in documents if doc["role"] == "final_bid" for block in doc["blocks"]]
    bid_signatures = [(grams(row["quote"]), set(CLAUSE_NUMBER.findall(row["quote"]))) for row in bid_blocks]
    issues: list[dict[str, Any]] = []
    selected_by_doc: dict[str, set[str]] = {doc["document_key"]: set() for doc in documents}
    for doc in documents:
        for block in doc["blocks"]:
            text = str(block["text"]).strip()
            if len(text) < 4:
                continue
            source = source_record(doc, block)
            if doc["role"] == "tender" and TENDER_CUES.search(text):
                selected_by_doc[doc["document_key"]].add(block["block_id"])
                for task in ("tender_clause_legality", "bid_responsiveness"):
                    pair = find_pair(source, bid_blocks, bid_signatures) if task == "bid_responsiveness" else None
                    issues.append({
                        "issue_id": candidate_id(task, source), "task": task,
                        "primary_source": source, "tender_basis": source if task == "bid_responsiveness" else None,
                        "pairing": pair, "risk_conclusion": "not_yet_assessed",
                        "discrepancy": "not_yet_assessed", "overall_status": "requires_human_second_review",
                    })
            elif doc["role"] == "final_bid" and BID_CUES.search(text):
                selected_by_doc[doc["document_key"]].add(block["block_id"])
                issues.append({
                    "issue_id": candidate_id("bid_standalone_legality", source),
                    "task": "bid_standalone_legality", "primary_source": source,
                    "tender_basis": None, "pairing": None,
                    "risk_conclusion": "not_yet_assessed", "discrepancy": "not_yet_assessed",
                    "overall_status": "requires_human_second_review",
                })
    coverage_docs = []
    for doc in documents:
        quality = doc["extraction_quality"]
        selected = selected_by_doc[doc["document_key"]]
        all_blocks = [b["block_id"] for b in doc["blocks"]]
        coverage_docs.append({
            "document_key": doc["document_key"], "role": doc["role"],
            "file_format": doc["file_format"], "quality_status": doc["quality_status"],
            "total_extracted_blocks": len(all_blocks), "candidate_source_blocks": len(selected),
            "not_selected_for_semantic_review_block_ids": [x for x in all_blocks if x not in selected],
            "physical_page_count": quality.get("page_count"),
            "unreadable_or_empty_physical_pages": quality.get("empty_pages", []),
            "page_ledger_path": quality.get("page_ledger_path"),
            "preflight_verdict": quality.get("preflight_verdict"),
            "preflight_warnings": quality.get("preflight_warnings", []),
            "ocr_semantic_accuracy_verified": quality.get("ocr_semantic_accuracy_verified"),
            "page_locator_limitation": "DOCX has structural paragraph/table locators only" if doc["file_format"] == "docx" else "",
            "conditional_enhancement_recommended": "MinerU_then_local_coordinate_OCR_if_unresolved"
            if doc["quality_status"] != "pass" and doc["file_format"] == "pdf" else None,
            "candidate_coverage_is_not_recall": True,
        })
    coverage = {
        "documents": coverage_docs,
        "candidate_count_by_task": {task: sum(i["task"] == task for i in issues) for task in sorted(TASKS)},
        "pairing_status_counts": {status: sum((i.get("pairing") or {}).get("status") == status for i in issues if i["task"] == "bid_responsiveness")
                                  for status in ("provisional_match_needs_verification", "ambiguous_needs_human_matching", "not_found_in_reviewed_text")},
        "independent_item_recall": None, "independent_pairing_accuracy": None,
    }
    return issues, coverage


def build_core_labels(manifest: dict[str, Any], documents: list[dict[str, Any]], issues: list[dict[str, Any]], coverage: dict[str, Any]) -> list[dict[str, Any]]:
    received = [d["document_id"] for d in documents]
    coverage_summary = [{
        "document_key": row["document_key"], "quality_status": row["quality_status"],
        "unreadable_or_empty_physical_pages": row["unreadable_or_empty_physical_pages"],
        "unselected_block_count": len(row["not_selected_for_semantic_review_block_ids"]),
        "page_locator_limitation": row["page_locator_limitation"],
    } for row in coverage["documents"]]
    labels = []
    for issue in issues:
        if issue["task"] == "bid_responsiveness" and (issue.get("pairing") or {}).get("status") != "provisional_match_needs_verification":
            # An uncertain match is a human matching task, not evidence that
            # a submitted bid failed to respond to a requirement.
            continue
        source = issue["primary_source"]
        pair = issue.get("pairing") or {}
        matches = pair.get("candidate_matches", [])
        paired = matches[0]["source"] if matches and pair["status"] == "provisional_match_needs_verification" else None
        evidence = {"task": issue["task"], "primary": source, "paired_bid_source": paired,
                    "pairing_status": pair.get("status"), "alternatives": matches if not paired else [],
                    "documents_received": received, "coverage": coverage_summary}
        excerpt = source["quote"]
        if paired:
            excerpt = "招标要求：" + source["quote"] + "\n投标响应：" + paired["quote"]
        context = dict(manifest.get("project_context") or {})
        context.setdefault("project_type", manifest["project_type"])
        context.setdefault("project_location", manifest.get("project_location") or {})
        labels.append({
            "issue_id": issue["issue_id"], "project_id": manifest["project_id"],
            "document_id": source["document_id"], "document_location": source["source_locator"],
            "document_excerpt": excerpt, "retrieval_queries": [source["quote"]] + ([paired["quote"]] if paired else []),
            "runtime_project_context": context, "bundle_evidence": evidence,
            "review_task_kind": issue["task"],
        })
    return labels


def run(manifest_path: Path, output_root: Path) -> dict[str, Any]:
    manifest = require_manifest(manifest_path)
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError("output_root_must_be_new_or_empty")
    output_root.mkdir(parents=True, exist_ok=True)
    documents = intake(manifest, output_root)
    issues, coverage = discover(documents)
    labels = build_core_labels(manifest, documents, issues, coverage)
    intake_summary = [{k: v for k, v in d.items() if k not in {"blocks", "extraction_quality"}} for d in documents]
    outputs = {"bundle_intake.json": {"project_id": manifest["project_id"], "documents": intake_summary,
                                      "addenda_inventory": manifest.get("addenda_inventory"),
                                      "excluded_or_reference_only": manifest.get("excluded_or_reference_only", [])},
               "candidates.json": issues, "coverage.json": coverage}
    for name, data in outputs.items():
        (output_root / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_root / "candidate_labels.jsonl").write_text(
        "".join(json.dumps(label, ensure_ascii=False) + "\n" for label in labels), encoding="utf-8")
    (output_root / "legal_core_labels.jsonl").write_text(
        "".join(json.dumps(label, ensure_ascii=False) + "\n" for label in labels
                if label["review_task_kind"] != "bid_responsiveness"), encoding="utf-8")
    (output_root / "pair_labels.jsonl").write_text(
        "".join(json.dumps(label, ensure_ascii=False) + "\n" for label in labels
                if label["review_task_kind"] == "bid_responsiveness"), encoding="utf-8")
    return {"project_id": manifest["project_id"], "documents": len(documents), "candidates": len(issues),
            "legal_core_eligible": sum(l["review_task_kind"] != "bid_responsiveness" for l in labels),
            "pair_reasoning_eligible": sum(l["review_task_kind"] == "bid_responsiveness" for l in labels),
            "output_root": str(output_root), "status": "discovery_and_pairing_only_not_legal_assessment"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.manifest.resolve(), args.output_root.resolve()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
