"""Local-only source-role ablation on fixed saved responses and evidence.

Accepts default-gate local runs only; refuses a historical gate mismatch. No
labels, API configuration, source documents or credentials are loaded. P3
external arms are deliberately excluded because they use a different gate.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PACKAGE/'src'))
sys.path.insert(0,str(PACKAGE/'experiments/main_controls_v1'))
from experiment_integrity import file_digest, write_new_json, code_inventory, utc_now
from controls import semantic_observation
from llm_abstention_gate import apply_gate
from source_role_policy import VERSION, restriction_reasons, prepare_runtime


def replay_one(source):
    original = semantic_observation(source)
    candidate = deepcopy(source)
    runtime = source.get('runtime_input') or {}
    rows = runtime.get('retrieved_legal_evidence') or []
    restricted = [r for r in rows if isinstance(r,dict) and restriction_reasons(r)]
    contradicted = [r for r in restricted if r.get('independent_legal_evidence') is True]
    gate = source.get('post_llm_gate') or {}
    original_citations = [r for f in gate.get('response',{}).get('findings',[])
                          for r in f.get('legal_evidence',[]) if isinstance(r,dict)]
    before_citations = [r for r in original_citations if restriction_reasons(r)
                        and r.get('independent_legal_evidence') is True]
    reproduced = None
    if original['status']=='completed':
        raw = deepcopy(source['final_llm_response']['parsed'])
        normal = apply_gate(raw,deepcopy(runtime))
        reproduced = normal == gate
        if not reproduced:
            raise ValueError('default_gate_mismatch:'+source['issue_id'])
        candidate['post_llm_gate'] = apply_gate(raw,deepcopy(runtime),source_role_guard=True)
        after = [r for f in candidate['post_llm_gate']['response'].get('findings',[])
                 for r in f.get('legal_evidence',[]) if isinstance(r,dict)]
        if any(restriction_reasons(r) and r.get('independent_legal_evidence') is True for r in after):
            raise ValueError('restricted_citation_still_independent')
    prepared = prepare_runtime(runtime) if rows else None
    if prepared:
        # Not a retrieval experiment: IDs/order/ranking and all source text
        # must remain byte-for-byte equal as parsed JSON values.
        kept = ('chunk_id','law','article','legal_quote','source_locator','normative_level','rank','retrieval_scores')
        for a,b in zip(rows,prepared['retrieved_legal_evidence']):
            if any(a.get(k)!=b.get(k) for k in kept):
                raise ValueError('source_role_guard_changed_retrieval_or_content')
    updated = semantic_observation(candidate)
    detail = {'unit_id':source['issue_id'],'original':original,'candidate':updated,
        'default_gate_exact_reproduction':reproduced,
        'restricted_evidence_rows':len(restricted),
        'contradictory_independent_rows':len(contradicted),
        'contradictory_final_citations_before':len(before_citations),
        'contradictory_final_citations_after':0 if original['status']=='completed' else None,
        'contradictory_ids': [r.get('chunk_id') for r in contradicted],
        'verdict_or_status_changed':original != updated}
    return detail,candidate.get('post_llm_gate')


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--arms',nargs='+');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('new output directory required')
    completion=json.loads((a.run/'completion.json').read_text(encoding='utf-8'))
    if completion.get('complete_attempts') is not True:raise ValueError('source_run_not_complete')
    files=sorted((a.run/'results').glob('*/*.json'))
    if a.arms:files=[f for f in files if f.parent.name in a.arms]
    if not files:raise ValueError('no_source_results')
    hashes={str(f):file_digest(f) for f in files};rows=[]
    for f in files:
        source=json.loads(f.read_text(encoding='utf-8'))
        if source.get('p3_arm') not in (None,'A_local'):
            raise ValueError('external_arm_not_supported_by_default_gate_replay')
        row,gate=replay_one(source);row.update(arm=f.parent.name,source_sha256=hashes[str(f)])
        rows.append(row)
        write_new_json(a.output/'results'/f.parent.name/f.name,
            {'source_file':str(f),'source_sha256':hashes[str(f)],
             'fixed_raw_response':True,'no_new_model_generation':True,
             'detail':row,'candidate_gate':gate})
    if any(file_digest(f)!=sha for f,sha in hashes.items()):raise ValueError('source_changed')
    summary={}
    for arm in sorted({r['arm'] for r in rows}):
        selected=[r for r in rows if r['arm']==arm]
        summary[arm]={'n':len(selected),
            'original_status':dict(Counter(r['original']['status'] for r in selected)),
            'default_exact_n':sum(r['default_gate_exact_reproduction'] is True for r in selected),
            'affected_evidence_packets':sum(r['contradictory_independent_rows']>0 for r in selected),
            'contradictory_independent_rows':sum(r['contradictory_independent_rows'] for r in selected),
            'contradictory_final_citations_before':sum(r['contradictory_final_citations_before'] for r in selected),
            'transitions':dict(Counter(str(r['original']['verdict'])+'->'+str(r['candidate']['verdict']) for r in selected)),
            'changed_n':sum(r['verdict_or_status_changed'] for r in selected)}
    analysis={'policy_version':VERSION,'checked_at':utc_now(),'mode':'fixed_response_offline_gate_replay',
        'source_completion_sha256':file_digest(a.run/'completion.json'),'summary':summary,
        'detail':rows,'source_hashes':hashes,'code_inventory':code_inventory(PACKAGE),
        'source_files_modified':0,'api_calls':0,'gold_labels_read':False,
        'corpus_expanded':False,'retrieval_ranking_changed':False,
        'llm_behavior_effect_measured':False,'independent_holdout':False,
        'limitations':['Dependent observations; no pooled accuracy or significance claim.',
            'Default-gate replay only; no new triage/retrieval/LLM generation.',
            'Not legal adjudication; declared source roles are enforced, not independently verified.']}
    write_new_json(a.output/'analysis.private.json',analysis)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
