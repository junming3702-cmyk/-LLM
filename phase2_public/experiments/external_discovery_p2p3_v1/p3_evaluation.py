"""Prospective registration/readiness + locked-label metrics, NOT an A/B/C runner.

Gold material is never loaded into a reasoning request. This evaluator consumes
already-generated arm outputs; execution adapters must be separately validated.
"""
import argparse
import json
from pathlib import Path
from discovery import canonical_hash

MATCHED_CONTROLS = ('task_inputs_sha256', 'local_corpus_sha256', 'withholding_manifest_sha256',
                    'model', 'temperature', 'max_tokens', 'prompt_sha256', 'as_of_policy', 'review_policy_sha256')

def evaluate(spec, labels, arms):
    if labels.get('status') != 'human_confirmed_locked' or labels.get('task_spec_sha256') != canonical_hash(spec):
        raise ValueError('human_reference_lock_missing_or_stale')
    if not labels.get('reviewer_id') or not labels.get('locked_at') or not labels.get('reference_snapshot_sha256'):
        raise ValueError('reference_lock_incomplete')
    tasks = {t['id']: t for t in spec['tasks']}
    refs = labels.get('cases', {})
    if set(refs) != set(tasks):
        raise ValueError('case_coverage_mismatch')
    if set(arms) != {'A_local', 'B_fixed_access', 'C_article_discovery'}:
        raise ValueError('three_comparison_arms_required')
    controls = [a.get('controls', {}) for a in arms.values()]
    for key in MATCHED_CONTROLS:
        if any(key not in c for c in controls) or len({canonical_hash(c[key]) for c in controls}) != 1:
            raise ValueError('unmatched_control_' + key)
    output = {}
    for arm, bundle in arms.items():
        rows = bundle.get('cases', [])
        if len(rows) != len(tasks) or {r['id'] for r in rows} != set(tasks):
            raise ValueError('arm_case_coverage_mismatch')
        recalls, reciprocal_ranks = [], []
        correct, safety_total, safety_pass, citations, traced = 0, 0, 0, 0, 0
        for row in rows:
            gold = refs[row['id']]
            if gold.get('status') != 'confirmed': raise ValueError('case_not_confirmed')
            relevant = set(gold['relevant_evidence_ids'])
            ranked = row['ranked_evidence_ids']
            if len(set(ranked)) != len(ranked): raise ValueError('duplicate_ranked_id')
            if relevant:  # Zero-relevant tasks excluded; not scored as perfect retrieval.
                recalls.append(len(relevant.intersection(ranked[:5])) / len(relevant))
                reciprocal_ranks.append(next((1/i for i, rid in enumerate(ranked, 1) if rid in relevant), 0))
            correct += row['conclusion'] == gold['conclusion']
            if gold.get('must_abstain'):
                safety_total += 1
                safety_pass += row['conclusion'] == gold['conclusion'] and not row.get('unsupported_independent_citation', True)
            citations += row.get('citation_count', 0)
            traced += row.get('traceable_citation_count', 0)
        output[arm] = {'retrieval_denominator': len(recalls),
                       'macro_evidence_recall_at_5': sum(recalls)/len(recalls) if recalls else None,
                       'mrr_over_returned_ranking': sum(reciprocal_ranks)/len(reciprocal_ranks) if reciprocal_ranks else None,
                       'conclusion_agreement_count': correct, 'total_tasks': len(rows),
                       'safety_pass': safety_pass, 'safety_denominator': safety_total,
                       'traceable_citations': traced, 'citation_denominator': citations,
                       'not_causal_or_population_estimate': True}
    return output

def prepare(spec, out):
    out.mkdir(parents=True, exist_ok=False)
    sha = canonical_hash(spec)
    registration = {'schema': 'p3-registration.v1', 'task_spec_sha256': sha, 'tasks': len(spec['tasks']),
                    'status': 'proposal_snapshot_NOT_human_gold_lock', 'reference_labels_confirmed': 0,
                    'full_abc_execution_ready': False,
                    'blocking_prerequisites': ['human reference and scope lock', 'identical baseline/withholding snapshots',
                                               'A/B/C execution adapters and arm-specific provenance verification',
                                               'fixed model/prompt/request parameters and review effort log'],
                    'development_fixtures_separate': True, 'frozen_expert_outputs_modified': False}
    (out / 'registration.json').write_text(json.dumps(registration, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / 'task_proposals.snapshot.json').write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
    labels = {'status': 'pending_human_review', 'task_spec_sha256': sha, 'reviewer_id': None, 'locked_at': None,
              'reference_snapshot_sha256': None, 'cases': {t['id']: {'status': 'pending', 'relevant_evidence_ids': None,
                  'conclusion': None, 'must_abstain': None, 'rationale': None} for t in spec['tasks']}}
    (out / 'human_labels.pending.json').write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# P3：30条新任务逐条审阅稿', '', '## Material Passport', '',
             '- Origin Skill: academic-research-suite / experiment-agent', '- Origin Mode: plan',
             '- Origin Date: 2026-09-17', '- Verification Status: UNVERIFIED', '- Version Label: p3_draft_v1', '',
             '这些是AI新编的合成任务，不是专家数据或已经确认的gold。参考条文和结论均为待审假设。',
             '请逐条确认/修正：任务事实是否足够、采购制度、地域/时间/工程类型、完整法条、条件与例外、结论。',
             'P1审批不等于这些新任务的答案审批。含多个相似任务的family不应被视为独立项目。', '',
             '对照：A本地四层；B本地+旧固定来源访问；C本地+新条款发现。正式三臂测试尚未运行。',
             '人工制造的本地缺条必须在三臂采用相同剔除清单，并与原始语料自然缺条分开报告。', '',
             f'任务快照：`{sha}`', '']
    for t in spec['tasks']:
        context = {**spec['default_context'], **t.get('context', {})}
        lines += [f"## {t['id']} · {t['category']} · {t['family']}", '', t['text'], '',
                  f"上下文：`{json.dumps(context, ensure_ascii=False)}`", '',
                  f"拟参考条文：{', '.join(t['references']) or '不预设可适用条文；不等于全部法律均无命中'}", '',
                  f"拟结论：`{t['proposed_outcome']}`", '', '人工决定：□确认 □修改 □排除', '',
                  '完整依据/版本/条件/修正意见：________', '']
    (out / '01_P3_30条新任务_待人工确认.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(registration, ensure_ascii=False))

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--prepare', type=Path, required=True)
    args = ap.parse_args()
    prepare(json.loads((Path(__file__).parent / 'p3_tasks.pending.json').read_text('utf-8')), args.prepare)
