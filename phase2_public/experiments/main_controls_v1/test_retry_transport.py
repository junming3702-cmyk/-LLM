import unittest
from retry_transport import is_transport_failure

class TransportEligibilityTests(unittest.TestCase):
    def test_only_failed_transport(self):
        result={'gated_observation':{'status':'execution_failed'}}
        self.assertTrue(is_transport_failure(result,[{'ok':False,'http_status':None,'transport_error':'ProxyError'}]))
    def test_no_retry_for_quality_or_success(self):
        for status in ('completed','invalid_output','gate_blocked'):
            self.assertFalse(is_transport_failure({'gated_observation':{'status':status}},[{'ok':False,'http_status':None,'transport_error':'ProxyError'}]))
    def test_http_failure_not_transport(self):
        self.assertFalse(is_transport_failure({'gated_observation':{'status':'execution_failed'}},[{'ok':False,'http_status':500,'transport_error':None}]))
    def test_no_observed_failure_not_retryable(self):
        self.assertFalse(is_transport_failure({'gated_observation':{'status':'execution_failed'}},[]))

if __name__=='__main__':unittest.main()
