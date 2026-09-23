import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gate import context_errors
import online_validation as online


class OnlineValidationTests(unittest.TestCase):
    def test_eight_contexts_valid(self):
        for i in range(1,9):
            self.assertEqual([],context_errors(online.synthetic_context(f'S{i:02}')))

    def test_requests_do_not_contain_answer_key(self):
        body=online.body_for(online.synthetic_context('S03'))
        self.assertNotIn('synthetic_expectations',json.dumps(body))
        self.assertEqual(2,len(body['messages']))
        self.assertEqual('deepseek-v4-flash',body['model'])

    def test_missing_scope_metadata_never_promoted(self):
        ctx=online.synthetic_context('S06')
        self.assertEqual('unknown',ctx['laws'][0]['applicability_status'])

    def test_prepare_is_offline_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td, patch('socket.socket.connect',side_effect=AssertionError('network')):
            out=Path(td)/'new'
            online.prepare(out,None)
            lock=json.loads((out/'lock.json').read_text(encoding='utf-8'))
            self.assertEqual(8,lock['max_calls'])
            self.assertEqual(0,lock['automatic_retries'])
            for case in lock['order']:
                request=json.loads((out/'requests'/f'{case}.json').read_text(encoding='utf-8'))
                self.assertEqual({'case_id','body','context'},set(request))
            with self.assertRaises(FileExistsError): online.prepare(out,None)

    def test_law_metadata_and_snapshot_provenance(self):
        ctx=online.synthetic_context('S01')
        old={'scope_spec':{'question_verbatim':ctx['task']['question'],
             'review_mode':ctx['task']['review_mode'],'excluded_dependencies':ctx['task']['excluded_dependencies'],
             'required_claims':ctx['task']['required_claims']},
             'runtime_input':{'contract_evidence':{'document_excerpt':'合成脱敏摘录'},
             'retrieved_legal_evidence':[{'chunk_id':'L1','file_hash':'a'*64,'article':'test1',
                'legal_quote':'虚构规则','citation_ready':True,'independent_legal_evidence':True,
                'applicability_status':'not_explicitly_stated'}]}}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'input.json';online.write(path,old)
            converted,audit=online.legacy_snapshot(path)
            self.assertEqual([],context_errors(converted))
            self.assertEqual('unknown',converted['laws'][0]['temporal_status'])
            self.assertEqual('unknown',converted['laws'][0]['applicability_status'])
            self.assertFalse(audit['physical_source_location_verified'])
            self.assertTrue(converted['sources'][0]['locator'].startswith('INPUT-SNAPSHOT-ONLY:'))


if __name__=='__main__': unittest.main()
