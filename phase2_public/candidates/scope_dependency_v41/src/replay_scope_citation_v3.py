"""Local frozen-response replay. No REF, review workbook, network or API keys.

The catalogue contains only unit_id and runtime-result path. Run baseline and
candidate in separate processes. This is a post-hoc software diagnostic, not
an independent outcome evaluation or a prompt-generation experiment.
"""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import argparse,hashlib,json,socket,sys,time

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
def no_network(*args,**kwargs):raise RuntimeError('Network disabled in frozen replay')
def summary(g):
    fs=(g.get('response') or {}).get('findings') or []
    return {'blocked':g.get('blocked'),'conclusions':[f.get('conclusion_type') for f in fs],
        'processing':[f.get('nu_boundary_audit',{}).get('processing_status') for f in fs],
        'binding_errors':[f.get('nu_boundary_audit',{}).get('evidence_binding_errors',[]) for f in fs],
        'blocking_reasons':[f.get('nu_boundary_audit',{}).get('blocking_reasons',[]) for f in fs]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['package','catalogue','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--candidate',action='store_true');a=p.parse_args()
    if a.output.exists():raise FileExistsError('Do not overwrite a replay')
    a.output.mkdir(parents=True);(a.output/'results').mkdir()
    sys.dont_write_bytecode=True;sys.path.insert(0,str(a.package/'src'))
    socket.socket.connect=no_network;socket.create_connection=no_network
    from llm_abstention_gate import apply_gate
    from review_task_contract_v2 import build_contract
    catalogue=read(a.catalogue);assert len(catalogue)==30
    assert all(set(row)=={'unit_id','result_path'} for row in catalogue)
    hashes={row['result_path']:sha(Path(row['result_path'])) for row in catalogue}
    source_hashes={str(p.relative_to(a.package)):sha(p) for p in sorted((a.package/'src').glob('*.py'))}
    manifest={'candidate':a.candidate,'catalogue_sha256':sha(a.catalogue),'results_sha256':hashes,'code_sha256':source_hashes,
        'network_calls':0,'references_loaded':False,'response_reused':True,'prompt_effect_tested':False,
        'scope_contract_recomputed_only_for_candidate':a.candidate}
    (a.output/'manifest.private.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[];tick=time.monotonic()
    for item in catalogue:
        r=read(Path(item['result_path']));rt=deepcopy(r['runtime_input']);original_runtime_hash=digest(rt)
        raw=r['final_llm_response']['parsed'];assert isinstance(raw,dict)
        if a.candidate:rt['review_task_contract_v2']=build_contract(rt)
        rt_bound=digest(rt)
        g=apply_gate(deepcopy(raw),rt,source_role_guard=True,nu_boundary=True,task_contract_v2=True,external_auto_candidates=True)
        assert digest(raw)==digest(r['final_llm_response']['parsed']) and digest(rt)==rt_bound
        before=summary(r['post_llm_gate']);after=summary(g)
        row={'unit_id':item['unit_id'],'recorded':before,'replayed':after,'same_recorded_diagnostic':before==after,
             'exact_recorded_gate_equal':digest(r['post_llm_gate'])==digest(g),
             'contract_scope':rt['review_task_contract_v2']['scope'],'original_runtime_sha256':original_runtime_hash,
             'candidate_runtime_sha256':rt_bound,'raw_response_sha256':digest(raw)}
        rows.append(row)
        (a.output/'results'/f"{item['unit_id']}.json").write_text(json.dumps({'row':row,'gate_result':g},ensure_ascii=False,indent=2),encoding='utf-8')
    preserved=all(sha(Path(p))==h for p,h in hashes.items())
    result={'n':len(rows),'candidate':a.candidate,'elapsed_seconds':time.monotonic()-tick,
        'source_hashes_preserved':preserved,'same_recorded_diagnostic_n':sum(r['same_recorded_diagnostic'] for r in rows),
        'exact_recorded_gate_equal_n':sum(r['exact_recorded_gate_equal'] for r in rows),
        'blocked':sum(r['replayed']['blocked'] for r in rows),
        'valid_conclusions':dict(Counter(c for r in rows if not r['replayed']['blocked'] for c in r['replayed']['conclusions'])),
        'network_calls':0,'rows':rows}
    (a.output/'summary.private.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False))
    assert preserved
if __name__=='__main__':main()
