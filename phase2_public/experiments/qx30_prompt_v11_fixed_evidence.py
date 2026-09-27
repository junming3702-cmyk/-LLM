"""Paired fixed-evidence QX30 prompt check; never loads reference or expert files.

The historical final-request *user* input is frozen. Only the base system
prompt changes (active v10 versus candidate v11); old task/scope/compact
overlays, DeepSeek settings, and the historical gate are identical in both
arms. This is a formative development comparison, not an independent holdout.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_once(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-package", required=True, type=Path)
    parser.add_argument("--historical-package", required=True, type=Path)
    parser.add_argument("--historical-results", required=True, type=Path)
    parser.add_argument("--revision-results", required=True, type=Path)
    parser.add_argument("--prompt-snapshot", required=True, type=Path)
    parser.add_argument("--baseline-prompt", required=True, type=Path)
    parser.add_argument("--candidate-prompt", required=True, type=Path)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--ids", nargs="*", default=[])
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()

    require(args.workers in (1, 2, 3), "workers must be 1, 2 or 3")
    require(args.env_file.is_file(), "missing API environment file")
    require(args.runtime_package.is_dir(), "missing current runtime package")
    require(args.historical_package.is_dir(), "missing historical integrity helpers")
    os.environ["MODEL_PHASE_ROOT"] = str(args.runtime_package)
    os.environ["MODEL_ENV_FILE"] = str(args.env_file)
    os.environ.setdefault("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(args.runtime_package / "src"), str(args.historical_package / "src")]
    import run_hierarchy_gated_llm_smoke as runner
    from experiment_integrity import result_status, validate_runtime

    snapshot = read_json(args.prompt_snapshot)
    historical_effective = snapshot["effective_final"]
    require(isinstance(historical_effective, str) and len(historical_effective) > 1000, "invalid historical prompt snapshot")

    prompts = {}
    for arm, source in (("v10", args.baseline_prompt), ("v11", args.candidate_prompt)):
        base = source.read_text(encoding="utf-8")
        require("## 11. Required JSON output" in base, f"{arm}: missing JSON schema")
        # The current non-bundle route appends only its compact-output overlay.
        # Historical task-gate-v2 text-replacement overlay is incompatible with
        # both modern base prompts, so it is not silently transplanted here.
        prompts[arm] = base + runner.FINAL_COMPACT_OUTPUT_CONTRACT
    require(prompts["v10"] != prompts["v11"], "prompts are identical")

    all_ids = [f"QX-U{i:02d}" for i in range(1, 31)]
    ids = args.ids or all_ids
    require(bool(ids) and len(ids) == len(set(ids)) and set(ids) <= set(all_ids), "invalid IDs")
    frozen = {}
    for uid in ids:
        revision_file = args.revision_results / f"{uid}.json"
        source = revision_file if revision_file.is_file() else args.historical_results / f"{uid}.json"
        require(source.is_file(), f"missing frozen result {uid}")
        prior = read_json(source)
        request = prior.get("final_llm_response", {}).get("request_body", {})
        messages = request.get("messages", [])
        require(len(messages) == 2, f"missing frozen final request {uid}")
        require(messages[0].get("content") == historical_effective, f"historical prompt drift {uid}")
        require(request.get("model") == "deepseek-v4-flash", f"model drift {uid}")
        require(request.get("temperature") == 0.1, f"temperature drift {uid}")
        require(request.get("max_tokens") == 16384, f"budget drift {uid}")
        require(request.get("reasoning_effort") == "low", f"reasoning drift {uid}")
        user_text = messages[1].get("content", "")
        require("REF-QX-" not in user_text, f"reference leakage marker {uid}")
        runtime = json.loads(user_text)
        validate_runtime(runtime)
        require(runtime.get("issue_id") == uid, f"unit ID mismatch {uid}")
        context = runtime.get("project_context", {})
        require(context.get("reference_or_award_materials_included") is False, f"award leakage flag {uid}")
        task = runtime.get("review_task_contract_v2", {})
        require(task.get("question_verbatim") == context.get("review_question"), f"task-question drift {uid}")
        frozen[uid] = {
            "runtime": runtime,
            "input_sha256": sha256(user_text.encode("utf-8")),
            "source_path": str(source),
            "source_sha256": file_sha256(source),
            "historical_execution_status": prior.get("assessment_status", {}).get("execution_status"),
        }

    binding = {
        "design": "paired_v10_v11_current_nonbundle_fixed_historical_final_input_formative",
        "note": "QX30 was used in development; only the base prompt differs between arms. Historical task-gate-v2 overlay is not carried into the current non-bundle route.",
        "units": all_ids,
        "model": "deepseek-v4-flash",
        "temperature": 0.1,
        "max_tokens": 16384,
        "reasoning_effort": "low",
        "runtime_package": str(args.runtime_package),
        "gate_sha256": file_sha256(args.runtime_package / "src" / "llm_abstention_gate.py"),
        "runner_sha256": file_sha256(args.runtime_package / "src" / "run_hierarchy_gated_llm_smoke.py"),
        "historical_prompt_snapshot_sha256": file_sha256(args.prompt_snapshot),
        "baseline_prompt_sha256": file_sha256(args.baseline_prompt),
        "candidate_prompt_sha256": file_sha256(args.candidate_prompt),
        "effective_prompt_sha256": {k: sha256(v.encode("utf-8")) for k, v in prompts.items()},
        "source_inputs": {
            uid: {key: value for key, value in record.items() if key != "runtime"}
            for uid, record in frozen.items()
        },
    }
    args.out.mkdir(parents=True, exist_ok=True)
    binding_file = args.out / "binding.json"
    if binding_file.exists():
        prior_binding = read_json(binding_file)
        for key in ("design", "gate_sha256", "runner_sha256", "historical_prompt_snapshot_sha256", "baseline_prompt_sha256", "candidate_prompt_sha256", "effective_prompt_sha256"):
            require(prior_binding.get(key) == binding.get(key), f"run binding drift: {key}")
        for uid in ids:
            require(prior_binding["source_inputs"].get(uid) == binding["source_inputs"][uid], f"input drift: {uid}")
    else:
        # Freeze all thirty input hashes even for a limited smoke run.
        if len(ids) != 30:
            for uid in all_ids:
                if uid in frozen:
                    continue
                revision_file = args.revision_results / f"{uid}.json"
                source = revision_file if revision_file.is_file() else args.historical_results / f"{uid}.json"
                prior = read_json(source)
                user_text = prior["final_llm_response"]["request_body"]["messages"][1]["content"]
                binding["source_inputs"][uid] = {
                    "input_sha256": sha256(user_text.encode("utf-8")),
                    "source_path": str(source),
                    "source_sha256": file_sha256(source),
                    "historical_execution_status": prior.get("assessment_status", {}).get("execution_status"),
                }
        write_once(binding_file, binding)

    key = runner.load_api_key()
    require(bool(key), "no API key loaded")

    def run_one(uid: str) -> list[dict]:
        record = frozen[uid]
        frozen_runtime = record["runtime"]
        arm_order = ("v10", "v11") if int(uid[-2:]) % 2 else ("v11", "v10")
        completed = []
        for arm in arm_order:
            target = args.out / "responses" / arm / f"{uid}.json"
            if target.exists():
                saved = read_json(target)
                require(saved.get("input_sha256") == record["input_sha256"], f"resume input mismatch {uid}/{arm}")
                require(saved.get("system_prompt_sha256") == binding["effective_prompt_sha256"][arm], f"resume prompt mismatch {uid}/{arm}")
                completed.append({"unit": uid, "arm": arm, "status": "already_recorded"})
                continue
            started = time.monotonic()
            try:
                runtime = copy.deepcopy(frozen_runtime)
                require(
                    sha256(json.dumps(runtime, ensure_ascii=False, indent=2).encode("utf-8"))
                    == record["input_sha256"],
                    f"serialization drift {uid}/{arm}",
                )
                response, gate = runner.run_final_reasoning(
                    api_key=key, prompt=prompts[arm], runtime_input=runtime,
                    max_tokens=16384,
                )
                status = result_status({"final_llm_response": response, "post_llm_gate": gate, "runtime_input": runtime})
                safe_response = {key: value for key, value in response.items() if key != "request_body"}
                result = {
                    "unit_id": uid, "arm": arm, "input_sha256": record["input_sha256"],
                    "system_prompt_sha256": binding["effective_prompt_sha256"][arm],
                    "source_path": record["source_path"],
                    "historical_execution_status": record["historical_execution_status"],
                    "elapsed_seconds": time.monotonic() - started,
                    "response": safe_response, "gate": gate, "assessment_status": status,
                }
            except Exception as exc:
                result = {
                    "unit_id": uid, "arm": arm, "input_sha256": record["input_sha256"],
                    "system_prompt_sha256": binding["effective_prompt_sha256"][arm],
                    "source_path": record["source_path"],
                    "elapsed_seconds": time.monotonic() - started,
                    "execution_error": type(exc).__name__,
                    "assessment_status": {"execution_status": "execution_failed", "verdicts": []},
                }
            write_once(target, result)
            completed.append({"unit": uid, "arm": arm, "status": result["assessment_status"]["execution_status"], "elapsed_seconds": round(result["elapsed_seconds"], 1)})
            print(json.dumps(completed[-1], ensure_ascii=False), flush=True)
        return completed

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(run_one, uid) for uid in ids]):
            future.result()

    counts = {}
    for arm in ("v10", "v11"):
        current = Counter()
        verdicts = Counter()
        raw_types = Counter()
        usage = Counter()
        for uid in all_ids:
            path = args.out / "responses" / arm / f"{uid}.json"
            if not path.is_file():
                continue
            result = read_json(path)
            current[result["assessment_status"]["execution_status"]] += 1
            verdicts.update(result["assessment_status"].get("verdicts", []))
            parsed = result.get("response", {}).get("parsed")
            if isinstance(parsed, dict):
                raw_types.update(str(finding.get("conclusion_type", "missing")) for finding in parsed.get("findings", []) if isinstance(finding, dict))
            else:
                raw_types["invalid_json"] += 1
            detail = result.get("response", {}).get("usage") or {}
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if isinstance(detail.get(key), int):
                    usage[key] += detail[key]
        counts[arm] = {"recorded": sum(current.values()), "execution_status": dict(current), "gated_verdicts": dict(verdicts), "raw_conclusion_types": dict(raw_types), "usage": dict(usage)}
    summary_file = args.out / "summary.json"
    summary_file.write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": str(summary_file), "counts": counts}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
