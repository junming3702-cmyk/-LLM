#!/usr/bin/env python
"""Split a derived PDF into small, traceable chunks for MinerU Agent API."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--chunk-pages", type=int, default=20)
    parser.add_argument(
        "--pages",
        help="Optional comma-separated one-based source pages/ranges (for example 1,3,5,10-12).",
    )
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(args.input))
    total = len(reader.pages)
    source_hash = sha256_file(args.input)
    chunks: list[dict[str, object]] = []

    selected_pages: list[int] | None = None
    if args.pages:
        selected: set[int] = set()
        for part in args.pages.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                first, last = part.split("-", 1)
                selected.update(range(int(first), int(last) + 1))
            else:
                selected.add(int(part))
        selected_pages = sorted(selected)
        invalid = [page for page in selected_pages if page < 1 or page > total]
        if invalid:
            raise ValueError(f"Selected pages outside 1-{total}: {invalid}")

    if selected_pages is not None:
        path = args.output_root / "selected-problem-pages.pdf"
        writer = PdfWriter()
        for page_number in selected_pages:
            writer.add_page(reader.pages[page_number - 1])
        with path.open("wb") as f:
            writer.write(f)
        chunks.append({
            "chunk_file": str(path),
            "chunk_name": path.name,
            "original_pages": selected_pages,
            "chunk_page_count": len(selected_pages),
            "chunk_sha256": sha256_file(path),
            "chunk_size_bytes": path.stat().st_size,
        })
    else:

        for start in range(0, total, args.chunk_pages):
            end = min(total, start + args.chunk_pages)
            name = f"chunk-{start // args.chunk_pages + 1:03d}-pages-{start + 1:04d}-{end:04d}.pdf"
            path = args.output_root / name
            writer = PdfWriter()
            for index in range(start, end):
                writer.add_page(reader.pages[index])
            with path.open("wb") as f:
                writer.write(f)
            chunks.append({
                "chunk_file": str(path),
                "chunk_name": name,
                "original_page_start": start + 1,
                "original_page_end": end,
                "chunk_page_count": end - start,
                "chunk_sha256": sha256_file(path),
                "chunk_size_bytes": path.stat().st_size,
            })

    manifest = {
        "source_file": str(args.input),
        "source_sha256": source_hash,
        "source_page_count": total,
        "chunk_page_limit": args.chunk_pages,
        "selection_mode": "explicit_problem_pages" if selected_pages is not None else "sequential_chunks",
        "selected_original_pages": selected_pages,
        "chunks": chunks,
    }
    manifest_path = args.output_root / "split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "source_page_count": total, "chunk_count": len(chunks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
