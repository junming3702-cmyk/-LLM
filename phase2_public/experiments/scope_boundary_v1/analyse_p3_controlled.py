"""Offline P3 evaluator. Locked labels are never imported by runtime runners.

No global local/external Recall is fabricated from incompatible chunk IDs.
Conditional external rankings are evaluated against recorded article IDs only.
"""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import json
import statistics
import sys

PACKAGE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PACKAGE/'src'))
sys.path.insert(0,str(PACKAGE/'experiments/main_controls_v1'))
sys.path.insert(0,str(PACKAGE/'experiments/external_discovery_p2p3_v1'))
from experiment_integrity import digest,file_digest,validate_runtime,write_new_json,semantic_verdict
from controls import semantic_observation
from discovery import canonical_hash

ARMS=('A_local','B_fixed_access','B_source_matched_access','C_article_discovery')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def ranked_metrics(ranked,relevant):
    if len(ranked)!=len(set(ranked)):raise ValueError('duplicate_ranked_evidence')
    if not relevant:return None
    refs=set(relevant)
    return {'recall_at_5':len(refs.intersection(ranked[:5]))/len(refs),
        'reciprocal_rank':next((1/i for i,r in enumerate(ranked,1) if r in refs),0),
        'relevant_count':len(refs),'recovered_at_5':len(refs.intersection(ranked[:5])),
        'ranked_count':len(ranked)}


def summarize_rank(rows):
    values=[r for r in rows if r is not None]
    return {'denominator':len(values),
        'macro_evidence_recall_at_5':statistics.mean(r['recall_at_5'] for r in values) if values else None,
        'mrr_over_returned_ranking':statistics.mean(r['reciprocal_rank'] for r in values) if values else None,
        'scope':'conditional external recheck stage; NOT overall model retrieval',
        'reference_set_exhaustive':False}


def request_audit(run,binding):
    totals=Counter(); models=Counter(); status=Counter();times=[]; failures=[];n=0
    for path in sorted((run/'audit').glob('*/request_cache/*.json')):
        if path.name.endswith('.started.json'):continue
        item=read(path);obs=item['observation'];body=obs['request_body']
        if digest(obs)!=item['observation_hash']:raise ValueError('request_cache_tampered')
        if body['model']!=binding['requested_model'] or body['temperature']!=binding['temperature']:
            raise ValueError('unmatched_model_or_temperature')
        if body['max_tokens'] not in (binding['triage_max_tokens'],binding['final_max_tokens']):
            raise ValueError('unmatched_token_budget')
        if len(obs['attempts'])!=1:raise ValueError('unexpected_retry')
        for message in body['messages']:
            if message['role']=='user':
                runtime=json.loads(message['content']);validate_runtime(runtime)
                # Source human approval metadata is never itself model input.
                forbidden={'reviewer_id','confirmed_at','confirmation_basis','approval_scope',
                    'applies_to_tasks','proposed_outcome','relevant_evidence_ids','must_abstain'}
                def scan(value):
                    if isinstance(value,dict):
                        if set(value)&forbidden:raise ValueError('source_or_answer_metadata_in_runtime')
                        for v in value.values():scan(v)
                    elif isinstance(value,list):
                        for v in value:scan(v)
                scan(runtime)
        payload=obs.get('payload') or {};usage=payload.get('usage') or {}
        for k in ('total_tokens','prompt_tokens','completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'):
            if isinstance(usage.get(k),(int,float)):totals[k]+=usage[k]
        models[str(payload.get('model'))]+=1
        choices=payload.get('choices') or [{}]
        status[str(choices[0].get('finish_reason'))]+=1
        if not obs.get('ok'):failures.append({'path':str(path.relative_to(run)),
            'transport_error':obs.get('transport_error'),'http_status':obs.get('http_status')})
        times.append(obs['elapsed_seconds']);n+=1
    completion=read(run/'completion.json')
    if n!=completion['budgets']['requests']:raise ValueError('request_count_mismatch')
    return {'calls':n,'usage':dict(totals),'returned_model_names':dict(models),
        'finish_reasons':dict(status),'request_median_seconds':statistics.median(times) if times else None,
        'request_total_seconds':sum(times),'wall_seconds':completion['elapsed_seconds'],
        'failures':failures,'runtime_leak_scan_passed':True,'automatic_retries':0}


