#!/usr/bin/env python
"""Run the already-approved online MinerU API on derived PDF chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://mineru.net/api/v1/agent"


class ApiClient:
    def request(self, method: str, url: str, *, json_payload: dict[str, Any] | None = None, body: bytes | None = None, timeout: int = 60) -> bytes:
        headers = {"User-Agent": "phase1-mineru-api-docx-pdf-ab/1.0"}
        payload = body
        if json_payload is not None:
            payload = json.dumps(json_payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif body is not None:
            headers["Content-Type"] = ""
        request = urllib.request.Request(url, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {url}: {detail[:1000]}") from exc


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def submit_file(client: ApiClient, path: Path) -> tuple[str, str]:
    payload = {
        "file_name": path.name,
        "language": "ch",
        "enable_table": True,
        "is_ocr": False,
        "enable_formula": True,
    }
    result = json.loads(client.request("POST", f"{BASE_URL}/parse/file", json_payload=payload, timeout=60))
    if result.get("code") != 0:
        raise RuntimeError(f"MinerU submit failed: {result}")
    data = result["data"]
    return data["task_id"], data["file_url"]


def poll_result(client: ApiClient, task_id: str, timeout_seconds: int) -> dict[str, Any]:
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        result = json.loads(client.request("GET", f"{BASE_URL}/parse/{task_id}", timeout=60))
        if result.get("code") != 0:
            raise RuntimeError(f"MinerU poll failed: {result}")
        data = result.get("data", {})
        state = data.get("state")
        if state in {"done", "failed"}:
            return data
        time.sleep(5)
    raise TimeoutError(f"MinerU task timed out: {task_id}")


def run_chunk(client: ApiClient, row: dict[str, Any], output_root: Path, timeout_seconds: int) -> dict[str, Any]:
    path = Path(str(row["chunk_file"]))
    chunk_root = output_root / str(row["chunk_name"]).removesuffix(".pdf")
    chunk_root.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "chunk_name": row["chunk_name"],
        "source_file": str(path),
        "source_file_hash": row["chunk_sha256"],
        "original_page_start": row["original_page_start"],
        "original_page_end": row["original_page_end"],
        "chunk_page_count": row["chunk_page_count"],
        "file_size_bytes": path.stat().st_size,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    task_id, upload_url = submit_file(client, path)
    record["task_id"] = task_id
    client.request("PUT", upload_url, body=path.read_bytes(), timeout=300)
    record["upload_status"] = "success"
    data = poll_result(client, task_id, timeout_seconds)
    record["state"] = data.get("state")
    record["error_code"] = data.get("err_code")
    record["error_message"] = data.get("err_msg")
    if data.get("state") == "done":
        markdown_path = chunk_root / "mineru_full.md"
        markdown_path.write_bytes(client.request("GET", data["markdown_url"], timeout=120))
        record["markdown_path"] = str(markdown_path)
        record["markdown_sha256"] = sha256(markdown_path)
        record["markdown_character_count"] = len(markdown_path.read_text(encoding="utf-8"))
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    (chunk_root / "mineru_api_result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def combine_markdown(records: list[dict[str, Any]], output_root: Path) -> Path:
    parts = ["# MinerU API output — DOCX to formatted PDF branch", "", "<!-- Derived PDF branch; original DOCX remains the source authority. -->", ""]
    for record in records:
        if record.get("state") != "done" or not record.get("markdown_path"):
            continue
        parts.append(f"<!-- source_page_start: {record['original_page_start']} -->")
        parts.append(f"<!-- source_page_end: {record['original_page_end']} -->")
        parts.append(f"## Chunk {record['chunk_name']} (original pages {record['original_page_start']}-{record['original_page_end']})")
        parts.append(Path(str(record["markdown_path"])).read_text(encoding="utf-8"))
        parts.append("")
    destination = output_root / "combined_mineru_full.md"
    destination.write_text("\n".join(parts), encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split-manifest", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument(
        "--chunk-names",
        default="",
        help="Optional comma-separated chunk filenames; empty means all chunks.",
    )
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(args.split_manifest.read_text(encoding="utf-8"))
    selected_names = {name.strip() for name in args.chunk_names.split(",") if name.strip()}
    selected_chunks = [
        row for row in manifest["chunks"]
        if not selected_names or str(row["chunk_name"]) in selected_names
    ]
    if selected_names and len(selected_chunks) != len(selected_names):
        found = {str(row["chunk_name"]) for row in selected_chunks}
        missing = sorted(selected_names - found)
        raise ValueError(f"Requested chunk names not found in split manifest: {missing}")
    selected_manifest = {
        **manifest,
        "selection": sorted(selected_names) if selected_names else "all",
        "chunks": selected_chunks,
    }
    selected_manifest_path = args.output_root / "selected_split_manifest.json"
    selected_manifest_path.write_text(json.dumps(selected_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    client = ApiClient()
    records: list[dict[str, Any]] = []
    for row in selected_chunks:
        print(f"START {row['chunk_name']} pages={row['original_page_start']}-{row['original_page_end']}", flush=True)
        try:
            record = run_chunk(client, row, args.output_root, args.timeout_seconds)
            records.append(record)
            print(f"DONE  {row['chunk_name']}: {record.get('state')}", flush=True)
        except Exception as exc:
            failed = {**row, "state": "client_error", "error_message": repr(exc), "finished_at": datetime.now(timezone.utc).isoformat()}
            records.append(failed)
            print(f"ERROR {row['chunk_name']}: {exc}", file=sys.stderr, flush=True)
    combined = combine_markdown(records, args.output_root)
    output_manifest = {
        "test_id": "MINERU-API-DOCX-PDF-AB-20260824-001",
        "api_base": BASE_URL,
        "api_mode": "agent_lightweight_signed_upload",
        "derived_branch": "technical_spec_docx_to_formatted_pdf",
        "split_manifest": str(selected_manifest_path),
        "source_file": manifest["source_file"],
        "source_sha256": manifest["source_sha256"],
        "selection": sorted(selected_names) if selected_names else "all",
        "records": records,
        "combined_markdown": str(combined),
    }
    output_path = args.output_root / "mineru_api_chunked_manifest.json"
    output_path.write_text(json.dumps(output_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if records and all(record.get("state") == "done" for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
