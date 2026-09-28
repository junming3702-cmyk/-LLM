"""Formative QX30 gate replay and optional fixed-evidence v12 candidate call.

Never reads gold labels, expert results, award material, or source PDFs.
The candidate adds a caller-side gap audit to the same frozen final input;
it is therefore a protocol/input intervention, not a single-factor prompt test.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import requests


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def require(predicate: bool, reason: str) -> None:
    if not predicate:
        raise RuntimeError(reason)


def gate_state(gate: dict) -> dict:
    rows = ((gate.get("response") or {}).get("findings") or [])
    types = [row.get("conclusion_type") for row in rows if isinstance(row, dict)]
    return {"blocked": gate.get("blocked") is True,
            "failure_class": gate.get("failure_class"),
            "conclusion_types": types,
            "reason": (gate.get("actions") or [""])[-1]}


def nonlegal_task_route(runtime: dict) -> bool:
    task = runtime.get("review_task_contract_v2") or {}
    return (task.get("declared_task_type") == "document_completeness"
            or (task.get("declared_task_type") == "document_response"
                and task.get("scope") == "supplied_text_consistency"))


def load_compact_contract(path: Path) -> str:
    """Reuse the runner's exact constant without importing embedding models."""
    module = ast.parse(path.read_text(encoding="utf-8"))
    for node in module.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "FINAL_COMPACT_OUTPUT_CONTRACT"):
            return ast.literal_eval(node.value)
    raise RuntimeError("compact_output_contract_not_found")


def one_model_call(api_key: str, prompt: str, runtime: dict) -> dict:
    """Fixed parameters and channel merge mirror the existing runner."""
    from llm_response_parser_v1 import channel_diagnostic_snapshot, select_final_response

    body = {"model": "deepseek-v4-flash", "messages": [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(runtime, ensure_ascii=False, indent=2)},
    ], "temperature": 0.1, "max_tokens": 16384,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "enabled"}, "reasoning_effort": "low"}
    started = time.monotonic()
    response = requests.post(
        os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body, timeout=180)
    elapsed = round(time.monotonic() - started, 3)
    try:
        payload = response.json()
    except ValueError:
        payload = {"non_json_http_body": response.text[:2000]}
    choice = payload.get("choices", [{}])[0] if response.ok else {}
    message = choice.get("message", {}) if isinstance(choice, dict) else {}
    selected = select_final_response(message)
    return {
        "http_status": response.status_code, "ok": response.ok,
        "elapsed_seconds": elapsed, "model_requested": "deepseek-v4-flash",
        "model_returned": payload.get("model"),
        "thinking_mode_requested": "enabled", "reasoning_effort_requested": "low",
        "finish_reason": choice.get("finish_reason") if isinstance(choice, dict) else None,
        "usage": payload.get("usage"),
        "response_channel_diagnostics": {
            "response_contract": "final_review", "selection_rule": selected.get("selection_rule"),
            "selected_channel": selected.get("selected_channel"),
            "selected_parse_method": selected.get("selected_parse_method"),
            "reasoning_content": channel_diagnostic_snapshot(selected.get("reasoning_content", {})),
            "content": channel_diagnostic_snapshot(selected.get("content", {})),
        },
        "parsed": selected.get("parsed"),
        "selected_text": selected.get("selected_text", ""),
        "error_payload": None if response.ok else payload,
    }


