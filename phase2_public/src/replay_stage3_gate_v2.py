"""Offline replay of frozen saved responses through the Phase 2 gate.

This script never calls DeepSeek, MinerU, PaddleOCR, or external retrieval.
It reads saved source files without modifying them and writes derived gate
results under a new local Phase 2 run directory.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


MODEL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = MODEL_ROOT / ".local_runs" / "replay" / "source_saved_responses"
GATE_OUTPUT_ROOT = MODEL_ROOT / ".local_runs" / "replay" / "gate"
DEFAULT_OUTPUT_DIR = GATE_OUTPUT_ROOT / "saved60_replay_final"
PREVIOUS_OUTPUT_DIR = GATE_OUTPUT_ROOT / "saved60_replay_previous"
FROZEN_DIR = MODEL_ROOT / ".local_runs" / "retrieval" / "frozen_gold60_rebenchmark"

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from conclusion_contract_v2 import legacy_test_result  # noqa: E402
from llm_abstention_gate import apply_gate  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_files(source_dir: Path) -> list[Path]:
    return sorted(
        path for path in source_dir.glob("SYN-P1-*.json") if path.is_file()
    )


def _stage2_parsed(source: dict[str, Any]) -> Any:
    final_response = source.get("final_llm_response")
    if isinstance(final_response, dict):
        return final_response.get("parsed")
    return None


def _result_summary(gate_result: dict[str, Any]) -> dict[str, Any]:
    response = gate_result.get("response")
    response = response if isinstance(response, dict) else {}
    findings = response.get("findings")
    findings = findings if isinstance(findings, list) else []
    states = Counter(
        str(row.get("conclusion_type", ""))
        for row in findings
        if isinstance(row, dict)
    )
    legacy = Counter(
        legacy_test_result(row.get("conclusion_type"))
        for row in findings
        if isinstance(row, dict)
    )
    audit = response.get("stage3_decision_audit")
    audit = audit if isinstance(audit, dict) else {}
    return {
        "status": gate_result.get("status"),
        "blocked": gate_result.get("blocked") is True,
        "finding_count": len(findings),
        "conclusion_type_counts": dict(states),
        "legacy_three_class_counts": dict(legacy),
        "confirmation_validation_available_count": audit.get(
            "confirmation_validation_available_count", 0
        ),
        "confirmation_candidate_count": audit.get("confirmation_candidate_count", 0),
        "confirmed_count": audit.get("confirmed_count", 0),
    }


def replay(source_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to(GATE_OUTPUT_ROOT.resolve()) or output_dir == GATE_OUTPUT_ROOT.resolve():
        raise RuntimeError("derived replay output must be a child of the authorized gate directory")
    if output_dir == source_dir.resolve() or output_dir == PREVIOUS_OUTPUT_DIR.resolve():
        raise RuntimeError("use a separate final output, preserving source and rejected intermediate replay")
    source_files = _source_files(source_dir)
    if len(source_files) != 60:
        raise RuntimeError(
            f"expected exactly 60 saved SYN-P1 files, found {len(source_files)} in {source_dir}"
        )
    protected_paths = source_files + sorted(path for path in FROZEN_DIR.rglob("*") if path.is_file())
    protected_before = {str(path): _sha256(path) for path in protected_paths}
    output_dir.mkdir(parents=True, exist_ok=True)

    state_counts: Counter[str] = Counter()
    legacy_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    blocked_count = 0
    available_count = 0
    candidate_count = 0
    confirmed_count = 0
    source_hashes: list[dict[str, str]] = []
    output_files: list[str] = []
    changed_cases: list[dict[str, Any]] = []

    for source_path in source_files:
        source = json.loads(source_path.read_text(encoding="utf-8"))
        runtime_input = source.get("runtime_input")
        runtime_input = deepcopy(runtime_input) if isinstance(runtime_input, dict) else {}
        parsed = deepcopy(_stage2_parsed(source))
        gate_result = apply_gate(parsed, runtime_input)
        summary = _result_summary(gate_result)
        previous_path = PREVIOUS_OUTPUT_DIR / source_path.name
        if previous_path.exists():
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
            previous_states = previous.get("derived_summary", {}).get("conclusion_type_counts", {})
            if previous_states != summary["conclusion_type_counts"]:
                changed_cases.append({
                    "issue_id": source.get("issue_id"), "before": previous_states,
                    "after": summary["conclusion_type_counts"],
                    "runtime_fact": runtime_input.get("contract_evidence", {}),
                    "reasons": [row.get("reasoning_conclusion") for row in gate_result["response"].get("findings", [])],
                })
        response = gate_result.get("response")
        response = response if isinstance(response, dict) else {}
        for finding in response.get("findings", []):
            if not isinstance(finding, dict):
                continue
            state = str(finding.get("conclusion_type", ""))
            state_counts[state] += 1
            legacy_counts[legacy_test_result(state)] += 1
        status_counts[str(gate_result.get("status", ""))] += 1
        blocked_count += int(summary["blocked"])
        available_count += int(summary["confirmation_validation_available_count"] or 0)
        candidate_count += int(summary["confirmation_candidate_count"] or 0)
        confirmed_count += int(summary["confirmed_count"] or 0)

        source_hash = _sha256(source_path)
        source_hashes.append({"file": source_path.name, "sha256": source_hash})
        output_name = source_path.name
        output_path = output_dir / output_name
        derived = {
            "stage3_replay_version": "v2",
            "replay_mode": "offline_saved60",
            "api_calls": {
                "deepseek": False,
                "mineru": False,
                "paddleocr": False,
                "external_retrieval": False,
            },
            "source_stage2_file": str(source_path),
            "source_stage2_sha256": source_hash,
            "issue_id": source.get("issue_id"),
            "model": source.get("model"),
            "raw_stage2_final_llm_response": deepcopy(source.get("final_llm_response")),
            "stage3_gate_result": gate_result,
            "derived_summary": summary,
        }
        _write_json(output_path, derived)
        output_files.append(str(output_path))

    protected_after = {str(path): _sha256(path) for path in protected_paths}
    if protected_before != protected_after:
        raise RuntimeError("protected Stage 2/frozen source changed during replay")
    protected_digest = hashlib.sha256(json.dumps(protected_before, sort_keys=True).encode("utf-8")).hexdigest()
    implementation_files = [
        "scripts/llm_abstention_gate.py", "scripts/test_post_llm_gate_v2.py",
        "scripts/test_post_llm_recommendation_v1.py", "scripts/replay_stage3_gate_v2.py",
        "prompts/system_prompt_final.md", "scripts/external_fallback_v2.py",
    ]
    manifest = {
        "stage3_replay_version": "v2",
        "replay_mode": "offline_saved60",
        "source_stage2_dir": str(source_dir),
        "output_dir": str(output_dir),
        "source_file_count": len(source_files),
        "output_file_count": len(output_files),
        "source_hashes": source_hashes,
        "api_calls": {
            "deepseek": False,
            "mineru": False,
            "paddleocr": False,
            "external_retrieval": False,
        },
        "status_counts": dict(status_counts),
        "blocked_count": blocked_count,
        "conclusion_type_counts": dict(state_counts),
        "legacy_three_class_counts": dict(legacy_counts),
        "confirmation_validation_available_count": available_count,
        "confirmation_candidate_count": candidate_count,
        "confirmed_count": confirmed_count,
        "claim_confirmation_note": (
            "Saved Stage 2 runtime inputs contain no trusted upstream claim confirmation records; "
            "the replay intentionally fabricates none, so confirmed_count must remain zero."
        ),
        "source_stage2_unchanged": True,
        "frozen_rebenchmark_unchanged": True,
        "protected_file_count": len(protected_before),
        "protected_files_digest_before": protected_digest,
        "protected_files_digest_after": protected_digest,
        "implementation_sha256": {name: _sha256(MODEL_ROOT / name) for name in implementation_files},
        "changed_cases_from_rejected_intermediate": changed_cases,
        "distribution_note": "Descriptive offline counts only; neither gold labels nor a target distribution determine runtime decisions.",
        "output_schema": {
            "raw_stage2_final_llm_response": "original saved transport/parse record copied into derived output",
            "stage3_gate_result": "apply_gate(raw parsed response, runtime_input)",
            "derived_summary": "per-file canonical state and confirmation counters",
        },
        "output_files": output_files,
    }
    _write_json(output_dir / "manifest.json", manifest)
    lines = [
        "# Stage 3 v2 saved-60 offline replay",
        "",
        "No DeepSeek, MinerU, PaddleOCR, or external retrieval call was made.",
        "Stage 2 source files were read only and were not modified.",
        "",
        f"- Source files: {len(source_files)}",
        f"- Derived files: {len(output_files)}",
        f"- Blocked files: {blocked_count}",
        f"- Trusted confirmation records: {available_count}",
        f"- Confirmation candidates: {candidate_count}",
        f"- Confirmed findings: {confirmed_count}",
        "",
        "Canonical conclusion counts:",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(state_counts.items()))
    lines.extend(
        [
            "",
            "Files:",
            "",
            "- `manifest.json` — replay manifest, source hashes, counts, and schema.",
            "- `SYN-P1-*.json` — one derived gate result per saved Stage 2 issue, with raw Stage 2 transport preserved separately.",
        ]
    )
    (output_dir / "replay_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    manifest = replay(args.source_dir, args.output_dir)
    print(json.dumps({
        "source_file_count": manifest["source_file_count"],
        "output_file_count": manifest["output_file_count"],
        "blocked_count": manifest["blocked_count"],
        "confirmation_validation_available_count": manifest["confirmation_validation_available_count"],
        "confirmation_candidate_count": manifest["confirmation_candidate_count"],
        "confirmed_count": manifest["confirmed_count"],
        "conclusion_type_counts": manifest["conclusion_type_counts"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
