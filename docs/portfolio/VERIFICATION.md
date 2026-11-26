# Portfolio verification — 26 November 2026

This record covers the public examples and existing functional checks used for the portfolio update. The runtime and prompts are unchanged.

## Source and environment

- Runtime source commit: `c6c14036fbfbf68cabbd7b8ec1d8aa7abe701ee0`.
- Platform: macOS, arm64; Python **3.12.16**.
- Installed from the existing `phase2_public/requirements.txt` in an isolated environment.
- Key resolved versions: NumPy **2.5.5**, requests **2.34.2**, openpyxl **3.1.5**, sentence-transformers **6.3.0**, PyTorch **2.15.0**.
- Active prompt SHA-256: `13e5c8395805b8c37a8f34c1a6b72e4cbda0750f6226d58106eadf36522d34a8`.

These are the versions used for this run, not a new dependency lock. Package installation used network access. The checks and demonstration did not call LLM, OCR or external-law services or load model weights.

## Executed checks

| Check | Observed result |
| --- | --- |
| Existing core unittest suite | **97 passed** |
| Existing full-bundle fixture suite | **28 passed** |
| `test_post_llm_gate_v2.py` | **20 regression groups passed** |
| `test_post_llm_recommendation_v1.py` | Passed |
| `test_recommendation_comparison_v3.py` | **5 comparison checks passed** |
| `test_triage_normalization_v1.py` | Passed |
| `test_triage_response_parser_v1.py` | Passed |
| `docs/portfolio/run_demo.py` | Completed; generated sample retrieval, two evidence-gate results and a task-visibility result |

The five script-style suites are reported separately because ordinary unittest discovery does not execute their `main()` checks. Their groups are not added to the 125 unittest case count.

## Commands

From the repository root, after installing the existing requirements:

```bash
phase2_public/.venv/bin/python phase2_public/reproduce_offline.py --no-install

export PYTHONPATH=phase2_public/src
phase2_public/.venv/bin/python phase2_public/tests/test_post_llm_gate_v2.py
phase2_public/.venv/bin/python phase2_public/tests/test_post_llm_recommendation_v1.py
phase2_public/.venv/bin/python phase2_public/tests/test_recommendation_comparison_v3.py
phase2_public/.venv/bin/python phase2_public/tests/test_triage_normalization_v1.py
phase2_public/.venv/bin/python phase2_public/tests/test_triage_response_parser_v1.py

phase2_public/.venv/bin/python docs/portfolio/run_demo.py
```

For Windows PowerShell, use `phase2_public\.venv\Scripts\python.exe` and set `$env:PYTHONPATH = "phase2_public/src"`.

## Artifact provenance

The [run manifest](sample-results/run-manifest.json) records the source commit at execution, the wrapper and input hashes, environment versions, and generated-file hashes. The source commit identifies the unchanged runtime used for the run; the new wrapper and showcase files are identified by their own hashes and the commit containing this record.

The [walkthrough](WALKTHROUGH.md) distinguishes sample retrieval from separate preset-response fixtures. The generated JSON is published without replacing its outcomes with illustrative successes. Human review decisions remain unfilled.

The 98.08% retrieval metric and 49/60 reasoning agreement in the main README are historical records, not results rerun here. This verification establishes public-fixture behavior; it does not establish independent legal correctness, expert agreement, real-project completeness, productivity gains or production readiness.
