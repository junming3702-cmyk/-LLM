# Phase-2 operating runbook

All paths here are **repository-relative**. Run commands from the repository root with Python 3.10+. This document does not authorize any network transmission. Use a new output directory for each run and preserve prior raw/gated results.

## A. Public offline reproduction: one command

```powershell
python phase2_public/reproduce_offline.py
```

On first use this creates an ignored local virtual environment and installs `phase2_public/requirements.txt`. With dependencies already installed:

```powershell
python phase2_public/reproduce_offline.py --no-install --python "PATH_TO_PYTHON"
```

The offline check tests the active core and synthetic full-bundle fixture, prints the active prompt hash, and makes **no** DeepSeek, MinerU, OCR-provider or external-law call. A passing fixture is not real-project accuracy, item recall or cost/time-effectiveness evidence.

## B. Review an actual tender/final-bid bundle

1. Prepare a private copy of [the example bundle manifest](../../../candidates/full_bundle_review_v01/bundle_manifest.example.json) outside the public Git tree. Declare real `tender` and `final_bid` PDF/DOCX paths and their issued/final-submission status. Record project location, type, event date and addenda status from verifiable sources. Do not put evaluation reports, award records, expert labels or raw private documents in the repository.
2. Run offline intake:

```powershell
python phase2_public/candidates/full_bundle_review_v01/bundle_review.py --manifest "PRIVATE_MANIFEST.json" --output-root "NEW_PRIVATE_BUNDLE_DIR"
```

Check `bundle_intake.json`, `coverage.json`, `page_ledger.jsonl`, `candidates.json`, `legal_core_labels.jsonl` and `pair_labels.jsonl`. The parser writes Markdown and locator/quality files under the output directory. The bundle accepts a hash-bound verified pagewise parse cache when supplied by the manifest; that checks identity and page structure, **not** OCR meaning. An addenda inventory is not parsed effective addenda.

3. If some pages are `needs_human_review`, decide whether OCR is necessary before claiming coverage. `phase2_public/src/mineru_precision_preprocessor.py` accepts a source and new output root and uploads only after a separately scoped authorization. Pass its result through `phase2_public/src/mineru_source_locator_adapter.py` with the baseline root; inspect its quality gate and blocked-block log. `phase2_public/src/paddleocr_coordinate_smoke_test.py` is the local coordinate backup. No helper automatically turns an OCR guess into admitted legal evidence. Record unreadable pages even if other pages succeed.
4. Optional **offline developmental** scope audit: `phase2_public/candidates/full_bundle_review_v01/scope_alignment_v1.py` classifies candidate scope using topic probes. Its output is a routing aid, not a verified atomic rule inventory, legal finding or recall score. Inspect exclusions for lost legal duties, particularly in technical-bid pages.
5. Build the machine plan from the exact source manifest:

```powershell
python phase2_public/candidates/full_bundle_review_v01/auto_pre_review.py --mode plan --bundle-output "NEW_PRIVATE_BUNDLE_DIR" --source-manifest "PRIVATE_MANIFEST.json" --output-root "NEW_PRIVATE_PLAN_DIR"
```

Inspect `automation_plan.json`: task, issue, label hash, source location, pairing state, reviewability, privacy indicators, failed/unselected pages and addenda boundary.

## C. Online execution only after data and source review

The bundle's `execute-online` mode needs the same source manifest, an exact-label `approval-file`, positive `--max-issues`, an empty/new output root and `privacy_review_complete=true` after **human inspection of the actual outgoing snippets**. The optional `propose-pilot` mode creates an approval **candidate**; it does not grant permission or guarantee de-identification. Confirm allowed recipient, data categories, sample IDs and API cost ceiling separately before execution. `--max-issues` caps dispatched issues, **not** all internal LLM or external HTTP requests.

The current online legal route uses `deepseek-v4-flash`, the active v11 prompt, full-bundle addendum, four-level retriever and deterministic post-gate. It binds project/task/source IDs, then audits legal-U gaps independently. The paired-text route uses the same model but its own two-source prompt/gate. The legal route's final-token setting can be enlarged for a truncated response, but preserving raw `finish_reason`, channels and usage is mandatory; extra tokens cannot repair a missing source or unsupported legal relation.

If enabled with `--enable-external-fallback --external-manifest "ALLOWLISTED_MANIFEST"`, external lookup is **one** finite recheck after a local preliminary legal U. Log whether dispatch, provider and HTTP calls really occurred; pending candidates require source confirmation. A source-manifest URL hit alone must not be converted to an applicable article. Do not infer a broader Internet search than the configured adapter performed.

Do not put a real key in command arguments or commit it. Load it from the private local environment according to the repository's `.env.example`; keep `.env` ignored. MinerU, DeepSeek and external retrieval have different transmission boundaries.

## D. Assemble and inspect the human-review deliverable

After actual core/pair result directories exist, bind them back to the frozen bundle:

```powershell
python phase2_public/candidates/full_bundle_review_v01/assemble.py --bundle-output "NEW_PRIVATE_BUNDLE_DIR" --core-results "LEGAL_RESULTS_DIR" --pair-results "PAIR_RESULTS_DIR" --output "NEW_REVIEW.json" --excel "NEW_REVIEW.xlsx"
```

The assembler refuses to overwrite existing outputs. Inspect its issue rows **and** coverage notices. It keeps `not_run`, unresolved pairs, failed pages, unverified addenda and excluded files visible. Its optional three-layer handoff is supplemental; without a validated packet, `handoff_status=not_available`, not proof of a complete review.

For every delivered risk check the chain: original and authentic page/block locator → retrieved/admitted article → actor/trigger/phase/exception/threshold comparison → specific difference → human action. For a legal U inspect `legal_u_basis` and the independent `task_gap_audit`; for a processing hold inspect the source-transfer and response diagnostics. A risk row without a concrete comparison is not ready for delivery.

## E. Version and publication safeguards

Record hashes for original inputs, source manifest, corpus, prompt/addendum, source-version overlay, approval list, raw response and gate output. Preserve failed attempts; repair only in a new run or clearly marked replay. The public Git tree may contain code, prompts, schemas, synthetic fixtures, aggregate development records and this skill, but not API keys, private tender/bid excerpts, OCR/API payloads, expert scores or application materials. Do not report retrospective QX30, REAL45 or a previously used complete-project workflow test as a new independent validation.
