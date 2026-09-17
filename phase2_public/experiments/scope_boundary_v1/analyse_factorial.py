"""Offline evaluator for a completed four-arm run. Never called by the runner.

Reference labels are evaluation-only and must not be imported into runtime.
All planned observations, including failures, remain in the denominator.
"""
from collections import Counter
from pathlib import Path
import argparse
import json
import math
import statistics
import sys

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE/'src'))
from experiment_integrity import digest, file_digest, write_new_json
from scope_boundary_policy import ARMS, geographic_decision


def ratio(n, d):
    return n/d if d else None


def metrics(rows):
    n = len(rows)
    good = [r for r in rows if r['status'] == 'completed']
    decided = [r for r in good if r['verdict'] in ('N','R')]
    risk = [r for r in good if r['verdict'] == 'R']
    true_risk = [r for r in rows if r['reference'] == 'R']
    matches = sum(r['status']=='completed' and r['verdict']==r['reference'] for r in rows)
    correct_risk = sum(r['reference']=='R' for r in risk)
    return {'planned_n':n, 'status_counts':dict(Counter(r['status'] for r in rows)),
        'reference_counts':dict(Counter(r['reference'] for r in rows)),
        'verdict_counts_completed_only':dict(Counter(r['verdict'] for r in good)),
        'match_count':matches, 'agreement_all_planned':ratio(matches,n),
        'completed_count':len(good), 'completion_rate':ratio(len(good),n),
        'nonabstained_count':len(decided), 'nonabstained_coverage':ratio(len(decided),n),
        'selective_agreement':ratio(sum(r['verdict']==r['reference'] for r in decided),len(decided)),
        'risk_precision_numerator':correct_risk, 'risk_precision_denominator':len(risk),
        'risk_precision':ratio(correct_risk,len(risk)),
        'risk_recall_denominator':len(true_risk), 'risk_recall':ratio(correct_risk,len(true_risk)),
        'false_R_from_N':sum(r['reference']=='N' and r['verdict']=='R' for r in good),
        'false_N_from_R':sum(r['reference']=='R' and r['verdict']=='N' for r in good),
        'unsupported_upgrade_from_U':sum(r['reference']=='U' and r['verdict'] in ('N','R') for r in good),
        'confusion_including_failures':dict(Counter(r['reference']+'->'+(r['verdict'] if r['status']=='completed' else 'FAIL') for r in rows))}


def paired(rows, old, new, stage):
    a = {r['unit_id']:r for r in rows if r['arm']==old and r['stage']==stage}
    b = {r['unit_id']:r for r in rows if r['arm']==new and r['stage']==stage}
    if set(a) != set(b): raise ValueError('unpaired experimental arms')
    counts = Counter()
    changes = []
    for uid in sorted(a):
        x,y = a[uid],b[uid]
        cx = x['status']=='completed' and x['verdict']==x['reference']
        cy = y['status']=='completed' and y['verdict']==y['reference']
        kind = 'improved' if cy and not cx else 'worsened' if cx and not cy else 'unchanged_correctness'
        counts[kind] += 1
        if (x['status'],x['verdict']) != (y['status'],y['verdict']):
            changes.append({'unit_id':uid,'old_status':x['status'],'new_status':y['status'],
                'old_verdict':x['verdict'],'new_verdict':y['verdict'],'reference':x['reference'],'effect':kind})
    return {'from':old,'to':new,'stage':stage,'n':len(a), 'counts':dict(counts),
        'agreement_delta':ratio(counts['improved']-counts['worsened'],len(a)), 'changed':changes}


def distribution(values):
    values = sorted(values)
    return {'n':len(values),'sum':sum(values),
        'median':statistics.median(values) if values else None,
        'p90_nearest_rank':values[math.ceil(.9*len(values))-1] if values else None}


def load_reference(path):
    source = json.loads(path.read_text(encoding='utf-8'))
    by_id = {}
    for row in source['detail']:
        value = row['A_recorded_reference']
        if value not in ('N','R','U'): raise ValueError('unresolved reference')
        uid = row['unit_id']
        if uid in by_id and by_id[uid] != value: raise ValueError('conflicting frozen references')
        by_id[uid] = value
    return by_id


