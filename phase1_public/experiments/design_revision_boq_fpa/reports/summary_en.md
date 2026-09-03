## Material Passport

- Origin Skill: experiment-agent
- Origin Mode: run
- Origin Date: 2026-09-03
- Verification Status: VERIFIED
- Version Label: exp_result_v1

## Experiment Result

- **ID**: design_boq_fpa_pilot_v1
- **Type**: analysis
- **Status**: completed
- **Command**: `python src/generate_dataset.py --output inputs/cases.jsonl` followed by `python -m unittest discover -s tests -p "test_*.py" -v` and `python src/experiment.py --root .`
- **Working Directory**: repository-relative folder `phase1_public/experiments/design_revision_boq_fpa`
- **Duration**: not recorded as a scientific metric; the deterministic outputs do not depend on wall-clock time.
- **Exit Code**: 0

### Objective and boundary

This pilot tests whether a forced provenance attribution gate changes mapping decisions on 24 synthetic design-revision-to-BoQ episodes. M1 always selects the top deterministic lexical candidate. M2 adds source/version/locator support, conflict detection and a score-margin gate. The results are mechanism evidence only; they are not evidence of real-project productivity, cost savings or contractual validity.

### Measured overall results

| Method | Decision accuracy | Gold-accept recall | Accepted accuracy | Coverage | Unsupported attribution | High-confidence error | Provenance resolvability | Appropriate abstention |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M1 | 0.250 | 1.000 | 0.250 | 1.000 | 0.750 | 0.500 | 0.750 | 0.000 |
| M2 | 1.000 | 1.000 | 1.000 | 0.250 | 0.000 | 0.000 | 1.000 | 1.000 |

### Case-type stratification

The machine-readable `outputs/metrics.json` and `outputs/metrics.csv` contain the complete case-type breakdown. The six explicit cases were accepted by both methods. The 18 ambiguous, conflicting or insufficient-evidence cases were accepted by M1 and abstained by M2.

### Output files

- `inputs/cases.jsonl` — 24 canonical synthetic cases.
- `outputs/traces.jsonl` — one auditable trace per case with source versions, locators, candidate BoQ records, gold status, support evidence and conflict evidence.
- `outputs/metrics.json` and `outputs/metrics.csv` — overall and stratified metrics.
- `reports/summary_en.md` and `reports/summary_zh.md` — bilingual interpretation.
- `manifest.json` — SHA-256 hashes for deterministic artifacts, excluding the manifest itself.

### Anomalies detected

None. The run is deterministic and uses no external API, LLM, BIM model or blockchain.

### Limitations

The dataset is synthetic, the lexical scorer is intentionally simple, no language model is called, and no BIM or blockchain representation is used. The pilot does not establish generalisation to Hong Kong or other project settings, nor does it prove that the gate improves professional review outcomes. Those questions require authorised data and qualified reviewers in later research.
