"""Offline-only new-protocol workbook bridge. No legacy coercion or inference."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from consumers import assert_candidate, review_rows
from gate import evaluate
from spec import VERSION, SPEC, digest, RELATION_RULES

EXPORT_VERSION = "three-layer-xlsx-v1"
BOUNDARY = "全部结果需人工二次审核。ready仅表示可交接，不等于法律正确；未计算准确率或联合交接有效率。"


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def table(name, columns, rows, widths, note):
    return {"name": name, "columns": columns, "rows": rows, "widths": widths, "note": note}


def build_packet(records):
    """Re-evaluate unchanged raw input and require EXACT saved gate-result equality.

    This validates provenance of the export, not a new legal decision. Diagnostic
    holds remain diagnostic. Invalid/missing trusted envelopes can be displayed
    only through a saved reproducible result, never repaired by this adapter.
    """
    before = deepcopy(records)
    if not isinstance(records, list) or not records:
        raise ValueError("nonempty_records_required")
    seen, reviews, checks, gaps, audits = set(), [], [], [], []
    for record in records:
        if set(record) != {"case_id", "context", "result", "execution"}:
            raise ValueError("record_envelope_fields_mismatch")
        case_id, ctx, result, execution = (record[k] for k in ("case_id", "context", "result", "execution"))
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            raise ValueError("unique_nonempty_case_id_required")
        seen.add(case_id)
        assert_candidate(result)
        if set(execution) != {"finish_reason", "transport_ok"} or type(execution["transport_ok"]) is not bool:
            raise ValueError("explicit_execution_metadata_required")
        replay = evaluate(result["raw_received"], ctx, **execution,
                          normalization=result["normalization_enabled"])
        if replay != result:
            raise ValueError("saved_result_does_not_match_current_gate_and_context:" + case_id)
        task = ctx.get("task", {}) if isinstance(ctx, dict) else {}
        required = {c["claim_id"]: c for c in task.get("required_claims", [])}
        valid = result["processing_status"] == "valid"
        candidate = result["normalized_response"] if valid else None
        claims = {c["claim_id"]: c for c in result["claim_states"]}
        for row in review_rows(case_id, result):
            claim = claims.get(row["claim_id"], {})
            reviews.append([case_id, row["claim_id"] or None,
                            required.get(row["claim_id"], {}).get("description", task.get("question")),
                            row["claim_state"], row["finding"], row["question_completion"],
                            row["handoff_status"], json_text(row["claim_gap_ids"]),
                            json_text(row["question_blocking_gap_ids"]), claim.get("rationale"),
                            json_text(claim.get("check_ids", []) + claim.get("observation_ids", [])),
                            True, None, None])
        if valid:
            evid = {e["evidence_id"]: e for e in ctx["evidence_registry"]}
            laws = {law["chunk_id"]: law for law in ctx["laws"]}
            for c in candidate["completed_checks"]:
                selected = [evid[e] for e in c["document_evidence_refs"]]
                law_rows = [laws[k] for k in c["legal_chunk_ids"]]
                checks.append([case_id, c["check_id"], c["check_kind"], json_text(c["claim_ids"]),
                               c["check"], json_text(c["document_evidence_refs"]),
                               "\n".join(e["evidence_id"] + ": " + e["quote"] for e in selected),
                               "\n".join(e["evidence_id"] + ": " + e["source_id"] + " / " + e["locator"] for e in selected),
                               "\n".join(e["evidence_id"] + ": " + e["document_sha256"] for e in selected),
                               "\n".join(l["chunk_id"] + ": " + l["text"] for l in law_rows) or None,
                               "\n".join(l["chunk_id"] + ": " + l["locator"] + " / " + l["source_sha256"] for l in law_rows) or None,
                               c["comparison"]])
            for g in candidate["gaps"]:
                gaps.append([case_id, g["gap_id"], g["kind"], g["dependency_key"], g["task_relation"],
                             RELATION_RULES[g["task_relation"]]["group"], json_text(g["affected_claim_ids"]),
                             g["detail"], g["reason"], g["counterfactual_impact"],
                             g["dependency_trigger"], json_text(g["trigger_refs"]), g["next_step"]])
        audits.append([case_id, result["processing_status"], result["raw_structure_valid"],
                       result["normalized_structure_valid"], result["normalization_enabled"],
                       json_text(result["normalization_actions"]), result["claim_ledger_complete"],
                       json_text(result["technical_errors"] + result["errors"]),
                       json_text(result["declared_blocking_gap_ids_unvalidated"]),
                       execution["finish_reason"], execution["transport_ok"],
                       result["raw_response_sha256"], result["spec_sha256"],
                       ctx.get("task_scope_sha256") if isinstance(ctx, dict) else None,
                       ctx.get("input_sha256") if isinstance(ctx, dict) else None,
                       False, None])
    if before != records:
        raise AssertionError("input_mutation")
    sheets = [
        table("三层复核", ["单元ID", "子结论ID", "锁定子问题", "子结论状态", "发现判断", "整体完成度", "人工交接状态",
                           "本子结论缺口ID", "整体阻断缺口ID", "结论理由", "检查及观察ID", "需人工二次审核", "人工复核结论", "人工复核意见"],
              reviews, [22, 14, 34, 36, 32, 21, 36, 22, 23, 48, 23, 20, 28, 48],
              "空白判断表示未评/不可计算，不是N或0。人工填写最后两列不会修改模型原始状态。"),
        table("检查与证据", ["单元ID", "检查ID", "检查类型", "子结论ID", "检查事项", "文件证据ID", "合同/文件原文", "原文定位",
                            "原文件hash", "法规条文", "法条定位及hash", "原文与规则比较说明"],
              checks, [22, 14, 26, 18, 28, 23, 52, 32, 40, 52, 40, 58],
              "仅展开通过协议检查的引用。法源准入/效力依赖可信上游元数据；text_observation不构成法律判断。"),
        table("缺口任务", ["单元ID", "缺口ID", "材料状态", "依赖类型", "任务关系", "输出分组", "受影响子结论", "缺失材料",
                           "为何需要", "对任务的影响", "触发类型", "触发引用", "人工补查建议"],
              gaps, [22, 14, 34, 34, 28, 27, 21, 36, 42, 44, 33, 42, 44],
              "blocking_gap仍阻断相应子问题；out_of_scope_item不等于不存在风险；scope_review_item先厘清关系。"),
        table("处理审计", ["单元ID", "处理状态", "原始结构合格", "规范化后结构合格", "启用机械规范化", "机械规范化动作", "台账项齐全",
                           "处理错误详情", "未验证的自报阻断ID", "finish_reason", "传输成功", "原响应hash", "协议hash", "任务hash", "输入hash",
                           "语义正确性已验证", "联合交接有效性"],
              audits, [22, 25, 18, 23, 23, 48, 17, 58, 27, 20, 16, 42, 42, 42, 42, 23, 23],
              "协议/技术失败只作诊断，不展开为已验证法律结论。联合交接有效性留空。原响应保留于records.json。"),
    ]
    for sheet in sheets:
        for row in sheet["rows"]:
            if len(row) != len(sheet["columns"]):
                raise ValueError("ragged_export_row")
            for cell in row:
                if isinstance(cell, str) and (len(cell.encode("utf-16-le")) // 2 > 32767 or
                                               any(ord(c) < 32 and c not in "\t\n\r" for c in cell)):
                    raise ValueError("excel_text_limit_or_invalid_control; do_not_silently_truncate")
    return {"export_version": EXPORT_VERSION, "protocol_version": VERSION, "spec_sha256": digest(SPEC),
            "source_records_sha256": digest(records), "record_count": len(records), "boundary": BOUNDARY,
            "legal_accuracy": None, "expert_agreement": None, "joint_handoff_effectiveness": None,
            "sheets": sheets}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--node", required=True, type=Path)
    p.add_argument("--runtime", required=True, type=Path, help="directory with bundled node_modules junction")
    args = p.parse_args()
    data = args.input.read_bytes()
    records = json.loads(data.decode("utf-8-sig"))
    packet = build_packet(records)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "records.json").write_bytes(data)  # preserve original bytes, no semantic rewrite
    (out / "workbook_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = subprocess.run([str(args.node.resolve()), str(Path(__file__).with_name("export_review.mjs")),
                             str(out / "workbook_packet.json"), str(out), str(args.runtime.resolve())],
                            cwd=out, capture_output=True, text=True, encoding="utf-8", timeout=300)
    (out / "export_stdout.log").write_text(result.stdout, encoding="utf-8")
    (out / "export_stderr.log").write_text(result.stderr, encoding="utf-8")
    if result.returncode:
        print("Workbook export failed. Original inputs retained; see export_stderr.log.", file=sys.stderr)
        return result.returncode
    paths = [out / n for n in ("records.json", "workbook_packet.json", "三层协议_离线复核.xlsx", "xlsx_checks.json")]
    manifest = {"export_version": EXPORT_VERSION, "protocol_version": VERSION,
                "new_llm_calls": 0, "historical_outputs_modified": False, "production_enabled": False,
                "files": {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in paths}}
    (out / "export_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "exported_and_readback_verified", "records": len(records),
                      "output": str(paths[2])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
