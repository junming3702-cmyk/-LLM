"""Consent-scoped four-arm runtime-only experiment, with fixed corpus.

Reads no expert/reference files. Primary attempts are never overwritten. The
journal preserves every request, raw response, failure and gate modification.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import json
import os
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
sys.path.insert(0, str(PACKAGE/'src'))
from experiment_integrity import (RunJournal, code_inventory, digest, file_digest,
    validate_runtime, write_new_json, utc_now)
from scope_boundary_policy import ARMS, ScopePolicy, make_scope_registry, TASK_PROMPT

ALLOWED_INPUT_KEYS = {'issue_id','project_id','document_id','document_location','document_excerpt',
    'runtime_project_context','retrieval_queries','external_legal_query_terms','external_query_ids'}


def order_for(index, arms):
    shift = index % len(arms)
    return arms[shift:] + arms[:shift]


def validate_rows(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError('nonempty runtime list required')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not set(row) <= ALLOWED_INPUT_KEYS:
            raise ValueError('unapproved runtime fields')
        uid = row.get('issue_id')
        if not isinstance(uid, str) or not uid or any(c in uid for c in '/\\:'):
            raise ValueError('unsafe issue identifier')
        if uid in seen:
            raise ValueError('duplicate issue identifier')
        seen.add(uid)
        for field in ('document_id', 'document_location', 'document_excerpt'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError('missing runtime field: '+field)
        validate_runtime(row)


def main():
    p = argparse.ArgumentParser()
    for name in ['inputs','corpus','embedding-cache','env-file','output']:
        p.add_argument('--'+name, required=True, type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--online-authorized-runtime-only', action='store_true')
    args = p.parse_args()
    os.environ.update({'MODEL_PHASE_ROOT':str(PACKAGE),'RAG_CORPUS_FILE':str(args.corpus),
        'EMBEDDING_MODEL_CACHE':str(args.embedding_cache),'MODEL_ENV_FILE':str(args.env_file),
        'SYSTEM_PROMPT_FILE':str(PACKAGE/'prompts/system_prompt_final.md'),
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false',
        'HF_HOME':str(args.output/'cache'),'DEEPSEEK_API_URL':'https://api.deepseek.com/v1/chat/completions'})
    sys.dont_write_bytecode = True
    rows = json.loads(args.inputs.read_text(encoding='utf-8'))
    validate_rows(rows)
    arms = tuple(ARMS)
    prompt = (PACKAGE/'prompts/system_prompt_final.md').read_text(encoding='utf-8')
    binding = {'run_id':args.run_id,'input_sha256':file_digest(args.inputs),
        'corpus_sha256':file_digest(args.corpus),'candidate_code':code_inventory(PACKAGE),
        'runner_sha256':file_digest(__file__),'prompt_sha256':digest(prompt),
        'comparison_helpers_sha256':file_digest(PACKAGE/'experiments/main_controls_v1/controls.py'),
        'task_overlay_sha256':digest(TASK_PROMPT),
        'arms':{name:ScopePolicy.for_arm(name).flags() for name in arms},
        'requested_model':'deepseek-v4-flash','embedding_model':'BAAI/bge-small-zh-v1.5',
        'top_k_per_level_phase':5,'temperature':0.1,'final_max_tokens':16384,'triage_max_tokens':2048,
        'external_retrieval':'disabled_fixed_corpus_factorial','repeat_count':1,
        'primary_transport_attempts':1,'max_parallel_units':3,'max_wall_seconds':14400,
        'max_requests':9*len(rows)*len(arms),'max_request_chars':80000000,
        'max_reserved_output_tokens':6000000,'max_single_request_chars':220000,
        'method_order':'cyclic_per_input_index_no_outcome_selection','independent_holdout':False,
        'expert_data_accessed':False,'online_authorization':args.online_authorized_runtime_only,
        'planned_units':len(rows),'planned_outputs':len(rows)*len(arms)}
    if args.preflight:
        write_new_json(args.output/'preflight.json',binding)
        print('PREFLIGHT_READY '+str(binding['planned_outputs'])+' outputs; no API requests',flush=True)
        return 0
    if not args.online_authorized_runtime_only:
        p.error('explicit runtime-only online authorization required')
    assert json.loads((args.output/'preflight.json').read_text(encoding='utf-8')) == binding
    write_new_json(args.output/'run_manifest.json',{'binding':binding,'started_at':utc_now(),'pid':os.getpid()})
    import torch
    torch.set_num_threads(2)
    import run_hierarchy_gated_llm_smoke as runner
    from external_fallback_v2 import ExternalFallbackStateMachine
    sys.path.insert(0, str(PACKAGE/'experiments/main_controls_v1'))
    from controls import semantic_observation, FINAL_OVERRIDE
    print('LOADING_FIXED_LOCAL_EMBEDDINGS',flush=True)
    base = runner.StrictHierarchyHybridRetriever()
    registry = make_scope_registry(base.corpus)
    write_new_json(args.output/'source_scope_overlay.json',registry)
    class LockedEncoder:
        def __init__(self, model): self.model,self.lock=model,threading.Lock()
        def encode(self,*a,**kw):
            with self.lock: return self.model.encode(*a,**kw)
    # Lock only model encoding. Wrapping the retriever itself would invalidate
    # the per-request filtered copy's owned candidate indices.
    base.model = LockedEncoder(base.model)
    started = time.monotonic()
    lock = threading.Lock()
    budgets = {'requests':0,'request_chars':0,'reserved_output_tokens':0}
    class BoundedJournal(RunJournal):
        def request(self,url,body,api_key,post,**kwargs):
            assert url == 'https://api.deepseek.com/v1/chat/completions'
            assert body['model'] == binding['requested_model']
            size=len(json.dumps(body,ensure_ascii=False))
            with lock:
                if (time.monotonic()-started > binding['max_wall_seconds'] or
                    budgets['requests'] >= binding['max_requests'] or
                    budgets['request_chars']+size > binding['max_request_chars'] or
                    size > binding['max_single_request_chars'] or
                    budgets['reserved_output_tokens']+body['max_tokens'] > binding['max_reserved_output_tokens']):
                    raise RuntimeError('registered_budget_exceeded')
                budgets['requests']+=1;budgets['request_chars']+=size
                budgets['reserved_output_tokens']+=body['max_tokens']
            return super().request(url,body,api_key,post,**kwargs)
    key=runner.load_api_key()
    def one(index,row):
        collected=[]
        for arm in order_for(index,arms):
            uid=row['issue_id']; tick=time.monotonic()
            print('START '+arm+' '+uid,flush=True)
            journal=BoundedJournal(args.output/'audit'/arm/uid,{**binding,'arm':arm},max_attempts=1)
            with journal.case(uid):
                try:
                    result=runner.run_case(api_key=key,retriever=base,final_prompt=prompt+FINAL_OVERRIDE,
                        context_template={},label=row,top_k=5,final_max_tokens=16384,triage_max_tokens=2048,
                        compact_final_output=True,experiment_run_id=args.run_id,
                        external_fallback=ExternalFallbackStateMachine(enabled=False,provider=None),
                        scope_policy=ScopePolicy.for_arm(arm,registry))
                except Exception as exc:
                    result={'issue_id':uid,'execution_error':type(exc).__name__}
                result['experimental_arm']=arm
                result['raw_observation']=semantic_observation(result,True)
                result['gated_observation']=semantic_observation(result)
                result['experiment_provenance']={'input_sha256':digest(row),'arm':arm,
                    'elapsed_seconds':time.monotonic()-tick,'finished_at':utc_now(),
                    'request_count':len(journal.current_calls),'expert_data_accessed':False}
                write_new_json(args.output/'results'/arm/(uid+'.json'),result)
            item={'arm':arm,'issue_id':uid,'status':result['gated_observation']['status']}
            with lock:
                with (args.output/'progress.jsonl').open('a',encoding='utf-8') as handle:
                    handle.write(json.dumps({**item,'at':utc_now()})+'\n')
            print('DONE '+arm+' '+uid+' '+item['status'],flush=True)
            collected.append(item)
        return collected
    outcomes=one(0,rows[0])
    smoke_ok=all(r['status']=='completed' for r in outcomes)
    write_new_json(args.output/'smoke_check.json',{'outcomes':outcomes,'passed':smoke_ok,'included_in_primary_batch':True})
    if smoke_ok:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(one,i,r) for i,r in enumerate(rows[1:],1)]):
                outcomes.extend(future.result())
    from collections import Counter
    completion={'outcomes':outcomes,'counts':dict(Counter(r['status'] for r in outcomes)),
        'budgets':budgets,'elapsed_seconds':time.monotonic()-started,'finished_at':utc_now(),
        'complete_attempts':len(outcomes)==binding['planned_outputs'],'smoke_passed':smoke_ok,
        'all_completed':len(outcomes)==binding['planned_outputs'] and all(r['status']=='completed' for r in outcomes),
        'expert_data_accessed':False,'automatic_retries':0}
    write_new_json(args.output/'completion.json',completion)
    print(json.dumps({k:v for k,v in completion.items() if k!='outcomes'}),flush=True)
    return 0 if completion['complete_attempts'] else 2


if __name__=='__main__':
    raise SystemExit(main())
