"""Offline candidate-pool probing + saved-response gate sensitivity, NOT a new
LLM experiment. Expert labels are neither read nor sent to runtime. All paths
are explicit and outputs are exclusive-create. Keep results private.
"""
from pathlib import Path
from collections import Counter
from copy import deepcopy
from unittest.mock import patch
import argparse
import hashlib
import importlib.util
import json
import os
import socket
import sys
import time

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE / 'src'))
from experiment_integrity import digest, file_digest, validate_runtime, write_new_json, code_inventory
from scope_boundary_policy import ARMS, ScopePolicy, make_scope_registry, ContextFilteredRetriever, prepare_runtime, task_contract, geographic_decision


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def verdict(gate):
    findings = (gate.get('response') or {}).get('findings') or []
    return [x.get('conclusion_type') for x in findings]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--runtime-inputs', type=Path, required=True)
    p.add_argument('--saved-results', type=Path, required=True)
    p.add_argument('--embedding-cache', type=Path, required=True)
    p.add_argument('--baseline-code', type=Path, required=True)
    p.add_argument('--protected-manifest', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError('Use a fresh output directory; frozen observations are never overwritten')
    os.environ.update({'RAG_CORPUS_FILE': str(args.corpus), 'EMBEDDING_MODEL_CACHE': str(args.embedding_cache),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'TOKENIZERS_PARALLELISM': 'false',
        'HF_HOME': str(args.output/'cache')})
    sys.dont_write_bytecode = True
    rows = read(args.runtime_inputs)
    assert rows and len({r['issue_id'] for r in rows}) == len(rows)
    for row in rows:
        validate_runtime(row)
    protected = read(args.protected_manifest)['before']
    protected = {**protected, str(args.runtime_inputs): file_digest(args.runtime_inputs),
                 str(args.corpus): file_digest(args.corpus)}
    for f in (args.baseline_code/'src').glob('*.py'):
        protected[str(f)] = file_digest(f)
    for name, expected in protected.items():
        assert file_digest(name) == expected, 'Input changed since freeze: ' + name
    write_new_json(args.output/'source_integrity_before.private.json', protected)
    manifest = {'experiment': 'scope-boundary-v1', 'arms': {k: ScopePolicy.for_arm(k).flags() for k in ARMS},
        'baseline_code': str(args.baseline_code), 'candidate_code': code_inventory(PACKAGE),
        'input_sha256': file_digest(args.runtime_inputs), 'corpus_sha256': file_digest(args.corpus),
        'expert_labels_read': False, 'new_model_calls': 0, 'external_retrieval_calls': 0,
        'corpus_expansion': False, 'unit_count': len(rows),
        'design': 'All-level offline candidate probing (not live sequential triage); separately replay identical saved raw responses through gates.',
        'performance_claims': 'No new accuracy, Recall@5, MRR, end-to-end efficiency or generalisation estimate.',
        'independent_holdout': False, 'max_wall_seconds': 900}
    write_new_json(args.output/'experiment_manifest.private.json', manifest)
    started = time.monotonic()
    def no_network(*_a, **_k):
        raise RuntimeError('network_disabled_for_scope_boundary_validation')
    with patch.object(socket.socket, 'connect', no_network), patch.object(socket, 'create_connection', no_network):
        import torch
        torch.set_num_threads(2)
        from hierarchy_cascade_retriever import StrictHierarchyHybridRetriever, LEVEL_ORDER
        from llm_abstention_gate import apply_gate
        from scope_boundary_policy import geographic_decision
        spec = importlib.util.spec_from_file_location('frozen_gate_baseline', args.baseline_code/'src/llm_abstention_gate.py')
        original_gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(original_gate)
        print('LOADING_LOCAL_EMBEDDINGS', flush=True)
        base = StrictHierarchyHybridRetriever()
        class CachedEncoder:
            def __init__(self, inner): self.inner, self.values = inner, {}
            def encode(self, texts, **kwargs):
                key = (tuple(texts), digest(kwargs))
                if key not in self.values:
                    self.values[key] = self.inner.encode(texts, **kwargs)
                return self.values[key]
        base.model = CachedEncoder(base.model)
        registry = make_scope_registry(base.corpus)
        write_new_json(args.output/'source_scope_overlay.private.json', registry)
        corpus_before = digest(base.corpus)
        rankings, replay, documents = [], [], []
        for pos, row in enumerate(rows, 1):
            if time.monotonic() - started > 900:
                raise TimeoutError('registered_offline_timeout')
            uid, ctx = row['issue_id'], row['runtime_project_context']
            filtered = ContextFilteredRetriever(base, ctx, ScopePolicy(True, False, registry))
            unit_rankings = {}
            for level in LEVEL_ORDER:
                for phase in ('primary', 'supplement'):
                    before = base.retrieve_many(row['retrieval_queries'], level=level, phase=phase, top_k=5)
                    after = filtered.retrieve_many(row['retrieval_queries'], level=level, phase=phase, top_k=5)
                    key = level + '/' + phase
                    unit_rankings[key] = {'baseline': before, 'geo_only': after,
                        'task_only_reuses': 'baseline', 'geo_task_reuses': 'geo_only'}
                    for candidate in after:
                        assert geographic_decision(candidate, ctx, registry)['allowed']
                    if level != 'Level 4':
                        assert before == after, 'Unexpected nonlocal ranking change in frozen corpus'
            rankings.append({'issue_id': uid, 'project_id': row['project_id'], 'pools': unit_rankings,
                'scope_filter_audit': filtered.audit})
            saved_path = args.saved_results/(uid+'.json')
            saved = read(saved_path)
            protected[str(saved_path)] = file_digest(saved_path)
            original_runtime = saved.get('runtime_input') or {}
            raw = (saved.get('final_llm_response') or {}).get('parsed')
            if raw is None or not original_runtime:
                replay.append({'issue_id': uid, 'status': 'unreplayable_original_failure_retained', 'arms': {}})
                print('PROBED', pos, uid, 'unreplayable', flush=True)
                continue
            validate_runtime(original_runtime)
            frozen_result = original_gate.apply_gate(raw, original_runtime)
            compatibility = apply_gate(raw, original_runtime)
            assert compatibility == frozen_result, 'Opt-out gate changed'
            snapshots = {}
            original_digest = digest(original_runtime)
            raw_digest = digest(raw)
            for arm in ARMS:
                policy = ScopePolicy.for_arm(arm, registry)
                prepared = prepare_runtime(original_runtime, policy)
                gate = apply_gate(raw, prepared)
                snapshots[arm] = {'conclusions': verdict(gate), 'blocked': gate.get('blocked'),
                    'runtime': prepared, 'gate': gate,
                    'stale_model_response_reused': True, 'new_reasoning_performed': False}
                # Determinism on identical inputs, not fresh stochastic inference.
                assert gate == apply_gate(raw, prepared), 'Non-deterministic gate replay'
            assert digest(original_runtime) == original_digest and digest(raw) == raw_digest
            replay.append({'issue_id': uid, 'status': 'replayed', 'arms': snapshots,
                'opt_out_exact_compatibility': True,
                'saved_gate_exact_match': compatibility == saved.get('post_llm_gate')})
            documents.append({'issue_id': uid, 'project_id': row['project_id'],
                'task': task_contract(original_runtime),
                'original_local_count': sum(geographic_decision(x, ctx, registry)['is_local'] for x in original_runtime.get('retrieved_legal_evidence', [])),
                'removed_from_saved_packet': snapshots['geo_only']['runtime'].get('geographic_admission_audit', {}).get('excluded', []),
                'conclusions': {arm: v['conclusions'] for arm, v in snapshots.items()},
                'task_observations': [f.get('runtime_task_boundary') for f in snapshots['task_only']['gate']['response'].get('findings', [])]})
            assert digest(base.corpus) == corpus_before
            print('PROBED', pos, uid, flush=True)
        for name, expected in protected.items():
            assert file_digest(name) == expected, 'Protected source modified'
        write_new_json(args.output/'candidate_rankings.private.json', rankings)
        write_new_json(args.output/'gate_sensitivity.private.json', replay)
        write_new_json(args.output/'unit_audit.private.json', documents)
        completed = [r for r in replay if r['status'] == 'replayed']
        summary = {'unit_count': len(rows), 'replayable': len(completed),
            'original_failures_retained': len(replay)-len(completed),
            'opt_out_gate_exact_compatibility': all(r['opt_out_exact_compatibility'] for r in completed),
            'saved_gate_exact_match_count': sum(r['saved_gate_exact_match'] for r in completed),
            'saved_packet_units_with_exclusions': sum(bool(d['removed_from_saved_packet']) for d in documents),
            'saved_packet_excluded_entries': sum(len(d['removed_from_saved_packet']) for d in documents),
            'saved_packet_exclusion_reasons': dict(Counter(x['reason'] for d in documents for x in d['removed_from_saved_packet'])),
            'task_types': dict(Counter(d['task']['task_type'] for d in documents)),
            'replayed_verdict_changes_vs_baseline': {arm: sum(r['arms'][arm]['conclusions'] != r['arms']['baseline']['conclusions'] for r in completed) for arm in ARMS},
            'new_model_calls': 0, 'network_enabled': False, 'law_chunks_added': 0,
            'nonlocal_ranking_unchanged': True, 'per_request_base_corpus_unchanged': True,
            'protected_file_count': len(protected), 'protected_files_unchanged': True,
            'elapsed_seconds_not_efficiency_benchmark': time.monotonic()-started,
            'labels_read': False, 'legal_accuracy_evaluated': False}
        write_new_json(args.output/'summary.private.json', summary)
        write_new_json(args.output/'source_integrity_after.private.json', {'all_unchanged': True, 'hashes': protected})
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
