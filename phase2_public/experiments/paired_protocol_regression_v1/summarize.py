"""Descriptive paired protocol/processing counters, NOT legal effectiveness."""
from collections import Counter
from statistics import median

def row_metrics(r):
 g=r.get('raw_gate') or {};n=r.get('normalized_gate') or {};arm=r['arm']
 transport=r.get('transport_ok') is True and r.get('finish_reason')=='stop' and not r.get('strict_json_error') and not r.get('gate_error')
 if arm=='new':
  raw_structure=g.get('raw_structure_valid') is True
  norm_structure=n.get('normalized_structure_valid') is True
  processing=n.get('processing_status','not_evaluated')
  completion=n.get('question_completion');handoff=n.get('handoff_status')
  assessed=n.get('assessed_claim_count');required=n.get('required_claim_count')
  changes=len(n.get('normalization_actions') or [])
 else:
  d=g.get('protocol_diagnostics') or {};dn=n.get('protocol_diagnostics') or {}
  raw_structure=(d.get('raw') or {}).get('valid') is True
  norm_structure=(dn.get('normalized') or {}).get('valid') is True
  fs=(n.get('response') or {}).get('findings') or []
  statuses=[(f.get('nu_boundary_audit') or {}).get('processing_status','not_evaluated') for f in fs]
  processing='valid' if len(statuses)==1 and statuses[0]=='valid' else '|'.join(sorted(set(statuses))) or n.get('processing_status','no_deliverable_finding')
  completion=None;handoff=None;assessed=None;required=None;changes=len(dn.get('actions') or [])
 usage=r.get('usage') or {}
 return dict(issue_id=r['issue_id'],arm=arm,project=r['issue_id'][:2],
  final_json_complete=transport,raw_structure_valid=transport and raw_structure,
  normalized_structure_valid=transport and norm_structure,processing_status=processing,
  full_gate_valid=transport and processing=='valid',question_completion=completion,handoff_status=handoff,
  assessed_claims=assessed,required_claims=required,normalization_actions=changes,
  prompt_tokens=usage.get('prompt_tokens'),completion_tokens=usage.get('completion_tokens'),
  total_tokens=usage.get('total_tokens'),elapsed_seconds=r.get('elapsed_seconds'))

def summarize(records):
 rows=[row_metrics(r) for r in records];groups={}
 for group,projects in [('REAL45',{'P1','P2','P3'}),('REAL30',{'P1','P3'}),('P1',{'P1'}),('P2',{'P2'}),('P3',{'P3'})]:
  arms={}
  for arm in ('old','new'):
   rs=[r for r in rows if r['project'] in projects and r['arm']==arm];n=len(rs)
   arms[arm]={'attempts':n,**{k:sum(r[k] is True for r in rs) for k in ('final_json_complete','raw_structure_valid','normalized_structure_valid','full_gate_valid')},
    'processing_counts':dict(Counter(r['processing_status'] for r in rs)),
    'completion_counts':dict(Counter(str(r['question_completion']) for r in rs)),
    'handoff_counts':dict(Counter(str(r['handoff_status']) for r in rs)),
    'prompt_tokens':sum(r['prompt_tokens'] or 0 for r in rs),'completion_tokens':sum(r['completion_tokens'] or 0 for r in rs),
    'total_tokens':sum(r['total_tokens'] or 0 for r in rs),'usage_available':sum(r['total_tokens'] is not None for r in rs),
    'median_elapsed_seconds':median(r['elapsed_seconds'] for r in rs) if rs else None,
    'normalization_changed_responses':sum(r['normalization_actions']>0 for r in rs)}
  pairs={}
  for uid in sorted({r['issue_id'] for r in rows if r['project'] in projects}):
   pair={r['arm']:r for r in rows if r['issue_id']==uid}
   if len(pair)==2:pairs[uid]=pair
  transitions=Counter(f"old_{'valid' if x['old']['full_gate_valid'] else 'held'}__new_{'valid' if x['new']['full_gate_valid'] else 'held'}" for x in pairs.values())
  groups[group]={'arms':arms,'paired_n':len(pairs),'gate_status_pairs_not_accuracy':dict(transitions)}
 return {'rows':rows,'groups':groups,'legal_accuracy':None,'expert_agreement':None,'joint_handoff_effectiveness':None,
  'warning':'Different output schemas and gate requirements: conformance comparison is operational, not equal-difficulty legal accuracy. Cases nested in 3 already exposed projects; no independent inference or p-values.'}
