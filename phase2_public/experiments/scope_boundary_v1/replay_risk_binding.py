"""Offline, raw-response-fixed candidate gate replay. Never makes API calls.

All source observations stay unchanged, including invalid/failed outputs.
References are used ONLY here after generation, never by the policy module.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import json
import sys

PACKAGE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE / 'src'))
sys.path.insert(0, str(PACKAGE / 'experiments/main_controls_v1'))
from experiment_integrity import file_digest, write_new_json, code_inventory
from llm_abstention_gate import apply_gate
from risk_binding_policy import VERSION
from controls import semantic_observation
from analyse_factorial import load_reference, metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--references', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('new output directory required')
    completion = json.loads((args.run/'completion.json').read_text(encoding='utf-8'))
    if not completion['complete_attempts']:
        raise ValueError('source primary batch incomplete')
    references = load_reference(args.references)
    rows, changes, fingerprints = [], [], {}
    by_arm = {}
    for path in sorted((args.run/'results').glob('*/*.json')):
        source = json.loads(path.read_text(encoding='utf-8'))
        arm, uid = source['experimental_arm'], source['issue_id']
        if uid not in references or uid in by_arm.setdefault(arm, set()):
            raise ValueError('duplicate or unexpected issue')
        by_arm[arm].add(uid)
        fingerprints[str(path)] = file_digest(path)
        original = semantic_observation(source)
        candidate = deepcopy(source)
        raw = source.get('final_llm_response') or {}
        default_equal = None
        # Replaying a failed generation cannot turn it into a successful case.
        if original['status'] == 'completed':
            default = apply_gate(deepcopy(raw['parsed']), deepcopy(source['runtime_input']))
            default_equal = default == source['post_llm_gate']
            if not default_equal:
                raise ValueError('default gate no longer exactly reproduces frozen result: '+arm+'/'+uid)
            candidate['post_llm_gate'] = apply_gate(deepcopy(raw['parsed']),
                deepcopy(source['runtime_input']), risk_binding=True)
        updated = semantic_observation(candidate)
        findings = (candidate.get('post_llm_gate', {}).get('response') or {}).get('findings') or []
        audits = [f.get('risk_binding_audit', {}) for f in findings if isinstance(f, dict)]
        record = {'arm': arm, 'unit_id': uid, 'reference': references[uid],
            'original': original, 'candidate': updated, 'default_exact_reproduction': default_equal,
            'binding_audits': audits, 'source_sha256': fingerprints[str(path)]}
        rows.append(record)
        if original != updated:
            changes.append(record)
        write_new_json(args.output/'results'/arm/(uid+'.json'), {
            'analysis_type': 'offline_fixed_raw_response_gate_replay',
            'policy_version': VERSION, 'source_sha256': fingerprints[str(path)],
            'source_file': str(path), 'observation': updated,
            'candidate_gate': candidate.get('post_llm_gate'),
            'source_generation_status': original['status']})
    if len(by_arm) != 4 or any(ids != set(references) for ids in by_arm.values()):
        raise ValueError('source factorial incomplete')
    summary = {}
    for arm in by_arm:
        summary[arm] = {}
        for stage in ('original','candidate'):
            selected = [{'reference': r['reference'], **r[stage]} for r in rows if r['arm']==arm]
            summary[arm][stage] = metrics(selected)
    if any(file_digest(p) != sha for p,sha in fingerprints.items()):
        raise ValueError('source file changed during replay')
    output = {'analysis_type':'offline_fixed_raw_response_gate_replay', 'policy_version':VERSION,
        'no_api_calls':True,'independent_holdout':False,'prompt_effect_measured':False,
        'legal_entailment_verified':False,'source_results_unchanged':True,
        'reference_sha256':file_digest(args.references),'code_inventory':code_inventory(PACKAGE),
        'planned_n':len(rows),'changed_n':len(changes),'changes':changes,
        'summary':summary,'detail':rows,'source_hashes':fingerprints,
        'limits':['Post-hoc diagnostic replay; not a new independent test.',
                  'Structural support is necessary, not sufficient legal entailment.',
                  'Abstention may increase; no verdict is relabelled compliant by this guard.',
                  'Original errors and failures remain in the denominator.']}
    write_new_json(args.output/'analysis.private.json', output)
    print(json.dumps({'planned_n':len(rows),'changed_n':len(changes),'summary':summary}, ensure_ascii=False))


if __name__ == '__main__':
    main()
