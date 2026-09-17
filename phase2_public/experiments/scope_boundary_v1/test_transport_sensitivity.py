import unittest
from retry_transport_sensitivity import transport_eligible


class EligibilityTests(unittest.TestCase):
    def r(self, status): return {'gated_observation':{'status':status}}
    def test_completed_and_semantic_failures_never_repeated(self):
        failure = [{'ok':False,'transport_error':'ProxyError'}]
        for status in ('completed','invalid_output','gate_blocked'):
            self.assertFalse(transport_eligible(self.r(status),failure))

    def test_only_audited_transient_failure(self):
        r = self.r('execution_failed')
        self.assertTrue(transport_eligible(r,[{'ok':False,'transport_error':'ProxyError'}]))
        self.assertTrue(transport_eligible(r,[{'ok':False,'http_status':503}]))
        self.assertFalse(transport_eligible(r,[{'ok':False,'http_status':401}]))
        self.assertFalse(transport_eligible(r,[{'ok':True,'http_status':200}]))
        self.assertFalse(transport_eligible(r,[]))

if __name__ == '__main__': unittest.main()
