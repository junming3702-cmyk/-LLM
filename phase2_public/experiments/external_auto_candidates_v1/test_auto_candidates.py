"""Offline engineering fixtures only, not legal evaluation cases."""
from copy import deepcopy
import unittest
from auto_candidates import bridge_auto_candidate
from external_auto_candidate_policy import machine_candidate_admitted, seal_source
from discovery import digest, discover_articles, html_text
from test_discovery import fixture_packet, RAW, SOURCE, CONTEXT
from llm_abstention_gate import _canonicalize_evidence
from external_fallback_v2 import is_usable_legal_basis
from scope_boundary_policy import ScopePolicy, prepare_runtime


class AutoCandidatesTests(unittest.TestCase):
    def setUp(self):
        self.packet = fixture_packet(); self.source = deepcopy(SOURCE)
        self.context = {**CONTEXT, 'issue_id': 'FIXTURE-01'}
        self.runtime = {'issue_id': 'FIXTURE-01', 'project_context': {
            'project_type': '学校升级改造施工', 'project_location': {'province': '四川省', 'human_confirmation': 'confirmed'}},
            'retrieved_legal_evidence': []}
        self.snapshot = (RAW, {'source_url': SOURCE['url'], 'encoding': 'utf-8',
                              'raw_sha256': digest(RAW), 'fetched_at': '2026-09-17T00:00:00Z'})

    def bridge(self):
        return bridge_auto_candidate(self.packet, self.source, self.context, self.snapshot, self.runtime)

    def test_machine_admission_without_human_attestation(self):
        row, audit = self.bridge()
        self.assertEqual(audit['status'], 'auto_admitted_supplement')
        self.assertEqual(row['human_confirmation_status'], 'not_requested')
        self.assertFalse(row['independent_legal_evidence'])
        self.assertTrue(machine_candidate_admitted(row, self.runtime))
        self.assertFalse(is_usable_legal_basis(row))

    def test_opt_in_keeps_citation_without_fake_effective_date(self):
        row, _ = self.bridge(); self.runtime['retrieved_legal_evidence'] = [row]
        finding = {'legal_evidence': [{'chunk_id': row['chunk_id'], 'independent_legal_evidence': True}]}
        retained, invalid, only = _canonicalize_evidence(finding, self.runtime, [], external_auto_candidates=True)
        self.assertFalse(invalid); self.assertTrue(only); self.assertEqual(len(retained), 1)
        self.assertFalse(retained[0]['independent_legal_evidence'])
        self.assertIsNone(retained[0]['effective_date'])

    def test_default_gate_unchanged(self):
        row, _ = self.bridge(); self.runtime['retrieved_legal_evidence'] = [row]
        _, invalid, _ = _canonicalize_evidence({'legal_evidence': [{'chunk_id': row['chunk_id']}]}, self.runtime, [])
        self.assertTrue(invalid)

    def test_quote_tamper_rejected(self):
        self.packet['legal_quote'] += '篡改'
        self.assertIsNone(self.bridge()[0])

    def test_raw_snapshot_tamper_rejected(self):
        self.snapshot = (RAW + b'corrupt', self.snapshot[1])
        self.assertIsNone(self.bridge()[0])

    def test_url_binding_rejected(self):
        self.source['url'] = 'https://example.gov.cn/other'
        self.assertIsNone(self.bridge()[0])

    def test_version_anchor_rechecked(self):
        self.source['version_anchors'] = ['NOT PRESENT']
        self.assertIsNone(self.bridge()[0])

    def test_historical_source_rejected(self):
        self.source['temporal_status'] = 'historical_only_not_for_current_admission'
        self.assertIsNone(self.bridge()[0])

    def test_project_type_mismatch_rejected(self):
        self.context['project_type'] = 'services'
        self.assertIsNone(self.bridge()[0])

    def test_context_mutation_breaks_binding(self):
        row, _ = self.bridge(); self.runtime['project_context']['project_type'] = 'services'
        self.assertFalse(machine_candidate_admitted(row, self.runtime))

    def test_independence_cannot_be_promoted_even_by_reseal(self):
        row, _ = self.bridge(); row['independent_legal_evidence'] = True
        seal_source(row, self.runtime)
        self.assertFalse(machine_candidate_admitted(row, self.runtime))

    def test_local_matching_survives_geo_annotation(self):
        self.source.update(geographic_scope='四川省', actual_normative_level='Level 4')
        self.packet = discover_articles(self.source, html_text(RAW), digest(RAW), ['资格'])[0][0]
        row, _ = self.bridge(); self.runtime['retrieved_legal_evidence'] = [row]
        prepared = prepare_runtime(self.runtime, ScopePolicy.for_arm('geo_task', {}))
        self.assertEqual(len(prepared['retrieved_legal_evidence']), 1)
        self.assertTrue(machine_candidate_admitted(prepared['retrieved_legal_evidence'][0], prepared))
        self.context['jurisdiction'] = '天津市'
        self.assertIsNone(self.bridge()[0])


if __name__ == '__main__': unittest.main()
