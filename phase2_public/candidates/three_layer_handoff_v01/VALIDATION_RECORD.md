# Offline validation record

This document preserves the initial offline sequence. A separately authorized
online follow-up is described at the end; initial "no calls" statements refer
only to the corresponding offline runs, not all subsequent development.

## Material Passport

- Origin Skill / Mode: academic-research-suite / experiment-agent / run.
- Date: 2026-09-23.
- Version: scope-completion-handoff-v0.1-candidate.
- Verification Status: VERIFIED for the latest new deterministic fixture suite only.
- Follow-up verification: frozen legacy regression and actual XLSX bridge also
  verified offline on 2026-09-23; no substantive gate or prompt change.
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

Not checked in the initial implementation: actual new XLSX creation/rendering, production-runner integration,
arbitrary natural-language semantic consistency, correct legal applicability
beyond caller metadata, LLM generation quality, independent legal truth or
expert productivity/effectiveness.

The initial sibling regression failed during import, not because an old test
assertion failed. It was unverified at that handoff. The separately authorized
environment repair and follow-up evidence below supersede that open item, without
erasing its failed attempt.

## Authorized follow-up: legacy environment and actual XLSX bridge

- Existing project Python has sentence-transformers 3.4.1 and torch 2.5.1+cpu.
  Only openpyxl 3.1.5 and et-xmlfile 2.0.0 were added in an isolated dependency
  overlay, without changing the project environment or frozen source code.
- Frozen regression 02: 328 methods/groups, 0 failures, 0 errors, 0 skipped;
  frozen source hashes preserved. The unchanged suite includes its old XLSX test.
- Frozen regression 03: repeat through the new reusable environment wrapper,
  328 methods/groups, 0 failures/errors/skips; frozen source hashes preserved.
- New suite 04 and final suite 05: 46 test methods each (35 existing + 11 export),
  134 recorded protocol scenarios, 0 failures/errors, 0 observed socket attempts,
  0 unexpected overall-complete releases. Export guards also exercise saved-result
  integrity, original-versus-normalized conformance, typed nulls and all four
  blocking guard families. Repeated executions are not independent observations.
- XLSX attempt 01: 12 synthetic envelopes exported/read back successfully.
- XLSX attempt 02: added literal-text guard; exact readback failed because an
  unnecessary escape before '@' became a visible apostrophe. Attempt retained.
- XLSX attempt 03 (final): escaping restricted to the documented leading '='
  case. 13 synthetic envelopes produced 16 claim/diagnostic rows, 9 check rows,
  5 gap rows and 13 processing-audit rows. Artifact Tool exact readback passed.
- Independent openpyxl read-only verification: all 674 header/data cells matched;
  nulls, booleans, 2 formula-like literal cells, 4 tables, C7 frozen panes, hidden
  gridlines and 2 conditional-format ranges verified. No formula/error cells.
  File hash unchanged after verification.
- All four sheets rendered and visually reviewed; the literal-text and
  mechanical-normalization rows were additionally rendered from the saved file.
  Microsoft Excel desktop interaction was not tested.
- The 134 recorded protocol result objects from suite 05 are exactly equal to
  the original final suite 03 objects. Current executable hashes match suite 05.

Gate.py, spec.py, generated prompt/spec files, the frozen v4.1.x package,
historical model responses, reference labels and expert workbooks were not edited.

## Authorized bounded online follow-up (2026-09-23)

- New suite 06: 46 methods, 134 recorded protocol fixture executions, no
  failures/errors/network attempts/unexpected complete releases.
- Five separate client/adapter tests passed: valid input contexts, no answer
  keys in requests, unknown applicability retained, offline preparation/refusal
  to overwrite, and snapshot-versus-original provenance with unknown law status.
- Frozen regression 04: 328 methods, no failures/errors/skips; frozen code hashes
  preserved. These counts do not represent independent legal cases.
- Eight fictional scenarios were called once each under frozen requests. All
  eight final responses had finish_reason=stop, raw structural and full protocol
  conformance, and the locally specified claim-state/finding outcomes. No
  mechanical normalization was needed. Expected outcomes were not sent.
- These include partial completion, missing rule, unknown applicability,
  unreadable material, and incomplete actual-submission input. No real laws or
  private source text are distributed in this public record.
- Optional private development diagnostics and their failures are retained in
  the local research record; they are not treated as independent holdout accuracy.
- The offline Excel bridge can also review online records without new inference.
  The exporter replays the gate from exact raw content/context and requires full
  result equality. An exported workbook does not constitute semantic approval.
- No production switch, historical response backfill, U/N/R migration or new
  expert-score claim was performed. Further full-batch tests were not initiated.
The final XLSX is only an export/compatibility demonstration using synthetic
records. No new legal accuracy, agreement, retrieval or handoff-effectiveness
metric is computed. Production integration and online validation remain separate.

## Interpretation limits

The negative fixtures deliberately dominate the suite. Their protocol holds
are expected defenses, not an estimate of how often a real LLM will fail.
Passing all test methods does not imply every legal dependency will be discovered
or that harmful semantic paraphrases cannot bypass a finite lexical guard.

Useful partial information can be routed to human review while decisive gaps
remain. That routing is the tested software behavior; legal accuracy,
Recall@5, MRR, expert agreement and joint handoff effectiveness were not recomputed.
