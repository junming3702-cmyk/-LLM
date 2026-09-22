"""Network-free paired gate replay; reads no reference labels or API secrets.

Freeze input-bound contracts before reading responses. Output is private and
exclusive-create. Candidate prompt is NOT applied retroactively to generations.
"""
from argparse import ArgumentParser
from collections import Counter
from copy import deepcopy
from pathlib import Path
import json
import socket
from experiment_integrity import file_digest, write_new_json, validate_runtime, utc_now, semantic_verdict
from review_task_contract_v2 import build_contract, digest, VERSION
from llm_abstention_gate import apply_gate
from task_gate_v2_prompt import candidate_prompt


def offline_only(*args, **kwargs):
    raise RuntimeError("Network is disabled in offline gate replay")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def label(gate):
    findings = (gate.get("response") or {}).get("findings") or []
    if gate.get("blocked") or len(findings) != 1:
        return "FAIL"
    return semantic_verdict(findings[0].get("conclusion_type")) or "FAIL"


def replay(inputs, results, output, *, external_auto_candidates=False):
    if output.exists():
        raise FileExistsError("Choose a new run directory; never overwrite a replay")
    inputs, results = inputs.resolve(), results.resolve()
    output = output.resolve()
    if output == inputs or inputs in output.parents or output == results or results in output.parents:
        raise ValueError("Output must be outside frozen input/result directories")
    input_paths = sorted(inputs.glob("*.json"))
    if not input_paths:
        raise ValueError("No frozen runtime inputs")
    runtimes = {p.stem: read(p) for p in input_paths}
    for runtime in runtimes.values():
        validate_runtime(runtime)
    contracts = {uid: build_contract(rt) for uid, rt in runtimes.items()}
    source_paths = input_paths + [results / (uid + ".json") for uid in runtimes]
    hashes = {str(p): file_digest(p) for p in source_paths}
    code_root = Path(__file__).parent
    code_hashes = {str(p.relative_to(code_root.parent)): file_digest(p) for p in sorted(code_root.glob("*.py"))}
    manifest = {"version": VERSION, "created_at": utc_now(), "source_hashes": hashes,
        "code_hashes": code_hashes, "contracts": contracts, "network_calls": 0,
        "reference_labels_loaded": False, "prompt_effect_tested": False,
        "contract_used_at_original_generation": False, "external_auto_candidates": external_auto_candidates,
        "design": "same frozen provider responses; post-hoc paired deterministic gates",
        "human_scope_approval": False, "candidate_prompt_sha256": digest(candidate_prompt())}
    write_new_json(output / "manifest.private.json", manifest)
    (output / "candidate_prompt.md").write_text(candidate_prompt(), encoding="utf-8")
    rows, export_records = [], []
    flags = {"external_auto_candidates": external_auto_candidates, "nu_boundary": True}
    for uid, rt in runtimes.items():
        result = read(results / (uid + ".json"))
        if result.get("runtime_input") != rt:
            raise ValueError("Frozen runtime/result mismatch: " + uid)
        provider = result.get("final_llm_response") or {}
        raw = provider.get("parsed")
        runtime = deepcopy(rt)
        runtime["review_task_contract_v2"] = contracts[uid]
        failed = (result.get("execution_error") or provider.get("ok") is False or
                  provider.get("finish_reason") == "length" or not isinstance(raw, dict) or
                  (rt.get("hierarchy_retrieval_audit") or {}).get("cascade_failure_level") not in (None, "", "none"))
        if failed:
            old = result.get("post_llm_gate") or {}
            new = {"blocked": True, "status": "technical_failure", "response": {"findings": []}}
            old_label = new_label = "FAIL"
        else:
            old = apply_gate(deepcopy(raw), deepcopy(rt), **flags)
            new = apply_gate(deepcopy(raw), runtime, task_contract_v2=True, **flags)
            old_label, new_label = label(old), label(new)
            # A different comparator would invalidate a claimed gate-only effect.
            stored = result.get("gated_observation") or {}
            stored_label = stored.get("verdict") if stored.get("status") == "completed" else "FAIL"
            if old_label != stored_label:
                raise ValueError(f"Baseline replay drift: {uid}: {old_label} != {stored_label}")
        record = {"issue_id": uid, "runtime_input": runtime, "stage3_gate_result": new,
                  "baseline_gate_result": old, "raw_response_sha256": digest(raw),
                  "original_result_sha256": hashes[str(results / (uid + ".json"))],
                  "original_execution_failed": bool(failed), "provider_response_reused": True}
        write_new_json(output / "results" / (uid + ".json"), record)
        finding = ((new.get("response") or {}).get("findings") or [{}])[0]
        semantic = semantic_verdict(finding.get("conclusion_type")) if finding else "FAIL"
        rows.append({"issue_id": uid, "baseline": old_label, "candidate": new_label,
                     "candidate_semantic_diagnostic_only": semantic,
                     "processing_status": (finding.get("review_handoff") or {}).get("processing_status", "technical_failure"),
                     "scope": contracts[uid]["scope"], "scope_needs_confirmation": contracts[uid]["ambiguity_requires_review"],
                     "changed": old_label != new_label})
        export_records.append(record)
    preserved = all(file_digest(Path(p)) == h for p, h in hashes.items())
    if not preserved:
        raise ValueError("Frozen source changed during replay")
    summary = {"n": len(rows), "source_hashes_preserved": preserved,
        "baseline": dict(Counter(r["baseline"] for r in rows)), "candidate": dict(Counter(r["candidate"] for r in rows)),
        "changed": sum(r["changed"] for r in rows), "scope_counts": dict(Counter(r["scope"] for r in rows)),
        "prompt_effect_tested": False, "network_calls": 0, "rows": rows}
    write_new_json(output / "replay_summary.private.json", summary)
    write_new_json(output / "review_records.private.json", export_records)
    return summary


def main():
    parser = ArgumentParser(description=__doc__)
    for name in ("inputs", "results", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--external-auto-candidates", action="store_true")
    args = parser.parse_args()
    socket.create_connection = offline_only
    socket.socket.connect = offline_only
    result = replay(args.inputs, args.results, args.output, external_auto_candidates=args.external_auto_candidates)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
