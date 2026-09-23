"""Deterministic export guards, separate from gate effect/accuracy metrics."""
from copy import deepcopy
import unittest
import fixtures as f
from gate import evaluate
from export_examples import examples
from export_review import build_packet


class ExportPacketGuards(unittest.TestCase):
    def test_all_fixture_rows_and_no_mutation(self):
        data = examples()
        before = deepcopy(data)
        packet = build_packet(data)
        self.assertEqual(before, data)
        self.assertEqual(13, packet["record_count"])
        self.assertEqual(16, len(packet["sheets"][0]["rows"]))
        self.assertEqual(4, len(packet["sheets"]))
        self.assertIsNone(packet["joint_handoff_effectiveness"])

    def test_partial_claim_gap_is_not_question_gap(self):
        rows = build_packet(examples())["sheets"][0]["rows"]
        a, b = [r for r in rows if r[0] == "SYN-XLSX-partial"]
        self.assertEqual("[]", a[7])
        self.assertEqual('["G1"]', a[8])
        self.assertEqual('["G1"]', b[7])
        self.assertEqual("partial", a[5])
        self.assertIsNone(b[4])

    def test_no_diagnostic_declared_checks_as_valid(self):
        packet = build_packet(examples())
        held = {r[0] for r in packet["sheets"][3]["rows"] if r[1] != "valid"}
        for sheet in packet["sheets"][1:3]:
            self.assertFalse(any(r[0] in held for r in sheet["rows"]))
        for r in packet["sheets"][0]["rows"]:
            if r[0] in held:
                self.assertIsNone(r[4]); self.assertIsNone(r[5])
            self.assertIs(r[11], True)
            self.assertEqual([None, None], r[12:])

    def test_normalization_is_separately_reported(self):
        rows = build_packet(examples())["sheets"][3]["rows"]
        raw, normalized = rows[-3:-1]
        self.assertEqual("protocol_hold", raw[1]); self.assertEqual("valid", normalized[1])
        self.assertIs(raw[2], False); self.assertIs(normalized[2], False)
        self.assertIs(normalized[3], True)
        self.assertNotEqual("[]", normalized[5])
        self.assertEqual(raw[11], normalized[11])

    def test_changed_result_rejected(self):
        for field, value in (("question_completion", "partial"), ("handoff_status", "ready_for_bounded_review"),
                             ("spec_sha256", "a"*64)):
            with self.subTest(field=field):
                data = examples()[:1]
                data[0]["result"][field] = value
                with self.assertRaisesRegex(ValueError, "does_not_match"):
                    build_packet(data)

    def test_changed_context_rejected(self):
        data = examples()[:1]
        data[0]["context"]["sources"][0]["text"] += " changed"
        with self.assertRaisesRegex(ValueError, "does_not_match"):
            build_packet(data)

    def test_fake_effectiveness_and_legacy_rejected(self):
        for field, value in (("joint_handoff_effectiveness", 1), ("legacy_legal_verdict", "N"), ("human_review_required", False)):
            data = examples()[:1]; data[0]["result"][field] = value
            with self.assertRaises(ValueError): build_packet(data)

    def test_duplicate_ids_and_missing_execution_rejected(self):
        data = examples()[:1]
        for bad in ([], data*2, [{k:v for k,v in data[0].items() if k != "execution"}]):
            with self.assertRaises(ValueError): build_packet(bad)

    def test_missing_and_false_are_not_zero(self):
        rows = build_packet(examples())["sheets"][3]["rows"]
        self.assertTrue(all(r[-1] is None for r in rows))
        self.assertTrue(all(r[-2] is False for r in rows))

    def test_oversized_text_refused_not_truncated(self):
        ctx, raw = f.complete()
        raw["claim_assessments"][0]["rationale"] = "x" * 32768
        rec = {"case_id":"long", "context":ctx, "execution":{"finish_reason":"stop", "transport_ok":True},
               "result":evaluate(raw, ctx, finish_reason="stop")}
        with self.assertRaisesRegex(ValueError, "do_not_silently_truncate"):
            build_packet([rec])

    def test_four_guard_families_remain_protocol_holds(self):
        for family in ("missing-trigger", "decisive-assessed", "missing-claim", "narrowed-scope"):
            ctx, raw = f.blocked()
            if family == "missing-trigger": raw["gaps"][1]["trigger_refs"] = []
            if family == "decisive-assessed": raw["claim_assessments"][0].update(assessment_state="assessed", finding="no_supported_issue")
            if family == "missing-claim": raw["claim_assessments"].pop()
            if family == "narrowed-scope": raw["gaps"][0]["task_relation"] = "outside_locked_scope"
            rec = {"case_id":family, "context":ctx, "execution":{"finish_reason":"stop", "transport_ok":True},
                   "result":evaluate(raw, ctx, finish_reason="stop")}
            packet = build_packet([rec])
            self.assertEqual("protocol_hold", packet["sheets"][3]["rows"][0][1])
            self.assertEqual([], packet["sheets"][1]["rows"])


if __name__ == "__main__": unittest.main()
