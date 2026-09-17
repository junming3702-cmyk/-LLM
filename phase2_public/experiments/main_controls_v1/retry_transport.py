"""Consent-gated, separate sensitivity run. Never replaces primary observations."""
from pathlib import Path
import argparse
import json
import os
import sys
import time

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
sys.path.insert(0, str(PACKAGE / 'src'))
from experiment_integrity import (RunJournal, code_inventory, digest, file_digest,
                                  validate_runtime, write_new_json, utc_now)

TRANSPORT_ERRORS = {'ProxyError', 'ConnectionError', 'ConnectTimeout', 'ReadTimeout', 'Timeout', 'SSLError'}

def is_transport_failure(result, observations):
    """No retries for bad labels, gate blocks, invalid JSON or HTTP errors alone."""
    if (result.get('gated_observation') or {}).get('status') != 'execution_failed':
        return False
    return any(o.get('ok') is False and o.get('http_status') is None
               and o.get('transport_error') in TRANSPORT_ERRORS for o in observations)

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--primary', type=Path, required=True)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--embedding-cache', type=Path, required=True)
    p.add_argument('--env-file', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--online-authorized-transport-once', action='store_true')
    args = p.parse_args()
    if not args.online_authorized_transport_once:
        p.error('separate transport-retry consent required')
    primary = read(args.primary / 'run_manifest.json')['binding']
    completion = read(args.primary / 'completion.json')  # primary batch must be finished
    assert completion['attempted_outputs'] == 135
    assert file_digest(args.inputs) == primary['input_sha256']
    assert file_digest(args.corpus) == primary['corpus_sha256']
    assert code_inventory(PACKAGE) == primary['production_code_inventory']
    for filename, expected in primary['experiment_code'].items():
        assert file_digest(HERE / filename) == expected
    rows = {r['issue_id']: r for r in read(args.inputs)}
    for row in rows.values(): validate_runtime(row)
    eligible = []
    for item in completion['outcomes']:
        path = args.primary / item['relative_path']
        assert file_digest(path) == item['sha256']
        result = read(path)
        observations = [read(f)['observation'] for f in
            (args.primary / 'audit' / item['method'] / item['issue_id'] / 'request_cache').glob('*.json')
            if not f.name.endswith('.started.json')]
        if is_transport_failure(result, observations):
            eligible.append({**item, 'primary_observations': observations})
    os.environ.update({'MODEL_PHASE_ROOT': str(PACKAGE), 'RAG_CORPUS_FILE': str(args.corpus),
        'EMBEDDING_MODEL_CACHE': str(args.embedding_cache), 'MODEL_ENV_FILE': str(args.env_file),
        'SYSTEM_PROMPT_FILE': str(PACKAGE / 'prompts/system_prompt_final.md'),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
        'HF_HOME': str(args.output / 'cache'), 'DEEPSEEK_API_URL': 'https://api.deepseek.com/v1/chat/completions'})
    import run_hierarchy_gated_llm_smoke as runner
    from controls import run_method
    prompt = (PACKAGE / 'prompts/system_prompt_final.md').read_text(encoding='utf-8')
    assert digest(prompt) == primary['prompt_sha256']
    binding = {'run_id': args.run_id, 'parent_run_id': primary['run_id'],
        'primary_manifest_sha256': file_digest(args.primary / 'run_manifest.json'),
        'retry_code_sha256': file_digest(Path(__file__)),
        'primary_binding': primary, 'consent': True, 'attempts_per_failed_arm': 1,
        'primary_analysis_unchanged': True, 'purpose': 'transport_failure_sensitivity_only'}
    write_new_json(args.output / 'retry_manifest.json', {'binding': binding,
        'eligible': [{k: v for k, v in x.items() if k != 'primary_observations'} for x in eligible],
        'started_at': utc_now()})
    retriever = None
    if any(x['method'] == 'strict_hierarchy' for x in eligible):
        import torch
        torch.set_num_threads(2)
        retriever = runner.StrictHierarchyHybridRetriever()
    flat = read(args.primary / 'flat_retrieval_packets.json')
    key = runner.load_api_key() if eligible else None
    outcomes = []
    for item in eligible:
        uid, method = item['issue_id'], item['method']
        expected_body = item['primary_observations'][0].get('request_body')
        class RetryJournal(RunJournal):
            def request(self, url, body, api_key, post, **kwargs):
                assert url == 'https://api.deepseek.com/v1/chat/completions'
                assert body['model'] == primary['requested_model']
                if len(self.current_calls) >= 6:
                    raise RuntimeError('retry_call_budget_exceeded')
                if method in {'llm_only', 'flat_hybrid'}:
                    assert body == expected_body, 'retry request differs from primary request'
                return super().request(url, body, api_key, post, **kwargs)
        journal = RetryJournal(args.output / 'audit' / method / uid, binding, max_attempts=1)
        tick = time.monotonic()
        print('TRANSPORT_RETRY_START ' + method + ' ' + uid, flush=True)
        with journal.case(uid):
            try:
                # Retain the original runtime run_id so baseline request bodies remain identical.
                result = run_method(method, rows[uid], retriever, flat[uid], key, prompt, primary['run_id'])
            except Exception as exc:
                result = {'issue_id': uid, 'experimental_method': method, 'execution_error': type(exc).__name__,
                    'raw_observation': {'status': 'execution_failed', 'verdict': None},
                    'gated_observation': {'status': 'execution_failed', 'verdict': None}}
        result['transport_retry_provenance'] = {'run_id': args.run_id, 'parent_result_sha256': item['sha256'],
            'input_hash': digest(rows[uid]), 'method': method, 'attempt': 2,
            'elapsed_seconds': time.monotonic() - tick, 'finished_at': utc_now(),
            'identical_request_body_asserted': method in {'llm_only', 'flat_hybrid'},
            'request_count': len(journal.current_calls), 'sensitivity_only': True}
        dest = args.output / 'results' / method / (uid + '.json')
        write_new_json(dest, result)
        outcomes.append({'method': method, 'issue_id': uid, 'status': result['gated_observation']['status'],
            'relative_path': str(dest.relative_to(args.output)), 'sha256': file_digest(dest)})
        print('TRANSPORT_RETRY_DONE ' + method + ' ' + uid + ' ' + result['gated_observation']['status'], flush=True)
    write_new_json(args.output / 'completion.json', {'outcomes': outcomes, 'finished_at': utc_now(),
        'eligible_count': len(eligible), 'retry_attempted': len(outcomes), 'primary_analysis_unchanged': True})
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
