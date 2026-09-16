"""Freeze an already-issued human admission, without inventing legal dates.

The trusted approval record is supplied out-of-band. This tool never generates
user consent, fills unknown statutory commencement dates, or modifies a corpus.
It creates a new private experiment snapshot and a separate evaluator label file.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
from discovery import (SnapshotStore, admit_candidate, canonical_hash, load_catalogue,
                       packet_integrity)

BINDINGS = ('target_id', 'source_id', 'source_url', 'law_title', 'version_label',
            'article_sha256', 'raw_snapshot_sha256')

def build_review(packet, approval, spec, catalogue_source):
    case_day = spec['default_context']['as_of']
    fields = ('jurisdiction','project_type','procurement_regime','as_of')
    contexts = {t['id']:{**spec['default_context'],**t.get('context',{})} for t in spec['tasks']}
    date.fromisoformat(case_day)
    datetime.fromisoformat(approval['recorded_at'].replace('Z', '+00:00'))
    # This is an admitted case-date window, NOT the legislation's start date.
    # Historical/future tasks remain blocked unless separately reviewed.
    review = {key: packet[key] for key in ('candidate_id', 'law_title', 'version_label',
              'article_sha256', 'raw_snapshot_sha256', 'geographic_scope')}
    review.update(status='confirmed', reviewer_id=approval['reviewer_id'],
                  confirmed_at=approval['recorded_at'], confirmation_basis=approval['user_statement'],
                  valid_from=case_day, verified_through=case_day, valid_to_exclusive=None,
                  validity_field_semantics='single_registered_case_day_not_statutory_commencement',
                  statutory_effective_date=None, statutory_expiry_date=None,
                  allowed_project_types=catalogue_source['project_types'],
                  procurement_regime=('government_procurement' if 'government_procurement' in catalogue_source['regimes'] else 'construction_tender'),
                  source_provenance_confirmed=True, dependency_review='complete',
                  facts_sufficient_for_applicability=True,
                  facts_confirmation_boundary='registered law-level applicability only; not confirmation of violation or missing attachments',
                  approval_scope={'scope_id':approval['scope_id'], 'task_spec_sha256':approval['task_spec_sha256'],
                                  'allowed_issue_ids':[t['id'] for t in spec['tasks']],
                                  'context_hashes':{k:canonical_hash({f:v.get(f) for f in fields}) for k,v in contexts.items()}})
    return review

def prepare(task_approval_dir, admission_file, cache_dirs, out):
    read = lambda p: json.loads(Path(p).read_text(encoding='utf-8'))
    spec=read(task_approval_dir/'task_spec.approved_snapshot.json')
    task_approval=read(task_approval_dir/'approval_record.private.json')
    task_labels=read(task_approval_dir/'human_labels.task_approved.private.json')
    bound=read(task_approval_dir/'reference_bindings.pending.private.json')
    approval=read(admission_file)
    if approval.get('status')!='all_listed_articles_admitted' or not approval.get('user_statement') or not approval.get('reviewer_id'):
        raise ValueError('explicit_human_admission_record_required')
    sha=canonical_hash(spec)
    if any(item.get('task_spec_sha256')!=sha for item in (task_approval,task_labels,bound,approval)):
        raise ValueError('task_spec_binding_mismatch')
    if task_approval.get('status')!='task_specification_and_proposed_outcomes_approved':
        raise ValueError('task_approval_missing')
    if set(task_labels['cases'])!={t['id'] for t in spec['tasks']}:
        raise ValueError('task_label_coverage_mismatch')
    ids={p['target_id'] for p in bound['packets']}
    approved={p['target_id']:p for p in approval['articles']}
    if len(approved)!=len(approval['articles']) or set(approved)!=ids:
        raise ValueError('article_approval_coverage_mismatch')
    catalogue={s['source_id']:s for s in load_catalogue()}
    stores=[SnapshotStore(p) for p in cache_dirs]
    reviews, packets, checks, raw_sources = {}, [], [], {}
    for original in bound['packets']:
        if any(original.get(k)!=approved[original['target_id']].get(k) for k in BINDINGS):
            raise ValueError('article_approval_binding_mismatch')
        source=catalogue[original['source_id']]
        if source['url']!=original['source_url']: raise ValueError('catalogue_url_drift')
        cached=next((value for s in stores if (value:=s.get(source['url']))), None)
        if not cached: raise ValueError('frozen_source_missing')
        packet=deepcopy(original)
        packet['candidate_id']=canonical_hash([packet['source_url'],packet['raw_snapshot_sha256'],packet['article'],packet['article_sha256']])[:24]
        packet['regimes']=source['regimes']
        packet['evidence_id']=packet['target_id']+':'+packet['article_sha256']
        if packet_integrity(packet,cached): raise ValueError('frozen_article_integrity_failed')
        review=build_review(packet,approval,spec,source)
        # Probe a scope-compatible context. This is a software gate check, not
        # retrieval of a gold answer or evaluation of any case's legal outcome.
        compatible=[]
        for t in spec['tasks']:
            ctx={**spec['default_context'],**t.get('context',{})}
            if ctx.get('procurement_regime')==review['procurement_regime'] and ctx.get('project_type') in source['project_types'] and ctx.get('as_of')==review['valid_from'] and ctx.get('jurisdiction'):
                compatible.append((t['id'],ctx))
        if not compatible: raise ValueError('no_approved_context_for_source')
        issue_id,context=compatible[0]
        context={**context,'scope_id':approval['scope_id'],'task_spec_sha256':sha,'issue_id':issue_id}
        result=admit_candidate(packet,review,context,cached)
        if not result['independent_legal_evidence']: raise ValueError('approved_article_gate_failed')
        denied = {}
        mutations = {'unregistered_issue':{'issue_id':'OUTSIDE-P3'},
                     'future_day':{'as_of':str(date.fromisoformat(context['as_of']).replace(year=2027))},
                     'historical_day':{'as_of':'2018-06-01'}, 'missing_scope':{'scope_id':None},
                     'changed_task_spec':{'task_spec_sha256':'unapproved'},
                     'wrong_regime':{'procurement_regime':'unapproved'}, 'missing_location':{'jurisdiction':None}}
        for name,changes in mutations.items():
            denied[name]=not admit_candidate(packet,review,{**context,**changes},cached)['independent_legal_evidence']
        if not all(denied.values()): raise ValueError('approval_scope_escaped')
        reviews[packet['candidate_id']]=review
        packet.update(admission_status='human_confirmed_library_member_context_gate_required',
                      independent_legal_evidence=False,
                      approval_scope_id=approval['scope_id'])
        # The library itself is not a per-issue gate result. Recheck each actual
        # context before admitting evidence to a reasoning request.
        packets.append(packet)
        checks.append({'reference_key':packet['target_id'],'in_scope_gate_pass':True,'out_of_scope_denials':denied})
        raw_sources[packet['source_url']]=cached
    by_key={p['target_id']:p for p in packets}
    reference_sha=canonical_hash(packets)
    locked_cases={}
    for task in spec['tasks']:
        prior=task_labels['cases'][task['id']]
        if prior.get('status')!='approved_by_user_at_task_level' or prior['conclusion']!=task['proposed_outcome']:
            raise ValueError('approved_task_label_changed')
        locked_cases[task['id']]={'status':'confirmed','relevant_evidence_ids':[by_key[k]['evidence_id'] for k in task['references']],
            'conclusion':prior['conclusion'],'must_abstain':prior['must_abstain'],
            'reference_completeness':'recorded_reference_set_not_certified_exhaustive',
            'approval_basis':'user task approval plus bound article admission; not independent expert adjudication'}
    labels={'status':'human_confirmed_locked','task_spec_sha256':sha,'reviewer_id':approval['reviewer_id'],
            'locked_at':approval['recorded_at'],'reference_snapshot_sha256':reference_sha,
            'source':'AI-authored tasks approved by user; no expert dataset used','cases':locked_cases}
    readiness={'task_and_article_approval_complete':True,'approved_tasks':len(spec['tasks']),
               'admitted_library_articles':len(packets),'article_gate_positive_checks':len(checks),
               'article_gate_negative_checks':sum(len(c['out_of_scope_denials']) for c in checks),
               'formal_abc_execution_ready':False,'unresolved_approvals_for_these_tasks_and_articles':[],
               'remaining_engineering':['separate fact-only runtime inputs from test instructions/reference answers',
                  'validate A/B/C execution adapters and actual fault injection',
                  'freeze identical local corpus/masks and prompt/parameters',
                  'verify runtime citation to final Markdown/Excel lineage'],
               'references_used_to_inject_retrieval_hits':False,'llm_calls':0,'network_requests':0}
    out.mkdir(parents=True,exist_ok=False)
    frozen=SnapshotStore(out/'source_snapshots')
    for url,(raw,meta) in raw_sources.items(): frozen.put(url,raw,meta)
    for name,value in [('approval_record.private.json',approval),('task_spec.snapshot.json',spec),
                       ('human_reviews.confirmed.private.json',reviews),('approved_library.private.json',packets),
                       ('human_labels.locked.private.json',labels),('gate_checks.private.json',checks),
                       ('readiness.private.json',readiness)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(readiness,ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--task-approval-dir',type=Path,required=True)
    ap.add_argument('--admission-file',type=Path,required=True)
    ap.add_argument('--cache-dir',nargs='+',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();prepare(args.task_approval_dir,args.admission_file,args.cache_dir,args.out)
