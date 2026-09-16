"""Isolated P1 article verification; never performs discovery or LLM reasoning.

Only public, explicitly allowlisted URLs may be fetched. Extracted candidates
are data, not instructions. Article text remains ineligible until a separately
recorded human review binds the content, version and applicability scope.
"""
from __future__ import annotations
import hashlib,html,ipaddress,json,re,socket,ssl,time
from datetime import date,datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler,HTTPSHandler
from urllib.error import HTTPError,URLError

PARSER_VERSION='p1-html-blocks-2'
HEADER=re.compile(r'(?m)^[ \t\u3000]*(第[零〇一二三四五六七八九十百千万两\d]+条)[ \t\u3000]*(?=[^\n])')
CHAPTER=re.compile(r'(?m)^[ \t\u3000]*第[一二三四五六七八九十百]+[章节编][ \t\u3000]+')
def digest(b):return hashlib.sha256(b).hexdigest()
def normalize(s):return re.sub(r'\s+','',s)

class TextExtractor(HTMLParser):
    BLOCKS={'p','div','br','li','tr','td','h1','h2','h3','h4','section','article','header','footer'}
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript'}:self.hidden+=1
        elif not self.hidden and tag in self.BLOCKS:self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript'}:self.hidden=max(0,self.hidden-1)
        elif not self.hidden and tag in self.BLOCKS:self.parts.append('\n')
    def handle_data(self,data):
        if not self.hidden:self.parts.append(data)

def html_text(raw,encoding='utf-8'):
    parsed=TextExtractor();parsed.feed(raw.decode(encoding,errors='strict'))
    return '\n'.join(line.strip() for line in ''.join(parsed.parts).splitlines() if line.strip())

