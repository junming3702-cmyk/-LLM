# Code Experiment Plan

## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: plan
- Origin Date: 2026-09-03
- Verification Status: UNVERIFIED
- Version Label: code_plan_v1

## Experiment Overview

- **Title**: Deterministic Design-Revision-to-BoQ Forced-Provenance Attribution Pilot
- **Objective**: Test whether a forced provenance gate prevents unsupported or ambiguous top-candidate attribution.
- **Hypothesis**: M2 will trade coverage for higher decision correctness, lower unsupported attribution and more appropriate abstention than unconstrained M1 on deliberately difficult synthetic cases.
- **Type**: analysis

## Setup

- **Language/Framework**: Python standard library only
- **Entry Command**: `python src/experiment.py --root .`
- **Working Directory**: repository-relative folder `phase1_public/experiments/design_revision_boq_fpa`
- **Dependencies**: None beyond the Python standard library
- **Environment**: Windows/local filesystem; no GPU, network or external service

## Inputs

| Input | Path | Description |
|---|---|---|
| Synthetic cases | `inputs/cases.jsonl` | 24 auditable episodes: six each of explicit mapping, ambiguous alternatives, cross-document/version conflict and insufficient evidence. |
| Configuration | `config.json` | Thresholds, model-routing record and data policy. |

## Expected Outputs

| Output | Path | Format | Success Criterion |
|---|---|---|---|
| Per-case traces | `outputs/traces.jsonl` | JSONL | 24 records with source/version/locator, candidate BoQ, gold, support/conflict evidence and M1/M2 decisions. |
| Metrics | `outputs/metrics.json` | JSON | Overall and case-type metrics for both methods. |
| Metrics table | `outputs/metrics.csv` | CSV | Header plus ten deterministic method/type rows (overall plus four case types). |
| Hash manifest | `manifest.json` | JSON | SHA-256 for deterministic artifacts. |
| Bilingual reports | `reports/summary_en.md`, `reports/summary_zh.md` | Markdown | Results, boundaries and limitations present. |

## Monitoring Configuration

- **Timeout**: 30 minutes hard limit; expected run is short.
- **Monitor files**: `logs/run.log`
- **Experiment type override**: analysis
- **Metric file**: `outputs/metrics.json`
- **Metric key**: `overall.M2.decision_accuracy`

## Analysis Plan

- **Primary metrics**: decision accuracy, gold-accept recall, accepted accuracy, unsupported attribution, provenance resolvability and appropriate abstention.
- **Success threshold**: no pre-registered performance claim; the pilot succeeds if tests pass, all 24 traces are emitted, and M2 exhibits the expected gate behavior on its labelled cases.
- **Comparison**: M1 unconstrained top-candidate mapper versus M2 forced-provenance gate.

## Reproducibility boundary

The generator, input JSONL, source code, tests and output manifest remain inside this E-drive directory. The experiment is deterministic, uses no randomness, and makes no external API calls. A replay should produce byte-identical deterministic artifacts except for any user-added local diagnostic files.
