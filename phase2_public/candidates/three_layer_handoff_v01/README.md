# Three-layer completion and handoff candidate

## Status and approval

The user approved the design on 2026-09-23. This package implements an isolated
offline candidate. It is **not production-enabled**, not a new LLM experiment,
and not a replacement for the frozen v4.1.x package.

Design: ../../designs/three_layer_handoff_v01/PROTOCOL_CANDIDATE.md

The runtime wire version is scope-completion-handoff-v0.1-candidate.
The design-version identifier is not a runtime protocol identifier.

## What is implemented

- A single specification for required fields, enums, dependency-kind pairs,
  task-mode/target mappings, claim-state constraints, relationship rules,
  derivation priorities, mechanical aliases and rule identifiers.
- Explicit per-required-claim bookkeeping; no guessed missing claims.
- Gate-derived overall completion and human-handoff presentation status.
- Explicit reuse of given source evidence/check IDs; no implicit trigger linkage.
- Fail-closed response/task/source binding and law-admission checks.
- Separate technical failure, protocol error, unresolved scope, unassessed work
  and declared decisive gaps.
- Raw response preservation and separately logged mechanical normalization.
- Shared JSON/Markdown/typed Excel-column projection; a legacy-output barrier.
  No U/N/R projection is provided.
- Offline synthetic fixtures only; no external provider client or credential access.

Python standard library only for this new suite. The package also reads the
unchanged sibling scope_dependency_v41/src/question_scope_signals.py helper.
Use the repository layout, not this folder alone. The legacy package and its
other dependencies are not imported by the new protocol.

## Reproduce

From this directory, using Python 3.10 or newer:

    python generate.py --check
    python run_offline.py --output /path/to/a/new/offline-run-directory

The output directory must not exist. It stores all results and refuses overwrite.
Socket connection and name-resolution routes are disabled while the new tests run.
No API keys, embeddings, model weights, actual contracts or expert sheets are needed.

Generated files are deterministic products of spec.py:
generated/protocol.spec.json and generated/prompt_candidate.md.
The JSON is a documented restricted schema dialect, not full JSON Schema.
The prompt is an isolated field/relationship protocol supplement, NOT a complete
replacement for the application's substantive compliance instructions.

## Trusted input envelope

gate.seal_context is a caller-side construction helper used BEFORE inference,
not a model-side repair operation. Its digests are change-detection bindings,
not digital signatures and not proof of human approval.

The caller supplies:
- task: locked question, mode, target, stage, exclusions and required claims/dependencies;
- sources: input-bound source segments, identifiers, locators and document hashes;
- evidence_registry: exact quotes tied to source segment, locator and document hash;
- laws: chunk identity, text, locator/source hash and upstream admission,
  independent-evidence, geographical/scope applicability and temporal-status metadata.

The gate checks consistency of this envelope, response bindings and citations.
It does NOT fetch laws, confirm official legal status online, prove that the
upstream document hash belongs to an authentic original, or create reliable
physical locators from unavailable OCR. Those remain upstream duties.

Law applicability/time marked unknown cannot support an assessed legal check.
Supplement-only/unadmitted evidence cannot become independent legal support.
All output remains subject to human review.

## Four preserved guard families

1. An observed conflict needs explicit, resolvable pointers to both declared sides.
   Two IDs or exact text matches do not prove a genuine semantic/legal conflict.
2. Declared decisive gaps cannot coexist with an assessed status for that claim.
   Useful partial handoff does not erase missing dependencies or permit overall N.
3. Every locked claim occurs exactly once. Explicit not_assessed is distinct
   from omission; neither is silently turned into a completed legal judgment.
4. The model cannot exclude required dependencies or narrow the locked task.
   A requirement-not-applicable finding remains inside the original claim.

Mixed-material detection remains a finite conservative vocabulary guard, not
a general language classifier. The v4.1.2 alias enhancement remains OFF/not imported.
Novel paraphrases, legal entailment, omitted but undeclared dependencies and
semantic sufficiency still need human/independent evaluation.

## Validation, limitations and next boundary

See VALIDATION_RECORD.md. The latest new-suite run passed 35 test methods,
with 134 fixture executions, including 28 planned guard groups. These are
software cases, not independent legal examples or measures of model efficacy.

New Excel support is currently a typed column projection only. Actual workbook
writing/rendering and production-runner integration are NOT implemented.
Legacy workbook/verdict consumers explicitly reject this protocol.
No existing workbook was edited by this candidate.

The counter named handoff_presentation_counts describes software routing,
not joint handoff effectiveness. Legal accuracy, expert agreement and joint
handoff effectiveness are null. Raw and normalized structural conformance
are reported separately; no new legal-score claim is made.

Future integration must keep:
- task/claim and law-admission preparation outside model authority;
- original raw response and downstream projection versioning;
- explicit new-protocol handling in all UI/export/statistical consumers;
- no historical response backfill and no automatic U-to-N migration.

Production promotion, LLM generation tests, historical rescoring, input/context
changes and activation of other candidates remain separate approval steps.
