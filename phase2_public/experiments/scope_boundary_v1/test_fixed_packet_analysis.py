import json
import unittest
from copy import deepcopy
from analyse_fixed_packet_reasoning import check_request


class RequestIdentityTests(unittest.TestCase):
    def setUp(self):
        self.runtime={'issue_id':'SYN-001','contract_evidence':{'document_excerpt':'合成条款'}}
        self.binding={'requested_model':'deepseek-v4-flash'}
        self.body={'model':'deepseek-v4-flash','max_tokens':16384,'temperature':.1,
            'thinking':{'type':'enabled'},'reasoning_effort':'low',
            'messages':[{'role':'system','content':'synthetic prompt'},
                        {'role':'user','content':json.dumps(self.runtime)}]}

    def test_exact_passes(self):
        check_request(self.body,self.runtime,'synthetic prompt',self.binding)

    def test_modified_evidence_fails(self):
        runtime=deepcopy(self.runtime); runtime['contract_evidence']['document_excerpt']='改动'
        with self.assertRaises(ValueError): check_request(self.body,runtime,'synthetic prompt',self.binding)

    def test_modified_prompt_fails(self):
        with self.assertRaises(ValueError): check_request(self.body,self.runtime,'new prompt',self.binding)

    def test_modified_model_parameter_fails(self):
        self.body['temperature']=1
        with self.assertRaises(ValueError): check_request(self.body,self.runtime,'synthetic prompt',self.binding)


if __name__=='__main__': unittest.main()
