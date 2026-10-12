"""Opt-in gate for runtime-owned, machine-checked supplementary web articles.

Unlike the historical human-scope bridge, this policy never claims human
approval or independent legal applicability. The ingestion adapter verifies
the actual snapshot; this gate binds that trusted record to the exact runtime.
"""
import hashlib
import json
import re

VERSION = 'external-auto-supplement-v1'
FIELDS = ('chunk_id', 'source_id', 'source_url', 'source_title', 'issuer', 'source_version',
          'source_hash', 'article_sha256', 'normalized_snapshot_sha256', 'source_locator',
          'source_locator_coordinates', 'article', 'legal_quote', 'retrieved_at',
          'normative_level', 'geographic_scope', 'independent_legal_evidence',
          'independent_evidence', 'legal_evidence_eligibility', 'human_confirmation_status')


def sha(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def seal_source(source, runtime):
    source['automatic_source_admission'] = {'producer': VERSION,
        'issue_id': runtime.get('issue_id'), 'context_sha256': sha(runtime.get('project_context')),
        'source_record_sha256': sha({k: source.get(k) for k in FIELDS}),
        'snapshot_integrity_passed': True, 'title_version_anchor_passed': True,
        'human_pre_admission_required': False, 'admission_kind': 'supplement_only'}


def machine_candidate_admitted(source, runtime):
    record = source.get('automatic_source_admission') or {}
    if record.get('producer') != VERSION or record.get('admission_kind') != 'supplement_only':
        return False
    if record.get('issue_id') != runtime.get('issue_id') or not runtime.get('issue_id'):
        return False
    if record.get('context_sha256') != sha(runtime.get('project_context')):
        return False
    if record.get('source_record_sha256') != sha({k: source.get(k) for k in FIELDS}):
        return False
    if any(record.get(k) is not True for k in ('snapshot_integrity_passed', 'title_version_anchor_passed')):
        return False
    if source.get('independent_legal_evidence') is not False or source.get('independent_evidence') is not False:
        return False
    if source.get('legal_evidence_eligibility') != 'supplement_only':
        return False
    if source.get('human_confirmation_status') != 'not_requested':
        return False
    for field in ('source_hash', 'article_sha256', 'normalized_snapshot_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', str(source.get(field, ''))):
            return False
    quote = source.get('legal_quote')
    if not isinstance(quote, str) or hashlib.sha256(quote.encode()).hexdigest() != source['article_sha256']:
        return False
    return bool(source.get('source_locator') and source.get('source_url'))
