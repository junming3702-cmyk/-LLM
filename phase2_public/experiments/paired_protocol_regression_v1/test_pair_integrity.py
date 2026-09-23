from copy import deepcopy
import hashlib,json,unittest
from runner import validate_pair

def fixture():
 spec={'question_verbatim':'Synthetic text review','review_mode':'clause_design','required_claims':[{'claim_id':'C1','description':'Compare text','required_dependencies':['applicable_rule']}],'excluded_dependencies':[]}
 common={'contract_evidence':{'document_location':'SYN:1','document_excerpt':'Synthetic text'},'project_context':{'project_type':'fictional'},'locked_scope_spec':spec,
  'retrieved_legal_evidence':[{'chunk_id':'L1','legal_quote':'Fictional rule','citation_ready':False,'independent_legal_evidence':False,'applicability_status':'unknown','temporal_status':'unknown'}]}
 old={'review_task_contract_v41':{'scope_spec':deepcopy(spec)}}
 new={'task':{'question':spec['question_verbatim'],'project_context':deepcopy(common['project_context']),**{k:deepcopy(spec[k]) for k in ('review_mode','required_claims','excluded_dependencies')}},
  'sources':[{'locator':'SYN:1','text':'Synthetic text'}],
  'laws':[{'chunk_id':'L1','text':'Fictional rule','admitted':False,'independent_legal_basis':False,'applicability_status':'unknown','temporal_status':'unknown'}]}
 h=hashlib.sha256(json.dumps(common,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 return [{'common_input_sha256':h,'body':{'messages':[{'role':'system','content':'test'},{'role':'user','content':json.dumps({'common_evidence_packet':deepcopy(common),'protocol_context':p})}]}} for p in (old,new)]
def mutate(rec,callback):
 wire=json.loads(rec['body']['messages'][1]['content']);callback(wire);rec['body']['messages'][1]['content']=json.dumps(wire)
class PairIntegrityTests(unittest.TestCase):
 def test_identical_common_packet(self):self.assertTrue(validate_pair(*fixture()))
 def test_hidden_nested_prior_prediction(self):
  a,b=fixture()
  for r in (a,b):mutate(r,lambda w:w['common_evidence_packet'].update(audit={'level_results':[{'missing_elements':['predicted answer']}] }))
  with self.assertRaisesRegex(ValueError,'historical'):validate_pair(a,b)
 def test_different_contract(self):
  a,b=fixture();mutate(b,lambda w:w['common_evidence_packet']['contract_evidence'].update(document_excerpt='Different'))
  with self.assertRaisesRegex(ValueError,'asymmetric'):validate_pair(a,b)
 def test_new_law_promotion(self):
  a,b=fixture();mutate(b,lambda w:w['protocol_context']['laws'][0].update(admitted=True))
  with self.assertRaisesRegex(ValueError,'law_or_admission'):validate_pair(a,b)
 def test_claim_omission(self):
  a,b=fixture();mutate(b,lambda w:w['protocol_context']['task'].update(required_claims=[]))
  with self.assertRaisesRegex(ValueError,'scope'):validate_pair(a,b)
 def test_stale_hash(self):
  a,b=fixture();b['common_input_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'hash'):validate_pair(a,b)
 def test_evidence_span_changed(self):
  a,b=fixture();mutate(b,lambda w:w['protocol_context']['sources'][0].update(text='Other text'))
  with self.assertRaisesRegex(ValueError,'source_span'):validate_pair(a,b)
if __name__=='__main__':unittest.main()
