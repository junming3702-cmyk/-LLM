"""Fixed-evidence intervention runner. Default preflight; online requires consent.

This is not a new retriever, a source of legal labels, or an expert-study runner.
Runtime packets and evaluator labels are separate files. No synthetic benchmark
or expert workbook is automatically opened. Prepared variants require human QA.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
from pathlib import Path
import uuid
from experiment_integrity import (
    RunJournal, code_inventory, digest, file_digest, result_status,
    validate_runtime, write_new_json,
)

ROW_KEYS = {"observation_id", "mother_case_id", "variant_id", "method_id",
            "repeat_id", "project_id", "runtime_input"}


def load_packets(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("empty packet file")
    identifiers = set()
    for row in rows:
        if set(row) != ROW_KEYS:
            raise ValueError("runtime packet envelope must use only declared fields")
        validate_runtime(row)
        if row["observation_id"] in identifiers:
            raise ValueError("duplicate observation_id")
        identifiers.add(row["observation_id"])
        runtime = row["runtime_input"]
        required = {"project_id", "issue_id", "contract_evidence", "project_context", "retrieved_legal_evidence"}
        if not isinstance(runtime, dict) or not required.issubset(runtime):
            raise ValueError("incomplete runtime packet")
        if runtime["project_id"] != row["project_id"]:
            raise ValueError("project identity mismatch")
        for record in runtime["retrieved_legal_evidence"]:
            if not isinstance(record, dict) or not record.get("chunk_id"):
                raise ValueError("invalid evidence item")
    return rows


def preflight(rows, approval, packet_hash):
    approved = (approval.get("status") == "human_verified"
                and approval.get("runtime_packets_sha256") == packet_hash
                and bool(approval.get("reviewed_by"))
                and bool(approval.get("reviewed_at")))
    evidence_by_mother = {}
    for row in rows:
        key = (row["mother_case_id"], row["method_id"], row["repeat_id"])
        evidence_hash = digest(row["runtime_input"]["retrieved_legal_evidence"])
        if key in evidence_by_mother and evidence_by_mother[key] != evidence_hash:
            raise ValueError("fixed-evidence intervention changed its evidence package")
        evidence_by_mother[key] = evidence_hash
    policy = approval.get("external_policy")
    external = policy in {"disabled", "frozen_evidence_only"}
    if policy == "disabled":
        for row in rows:
            runtime = row["runtime_input"]
            evidence = runtime.get("retrieved_legal_evidence", [])
            if runtime.get("external_sources_used") or any(
                isinstance(item, dict) and (item.get("external_source") is True
                                            or item.get("provenance_origin") == "external")
                for item in evidence
            ):
                raise ValueError("disabled external policy conflicts with supplied external evidence")
    return {"packet_count": len(rows), "mother_cases": len({r["mother_case_id"] for r in rows}),
            "runtime_packets_sha256": packet_hash,
            "human_variant_verification": "verified" if approved else "pending",
            "external_policy_valid": external, "ready_for_online": approved and external,
            "reference_labels_loaded": False, "expert_scores_loaded": False,
            "model_calls": 0, "mode": "preflight_only"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packets", required=True, type=Path)
    parser.add_argument("--approval-manifest", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--max-tokens", type=int, default=16384)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--transport-max-attempts", type=int, choices=(1, 2), default=1)
    parser.add_argument("--online-authorized-deepseek", action="store_true",
                        help="Use only after explicit authorization for this packet content.")
    args = parser.parse_args()
    rows = load_packets(args.packets)
    approval = json.loads(args.approval_manifest.read_text(encoding="utf-8"))
    audit = preflight(rows, approval, file_digest(args.packets))
    audit["corpus_sha256"] = file_digest(args.corpus)
    if not args.online_authorized_deepseek:
        print(json.dumps(audit, ensure_ascii=False, indent=2))
        return 0
    if not audit["ready_for_online"]:
        parser.error("human-approved packet freeze and external policy required")
    # Delayed import: preflight works without ML dependencies or credentials.
    from run_hierarchy_gated_llm_smoke import (
        run_final_reasoning, load_api_key, PROMPT_FILE, PACKAGE_ROOT,
        MODEL_NAME, FINAL_COMPACT_OUTPUT_CONTRACT,
    )
    prompt = PROMPT_FILE.read_text(encoding="utf-8") + FINAL_COMPACT_OUTPUT_CONTRACT
    binding = {"run_id": args.run_id, "method_version": "fixed-evidence-intervention-v1",
               "model": MODEL_NAME, "max_tokens": args.max_tokens,
               "prompt_hash": digest(prompt), "corpus_hash": audit["corpus_sha256"],
               "code_inventory": code_inventory(PACKAGE_ROOT),
               "packet_hash": audit["runtime_packets_sha256"],
               "external_policy": approval["external_policy"], "history": []}
    journal = RunJournal(args.output / "audit", binding, resume=args.resume,
                         max_attempts=args.transport_max_attempts)
    api_key = load_api_key()
    invocation = uuid.uuid4().hex
    summary = []
    for row in rows:
        runtime = deepcopy(row["runtime_input"])
        with journal.case(row["observation_id"]):
            try:
                response, gate = run_final_reasoning(api_key=api_key, prompt=prompt,
                                                     runtime_input=runtime, max_tokens=args.max_tokens)
                result = {"runtime_input": runtime, "final_llm_response": response,
                          "post_llm_gate": gate}
            except Exception as exc:
                result = {"runtime_input": runtime, "execution_error": type(exc).__name__}
            result["assessment_status"] = result_status(result)
            result["identity"] = {k: v for k, v in row.items() if k != "runtime_input"}
            result["experiment_binding"] = binding
            journal.event("case_finished", result["assessment_status"])
        path = args.output / "results" / f"{digest(row['observation_id'])[:20]}-{invocation}.json"
        write_new_json(path, result)
        summary.append({"observation_id": row["observation_id"], "path": str(path),
                        "execution_status": result["assessment_status"]["execution_status"]})
        print(row["observation_id"], summary[-1]["execution_status"], flush=True)
    write_new_json(args.output / f"manifest-{invocation}.json", {"binding": binding, "results": summary})
    return 0 if all(r["execution_status"] == "completed" for r in summary) else 2


if __name__ == "__main__":
    raise SystemExit(main())
