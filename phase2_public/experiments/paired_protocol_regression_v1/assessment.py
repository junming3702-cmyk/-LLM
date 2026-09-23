"""Offline strict-final-channel assessment, leaving raw provider records intact.

Legacy apply_gate expects an already parsed object for protocol diagnostics;
the new evaluate accepts a JSON string. Normalize this transport difference
without changing either gate, any field, any enum or a substantive finding.
"""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runner import assess,read,write,sha,utc

def strict_json(text):
 def pairs(items):
  out={}
  for k,v in items:
   if k in out:raise ValueError('duplicate_json_key')
   out[k]=v
  return out
 def constant(value):raise ValueError('nonfinite_json_number')
 return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)

def recheck(out):
 out=Path(out);dest=out/'assessment_v2';dest.mkdir(exist_ok=False)
 for p in sorted((out/'results').glob('*.json')):
  rec=read(p);case=rec['case_id'];inp=read(out/'requests'/f'{case}.json')
  provider=read(out/'raw'/f'{case}.json') if (out/'raw'/f'{case}.json').exists() else {}
  choices=provider.get('choices') or [];content=(choices[0].get('message',{}).get('content') or '') if choices else ''
  parse_error=None
  try:parsed=strict_json(content)
  except (ValueError,TypeError,RecursionError) as e:parsed=None;parse_error=type(e).__name__
  ok=rec['transport_ok'] and parse_error is None
  # Both arms get exact parsed final JSON, never reasoning fragments.
  raw_gate=assess(parsed,inp,rec['finish_reason'],ok,False)
  normalized_gate=assess(parsed,inp,rec['finish_reason'],ok,True)
  rec.update(raw_gate=raw_gate,normalized_gate=normalized_gate,gate_error=None,strict_json_error=parse_error,
   scoring_adapter='strict_content_json_before_both_gates',initial_result_sha256=sha(p),provider_raw_sha256=sha(out/'raw'/f'{case}.json') if (out/'raw'/f'{case}.json').exists() else None)
  write(dest/f'{case}.json',rec)
 write(dest/'assessment_audit.json',dict(created_utc=utc(),assessment_source_sha256=sha(Path(__file__)),
  cases=len(list((out/'results').glob('*.json'))),new_api_calls=0,raw_responses_edited=False,
  correction='Legacy gate protocol diagnostics require parsed object rather than JSON transport string; strict deserialization only; no semantic repair.',
  raw_and_normalized_preserved=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();recheck(a.out)
