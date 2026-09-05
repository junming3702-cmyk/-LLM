"""Deterministic Stage 3 external-fallback and runner-integration tests.

All provider responses are local fixtures.  No public endpoint and no LLM API
is called by this test module.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from external_fallback_v2 import (
    COMPLETED_NO_HIT,
    ExternalFallbackStateMachine,
    ExternalRequest,
    ManifestHttpProvider,
    PENDING_HUMAN_SCOPE,
    ProviderResponse,
    build_local_search_completion,
    derive_verification_reasons,
    is_usable_legal_basis,
    sanitize_legal_query_terms,
    sha256_text,
)


OFFICIAL_ENTRY = {
    "external_source_id": "EXT-OFFICIAL-001",
    "source_name": "国家法律法规数据库 fixture",
    "base_url": "https://law.example.gov.cn/search",
    "source_category": "national_legal_database",
    "issuer": "fixture official issuer",
}
CECN_ENTRY = {
    "external_source_id": "EXT-CECN-001",
    "source_name": "建设造价信息网 fixture",
    "base_url": "https://www.cecn.gov.cn/index.asp",
    "source_category": "industry_cost_information",
}
ARTICLE_ENTRY = {
    "external_source_id": "EXT-OFFICIAL-ARTICLE-001",
    "source_name": "国家法律法规数据库 fixture",
    "base_url": "https://law.example.gov.cn/article/10",
    "source_category": "national_legal_database",
    "issuer": "fixture official issuer",
    "law_title": "中华人民共和国招标投标法",
    "article": "第十条",
    "expected_quote": "投标人应当按照法律规定提交投标文件。",
    "version": "2017 revision fixture",
    "effective_date": "2017-12-28",
    "normative_level": "Level 1",
    "source_locator": "https://law.example.gov.cn/article/10#article=第十条",
}


def local_no_hit() -> dict:
    return {
        "status": COMPLETED_NO_HIT,
        "executed_levels": ["Level 1", "Level 2", "Level 3", "Level 4"],
        "level_results": [
            {"level": level, "status": "completed", "level_state": "no_usable_violation_found"}
            for level in ("Level 1", "Level 2", "Level 3", "Level 4")
        ],
        "all_levels_executed": True,
        "no_usable_applicable_basis": True,
        "usable_local_evidence_count": 0,
        "retrieved_local_evidence_count": 0,
        "blocked_scope_levels": [],
        "stopped_at_level": "none",
        "explicit_satisfaction_found": False,
        "completion_basis": "runtime_execution",
        "completion_basis_detail": "strict_level_1_to_4_local_search_no_usable_basis",
        "failure_reason": "",
    }


class FixtureProvider:
    def __init__(self, response: ProviderResponse, provider_id: str = "fixture-provider-v2") -> None:
        self.response = response
        self.provider_id = provider_id
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return self.response


def valid_candidate(*, source_url: str, normative_level: str, source_category: str = "national_legal_database") -> dict:
    quote = "投标人应当按照法律规定提交投标文件。"
    return {
        "candidate_id": "EXT-CANDIDATE-001",
        "source_url": source_url,
        "issuer": "fixture official issuer",
        "title": "中华人民共和国招标投标法 fixture",
        "version": "2017 revision fixture",
        "effective_date": "2017-12-28",
        "retrieved_at": "2026-09-05T00:00:00+00:00",
        "content_sha256": sha256_text(quote),
        "article": "第十条",
        "legal_quote": quote,
        "normative_level": normative_level,
        "source_category": source_category,
    }


class ExternalFallbackV2Tests(unittest.TestCase):
    def machine(self, response: ProviderResponse, entries=None) -> tuple[ExternalFallbackStateMachine, FixtureProvider]:
        provider = FixtureProvider(response)
        machine = ExternalFallbackStateMachine(
            enabled=True,
            provider=provider,
            manifest_entries=entries or [OFFICIAL_ENTRY],
        )
        return machine, provider

    def run_machine(self, machine, *, local=None, reasons=(), terms=("招标投标法",), explicit=False):
        return machine.run(
            issue_id="P3-I01",
            local_search_completion=local or local_no_hit(),
            verification_reasons=reasons,
            legal_query_terms=terms,
            query_ids=("P3-I01:legal-scope",),
            project_scope={"jurisdiction_status": "uncertain", "project_type": "construction"},
            local_explicit_satisfaction=explicit,
        )

    def test_success_is_hit_but_candidate_remains_pending_and_keeps_actual_level(self):
        response = ProviderResponse(
            provider_id="fixture-official",
            status="completed",
            candidates=[valid_candidate(source_url=OFFICIAL_ENTRY["base_url"], normative_level="Level 2")],
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
            query_ids=["P3-I01:legal-scope"],
        )
        machine, provider = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], "hit")
        self.assertTrue(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])
        candidate = audit["candidates"][0]
        self.assertEqual(candidate["normative_level"], "Level 2")
        self.assertEqual(candidate["actual_normative_level"], "Level 2")
        self.assertFalse(candidate["independent_legal_evidence"])
        self.assertEqual(candidate["human_confirmation_status"], "pending")
        self.assertEqual(candidate["legal_evidence_eligibility"], "verification_only")
        self.assertTrue(candidate["source_locator"])
        self.assertEqual(candidate["source_title"], candidate["title"])
        self.assertEqual(candidate["source_version"], candidate["version"])
        self.assertEqual(candidate["source_hash"], candidate["content_sha256"])
        self.assertTrue(candidate["external_candidate"])
        self.assertTrue(audit["dispatch_attempted"])
        self.assertTrue(audit["provider_call_attempted"])
        self.assertFalse(audit["http_called"])
        self.assertEqual(len(provider.requests), 1)
        self.assertNotIn("document_excerpt", provider.requests[0].__dict__)

    def test_local_admission_predicate_matches_gate_for_targeted_blockers(self):
        """Fallback and gate must agree on the narrow evidence-admission cases."""

        import llm_abstention_gate as gate

        base = {
            "source_locator": "中华人民共和国招标投标法/第十条",
            "legal_quote": "投标人应当按照法律规定提交投标文件。",
            "independent_legal_evidence": True,
            "normative_level": "Level 1",
        }
        cases = {
            "legacy_optional_fields_omitted": base,
            "independent_primary_missing": {**base, "independent_legal_evidence": None},
            "independent_primary_false": {**base, "independent_legal_evidence": False},
            "independent_alias_false": {**base, "independent_evidence": False},
            "retrieval_admission_rejected": {**base, "retrieval_admission": "excluded_pending_review"},
            "verification_pending": {**base, "verification_status": "pending_human_verification"},
            "non_level4_mismatch": {**base, "applicability_status": "mismatch"},
            "non_level4_not_applicable": {**base, "applicability_status": "not_applicable"},
            "level4_scope_mismatch": {
                **base,
                "normative_level": "Level 4",
                "applicability_status": "pending_human_applicability_confirmation",
            },
            "legacy_inferred_level4_scope_mismatch": {
                **base,
                "normative_level": "",
                "scope_classification": "local_regional",
                "applicability_status": "mismatch",
            },
        }
        expected = {
            "legacy_optional_fields_omitted": True,
            "independent_primary_missing": False,
            "independent_primary_false": False,
            "independent_alias_false": False,
            "retrieval_admission_rejected": False,
            "verification_pending": False,
            "non_level4_mismatch": False,
            "non_level4_not_applicable": False,
            "level4_scope_mismatch": False,
            "legacy_inferred_level4_scope_mismatch": False,
        }
        for name, row in cases.items():
            self.assertEqual(is_usable_legal_basis(row), expected[name], msg=name)
            self.assertEqual(gate._is_usable_legal_basis(row), expected[name], msg=f"gate:{name}")

    def test_explicit_null_admission_signals_are_fail_closed(self):
        base = {
            "source_locator": "中华人民共和国招标投标法/第十条",
            "legal_quote": "投标人应当按照法律规定提交投标文件。",
            "independent_legal_evidence": True,
            "normative_level": "Level 1",
        }
        for field in ("independent_evidence", "legal_evidence_eligibility", "retrieval_admission", "verification_status"):
            row = {**base, field: None}
            self.assertFalse(is_usable_legal_basis(row), msg=field)

    def test_invalid_local_basis_triggers_fallback_eligibility_in_completion_summary(self):
        hierarchy = {
            "levels": [
                {
                    "level": level,
                    "status": "completed",
                    "retrieval_executed": True,
                    "retrieval_status": "completed",
                    "level_state": "no_usable_violation_found",
                }
                for level in ("Level 1", "Level 2", "Level 3", "Level 4")
            ],
            "stopped_at_level": "none",
        }
        base = {
            "source_locator": "中华人民共和国招标投标法/第十条",
            "legal_quote": "投标人应当按照法律规定提交投标文件。",
            "independent_legal_evidence": True,
            "normative_level": "Level 1",
        }
        for blocker in (
            {"independent_legal_evidence": None},
            {"independent_evidence": False},
            {"retrieval_admission": "excluded_pending_review"},
            {"verification_status": "unverified"},
            {"applicability_status": "mismatch"},
        ):
            row = {**base, **blocker}
            summary = build_local_search_completion(hierarchy, [row])
            self.assertEqual(summary["usable_local_evidence_count"], 0, msg=str(blocker))
            self.assertTrue(summary["no_usable_applicable_basis"], msg=str(blocker))
            self.assertTrue(summary["fallback_discovery_eligible"], msg=str(blocker))

    def test_actual_provider_nohit_can_support_no_applicable_status(self):
        response = ProviderResponse(
            provider_id="fixture-official",
            status="completed",
            candidates=[],
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], COMPLETED_NO_HIT)
        self.assertTrue(audit["external_search_completed"])
        self.assertTrue(audit["external_no_applicable_independent_source"])

    def test_scope_completion_requires_actual_scope_or_human_attestation(self):
        incomplete_response = ProviderResponse(
            provider_id="fixture-incomplete-scope",
            status="completed",
            candidates=[],
            configured_search_scope=["scope-a"],
            executed_search_scope=[],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(incomplete_response)
        incomplete = self.run_machine(machine)
        self.assertEqual(incomplete["external_search_status"], "pending")
        self.assertFalse(incomplete["external_search_completed"])
        self.assertFalse(incomplete["external_no_applicable_independent_source"])

        unattested_response = ProviderResponse(
            provider_id="fixture-manual-scope",
            status="completed",
            candidates=[],
            configured_search_scope=["scope-a"],
            executed_search_scope=["scope-a"],
            scope_completed=True,
            scope_completion_basis="human_attested_manual_discovery",
            human_attested=True,
            scope_attestation_id="",
        )
        machine, _ = self.machine(unattested_response)
        unattested = self.run_machine(machine)
        self.assertEqual(unattested["external_search_status"], "pending")
        self.assertFalse(unattested["external_search_completed"])

        attested_response = ProviderResponse(
            provider_id="fixture-manual-scope",
            status="completed",
            candidates=[],
            configured_search_scope=["scope-a"],
            executed_search_scope=["scope-a"],
            scope_completed=True,
            scope_completion_basis="human_attested_manual_discovery",
            human_attested=True,
            scope_attestation_id="ATTEST-001",
        )
        machine, _ = self.machine(attested_response)
        attested = self.run_machine(machine)
        self.assertEqual(attested["external_search_status"], COMPLETED_NO_HIT)
        self.assertTrue(attested["external_search_completed"])
        self.assertTrue(attested["external_no_applicable_independent_source"])

    def test_manifest_only_finite_fetch_is_pending_not_nohit(self):
        response = ProviderResponse(
            provider_id="manifest-http-fixture",
            status="pending",
            candidates=[],
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=False,
            scope_completion_basis="manifest_lookup",
            failure_reason="finite_manifest_fetch_not_exhaustive",
            provider_mode="manifest_lookup_only",
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], "pending")
        self.assertEqual(audit["discovery"]["status"], PENDING_HUMAN_SCOPE)
        self.assertFalse(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])

    def test_version_doubt_runs_verification_without_turning_local_satisfaction_into_discovery_nohit(self):
        local = {
            "status": "completed_with_candidates",
            "no_usable_applicable_basis": False,
            "all_levels_executed": True,
            "usable_local_evidence_count": 1,
        }
        response = ProviderResponse(
            provider_id="fixture-verifier",
            status="pending",
            scope_completed=False,
            scope_completion_basis="manifest_lookup",
        )
        machine, provider = self.machine(response)
        audit = self.run_machine(
            machine,
            local=local,
            reasons=("source_version_or_status_doubt",),
            explicit=True,
        )
        self.assertEqual(audit["discovery"]["status"], "not_called")
        self.assertEqual(audit["verification"]["status"], PENDING_HUMAN_SCOPE)
        self.assertEqual(len(provider.requests), 1)
        self.assertEqual(provider.requests[0].mode, "verification")

    def test_local_scope_mismatch_triggers_verification_but_not_discovery_completion(self):
        local = {
            "status": PENDING_HUMAN_SCOPE,
            "no_usable_applicable_basis": False,
            "all_levels_executed": False,
            "blocked_scope_levels": ["Level 4"],
        }
        response = ProviderResponse(
            provider_id="fixture-verifier",
            status="pending",
            scope_completed=False,
            scope_completion_basis="manifest_lookup",
        )
        machine, provider = self.machine(response)
        audit = self.run_machine(machine, local=local, reasons=("local_level4_scope_mismatch",))
        self.assertEqual(audit["discovery"]["status"], "not_called")
        self.assertEqual(audit["verification"]["status"], PENDING_HUMAN_SCOPE)
        self.assertFalse(audit["external_search_completed"])
        self.assertEqual(provider.requests[0].mode, "verification")

    def test_relevant_pending_article_blocks_no_applicable_law_conclusion(self):
        local = local_no_hit()
        local.update(
            {
                "status": "completed_with_candidates",
                "no_usable_applicable_basis": True,
                "fallback_discovery_eligible": True,
                "no_applicable_status_eligible": False,
                "observed_candidate_count": 1,
                "decisive_missing_facts": ["工程所在地"],
                "has_relevant_inconclusive": True,
            }
        )
        response = ProviderResponse(
            provider_id="fixture-official",
            status="completed",
            candidates=[],
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine, local=local)
        self.assertEqual(audit["external_search_status"], COMPLETED_NO_HIT)
        self.assertTrue(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])

    def test_manifest_http_adapter_records_http_call_but_keeps_finite_miss_pending(self):
        class FakeResponse:
            ok = True
            status_code = 200
            content = b"fixture public page"
            headers = {"content-type": "text/html"}

        provider = ManifestHttpProvider([OFFICIAL_ENTRY], timeout_seconds=1)
        machine = ExternalFallbackStateMachine(
            enabled=True,
            provider=provider,
            manifest_entries=[OFFICIAL_ENTRY],
        )
        request = ExternalRequest(
            mode="discovery",
            issue_id="P3-I01",
            local_search_completion=local_no_hit(),
            verification_reasons=(),
            legal_query_terms=("招标投标法",),
            query_ids=("P3-I01:legal-scope",),
            manifest_entries=(OFFICIAL_ENTRY,),
            project_scope={"jurisdiction_status": "uncertain"},
        )
        with patch("external_fallback_v2._resolve_addresses_are_public", return_value=True), patch(
            "external_fallback_v2.requests.get", return_value=FakeResponse()
        ):
            response = provider.execute(request)
            audit = machine.run(
                issue_id="P3-I01",
                local_search_completion=local_no_hit(),
                legal_query_terms=("招标投标法",),
                query_ids=("P3-I01:legal-scope",),
                project_scope={"jurisdiction_status": "uncertain"},
            )
        self.assertEqual(response.status, "pending")
        self.assertTrue(response.provider_call_attempted)
        self.assertTrue(response.http_called)
        self.assertEqual(response.http_call_count, 1)
        self.assertFalse(response.scope_completed)
        self.assertEqual(response.scope_completion_basis, "manifest_lookup")
        self.assertEqual(audit["external_search_status"], "pending")
        self.assertTrue(audit["http_called"])
        self.assertFalse(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])

    def test_manifest_declared_article_match_emits_pending_candidate_but_not_exhaustive_search(self):
        class FakeResponse:
            ok = True
            status_code = 200
            content = (
                "<html><h1>中华人民共和国招标投标法</h1>"
                "<p>第十条 投标人应当按照法律规定提交投标文件。</p></html>"
            ).encode("utf-8")
            headers = {"content-type": "text/html; charset=utf-8"}

        provider = ManifestHttpProvider([ARTICLE_ENTRY], timeout_seconds=1)
        request = ExternalRequest(
            mode="discovery",
            issue_id="P3-I01",
            local_search_completion=local_no_hit(),
            verification_reasons=(),
            legal_query_terms=("招标投标法",),
            query_ids=("P3-I01:legal-scope",),
            manifest_entries=(ARTICLE_ENTRY,),
            project_scope={"jurisdiction_status": "uncertain"},
        )
        with patch("external_fallback_v2._resolve_addresses_are_public", return_value=True), patch(
            "external_fallback_v2.requests.get", return_value=FakeResponse()
        ):
            response = provider.execute(request)
            machine = ExternalFallbackStateMachine(
                enabled=True,
                provider=provider,
                manifest_entries=[ARTICLE_ENTRY],
            )
            audit = machine.run(
                issue_id="P3-I01",
                local_search_completion=local_no_hit(),
                legal_query_terms=("招标投标法",),
                query_ids=("P3-I01:legal-scope",),
                project_scope={"jurisdiction_status": "uncertain"},
            )
        self.assertEqual(response.status, "completed")
        self.assertEqual(len(response.candidates), 1)
        self.assertEqual(
            response.fetch_records[0]["article_target_check"]["status"],
            "declared_article_target_matched_pending_human_confirmation",
        )
        self.assertEqual(audit["external_search_status"], "hit")
        self.assertFalse(audit["external_search_completed"])
        candidate = audit["candidates"][0]
        self.assertEqual(candidate["source_locator"], ARTICLE_ENTRY["source_locator"])
        self.assertEqual(candidate["source_title"], ARTICLE_ENTRY["law_title"])
        self.assertEqual(candidate["source_version"], ARTICLE_ENTRY["version"])
        self.assertEqual(candidate["source_hash"], candidate["content_sha256"])
        self.assertFalse(candidate["independent_legal_evidence"])
        self.assertTrue(candidate["human_confirmation_required"])

    def test_provider_failure_with_partial_candidates_is_failed_and_keeps_partial_audit_separate(self):
        response = ProviderResponse(
            provider_id="fixture-transport-failure",
            status="failed",
            candidates=[valid_candidate(source_url=OFFICIAL_ENTRY["base_url"], normative_level="Level 1")],
            failure_reason="timeout_after_partial_payload",
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=False,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], "failed")
        self.assertFalse(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])
        self.assertEqual(audit["discovery"]["status"], "failed")
        self.assertEqual(audit["discovery"]["candidate_count"], 0)
        self.assertEqual(audit["discovery"]["partial_candidate_count"], 1)
        self.assertEqual(audit["discovery"]["partial_candidates"][0]["source_locator"], f"{OFFICIAL_ENTRY['base_url']}#article=第十条")

    def test_not_called_status_cannot_become_completed_nohit_from_scope_flags(self):
        response = ProviderResponse(
            provider_id="fixture-not-called",
            status="not_called",
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
            provider_call_attempted=False,
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["discovery"]["status"], "pending_provider")
        self.assertEqual(audit["external_search_status"], "pending")
        self.assertFalse(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])

    def test_level4_scope_metadata_matched_is_preserved_by_runner(self):
        import run_hierarchy_gated_llm_smoke as runner

        candidate = {
            "normative_level": "Level 4",
            "scope_classification": "local_regional",
            "geographic_scope": "四川省",
            "project_type_scope": "房屋建筑工程",
            "applicability_status": "matched",
            "applicability_basis": "source registry explicitly matched project location and type",
            "evidence_support_confidence": "medium",
            "applicability_confidence": "high",
        }
        result = runner.evidence_applicability(candidate, {})
        self.assertEqual(result["applicability_status"], "matched")
        self.assertEqual(result["geographic_scope"], "四川省")
        self.assertEqual(result["project_type_scope"], "房屋建筑工程")
        self.assertEqual(result["applicability_basis"], candidate["applicability_basis"])
        self.assertEqual(result["applicability_confidence"], "high")

    def test_failed_triage_marks_enclosing_level_failed_and_skips_lower_levels(self):
        import run_hierarchy_gated_llm_smoke as runner

        class OneCandidateRetriever:
            embedding_model_name = "fixture-embedding"

            def retrieve_many(self, queries, *, level, phase, top_k):
                if level == "Level 1" and phase == "primary":
                    return [{
                        "chunk_id": "local:l1:failed-triage",
                        "source_locator": "第十条",
                        "legal_quote": "投标人应当按照法律规定提交投标文件。",
                        "law": "中华人民共和国招标投标法",
                        "article": "第十条",
                        "normative_level": "Level 1",
                        "independent_legal_evidence": True,
                        "legal_evidence_eligibility": "independent_candidate",
                        "source_role": "primary_candidate",
                    }]
                return []

            def assert_no_cross_level_mix(self, candidates, expected_level):
                return None

        label = {
            "issue_id": "P3-I01",
            "project_id": "P3",
            "document_id": "DOC-P3",
            "document_location": "fixture document",
            "document_excerpt": "测试合同摘录",
        }

        def failed_triage_request(*args, **kwargs):
            return {"parsed": None, "selected_text": "{", "finish_reason": "length", "usage": {}}

        with patch.object(runner, "model_request", side_effect=failed_triage_request), patch.object(
            runner, "apply_gate", side_effect=lambda raw, runtime: {"status": "passed", "response": raw}
        ):
            result = runner.run_case(
                api_key="unused-fixture-key",
                retriever=OneCandidateRetriever(),
                final_prompt="fixture prompt",
                context_template={"project_location": {"human_confirmation": "confirmed"}, "project_type": "construction"},
                label=label,
                top_k=5,
                final_max_tokens=128,
                triage_max_tokens=64,
                compact_final_output=True,
                experiment_run_id="stage3-triage-failure",
                external_fallback=ExternalFallbackStateMachine(enabled=False, provider=None),
            )
        cascade = result["cascade_execution_audit"]
        self.assertEqual(cascade[0]["status"], "failed")
        self.assertEqual(cascade[0]["failure_reason"], "triage_response_not_valid_json_object")
        self.assertEqual(cascade[1]["status"], "skipped_after_prior_level_failure")
        self.assertFalse(result["local_search_completion"]["all_levels_executed"])
        self.assertFalse(result["local_search_completion"]["fallback_discovery_eligible"])

    def test_real_gate_applies_to_state_machine_output_and_preserves_external_provenance(self):
        from llm_abstention_gate import apply_gate as real_apply_gate

        response = ProviderResponse(
            provider_id="fixture-official",
            status="completed",
            candidates=[valid_candidate(source_url=OFFICIAL_ENTRY["base_url"], normative_level="Level 2")],
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
            query_ids=["P3-I01:legal-scope"],
        )
        machine, _ = self.machine(response)
        external_audit = self.run_machine(machine)
        candidate = external_audit["candidates"][0]
        runtime = {
            "run_id": "stage3-gate-integration",
            "project_id": "P3",
            "issue_id": "P3-I01",
            "review_scope": {"jurisdiction_status": "uncertain"},
            "project_context": {"project_id": "P3", "project_type": "construction"},
            "contract_evidence": {
                "document_id": "DOC-P3",
                "document_location": "fixture document",
                "document_excerpt": "测试合同摘录",
            },
            "hierarchy_retrieval_audit": {
                "issue_id": "P3-I01",
                "levels": [],
                "stopped_at_level": "none",
            },
            "local_search_completion": local_no_hit(),
            "external_retrieval_audit": external_audit,
            "retrieved_legal_evidence": [candidate],
            "external_sources_used": [candidate],
            "triage_binding": {
                "issue_id": "P3-I01",
                "level_decisions_are_issue_specific": True,
                "do_not_distribute_triage_state_to_unrelated_findings": True,
            },
            "runtime_constraints": {
                "external_retrieval_called": True,
                "external_provider_call_attempted": True,
                "external_http_called": False,
                "external_search_status": "hit",
                "external_search_completed": True,
                "external_no_applicable_independent_source": False,
            },
        }
        raw = {
            "findings": [{
                "finding_id": "P3-I01-F01",
                "issue_id": "P3-I01",
                "risk_category": "potential_non_compliance",
                "risk_severity": "medium",
                "legal_element_coverage": {
                    "subject": "supported",
                    "conduct_or_condition": "supported",
                    "jurisdiction_and_scope": "supported",
                    "legal_consequence": "supported",
                },
                "compliance_relation": "potential_non_compliance",
                "obligation_phase": "tender_submission",
                "requirement_lifecycle": "current",
                "severity_basis": "procedural_or_temporal_concern",
                "scope_assessment": "within_review_scope",
                "legal_evidence": [{"chunk_id": candidate["chunk_id"]}],
                "reasoning_conclusion": "外部候选条款仅用于人工核验。",
                "conclusion_type": "requires_human_legal_review",
                "evidence_boundary": "supported_by_verification_pending_source",
                "confidence_assessment": "low",
                "recommended_human_action": "请人工核验外部来源及适用性。",
                "human_review_status": "review_required",
            }],
        }
        gated = real_apply_gate(raw, runtime)
        self.assertFalse(gated["blocked"])
        finding = gated["response"]["findings"][0]
        self.assertEqual(finding["conclusion_type"], "insufficient_information_needs_human_confirm")
        self.assertEqual(len(finding["legal_evidence"]), 1)
        gated_evidence = finding["legal_evidence"][0]
        self.assertEqual(gated_evidence["source_locator"], candidate["source_locator"])
        self.assertEqual(gated_evidence["source_role"], "external_candidate")
        self.assertEqual(gated_evidence["source_title"], candidate["source_title"])
        self.assertEqual(gated_evidence["source_version"], candidate["source_version"])
        self.assertEqual(gated_evidence["source_hash"], candidate["source_hash"])
        self.assertEqual(gated_evidence["legal_evidence_eligibility"], "verification_only")
        self.assertEqual(gated["response"]["retrieval_audit"]["external_retrieval_audit"]["local_search_completion"]["status"], local_no_hit()["status"])

    def test_runner_preserves_explicit_non_level4_scope_metadata(self):
        import run_hierarchy_gated_llm_smoke as runner

        candidate = {
            "normative_level": "Level 2",
            "scope_classification": "explicit_scope_from_source_registry",
            "geographic_scope": "source_declared_scope",
            "project_type_scope": "source_declared_project_type",
            "applicability_status": "source_status_pending",
            "applicability_basis": "source_registry_record",
            "evidence_support_confidence": "low",
            "applicability_confidence": "low",
        }
        result = runner.evidence_applicability(candidate, {})
        self.assertEqual(result["scope_classification"], "explicit_scope_from_source_registry")
        self.assertEqual(result["geographic_scope"], "source_declared_scope")
        self.assertEqual(result["project_type_scope"], "source_declared_project_type")
        self.assertEqual(result["applicability_status"], "source_status_pending")
        self.assertEqual(result["applicability_basis"], "source_registry_record")

    def test_network_failure_is_failed_and_never_nohit(self):
        response = ProviderResponse(
            provider_id="fixture-network",
            status="failed",
            failure_reason="timeout",
            scope_completed=False,
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], "failed")
        self.assertFalse(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])
        self.assertEqual(audit["external_failure_reason"], "timeout")

    def test_cecn_candidate_is_contextual_only_and_not_sole_basis(self):
        response = ProviderResponse(
            provider_id="fixture-cecn",
            status="completed",
            candidates=[
                valid_candidate(
                    source_url=CECN_ENTRY["base_url"],
                    normative_level="S2",
                    source_category="industry_cost_information",
                )
            ],
            configured_search_scope=[CECN_ENTRY["external_source_id"]],
            executed_search_scope=[CECN_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response, entries=[CECN_ENTRY])
        audit = self.run_machine(machine)
        candidate = audit["candidates"][0]
        self.assertEqual(audit["external_search_status"], "hit")
        self.assertTrue(candidate["cecn_candidate_only"])
        self.assertEqual(candidate["normative_level"], "S2")
        self.assertEqual(candidate["legal_evidence_eligibility"], "supplement_only")
        self.assertFalse(candidate["independent_legal_evidence"])
        self.assertFalse(audit["external_no_applicable_independent_source"])

    def test_rejected_candidate_is_not_reclassified_as_nohit(self):
        invalid = valid_candidate(source_url=OFFICIAL_ENTRY["base_url"], normative_level="Level 1")
        invalid["article"] = "candidate only; exact article must be confirmed"
        response = ProviderResponse(
            provider_id="fixture-invalid",
            status="completed",
            candidates=[invalid],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], "pending")
        self.assertFalse(audit["external_search_completed"])
        self.assertFalse(audit["external_no_applicable_independent_source"])
        self.assertEqual(audit["discovery"]["rejected_candidate_count"], 1)

    def test_dispatch_provider_and_http_flags_are_distinct(self):
        enabled_without_provider = ExternalFallbackStateMachine(
            enabled=True,
            provider=None,
            manifest_entries=[OFFICIAL_ENTRY],
        )
        audit = self.run_machine(enabled_without_provider)
        self.assertTrue(audit["dispatch_attempted"])
        self.assertFalse(audit["provider_call_attempted"])
        self.assertFalse(audit["http_called"])
        disabled = ExternalFallbackStateMachine(enabled=False, provider=None, manifest_entries=[OFFICIAL_ENTRY])
        audit_disabled = self.run_machine(disabled)
        self.assertEqual(audit_disabled["external_search_status"], "not_called")
        self.assertFalse(audit_disabled["dispatch_attempted"])
        self.assertFalse(audit_disabled["provider_call_attempted"])
        self.assertFalse(audit_disabled["http_called"])

    def test_query_sanitization_rejects_document_path_without_logging_text(self):
        accepted, rejected = sanitize_legal_query_terms(["招标投标法 投标保证金", r"X:\private\contract.docx"])
        self.assertEqual(accepted, ["招标投标法 投标保证金"])
        self.assertEqual(rejected, ["query_rejected_private_or_sensitive_pattern"])

    def test_local_completion_helper_does_not_call_explicit_satisfaction_nohit(self):
        audit = {
            "issue_id": "P3-I01",
            "stopped_at_level": "none",
            "levels": [
                {
                    "issue_id": "P3-I01",
                    "level": level,
                    "status": "completed",
                    "level_state": "no_usable_violation_found",
                }
                for level in ("Level 1", "Level 2", "Level 3", "Level 4")
            ],
        }
        local = build_local_search_completion(
            audit,
            [
                {
                    "chunk_id": "local:l1:1",
                    "source_locator": "第十条",
                    "legal_quote": "投标人应当按照法律规定提交投标文件。",
                    "normative_level": "Level 1",
                    "independent_legal_evidence": True,
                    "legal_evidence_eligibility": "independent_candidate",
                    "source_role": "primary_candidate",
                }
            ],
            local_explicit_satisfaction=True,
        )
        self.assertEqual(local["status"], "completed_with_candidates")
        self.assertFalse(local["no_usable_applicable_basis"])
        self.assertTrue(local["explicit_satisfaction_found"])

    def test_local_completion_requires_actual_complete_rows_and_does_not_count_skipped_presence(self):
        audit = {
            "issue_id": "P3-I01",
            "stopped_at_level": "none",
            "levels": [
                {
                    "issue_id": "P3-I01",
                    "level": "Level 1",
                    "status": "completed",
                    "retrieval_executed": True,
                    "retrieval_status": "completed_no_hit",
                    "phases": [],
                },
                {
                    "issue_id": "P3-I01",
                    "level": "Level 2",
                    "status": "completed",
                    "retrieval_executed": True,
                    "retrieval_status": "completed_no_hit",
                    "phases": [],
                },
                {
                    "issue_id": "P3-I01",
                    "level": "Level 3",
                    "status": "skipped_after_prior_level_failure",
                    "retrieval_executed": False,
                    "retrieval_status": "skipped_after_prior_level_failure",
                    "phases": [],
                },
                {
                    "issue_id": "P3-I01",
                    "level": "Level 4",
                    "status": "completed",
                    "retrieval_executed": True,
                    "retrieval_status": "completed_no_hit",
                    "phases": [],
                },
            ],
        }
        local = build_local_search_completion(audit, [])
        self.assertFalse(local["all_levels_executed"])
        self.assertFalse(local["no_usable_applicable_basis"])
        self.assertEqual(local["status"], PENDING_HUMAN_SCOPE)
        self.assertEqual(local["completion_basis"], "runtime_partial")
        self.assertIn("Level 3", local["level_completion_audit"]["incomplete_levels"])

    def test_none_stopped_at_value_is_not_treated_as_truthy_early_stop(self):
        audit = {
            "issue_id": "P3-I01",
            "stopped_at_level": "none",
            "levels": [
                {
                    "level": level,
                    "status": "completed",
                    "retrieval_executed": True,
                    "retrieval_status": "completed_no_hit",
                    "phases": [],
                }
                for level in ("Level 1", "Level 2", "Level 3", "Level 4")
            ],
        }
        local = build_local_search_completion(audit, [])
        self.assertTrue(local["all_levels_executed"])
        self.assertEqual(local["status"], COMPLETED_NO_HIT)
        self.assertEqual(local["completion_basis"], "runtime_execution")

    def test_provider_failure_with_partial_candidate_does_not_make_aggregate_candidate_hit(self):
        response = ProviderResponse(
            provider_id="fixture-transport-failure",
            status="failed",
            candidates=[valid_candidate(source_url=OFFICIAL_ENTRY["base_url"], normative_level="Level 1")],
            failure_reason="transport_failure",
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response)
        audit = self.run_machine(machine)
        self.assertEqual(audit["external_search_status"], "failed")
        self.assertEqual(audit["candidate_count"], 0)
        self.assertEqual(audit["discovery"]["partial_candidate_count"], 1)
        self.assertFalse(audit["external_no_applicable_independent_source"])

    def test_runner_runtime_contains_issue_bound_local_and_external_audits_without_api(self):
        import run_hierarchy_gated_llm_smoke as runner

        class EmptyRetriever:
            embedding_model_name = "fixture-embedding"

            def retrieve_many(self, queries, *, level, phase, top_k):
                return []

            def assert_no_cross_level_mix(self, candidates, expected_level):
                return None

        response = ProviderResponse(
            provider_id="fixture-official",
            status="completed",
            candidates=[],
            configured_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            executed_search_scope=[OFFICIAL_ENTRY["external_source_id"]],
            scope_completed=True,
            scope_completion_basis="provider_execution",
        )
        machine, _ = self.machine(response)
        label = {
            "issue_id": "P3-I01",
            "project_id": "P3",
            "document_id": "DOC-P3",
            "document_location": "fixture document",
            "document_excerpt": "测试合同摘录",
        }

        def fake_model_request(*args, **kwargs):
            if kwargs.get("response_contract") == "triage":
                parsed = {
                    "level_state": "no_usable_violation_found",
                    "selected_chunk_ids": [],
                    "reason": "",
                    "missing_elements": [],
                    "confidence": "low",
                }
            else:
                parsed = {
                    "findings": [
                        {
                            "conclusion_type": (
                                "insufficient_information_needs_human_confirm"
                            )
                        }
                    ]
                }
            return {"parsed": parsed, "selected_text": "", "finish_reason": "stop", "usage": {}}

        with patch.object(
            runner, "model_request", side_effect=fake_model_request
        ) as model_mock, patch.object(
            runner, "apply_gate", side_effect=lambda raw, runtime: {"status": "passed", "response": raw}
        ):
            result = runner.run_case(
                api_key="unused-fixture-key",
                retriever=EmptyRetriever(),
                final_prompt="fixture prompt",
                context_template={
                    "project_location": {"province": "四川省", "human_confirmation": "confirmed"},
                    "project_type": "construction",
                },
                label=label,
                top_k=5,
                final_max_tokens=128,
                triage_max_tokens=64,
                compact_final_output=True,
                experiment_run_id="stage3-test",
                external_fallback=machine,
            )
        runtime = result["runtime_input"]
        self.assertEqual(runtime["issue_id"], "P3-I01")
        self.assertEqual(runtime["hierarchy_retrieval_audit"]["issue_id"], "P3-I01")
        self.assertEqual(runtime["local_search_completion"]["status"], COMPLETED_NO_HIT)
        self.assertEqual(runtime["external_retrieval_audit"]["external_search_status"], COMPLETED_NO_HIT)
        self.assertEqual(
            runtime["external_retrieval_audit"]["local_search_completion"]["status"],
            COMPLETED_NO_HIT,
        )
        self.assertEqual(
            runtime["external_retrieval_audit"]["local_search_completion"]["completion_basis"],
            "runtime_execution",
        )
        self.assertTrue(runtime["external_retrieval_audit"]["external_no_applicable_independent_source"])
        self.assertTrue(runtime["runtime_constraints"]["external_provider_call_attempted"])
        self.assertFalse(runtime["runtime_constraints"]["external_http_called"])
        self.assertTrue(runtime["triage_binding"]["do_not_distribute_triage_state_to_unrelated_findings"])
        self.assertEqual(len(machine.provider.requests), 1)
        self.assertEqual(model_mock.call_count, 1)
        self.assertTrue(result["external_recheck"]["eligible"])
        self.assertTrue(result["external_recheck"]["attempted"])
        self.assertEqual(result["external_recheck"]["attempt_count"], 1)
        self.assertFalse(result["external_recheck"]["final_reasoning_rerun"])
        self.assertEqual(
            result["external_recheck"]["outcome"],
            "insufficient_information_preserved_after_single_recheck",
        )
        self.assertEqual(
            result["external_recheck"]["final_conclusion_types"],
            ["insufficient_information_needs_human_confirm"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
