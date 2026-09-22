"""Opt-in acceptance of explicitly approved, case-day scoped external sources.

This does not invent statutory effective dates. It is disabled in production
and requires runtime-owned source validation tied to the exact case context.
"""
from datetime import date
import hashlib
import json
import re

VERSION='p3-source-scope-bridge-v1'


def context_binding(context):
    return {k:context.get(k) for k in ('jurisdiction','project_type','procurement_regime','as_of')}


def hash_context(context):
    return hashlib.sha256(json.dumps(context_binding(context),ensure_ascii=False,
        sort_keys=True,separators=(',',':')).encode()).hexdigest()


def scoped_temporal_admission(source,runtime):
    record=source.get('registered_source_scope_validation')
    if not isinstance(record,dict) or record.get('producer')!=VERSION:return False
    ctx=runtime.get('project_context') or {}
    loc=ctx.get('project_location') or {}
    if loc.get('human_confirmation')!='confirmed':return False
    actual={'jurisdiction':loc.get('province'),'project_type':ctx.get('project_type_code'),
        'procurement_regime':ctx.get('procurement_regime'),'as_of':ctx.get('review_as_of')}
    if not all(actual.values()):return False
    if record.get('context_sha256')!=hash_context(actual) or record.get('issue_id')!=runtime.get('issue_id'):return False
    try:
        at=date.fromisoformat(actual['as_of'])
        if not date.fromisoformat(record['valid_from'])<=at<=date.fromisoformat(record['verified_through']):return False
    except (KeyError,TypeError,ValueError):return False
    if source.get('human_confirmation_status')!='confirmed' or source.get('independent_legal_evidence') is not True:return False
    if record.get('sidecar_admission_passed') is not True or record.get('snapshot_integrity_passed') is not True:return False
    if not re.fullmatch('[a-f0-9]{64}',str(record.get('source_review_sha256',''))):return False
    for field in ('source_hash','article_sha256'):
        if not re.fullmatch('[a-f0-9]{64}',str(source.get(field,''))) or record.get(field)!=source.get(field):return False
    quote=source.get('legal_quote')
    if not isinstance(quote,str) or hashlib.sha256(quote.encode()).hexdigest()!=source['article_sha256']:return False
    return True
