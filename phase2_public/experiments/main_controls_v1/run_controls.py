"""Generic runner; explicitly authorized runtime-only packets; no expert reads."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
sys.path.insert(0, str(PACKAGE/'src'))
from experiment_integrity import RunJournal, code_inventory, digest, file_digest, validate_runtime, write_new_json, utc_now
from controls import METHODS, method_order

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--embedding-cache', type=Path, required=True)
    p.add_argument('--env-file', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--online-authorized-real45', action='store_true')
    p.add_argument('--preflight', action='store_true')
    args = p.parse_args()
    os.environ.update({'MODEL_PHASE_ROOT': str(PACKAGE), 'RAG_CORPUS_FILE': str(args.corpus),
        'EMBEDDING_MODEL_CACHE': str(args.embedding_cache), 'MODEL_ENV_FILE': str(args.env_file),
        'SYSTEM_PROMPT_FILE': str(PACKAGE/'prompts/system_prompt_final.md'),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
        'HF_HOME': str(args.output/'cache'), 'DEEPSEEK_API_URL': 'https://api.deepseek.com/v1/chat/completions'})
    sys.dont_write_bytecode = True
    rows = json.loads(args.inputs.read_text(encoding='utf-8'))
    assert len(rows) == 45 and len({r['issue_id'] for r in rows}) == 45
    allowed = {'issue_id','project_id','document_id','document_location','document_excerpt','runtime_project_context','retrieval_queries','external_legal_query_terms','external_query_ids'}
    for row in rows:
        assert set(row) <= allowed
        validate_runtime(row)
    import torch
    torch.set_num_threads(2)
    import run_hierarchy_gated_llm_smoke as runner
    from controls import GlobalRanker, run_method, FINAL_OVERRIDE, LLM_ONLY_OVERRIDE
    prompt = (PACKAGE/'prompts/system_prompt_final.md').read_text(encoding='utf-8')
    binding = {'run_id': args.run_id, 'input_sha256': file_digest(args.inputs),
        'corpus_sha256': file_digest(args.corpus), 'production_code_inventory': code_inventory(PACKAGE),
        'experiment_code': {f.name: file_digest(f) for f in HERE.glob('*.py')},
        'prompt_sha256': digest(prompt), 'shared_override_sha256': digest(FINAL_OVERRIDE),
        'llm_only_override_sha256': digest(LLM_ONLY_OVERRIDE),
        'requested_model': 'deepseek-v4-flash', 'top_k_per_level_phase': 5, 'global_flat_budget': 25,
        'temperature': .1, 'final_max_tokens': 16384, 'triage_max_tokens': 2048,
        'external_policy': 'disabled_in_all_arms', 'transport_attempts': 1,
        'order': 'rotated_per_unit_index', 'repeat_count': 1,
        'expert_labels_or_scores_available': False, 'online_consent': args.online_authorized_real45}
    if args.preflight:
        write_new_json(args.output/'preflight.json', binding)
        print('PREFLIGHT_READY 45 units, 3 arms, no API request', flush=True)
        return 0
    if not args.online_authorized_real45:
        p.error('explicit REAL45 consent required')
    assert json.loads((args.output/'preflight.json').read_text(encoding='utf-8')) == binding
    write_new_json(args.output/'run_manifest.json', {'binding': binding, 'started_at': utc_now(), 'state': 'running'})
    print('LOADING_LOCAL_EMBEDDINGS', flush=True)
    retriever = runner.StrictHierarchyHybridRetriever()
    ranker = GlobalRanker(retriever)
    flat = {r['issue_id']: ranker.retrieve(r['retrieval_queries'], depth=25) for r in rows}
    write_new_json(args.output/'flat_retrieval_packets.json', flat)
    lock = threading.Lock()
    class LockedRetriever:
        def __getattr__(self, name): return getattr(retriever, name)
        def retrieve_many(self, *a, **kw):
            with lock: return retriever.retrieve_many(*a, **kw)
    frozen = LockedRetriever()
    started = time.monotonic()
    budget_lock = threading.Lock()
    budgets = {'requests': 0, 'request_chars': 0, 'output_tokens_reserved': 0}
    class BoundedJournal(RunJournal):
        def request(self, url, body, api_key, post, **kwargs):
            assert url == 'https://api.deepseek.com/v1/chat/completions' and body['model'] == 'deepseek-v4-flash'
            n = len(json.dumps(body, ensure_ascii=False))
            with budget_lock:
                if time.monotonic()-started > 7200 or budgets['requests'] >= 405 or n > 220000 or budgets['request_chars']+n > 24000000 or budgets['output_tokens_reserved']+body['max_tokens'] > 2703360:
                    raise RuntimeError('registered_budget_exceeded')
                budgets['requests'] += 1
                budgets['request_chars'] += n
                budgets['output_tokens_reserved'] += body['max_tokens']
            return super().request(url, body, api_key, post, **kwargs)
    key = runner.load_api_key()
    def one(index, row):
        outcomes = []
        for method in method_order(index):
            uid = row['issue_id']
            print('START '+method+' '+uid, flush=True)
            t = time.monotonic()
            journal = BoundedJournal(args.output/'audit'/method/uid, {**binding, 'method': method}, max_attempts=1)
            with journal.case(uid):
                try:
                    result = run_method(method, row, frozen, flat[uid], key, prompt, args.run_id)
                except Exception as exc:
                    result = {'issue_id': uid, 'experimental_method': method, 'execution_error': type(exc).__name__,
                              'raw_observation': {'status':'execution_failed','verdict':None},
                              'gated_observation': {'status':'execution_failed','verdict':None}}
                result['experiment_provenance'] = {'run_id': args.run_id, 'method': method,
                    'input_hash': digest(row), 'finished_at': utc_now(), 'elapsed_seconds': time.monotonic()-t,
                    'request_count': len(journal.current_calls), 'expert_data_accessed': False}
            dest = args.output/'results'/method/(uid+'.json')
            write_new_json(dest, result)
            item = {'method': method, 'issue_id': uid, 'status': result['gated_observation']['status'],
                    'sha256': file_digest(dest), 'relative_path': str(dest.relative_to(args.output))}
            outcomes.append(item)
            with budget_lock:
                with (args.output/'progress.jsonl').open('a', encoding='utf-8') as f:
                    f.write(json.dumps({**item,'at':utc_now()},ensure_ascii=False)+'\n')
            print('DONE '+method+' '+uid+' '+item['status'], flush=True)
        return outcomes
    first = one(0, rows[0])
    outcomes = list(first)
    if all(x['status'] == 'completed' for x in first):
        with ThreadPoolExecutor(max_workers=3) as pool:
            for future in as_completed([pool.submit(one, i, row) for i,row in enumerate(rows[1:],1)]):
                outcomes.extend(future.result())
    completion = {'finished_at': utc_now(), 'outcomes': outcomes, 'budgets': budgets,
        'elapsed_seconds': time.monotonic()-started, 'counts': dict(Counter(x['status'] for x in outcomes)),
        'planned_outputs': 135, 'attempted_outputs': len(outcomes),
        'complete': len(outcomes)==135 and all(x['status']=='completed' for x in outcomes),
        'expert_data_accessed': False, 'automatic_retries': 0}
    write_new_json(args.output/'completion.json', completion)
    print(json.dumps({k:v for k,v in completion.items() if k!='outcomes'}), flush=True)
    return 0 if completion['complete'] else 2

if __name__ == '__main__':
    raise SystemExit(main())
