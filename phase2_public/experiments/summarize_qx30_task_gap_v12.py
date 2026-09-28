"""Summarize private formative QX30 records without loading reference labels."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def state_label(state: dict) -> str:
    if state.get("blocked"):
        return "HOLD:" + str(state.get("failure_class") or "unspecified")
    types = state.get("conclusion_types") or []
    return "+".join(types) if types else "NO_CONCLUSION"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paired-v11-dir", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    binding = read(args.run_dir / "binding.json")
    rows: list[dict] = []
    for index in range(1, 31):
        uid = f"QX-U{index:02d}"
        prior = read(args.paired_v11_dir / "responses" / "v11" / f"{uid}.json")
        offline = read(args.run_dir / "offline_replay" / f"{uid}.json")
        online = read(args.run_dir / "online_candidate" / f"{uid}.json")
        original = read(Path(prior["source_path"]))
        runtime = original["runtime_input"]
        task = runtime.get("review_task_contract_v2") or {}
        task_file = args.run_dir / "source_bound_tasks" / f"{uid}.json"
        task_result = read(task_file) if task_file.is_file() else {}
        raw = (online.get("response") or {}).get("parsed") or {}
        findings = raw.get("findings") or []
        finding = findings[0] if findings and isinstance(findings[0], dict) else {}
        basis = finding.get("legal_u_basis") or {}
        rows.append({
            "issue_id": uid,
            "task_type": task.get("declared_task_type"),
            "task_scope": task.get("scope"),
            "question": task.get("question_verbatim"),
            "old_v11_gated": state_label(offline["old_gate"]),
            "old_raw_under_new_gate": state_label(offline["new_gate"]),
            "new_raw_conclusion": finding.get("conclusion_type") or "NOT_CALLED_OR_UNPARSEABLE",
            "new_gated": state_label(online["gate_state"]),
            "new_gate_reason": online["gate_state"].get("reason", ""),
            "legal_u_basis_present": bool(basis),
            "independent_validated_gap_rows": binding["units"][uid]["verified_legal_u_gap_rows"],
            "separate_task_completion": (task_result.get("task_gate") or {}).get("response", {}).get("task_completion", ""),
            "legal_model_called": not online.get("online_legal_call_skipped", False),
            "finish_reason": (online.get("response") or {}).get("finish_reason", ""),
            "prompt_tokens": ((online.get("response") or {}).get("usage") or {}).get("prompt_tokens", ""),
            "completion_tokens": ((online.get("response") or {}).get("usage") or {}).get("completion_tokens", ""),
            "input_sha256": binding["units"][uid]["frozen_input_sha256"],
        })
    if len(rows) != 30 or len({row["issue_id"] for row in rows}) != 30:
        raise RuntimeError("incomplete_30_unit_comparison")
    output = args.run_dir / "QX30_v12_逐题复测.csv"
    with output.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    old = Counter(row["old_v11_gated"] for row in rows)
    new = Counter(row["new_gated"] for row in rows)
    task = Counter(row["separate_task_completion"] for row in rows if row["separate_task_completion"])
    total_prompt = sum(int(row["prompt_tokens"]) for row in rows if row["prompt_tokens"] != "")
    total_completion = sum(int(row["completion_tokens"]) for row in rows if row["completion_tokens"] != "")
    lines = [
        "# QX30 v12 task-gap controlled retest (formative)", "",
        "The same 30 historical final-inference excerpts and frozen legal evidence were used. "
        "The v12 arm changes the system addendum, supplies a separate caller-side gap ledger, "
        "opts in to the task-aware gate, and routes four source-bound tasks outside legal inference. "
        "Therefore this is a multi-component protocol check, not a single-factor prompt improvement or independent accuracy estimate.", "",
        "No award/selection decision, expert scores, gold answer, or reference judgment entered the model input. "
        "Winning a tender is not a per-issue N label. A positive text observation is not full legal compliance.", "",
        f"- Old v11 gate counts (n=30): {dict(old)}",
        f"- New gate counts (n=30): {dict(new)}",
        f"- Separate source-bound task completion (n={sum(task.values())}): {dict(task)}",
        f"- Legal model called: {sum(row['legal_model_called'] for row in rows)}/30; "
        f"no legal call for {30-sum(row['legal_model_called'] for row in rows)} source-bound tasks.",
        f"- Usage for recorded online calls: prompt {total_prompt}, completion {total_completion} tokens. "
        "This is API usage, not reviewer time or monetary cost.", "",
        "`HOLD` is a processing/protocol state, not a legal U and not an N. "
        "The offline replay is a gate-only check on old raw responses; it cannot assess whether the revised prompt "
        "elicits a valid legal_u_basis. The online arm tests that separately.", "",
        "| Unit | Locked task | v11 gated | old raw/new gate | v12 online gated | source-bound route |", "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[key]).replace("|", "\\|") for key in
                       ("issue_id", "task_type", "old_v11_gated", "old_raw_under_new_gate",
                        "new_gated", "separate_task_completion")) + " |")
    lines += ["", "Limitations: QX30 and its frozen inputs have been used in development; this cannot establish "
              "independent accuracy, complete-package coverage, professional net benefit, or reduced review time. "
              "Holds require source recovery/task-contract repair or independent gap attestation, not relabeling as N."]
    (args.run_dir / "QX30_v12_受控复测报告.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"old": dict(old), "new": dict(new), "source_bound": dict(task),
                      "legal_calls": sum(row["legal_model_called"] for row in rows),
                      "prompt_tokens": total_prompt, "completion_tokens": total_completion,
                      "table": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
