"""Offline fixture execution and audit recording; external transports disabled."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import socket
import time
import unittest
from unittest.mock import patch
from spec import VERSION, SPEC, digest
import test_three_layer_protocol as tests
import test_export_packet as export_tests
from consumers import summary, markdown, excel_projection

def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    tests.OBSERVATIONS.clear()
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    network_attempts = []
    def deny(*args, **kwargs):
        network_attempts.append("blocked_network_attempt")
        raise RuntimeError("network disabled for offline test")
    log = io.StringIO()
    with patch.object(socket, "create_connection", deny), patch.object(socket.socket, "connect", deny), \
         patch.object(socket.socket, "connect_ex", deny), patch.object(socket, "getaddrinfo", deny):
        suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(export_tests))
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    observations = tests.OBSERVATIONS
    records = [o["result"] for o in observations]
    code_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.iterdir()
                   if p.suffix in (".py", ".mjs", ".ps1")}
    unexpected_complete = sum(o["expected_completion"] != "complete" and o["result"]["question_completion"] == "complete" for o in observations)
    report = {
        "version": VERSION, "status": "passed" if result.wasSuccessful() and not network_attempts else "failed",
        "started_utc": started, "duration_seconds": round(time.perf_counter() - t0, 6),
        "planned_guard_groups": 28, "unit_tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "recorded_scenarios": len(observations), "network_attempts": len(network_attempts),
        "new_llm_calls": 0, "new_external_retrieval_calls": 0,
        "unexpected_complete_releases": unexpected_complete,
        "spec_sha256": digest(SPEC), "source_sha256": code_hashes,
        "software_fixture_metrics": summary(records),
        "production_enabled": False, "historical_results_recalculated": False,
        "semantic_correctness_verified": False,
        "consumer_boundary": "JSON/Markdown/provenance-checked Excel packet and legacy rejection; actual XLSX export/readback recorded in a separate export run; no production integration",
        "verification_scope": "deterministic fixture checks only, not legal accuracy or human handoff effectiveness",
    }
    save_json(out / "results.json", observations)
    save_json(out / "summary.json", report)
    (out / "tests.log").write_text(log.getvalue(), encoding="utf-8")
    examples = [o for o in observations if o["case_id"] in ("G02", "G06", "G08", "G11", "G15", "G16", "G20-length", "G25")]
    (out / "review_examples.md").write_text("\n\n".join("## " + o["case_id"] + "\n\n" + markdown(o["case_id"], o["result"]) for o in examples), encoding="utf-8")
    save_json(out / "excel_column_projection.json", {o["case_id"]: excel_projection(o["case_id"], o["result"]) for o in examples})
    text = [
        "# 三层协议候选：零API验证记录", "", "## Material Passport", "",
        "- Origin Skill / Mode: academic-research-suite / experiment-agent / run",
        "- Verification Status: " + ("VERIFIED（仅本轮确定性软件测试）" if report["status"] == "passed" else "UNVERIFIED"),
        "- Version: " + VERSION, "- Date: " + started, "",
        "## 结果", "",
        "- 预定守护组：28；实际测试方法数：" + str(result.testsRun) + "。",
        "- 记录的合成场景执行数：" + str(len(observations)) + "；不是独立真实案例数。",
        "- 失败：" + str(len(result.failures)) + "；错误：" + str(len(result.errors)) + "。",
        "- 不符合预期却被完整放行：" + str(unexpected_complete) + "。",
        "- 新LLM/外检调用：0；网络尝试：" + str(len(network_attempts)) + "。",
        "- 原响应及上下文不可变断言随每次场景检查；规范化后状态另列。", "",
        "## 完成边界", "",
        "本轮实现独立候选，不接现行线上runner，不改参照，不改U14开关，不回填旧响应，不改历史指标。",
        "JSON、Markdown与Excel的类型化列投影使用同一结果对象；旧标签/旧工作簿出口明确拒绝新协议。",
        "本软件测试不生成XLSX。新协议导出器的实际文件导出、回读及排版检查另记export_manifest.json与xlsx_checks.json；生产集成仍未启用。",
        "引用存在和字段关系通过不证明语义充分；任意自然语言混合事项、法律适用和遗漏风险仍须人工审查。",
        "不报告新的法律准确率、专家一致率、Recall@5、MRR或联合交接有效率。ready只是呈现条件满足。",
        "", "## 证据", "", "summary.json、results.json、tests.log、review_examples.md、excel_column_projection.json。",
    ]
    (out / "offline_report.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "unit_tests_run", "failures", "errors", "recorded_scenarios", "network_attempts", "unexpected_complete_releases")}, ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "passed" else 1)

if __name__ == "__main__":
    main()
