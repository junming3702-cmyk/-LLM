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
- Shared JSON/Markdown/typed Excel-column projection, provenance-checked new XLSX
  export and exact readback; a legacy-output barrier.
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

See VALIDATION_RECORD.md. The latest new-suite run passed 46 test methods
(35 protocol plus 11 export guards), with 134 recorded protocol fixture
executions, including 28 planned guard groups. These are
software cases, not independent legal examples or measures of model efficacy.

New Excel support writes a separate four-sheet workbook using the bundled
Artifact Tool. Original bytes and input/result hashes accompany each export.
Every saved result is reproduced from the exact raw response, execution metadata
and trusted context; mismatches are rejected, never silently replaced.
Contract/source excerpts, law text and locators are expanded only for protocol-valid
results. Technical/protocol failures retain diagnostic rows, not purported legal
checks. Export cannot fill missing legal judgments or map states to U/N/R.
Production-runner integration is NOT enabled.
Legacy workbook/verdict consumers explicitly reject this protocol.
No existing workbook was edited by this candidate.

## Reproduce the frozen legacy regression

Use the existing Python environment that already contains the inherited retrieval
dependencies. If only the Excel reader is missing, install the two pinned packages
from offline_excel_requirements.txt into a NEW isolated dependency directory using
pip's --target option. Do not mix the bundled native/ML libraries into that environment.

    ./run_legacy_regression.ps1 -Python /path/to/existing/python.exe -DependencyDirectory /path/to/isolated-overlay -OutputDirectory /path/to/new-run

The wrapper restores process environment variables afterward, enables offline HF
flags and invokes the unchanged frozen runner. The runner disables socket connection
functions, directs temporary files into the output directory and verifies frozen
source hashes. It loads no API keys and makes no model requests. Its network_calls
field is a fixed legacy field, not a counted network-attempt metric.
The 328-method suite passed both directly and through this wrapper on 2026-09-23.

## Reproduce the new workbook

Use the app's dependency loader to locate the bundled Node and node_modules.
In a separate writable runtime directory, create a node_modules junction/symlink
to that bundled directory. Do not install packages into the repository.

    python export_examples.py --output /path/to/new-examples/records.json
    python export_review.py --input /path/to/new-examples/records.json --output /path/to/new-export --node /path/to/bundled/node --runtime /path/to/runtime-directory
    python verify_xlsx.py --output /path/to/new-export

The last command requires openpyxl for READ-ONLY independent verification, not
authoring. Input is a list of case_id/context/result/execution envelopes. Execution
must explicitly contain finish_reason and transport_ok. Context is the original
trusted envelope, not reconstructed from old scores or invented locators.
Use the Python bridge, not the presentation-only JS file, as the entry point.

Sheets: three-layer review, checks/evidence, gap tasks, processing audit.
The human conclusion and comment columns start blank. They do not automatically
change any model status. All results still require human review. Technical nulls
are not zeros or N. Raw and mechanically normalized conformance remain separate.
Long cells over the Excel limit or illegal control characters are rejected rather
than silently truncated. Leading '=' is escaped for typed literal text; export
and an independent reader check exact values and absence of formulas.

Only deliver exports with export_manifest.json AND passed xlsx_checks.json;
independent_readback.json records the separate reader check. A failed attempt may
retain an intermediate workbook for diagnosis and must not be treated as approved.
The exported workbook is a review projection, not a production deployment or an
expert-response import/scoring implementation.

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
