import json
from pathlib import Path
import unittest
from prepare_execution import compile_inputs, FACTS
from discovery import canonical_hash

class FactInputTests(unittest.TestCase):
    def spec(self):return json.loads((Path(__file__).parent/'p3_tasks.pending.json').read_text(encoding='utf-8'))
    def approval(self,spec):return {'task_spec_sha256':canonical_hash(spec),'status':'all_listed_articles_admitted','scope_id':'TEST-SYNTHETIC-ONLY'}
    def test_references_labels_and_test_instructions_excluded(self):
        spec=self.spec();rows,fixtures,contexts,audit=compile_inputs(spec,self.approval(spec))
        self.assertEqual(len(rows),30)
        self.assertEqual(sum(f['engineering_only'] for f in fixtures),8)
        text=json.dumps(rows,ensure_ascii=False)
        for banned in ('proposed_outcome','references','must_abstain','candidate_references','requires_human_legal_review','应显示访问失败','不得显示依法合规','忽略闸门'):
            self.assertNotIn(banned,text)
        self.assertEqual(len(audit),30)
        self.assertEqual(contexts['P3-12']['as_of'],'2018-06-01')
    def test_missing_context_not_invented(self):
        spec=self.spec();rows,*_=compile_inputs(spec,self.approval(spec));by={r['issue_id']:r for r in rows}
        self.assertIsNone(by['P3-17']['runtime_project_context']['project_location']['province'])
        self.assertEqual(by['P3-18']['runtime_project_context']['project_type'],'unknown')
        self.assertIsNone(by['P3-20']['runtime_project_context']['review_as_of'])
    def test_scope_change_rejected(self):
        spec=self.spec();approval=self.approval(spec);spec['default_context']['jurisdiction']='altered'
        with self.assertRaises(ValueError):compile_inputs(spec,approval)
    def test_unknown_task_cannot_inherit_transform(self):
        spec=self.spec();spec['tasks'][0]['id']='outside'
        with self.assertRaises(ValueError):compile_inputs(spec,self.approval(spec))

if __name__=='__main__':unittest.main()
