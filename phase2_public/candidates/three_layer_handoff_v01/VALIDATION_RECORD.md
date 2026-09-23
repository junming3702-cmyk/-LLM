# Offline validation record

## Material Passport

- Origin Skill / Mode: academic-research-suite / experiment-agent / run.
- Date: 2026-09-23.
- Version: scope-completion-handoff-v0.1-candidate.
- Verification Status: VERIFIED for the latest new deterministic fixture suite only.
- No external LLM, retrieval, OCR, or legal-status verification calls were made.
- Not production-enabled. Not an accuracy or human-handoff-effectiveness study.

## Recorded attempts

| Attempt | Result | Boundary |
|---|---|---|
| New suite 01 | 34 methods, 132 recorded scenario executions; 1 failure, 0 errors | All 28 planned guard groups passed. Same-source snapshot equality failed because Python tuple containers serialize to JSON arrays. Failure retained. |
| New suite 02 | 34 methods, 132 recorded scenario executions; 0 failures, 0 errors | Specification containers changed to JSON-compatible lists without changing the serialized rules or priorities. Consumer columns also separated claim-specific gaps from whole-question gaps, with assertions added. |
| New suite 03 (final) | 35 methods, 134 recorded scenario executions; 0 failures, 0 errors | Added an explicit ledger-presence-versus-protocol-validity guard. A complete ledger may still fail evidence/relationship checks; this does not change any U/N/R label. |
| Frozen sibling regression 01 | Import stopped before test execution | Bundled verification Python lacks sentence_transformers. No dependencies installed, no retry, and no new 328-test pass claimed. |

All three new-suite attempts remain separate in the local model validation
directory. They must not be merged into a claim of first-attempt success.
Source hashes were recorded for each completed run. Private local file paths
and execution logs are not required for this public model description.

Latest new-suite source-spec SHA256 (canonical JSON serialization):
5f52eb9da7871d6552ceab68f7e17f9c173fa1f69969f30b4304a4b44040505c

## What was checked

- 28 planned guard groups plus 7 robustness/snapshot/consumer test methods.
- 134 fixture executions, including intentionally malformed and invalid inputs.
- No unexpected overall-complete release among these prescribed expectations.
- Raw response and trusted context unchanged on every recorded invocation.
- Zero observed network attempts in the new suite, with transport functions disabled.
- Explicit outside-scope item, true decisive gap, partial completion, no completed
  claims with bounded handoff, unknown relationship and technical failure paths.
- Mechanical normalization records remain distinct from raw conformance.
- New JSON/Markdown/typed Excel-column projections preserve the same statuses.
- Legacy output/barrier refuses fabricated U/N/R or workbook compatibility.

Not checked: actual new XLSX creation/rendering, production-runner integration,
arbitrary natural-language semantic consistency, correct legal applicability
beyond caller metadata, LLM generation quality, independent legal truth or
expert productivity/effectiveness.

The sibling regression failed during import, not because an old test assertion
failed. Nonetheless it is unverified in this environment and is not reported
as passed.

## Interpretation limits

The negative fixtures deliberately dominate the suite. Their protocol holds
are expected defenses, not an estimate of how often a real LLM will fail.
Passing all test methods does not imply every legal dependency will be discovered
or that harmful semantic paraphrases cannot bypass a finite lexical guard.

Useful partial information can be routed to human review while decisive gaps
remain. That routing is the tested software behavior; legal accuracy,
Recall@5, MRR, expert agreement and joint handoff effectiveness were not recomputed.
