"""Synthetic protocol/relationship guards, NOT new independent performance data."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest

from test_scope_dependency_v4 import fixture as v4_fixture
from test_nu_boundary_policy import N, U
from llm_abstention_gate import apply_gate
from scope_dependency_v41 import build_contract
from scope_dependency_v41_schema import SCHEMA, DEPENDENCIES, validate_basis, normalize_response, render_schema
from scope_dependency_v41_prompt import build_addendum, examples, build_prompt


def fixture(mode="text_response_comparison"):
    rt, f, spec = v4_fixture(mode)
    rt.pop("review_task_contract_v4")
    rt["review_task_contract_v41"] = build_contract(rt, spec)
    f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v41"]["input_scope_sha256"]
    return rt, f, spec


def add_gap(f, dep="submission_package_completeness", relation="outside_locked_scope", **kwargs):
    detail = {"submission_package_completeness": "最终递交包完整性未核验。",
              "authenticity": "真实性尚未核验。", "actual_performance": "后续履行未核验。",
              "current_clause_context": "当前条款上下文未提供。",
              "comparison_operand": "当前核算所需比较数值未提供。",
              "applicable_rule": "当前判断所需具体法条缺失。",
              "regulatory_applicability": "当前使用规则的适用前提缺失。",
              "readability": "关键证据不可读。", "other_undetermined": "尚无法识别此材料类型。"}[dep]
    g = {"gap_id": "G" + str(len(f["decision_basis"]["gaps"]) + 1),
         "kind": DEPENDENCIES[dep][0], "dependency_key": dep, "detail": detail,
         "task_relation": relation, "affected_claim_ids": ["C1"] if relation == "decisive_for_claim" else [],
         "blocks_current_question": relation == "decisive_for_claim",
         "reason": "当前子结论明确需要此依赖。" if relation == "decisive_for_claim" else "锁定问题明确排除此核验。",
         "counterfactual_impact": "缺少此值无法完成当前指定比较。" if relation == "decisive_for_claim" else "该核查不改变当前提供文字的比对。",
         "dependency_trigger": "locked_requirement" if relation == "decisive_for_claim" else "explicit_scope_exclusion",
         "trigger_evidence": []}
    g.update(kwargs)
    f["decision_basis"]["gaps"].append(g)
    if relation == "decisive_for_claim":
        f["decision_basis"]["answerability"] = "decisive_gap"
        f["conclusion_type"] = U
    if relation == "undetermined":
        f["decision_basis"]["answerability"] = "scope_unresolved"
    return g


def run(rt, f, spec, **kwargs):
    return apply_gate({"findings": [f]}, rt, scope_dependency_v41=spec, **kwargs)


def finding(result):
    return result["response"]["findings"][0]


class ProtocolAlignmentTests(unittest.TestCase):
    def test_generated_mirrors_and_examples(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual((root / "schemas/scope_dependency_v41.schema.json").read_text(encoding="utf-8"), render_schema() + "\n")
        self.assertEqual((root / "prompts/scope_dependency_v41_candidate.md").read_text(encoding="utf-8").strip(), build_addendum().strip())
        for name, basis in examples().items():
            self.assertEqual(validate_basis(basis), [], name)

    def test_all_check_fields_required_except_fragments(self):
        for key, rule in SCHEMA["check"].items():
            if not rule["required"]:
                continue
            with self.subTest(key=key):
                rt, f, s = fixture()
                f["decision_basis"]["completed_checks"][0].pop(key)
                result = run(rt, f, s, normalize_protocol_v41=True)
                self.assertTrue(result["blocked"])
                self.assertFalse(result["protocol_diagnostics"]["normalized"]["valid"])

    def test_all_gap_fields_required(self):
        for key in SCHEMA["gap"]:
            with self.subTest(key=key):
                rt, f, s = fixture(); g = add_gap(f); g.pop(key)
                self.assertTrue(run(rt, f, s)["blocked"])

    def test_pairs_single_source_and_wrong_pairs_rejected(self):
        for dep, kinds in DEPENDENCIES.items():
            rt, f, s = fixture(); g = add_gap(f, dep)
            for kind in kinds:
                g["kind"] = kind
                self.assertEqual(validate_basis(f["decision_basis"]), [])
            g["kind"] = "other_outside_question"
            self.assertTrue(validate_basis(f["decision_basis"]))

    def test_unknown_fields_not_silently_deleted(self):
        rt, f, s = fixture(); g = add_gap(f); g["output_group"] = "out_of_scope_item"
        r = run(rt, f, s, normalize_protocol_v41=True)
        self.assertTrue(r["blocked"])
        self.assertEqual(r["raw_response"]["findings"][0]["decision_basis"]["gaps"], f["decision_basis"]["gaps"])

    def test_missing_check_not_generated_from_comparison(self):
        rt, f, s = fixture(); f["decision_basis"]["completed_checks"][0].pop("check")
        r = run(rt, f, s, normalize_protocol_v41=True)
        self.assertTrue(r["blocked"])
        self.assertEqual(r["protocol_diagnostics"]["actions"], [])

    def test_alias_opt_in_raw_failure_normalized_pass_separate(self):
        rt, f, s = fixture(); c = f["decision_basis"]["completed_checks"][0]
        c["check_name"] = c.pop("check")
        before = deepcopy(f)
        self.assertTrue(run(rt, f, s)["blocked"])
        r = run(rt, f, s, normalize_protocol_v41=True)
        self.assertFalse(r["blocked"])
        self.assertFalse(r["protocol_diagnostics"]["raw"]["valid"])
        self.assertTrue(r["protocol_diagnostics"]["normalized"]["valid"])
        self.assertEqual(f, before)
        self.assertEqual(r["raw_response"]["findings"][0], before)

    def test_alias_collision_is_not_resolved_by_guessing(self):
        rt, f, s = fixture(); f["decision_basis"]["completed_checks"][0]["check_name"] = "different"
        self.assertTrue(run(rt, f, s, normalize_protocol_v41=True)["blocked"])

    def test_cosmetic_enum_normalization_only(self):
        rt, f, s = fixture(); c = f["decision_basis"]["completed_checks"][0]
        c["check_kind"] = " LEGAL_COMPARISON "
        raw = {"findings": [f]}; before = deepcopy(raw)
        normalized, audit = normalize_response(raw, True)
        self.assertEqual(raw, before)
        self.assertEqual(normalized["findings"][0]["decision_basis"]["completed_checks"][0]["check_kind"], "legal_comparison")
        self.assertEqual(c["document_quote"], normalized["findings"][0]["decision_basis"]["completed_checks"][0]["document_quote"])
        self.assertFalse(audit["raw"]["valid"]); self.assertTrue(audit["normalized"]["valid"])

    def test_normalizer_cannot_reclassify_dependency(self):
        rt, f, s = fixture(); g = add_gap(f); g["kind"] = "other_outside_question"
        r = run(rt, f, s, normalize_protocol_v41=True)
        self.assertTrue(r["blocked"]); self.assertEqual(r["protocol_diagnostics"]["actions"], [])

    def test_normalizer_cannot_repair_quote_or_locator(self):
        for key, value in (("document_quote", "不存在的伪造引文"), ("document_locator", "p999")):
            rt, f, s = fixture(); f["decision_basis"]["completed_checks"][0][key] = value
            r = run(rt, f, s, normalize_protocol_v41=True)
            self.assertTrue(r["blocked"])
            self.assertEqual(finding(r)["nu_boundary_audit"]["processing_status"], "evidence_binding_blocked")

    def test_malformed_types_fail_closed_without_crash(self):
        for key, val in (("gaps", None), ("completed_checks", "not-list"), ("review_target", {}),
                         ("answerability", []), ("bounded_conclusion", 42)):
            rt, f, s = fixture(); f["decision_basis"][key] = val
            self.assertTrue(run(rt, f, s)["blocked"])
        for key in SCHEMA["gap"]:
            rt, f, s = fixture(); g = add_gap(f); g[key] = {}
            self.assertTrue(run(rt, f, s)["blocked"])

    def test_duplicate_identifiers_block(self):
        for what in ("check", "gap"):
            rt, f, s = fixture()
            if what == "check":
                f["decision_basis"]["completed_checks"] *= 2
            else:
                g = add_gap(f); f["decision_basis"]["gaps"].append(deepcopy(g))
            self.assertTrue(run(rt, f, s)["blocked"])

    def test_cannot_enable_normalization_without_candidate(self):
        rt, f, s = fixture()
        with self.assertRaises(ValueError):
            apply_gate({"findings": [f]}, rt, normalize_protocol_v41=True)

    def test_empty_and_unparsed_outputs_keep_raw_diagnostics(self):
        rt, _, s = fixture()
        for raw in ("not JSON", {}, {"findings": []}):
            r = apply_gate(raw, rt, scope_dependency_v41=s, normalize_protocol_v41=True)
            self.assertTrue(r["blocked"])
            self.assertEqual(r["raw_response"], raw)
            self.assertFalse(r["protocol_diagnostics"]["raw"]["valid"])
            self.assertFalse(r["valid_legal_verdicts"])

    def test_batch_metrics_keep_parse_failure_in_response_denominator(self):
        from scope_dependency_v41_metrics import summarize_protocol_batch
        rt, f, s = fixture()
        clean = run(rt, f, s)
        c = f["decision_basis"]["completed_checks"][0]; c["check_name"] = c.pop("check")
        repaired = run(rt, f, s, normalize_protocol_v41=True)
        failed = apply_gate("not JSON", rt, scope_dependency_v41=s)
        summary = summarize_protocol_batch([clean, repaired, failed])
        self.assertEqual(summary["responses_total_including_parse_failures"], 3)
        self.assertEqual(summary["raw_protocol_conformant_responses"], 1)
        self.assertEqual(summary["normalized_protocol_conformant_responses"], 2)
        self.assertEqual(summary["observed_findings_denominator"], 2)
        self.assertEqual(summary["normalizer_changed_responses"], 1)


class RelationshipGuards(unittest.TestCase):
    def test_explicit_outside_keeps_bounded_N(self):
        rt, f, s = fixture(); add_gap(f); r = run(rt, f, s)
        self.assertFalse(r["blocked"])
        self.assertEqual(r["valid_legal_verdicts"], [N])
        self.assertEqual(len(finding(r)["review_handoff"]["out_of_scope_items"]), 1)

    def test_each_declared_decisive_dependency_remains_U(self):
        for dep in ("applicable_rule", "current_clause_context", "regulatory_applicability", "comparison_operand", "readability"):
            rt, f, s = fixture(); add_gap(f, dep, "decisive_for_claim")
            r = run(rt, f, s); self.assertFalse(r["blocked"], dep)
            self.assertEqual(r["valid_legal_verdicts"], [U], dep)

    def test_unknown_relation_is_not_legal_U(self):
        rt, f, s = fixture(); add_gap(f, "other_undetermined", "undetermined")
        r = run(rt, f, s)
        self.assertEqual(r["status"], "scope_review_required")
        self.assertEqual(r["valid_legal_verdicts"], [])
        self.assertIsNone(finding(r)["review_handoff"]["decision_status"])
        self.assertEqual(r["response"]["review_table"][0]["conclusion"]["conclusion_type"], "scope_review_required")

    def test_core_false_empty_claim_not_enough_to_release(self):
        rt, f, s = fixture(); add_gap(f, "current_clause_context")
        r = run(rt, f, s)
        self.assertTrue(r["scope_review_required"])
        self.assertFalse(r["valid_legal_verdicts"])

    def test_mixed_gap_preserved_not_split_automatically(self):
        for detail in ("最终递交包完整性与补遗未核验。", "真实性及后续履行均未知。", "最终递交包缺项目金额。"):
            rt, f, s = fixture(); add_gap(f, detail=detail); r = run(rt, f, s)
            self.assertTrue(r["scope_review_required"])
            self.assertEqual(len(r["raw_response"]["findings"][0]["decision_basis"]["gaps"]), 1)

    def test_package_and_context_separate_results(self):
        rt, f, s = fixture(); add_gap(f); add_gap(f, "current_clause_context", "decisive_for_claim")
        r = run(rt, f, s); h = finding(r)["review_handoff"]
        self.assertEqual(len(h["out_of_scope_items"]), 1)
        self.assertEqual(len(h["blocking_gaps"]), 1)
        self.assertEqual(r["valid_legal_verdicts"], [U])

    def test_generic_amendment_possibility_is_scope_review_not_U(self):
        rt, f, s = fixture(); add_gap(f, "current_clause_context", "decisive_for_claim",
                                    dependency_trigger="generic_unverified_possibility")
        r = run(rt, f, s)
        self.assertTrue(r["scope_review_required"]); self.assertEqual(r["valid_legal_verdicts"], [])

    def test_concrete_context_trigger_needs_pointer(self):
        rt, f, s = fixture(); add_gap(f, "current_clause_context", "decisive_for_claim",
                                    dependency_trigger="observed_context_conflict")
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_concrete_context_trigger_exact_pointer(self):
        rt, f, s = fixture(); c = f["decision_basis"]["completed_checks"][0]
        add_gap(f, "current_clause_context", "decisive_for_claim",
                dependency_trigger="observed_context_conflict",
                trigger_evidence=[{k: c[k] for k in ("document_quote", "document_locator")}])
        self.assertEqual(run(rt, f, s)["valid_legal_verdicts"], [U])

    def test_fabricated_trigger_not_accepted(self):
        rt, f, s = fixture(); add_gap(f, "current_clause_context", "decisive_for_claim",
                                    dependency_trigger="observed_context_conflict",
                                    trigger_evidence=[{"document_quote": "不存在的触发原文", "document_locator": "p999"}])
        r = run(rt, f, s)
        self.assertEqual(finding(r)["nu_boundary_audit"]["processing_status"], "evidence_binding_blocked")
        self.assertFalse(r["valid_legal_verdicts"])

    def test_actual_submission_not_silently_narrowed(self):
        rt, f, s = fixture("actual_submission_check")
        add_gap(f, relation="decisive_for_claim")
        self.assertEqual(run(rt, f, s)["valid_legal_verdicts"], [U])
        f["decision_basis"]["gaps"][0].update(task_relation="outside_locked_scope", blocks_current_question=False, affected_claim_ids=[])
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_undeclared_dependency_goes_to_scope_review(self):
        rt, f, s = fixture(); s["required_claims"][0]["required_dependencies"].remove("comparison_operand")
        rt["review_task_contract_v41"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v41"]["input_scope_sha256"]
        add_gap(f, "comparison_operand", "decisive_for_claim")
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_false_cannot_override_decisive_relation(self):
        rt, f, s = fixture(); add_gap(f, "comparison_operand", "decisive_for_claim", blocks_current_question=False)
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_answerability_conflict_not_silent_U(self):
        rt, f, s = fixture(); add_gap(f, "comparison_operand", "decisive_for_claim")
        f["decision_basis"]["answerability"] = "sufficient"
        self.assertTrue(run(rt, f, s)["scope_review_required"])

    def test_observation_only_cannot_generate_legal_N(self):
        rt, f, s = fixture(); c = f["decision_basis"]["completed_checks"][0]
        c.update(check_kind="text_observation", claim_ids=[], legal_chunk_ids=[])
        r = run(rt, f, s)
        self.assertNotEqual(finding(r)["conclusion_type"], N)
        self.assertEqual(len(finding(r)["review_handoff"]["text_observations"]), 1)

    def test_no_law_and_supplement_cannot_release(self):
        for variant in ("empty", "supplement", "unknown"):
            rt, f, s = fixture(); add_gap(f)
            if variant == "empty": rt["retrieved_legal_evidence"] = []
            if variant == "supplement": rt["retrieved_legal_evidence"][0].update(independent_legal_evidence=False, legal_evidence_eligibility="supplement_only", source_role="supplement")
            if variant == "unknown": f["decision_basis"]["completed_checks"][0]["legal_chunk_ids"] = ["invented"]
            self.assertNotEqual(finding(run(rt, f, s))["conclusion_type"], N)

    def test_stale_context_binding_cannot_release(self):
        rt, f, s = fixture(); rt["contract_evidence"]["document_excerpt"] += "增加上下文"
        self.assertTrue(run(rt, f, s)["blocked"])

    def test_raw_input_spec_immutable(self):
        rt, f, s = fixture(); add_gap(f); before = deepcopy((rt, f, s))
        r = run(rt, f, s)
        self.assertEqual(before, (rt, f, s))
        self.assertEqual(r["raw_response"], {"findings": [f]})
        self.assertEqual(finding(r)["review_handoff"]["workflow_status"], "requires_human_second_review")

    def test_same_id_not_a_policy_shortcut(self):
        rt, f, s = fixture(); add_gap(f); a = run(rt, f, s)
        rt["issue_id"] = f["issue_id"] = "SYN-OTHER"
        b = run(rt, f, s)
        self.assertEqual(a["valid_legal_verdicts"], b["valid_legal_verdicts"])

    def test_v4_optout_unchanged(self):
        from test_scope_dependency_v4 import run as old_run, add_gap as old_gap
        rt, f, s = v4_fixture(); old_gap(f)
        self.assertFalse(old_run(rt, f, s)["blocked"])

    def test_entrypoint_builds_contract_and_prompt_before_mock_call(self):
        import run_hierarchy_gated_llm_smoke as runner
        rt, f, s = fixture(); rt.pop("review_task_contract_v41")
        base = (Path(__file__).resolve().parents[1] / "prompts/system_prompt_final.md").read_text(encoding="utf-8")
        def request(key, prompt, runtime, **kwargs):
            self.assertEqual(runtime["review_task_contract_v41"], build_contract(runtime, s))
            self.assertEqual(prompt, build_prompt(base))
            self.assertEqual(kwargs["reasoning_effort"], "low")
            return {"parsed": {"findings": [f]}}
        with patch.object(runner, "model_request", side_effect=request) as mocked:
            _, r = runner.run_final_reasoning(api_key="synthetic", prompt=base, runtime_input=rt,
                                              max_tokens=100, scope_dependency_v41=s)
        self.assertEqual(mocked.call_count, 1); self.assertFalse(r["blocked"])

    def test_export_row_distinguishes_scope_hold_without_changing_raw(self):
        from export_review_excel import flatten_record
        rt, f, s = fixture(); add_gap(f, "other_undetermined", "undetermined")
        g = run(rt, f, s)
        for include in (False, True):
            row = list(flatten_record({"gate_result": g, "runtime_input": rt}, include_handoff=include))[0]
            self.assertIn("scope_review_required", row[3])
            self.assertNotEqual(row[3], U)
            if include:
                self.assertEqual(row[14], s["question_verbatim"])

    def test_scope_does_not_bypass_geographic_filter(self):
        from test_scope_boundary_policy import local
        rt, f, s = fixture(); add_gap(f)
        rt["project_context"]["project_location"].update(province="天津市", city="天津市")
        law = local(); law["chunk_id"] = "law-1"
        rt["retrieved_legal_evidence"] = [law]
        rt["scope_boundary_experiment"] = {"version": "scope-boundary-v1", "geographic_filter": True, "task_boundary": False}
        rt["review_task_contract_v41"] = build_contract(rt, s)
        f["decision_basis"]["task_scope_sha256"] = rt["review_task_contract_v41"]["input_scope_sha256"]
        self.assertNotEqual(finding(run(rt, f, s))["conclusion_type"], N)

    def test_affirmative_risk_not_promoted_to_N_by_outside_gap(self):
        rt, f, s = fixture(); add_gap(f); f["conclusion_type"] = "requires_human_legal_review"
        r = run(rt, f, s)
        self.assertNotEqual(finding(r)["conclusion_type"], N)


if __name__ == "__main__":
    unittest.main()
