"""Fictional export fixtures only; no project, gold or expert data."""
import argparse
import json
from pathlib import Path
import fixtures as f
from gate import evaluate


def examples():
    records = []
    def add(case_id, ctx, raw, reason="stop", transport=True, normalize=False):
        execution = {"finish_reason": reason, "transport_ok": transport}
        records.append({"case_id": case_id, "context": ctx, "execution": execution,
                        "result": evaluate(raw, ctx, **execution, normalization=normalize)})
    for name, fixture in (("complete", f.complete), ("partial", f.partial), ("blocked", f.blocked), ("outside", f.outside)):
        add("SYN-XLSX-" + name, *fixture())
    ctx, raw = f.partial()
    raw["gaps"] = [f.gap(unknown=True)]
    raw["claim_assessments"][1]["assessment_state"] = "relation_unresolved"
    add("SYN-XLSX-scope", ctx, raw)
    ctx, raw = f.complete()
    raw["claim_assessments"] = [f.claim("C1", "not_assessed")]
    raw["completed_checks"] = []
    add("SYN-XLSX-unassessed", ctx, raw)
    ctx, raw = f.complete()
    raw["completed_checks"][0]["document_evidence_refs"] = ["MISSING"]
    add("SYN-XLSX-protocol-hold", ctx, raw)
    add("SYN-XLSX-truncated", *f.complete(), reason="length")
    add("SYN-XLSX-transport", *f.complete(), transport=False)
    add("SYN-XLSX-invalid-json", f.context(), '{"partial":')
    ctx, raw = f.complete()
    raw["completed_checks"][0]["check_name"] = raw["completed_checks"][0].pop("check")
    add("SYN-XLSX-alias-raw", ctx, raw)
    add("SYN-XLSX-alias-normalized", ctx, raw, normalize=True)
    ctx, raw = f.complete()
    raw["completed_checks"][0]["check"] = "=1+1"
    raw["claim_assessments"][0]["rationale"] = "@literal：仅验证Excel字面文本，不是法律评价。"
    add("SYN-XLSX-literal", ctx, raw)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(examples(), out, ensure_ascii=False, indent=2)
        out.write("\n")
