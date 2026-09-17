"""Offline sensitivity overlay; never replaces primary observations/files."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import argparse
import json
from analyse_factorial import metrics, collect_calls, file_digest, write_new_json


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--analysis',type=Path,required=True)
    p.add_argument('--sensitivity',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    read=lambda x:json.loads(Path(x).read_text(encoding='utf-8'))
    primary=read(a.analysis)
    manifest=read(a.sensitivity/'run_manifest.json')['binding']
    complete=read(a.sensitivity/'completion.json')
    if manifest['primary_binding']!=primary['run_manifest']['binding']:
        raise ValueError('sensitivity belongs to another primary experiment')
    if len(complete['outcomes'])!=len(manifest['selected']):raise ValueError('sensitivity incomplete')
    rows=deepcopy(primary['rows'])
    index={(r['arm'],r['unit_id'],r['stage']):r for r in rows}
    details={(r['arm'],r['unit_id']):r for r in primary['detail']}
    changes=[];costs=[]
    for selected in manifest['selected']:
        arm,uid=selected['arm'],selected['issue_id']
        old=details[(arm,uid)]
        path=a.sensitivity/'results'/arm/(uid+'.json')
        result=read(path)
        if result['experimental_arm']!=arm or result['issue_id']!=uid:
            raise ValueError('sensitivity result identity mismatch')
        provenance=result['experiment_provenance']
        if old['source_result_sha256']!=selected['primary_result_sha256'] or provenance['primary_result_sha256']!=old['source_result_sha256']:
            raise ValueError('primary linkage mismatch')
        if old['gated']['status']!='execution_failed':raise ValueError('non-transport status selected')
        for stage in ('raw','gated'):
            new=result[stage+'_observation'];row=index[(arm,uid,stage)]
            changes.append({'arm':arm,'unit_id':uid,'stage':stage,'reference':row['reference'],
                'primary':old[stage],'sensitivity':new,'result_sha256':file_digest(path)})
            row.update(new)
        calls=collect_calls(a.sensitivity/'audit'/arm/uid)
        if len(calls)!=provenance['request_count']:raise ValueError('sensitivity audit mismatch')
        usage=Counter()
        for call in calls:
            for k,v in (call['usage'] or {}).items():
                if isinstance(v,(int,float)) and not isinstance(v,bool):usage[k]+=v
        costs.append({'arm':arm,'unit_id':uid,'provider_attempts':len(calls),
            'usage_reported_totals':dict(usage),'calls_without_usage':sum(c['usage'] is None for c in calls),
            'elapsed_seconds':provenance['elapsed_seconds']})
    summary={arm:{stage:metrics([r for r in rows if r['arm']==arm and r['stage']==stage])
        for stage in ('raw','gated')} for arm in primary['summary']}
    write_new_json(a.output,{'primary_analysis_sha256':file_digest(a.analysis),
        'primary_files_modified':False,'summary':summary,'changes':changes,'extra_cost':costs,
        'boundary':'whole-unit stochastic repeat of transport failure only; primary analysis unchanged; no renewed expert B scores'})
    print(json.dumps({'changes':changes,'extra_cost':costs},ensure_ascii=False))


if __name__=='__main__':main()
