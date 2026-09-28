# Task-aware gate and sub-conclusions (candidate)

This candidate separates three outcomes that the historical single-finding
route could conflate:

1. **Legal U**: a locked legal question has a typed decisive gap, with a
   matching caller-attested `task_gap_audit`. Model-provided `coverage=missing`
   or prose alone does not attest a missing document.
2. **Processing/protocol hold**: transport, truncation, JSON/schema, source
   extraction, source binding, or unverified fact–law relation failed. The
   blocked table has no legal conclusion (`conclusion_type=null`). Its raw
   response and `failure_class` are retained.
3. **Task observation**: explicitly caller-locked text/visibility questions
   produce separate source-bound sub-conclusions, never an independent legal
   verdict. Visible text and unreadable graphics remain separate claims.

The old QX `review_task_contract_v2` does **not** activate this new legal gate
by its presence alone. Activation requires `gate_protocol_version` equal to
`task-aware-v1` plus a separately completed task-gap audit and a prompt that
emits `legal_u_basis` for any U. A QX legal U without those items is a
processing/review hold, not a substituted N. Historical outputs remain
unchanged and can be replayed under their original semantics.

The full-bundle `review_task_contract_v1` retains its typed legal protocol.
Its `comparison_operand` is required only when the trusted caller explicitly
sets `requires_comparison_operand=true` before inference. This avoids treating
unknown future events as gaps in conditional clause-design questions.

The separate `task_subconclusion_contract_v1` route is opt-in. The caller
supplies typed claims and exact-locator source excerpts; the gate checks
quote binding, required-claim completeness, and source kind. A chart claim
cannot be marked observed by a text index entry. This route is a complement
to, not a replacement for, the legal RAG route and human review. Pure
tender-to-bid text comparison remains in the separate `pair_reasoner` route;
this visibility gate does not infer textual compliance or legal responsiveness.

All tests are offline. No candidate here establishes a new legal-accuracy,
retrieval, or time-saving result. The active formal prompt is not replaced.
