"""Fresh prompt comparison on identical frozen geo+task evidence packets.

Two prompt arms, each with one fresh final generation; both deterministic
gates are applied to each raw answer. This isolates prompting from gating.
No retrieval, external fallback, expert data or reference answers are read.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
from collections import Counter
import argparse
import json
import os
import sys
import threading
import time

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE/'src'))
sys.path.insert(0, str(PACKAGE/'experiments/main_controls_v1'))
from experiment_integrity import (RunJournal, code_inventory, digest, file_digest,
    validate_runtime, write_new_json, utc_now)
from scope_boundary_policy import TASK_PROMPT
from risk_binding_policy import PROMPT as BINDING_PROMPT, VERSION
from controls import FINAL_OVERRIDE, semantic_observation
from llm_abstention_gate import apply_gate

ARMS = ('original_prompt', 'binding_prompt')
RUNTIME_KEYS = {'run_id','project_id','issue_id','review_scope','project_context',
    'contract_evidence','hierarchy_retrieval_audit','local_search_completion',
    'external_retrieval_audit','external_sources_used','retrieved_legal_evidence',
    'retrieval_queries','triage_binding','runtime_constraints','scope_boundary_experiment',
    'geographic_prefilter_audit','geographic_admission_audit','review_task_contract'}


def select_runtime(source):
    runtime = deepcopy(source['runtime_input'])
    if set(runtime) - RUNTIME_KEYS:
        raise ValueError('unapproved runtime keys')
    validate_runtime(runtime)
    if source['experimental_arm'] != 'geo_task' or runtime['issue_id'] != source['issue_id']:
        raise ValueError('unexpected source packet identity')
    flags = runtime.get('scope_boundary_experiment') or {}
    if not (flags.get('geographic_filter') and flags.get('task_boundary')):
        raise ValueError('not a geography+task packet')
    if (runtime.get('hierarchy_retrieval_audit') or {}).get('cascade_failure_level') not in (None,'','none'):
        raise ValueError('incomplete source retrieval')
    if runtime.get('external_sources_used'):
        raise ValueError('external material is not a fixed C0 packet')
    return runtime


def smoke_indices(rows):
    seen, indices = set(), []
    for i, row in enumerate(rows):
        if row['project_id'] not in seen:
            seen.add(row['project_id']); indices.append(i)
    return indices


def main():
    p = argparse.ArgumentParser()
    for field in ('source-run','env-file','output'):
        p.add_argument('--'+field, type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--preflight', action='store_true')
    p.add_argument('--online-authorized-runtime-only', action='store_true')
    args = p.parse_args()
    os.environ.update({'MODEL_PHASE_ROOT':str(PACKAGE), 'MODEL_ENV_FILE':str(args.env_file),
        'SYSTEM_PROMPT_FILE':str(PACKAGE/'prompts/system_prompt_final.md'),
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HF_HOME':str(args.output/'cache'),
        'DEEPSEEK_API_URL':'https://api.deepseek.com/v1/chat/completions'})
    sys.dont_write_bytecode = True
    # Import constructs no retriever and downloads no model.
    import run_hierarchy_gated_llm_smoke as runner
    completion = json.loads((args.source_run/'completion.json').read_text(encoding='utf-8'))
    if not completion['complete_attempts']:
        raise ValueError('source run incomplete')
    rows, source_hashes = [], {}
    for path in sorted((args.source_run/'results/geo_task').glob('*.json')):
        source = json.loads(path.read_text(encoding='utf-8'))
        rows.append(select_runtime(source)); source_hashes[str(path)] = file_digest(path)
    if len(rows) != 45 or len({r['issue_id'] for r in rows}) != 45:
        raise ValueError('expected complete 45 unique source packets')
    smokes = smoke_indices(rows)
    if len(smokes) != 3:
        raise ValueError('expected three project strata')
    prompt = ((PACKAGE/'prompts/system_prompt_final.md').read_text(encoding='utf-8')
              + FINAL_OVERRIDE + runner.FINAL_COMPACT_OUTPUT_CONTRACT + TASK_PROMPT)
    binding = {'run_id':args.run_id,'experiment':'fixed_packet_prompt_x_gate',
        'source_manifest_sha256':file_digest(args.source_run/'run_manifest.json'),
        'source_hashes':source_hashes, 'packet_hashes':{r['issue_id']:digest(r) for r in rows},
        'candidate_code':code_inventory(PACKAGE),'runner_sha256':file_digest(__file__),
        'helper_sha256':file_digest(PACKAGE/'experiments/main_controls_v1/controls.py'),
        'original_effective_prompt_sha256':digest(prompt),'overlay_sha256':digest(BINDING_PROMPT),
        'policy_version':VERSION,'requested_model':'deepseek-v4-flash',
        'max_tokens':16384,'temperature':0.1,'thinking_mode':'enabled','reasoning_effort':'low',
        'arms':list(ARMS),'planned_outputs':90,'gate_states':['original','risk_binding'],
        'max_parallel_units':3,'max_requests':90,'max_single_request_chars':220000,
        'max_total_request_chars':20000000,'max_reserved_output_tokens':1474560,
        'max_wall_seconds':7200,'primary_attempts':1,'automatic_retries':0,
        'smoke_issue_ids':[rows[i]['issue_id'] for i in smokes],
        'smoke_included_in_main':True,'method_order':'cyclic_by_input_index',
        'external_retrieval':'disabled','retrieval_rerun':False,'corpus_changed':False,
        'independent_holdout':False,'expert_data_accessed':False,
        'online_authorization':args.online_authorized_runtime_only}
    if args.preflight:
        write_new_json(args.output/'preflight.json',binding)
        print('PREFLIGHT_READY 90 final generations; no API calls',flush=True)
        return 0
    if not args.online_authorized_runtime_only:
        p.error('explicit runtime-only authorization required')
    if json.loads((args.output/'preflight.json').read_text(encoding='utf-8')) != binding:
        raise ValueError('preflight binding changed')
    write_new_json(args.output/'run_manifest.json',{'binding':binding,'started_at':utc_now(),'pid':os.getpid()})
    write_new_json(args.output/'effective_prompts.private.json',
        {'original_prompt':prompt,'binding_prompt':prompt+BINDING_PROMPT})
    started, lock = time.monotonic(), threading.Lock()
    budgets = {'requests':0,'request_chars':0,'reserved_output_tokens':0}
    class BoundedJournal(RunJournal):
        def request(self,url,body,api_key,post,**kwargs):
            if url != 'https://api.deepseek.com/v1/chat/completions' or body['model'] != binding['requested_model']:
                raise ValueError('unapproved endpoint or model')
            size = len(json.dumps(body,ensure_ascii=False))
            with lock:
                if (time.monotonic()-started > binding['max_wall_seconds'] or
                    budgets['requests'] >= binding['max_requests'] or
                    size > binding['max_single_request_chars'] or
                    budgets['request_chars']+size > binding['max_total_request_chars'] or
                    budgets['reserved_output_tokens']+body['max_tokens'] > binding['max_reserved_output_tokens']):
                    raise RuntimeError('registered_budget_exceeded')
                budgets['requests']+=1; budgets['request_chars']+=size
                budgets['reserved_output_tokens']+=body['max_tokens']
            return super().request(url,body,api_key,post,**kwargs)
    key = runner.load_api_key()
    def one(i):
        row = rows[i]; uid = row['issue_id']; out = []
        arms = ARMS[i % 2:] + ARMS[:i % 2]
        for arm in arms:
            tick = time.monotonic()
            print('START '+arm+' '+uid,flush=True)
            runtime = deepcopy(row)
            journal = BoundedJournal(args.output/'audit'/arm/uid,{**binding,'arm':arm},max_attempts=1)
            with journal.case(uid):
                result = {'issue_id':uid,'experimental_arm':arm,'runtime_input':runtime}
                try:
                    response, _ = runner.run_final_reasoning(api_key=key, prompt=prompt,
                        runtime_input=runtime,max_tokens=16384,risk_binding=(arm=='binding_prompt'))
                    result['final_llm_response'] = response
                    raw = response.get('parsed')
                    if raw is None: raw = response.get('selected_text','')
                    result['post_llm_gate'] = apply_gate(raw,runtime)
                    result['binding_gate'] = apply_gate(raw,runtime,risk_binding=True)
                except Exception as exc:
                    result['execution_error'] = type(exc).__name__
                if digest(runtime) != digest(row):
                    raise ValueError('fixed evidence packet mutated')
                result['raw_observation'] = semantic_observation(result,True)
                result['gated_observation'] = semantic_observation(result)
                result['binding_observation'] = semantic_observation({**result,'post_llm_gate':result.get('binding_gate')})
                result['experiment_provenance'] = {'packet_sha256':digest(row),
                    'elapsed_seconds':time.monotonic()-tick,'finished_at':utc_now(),
                    'request_count':len(journal.current_calls),'expert_data_accessed':False}
                write_new_json(args.output/'results'/arm/(uid+'.json'),result)
            item = {'arm':arm,'issue_id':uid,'status':result['raw_observation']['status']}
            with lock:
                with (args.output/'progress.jsonl').open('a',encoding='utf-8') as handle:
                    handle.write(json.dumps({**item,'at':utc_now()})+'\n')
            print('DONE '+arm+' '+uid+' '+item['status'],flush=True); out.append(item)
        return out
    outcomes = []
    for i in smokes: outcomes.extend(one(i))
    smoke_ok = all(r['status']=='completed' for r in outcomes)
    write_new_json(args.output/'smoke_check.json',{'passed':smoke_ok,'outcomes':outcomes,'included_in_primary':True})
    if smoke_ok:
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(one,i) for i in range(len(rows)) if i not in smokes]):
                outcomes.extend(future.result())
    unchanged = all(file_digest(path)==sha for path,sha in source_hashes.items())
    completion = {'outcomes':outcomes,'counts':dict(Counter(r['status'] for r in outcomes)),
        'complete_attempts':len(outcomes)==90,'smoke_passed':smoke_ok,
        'budgets':budgets,'elapsed_seconds':time.monotonic()-started,'finished_at':utc_now(),
        'source_packets_unchanged':unchanged,'expert_data_accessed':False,'automatic_retries':0}
    write_new_json(args.output/'completion.json',completion)
    print(json.dumps({k:v for k,v in completion.items() if k!='outcomes'}),flush=True)
    return 0 if completion['complete_attempts'] and unchanged else 2


if __name__ == '__main__':
    raise SystemExit(main())
