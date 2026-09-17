"""Read-only segment/index/provenance check; writes only a new validation report."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_candidate_index import digest_text,terms
from acquire_sources import trusted_pdf_pages
from experiment_integrity import file_digest,write_new_json,utc_now


def validate_rows(rows,source_texts,postings,source_records):
    ids={r['chunk_id'] for r in rows}
    if len(ids)!=len(rows):raise ValueError('duplicate_candidate_id')
    expected=defaultdict(list);groups=defaultdict(list)
    for row in rows:
        if (row.get('human_confirmed') is not False or row.get('independent_legal_evidence') is not False
            or row.get('corpus_partition')!='quarantine' or row.get('legal_evidence_eligibility')!='not_admitted_candidate'):
            raise ValueError('candidate_eligibility_escalation')
        sid=row['source_id'];text=source_texts[sid];record=source_records[sid]
        if row['file_hash']!=record['raw_sha256'] or row['snapshot_text_sha256']!=digest_text(text):
            raise ValueError('source_binding_changed')
        if row.get('normative_level')!=record.get('actual_normative_level') or row['instrument_type']!=record['instrument_type']:
            raise ValueError('instrument_type_or_level_changed')
        segments=row['source_locator']['segments'];previous=-1
        for s in segments:
            lo,hi=s['start'],s['end_exclusive']
            if not (type(lo) is int and type(hi) is int and 0<=lo<hi<=len(text) and lo>=previous):
                raise ValueError('invalid_or_overlapping_source_segments')
            previous=hi
        recovered='\n'.join(text[s['start']:s['end_exclusive']] for s in segments)
        if recovered!=row['text'] or digest_text(recovered)!=row['text_sha256']:
            raise ValueError('quote_locator_roundtrip_failed')
        if not set(row['scope_companion_candidate_ids'])<=ids:raise ValueError('missing_scope_companion')
        groups[sid].append(row)
        for term in sorted(terms(row['title']+' '+row['text'])):expected[term].append(row['chunk_id'])
    if set(groups)!=set(source_records):raise ValueError('whole_source_missing_or_unregistered')
    if dict(expected)!=postings:raise ValueError('postings_mismatch')
    for sid,group in groups.items():
        if [r['number'] for r in group]!=list(range(1,len(group)+1)):raise ValueError('unit_order_or_gap')
        group_ids={r['chunk_id'] for r in group}
        if any(not set(r['scope_companion_candidate_ids'])<=group_ids for r in group):
            raise ValueError('cross_instrument_scope_companion')
        if len(group)!=source_records[sid]['unit_count']:raise ValueError('source_count_mismatch')
    return {'units_checked':len(rows),'source_counts':dict(Counter(r['source_id'] for r in rows)),
        'all_segment_roundtrips_exact':True,'index_recomputed_matches':True,'all_candidates_ineligible':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True)
    p.add_argument('--c0',type=Path,required=True);p.add_argument('--scope-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=a.scope_root.resolve(strict=True)
    manifest=json.loads((a.package/'candidate_manifest.json').read_text(encoding='utf-8'))
    integrity=json.loads((a.package/'build_integrity.json').read_text(encoding='utf-8'))
    rows=[json.loads(line) for line in (a.package/'candidate_units.jsonl').read_text(encoding='utf-8').splitlines() if line]
    postings=json.loads((a.package/'candidate_postings.json').read_text(encoding='utf-8'))
    if len(rows)!=manifest['chunks']:raise ValueError('manifest_unit_count_mismatch')
    if file_digest(a.c0)!=manifest['c0_sha256']:raise ValueError('c0_hash_changed')
    for name,key in [('candidate_units.jsonl','candidate_units_sha256'),('candidate_postings.json','candidate_index_sha256')]:
        if file_digest(a.package/name)!=integrity[key]:raise ValueError('package_hash_changed')
    texts={};records={}
    for record in manifest['source_records']:
        if record['status']!='candidate_units_extracted':continue
        sid=record['source_id'];folder=Path(record['source_folder']).resolve(strict=True)
        if not folder.is_relative_to(root):raise ValueError('source_outside_scope')
        raw=folder/('source.pdf' if (folder/'source.pdf').is_file() else 'source.html')
        if file_digest(raw)!=record['raw_sha256']:raise ValueError('raw_source_changed')
        texts[sid]=(folder/'normalized_text.txt').read_text(encoding='utf-8');records[sid]=record
        if record.get('document_pages'):
            preflight=json.loads((folder/'pdf_read_preflight.json').read_text(encoding='utf-8'))
            if not trusted_pdf_pages(preflight,record['raw_sha256']):raise ValueError('pdf_preflight_no_longer_valid')
            page_rows=json.loads((folder/'pdf_pages.json').read_text(encoding='utf-8'))
            if [p.get('physical_page') for p in page_rows]!=list(range(1,len(page_rows)+1)):
                raise ValueError('pdf_page_sequence_changed')
            if '\n\n'.join(p['text'] for p in page_rows)!=texts[sid]:raise ValueError('pdf_page_text_changed')
            offsets=[];offset=0
            for page in page_rows:
                offsets.append((offset,offset+len(page['text']),page['physical_page']));offset+=len(page['text'])+2
            for row in [r for r in rows if r['source_id']==sid]:
                actual=sorted({num for lo,hi,num in offsets if any(s['start']<hi and s['end_exclusive']>lo for s in row['source_locator']['segments'])})
                if actual!=row['source_locator']['physical_pages'] or not set(actual)<=set(record['document_pages']):
                    raise ValueError('pdf_locator_outside_selected_attachment')
    result=validate_rows(rows,texts,postings,records)
    c0ids={json.loads(line)['chunk_id'] for line in a.c0.read_text(encoding='utf-8').splitlines() if line}
    if c0ids&{r['chunk_id'] for r in rows}:raise ValueError('candidate_c0_id_collision')
    result.update(checked_at=utc_now(),c0_unchanged=True,c0_chunks=len(c0ids),passed=True,
        production_admitted_chunks=0,provider_calls=0,candidate_units_sha256=integrity['candidate_units_sha256'])
    write_new_json(a.output,result);print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
