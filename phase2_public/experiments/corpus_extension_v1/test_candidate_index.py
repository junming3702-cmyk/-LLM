from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_candidate_index import (numeral,split_units,pdf_region,visible_segments,
    build_source,digest_text)
from experiment_integrity import file_digest


class CandidateExtractionTests(unittest.TestCase):
    def test_chinese_numerals(self):
        for raw,expected in [('一',1),('十',10),('二十三',23),('六十二',62),('八十八',88),('一百零一',101),('79',79)]:
            self.assertEqual(numeral(raw),expected)

    def text(self):return '示例规章\n第一章 总则\n第一条 条件甲且条件乙。\n例外不能省略。\n第二章 义务\n第二条 应当说明。\n本条还有下一款。\n责任编辑：测试\n导航'
    def spec(self):return {'expected_article_count':2,'footer_prefix':'责任编辑：'}

    def test_full_conditions_and_multiline_final(self):
        chunks,_=split_units(self.text(),self.spec())
        self.assertIn('条件甲且条件乙',chunks[0]['text'])
        self.assertIn('例外不能省略',chunks[0]['text'])
        self.assertIn('本条还有下一款',chunks[1]['text'])
        self.assertNotIn('第二章',chunks[0]['text'])
        self.assertNotIn('责任编辑',chunks[1]['text'])

    def test_exact_segment_roundtrip(self):
        text=self.text();chunks,_=split_units(text,self.spec())
        for row in chunks:
            recovered='\n'.join(text[s['start']:s['end_exclusive']] for s in row['source_locator']['segments'])
            self.assertEqual(recovered,row['text'])

    def test_duplicate_or_gap_never_silently_repaired(self):
        for text in [self.text()+'\n第一条 别的文件。',self.text().replace('第二条','第三条')]:
            with self.assertRaisesRegex(ValueError,'headings'):split_units(text,self.spec())

    def test_last_boundary_required(self):
        for spec in [{'expected_article_count':2},{'expected_article_count':2,'footer_prefix':'不存在'}]:
            with self.assertRaisesRegex(ValueError,'boundary'):split_units(self.text(),spec)

    def test_no_heading_space_still_detected(self):
        rows,_=split_units('第一条文本。\n第二条文本。',{'expected_article_count':2,'allow_end_of_snapshot':True})
        self.assertEqual(len(rows),2)

    def test_numbered_item_not_fabricated_as_article(self):
        rows,_=split_units('一、甲。\n二、乙。\n署名',{'heading_type':'numbered_items','expected_item_count':2,'footer_prefix':'署名'})
        self.assertEqual(rows[1]['heading'],'二、')
        self.assertEqual(rows[1]['heading_kind'],'numbered_item')

    def pages(self):
        return [{'physical_page':1,'page_anchor_trusted':True,'text':'一、地方条件。\n二、地方规则。'},
                {'physical_page':2,'page_anchor_trusted':True,'text':'全国文件\n一、中央条件且例外。\n- 2 -'},
                {'physical_page':3,'page_anchor_trusted':True,'text':'二、中央义务。\n署名'}]

    def test_pdf_attachment_keeps_physical_pages_not_cover_scope(self):
        pages=self.pages();text='\n\n'.join(p['text'] for p in pages)
        start,end,regions=pdf_region(text,pages,[2,3])
        rows,_=split_units(text,{'heading_type':'numbered_items','expected_item_count':2,'footer_prefix':'署名'},start,end,regions)
        self.assertEqual(rows[0]['source_locator']['physical_pages'],[2])
        self.assertEqual(rows[1]['source_locator']['physical_pages'],[3])
        self.assertNotIn('地方',str(rows));self.assertNotIn('- 2 -',rows[0]['text'])
        self.assertIn('条件且例外',rows[0]['text'])

    def test_untrusted_pdf_pages_blocked(self):
        pages=self.pages();pages[0]['page_anchor_trusted']=False
        with self.assertRaisesRegex(ValueError,'untrusted'):
            pdf_region('\n\n'.join(p['text'] for p in pages),pages,[2,3])

    def test_noncontiguous_pdf_region_blocked(self):
        with self.assertRaises(ValueError):pdf_region('',self.pages(),[1,3])

    def test_pdf_text_mismatch_blocked(self):
        with self.assertRaisesRegex(ValueError,'mismatch'):pdf_region('wrong',self.pages(),[2,3])

    def test_bare_numeric_legal_value_not_removed_as_page_number(self):
        text='第一条 上限为\n3\n个百分点。\n- 2 -'
        spans=visible_segments(text,0,len(text),pdf=True)
        recovered='\n'.join(text[s['start']:s['end_exclusive']] for s in spans)
        self.assertIn('\n3\n',recovered);self.assertNotIn('- 2 -',recovered)

    def test_reordered_page_labels_blocked(self):
        pages=self.pages();pages[0]['physical_page']=3
        with self.assertRaisesRegex(ValueError,'sequence'):
            pdf_region('\n\n'.join(p['text'] for p in pages),pages,[2,3])

    def fixture(self,folder):
        text='示例通知 2020版\n第一条 含条件的原文。\n结束'
        (folder/'source.html').write_bytes(b'<p>synthetic</p>')
        (folder/'normalized_text.txt').write_text(text,encoding='utf-8')
        source={'source_id':'TEST','url':'https://example.gov.cn/x','kind':'html','title':'示例通知',
            'version_anchors':['2020版'],'expected_article_count':1,
            'instrument_type':'administrative_normative_document','actual_normative_level':None}
        meta={'status':'extracted','source_id':'TEST','source_url':source['url'],
            'raw_sha256':file_digest(folder/'source.html'),'text_sha256':digest_text(text)}
        (folder/'metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        return source,{'footer_prefix':'结束','scope_articles':[1]}

    def test_candidate_does_not_grant_authority_or_human_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source,spec=self.fixture(folder);rows,record=build_source(folder,source,spec)
            self.assertFalse(rows[0]['independent_legal_evidence'])
            self.assertFalse(rows[0]['human_confirmed'])
            self.assertIsNone(rows[0]['normative_level'])
            self.assertEqual(rows[0]['corpus_partition'],'quarantine')
            self.assertFalse(record['admitted_to_c0_or_production'])

    def test_changed_snapshot_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source,spec=self.fixture(folder)
            (folder/'normalized_text.txt').write_text('tampered',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'hash_mismatch'):build_source(folder,source,spec)

    def test_wrong_version_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);source,spec=self.fixture(folder);source['version_anchors']=['2099版']
            with self.assertRaisesRegex(ValueError,'version_anchor_missing'):build_source(folder,source,spec)


if __name__=='__main__':unittest.main()
