"""Offline synthetic fixtures: no HTTP, real contracts, approvals or API keys."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
from acquire_sources import check_url, selected_sources, trusted_pdf_pages


class AcquisitionTests(unittest.TestCase):
    def test_exact_government_url(self):
        self.assertEqual(check_url('https://example.gov.cn/item?id=123'),'example.gov.cn')

    def test_reject_unsafe_or_secret_urls(self):
        for url in ['http://example.gov.cn/x','https://example.gov.cn.evil.org/x',
                    'https://user:password@example.gov.cn/x','https://example.gov.cn:444/x',
                    'https://example.gov.cn/x#fragment','https://example.gov.cn/x?api_key=x',
                    'https://127.0.0.1/x','https://example.com/x']:
            with self.subTest(url=url),self.assertRaises(ValueError):check_url(url)

    def catalogue(self):
        return {'sources':[{'source_id':'TEST-A','url':'https://example.gov.cn/a','kind':'html'},
                           {'source_id':'TEST-B','url':'https://example.gov.cn/b','kind':'pdf'}]}

    def test_subset_preserves_catalogue_order(self):
        self.assertEqual([s['source_id'] for s in selected_sources(self.catalogue(),['TEST-B'])],['TEST-B'])

    def test_unknown_selection_fails(self):
        with self.assertRaisesRegex(ValueError,'unknown_source_id'):
            selected_sources(self.catalogue(),['TEST-A','TYPO'])

    def test_duplicate_source_id_fails(self):
        cat=self.catalogue();cat['sources'].append(deepcopy(cat['sources'][0]))
        with self.assertRaisesRegex(ValueError,'invalid_sources'):selected_sources(cat)

    def test_path_traversal_id_fails(self):
        cat=self.catalogue();cat['sources'][0]['source_id']='../x'
        with self.assertRaisesRegex(ValueError,'unsafe_source_id'):selected_sources(cat)

    def test_unknown_kind_fails(self):
        cat=self.catalogue();cat['sources'][0]['kind']='executable'
        with self.assertRaisesRegex(ValueError,'unsupported_source_kind'):selected_sources(cat)

    def preflight(self):
        return {'verdict':'PASS','sha256':'abc','declared_page_count':2,
                'enumerated_page_count':2,'reader_page_count':2,'warnings':[]}

    def test_three_counts_and_hash_positive_control(self):
        self.assertTrue(trusted_pdf_pages(self.preflight(),'abc'))

    def test_zero_exit_or_verdict_alone_not_proof(self):
        for verdict in ['UNAVAILABLE','FAIL',None]:
            data=self.preflight();data['verdict']=verdict
            self.assertFalse(trusted_pdf_pages(data,'abc'))
        self.assertFalse(trusted_pdf_pages({'verdict':'PASS'},'abc'))

    def test_hash_warning_count_mismatch_fail_closed(self):
        for field,value in [('sha256','other'),('warnings',['parser repaired']),
                            ('reader_page_count',1),('declared_page_count',0),
                            ('enumerated_page_count',True)]:
            with self.subTest(field=field):
                data=self.preflight();data[field]=value
                self.assertFalse(trusted_pdf_pages(data,'abc'))


if __name__=='__main__':unittest.main()