def analyze(run,frozen):
    spec=read(frozen/'task_spec.snapshot.json');labels=read(frozen/'human_labels.locked.private.json')
    binding=read(run/'run_manifest.json')['binding'];complete=read(run/'completion.json')
    if not complete['complete_attempts']:raise ValueError('incomplete_run_not_full_denominator')
    if labels.get('status')!='human_confirmed_locked' or labels['task_spec_sha256']!=canonical_hash(spec):
        raise ValueError('reference_lock_invalid')
    if binding['task_spec_sha256']!=labels['task_spec_sha256']:raise ValueError('runtime_reference_spec_mismatch')
    tasks={t['id']:t for t in spec['tasks'] if not t.get('fault')}
    refs=labels['cases']
    if len(tasks)!=binding['legal_tasks']:raise ValueError('task_coverage_mismatch')
    details=[];aggregates={};pairs=[];all_external=[]
    for uid,t in tasks.items():
        ref=refs[uid];record={'issue_id':uid,'family':t['family'],'category':t['category'],
            'reference_conclusion':ref['conclusion'],'reference_verdict':semantic_verdict(ref['conclusion']),
            'arms':{}}
        audit=read(run/'external_audit'/(uid+'.json'))
        for arm in ARMS:
            result=read(run/'results'/arm/(uid+'.json'))
            if result['issue_id']!=uid or result['p3_arm']!=arm:raise ValueError('result_binding_mismatch')
            obs=semantic_observation(result);raw=semantic_observation(result,True)
            if obs!=result['gated_observation'] or raw!=result['raw_observation']:
                raise ValueError('saved_observation_mismatch')
            findings=((result.get('post_llm_gate') or {}).get('response') or {}).get('findings',[])
            f=findings[0] if len(findings)==1 else {}
            citations=f.get('legal_evidence') or []
            supplied={e['chunk_id']:e for e in result.get('runtime_input',{}).get('retrieved_legal_evidence',[])}
            unknown=[e.get('chunk_id') for e in citations if e.get('chunk_id') not in supplied]
            cited_external=[e.get('chunk_id') for e in citations if str(e.get('chunk_id','')).startswith('external:')]
            one={'status':obs['status'],'raw_verdict':raw['verdict'],'verdict':obs['verdict'],
                'conclusion':f.get('conclusion_type') if obs['status']=='completed' else None,
                'semantic_agreement':obs['status']=='completed' and obs['verdict']==record['reference_verdict'],
                'raw_semantic_agreement':raw['status']=='completed' and raw['verdict']==record['reference_verdict'],
                'exact_conclusion_agreement':obs['status']=='completed' and f.get('conclusion_type')==ref['conclusion'],
                'unknown_citations':unknown,'citation_count':len(citations),'external_citations':cited_external,
                'external_recheck_attempted':bool(result.get('p3_one_shot_audit',{}).get('attempted')),
                'new_final_generation':bool(result.get('new_final_generation')),
                'statement':f.get('risk_statement'),'recommendation':f.get('assistant_recommendation'),
                'reasoning':f.get('reasoning'),'evidence_boundary':f.get('evidence_boundary'),
                'gate_actions':(result.get('post_llm_gate') or {}).get('actions',[])}
            record['arms'][arm]=one
        ext=audit['sources'].get('C_article_discovery')
        rank_record={'issue_id':uid,'triggered':ext is not None,'positive_reference':bool(ref['relevant_evidence_ids'])}
        if ext is not None:
            rank_record.update(candidate=ranked_metrics([p['evidence_id'] for p in ext['candidates']],ref['relevant_evidence_ids']),
                admitted=ranked_metrics([p['evidence_id'] for p in ext['admitted_evidence']],ref['relevant_evidence_ids']),
                admitted_count=len(ext['admitted_evidence']))
        all_external.append(rank_record)
        details.append(record)
        a,c=record['arms']['A_local'],record['arms']['C_article_discovery']
        pairs.append({'issue_id':uid,'A':a['verdict'],'C':c['verdict'],
            'change':'improved' if c['semantic_agreement'] and not a['semantic_agreement'] else
            'worsened' if a['semantic_agreement'] and not c['semantic_agreement'] else 'unchanged_agreement',
            'both_completed':a['status']==c['status']=='completed'})
    for arm in ARMS:
        grouped=defaultdict(list)
        for d in details:grouped[d['family']].append(d)
        rows=[d['arms'][arm] for d in details]
        aggregates[arm]={'denominator':len(details),'status_counts':dict(Counter(r['status'] for r in rows)),
            'verdict_counts':dict(Counter(r['verdict'] for r in rows)),
            'semantic_agreement_count':sum(r['semantic_agreement'] for r in rows),
            'raw_semantic_agreement_count':sum(r['raw_semantic_agreement'] for r in rows),
            'exact_conclusion_agreement_count':sum(r['exact_conclusion_agreement'] for r in rows),
            'N_to_R':sum(d['reference_verdict']=='N' and d['arms'][arm]['verdict']=='R' for d in details),
            'U_to_decision':sum(d['reference_verdict']=='U' and d['arms'][arm]['verdict'] in ('N','R') for d in details),
            'R_to_N':sum(d['reference_verdict']=='R' and d['arms'][arm]['verdict']=='N' for d in details),
            'unknown_citation_count':sum(len(r['unknown_citations']) for r in rows),
            'actual_new_final_generations':sum(r['new_final_generation'] for r in rows),
            'per_family':{family:{'n':len(ds),'correct':sum(d['arms'][arm]['semantic_agreement'] for d in ds)} for family,ds in grouped.items()}}
    return {'run_manifest_sha256':file_digest(run/'run_manifest.json'),'corpus_mode':binding['corpus_mode'],
        'reference_sha256':file_digest(frozen/'human_labels.locked.private.json'),
        'reference_verdict_counts':dict(Counter(d['reference_verdict'] for d in details)),
        'aggregates':aggregates,'details':details,'paired_A_C':pairs,
        'conditional_external_retrieval':{'candidate':summarize_rank([r.get('candidate') for r in all_external]),
            'admitted':summarize_rank([r.get('admitted') for r in all_external]),'per_case':all_external},
        'request_audit':request_audit(run,binding),
        'overall_Recall_MRR_not_computed':'Local chunk IDs and external full-article IDs are not a validated common relevance space.',
        'reference_is_independent_expert_adjudication':False,'engineering_faults_in_legal_denominator':False,
        'verification_status':'ANALYZED','llm_reproducibility':'N/A external stochastic API; single primary attempt'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--frozen',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=analyze(a.run,a.frozen)
    write_new_json(a.output/'analysis.private.json',result)
    print(json.dumps({k:v for k,v in result.items() if k in ('corpus_mode','reference_verdict_counts','aggregates','request_audit')},ensure_ascii=False))


if __name__=='__main__':main()
