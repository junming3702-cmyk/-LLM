import unittest
from copy import deepcopy
from discovery import admit_candidate, canonical_hash, digest
from freeze_admission import build_review
from test_discovery import fixture_packet, RAW, SOURCE, CONTEXT

class ScopedApprovalTests(unittest.TestCase):
    def fixtures(self):
        spec={'default_context':CONTEXT,'tasks':[{'id':'CASE-01'}]}
        approval={'scope_id':'FIXTURE-ONLY','task_spec_sha256':canonical_hash(spec),
                  'reviewer_id':'SYNTHETIC-NOT-A-HUMAN','recorded_at':'2026-09-17T00:00:00+00:00','user_statement':'SYNTHETIC TEST APPROVAL'}
        p=fixture_packet()
        review=build_review(p,approval,spec,SOURCE)
        context={**CONTEXT,'scope_id':approval['scope_id'],'task_spec_sha256':approval['task_spec_sha256'],'issue_id':'CASE-01'}
        snapshot=(RAW,{'source_url':SOURCE['url'],'encoding':'utf-8','raw_sha256':digest(RAW)})
        return p,review,context,snapshot

    def test_scoped_admission(self):
        self.assertTrue(admit_candidate(*self.fixtures())['independent_legal_evidence'])

    def test_no_fabricated_statutory_dates(self):
        p,r,c,s=self.fixtures()
        self.assertIsNone(r['statutory_effective_date'])
        self.assertEqual(r['valid_from'],r['verified_through'])

    def test_changed_scope(self):
        p,r,c,s=self.fixtures();c['scope_id']='other'
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

    def test_changed_spec(self):
        p,r,c,s=self.fixtures();c['task_spec_sha256']='other'
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

    def test_new_case(self):
        p,r,c,s=self.fixtures();c['issue_id']='new'
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

    def test_context_cannot_be_rewritten_under_same_id(self):
        p,r,c,s=self.fixtures();c['jurisdiction']='广东省'
        self.assertIn('registered_project_context_mismatch',admit_candidate(p,r,c,s)['reasons'])

    def test_future_not_approved(self):
        p,r,c,s=self.fixtures();c['as_of']='2026-09-18'
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

    def test_missing_scope(self):
        p,r,c,s=self.fixtures();c.pop('scope_id')
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

    def test_malformed_scope(self):
        p,r,c,s=self.fixtures();r['approval_scope']=None
        self.assertIn('invalid_approval_scope',admit_candidate(p,r,c,s)['reasons'])

    def test_empty_allowed_cases(self):
        p,r,c,s=self.fixtures();r['approval_scope']['allowed_issue_ids']=[]
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

    def test_empty_context_bindings(self):
        p,r,c,s=self.fixtures();r['approval_scope']['context_hashes']={}
        self.assertFalse(admit_candidate(p,r,c,s)['independent_legal_evidence'])

if __name__=='__main__': unittest.main()