def reconcile(gate: dict, runtime: dict) -> dict:
    """Retain the frozen non-bundle Level-1/Level-2 delivery guard."""
    if gate.get("blocked"):
        return gate
    levels = {row.get("level"): row for row in
              (runtime.get("hierarchy_retrieval_audit") or {}).get("levels", [])
              if isinstance(row, dict)}
    level1, level2 = levels.get("Level 1") or {}, levels.get("Level 2") or {}
    if (level1.get("level_state") != "relevant_but_inconclusive"
            or level2.get("level_state") != "no_usable_violation_found"):
        return gate
    def selected(level: dict) -> set[str]:
        rows = level.get("phases") or []
        result: set[str] = set()
        for phase in rows:
            if not isinstance(phase, dict):
                continue
            decision = phase.get("decision")
            ids = decision.get("selected_chunk_ids") if isinstance(decision, dict) else phase.get("selected_chunk_ids")
            if isinstance(ids, list):
                result.update(str(x) for x in ids if x)
        return result
    l1, l2 = selected(level1), selected(level2)
    if not l2:
        return gate
    for finding in (gate.get("response") or {}).get("findings", []) or []:
        if finding.get("conclusion_type") not in {"requires_human_legal_review",
                                                 "requires_human_legal_confirm"}:
            continue
        citations = {str(row.get("chunk_id")) for row in finding.get("legal_evidence", [])
                     if isinstance(row, dict) and row.get("chunk_id")}
        if not citations.isdisjoint(l1) and (citations.isdisjoint(l2)
                                             or not str(finding.get("conflict_note") or "").strip()):
            return {**gate, "status": "blocked", "blocked": True,
                    "failure_class": "cross_level_protocol_failure",
                    "legal_conclusion_available": False,
                    "actions": list(gate.get("actions", [])) + ["cross_level_reconciliation_missing"]}
    return gate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-package", required=True, type=Path)
    parser.add_argument("--paired-v11-dir", required=True, type=Path)
    parser.add_argument("--baseline-prompt", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--ids", nargs="*", default=[])
    args = parser.parse_args()
    all_ids = [f"QX-U{i:02d}" for i in range(1, 31)]
    ids = args.ids or all_ids
    require(len(ids) == len(set(ids)) and set(ids) <= set(all_ids), "invalid issue list")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.runtime_package / "src"))
    from llm_abstention_gate import apply_gate
    from task_gap_protocol_v1 import attach_audit, prompt_addendum, digest

    if args.online:
        require(args.env_file is not None and args.env_file.is_file(), "online requires env file")
        os.environ["MODEL_PHASE_ROOT"] = str(args.runtime_package)
        os.environ["MODEL_ENV_FILE"] = str(args.env_file)
        os.environ.setdefault("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    base = args.baseline_prompt.read_text(encoding="utf-8")
    require("## 11. Required JSON output" in base, "candidate base prompt incomplete")
    effective_prompt = (base + load_compact_contract(args.runtime_package / "src" /
                                                     "run_hierarchy_gated_llm_smoke.py")
                        + prompt_addendum())
    manifest = {
        "design": "QX30-formative-fixed-final-input-v12-task-gap-protocol",
        "input_change": "appended caller-side task_gap_audit + gate opt-in; no retrieval, source, or model-label change",
        "prompt_change": "v11 + compact contract + schema-generated legal-U addendum for online arm",
        "not_independent_holdout": True,
        "no_award_or_expert_input": True,
        "model": "deepseek-v4-flash", "temperature": 0.1,
        "reasoning_effort": "low", "max_tokens": 16384,
        "base_prompt_sha256": sha(base.encode("utf-8")),
        "prompt_addendum_sha256": sha(prompt_addendum().encode("utf-8")),
        "effective_prompt_sha256": sha(effective_prompt.encode("utf-8")),
        "gate_sha256": sha((args.runtime_package / "src" / "llm_abstention_gate.py").read_bytes()),
        "gap_protocol_sha256": sha((args.runtime_package / "src" / "task_gap_protocol_v1.py").read_bytes()),
        "units": {},
    }
    frozen: dict[str, dict] = {}
    for uid in all_ids:
        prior_file = args.paired_v11_dir / "responses" / "v11" / f"{uid}.json"
        prior = read(prior_file)
        source = Path(prior["source_path"])
        source_result = read(source)
        request = source_result["final_llm_response"]["request_body"]
        require(request["model"] == "deepseek-v4-flash"
                and request["temperature"] == 0.1
                and request["reasoning_effort"] == "low"
                and request["max_tokens"] == 16384, f"model settings drift {uid}")
        source_text = request["messages"][1]["content"]
        require(sha(source_text.encode("utf-8")) == prior["input_sha256"], f"input drift {uid}")
        require("REF-QX-" not in source_text, f"reference leakage {uid}")
        runtime = json.loads(source_text)
        require(runtime.get("issue_id") == uid, f"identity drift {uid}")
        require((runtime.get("project_context") or {}).get("reference_or_award_materials_included") is False,
                f"award input flag {uid}")
        audited = attach_audit(runtime)
        frozen[uid] = {"runtime": audited, "prior": prior}
        manifest["units"][uid] = {
            "frozen_input_sha256": prior["input_sha256"],
            "augmented_runtime_sha256": digest(audited),
            "prior_response_sha256": sha(prior_file.read_bytes()),
            "verified_legal_u_gap_rows": sum(row["validated"] for row in audited["task_gap_audit"]),
            "nonlegal_task_route": nonlegal_task_route(audited),
        }
    binding_path = args.out / "binding.json"
    if binding_path.exists():
        require(read(binding_path) == manifest, "run binding changed; use new output folder")
    else:
        write_new(binding_path, manifest)

    for uid in ids:
        item = frozen[uid]
        offline_path = args.out / "offline_replay" / f"{uid}.json"
        if not offline_path.exists():
            raw = item["prior"]["response"].get("parsed")
            gate = apply_gate(raw, item["runtime"])
            write_new(offline_path, {
                "issue_id": uid, "source_arm": "v11_previous_raw_response",
                "frozen_input_sha256": manifest["units"][uid]["frozen_input_sha256"],
                "augmented_runtime_sha256": manifest["units"][uid]["augmented_runtime_sha256"],
                "raw_conclusions": [f.get("conclusion_type") for f in (raw or {}).get("findings", [])],
                "old_gate": gate_state(item["prior"]["gate"]),
                "new_gate": gate_state(gate),
                "gate": gate,
            })
        if not args.online:
            continue
        online_path = args.out / "online_candidate" / f"{uid}.json"
        if online_path.exists():
            continue
        if nonlegal_task_route(item["runtime"]):
            record = {"issue_id": uid, "online_legal_call_skipped": True,
                      "skip_reason": "source_bound_task_route_required",
                      "gate_state": {"blocked": True, "failure_class": "task_route_mismatch",
                                     "conclusion_types": [],
                                     "reason": "Legal LLM not called for a source-bound observation task"}}
            write_new(online_path, record)
            print(json.dumps({"issue_id": uid, **record["gate_state"]}, ensure_ascii=False), flush=True)
            continue
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=args.env_file, override=False)
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        require(bool(key), "DeepSeek API key unavailable")
        started = time.monotonic()
        try:
            response = one_model_call(key, effective_prompt, copy.deepcopy(item["runtime"]))
            from llm_abstention_gate import processing_hold
            if response.get("ok") is False:
                gate = processing_hold(response.get("selected_text", ""), item["runtime"],
                                       "llm_transport_or_http_failure_not_legal_u",
                                       failure_class="transport_failure")
            elif response.get("finish_reason") == "length":
                gate = processing_hold(response.get("selected_text", ""), item["runtime"],
                                       "llm_output_truncated_not_legal_u",
                                       failure_class="truncated_output")
            elif not isinstance(response.get("parsed"), dict):
                gate = processing_hold(response.get("selected_text", ""), item["runtime"],
                                       "llm_final_json_unparseable_not_legal_u",
                                       failure_class="invalid_json")
            else:
                gate = apply_gate(response["parsed"], item["runtime"])
            gate = reconcile(gate, item["runtime"])
            safe_response = response
            record = {"issue_id": uid, "elapsed_seconds": time.monotonic() - started,
                      "frozen_input_sha256": manifest["units"][uid]["frozen_input_sha256"],
                      "augmented_runtime_sha256": manifest["units"][uid]["augmented_runtime_sha256"],
                      "response": safe_response, "gate": gate,
                      "gate_state": gate_state(gate)}
        except Exception as exc:
            record = {"issue_id": uid, "elapsed_seconds": time.monotonic() - started,
                      "execution_error": type(exc).__name__,
                      "gate_state": {"blocked": True, "failure_class": "execution_failure",
                                     "conclusion_types": [], "reason": type(exc).__name__}}
        write_new(online_path, record)
        print(json.dumps({"issue_id": uid, **record["gate_state"]}, ensure_ascii=False), flush=True)

    summary = {"design": manifest["design"], "n_scheduled": len(ids), "offline": {}, "online": {}}
    for kind, folder in (("offline", "offline_replay"), ("online", "online_candidate")):
        counts: dict[str, int] = {}
        for uid in all_ids:
            file = args.out / folder / f"{uid}.json"
            if not file.is_file():
                continue
            record = read(file)
            state = record["new_gate"] if kind == "offline" else record["gate_state"]
            label = ("blocked:" + str(state["failure_class"]) if state["blocked"]
                     else "+".join(state["conclusion_types"]) or "no_conclusion")
            counts[label] = counts.get(label, 0) + 1
        summary[kind] = {"recorded": sum(counts.values()), "counts": counts}
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
