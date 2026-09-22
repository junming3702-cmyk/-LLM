"""No network, secrets, or real documents needed for registration tests."""
import importlib.util
from pathlib import Path
import unittest

RUNNER = Path(__file__).resolve().parents[1]/'experiments/scope_boundary_v1/run_factorial_online.py'
spec = importlib.util.spec_from_file_location('scope_factorial', RUNNER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RegistrationTests(unittest.TestCase):
    def fixture(self):
        return {'issue_id':'SYN-001','document_id':'SYN-DOC',
            'document_location':'synthetic paragraph 1','document_excerpt':'合成测试条款。'}

    def test_four_arm_order_balanced_within_one(self):
        arms = tuple(module.ARMS)
        counts = {a:[0]*4 for a in arms}
        for i in range(45):
            order = module.order_for(i, arms)
            self.assertEqual(set(order), set(arms))
            for j,a in enumerate(order): counts[a][j] += 1
        for values in counts.values(): self.assertLessEqual(max(values)-min(values),1)

    def test_runtime_allowed(self):
        module.validate_rows([self.fixture()])

    def test_expert_and_secret_fields_rejected(self):
        for field in ('expected_label','expert_score','api_key'):
            with self.assertRaises(ValueError):
                module.validate_rows([{**self.fixture(),field:'hidden'}])

    def test_nested_expert_rejected(self):
        with self.assertRaises(ValueError):
            module.validate_rows([{**self.fixture(),'runtime_project_context':{'expert_score':5}}])

    def test_duplicate_empty_and_unsafe_inputs_rejected(self):
        for rows in ([], [self.fixture(),self.fixture()],
                [{**self.fixture(),'issue_id':'../escape'}],
                [{**self.fixture(),'document_excerpt':''}]):
            with self.assertRaises(ValueError): module.validate_rows(rows)


if __name__ == '__main__': unittest.main()
