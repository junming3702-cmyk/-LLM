import json
import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from export_review_excel import flatten_record, build_workbook, HEADERS, HANDOFF_HEADERS
from test_review_task_contract_v2 import scoped_fixture, run
from llm_abstention_gate import apply_gate
from replay_task_gate_v2 import replay


class ExportReplayTests(unittest.TestCase):
    def record(self):
        rt,f=scoped_fixture()
        f['fact_law_comparison']={'difference_summary':'保留的具体比较'}
        return {'issue_id':'SYN-ONLY','runtime_input':rt,'stage3_gate_result':run(rt,f)}

    def test_handoff_flatten_preserves_explanation(self):
        row=list(flatten_record(self.record(),include_handoff=True))[0]
        self.assertEqual(len(row),len(HEADERS)+len(HANDOFF_HEADERS))
        self.assertIn('保留的具体比较',row[17]);self.assertIn('未经核验',row[17])
        self.assertEqual(row[10],'requires_human_second_review')

    def test_excel_literal_formula_and_no_overwrite(self):
        r=self.record();r['stage3_gate_result']['response']['findings'][0]['document_excerpt']='=1+1'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'review.xlsx';build_workbook([r],p,include_handoff=True)
            w=load_workbook(p);self.assertEqual(w['Human review']['C2'].value,'=1+1')
            self.assertEqual(w['Human review']['C2'].data_type,'s');w.close()
            with self.assertRaises(FileExistsError):build_workbook([r],p,include_handoff=True)

    def test_longtext_not_silently_truncated(self):
        r=self.record();r['stage3_gate_result']['response']['findings'][0]['document_excerpt']='a'*32768
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):build_workbook([r],Path(d)/'x.xlsx',include_handoff=True)

    def test_failed_row_still_preserves_original_input(self):
        r=self.record();r['stage3_gate_result']={'blocked':True,'response':{'findings':[]}}
        row=list(flatten_record(r,include_handoff=True))[0]
        self.assertEqual(row[2],r['runtime_input']['contract_evidence']['document_excerpt'])
        self.assertEqual(row[14],r['runtime_input']['review_task_contract_v2']['question_verbatim'])

    def test_replay_preserves_inputs_and_has_no_reference(self):
        rt,f=scoped_fixture();rt.pop('review_task_contract_v2');raw={'findings':[f]}
        old=apply_gate(raw,rt,nu_boundary=True)
        record={'runtime_input':rt,'final_llm_response':{'ok':True,'finish_reason':'stop','parsed':raw},
                'post_llm_gate':old,'gated_observation':{'status':'completed','verdict':'N'}}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'inputs').mkdir();(root/'results').mkdir()
            (root/'inputs/SYN-ONLY.json').write_text(json.dumps(rt,ensure_ascii=False),encoding='utf-8')
            (root/'results/SYN-ONLY.json').write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
            result=replay(root/'inputs',root/'results',root/'new')
            self.assertEqual(result['n'],1);self.assertTrue(result['source_hashes_preserved'])
            self.assertFalse(result['prompt_effect_tested']);self.assertEqual(result['network_calls'],0)
            with self.assertRaises(FileExistsError):replay(root/'inputs',root/'results',root/'new')


if __name__=='__main__':unittest.main()
