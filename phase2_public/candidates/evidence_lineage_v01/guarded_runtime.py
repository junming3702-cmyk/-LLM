"""Opt-in wrapper for the existing three-layer prepared request directory.

This file does not make an API call when imported or when run as a CLI. A
caller must explicitly invoke ``run_guarded`` with an existing prepared
directory and environment file. Frozen v0.1 requests/results are unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from preflight import audit_preflight, capture_selected_from_retrieval


def verify_request(record: dict[str, Any], selection: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = record.get("context")
    body = record.get("body")
    if not isinstance(ctx, dict) or not isinstance(body, dict):
        return {"status": "blocked_before_inference", "errors": ["prepared_record_missing_context_or_body"]}
    users = [m for m in body.get("messages", []) if isinstance(m, dict) and m.get("role") == "user"]
    if not users or not isinstance(users[-1].get("content"), str):
        return {"status": "blocked_before_inference", "errors": ["prepared_request_missing_user_content"]}
    selected = ctx.get("laws")
    if not isinstance(selected, list) or not isinstance(ctx.get("task"), dict):
        return {"status": "blocked_before_inference", "errors": ["trusted_context_missing_task_or_laws"]}
    independent_selection = False
    if isinstance(selection, dict) and isinstance(selection.get("retrieval_audit"), list):
        try:
            expected = capture_selected_from_retrieval(selection["retrieval_audit"], ctx["task"])
            independent_selection = all(selection.get(k) == expected[k] for k in
                                        ("origin", "retrieval_audit_sha256", "task_sha256", "selected_chunks"))
        except (TypeError, ValueError, KeyError):
            pass
    audited_selection = selection["selected_chunks"] if independent_selection else selected
    audit = audit_preflight(ctx["task"], users[-1]["content"], audited_selection)
    try:
        exact = json.loads(users[-1]["content"]) == ctx
    except ValueError:
        exact = False
    if not exact:
        audit["errors"].append("full_trusted_context_changed_in_final_request")
        audit["status"] = "blocked_before_inference"
    if selection is not None and not independent_selection:
        audit["errors"].append("upstream_selection_manifest_invalid")
        audit["status"] = "blocked_before_inference"
    audit["upstream_selection_status"] = "captured_before_final_packet" if independent_selection else "unverified_internal_packet_only"
    if audit["status"] == "ready_for_inference" and not independent_selection:
        audit["status"] = "internal_binding_only"
    return audit


def preflight_directory(directory: Path, selection_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    lock_path = directory / "lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    per_case = {}
    for case_id in lock["order"]:
        path = directory / "requests" / f"{case_id}.json"
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != lock["request_hashes"][case_id]:
            per_case[case_id] = {"status": "blocked_before_inference", "errors": ["frozen_request_hash_mismatch"]}
            continue
        selection = (selection_manifest or {}).get(case_id)
        per_case[case_id] = verify_request(json.loads(path.read_text(encoding="utf-8")), selection)
    statuses = {x["status"] for x in per_case.values()}
    overall = ("ready_for_inference" if statuses == {"ready_for_inference"} else
               "internal_binding_only" if statuses == {"internal_binding_only"} else "blocked_before_inference")
    return {"status": overall, "per_case": per_case, "provider_calls": 0,
            "original_requests_modified": False}


def run_guarded(directory: Path, env_file: Path, selection_manifest: dict[str, Any]) -> Any:
    """Explicit future opt-in call; nothing is automatically sent by this module."""
    audit = preflight_directory(directory, selection_manifest)
    if audit["status"] != "ready_for_inference":
        raise ValueError("evidence_or_task_preflight_blocked")
    old_module_path = Path(__file__).resolve().parent.parent / "three_layer_handoff_v01" / "online_validation.py"
    return subprocess.run([sys.executable, str(old_module_path), "run", "--output", str(directory),
                           "--env-file", str(env_file)], check=True, cwd=old_module_path.parent)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.selection_manifest.read_text(encoding="utf-8")) if args.selection_manifest else None
    report = preflight_directory(args.prepared_dir, manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["status"] in ("ready_for_inference", "internal_binding_only") else 2)


if __name__ == "__main__":
    main()
