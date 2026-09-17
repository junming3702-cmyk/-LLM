"""Offline, append-only official-source quarantine, NOT an admitted RAG corpus.

Preserve exact normalized-snapshot spans, version anchors and instrument type.
No model, expert labels, network, human certification or C0 writes. Indexing a
candidate does not grant authority, validity, project applicability or citation
eligibility. Future C0/C1 experiments require a separately bound admission step.
"""
from collections import defaultdict
from pathlib import Path
import argparse
import hashlib
import json
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from experiment_integrity import file_digest, write_new_json
from acquire_sources import trusted_pdf_pages

CN='零〇一二三四五六七八九十百'
ARTICLE=re.compile(r'(?m)^[^\S\n]*(第(['+CN+r'\d]+)条)[^\S\n]*')
ITEM=re.compile(r'(?m)^[^\S\n]*(['+CN+r']+)、[^\S\n]*')
CHAPTER=re.compile(r'(?m)^[^\S\n]*第['+CN+r']+[章节编][^\S\n]+[^\n]*')
PAGE_NUMBER=re.compile(r'^\s*[-－]\s*\d+\s*[-－]\s*$')


def digest_text(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
def compact(text):return re.sub(r'\s+','',text)


def numeral(value):
    if value.isdecimal():return int(value)
    digits={'零':0,'〇':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9}
    total=number=0
    for c in value:
        if c in digits:number=digits[c]
        elif c in {'十','百'}:total+=(number or 1)*{'十':10,'百':100}[c];number=0
        else:raise ValueError('invalid_chinese_numeral')
    return total+number


def pdf_region(text,pages,selected):
    if not selected or sorted(set(selected))!=selected:raise ValueError('invalid_selected_pages')
    if selected!=list(range(selected[0],selected[-1]+1)):raise ValueError('noncontiguous_document_pages')
    if '\n\n'.join(p['text'] for p in pages)!=text:raise ValueError('pdf_text_pages_mismatch')
    if [p.get('physical_page') for p in pages]!=list(range(1,len(pages)+1)):
        raise ValueError('pdf_page_sequence_untrusted')
    regions=[];offset=0
    for page in pages:
        end=offset+len(page['text'])
        regions.append((offset,end,page.get('physical_page')))
        offset=end+2
    chosen=[r for r in regions if r[2] in selected]
    if len(chosen)!=len(selected) or any(p.get('page_anchor_trusted') is not True for p in pages):
        raise ValueError('pdf_page_anchor_untrusted')
    return chosen[0][0],chosen[-1][1],regions


def visible_segments(text,start,end,pdf=False):
    """Drop only blank lines and exact PDF page-number lines, retain offsets."""
    segments=[];offset=start
    for line in text[start:end].splitlines(keepends=True):
        trimmed=line.strip()
        if trimmed and not (pdf and PAGE_NUMBER.fullmatch(trimmed)):
            left=len(line)-len(line.lstrip());a=offset+left;b=a+len(trimmed)
            segments.append({'start':a,'end_exclusive':b})
        offset+=len(line)
    return segments


def split_units(text,spec,start=0,end=None,pages=None):
    end=len(text) if end is None else end
    numbered=spec.get('heading_type')=='numbered_items'
    pattern=ITEM if numbered else ARTICLE
    headers=list(pattern.finditer(text,start,end))
    numbers=[numeral(m[1] if numbered else m[2]) for m in headers]
    expected=spec.get('expected_item_count' if numbered else 'expected_article_count')
    if type(expected) is not int or numbers!=list(range(1,expected+1)):
        raise ValueError('nonunique_nonsequential_or_incomplete_headings')
    footer=None
    if spec.get('footer_prefix'):
        hit=re.search(r'(?m)^[^\S\n]*'+re.escape(spec['footer_prefix']),text[headers[-1].end():end])
        if not hit:raise ValueError('last_unit_boundary_missing')
        footer=headers[-1].end()+hit.start()
    elif spec.get('allow_end_of_snapshot'):footer=end
    else:raise ValueError('last_unit_boundary_not_registered')
    units=[]
    for i,head in enumerate(headers):
        a=head.start();b=headers[i+1].start() if i+1<len(headers) else footer
        chapter=CHAPTER.search(text,head.end(),b)
        if chapter:b=chapter.start()
        spans=visible_segments(text,a,b,bool(pages))
        value='\n'.join(text[s['start']:s['end_exclusive']] for s in spans)
        if not value:raise ValueError('empty_unit')
        physical=sorted({p for lo,hi,p in (pages or []) if p and any(s['start']<hi and s['end_exclusive']>lo for s in spans)})
        units.append({'number':numbers[i], 'heading':head[1]+('、' if numbered else ''),
            'heading_kind':'numbered_item' if numbered else 'article', 'text':value,
            'source_locator':{'kind':'normalized_snapshot_segments','segments':spans,
                'physical_pages':physical,'normalization':'trim_line_whitespace_and_drop_blank_lines'+('_and_pdf_page_number_lines' if pages else '')}})
    return units,{'preamble_span':[start,headers[0].start()],'closing_span':[footer,end]}


def terms(text):
    found=set()
    for run in re.findall(r'[\u4e00-\u9fff]+',text):found.update(run[i:i+2] for i in range(len(run)-1))
    found.update(t.lower() for t in re.findall('[A-Za-z0-9_]{2,}',text))
    return found


def build_source(folder,source,spec):
    meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    if meta['status']!='extracted':raise ValueError('source_not_extracted')
    if meta['source_id']!=source['source_id'] or meta['source_url']!=source['url']:raise ValueError('source_identity_mismatch')
    raw=folder/('source.pdf' if source['kind']=='pdf' else 'source.html')
    text=(folder/'normalized_text.txt').read_text(encoding='utf-8')
    if file_digest(raw)!=meta['raw_sha256'] or digest_text(text)!=meta['text_sha256']:
        raise ValueError('source_hash_mismatch')
    start,end,regions=0,len(text),None
    if source['kind']=='pdf':
        preflight=json.loads((folder/'pdf_read_preflight.json').read_text(encoding='utf-8'))
        if not trusted_pdf_pages(preflight,meta['raw_sha256']):raise ValueError('pdf_preflight_not_pass')
        pages=json.loads((folder/'pdf_pages.json').read_text(encoding='utf-8'))
        start,end,regions=pdf_region(text,pages,source.get('document_pages'))
    body=text[start:end]
    anchors=[source['title'],*source.get('version_anchors',[])]
    if any(compact(a) not in compact(body) for a in anchors):raise ValueError('title_or_version_anchor_missing')
    merged={**source,**spec}
    units,contexts=split_units(text,merged,start,end,regions)
    scope_ids=[];chunks=[]
    for unit in units:
        identity=source['source_id']+'|'+meta['raw_sha256']+'|'+unit['heading']+'|'+digest_text(unit['text'])
        cid='C1Q-'+hashlib.sha256(identity.encode()).hexdigest()[:20]
        chunks.append({**unit,'chunk_id':cid,'source_id':source['source_id'],'title':source['title'],
            'source_url':source['url'],'file_hash':meta['raw_sha256'],'snapshot_text_sha256':meta['text_sha256'],
            'text_sha256':digest_text(unit['text']),'instrument_type':source['instrument_type'],
            'normative_level':source.get('actual_normative_level'),'acquisition_channel':'official_public_snapshot',
            'corpus_partition':'quarantine','source_role':'verification_pending',
            'legal_evidence_eligibility':'not_admitted_candidate','independent_legal_evidence':False,
            'human_confirmed':False,'temporal_validity':'requires_project_date_and_version_crosscheck',
            'applicability_status':'not_assessed_for_any_project','scope_classification':'national_instrument_candidate',
            'version_notes':merged.get('version_notes',[]),'requires_human_review':True})
        if unit['number'] in merged.get('scope_articles',[]):scope_ids.append(cid)
    for chunk in chunks:chunk['scope_companion_candidate_ids']=scope_ids
    return chunks,{'source_id':source['source_id'],'status':'candidate_units_extracted','unit_count':len(chunks),
        'raw_sha256':meta['raw_sha256'],'text_sha256':meta['text_sha256'],'source_folder':str(folder),
        'instrument_type':source['instrument_type'],'actual_normative_level':source.get('actual_normative_level'),
        'contexts':contexts,'document_pages':source.get('document_pages'),'human_confirmed':False,
        'admitted_to_c0_or_production':False}


def main():
    p=argparse.ArgumentParser();p.add_argument('--catalogue',type=Path,required=True)
    p.add_argument('--specs',type=Path,required=True);p.add_argument('--snapshots',type=Path,nargs='+',required=True)
    p.add_argument('--c0',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('new_output_required')
    c0_hash=file_digest(a.c0);catalogue=json.loads(a.catalogue.read_text(encoding='utf-8'))
    specs=json.loads(a.specs.read_text(encoding='utf-8'))['sources'];records=[];chunks=[]
    for source in catalogue['sources']:
        sid=source['source_id'];folders=[root/sid for root in a.snapshots if (root/sid/'metadata.json').is_file()]
        record={'source_id':sid,'human_confirmed':False,'admitted_to_c0_or_production':False}
        if len(folders)!=1:record.update(status='snapshot_missing_or_ambiguous')
        elif json.loads((folders[0]/'metadata.json').read_text(encoding='utf-8'))['status']!='extracted':
            record.update(status='acquisition_or_extraction_failed',source_folder=str(folders[0]))
        elif source.get('verification_only'):record.update(status='version_crosscheck_only',source_folder=str(folders[0]))
        elif sid not in specs:record.update(status='extraction_boundary_not_registered',source_folder=str(folders[0]))
        else:
            try:part,record=build_source(folders[0],source,specs[sid]);chunks.extend(part)
            except (ValueError,KeyError,OSError) as exc:
                record.update(status='quarantined_extraction_failure',reason=str(exc) if isinstance(exc,ValueError) else type(exc).__name__)
        records.append(record)
    if file_digest(a.c0)!=c0_hash:raise ValueError('c0_changed_during_build')
    write_new_json(a.output/'source_catalogue.snapshot.json',catalogue)
    write_new_json(a.output/'extraction_specs.snapshot.json',json.loads(a.specs.read_text(encoding='utf-8')))
    write_new_json(a.output/'candidate_manifest.json',{'schema':'candidate-quarantine.v1','c0_sha256':c0_hash,
        'catalogue_sha256':file_digest(a.catalogue),'specs_sha256':file_digest(a.specs),
        'chunks':len(chunks),'production_admitted_chunks':0,'source_records':records,
        'purpose':'source preparation and retrieval diagnostics only; not the admitted C1 reasoning experiment'})
    with (a.output/'candidate_units.jsonl').open('x',encoding='utf-8') as fh:
        for row in chunks:fh.write(json.dumps(row,ensure_ascii=False)+'\n')
    postings=defaultdict(list)
    for row in chunks:
        for term in sorted(terms(row['title']+' '+row['text'])):postings[term].append(row['chunk_id'])
    write_new_json(a.output/'candidate_postings.json',dict(sorted(postings.items())))
    write_new_json(a.output/'build_integrity.json',{'c0_unchanged':file_digest(a.c0)==c0_hash,
        'candidate_units_sha256':file_digest(a.output/'candidate_units.jsonl'),
        'candidate_index_sha256':file_digest(a.output/'candidate_postings.json'),'provider_calls':0,
        'new_human_approvals':0,'corpus_merge_performed':False})
    print(json.dumps({'candidate_units':len(chunks),'sources':records},ensure_ascii=False))


if __name__=='__main__':main()
