"""Isolated, prospective controls. Runtime inputs never contain expert labels.

This compares implemented systems, not the isolated causal effect of hierarchy.
The sole component ablation is raw vs gated on the identical generated response.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import time

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE / 'src'))

METHODS = ('llm_only', 'flat_hybrid', 'strict_hierarchy')
FINAL_OVERRIDE = '''
## Registered comparison execution policy
Follow the actual experimental_method in the runtime. For flat_hybrid, the
retriever searched the same Level 1-4 corpus globally without sequential triage;
do not invent a cascade, an early-stop decision, or treat the absence of a
cascade audit as missing project facts. The same source roles, local
applicability requirements, fact-law comparison and human-review boundary apply.
External discovery is disabled in this controlled experiment, not completed
with no applicable law. Do not infer validity from an unsuccessful search.
For strict_hierarchy, follow the supplied, actually executed cascade audit.
'''
LLM_ONLY_OVERRIDE = '''
## LLM-only experimental baseline
No retrieval is performed in this arm. Use your internal legal knowledge when
you can identify a specific applicable provision, explicitly marking every such
citation as unverified parametric knowledge. Do not fabricate source locators,
chunk IDs, online verification or retrieval execution. Missing retrieved
evidence alone does not require abstention in this baseline. Missing decisive
facts, uncertain law/version/applicability still require abstention. This is
research output for human review, never a legal or award decision. For this arm
only, legal_evidence may contain law/article/quote with provenance
parametric_unverified instead of supplied chunk_id. A risk comparison may cite
law/article without claiming an admitted supporting_chunk_id. Keep the same
single-finding JSON schema and N/R/U-compatible conclusion states. The RAG
evidence-admission gate is NOT applied to this no-retrieval arm. Human legal
correctness cannot be established by the absence of in-package citations.
'''

def method_order(index):
    shift = index % len(METHODS)
    return METHODS[shift:] + METHODS[:shift]

def ordered_unique(ids):
    return list(dict.fromkeys(ids))

def semantic_observation(result, before_gate=False):
    from experiment_integrity import semantic_verdict
    response = result.get('final_llm_response') or {}
    if result.get('execution_error') or response.get('ok') is False:
        return {'status': 'execution_failed', 'verdict': None}
    if response.get('finish_reason') == 'length' or not isinstance(response.get('parsed'), dict):
        return {'status': 'invalid_output', 'verdict': None}
    if (result.get('runtime_input', {}).get('hierarchy_retrieval_audit') or {}).get('cascade_failure_level') not in (None, '', 'none'):
        return {'status': 'execution_failed', 'verdict': None}
    gate = result.get('post_llm_gate') or {}
    if not before_gate and gate.get('blocked'):
        return {'status': 'gate_blocked', 'verdict': None}
    parsed = response['parsed'] if before_gate else gate.get('response', response['parsed'])
    findings = parsed.get('findings', []) if isinstance(parsed, dict) else []
    verdict = semantic_verdict(findings[0].get('conclusion_type')) if len(findings) == 1 and isinstance(findings[0], dict) else None
    return {'status': 'completed' if verdict else 'invalid_output', 'verdict': verdict}

class GlobalRanker:
    """Same embeddings/lexical implementation; global, never gold-level routed."""
    def __init__(self, retriever):
        from hierarchy_cascade_retriever import LEVEL_ORDER
        from run_retrieval_test import build_index
        self.retriever = retriever
        self.indices = [i for i, r in enumerate(retriever.corpus) if r.get('normative_level') in LEVEL_ORDER]
        self.chunks = [retriever.corpus[i] for i in self.indices]
        self.index = build_index(self.chunks)
        self.query_cache = {}

    def rank_query(self, query, method):
        from run_retrieval_test import bm25_rank
        from hierarchy_cascade_retriever import RankedCandidate
        if query not in self.query_cache:
            lexical = bm25_rank(query, self.chunks, self.index[0], self.index[1], self.index[3])
            scores = {i: s for s, i in lexical}
            maximum = max(scores.values(), default=1) or 1
            q = self.retriever.model.encode([query], normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)[0]
            dense = self.retriever.embeddings[self.indices] @ q
            self.query_cache[query] = [(scores[i]/maximum, max(0.0, float(dense[i]))) for i in range(len(self.chunks))]
        scores = self.query_cache[query]
        rows = []
        for i, row in enumerate(self.chunks):
            bm, dense = scores[i]
            value = bm if method == 'bm25' else dense if method == 'dense' else .6*bm+.4*dense
            rows.append((value, i, bm, dense))
        rows.sort(key=lambda r: (-r[0], str(self.chunks[r[1]]['chunk_id'])))
        return [RankedCandidate(self.chunks[i], value, bm, dense).as_dict(rank)
                for rank, (value, i, bm, dense) in enumerate(rows, 1)]

    def retrieve(self, queries, method='hybrid', depth=25):
        clean = [str(q).strip() for q in queries if str(q).strip()]
        if not clean:
            raise ValueError('empty query')
        if len(clean) == 1:
            return self.rank_query(clean[0], method)[:depth]
        merged = {}
        for qi, query in enumerate(clean):
            for rank, row in enumerate(self.rank_query(query, method)[:depth], 1):
                v = merged.setdefault(row['chunk_id'], {'row': row, 'rrf': 0., 'best': -1., 'queries': []})
                v['rrf'] += 1/(60+rank)
                v['best'] = max(v['best'], row['retrieval_scores']['hybrid_score'])
                v['queries'].append({'query_index': qi+1, 'rank': rank})
        ordered = sorted(merged.values(), key=lambda x: (-x['rrf'], -x['best'], x['row']['chunk_id']))[:depth]
        return [{**x['row'], 'rank': i, 'query_hits': x['queries'], 'fusion_score': x['rrf']}
                for i, x in enumerate(ordered, 1)]

def flat_runtime(label, evidence, run_id):
    import run_hierarchy_gated_llm_smoke as runner
    from hierarchy_cascade_retriever import LEVEL_ORDER
    context = deepcopy(label['runtime_project_context'])
    admitted = [{**r, **runner.evidence_applicability(r, context)} for r in evidence]
    return {
        'run_id': run_id, 'project_id': label['project_id'], 'issue_id': label['issue_id'],
        'experimental_method': 'flat_hybrid',
        'project_context': context,
        'contract_evidence': {k: label[k] for k in ('document_id', 'document_location', 'document_excerpt')},
        'review_scope': {'documents_received': [label['document_id']], 'jurisdiction_status': 'confirmed'},
        'retrieval_queries': label['retrieval_queries'],
        'retrieved_legal_evidence': admitted,
        'flat_retrieval_audit': {'searched_levels': list(LEVEL_ORDER), 'status': 'completed',
                                 'candidate_budget': 25, 'sequential_triage_executed': False},
        'external_sources_used': [],
        'external_retrieval_audit': {'enabled': False, 'external_search_status': 'disabled_controlled_comparison', 'external_search_completed': False},
        'runtime_constraints': {'gold_labels_available_to_runtime': False, 'external_retrieval_called': False,
                               'outside_legal_knowledge_allowed': False, 'human_review_called': False,
                               'single_issue_compact_output': True},
    }

def run_method(method, label, retriever, flat_evidence, key, prompt, run_id):
    import run_hierarchy_gated_llm_smoke as runner
    from external_fallback_v2 import ExternalFallbackStateMachine
    from experiment_integrity import result_status
    if method == 'strict_hierarchy':
        result = runner.run_case(api_key=key, retriever=retriever, final_prompt=prompt+FINAL_OVERRIDE,
            context_template={}, label=label, top_k=5, final_max_tokens=16384, triage_max_tokens=2048,
            compact_final_output=True, experiment_run_id=run_id,
            external_fallback=ExternalFallbackStateMachine(enabled=False, provider=None))
    else:
        runtime = flat_runtime(label, flat_evidence if method == 'flat_hybrid' else [], run_id)
        runtime['experimental_method'] = method
        effective = prompt+FINAL_OVERRIDE+runner.FINAL_COMPACT_OUTPUT_CONTRACT
        if method == 'llm_only':
            runtime.pop('flat_retrieval_audit')
            runtime['runtime_constraints']['outside_legal_knowledge_allowed'] = True
            effective += LLM_ONLY_OVERRIDE
            response = runner.model_request(key, effective, runtime, max_tokens=16384,
                response_contract='final_review', thinking_mode='enabled', reasoning_effort='low')
            gate = {'status': 'not_applied_llm_only_baseline', 'blocked': False, 'actions': [], 'response': response.get('parsed')}
        else:
            response, gate = runner.run_final_reasoning(api_key=key, prompt=effective, runtime_input=runtime, max_tokens=16384)
        result = {'issue_id': label['issue_id'], 'runtime_input': runtime, 'final_llm_response': response,
                  'post_llm_gate': gate}
        result['assessment_status'] = result_status(result)
        result['run_status'] = result['assessment_status']['execution_status']
    result['experimental_method'] = method
    result['raw_observation'] = semantic_observation(result, True)
    result['gated_observation'] = semantic_observation(result)
    return result
