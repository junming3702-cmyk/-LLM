"""Evaluation-only prompt/gate analysis with audited identical provider input."""
from pathlib import Path
from collections import Counter
import argparse
import json
import sys

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE/'src'))
sys.path.insert(0, str(PACKAGE/'experiments/main_controls_v1'))
from experiment_integrity import digest, file_digest, write_new_json, validate_runtime
from controls import semantic_observation
from analyse_factorial import load_reference, metrics, paired, collect_calls, distribution

ARMS = ('original_prompt','binding_prompt')
STAGES = ('raw','original_gate','binding_gate')


def check_request(body, runtime, prompt, binding):
    if (body.get('model') != binding['requested_model'] or body.get('max_tokens') != 16384
        or body.get('temperature') != .1 or body.get('reasoning_effort') != 'low'
        or body.get('thinking') != {'type':'enabled'}):
        raise ValueError('model parameter mismatch')
    messages = body.get('messages',[])
    if len(messages)!=2 or messages[0] != {'role':'system','content':prompt} or messages[1].get('role')!='user':
        raise ValueError('effective prompt mismatch')
    actual = json.loads(messages[1]['content'])
    validate_runtime(actual)
    if digest(actual) != digest(runtime):
        raise ValueError('provider evidence differs from frozen packet')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--references',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    completion=json.loads((args.run/'completion.json').read_text(encoding='utf-8'))
    if not completion['complete_attempts'] or not completion['source_packets_unchanged']:
        raise ValueError('incomplete or mutated batch; do not publish full-run metrics')
    manifest=json.loads((args.run/'run_manifest.json').read_text(encoding='utf-8'))
    binding=manifest['binding']
    prompts=json.loads((args.run/'effective_prompts.private.json').read_text(encoding='utf-8'))
    if digest(prompts['original_prompt'])!=binding['original_effective_prompt_sha256']:
        raise ValueError('original prompt hash mismatch')
    suffix=prompts['binding_prompt'].removeprefix(prompts['original_prompt'])
    if digest(suffix)!=binding['overlay_sha256']:
        raise ValueError('candidate prompt hash mismatch')
    references=load_reference(args.references)
    if set(references)!=set(binding['packet_hashes']): raise ValueError('reference set mismatch')
    if any(file_digest(path)!=sha for path,sha in binding['source_hashes'].items()):
        raise ValueError('source evidence changed after freeze')
    rows, detail, costs=[],[],[]
    for arm in ARMS:
        found={path.stem for path in (args.run/'results'/arm).glob('*.json')}
        if found!=set(references): raise ValueError('incomplete arm or unexpected result')
        for uid in sorted(references):
            path=args.run/'results'/arm/(uid+'.json')
            result=json.loads(path.read_text(encoding='utf-8'))
            runtime=result['runtime_input']
            if result['issue_id']!=uid or result['experimental_arm']!=arm:
                raise ValueError('identity mismatch')
            if digest(runtime)!=binding['packet_hashes'][uid]: raise ValueError('packet hash mismatch')
            final=result.get('final_llm_response') or {}
            audit_dir=args.run/'audit'/arm/uid
            requests=[]
            for cache in (audit_dir/'request_cache').glob('*.json'):
                if cache.name.endswith('.started.json'): continue
                saved=json.loads(cache.read_text(encoding='utf-8'))
                if digest(saved['observation'])!=saved['observation_hash']: raise ValueError('request hash mismatch')
                request=saved['observation']['request_body']
                check_request(request,runtime,prompts[arm],binding)
                requests.append(request)
            calls=collect_calls(audit_dir)
            if len(requests)!=1 or len(calls)!=1: raise ValueError('not exactly one primary attempt')
            if result['experiment_provenance']['request_count']!=1: raise ValueError('call count mismatch')
            computed={'raw':semantic_observation(result,True),
                'original_gate':semantic_observation(result),
                'binding_gate':semantic_observation({**result,'post_llm_gate':result.get('binding_gate')})}
            for stage,observation in computed.items():
                rows.append({'unit_id':uid,'project':runtime['project_id'],
                    'reference':references[uid],'arm':arm,'stage':stage,**observation})
            costs.append({'arm':arm,'unit_id':uid,'calls':calls,
                'unit_elapsed_seconds':result['experiment_provenance']['elapsed_seconds']})
            parsed = final.get('parsed')
            detail.append({'arm':arm,'unit_id':uid,'reference':references[uid],
                'project':runtime['project_id'],'observations':computed,
                'contract_evidence':runtime.get('contract_evidence'),
                'raw_findings':parsed.get('findings',[]) if isinstance(parsed,dict) else [],
                'original_gate':result.get('post_llm_gate'),'binding_gate':result.get('binding_gate'),
                'finish_reason':final.get('finish_reason'),'response_channel_diagnostics':final.get('response_channel_diagnostics'),
                'source_file':str(path),'source_sha256':file_digest(path),
                'human_review_status':'requires_human_second_review; no inherited expert B score'})
    summary={arm:{stage:{'all':metrics([r for r in rows if r['arm']==arm and r['stage']==stage]),
        'projects':{pid:metrics([r for r in rows if r['arm']==arm and r['stage']==stage and r['project']==pid])
        for pid in sorted({r['project'] for r in rows})}} for stage in STAGES} for arm in ARMS}
    contrasts=[paired(rows,*ARMS,stage) for stage in STAGES]
    for arm in ARMS:
        recoded=[{**r,'arm':r['stage'],'stage':'within_raw_response'} for r in rows if r['arm']==arm]
        contrast=paired(recoded,'original_gate','binding_gate','within_raw_response')
        contrast['prompt_arm']=arm; contrasts.append(contrast)
    efficiency={}
    for arm in ARMS:
        subset=[r for r in costs if r['arm']==arm]; calls=[c for r in subset for c in r['calls']]
        usage=Counter()
        for c in calls:
            for k,v in (c['usage'] or {}).items():
                if isinstance(v,(int,float)) and not isinstance(v,bool): usage[k]+=v
        efficiency[arm]={'provider_attempts':len(calls),'usage_totals':dict(usage),
            'calls_without_usage':sum(c['usage'] is None for c in calls),
            'returned_models':dict(Counter(str(c['returned_model']) for c in calls)),
            'unit_wall_seconds':distribution([r['unit_elapsed_seconds'] for r in subset]),
            'final_only_not_end_to_end':True}
    answer={'experiment':'fixed_packet_prompt_x_gate','reference_sha256':file_digest(args.references),
        'manifest':manifest,'completion':completion,'summary':summary,'contrasts':contrasts,
        'efficiency':efficiency,'rows':rows,'detail':detail,'cost_rows':costs,
        'actual_request_packet_and_prompt_verified':True,'independent_holdout':False,
        'recall_at_5':None,'mrr':None,'new_expert_B_scores':False,'p_values':None,
        'limits':['45 exposed development units nested in three projects.',
                  'One new generation per prompt arm, two deterministic gate observations per generation.',
                  'No fresh retrieval or corpus expansion; cannot claim end-to-end retrieval gains.',
                  'Failures retained in all denominators; no selective retries or reference relabelling.']}
    write_new_json(args.output/'analysis.private.json',answer)
    print(json.dumps({'summary':summary,'efficiency':efficiency},ensure_ascii=False))


if __name__=='__main__': main()
