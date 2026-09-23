"""Four-arm raw-response replay; disable sockets and write only to new outputs."""
from pathlib import Path
from copy import deepcopy
import argparse
import json
import socket
import sys

sys.dont_write_bytecode = True
PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE / "src"))


def deny_network(*args, **kwargs):
    raise RuntimeError("Offline replay forbids network")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", nargs="+", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Use a fresh output directory")
    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    from llm_abstention_gate import apply_gate
    from experiment_integrity import digest, file_digest, write_new_json
    from scope_routing_v412 import ENGINE_VERSION
    summary = {"engine_version": ENGINE_VERSION, "wire_protocol_unchanged": True,
               "network_calls": 0, "raw_response_rewrite": False, "records": []}
    for path in args.records:
        before = file_digest(path)
        source = json.loads(path.read_text(encoding="utf-8"))
        runtime = source["runtime_input"]
        raw = source["final_llm_response"]["parsed"]
        spec = runtime["review_task_contract_v41"]["scope_spec"]
        uid = source["issue_id"]
        rows = []
        gates = {}
        for arm, a, b in (("R0", False, False), ("R1", True, False), ("R2", False, True), ("R3", True, True)):
            result = apply_gate(deepcopy(raw), deepcopy(runtime), source_role_guard=True,
                                nu_boundary=True, task_contract_v2=True, external_auto_candidates=True,
                                scope_dependency_v41=spec, normalize_protocol_v41=False,
                                material_aliases_v412=a, processing_presentation_v412=b)
            gates[arm] = result
            assert result["raw_response"] == raw
            write_new_json(args.output / uid / (arm + ".json"), result)
            findings = result.get("response", {}).get("findings", [])
            rows.append({"arm": arm, "material_aliases": a, "processing_presentation": b,
                         "valid_legal_verdicts": result["valid_legal_verdicts"],
                         "status": result["status"],
                         "processing_statuses": [f.get("nu_boundary_audit", {}).get("processing_status") for f in findings],
                         "gap_routes": [[{"gap_id": g["gap_id"], "route": g["resolution"], "reason": g["reason"]}
                                         for g in f.get("nu_boundary_audit", {}).get("gap_resolutions", [])] for f in findings],
                         "gate_sha256": digest(result)})
        r0_equal = gates["R0"] == source["post_llm_gate"]
        presentation_preserves = all(
            gates[x]["valid_legal_verdicts"] == gates[y]["valid_legal_verdicts"] and
            [f["nu_boundary_audit"] for f in gates[x]["response"]["findings"]] ==
            [f["nu_boundary_audit"] for f in gates[y]["response"]["findings"]]
            for x, y in (("R0", "R2"), ("R1", "R3")))
        row = {"unit_id": uid, "source_result_sha256": before, "source_unchanged": file_digest(path) == before,
               "historical_gate_exactly_reproduced": r0_equal,
               "presentation_did_not_change_legal_or_routing_results": presentation_preserves, "arms": rows}
        summary["records"].append(row)
    summary["passed"] = all(r["source_unchanged"] and r["historical_gate_exactly_reproduced"] and
                            r["presentation_did_not_change_legal_or_routing_results"] for r in summary["records"])
    write_new_json(args.output / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
