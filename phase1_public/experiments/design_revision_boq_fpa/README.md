# Design-Revision-to-BoQ Forced-Provenance Attribution Pilot

This folder contains a small, auditable and deterministic experiment for a
forced-provenance attribution (FPA) gate. It uses 24 synthetic episodes across
four balanced case types: explicit mapping, ambiguous alternatives,
cross-document version conflict and insufficient evidence.

## Compared methods

- **M1 — unconstrained mapper:** scores every BoQ candidate and always selects
  the top-ranked candidate.
- **M2 — M1 + FPA gate:** accepts only when the selected candidate has
  resolvable source/version/locator support, no relevant conflict and a clear
  score margin; otherwise it abstains for human review.

## Reproduce

Run from this directory:

```text
python -B src/generate_dataset.py --output inputs/cases.jsonl
python -B -m unittest discover -s tests -p "test_*.py" -v
python -B src/experiment.py --root .
```

The nine-test suite checks the fixed dataset, serialized outputs, metric
arithmetic, manifest integrity and clean-root execution. The experiment uses no
external API and no randomness.

## Headline result

| Method | Accepted / abstained | Decision accuracy | Gold-accept recall | Coverage | Unsupported attribution |
|---|---:|---:|---:|---:|---:|
| M1 | 24 / 0 | 0.250 | 1.000 | 1.000 | 0.750 |
| M2 | 6 / 18 | 1.000 | 1.000 | 0.250 | 0.000 |

M2's decision accuracy includes 18 correct abstentions; it does not mean that
all 24 cases were mapped. The experiment therefore exposes the intended
coverage-risk trade-off rather than claiming universal accuracy.

## Audit trail

- `inputs/cases.jsonl`: canonical synthetic benchmark.
- `outputs/traces.jsonl`: per-case rankings, evidence references and gate
  decisions.
- `outputs/metrics.json` and `metrics.csv`: overall and stratified results.
- `reports/independent_qa.md`: independent recomputation and boundary audit.
- `manifest.json`: SHA-256 manifest for deterministic artifacts.

## Limitations

The data and evidence are synthetic, the mapper is intentionally simple and no
LLM, BIM model, blockchain or real project record is used. This pilot validates
only the internal logic and reproducibility of the gate. It does not establish
real-project accuracy, productivity, contractual validity, professional
acceptance or generalisation.
