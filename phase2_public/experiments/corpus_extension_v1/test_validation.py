from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_candidate_index import digest_text,terms
from validate_candidate_index import validate_rows


class CandidateValidationTests(unittest.TestCase):
    def fixture(self):
        text='第一条 示例条件。'
        row={'chunk_id':'Q1','source_id':'S','title':'示例','number':1,'text':text,
            'text_sha256':digest_text(text),'snapshot_text_sha256':digest_text(text),'file_hash':'hash',
            'source_locator':{'segments':[{'start':0,'end_exclusive':len(text)}]},
            'scope_companion_candidate_ids':['Q1'],'corpus_partition':'quarantine',
            'independent_legal_evidence':False,'human_confirmed':False,
            'legal_evidence_eligibility':'not_admitted_candidate',
            'normative_level':None,'instrument_type':'administrative_normative_document'}
        records={'S':{'raw_sha256':'hash','unit_count':1,'actual_normative_level':None,
            'instrument_type':'administrative_normative_document'}}
        return [row],{'S':text},{k:['Q1'] for k in terms('示例 '+text)},records

    def test_valid_roundtrip(self):
        self.assertTrue(validate_rows(*self.fixture())['all_segment_roundtrips_exact'])

    def test_granted_independence_rejected(self):
        args=self.fixture();args[0][0]['independent_legal_evidence']=True
        with self.assertRaisesRegex(ValueError,'escalation'):validate_rows(*args)

    def test_wrong_quote_or_locator_rejected(self):
        for kind in ['quote','locator']:
            args=self.fixture()
            if kind=='quote':args[0][0]['text']='不同原文'
            else:args[0][0]['source_locator']['segments'][0]['start']=1
            with self.assertRaisesRegex(ValueError,'roundtrip'):validate_rows(*args)

    def test_notice_cannot_become_department_regulation(self):
        args=self.fixture();args[0][0]['normative_level']='Level 3'
        with self.assertRaisesRegex(ValueError,'level_changed'):validate_rows(*args)

    def test_missing_whole_source_detected(self):
        args=self.fixture();args[3]['S2']=deepcopy(args[3]['S'])
        with self.assertRaisesRegex(ValueError,'whole_source'):validate_rows(*args)

    def test_posting_tamper_detected(self):
        args=self.fixture();args[2]['fake']=['Q1']
        with self.assertRaisesRegex(ValueError,'postings'):validate_rows(*args)


if __name__=='__main__':unittest.main()
