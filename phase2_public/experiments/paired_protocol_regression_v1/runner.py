"""Frozen paired protocol regression. Private prepared requests stay outside git.

No retrieval, no reference read, no prompt editing, no retries. Legacy and new
gates remain unmodified. Every provider attempt and both raw/normalized gate
states are saved separately; protocol validity is never legal accuracy.
"""
from pathlib import Path
import argparse, hashlib, json, os, sys, time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'candidates/scope_dependency_v41'
NEW=ROOT/'candidates/three_layer_handoff_v01'
sys.dont_write_bytecode=True
sys.path[:0]=[str(OLD/'src'),str(NEW)]
from gate import evaluate
from llm_abstention_gate import apply_gate

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2,allow_nan=False)
def utc():return datetime.now(timezone.utc).isoformat()
def strict_json(text):
 def pairs(items):
  out={}
  for k,v in items:
   if k in out:raise ValueError('duplicate_json_key')
   out[k]=v
  return out
 def constant(value):raise ValueError('nonfinite_json_number')
 return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
def keys_recursive(value):
 if isinstance(value,dict):return set(value).union(*(keys_recursive(v) for v in value.values()))
 if isinstance(value,list):return set().union(*(keys_recursive(v) for v in value))
 return set()
def validate_pair(left,right):
 """Compare actual serialized wires, not a claimed common hash sidecar."""
 from review_task_contract_v2 import source_spans
 a,b=[strict_json(x['body']['messages'][1]['content']) for x in (left,right)]
 if a['common_evidence_packet']!=b['common_evidence_packet']:raise ValueError('asymmetric_common_wire')
 forbidden={'missing_elements','decisive_missing_facts','level_state','triage_binding',
  'reference_answer','expert_scores','consensus_label','gold_label','nu_boundary_audit'}
 if forbidden & keys_recursive([a,b]):raise ValueError('historical_prediction_or_reference_in_wire')
 common=a['common_evidence_packet'];new=b['protocol_context'];old=a['protocol_context']
 spec=common['locked_scope_spec']
 if old['review_task_contract_v41']['scope_spec']!=spec:raise ValueError('old_scope_mismatch')
 for k in ('review_mode','required_claims','excluded_dependencies'):
  if new['task'][k]!=spec[k]:raise ValueError('new_scope_mismatch')
 if new['task']['question']!=spec['question_verbatim']:raise ValueError('new_question_mismatch')
 if new['task']['project_context']!=common['project_context']:raise ValueError('context_asymmetry')
 spans=[(loc,text) for loc,vs in source_spans(common).items() for text in vs if text.strip()]
 if [(s['locator'],s['text']) for s in new['sources']]!=spans:raise ValueError('source_span_asymmetry')
 oldlaw=common['retrieved_legal_evidence'];newlaw=new['laws']
 if len(oldlaw)!=len(newlaw):raise ValueError('law_count_asymmetry')
 for l,r in zip(oldlaw,newlaw):
  for x,y in [('chunk_id','chunk_id'),('legal_quote','text'),('citation_ready','admitted'),('independent_legal_evidence','independent_legal_basis'),('applicability_status','applicability_status'),('temporal_status','temporal_status')]:
   if l[x]!=r[y]:raise ValueError('law_or_admission_asymmetry')
 expected=hashlib.sha256(json.dumps(common,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 if left['common_input_sha256']!=expected or right['common_input_sha256']!=expected:raise ValueError('common_hash_mismatch')
 return True
def code_inventory():
 files=list((OLD/'src').glob('*.py'))+list((OLD/'prompts').glob('*.md'))
 files+=list(NEW.glob('*.py'))+list((NEW/'generated').glob('*'))+[Path(__file__)]
 return {str(p.relative_to(ROOT)):sha(p) for p in files if p.is_file()}
def assess(raw,inp,finish,ok,normalization):
 if isinstance(raw,str):
  try:raw=strict_json(raw)
  except (ValueError,TypeError,RecursionError):ok=False;raw=None
 if inp['arm']=='new':return evaluate(raw,inp['context'],finish_reason=finish,transport_ok=ok,normalization=normalization)
 if not ok or finish!='stop':return {'processing_status':'technical_failure','valid_legal_verdicts':[],'technical_errors':['transport_or_incomplete_response']}
 return apply_gate(raw,inp['runtime_input'],source_role_guard=True,nu_boundary=True,
   task_contract_v2=True,external_auto_candidates=True,scope_dependency_v41=inp['scope_spec'],
   normalize_protocol_v41=normalization,material_aliases_v412=False,processing_presentation_v412=False)
def run(out,envfile,workers):
 import requests
 from dotenv import load_dotenv
 out=Path(out);lock=read(out/'lock.json')
 if (out/'run_started.json').exists():raise ValueError('Run already started: no implicit retries or resume')
 assert code_inventory()==lock['code_hashes'],'Source changed since input freeze'
 for case,h in lock['request_hashes'].items():assert sha(out/'requests'/f'{case}.json')==h
 for uid in {case.rsplit('-',1)[0] for case in lock['order']}:
  validate_pair(read(out/'requests'/f'{uid}-old.json'),read(out/'requests'/f'{uid}-new.json'))
 load_dotenv(envfile,override=False);key=os.environ.get('DEEPSEEK_API_KEY','').strip()
 if not key:raise ValueError('missing_api_key')
 assert len(lock['order'])==lock['max_calls'] and len(set(lock['order']))==len(lock['order'])
 write(out/'run_started.json',{'started_utc':utc(),'lock_sha256':sha(out/'lock.json'),'workers':workers})
 def one(case):
  inp=read(out/'requests'/f'{case}.json');body=inp['body']
  assert body['model']=='deepseek-v4-flash'
  write(out/'attempts'/f'{case}.json',{'case_id':case,'started_utc':utc(),'request_sha256':lock['request_hashes'][case]})
  start=time.monotonic();finish=None;content='';ok=False;provider={};status=None;error=None
  try:
   with requests.Session() as session:
    session.mount('https://',requests.adapters.HTTPAdapter(max_retries=0))
    r=session.post(lock['endpoint'],json=body,headers={'Authorization':'Bearer '+key},timeout=(30,420),allow_redirects=False)
   status=r.status_code;p=out/'raw'/f'{case}.json';p.parent.mkdir(exist_ok=True)
   with p.open('xb') as f:f.write(r.content)
   if status==200:
    provider=r.json();choice=provider['choices'][0];finish=choice.get('finish_reason');content=choice.get('message',{}).get('content') or '';ok=True
   else:error='http_'+str(status)
  except Exception as e:error=type(e).__name__ # Never log exception strings/headers/secrets.
  elapsed=time.monotonic()-start
  try:
   raw_gate=assess(content,inp,finish,ok,False);normalized_gate=assess(content,inp,finish,ok,True)
   gate_error=None
  except Exception as e:raw_gate=None;normalized_gate=None;gate_error=type(e).__name__
  result={'case_id':case,'issue_id':inp['issue_id'],'arm':inp['arm'],'common_input_sha256':inp['common_input_sha256'],
    'http_status':status,'transport_ok':ok,'error':error,'gate_error':gate_error,'finish_reason':finish,
    'requested_model':body['model'],'returned_model':provider.get('model'),'usage':provider.get('usage'),
    'content_chars':len(content),'reasoning_chars':len(((provider.get('choices') or [{}])[0].get('message') or {}).get('reasoning_content') or ''),
    'channel':'content_only','elapsed_seconds':elapsed,'raw_gate':raw_gate,'normalized_gate':normalized_gate,
    'human_semantic_review':'pending','legal_accuracy':None,'joint_handoff_effectiveness':None}
  write(out/'results'/f'{case}.json',result)
  print(json.dumps({k:result[k] for k in ('case_id','finish_reason','http_status','error','gate_error','elapsed_seconds')}) ,flush=True)
  return case
 with ThreadPoolExecutor(max_workers=workers) as pool:
  futures=[pool.submit(one,k) for k in lock['order']]
  for f in as_completed(futures):f.result()
 write(out/'run_completed.json',{'completed_utc':utc(),'attempts':len(list((out/'attempts').glob('*.json'))),'results':len(list((out/'results').glob('*.json')))})
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--env-file',required=True);p.add_argument('--workers',type=int,default=3);a=p.parse_args()
 if a.workers not in (1,2,3,4):p.error('workers must be 1-4')
 run(a.out,a.env_file,a.workers)
