"""Canonical delivery metadata, without changing an answer or evidence.

External arms share a local result, but must not retain its stale execution
flags after a second generation. Historical raw run files stay immutable.
"""
from copy import deepcopy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from experiment_integrity import result_status


def finalize_metadata(result):
    result=deepcopy(result)
    result['assessment_status']=result_status(result)
    result['run_status']=result['assessment_status']['execution_status']
    result['ready_for_human_delivery']=result['assessment_status']['ready_for_human_delivery']
    audit=result.get('p3_one_shot_audit')
    if isinstance(audit,dict):
        attempted=audit.get('attempted') is True
        rounds=audit.get('rounds',0)
        if rounds!=(1 if attempted else 0):raise ValueError('inconsistent_external_round_count')
        generated=audit.get('new_final_generation') is True
        old=deepcopy(result.get('external_recheck') or {})
        result['pre_projection_external_recheck']=old
        result['external_recheck']={
            'policy':'one_shot_after_preliminary_insufficient_information',
            'attempted':attempted,'attempt_count':rounds,
            'final_reasoning_rerun_dispatched':generated,
            'final_reasoning_rerun_completed':generated and result['run_status']=='completed',
            'admitted_count':audit.get('admitted_count',0),
            'actual_external_http_requests':0,
            'source_mode':'frozen_snapshot_replay',
            'requires_human_second_review':True,
            'projection_basis':'p3_one_shot_audit_and_actual_final_response_not_old_local_flags'}
    return result


def main():
    import argparse,json
    from experiment_integrity import file_digest,write_new_json
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    rows=[]
    for path in sorted((a.run/'results').glob('*/*.json')):
        original=json.loads(path.read_text(encoding='utf-8'));updated=finalize_metadata(original)
        if updated.get('final_llm_response')!=original.get('final_llm_response') or updated.get('post_llm_gate')!=original.get('post_llm_gate'):
            raise ValueError('projection_changed_answer')
        rows.append({'source_file':str(path),'source_sha256':file_digest(path),
            'issue_id':original['issue_id'],'arm':original['p3_arm'],
            **{k:updated.get(k) for k in ('run_status','assessment_status','ready_for_human_delivery','external_recheck','pre_projection_external_recheck')},
            'answer_and_evidence_unchanged':True})
    write_new_json(a.output/'delivery_metadata.private.json',rows)
    write_new_json(a.output/'completion.json',{'rows':len(rows),'source_files_modified':0,
        'model_calls':0,'projection_only':True,'answers_changed':0})
    print('PROJECTED '+str(len(rows))+' metadata records; zero source writes/model calls')


if __name__=='__main__':main()