def extract_article(text,article):
    headers=list(HEADER.finditer(text));matches=[i for i,h in enumerate(headers) if h[1]==article]
    if len(matches)!=1:raise ValueError('article_absent' if not matches else 'article_boundary_ambiguous')
    i=matches[0]
    # Refuse a last-article/footer guess. This P1 manifest deliberately selects
    # non-final articles with an observed following article boundary.
    if i+1==len(headers):raise ValueError('next_article_boundary_missing')
    start=headers[i].start();end=headers[i+1].start()
    chapter=CHAPTER.search(text,headers[i].end(),end)
    if chapter:end=chapter.start()
    raw_span=text[start:end]
    start+=len(raw_span)-len(raw_span.lstrip())
    value=raw_span.strip()
    return value,{'kind':'normalized_snapshot_text_span','start':start,'end_exclusive':start+len(value),'article':article,'next_article':headers[i+1][1]}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def fetch_public(url,allowlist,max_bytes=2_000_000,timeout=15):
    """No automatic retries, redirects, credentials or request body."""
    if url not in allowlist:raise ValueError('url_not_allowlisted')
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.fragment or p.port not in (None,443):raise ValueError('unsafe_url')
    try:addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    except OSError:raise ValueError('dns_unavailable') from None
    if not addresses or not all(ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('non_public_destination')
    # TLS remains verified; proxies configured by the operator remain in force.
    # This is not a general untrusted-URL fetcher: only reviewed exact URLs.
    opener=build_opener(NoRedirect(),HTTPSHandler(context=ssl.create_default_context()))
    start=time.monotonic()
    req=Request(url,headers={'User-Agent':'EvidenceVerificationP1/1.0 (public-law verification)'})
    with opener.open(req,timeout=timeout) as response:
        content_type=response.headers.get_content_type()
        if content_type not in {'text/html','application/xhtml+xml'}:raise ValueError('unsupported_content_type')
        body=response.read(max_bytes+1)
        if len(body)>max_bytes:raise ValueError('response_too_large')
        encoding=response.headers.get_content_charset()
        if not encoding:
            match=re.search(br'charset=["\s\']*([A-Za-z0-9_-]+)',body[:8192],re.I)
            encoding=match[1].decode('ascii') if match else 'utf-8'
        return body,{'http_status':response.status,'content_type':content_type,'encoding':encoding,'elapsed_seconds':round(time.monotonic()-start,3),'raw_sha256':digest(body),'fetched_at':datetime.now(timezone.utc).isoformat()}

def verify_target(source,target,text,raw_hash):
    reasons=[]
    if normalize(source['law_title']) not in normalize(text):reasons.append('law_title_missing')
    if not all(normalize(x) in normalize(text) for x in source['version_anchors']):reasons.append('version_anchor_missing')
    if '征求意见稿' in text[:max(0,text.find('第一条'))]:reasons.append('draft_source')
    try:quote,locator=extract_article(text,target['article'])
    except ValueError as e:quote='';locator=None;reasons.append(str(e))
    if quote and normalize(target['anchor']) not in normalize(quote):reasons.append('anchor_not_in_target_article')
    if quote and target.get('expected_full_quote') and normalize(quote)!=normalize(target['expected_full_quote']):reasons.append('full_quote_mismatch')
    return {'target_id':target['target_id'],'source_id':source['source_id'],'source_url':source['url'],
      'law_title':source['law_title'],'issuer':source['issuer'],'version_label':source['version_label'],
      'actual_normative_level':source['actual_normative_level'],'instrument_type':source['instrument_type'],
      'geographic_scope':source['geographic_scope'],'temporal_status':source['temporal_status'],
      'candidate_valid_to_exclusive':source.get('candidate_valid_to_exclusive'),'temporal_support_url':source.get('temporal_support_url'),
      'article':target['article'],'legal_quote':quote,'article_sha256':digest(quote.encode('utf-8')) if quote else None,
      'raw_snapshot_sha256':raw_hash,'normalized_snapshot_sha256':digest(text.encode('utf-8')),
      'source_locator':locator,'parser_version':PARSER_VERSION,'machine_verification_passed':not reasons,'block_reasons':reasons,
      'acquisition_channel':'external_verification','admission_status':'pending_human_confirmation' if not reasons else 'blocked_machine_verification',
      'independent_legal_evidence':False,'source_version_certified':False}

def assess_admission(packet,review,context):
    """Pure gate demonstration. Never writes to a RAG corpus or model runner.

    review is an operator-controlled sidecar, never page/LLM-provided metadata.
    Confirmation is restricted to the exact source and the declared date interval.
    """
    reasons=[]
    if not packet.get('machine_verification_passed'):reasons.append('machine_verification_failed')
    if not isinstance(review,dict) or review.get('status')!='confirmed':reasons.append('human_confirmation_missing')
    else:
        if not isinstance(context,dict):context={}
        for k in ['reviewer_id','confirmed_at','law_title','version_label','article_sha256','raw_snapshot_sha256','valid_from','verified_through','allowed_project_types','geographic_scope']:
            if not review.get(k):reasons.append('review_missing_'+k)
        for k in ['law_title','version_label','article_sha256','raw_snapshot_sha256','geographic_scope']:
            if review.get(k)!=packet.get(k):reasons.append('review_binding_mismatch_'+k)
        try:
            datetime.fromisoformat(review['confirmed_at'].replace('Z','+00:00'))
            at=date.fromisoformat(context['as_of']);start=date.fromisoformat(review['valid_from']);through=date.fromisoformat(review['verified_through'])
            if not start<=at<=through:reasons.append('outside_verified_time_window')
            if review.get('valid_to_exclusive') and at>=date.fromisoformat(review['valid_to_exclusive']):reasons.append('expired_for_case_date')
            if packet.get('candidate_valid_to_exclusive') and at>=date.fromisoformat(packet['candidate_valid_to_exclusive']):reasons.append('historical_source_not_for_case_date')
        except (KeyError,ValueError,TypeError):reasons.append('date_missing_or_invalid')
        allowed_types=review.get('allowed_project_types')
        if not isinstance(allowed_types,list) or not allowed_types or not all(isinstance(x,str) and x for x in allowed_types):
            reasons.append('invalid_project_type_review_schema');allowed_types=[]
        if not context.get('project_type') or context['project_type'] not in allowed_types:reasons.append('project_type_missing_or_not_confirmed')
        if packet.get('geographic_scope')!='national' and context.get('jurisdiction')!=packet.get('geographic_scope'):reasons.append('local_jurisdiction_missing_or_mismatch')
    return {'status':'eligible_for_reviewed_scope' if not reasons else 'not_admitted','independent_legal_evidence':not reasons,'reasons':reasons,
      'actual_normative_level':packet.get('actual_normative_level'),'acquisition_channel':'external_verification',
      'requires_human_second_review':True,'integrated_into_production':False}
