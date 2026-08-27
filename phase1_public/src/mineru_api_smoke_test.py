"""Run a small MinerU Agent API parsing comparison on public law-source samples.

This script uploads only the explicitly selected public-law samples to the
official MinerU Agent API. It keeps source files and MinerU Markdown results
separate from the baseline DocumentIngestor output and never calls retrieval
or an LLM.
"""

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
    """Small standard-library HTTP client; no local MinerU package is needed."""

    def request(
        self,
        method: str,
        url: str,
        *,
        json_payload: dict[str, Any] | None = None,
        body: bytes | None = None,
        timeout: int = 60,
    ) -> bytes:
        headers = {"User-Agent": "phase1-mineru-api-smoke-test/1.0"}
        payload = body
        if json_payload is not None:
            payload = json.dumps(json_payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif body is not None:
            # MinerU's signed OSS upload requires no Content-Type header. urllib
            # otherwise supplies application/x-www-form-urlencoded automatically.
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


def find_one(root: Path, pattern: str) -> Path:
    matches = sorted(root.rglob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched {pattern!r} below {root}")
    return matches[0]


def build_cases(law_root: Path) -> list[dict[str, Any]]:
    gb = find_one(law_root, "GB_T50500-2024*.pdf")
    return [
        {
            "case_id": "gb_t50500_pages_1_10_ocr",
            "path": gb,
            "page_range": "1-10",
            "is_ocr": True,
            "reason": "Known missing-text pages 1, 2, 4 and 10 in the baseline run",
        },
        {
            "case_id": "gb_t50500_page_320_ocr",
            "path": gb,
            "page_range": "320",
            "is_ocr": True,
            "reason": "Known missing-text page 320 in the baseline run",
        },
        {
            "case_id": "must_tender_pdf_control",
            "path": find_one(law_root, "必须招标的工程项目规定.pdf"),
            "page_range": None,
            "is_ocr": False,
            "reason": "Text-PDF control sample; baseline parser passed",
        },
        {
            "case_id": "technical_spec_docx",
            "path": find_one(law_root, "技术规范发布稿.docx"),
            "page_range": None,
            "is_ocr": False,
            "reason": "DOCX structure sample with potential layout/table sensitivity",
        },
        {
            "case_id": "sichuan_local_docx",
            "path": find_one(law_root, "四川省建筑管理条例_20210929.docx"),
            "page_range": None,
            "is_ocr": False,
            "reason": "Local-regulation DOCX sample for paragraph locator comparison",
        },
    ]


def submit_file(client: ApiClient, path: Path, page_range: str | None, is_ocr: bool) -> tuple[str, str]:
    payload: dict[str, Any] = {
        "file_name": path.name,
        "language": "ch",
        "enable_table": True,
        "is_ocr": is_ocr,
        "enable_formula": True,
    }
    if page_range:
        payload["page_range"] = page_range
    result = json.loads(client.request("POST", f"{BASE_URL}/parse/file", json_payload=payload, timeout=60))
    if result.get("code") != 0:
        raise RuntimeError(f"MinerU submit failed: {result}")
    data = result["data"]
    return data["task_id"], data["file_url"]


def poll_result(client: ApiClient, task_id: str, timeout_seconds: int = 900) -> dict[str, Any]:
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


def download_markdown(client: ApiClient, markdown_url: str, destination: Path) -> None:
    content = client.request("GET", markdown_url, timeout=120)
    destination.write_bytes(content)


def run_case(client: ApiClient, case: dict[str, Any], output_root: Path, timeout_seconds: int) -> dict[str, Any]:
    path: Path = case["path"]
    case_root = output_root / case["case_id"]
    case_root.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "case_id": case["case_id"],
        "source_file": str(path),
        "source_file_hash": sha256(path),
        "page_range": case["page_range"],
        "is_ocr": case["is_ocr"],
        "reason": case["reason"],
        "file_size_bytes": path.stat().st_size,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    task_id, upload_url = submit_file(client, path, case["page_range"], case["is_ocr"])
    record["task_id"] = task_id
    # The signed URL is deliberately not persisted in the result record.
    with path.open("rb") as handle:
        upload_body = handle.read()
    client.request("PUT", upload_url, body=upload_body, timeout=300)
    record["upload_status"] = "success"
    data = poll_result(client, task_id, timeout_seconds=timeout_seconds)
    record["state"] = data.get("state")
    record["error_code"] = data.get("err_code")
    record["error_message"] = data.get("err_msg")
    if data.get("state") == "done":
        markdown_path = case_root / "mineru_full.md"
        download_markdown(client, data["markdown_url"], markdown_path)
        record["markdown_path"] = str(markdown_path)
        record["markdown_sha256"] = sha256(markdown_path)
        record["markdown_character_count"] = len(markdown_path.read_text(encoding="utf-8"))
    record["finished_at"] = datetime.now(timezone.utc).isoformat()
    (case_root / "mineru_api_result.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--law-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()
    args.output_root.mkdir(parents=True, exist_ok=True)

    client = ApiClient()
    records: list[dict[str, Any]] = []
    for case in build_cases(args.law_root):
        print(f"START {case['case_id']}: {case['path'].name} page_range={case['page_range']}", flush=True)
        try:
            records.append(run_case(client, case, args.output_root, args.timeout_seconds))
            print(f"DONE  {case['case_id']}: {records[-1].get('state')}", flush=True)
        except Exception as exc:  # Keep the batch audit record even if one case fails.
            failed = {
                "case_id": case["case_id"],
                "source_file": str(case["path"]),
                "source_file_hash": sha256(case["path"]),
                "page_range": case["page_range"],
                "is_ocr": case["is_ocr"],
                "reason": case["reason"],
                "state": "client_error",
                "error_message": repr(exc),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
            records.append(failed)
            print(f"ERROR {case['case_id']}: {exc}", file=sys.stderr, flush=True)

    manifest = {
        "test_id": "MINERU-API-SMOKE-20260824-001",
        "api_base": BASE_URL,
        "api_mode": "agent_lightweight_signed_upload",
        "scope": "public law-source samples only",
        "records": records,
    }
    (args.output_root / "mineru_api_smoke_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if all(record.get("state") == "done" for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
