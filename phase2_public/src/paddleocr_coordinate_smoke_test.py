#!/usr/bin/env python
"""Coordinate-OCR smoke test for pages where the baseline PDF parser failed.

This is an experiment-side DocumentIngestor enhancement. It never overwrites
the baseline text or locator map; it emits a second locator map whose physical
coordinates are explicit and whose quality status remains human-review gated.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

import pypdfium2 as pdfium


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "tolist"):
        return jsonable(value.tolist())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return str(value)


def result_payload(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return item.get("res", item)
    for name in ("json", "to_json"):
        if hasattr(item, name):
            value = getattr(item, name)
            try:
                value = value() if callable(value) else value
                if isinstance(value, str):
                    value = json.loads(value)
                if isinstance(value, dict):
                    return value.get("res", value)
            except Exception:
                pass
    if hasattr(item, "res") and isinstance(item.res, dict):
        return item.res
    return vars(item) if hasattr(item, "__dict__") else {}


def as_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return jsonable(value)
    return []


def polygon_to_points(poly: Any) -> list[list[float]]:
    value = jsonable(poly)
    if isinstance(value, dict):
        value = value.get("points") or value.get("polygon") or []
    if not isinstance(value, list):
        return []
    if len(value) == 4 and all(isinstance(x, (int, float)) for x in value):
        x0, y0, x1, y1 = [float(x) for x in value]
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    points: list[list[float]] = []
    for point in value:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append([float(point[0]), float(point[1])])
    return points


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def map_polygon(points: list[list[float]], image_w: int, image_h: int, pdf_w: float, pdf_h: float) -> dict[str, Any]:
    pixel = [[round(float(x), 2), round(float(y), 2)] for x, y in points]
    pdf_top = [[round(float(x) * pdf_w / image_w, 3), round(float(y) * pdf_h / image_h, 3)] for x, y in points]
    pdf_bottom = [[x, round(pdf_h - y, 3)] for x, y in pdf_top]
    return {"pixel_polygon": pixel, "pdf_polygon_top_left": pdf_top, "pdf_polygon_bottom_left": pdf_bottom}


def load_baseline(path: Path) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    if not path.exists():
        return grouped
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        grouped.setdefault(int(row.get("page_number", 0)), []).append(row)
    return grouped


def match_baseline(text: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    query = normalize_text(text)
    if not query:
        return None
    for row in rows:
        candidate = normalize_text(row.get("text", ""))
        if query == candidate or (len(query) >= 6 and query in candidate) or (len(candidate) >= 6 and candidate in query):
            return {"block_id": row.get("block_id"), "source_locator": row.get("source_locator"), "match": "text_overlap"}
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--baseline-locator-map", type=Path)
    parser.add_argument(
        "--pages",
        default="auto",
        help="Comma-separated 1-based pages, or 'auto' for every page.",
    )
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    image_root = args.output_root / "rendered_pages"
    image_root.mkdir(exist_ok=True)
    locator_path = args.output_root / "paddleocr_coordinate_locator_map.jsonl"
    quality_path = args.output_root / "paddleocr_coordinate_quality.json"
    markdown_path = args.output_root / "paddleocr_coordinate.md"
    baseline = load_baseline(args.baseline_locator_map) if args.baseline_locator_map else {}
    source_hash = sha256_file(args.input)
    document_id = f"DOC-{source_hash[:12]}"

    from paddleocr import PaddleOCR

    try:
        ocr = PaddleOCR(
            lang="ch",
            device="cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        ocr = PaddleOCR(lang="ch", device="cpu")

    pdf = pdfium.PdfDocument(str(args.input))
    if args.pages.strip().lower() == "auto":
        pages = list(range(1, len(pdf) + 1))
    else:
        pages = [int(x.strip()) for x in args.pages.split(",") if x.strip()]
    invalid_pages = [page for page in pages if page < 1 or page > len(pdf)]
    if invalid_pages:
        raise ValueError(f"Requested pages outside 1-{len(pdf)}: {invalid_pages}")
    locator_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    md_parts: list[str] = ["# PaddleOCR coordinate smoke test", "", f"- source: `{args.input}`", f"- source_sha256: `{source_hash}`", "- status: `needs_human_review`", ""]

    for page_number in pages:
        page = pdf[page_number - 1]
        pdf_w, pdf_h = page.get_size()
        bitmap = page.render(scale=args.scale)
        image = bitmap.to_pil()
        image_path = image_root / f"page-{page_number:04d}.png"
        image.save(image_path)
        image_w, image_h = image.size

        results = ocr.predict(str(image_path))
        items = list(results) if results is not None else []
        payload = result_payload(items[0]) if items else {}
        texts = as_list(payload, "rec_texts", "texts")
        scores = as_list(payload, "rec_scores", "scores")
        polys = as_list(payload, "rec_polys", "dt_polys", "rec_boxes", "boxes")
        page_rows: list[dict[str, Any]] = []
        page_md: list[str] = [f"## Page {page_number}", ""]
        for idx, text in enumerate(texts):
            text = str(text)
            if not text.strip():
                continue
            score = float(scores[idx]) if idx < len(scores) else None
            points = polygon_to_points(polys[idx]) if idx < len(polys) else []
            geometry = map_polygon(points, image_w, image_h, pdf_w, pdf_h) if points else {}
            block_id = f"page-{page_number:04d}-ocr-{len(page_rows)+1:04d}"
            locator = f"{document_id}::pdf-page-{page_number:04d}::ocr-bbox-{len(page_rows)+1:04d}"
            row = {
                "document_id": document_id,
                "block_id": block_id,
                "block_type": "ocr_textline",
                "source_locator": locator,
                "text": text,
                "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "markdown_anchor": locator,
                "page_number": page_number,
                "line_number": len(page_rows) + 1,
                "extraction_method": "paddleocr_coordinate",
                "ocr_score": score,
                "baseline_match": match_baseline(text, baseline.get(page_number, [])),
                **geometry,
            }
            page_rows.append(row)
            locator_rows.append(row)
            page_md.append(f"<!-- source_locator: {locator} -->")
            page_md.append(text)
            page_md.append("")

        page_scores = [row["ocr_score"] for row in page_rows if row.get("ocr_score") is not None]
        quality = {
            "page_number": page_number,
            "rendered_image": str(image_path),
            "pdf_size_points": [round(pdf_w, 3), round(pdf_h, 3)],
            "image_size_pixels": [image_w, image_h],
            "detected_textline_count": len(page_rows),
            "text_chars": sum(len(row["text"]) for row in page_rows),
            "average_ocr_score": round(mean(page_scores), 4) if page_scores else None,
            "minimum_ocr_score": round(min(page_scores), 4) if page_scores else None,
            "coordinate_coverage": round(sum(bool(row.get("pixel_polygon")) for row in page_rows) / len(page_rows), 4) if page_rows else 0.0,
            "baseline_text_overlap_count": sum(bool(row.get("baseline_match")) for row in page_rows),
            "quality_status": "needs_human_review",
            "gate_reasons": ["OCR-derived text", "coordinate locator requires visual/semantic confirmation"],
        }
        quality_rows.append(quality)
        md_parts.extend(page_md)

    locator_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in locator_rows), encoding="utf-8")
    coordinate_rows = len(locator_rows)
    page_coverage = round(sum(row["detected_textline_count"] > 0 for row in quality_rows) / len(quality_rows), 4) if quality_rows else 0.0
    coordinate_coverage = round(sum(bool(row.get("pixel_polygon")) for row in locator_rows) / coordinate_rows, 4) if coordinate_rows else 0.0
    quality_path.write_text(
        json.dumps(
            {
                "source_file": str(args.input),
                "source_sha256": source_hash,
                "document_id": document_id,
                "pages": quality_rows,
                "page_text_coverage": page_coverage,
                "coordinate_coverage": coordinate_coverage,
                "overall_status": "needs_human_review",
                "retrieval_admission": "candidate_enhancement_only",
                "gate_note": "Coordinate OCR supplies physical locators but does not independently establish legal meaning.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    markdown_path.write_text("\n".join(md_parts), encoding="utf-8")
    print(json.dumps({"locator_map": str(locator_path), "quality": str(quality_path), "markdown": str(markdown_path), "rows": len(locator_rows), "pages": pages}, ensure_ascii=False))


if __name__ == "__main__":
    main()
