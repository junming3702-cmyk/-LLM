# Independent QA Report

## Scope and verdict

- **Artifact audited**: `design_boq_fpa_pilot`
- **Audit date**: 2026-09-03
- **Mode**: read-only audit; no source, input, configuration, existing output, manifest, README or existing report was changed.
- **Overall verdict**: **PASS for a bounded deterministic mechanism demonstration; not evidence of real-project performance.**

The initial audit found two high-priority reporting weaknesses: `mapping_accuracy` counted correct abstentions, and the tests depended on the production implementation. The final framework corrects these points by reporting `decision_accuracy` separately from `gold_accept_recall`, accepted accuracy, coverage and appropriate abstention, and by adding independent serialized-artifact/oracle tests. The experiment is internally reproducible and the forced-provenance gate behaves as implemented.

## Checks and pass/fail results

| Check | Result | Evidence |
|---|---|---|
| Unit tests | **PASS** | 9/9 tests passed before and after the final in-place replay with `-B`. |
| Dataset balance | **PASS** | 24 cases; four case types with 6 each; gold status: 6 accept and 18 abstain. |
| Observed input schema | **PASS with caveat** | All 24 records contain the required case-level structures; case IDs are unique; candidate IDs are unique within each case. The observed candidate count is 12 cases with 1 candidate and 12 with 2; support evidence counts are 12/6/6 for 2/1/0; conflict evidence is present in 6 cases. There is no formal JSON Schema or complete type/reference validator. |
| M1/M2 implementation fidelity | **PASS** | Independent recomputation of 48 method-case decisions across status, selected candidate, top candidate, score, margin and gate reasons produced 0 failures. |
| Headline metric recomputation | **PASS arithmetically** | Independent parsing of `inputs/cases.jsonl` and `outputs/traces.jsonl` reproduced the saved headline values exactly. |
| Trace integrity and resolvability | **PASS** | 24 traces; duplicate IDs 0; missing IDs 0; extra IDs 0; input-to-trace mismatches 0; unresolved candidate/evidence references 0. |
| Manifest verification | **PASS at audit time** | 19 manifest entries matched 19 scoped files; missing 0; unmanifested 0; hash/size mismatches 0. This check preceded creation of this report; the report is intentionally not added to the unchanged manifest. |
| Deterministic replay | **PASS** | A replay in an E-drive temporary directory completed; a second replay changed 0 temporary file hashes. Core `traces.jsonl`, `metrics.json` and `metrics.csv` were byte-identical to the committed outputs. |
| E-drive artifact location | **PASS** | Artifacts, logs, caches and temporary replay data are under the E-drive experiment directory; the final README uses portable relative commands and contains no C-drive path. |
| Scientific metric naming | **PASS after correction** | Overall exact outcomes are now `decision_accuracy`; accepted mapping performance, `gold_accept_recall`, coverage and appropriate abstention are reported separately. |
| Test independence | **PASS after correction** | Regression tests are supplemented by independent canonical-input, serialized-output and manifest oracle checks. |

## Independently recomputed metrics

The independent calculation used the canonical input cases and serialized traces. It recomputed lexical ranking, score margin, provenance resolvability, conflict presence, exact case decisions and all denominators without importing the experiment implementation.

| Method | Accepted / abstained | Decision accuracy | Gold-accept recall | Accepted accuracy | Coverage | Unsupported attribution | High-confidence error | Provenance resolvability | Appropriate abstention |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 24 / 0 | 6/24 = 0.250 | 6/6 = 1.000 | 6/24 = 0.250 | 1.000 | 18/24 = 0.750 | 12/24 = 0.500 | 18/24 = 0.750 | 0/18 = 0.000 |
| M2 | 6 / 18 | 24/24 = 1.000 | 6/6 = 1.000 | 6/6 = 1.000 | 0.250 | 0/6 = 0.000 | 0/6 = 0.000 | 6/6 = 1.000 | 18/18 = 1.000 |

The important interpretation is that M2's `decision_accuracy = 1.000` comprises six accepted mappings and 18 correct abstentions. It does not mean that all 24 cases were mapped. M2 retained `gold_accept_recall = 1.000` on the six explicitly mappable cases, while overall coverage fell to 0.250.

### Case-type outcome check

| Case type | Gold | M1 | M2 |
|---|---|---|---|
| `explicit_mapping` (6) | accept | 6 accepted and correct | 6 accepted and correct |
| `ambiguous_alternatives` (6) | abstain | 6 accepted, all unsupported; all 6 are high-confidence errors | 6 abstained appropriately |
| `cross_document_version_conflict` (6) | abstain | 6 accepted, all unsupported; all 6 are high-confidence errors | 6 abstained appropriately |
| `insufficient_evidence` (6) | abstain | 6 accepted, all unsupported and unresolvable | 6 abstained appropriately |

## Implementation and claim audit

### What passes

- M1 always accepts the top deterministic lexical candidate.
- M2 abstains when the score threshold, margin, support-evidence, conflict or provenance condition fails.
- The observed gate thresholds are acceptance score `0.55`, minimum margin `0.15` and minimum support evidence `1`.
- Serialized traces retain the case, design revision, candidate BoQ records, gold label, support/conflict evidence and method decisions.
- Existing reports correctly limit the result to mechanism evidence and explicitly do not claim real-project productivity, cost savings, contractual validity or professional-outcome improvement.

### Initial issues and final disposition

1. **Resolved — metric terminology.** The former `mapping_accuracy` field was renamed `decision_accuracy`; `gold_accept_recall` was added and coverage remains explicit.

   **Remaining boundary:** the perfect decision score is a property of the deliberately constructed synthetic cases, not a generalisation claim.

2. **Resolved — test independence.** The original regression tests are retained, and independent oracle tests now read the canonical JSONL, serialized traces, saved metrics and manifest without using the production metric functions for expected values.

   **Remaining boundary:** the oracle validates this fixed benchmark; it is not external validation on unseen real projects.

3. **Resolved — clean-root execution.** The entry point creates required directories and a clean-root smoke test now passes.

4. **Pass — routing provenance.** `config.json` matches the latest authorised hierarchy: decision layer `gpt-5.6-sol` at `high`, execution layer `gpt-5.6-luna` at `ultra`. The deterministic Python pilot itself did not call either model; the record documents the surrounding workflow.

5. **Resolved — E-drive and portability wording.** The final README uses relative Python commands. All project workspaces, generated artifacts, logs and caches remain under the E-drive experiment directory.

6. **Resolved — manifest portability.** `manifest.json`, `reports/independent_qa.md`, `tmp/`, `__pycache__/` and `*.pyc` are excluded from the deterministic manifest contract.

## Reproduction record

The following read-only checks were completed from the experiment directory:

```text
python -B -m unittest discover -s tests -p "test_*.py" -v
python -B src/experiment.py --root <isolated E-drive replay directory>
```

The isolated replay reported 24 cases, M1 decision accuracy 0.25, M2 decision accuracy 1.0, gold-accept recall 1.0 for both methods, M1 coverage 1.0, M2 coverage 0.25 and M2 appropriate abstention 1.0. A repeated replay produced no changed deterministic file hashes. The final in-place run and the subsequent nine-test suite also completed successfully.

## Final disposition

**Internal mechanism status: PASS.** The gate, traces, corrected metrics, independent oracle checks, clean-root execution and deterministic outputs are coherent.

**Scientific reporting status: PASS with explicit limits.** The pilot is suitable as a bounded synthetic mechanism demonstration. It does not validate real-project accuracy, productivity, contractual validity, professional acceptance, BIM interoperability or blockchain performance.
