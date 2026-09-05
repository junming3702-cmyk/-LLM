"""MinerU precision-API preprocessor with provenance-safe local upload.

The user's root ``Mineru.py`` is a minimal public-URL example.  This production
candidate implements the official v4 signed-upload batch flow for local files:

1. request signed upload URLs;
2. PUT local bytes to those URLs;
3. poll the batch result;
4. download and safely extract the result ZIP;
5. write a locator-adapter-compatible ``mineru_api_result.json``.

Tokens and signed URLs are never written to disk or printed.  MinerU output is
an untrusted candidate parse and must still pass ``mineru_source_locator_adapter``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = Path(os.environ.get("MODEL_ENV_FILE", PACKAGE_ROOT / ".env")).expanduser().resolve()
OFFICIAL_API_BASE = "https://mineru.net/api/v4"
SUPPORTED_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".png", ".jpg", ".jpeg"}
TERMINAL_STATES = {"done", "failed"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_api_base(raw: str) -> tuple[str, str]:
    """Accept only MinerU's official HTTPS host; fail over without leaking data."""

    value = raw.strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.hostname == "mineru.net":
        if parsed.path.endswith("/extract/task"):
            value = value[: -len("/extract/task")]
        if not value.endswith("/api/v4"):
            value = value.rstrip("/") + "/api/v4"
        return value, "environment_validated"
    return OFFICIAL_API_BASE, "safe_default_due_invalid_environment_url"


def load_configuration(env_file: Path) -> tuple[str, str, str]:
    if not env_file.exists():
        raise FileNotFoundError(env_file)
    load_dotenv(dotenv_path=env_file, override=False)
    token = os.environ.get("Mineru_API_KEY", "").strip()
    if not token:
        raise RuntimeError("Mineru_API_KEY is missing or empty")
    base, source = safe_api_base(os.environ.get("Mineru_BASE_URL", ""))
    return token, base, source