def collect_calls(folder):
    calls=[]
    for path in sorted(folder.glob('request_cache/*.json')):
        if path.name.endswith('.started.json'): continue
        record=json.loads(path.read_text(encoding='utf-8'))
        observation=record['observation']
        if digest(observation)!=record['observation_hash']: raise ValueError('response audit hash mismatch')
        attempts=observation.get('attempts',[])
        for attempt in attempts:
            payload=attempt.get('payload') or {}
            calls.append({'request_key':record['request_key'],'attempt':attempt.get('attempt'),
                'http_status':attempt.get('http_status'),'ok':attempt.get('ok'),
                'transport_error':attempt.get('transport_error'),'usage':payload.get('usage'),
                'returned_model':payload.get('model'),'elapsed_seconds':attempt.get('elapsed_seconds',0)})
    return calls


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--references',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    completion=json.loads((args.run/'completion.json').read_text(encoding='utf-8'))
    if not completion['complete_attempts']: raise ValueError('primary batch incomplete; no selective analysis')
    manifest=json.loads((args.run/'run_manifest.json').read_text(encoding='utf-8'))
    if file_digest(args.inputs)!=manifest['binding']['input_sha256']: raise ValueError('runtime input changed')
    inputs=json.loads(args.inputs.read_text(encoding='utf-8'))
    references=load_reference(args.references)
    if set(references)!=set(r['issue_id'] for r in inputs): raise ValueError('reference/input set mismatch')
    registry=json.loads((args.run/'source_scope_overlay.json').read_text(encoding='utf-8'))
    rows,detail,cost_rows,integrity=[],[],[],[]
    for arm in ARMS:
        for original in inputs:
            uid=original['issue_id']
            path=args.run/'results'/arm/(uid+'.json')
            result=json.loads(path.read_text(encoding='utf-8'))
            if result['experiment_provenance']['input_sha256'] != digest(original): raise ValueError('input binding mismatch')
            if result['experimental_arm'] != arm or result['issue_id'] != uid: raise ValueError('result identity mismatch')
            for stage,key in [('raw','raw_observation'),('gated','gated_observation')]:
                obs=result[key]
                rows.append({'unit_id':uid,'project':original['project_id'],'arm':arm,'stage':stage,
                    'reference':references[uid],**obs})
            runtime=result.get('runtime_input') or {}
            gate=result.get('post_llm_gate') or {}
            response=gate.get('response') or {}
            findings=response.get('findings',[]) if isinstance(response,dict) else []
            finding=findings[0] if len(findings)==1 and isinstance(findings[0],dict) else {}
            raw_parsed=(result.get('final_llm_response') or {}).get('parsed')
            evidence=runtime.get('retrieved_legal_evidence') or []
            cited=[e.get('chunk_id') for e in finding.get('legal_evidence',[]) if isinstance(e,dict)]
            rejected=[]
            for source in evidence:
                decision=geographic_decision(source,runtime.get('project_context') or {},registry)
                if not decision['allowed']: rejected.append(decision)
            rejected_ids={d['chunk_id'] for d in rejected}
            calls=collect_calls(args.run/'audit'/arm/uid)
            expected_calls=result['experiment_provenance']['request_count']
            if len(calls)!=expected_calls: raise ValueError('call audit count mismatch')
            cost_rows.append({'arm':arm,'unit_id':uid,
                'unit_elapsed_seconds':result['experiment_provenance']['elapsed_seconds'],'calls':calls})
            detail.append({'arm':arm,'unit_id':uid,'project':original['project_id'],
                'reference':references[uid],'raw':result['raw_observation'],'gated':result['gated_observation'],
                'document_location':original['document_location'],'contract_excerpt':original['document_excerpt'],
                'review_task':runtime.get('review_task_contract'), 'finding':finding,
                'gate_actions':gate.get('actions',[]),'packet_unsafe_local_entries':rejected,
                'raw_finding':raw_parsed.get('findings',[]) if isinstance(raw_parsed,dict) else [],
                'finish_reason':(result.get('final_llm_response') or {}).get('finish_reason'),
                'response_channel_diagnostics':(result.get('final_llm_response') or {}).get('response_channel_diagnostics'),
                'unsafe_local_citation_ids':sorted(set(cited)&rejected_ids),
                'human_review':'需要人工二次审核；新输出未接受原阶段B专家评价',
                'source_result':str(path),'source_result_sha256':file_digest(path)})
            integrity.append({'path':str(path),'sha256':file_digest(path)})
    summaries={}
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm]
        summaries[arm]={stage:{'all':metrics([r for r in selected if r['stage']==stage]),
            'projects':{pid:metrics([r for r in selected if r['stage']==stage and r['project']==pid])
                for pid in sorted({r['project'] for r in selected})}} for stage in ('raw','gated')}
    comparisons=[paired(rows,a,b,s) for s in ('raw','gated') for a,b in (
        ('baseline','geo_only'),('task_only','geo_task'),('baseline','task_only'),('geo_only','geo_task'),('baseline','geo_task'))]
    interaction={s:(summaries['geo_task'][s]['all']['agreement_all_planned']
        -summaries['task_only'][s]['all']['agreement_all_planned']
        -summaries['geo_only'][s]['all']['agreement_all_planned']
        +summaries['baseline'][s]['all']['agreement_all_planned']) for s in ('raw','gated')}
    efficiency={}
    for arm in ARMS:
        subset=[r for r in cost_rows if r['arm']==arm]
        calls=[c for r in subset for c in r['calls']]
        usage=Counter()
        for c in calls:
            for k,v in (c['usage'] or {}).items():
                if isinstance(v,(int,float)) and not isinstance(v,bool): usage[k]+=v
        efficiency[arm]={'provider_attempts':len(calls),'usage_totals':dict(usage),
            'calls_without_usage':sum(c['usage'] is None for c in calls),
            'returned_models':dict(Counter(str(c['returned_model']) for c in calls)),
            'provider_elapsed_seconds_serial_equivalent':sum(c['elapsed_seconds'] for c in calls),
            'per_unit_wall_seconds':distribution([r['unit_elapsed_seconds'] for r in subset]),
            'warning':'parallel duration sums are NOT batch wall time; no billing amount inferred'}
    source_safety={arm:{'packet_ineligible_local_entries':sum(len(d['packet_unsafe_local_entries']) for d in detail if d['arm']==arm),
        'packet_affected_units':sum(bool(d['packet_unsafe_local_entries']) for d in detail if d['arm']==arm),
        'unsafe_citation_entries':sum(len(d['unsafe_local_citation_ids']) for d in detail if d['arm']==arm),
        'unsafe_citation_units':sum(bool(d['unsafe_local_citation_ids']) for d in detail if d['arm']==arm)} for arm in ARMS}
    task_adherence={arm:{'runtime_task_types':dict(Counter((d['review_task'] or {}).get('task_type','not_enabled') for d in detail if d['arm']==arm)),
        'gated_claim_scopes':dict(Counter(d['finding'].get('claim_scope','not_reported') for d in detail if d['arm']==arm)),
        'gate_changed_observation_count':sum(d['raw']!=d['gated'] for d in detail if d['arm']==arm),
        'length_truncations':sum(d['finish_reason']=='length' for d in detail if d['arm']==arm)} for arm in ARMS}
    report={'scope':'development-exposed REAL45; fixed-corpus two-factor comparison, not independent validation',
        'new_expert_B_scores':False,'reference_file_sha256':file_digest(args.references),
        'run_manifest':manifest,'completion':completion,'summary':summaries,'contrasts':comparisons,
        'interaction_agreement_difference':interaction,'efficiency':efficiency,'source_safety':source_safety,'task_adherence':task_adherence,
        'rows':rows,'detail':detail,'cost_rows':cost_rows,'source_integrity':integrity,
        'recall_at_5':None,'mrr':None,'retrieval_metric_reason':'no exhaustive verified REAL45 relevance judgments',
        'p_values':None,'inference_boundary':'three projects, one API generation per arm/unit; descriptive only'}
    write_new_json(args.output/'analysis.private.json',report)
    print(json.dumps({'summary':summaries,'source_safety':source_safety,'output':str(args.output)},ensure_ascii=False))


if __name__=='__main__': main()
