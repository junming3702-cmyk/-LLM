"""Bounded exact-URL public-law snapshots for an isolated corpus candidate.

No private input, secret, expert file, LLM or corpus update. Failed downloads
stay failures. Parsed source content is data, never tool instructions.
"""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler
import argparse
import hashlib
import ipaddress
import json
import multiprocessing as mp
import re
import socket
import ssl
import sys
import time

PACKAGE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PACKAGE/'src'))
sys.path.insert(0,str(PACKAGE/'experiments/external_verification_p1_v1'))
from experiment_integrity import file_digest, write_new_json
from verification import NoRedirect, html_text

MAX_BYTES=5_000_000


def check_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None,443):
        raise ValueError('unsafe_url')
    if not (p.hostname=='gov.cn' or p.hostname.endswith('.gov.cn')):
        raise ValueError('non_government_host')
    if re.search(r'(?i)(api.?key|secret|password|token|authorization)',p.query):
        raise ValueError('credential_query_rejected')
    return p.hostname


def fetch_worker(conn,source):
    try:
        host=check_url(source['url'])
        addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
        if not addresses or not all(ipaddress.ip_address(x[4][0]).is_global for x in addresses):
            raise ValueError('non_public_destination')
        opener=build_opener(NoRedirect(),HTTPSHandler(context=ssl.create_default_context()))
        request=Request(source['url'],headers={'User-Agent':'PublicLawCorpusAudit/1.0'})
        with opener.open(request,timeout=20) as response:
            ct=response.headers.get_content_type()
            allowed={'application/pdf','application/octet-stream'} if source['kind']=='pdf' else {'text/html','application/xhtml+xml'}
            if ct not in allowed:raise ValueError('unexpected_content_type')
            body=response.read(MAX_BYTES+1)
            if len(body)>MAX_BYTES:raise ValueError('response_too_large')
            if source['kind']=='pdf' and not body.startswith(b'%PDF-'):raise ValueError('pdf_magic_missing')
            encoding=response.headers.get_content_charset()
            if source['kind']=='html' and not encoding:
                m=re.search(br'charset=["\s\x27]*([A-Za-z0-9_-]+)',body[:8192],re.I)
                encoding=m[1].decode('ascii') if m else 'utf-8'
            conn.send(('ok',body,{'http_status':response.status,'content_type':ct,'encoding':encoding}))
    except Exception as exc:
        reason=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[a-z_]+',str(exc)) else type(exc).__name__
        conn.send(('failed',{'reason':reason,'http_status':getattr(exc,'code',None)}))
    finally:conn.close()


def fetch_one(source):
    ctx=mp.get_context('spawn');reader,writer=ctx.Pipe(duplex=False)
    child=ctx.Process(target=fetch_worker,args=(writer,source));child.start();writer.close()
    try:
        if not reader.poll(35):return ('failed',{'reason':'hard_fetch_deadline','http_status':None})
        try:return reader.recv()
        except EOFError:return ('failed',{'reason':'worker_closed_without_result','http_status':None})
    finally:
        if child.is_alive():child.terminate()
        child.join(2);reader.close()


def trusted_pdf_pages(preflight, expected_hash):
    counts=[preflight.get(k) for k in ('declared_page_count','enumerated_page_count','reader_page_count')]
    return (preflight.get('verdict')=='PASS' and preflight.get('sha256')==expected_hash
        and not preflight.get('warnings') and all(type(n) is int and n>0 for n in counts)
        and len(set(counts))==1)


def pdf_extract(path,preflight_path,out):
    # Use the script's public CLI contract, not guessed internal call names.
    import subprocess
    done=subprocess.run([sys.executable,str(preflight_path),str(path),'--output',str(out/'pdf_read_preflight.json')],
        capture_output=True,text=True,timeout=25)
    if done.returncode:raise ValueError('pdf_preflight_execution_failed')
    preflight=json.loads((out/'pdf_read_preflight.json').read_text(encoding='utf-8'))
    from pypdf import PdfReader
    reader=PdfReader(path)
    trusted=trusted_pdf_pages(preflight,file_digest(path))
    pages=[{'observed_page_index':i+1,'physical_page':i+1 if trusted else None,
            'page_anchor_trusted':trusted,'text':page.extract_text() or ''} for i,page in enumerate(reader.pages)]
    if len(pages)!=preflight.get('reader_page_count'):
        for page in pages:page.update(physical_page=None,page_anchor_trusted=False)
    write_new_json(out/'pdf_pages.json',pages)
    return '\n\n'.join(p['text'] for p in pages),preflight


def selected_sources(catalogue, source_ids=None):
    sources=catalogue['sources']
    ids=[s['source_id'] for s in sources]
    if not sources or len(set(ids))!=len(ids):raise ValueError('invalid_sources')
    if source_ids:
        if set(source_ids)-set(ids):raise ValueError('unknown_source_id')
        sources=[s for s in sources if s['source_id'] in source_ids]
    for source in sources:
        check_url(source['url'])
        if not re.fullmatch('[A-Z0-9-]+',source['source_id']):raise ValueError('unsafe_source_id')
        if source['kind'] not in ('html','pdf'):raise ValueError('unsupported_source_kind')
    return sources


def main():
    p=argparse.ArgumentParser();p.add_argument('--catalogue',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--pdf-preflight',type=Path,required=True)
    p.add_argument('--source-ids',nargs='+');a=p.parse_args()
    if a.output.exists():raise ValueError('new output directory required')
    catalogue=json.loads(a.catalogue.read_text(encoding='utf-8'))
    sources=selected_sources(catalogue,a.source_ids)
    if not a.pdf_preflight.is_file():raise ValueError('pdf_preflight_script_missing')
    write_new_json(a.output/'source_catalogue.snapshot.json',catalogue)
    results=[]
    for source in sources:
        start=time.monotonic();result=fetch_one(source)
        record={'source_id':source['source_id'],'source_url':source['url'],
            'fetched_at':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':round(time.monotonic()-start,3),
            'attempt_count':1,'human_confirmed':False,'integrated_into_corpus':False}
        folder=a.output/source['source_id'];folder.mkdir()
        if result[0]=='failed':record.update(status='fetch_failed',**result[1])
        else:
            _,body,meta=result;record.update(status='downloaded',**meta)
            target=folder/('source.pdf' if source['kind']=='pdf' else 'source.html')
            with target.open('xb') as f:f.write(body)
            record['raw_sha256']=file_digest(target)
            try:
                if source['kind']=='pdf':
                    text,preflight=pdf_extract(target,a.pdf_preflight,folder)
                    record['pdf_preflight']=preflight
                else:text=html_text(body,meta['encoding'])
                with (folder/'normalized_text.txt').open('x',encoding='utf-8') as f:f.write(text)
                record.update(status='extracted',text_sha256=hashlib.sha256(text.encode()).hexdigest(),text_chars=len(text))
            except Exception as exc:record.update(status='extraction_failed',extraction_error=type(exc).__name__)
        write_new_json(folder/'metadata.json',record);results.append(record)
        print(source['source_id']+' '+record['status'],flush=True)
    write_new_json(a.output/'acquisition_report.json',{'sources':results,'requests':len(results),
        'selected_source_ids':[s['source_id'] for s in sources],
        'automatic_retries':0,'private_data_sent':False,'source_catalogue_sha256':file_digest(a.catalogue)})
    return 0


if __name__=='__main__':raise SystemExit(main())
