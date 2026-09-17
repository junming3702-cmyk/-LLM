"""Fictional engineering fixtures; no human or real-project results."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from controlled_execution import (ReadOnlySnapshots, bridge_candidate, compile_controls,
    constrain_catalogue, fault_probe, replay_discovery, replay_fixed_access,
    source_matched_access_entries)
from discovery import SnapshotStore, digest, INSUFFICIENT, safe_url
from test_discovery import SOURCE, RAW, CONTEXT, fixture_packet, fixture_review


class ControlledExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.meta={'encoding':'utf-8','source_url':SOURCE['url'],'raw_sha256':digest(RAW)}
        SnapshotStore(self.temp.name).put(SOURCE['url'],RAW,self.meta)
        self.store=ReadOnlySnapshots([self.temp.name])
        self.packet=fixture_packet()
        self.review=fixture_review(self.packet)
        self.control={'candidate_allowlist':None,'source_allowlist':None,'fault':None}

    def test_no_reference_answer_consumption(self):
        a={'tasks':[{'id':'a','category':'negative','references':['secret'],'proposed_outcome':'answer'}]}
        b=copy.deepcopy(a);b['tasks'][0].update(references=['changed'],proposed_outcome='changed')
        self.assertEqual(compile_controls(a),compile_controls(b))

    def test_wrong_regime_candidate_constrained_too(self):
        spec=json.loads((Path(__file__).parent/'p3_tasks.pending.json').read_text('utf-8'))
        c=compile_controls(spec)
        self.assertEqual(c['P3-14']['source_allowlist'],['SAC-GOVPROC-2014'])
        self.assertEqual(sum(x['engineering_only'] for x in c.values()),8)

    def test_article_constraint_before_top_k(self):
        c={**self.control,'candidate_allowlist':['FIXTURE:第二条']}
        result=replay_discovery(['资格','分包'],CONTEXT,[SOURCE],self.store,{},c)
        self.assertEqual([x['article'] for x in result['candidates']],['第二条'])

    def test_source_constraint_before_routing(self):
        with self.assertRaisesRegex(ValueError,'not_in_catalogue'):
            constrain_catalogue([SOURCE],{'source_allowlist':['unknown']})

    def test_supplement_never_replaced_with_national_law(self):
        self.assertEqual(constrain_catalogue([SOURCE],{'source_class_hint':'supplement_only'}),[])

    def test_no_mutation_of_source_controls(self):
        old=copy.deepcopy(SOURCE)
        replay_discovery(['资格'],CONTEXT,[SOURCE],self.store,{},self.control)
        self.assertEqual(old,SOURCE)

    def test_readonly_snapshots(self):
        root=Path(self.temp.name)
        before={p.name:p.read_bytes() for p in root.iterdir()}
        self.assertEqual(self.store.get(SOURCE['url'])[0],RAW)
        self.assertEqual(before,{p.name:p.read_bytes() for p in root.iterdir()})

    def test_conflicting_snapshots_denied(self):
        other=Path(self.temp.name)/'other'
        raw=RAW+b' changed'
        SnapshotStore(other).put(SOURCE['url'],raw,{**self.meta,'raw_sha256':digest(raw)})
        with self.assertRaisesRegex(ValueError,'conflicting_frozen'):
            ReadOnlySnapshots([self.temp.name,other]).get(SOURCE['url'])

    def test_bridge_whitelist_no_reviewers_or_gold(self):
        packet={**self.packet,'applies_to_tasks':['sensitive-reference'],'rationale':'hidden'}
        row,check=bridge_candidate(packet,self.review,CONTEXT,(RAW,self.meta))
        self.assertTrue(check['admitted'])
        text=json.dumps(row,ensure_ascii=False)
        for forbidden in ('reviewer_id','SYNTHETIC-ENGINEERING-NOT-HUMAN','applies_to_tasks','sensitive-reference','rationale'):
            self.assertNotIn(forbidden,text)
        self.assertIsNone(row['statutory_effective_date'])
        self.assertEqual(row['normative_level'],'Level 1')

    def test_bridge_rechecks_hash_not_packet_claim(self):
        p={**self.packet,'independent_legal_evidence':True,'article_sha256':'bad'}
        row,audit=bridge_candidate(p,self.review,CONTEXT,(RAW,self.meta))
        self.assertIsNone(row);self.assertFalse(audit['admitted'])

    def test_supplement_not_independent_even_if_sidecar_confirmed(self):
        row,check=bridge_candidate({**self.packet,'instrument_type':'practice_note'},self.review,CONTEXT,(RAW,self.meta))
        self.assertIsNone(row)
        self.assertIn('non_legal_instrument_not_independent',check['reasons'])

    def test_runtime_gate_accepts_bridge_but_never_confirms_verdict(self):
        from external_fallback_v2 import is_usable_legal_basis
        from llm_abstention_gate import _external_evidence_is_pending
        row,_=bridge_candidate(self.packet,self.review,CONTEXT,(RAW,self.meta))
        self.assertTrue(is_usable_legal_basis(row));self.assertFalse(_external_evidence_is_pending(row))
        self.assertNotIn('claim_confirmation_validation',row)

    def test_bridge_refuses_unapproved_context(self):
        row,_=bridge_candidate(self.packet,self.review,{**CONTEXT,'as_of':'2018-01-01'},(RAW,self.meta))
        self.assertIsNone(row)

    def test_legacy_no_fabricated_article(self):
        r=replay_fixed_access(['资格'],CONTEXT,[SOURCE],self.store,[{'base_url':SOURCE['url']}],self.control)
        self.assertFalse(r['admitted_evidence'])
        self.assertEqual(r['sources'][0]['status'],'lookup_only_missing_article_target_fields')
        self.assertEqual(r['final_conclusion'],INSUFFICIENT)

    def test_fixed_manifest_targets_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError,'now_has_targets'):
            replay_fixed_access(['资格'],CONTEXT,[SOURCE],self.store,[{'article':'第一条'}],self.control)

    def test_source_matched_control_same_urls_not_historical(self):
        self.assertEqual(source_matched_access_entries([SOURCE])[0]['base_url'],SOURCE['url'])

    def test_one_shot_and_no_trigger(self):
        r=replay_discovery(['资格'],CONTEXT,[SOURCE],self.store,{},self.control,prior_attempts=1)
        self.assertEqual(r['status'],'one_shot_already_used')
        r=replay_discovery(['资格'],CONTEXT,[SOURCE],self.store,{},self.control,preliminary='requires_human_legal_review')
        self.assertEqual(r['status'],'not_triggered')

    def test_private_destination_no_dns_or_network(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('must not resolve')):
            for url in ('https://127.0.0.1/law','https://[::1]/law','https://10.1.2.3/law','https://localhost/law','https://host.local/law'):
                with self.assertRaisesRegex(ValueError,'non_public'): safe_url(url)

    def test_all_faults_exercised_with_positive_control(self):
        from controlled_execution import FAULTS
        # Fictional source article contains 资格, not the public corpus terms.
        p={**self.packet,'matched_public_terms':['资格']}
        for fault in FAULTS:
            with self.subTest(fault=fault):
                r=fault_probe(fault,SOURCE,RAW,self.meta,p,self.review,CONTEXT)
                self.assertTrue(r['positive_control_passed'])
                self.assertTrue(r['denial_passed'])
                self.assertEqual(r['actual_network_requests'],0)
                self.assertFalse(r['legal_accuracy_measured'])

    def test_invalid_positive_control_cannot_count_as_fault_pass(self):
        with self.assertRaisesRegex(ValueError,'positive_control_not_eligible'):
            fault_probe('locator_mismatch',SOURCE,RAW,self.meta,self.packet,None,CONTEXT)

    def test_legacy_p1_snapshot_readonly_and_bound(self):
        root=Path(self.temp.name)/'p1';(root/'snapshots').mkdir(parents=True)
        rec={'source_id':'FIXTURE','source_url':SOURCE['url'],'status':'fetched',**self.meta}
        (root/'report.json').write_text(json.dumps({'sources':[rec]}),encoding='utf-8')
        (root/'snapshots/FIXTURE.html').write_bytes(RAW)
        (root/'snapshots/FIXTURE.metadata.json').write_text(json.dumps(self.meta),encoding='utf-8')
        self.assertEqual(ReadOnlySnapshots([self.temp.name],[root]).get(SOURCE['url'])[0],RAW)
        (root/'snapshots/FIXTURE.html').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'p1_snapshot_hash_mismatch'):
            ReadOnlySnapshots([self.temp.name],[root]).get(SOURCE['url'])


if __name__=='__main__':unittest.main()