def discover_inputs(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_SUFFIXES else []
    return sorted(file for file in path.rglob("*") if file.is_file() and file.suffix.lower() in SUPPORTED_SUFFIXES)


def checked_json(response: requests.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{operation} returned a non-JSON HTTP response ({response.status_code})") from exc
    if not response.ok:
        raise RuntimeError(f"{operation} failed with HTTP {response.status_code}: {payload.get('msg', 'unknown error')}")
    if payload.get("code") not in (0, None):
        raise RuntimeError(f"{operation} failed: code={payload.get('code')} msg={payload.get('msg')}")
    return payload


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsafe ZIP member rejected: {member.filename}")
        handle.extractall(destination)


def locate_output(extracted: Path, patterns: tuple[str, ...]) -> Path | None:
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(extracted.rglob(pattern))
    files = sorted({path.resolve() for path in matches if path.is_file()}, key=lambda p: (len(str(p)), str(p)))
    return files[0] if files else None


class MinerUPrecisionClient:
    def __init__(self, token: str, api_base: str) -> None:
        self.api_base = api_base.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def create_batch(self, files: list[Path], data_ids: list[str]) -> tuple[str, list[str], str | None]:
        body = {
            "files": [{"name": path.name, "data_id": data_id} for path, data_id in zip(files, data_ids)],
            "model_version": "vlm",
            "language": "ch",
            "enable_formula": True,
            "enable_table": True,
        }
        response = requests.post(
            f"{self.api_base}/file-urls/batch", headers=self.headers, json=body, timeout=60
        )
        payload = checked_json(response, "MinerU signed-upload request")
        data = payload.get("data") or {}
        batch_id = str(data.get("batch_id") or "")
        upload_urls = list(data.get("file_urls") or [])
        if not batch_id or len(upload_urls) != len(files):
            raise RuntimeError("MinerU signed-upload response is missing batch_id or file_urls")
        return batch_id, upload_urls, payload.get("trace_id")

    @staticmethod
    def upload(path: Path, signed_url: str) -> None:
        with path.open("rb") as handle:
            response = requests.put(signed_url, data=handle, timeout=600)
        if not response.ok:
            raise RuntimeError(f"MinerU object upload failed with HTTP {response.status_code}")

    def poll(self, batch_id: str, timeout_seconds: int, interval_seconds: int) -> tuple[list[dict[str, Any]], str | None]:
        start = time.monotonic()
        while time.monotonic() - start < timeout_seconds:
            response = requests.get(
                f"{self.api_base}/extract-results/batch/{batch_id}", headers=self.headers, timeout=60
            )
            payload = checked_json(response, "MinerU batch poll")
            data = payload.get("data") or {}
            results = list(data.get("extract_result") or data.get("extract_results") or [])
            if results and all(str(row.get("state")) in TERMINAL_STATES for row in results):
                return results, payload.get("trace_id")
            time.sleep(interval_seconds)
        raise TimeoutError(f"MinerU batch timed out after {timeout_seconds}s: {batch_id}")


def write_result(
    *,
    source: Path,
    uploaded_file: Path,
    source_hash: str,
    uploaded_file_hash: str,
    data_id: str,
    batch_id: str,
    result: dict[str, Any],
    output_root: Path,
    authorization_scope: str,
    is_ocr: bool,
) -> dict[str, Any]:
    case_root = output_root / source_hash[:12]
    case_root.mkdir(parents=True, exist_ok=True)
    state = str(result.get("state") or "unknown")
    record: dict[str, Any] = {
        "case_id": data_id,
        "source_file": str(source),
        "source_file_hash": source_hash,
        "uploaded_file": str(uploaded_file),
        "uploaded_file_hash": uploaded_file_hash,
        "file_size_bytes": uploaded_file.stat().st_size,
        "is_ocr": is_ocr,
        "language": "ch",
        "enable_table": True,
        "enable_formula": True,
        "model_version": "vlm",
        "api_mode": "precision_v4_signed_batch_upload",
        "batch_id": batch_id,
        "task_id": batch_id,
        "data_id": data_id,
        "state": state,
        "error_code": result.get("err_code"),
        "error_message": result.get("err_msg"),
        "authorization_scope": authorization_scope,
        "finished_at": now_utc(),
    }
    if state == "done":
        zip_url = result.get("full_zip_url")
        if not zip_url:
            raise RuntimeError(f"MinerU result for {source.name} is done but has no full_zip_url")
        archive = case_root / "mineru_result.zip"
        response = requests.get(str(zip_url), timeout=300)
        if not response.ok:
            raise RuntimeError(f"MinerU ZIP download failed with HTTP {response.status_code}")
        archive.write_bytes(response.content)
        extracted = case_root / "extracted"
        safe_extract_zip(archive, extracted)
        markdown = locate_output(extracted, ("*.md",))
        content_list = locate_output(extracted, ("*content_list*.json", "content_list.json"))
        middle_json = locate_output(extracted, ("*middle*.json",))
        if markdown is None:
            raise RuntimeError(f"MinerU ZIP for {source.name} contains no Markdown output")
        record.update(
            {
                "result_zip_path": str(archive),
                "result_zip_sha256": sha256_file(archive),
                "markdown_path": str(markdown),
                "markdown_sha256": sha256_file(markdown),
                "markdown_character_count": len(markdown.read_text(encoding="utf-8", errors="replace")),
                "content_list_path": str(content_list) if content_list else None,
                "middle_json_path": str(middle_json) if middle_json else None,
                "output_has_native_layout_json": bool(content_list or middle_json),
            }
        )
    result_path = case_root / "mineru_api_result.json"
    result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**record, "record_path": str(result_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--source-authority",
        type=Path,
        help="Original source-of-truth file when --input is one derived PDF (for example DOCX -> PDF).",
    )
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-interval-seconds", type=int, default=8)
    parser.add_argument(
        "--ocr-mode",
        choices=["auto", "true", "false"],
        default="auto",
        help="Whether the uploaded file is an OCR recovery run. Auto treats a DOC/DOCX-derived PDF as non-OCR.",
    )
    parser.add_argument(
        "--authorization-scope",
        required=True,
        help="Non-secret audit statement describing the user-authorized upload scope.",
    )
    args = parser.parse_args()

    source_path = args.input.resolve()
    files = discover_inputs(source_path)
    if not files:
        raise ValueError(f"No supported MinerU inputs found under {source_path}")
    if len(files) > 200:
        raise ValueError("MinerU precision batches are limited to 200 files; split this run")
    if args.source_authority and len(files) != 1:
        raise ValueError("--source-authority requires exactly one uploaded input")
    args.output_root.mkdir(parents=True, exist_ok=True)
    token, api_base, base_source = load_configuration(args.env_file.resolve())
    uploaded_hashes = [sha256_file(path) for path in files]
    authority_files = [args.source_authority.resolve()] if args.source_authority else files
    if args.source_authority and not authority_files[0].exists():
        raise FileNotFoundError(authority_files[0])
    authority_hashes = [sha256_file(path) for path in authority_files]
    data_ids = [f"phase2-{digest[:20]}" for digest in uploaded_hashes]
    client = MinerUPrecisionClient(token, api_base)

    started_at = now_utc()
    batch_id, upload_urls, submit_trace_id = client.create_batch(files, data_ids)
    for path, signed_url in zip(files, upload_urls):
        print(f"UPLOAD {path.name} bytes={path.stat().st_size}", flush=True)
        client.upload(path, signed_url)
    results, poll_trace_id = client.poll(batch_id, args.timeout_seconds, args.poll_interval_seconds)
    result_by_data_id = {str(row.get("data_id")): row for row in results}
    result_by_name = {str(row.get("file_name")): row for row in results}
    records = []
    for path, uploaded_digest, authority, authority_digest, data_id in zip(
        files, uploaded_hashes, authority_files, authority_hashes, data_ids
    ):
        result = result_by_data_id.get(data_id) or result_by_name.get(path.name)
        if result is None:
            raise RuntimeError(f"MinerU result missing for {path.name}")
        records.append(
            write_result(
                source=authority,
                uploaded_file=path,
                source_hash=authority_digest,
                uploaded_file_hash=uploaded_digest,
                data_id=data_id,
                batch_id=batch_id,
                result=result,
                output_root=args.output_root,
                authorization_scope=args.authorization_scope,
                is_ocr=(
                    args.ocr_mode == "true"
                    or (
                        args.ocr_mode == "auto"
                        and authority.suffix.lower() not in {".doc", ".docx"}
                    )
                ),
            )
        )
        print(f"DONE {path.name} state={result.get('state')}", flush=True)
    manifest = {
        "run_id": f"mineru-precision-{batch_id}",
        "started_at": started_at,
        "finished_at": now_utc(),
        "api_base": api_base,
        "api_base_configuration": base_source,
        "api_mode": "precision_v4_signed_batch_upload",
        "model_version": "vlm",
        "batch_id": batch_id,
        "submit_trace_id": submit_trace_id,
        "poll_trace_id": poll_trace_id,
        "token_persisted": False,
        "signed_urls_persisted": False,
        "authorization_scope": args.authorization_scope,
        "records": records,
    }
    manifest_path = args.output_root / "mineru_precision_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), "completed": len(records)}, ensure_ascii=False))
    return 0 if all(row.get("state") == "done" for row in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
