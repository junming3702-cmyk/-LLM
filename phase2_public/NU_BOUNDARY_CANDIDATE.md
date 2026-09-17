# Opt-in question-relative answerability candidate

This candidate distinguishes bounded textual pre-review from document-completeness and actual-conduct verification. It is disabled by default. It does not replace the production system prompt or certify legal correctness.

Enable both the final-reasoning prompt addition and deterministic audit with `run_final_reasoning(..., nu_boundary=True)`. Standalone gate replay uses `apply_gate(..., nu_boundary=True)`. The policy text is reproduced in `prompts/nu_boundary_candidate_v1.md`; the executable constant is in `src/nu_boundary_policy.py`.

Every finding must include `decision_basis` with the exact runtime review question, review target, answerability, completed comparisons and typed gaps. A bounded no-issue statement needs an independent applicable cited provision, an exact supplied document quote and locator, and a substantive comparison. This verifies structure and provenance, not entailment or legal correctness.

Required documents missing from an examined package and evidence missing from the current input both remain insufficient. Missing decisive rules, comparison values and applicability also remain insufficient. Authenticity or future-performance follow-up alone does not make a textual question unanswerable, but stays decisive when it is the actual review task. No-hit or supplement-only material is not proof of compliance.

Missing/invalid decision-basis schema is blocked as a technical invalid output, not counted as valid abstention. All output remains subject to human second review. Existing provenance, geographic applicability and risk safeguards remain active. No record-ID rules, expert labels or specific project answers are included.

Synthetic regression coverage: `tests/test_nu_boundary_policy.py`. Run with the model environment, source and test directories on the Python path. Frozen private experiment data and evaluation workbooks must remain outside the public repository.
