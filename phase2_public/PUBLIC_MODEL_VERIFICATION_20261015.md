# Public model verification — 2026-10-15

## Scope and version

This final synchronization records the currently approved public Phase 2
runtime, alongside the unchanged Phase 1 baseline. It does not change the
inference code, prompts, gate, corpus, dependencies, or experimental results.
The verified runtime source commit is
`21f6ccf8b6d22d0a926a2c7330728711e68967c2`.
The commit containing this record identifies the documentation update.

The [runtime inventory](public_model_inventory_20261015.json) records Git blob
IDs and SHA-256 values for 33 runtime, prompt, operator-skill and reproduction
files. Repository bytes and the tested Windows checkout are identified
separately: line-ending differences do not imply a change of model behavior.
The historical `release_manifest.json` is left unchanged.

The public model includes strict four-level retrieval and applicability
checks; baseline ingestion with conditional MinerU parsing and coordinate OCR
backup; source-locator adaptation; task-aware reasoning and deterministic
post-processing; evidence-bounded external recheck; and human-review exports.
The application model remains `deepseek-v4-flash`. Opt-in experimental modules
and historical branches have not been silently promoted into the default path.
Their individual documentation and evidence-admission policies still apply.

## Offline verification

The existing public reproduction entry point completed successfully in an
already provisioned Python 3.11.5 environment on Windows:

| Check | Result | Interpretation |
|---|---:|---|
| Core `unittest` cases | 97/97 passed | Deterministic public fixtures |
| Full-bundle `unittest` cases | 28/28 passed | Opt-in bundle fixtures, not private projects |
| Additional script-style suites | 5/5 passed | Reported separately from case counts |

The additional scripts are important because ordinary `unittest` discovery
does not execute their plain-function `main()` checks:

- `tests/test_post_llm_gate_v2.py`: 20 regression groups.
- `tests/test_post_llm_recommendation_v1.py`: recommendation fixtures.
- `tests/test_recommendation_comparison_v3.py`: five comparison checks.
- `tests/test_triage_normalization_v1.py`: normalization fixtures.
- `tests/test_triage_response_parser_v1.py`: response-parser fixtures.

The core run used `requests` 2.34.2, `numpy` 2.3.5,
`sentence-transformers` 3.4.1, `torch` 2.5.1+cpu and `openpyxl` 3.1.5.
These are tested environment versions, not a new dependency lock or a claim
that every supported package combination was tested. An initial attempt with
an unprovisioned bundled Python environment failed at dependency import; the
complete provisioned-environment run is the verification reported above.

From the repository root, after installing `phase2_public/requirements.txt`:

```powershell
python phase2_public/reproduce_offline.py --no-install

# Additional existing script-style checks, with source modules on the path:
$env:PYTHONPATH = (Join-Path (Get-Location) 'phase2_public/src')
python phase2_public/tests/test_post_llm_gate_v2.py
python phase2_public/tests/test_post_llm_recommendation_v1.py
python phase2_public/tests/test_recommendation_comparison_v3.py
python phase2_public/tests/test_triage_normalization_v1.py
python phase2_public/tests/test_triage_response_parser_v1.py
```

Alternatively, `python phase2_public/reproduce_offline.py` prepares an ignored
local environment and runs the two `unittest` groups. Package installation
requires network access; the fixture tests do not require LLM, MinerU or
external legal-retrieval calls. This synchronization ran no online inference
or private-project evaluation and downloaded no model weights.

## Publication safety and evidence boundary

The complete tracked public-model tree was checked for credential patterns,
matches to local credential values, private absolute paths, nonempty example
credentials and private-document paths. No matches requiring exclusion were
found. The three existing synthetic BoQ pilot outputs were retained only after
checking their documented synthetic origin and unchanged Git content; this is
not permission to publish arbitrary generated output folders.

Only empty credential placeholders in `.env.example` are tracked. Real `.env`
files, API keys, project PDFs, bidding documents, OCR/API payloads, expert
workbooks, consent records, manuscripts, research-review material, and
scholarship/PhD application documents remain outside this public update.
Private audit logs also remain local.

Passing these fixtures establishes regression consistency for the checked
software contracts. It does not establish independent legal accuracy,
real-project completeness, expert agreement, productivity improvement, or
production readiness. Earlier benchmark denominators and frozen expert-study
versions must not be relabelled as results of this documentation update.
