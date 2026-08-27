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
    args = parser.parse_args()

    args.output_root.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(args.input))
    total = len(reader.pages)
    source_hash = sha256_file(args.input)
    chunks: list[dict[str, object]] = []

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
        "chunks": chunks,
    }
    manifest_path = args.output_root / "split_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "source_page_count": total, "chunk_count": len(chunks)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
