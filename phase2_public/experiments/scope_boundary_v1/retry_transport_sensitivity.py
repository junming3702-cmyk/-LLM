"""One separate repeat of transport-failed units, never a primary replacement.

The completed primary batch decides eligibility without reading any reference.
Use the original frozen package, corpus, input, model and parameters. A complete
unit is repeated (successful units are not); this is explicitly a stochastic
sensitivity run, not an exact replay of the successful prefix of API calls.
"""
from pathlib import Path
import argparse
import json
import os
import sys
import time

RETRYABLE_ERRORS = {'ProxyError', 'Timeout', 'ConnectTimeout', 'ReadTimeout',
                    'ConnectionError', 'ChunkedEncodingError'}
RETRYABLE_HTTP = {429, 502, 503, 504}


def transport_eligible(result, observations):
    """No schema, truncation, legal error or successful unit may be selected."""
    if (result.get('gated_observation') or {}).get('status') != 'execution_failed':
        return False
    return any(not o.get('ok') and (o.get('transport_error') in RETRYABLE_ERRORS
               or o.get('http_status') in RETRYABLE_HTTP) for o in observations)


def main():
    p = argparse.ArgumentParser()
    for name in ('primary', 'frozen-package', 'inputs', 'corpus', 'embedding-cache',
                 'env-file', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--online-authorized-runtime-only', action='store_true')
    p.add_argument('--preflight', action='store_true')
    a = p.parse_args()
    package = a.frozen_package.resolve()
    sys.path.insert(0, str(package/'src'))
    from experiment_integrity import (RunJournal, code_inventory, digest,
        file_digest, write_new_json, utc_now, validate_runtime)
    from scope_boundary_policy import ScopePolicy, TASK_PROMPT
    read = lambda path: json.loads(Path(path).read_text(encoding='utf-8'))
    primary = read(a.primary/'run_manifest.json')
    completion = read(a.primary/'completion.json')
    b = primary['binding']
    if not completion['complete_attempts']:
        raise ValueError('primary attempts must finish before sensitivity selection')
    checks = {
        'code': code_inventory(package) == b['candidate_code'],
        'inputs': file_digest(a.inputs) == b['input_sha256'],
        'corpus': file_digest(a.corpus) == b['corpus_sha256'],
        'task_overlay': digest(TASK_PROMPT) == b['task_overlay_sha256'],
        'helpers': file_digest(package/'experiments/main_controls_v1/controls.py')
                   == b['comparison_helpers_sha256'],
        'model': b['requested_model'] == 'deepseek-v4-flash',
        'external': b['external_retrieval'] == 'disabled_fixed_corpus_factorial',
    }
    if not all(checks.values()):
        raise ValueError('frozen binding changed: '+str(checks))
    rows = read(a.inputs)
    for row in rows: validate_runtime(row)
    by_id = {r['issue_id']:r for r in rows}
    selected = []
    for item in completion['outcomes']:
        arm, uid = item['arm'], item['issue_id']
        path = a.primary/'results'/arm/(uid+'.json')
        result = read(path)
        observations = []
        for cache in sorted((a.primary/'audit'/arm/uid/'request_cache').glob('*.json')):
            if cache.name.endswith('.started.json'): continue
            record = read(cache)
            if digest(record['observation']) != record['observation_hash']:
                raise ValueError('primary audit integrity failure')
            observations.extend(record['observation'].get('attempts', []))
        if transport_eligible(result, observations):
            selected.append({'arm':arm, 'issue_id':uid,
                'primary_result_sha256':file_digest(path)})
    binding = {'primary_manifest_sha256':file_digest(a.primary/'run_manifest.json'),
        'primary_completion_sha256':file_digest(a.primary/'completion.json'),
        'primary_binding':b, 'selected':selected,
        'selection':'execution_failed AND audited transient transport failure; no reference access',
        'unit_repeat_limit':1, 'request_attempts':1,
        'primary_overwritten':False, 'expert_data_accessed':False,
        'online_authorization':a.online_authorized_runtime_only,
        'runner_sha256':file_digest(__file__)}
    if a.preflight:
        write_new_json(a.output/'preflight.json', binding)
        print(json.dumps({'eligible':selected,'calls':0}, ensure_ascii=False))
        return
    if not a.online_authorized_runtime_only:
        p.error('runtime-only online authorization required')
    if read(a.output/'preflight.json') != binding:
        raise ValueError('sensitivity preflight changed')
    # Exclusive manifest prevents another repeat under the same experiment.
    write_new_json(a.output/'run_manifest.json', {'binding':binding,'started_at':utc_now()})
    os.environ.update({'MODEL_PHASE_ROOT':str(package),'RAG_CORPUS_FILE':str(a.corpus),
        'EMBEDDING_MODEL_CACHE':str(a.embedding_cache),'MODEL_ENV_FILE':str(a.env_file),
        'SYSTEM_PROMPT_FILE':str(package/'prompts/system_prompt_final.md'),
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','TOKENIZERS_PARALLELISM':'false',
        'HF_HOME':str(a.output/'cache'),'DEEPSEEK_API_URL':'https://api.deepseek.com/v1/chat/completions'})
    sys.dont_write_bytecode = True
    import torch
    torch.set_num_threads(2)
    import run_hierarchy_gated_llm_smoke as runner
    from external_fallback_v2 import ExternalFallbackStateMachine
    sys.path.insert(0, str(package/'experiments/main_controls_v1'))
    from controls import semantic_observation, FINAL_OVERRIDE
    base = runner.StrictHierarchyHybridRetriever() if selected else None
    registry = read(a.primary/'source_scope_overlay.json')
    prompt = (package/'prompts/system_prompt_final.md').read_text(encoding='utf-8')
    key = runner.load_api_key() if selected else None
    started = time.monotonic()
    class BoundedJournal(RunJournal):
        def request(self, url, body, api_key, post, **kwargs):
            if (url != 'https://api.deepseek.com/v1/chat/completions' or
                body['model'] != b['requested_model'] or
                len(self.current_calls) >= 9 or time.monotonic()-started > 3600 or
                len(json.dumps(body,ensure_ascii=False)) > b['max_single_request_chars']):
                raise ValueError('sensitivity request boundary exceeded')
            return super().request(url, body, api_key, post, **kwargs)
    outcomes = []
    for item in selected:
        arm, uid = item['arm'], item['issue_id']
        journal = BoundedJournal(a.output/'audit'/arm/uid, {**binding,**item},max_attempts=1)
        tick = time.monotonic()
        with journal.case(uid):
            try:
                result = runner.run_case(api_key=key, retriever=base,
                    final_prompt=prompt+FINAL_OVERRIDE, context_template={},label=by_id[uid],
                    top_k=b['top_k_per_level_phase'],final_max_tokens=b['final_max_tokens'],
                    triage_max_tokens=b['triage_max_tokens'],compact_final_output=True,
                    experiment_run_id=b['run_id'],
                    external_fallback=ExternalFallbackStateMachine(enabled=False,provider=None),
                    scope_policy=ScopePolicy.for_arm(arm,registry))
            except Exception as exc:
                result = {'issue_id':uid,'execution_error':type(exc).__name__}
            result['experimental_arm'] = arm
            result['raw_observation'] = semantic_observation(result, True)
            result['gated_observation'] = semantic_observation(result)
            result['experiment_provenance'] = {'input_sha256':digest(by_id[uid]),
                'arm':arm,'elapsed_seconds':time.monotonic()-tick,'finished_at':utc_now(),
                'request_count':len(journal.current_calls),'expert_data_accessed':False,
                'sensitivity_only':True, 'primary_result_sha256':item['primary_result_sha256']}
            write_new_json(a.output/'results'/arm/(uid+'.json'),result)
        outcomes.append({**item, 'status':result['gated_observation']['status']})
        print('SENSITIVITY_DONE '+arm+' '+uid+' '+outcomes[-1]['status'],flush=True)
    write_new_json(a.output/'completion.json',{'outcomes':outcomes,
        'attempted':len(outcomes),'repeat_limit':1,'primary_unchanged':True,
        'elapsed_seconds':time.monotonic()-started,'finished_at':utc_now()})


if __name__ == '__main__': main()
