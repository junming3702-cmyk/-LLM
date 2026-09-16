# P1: isolated public-law article verification

Status: **engineering experiment; target list and legal version/applicability confirmation remain pending human review**. This does not modify the evaluated model, its prompt, corpus, frozen outputs, or expert-study files. No new LLM reasoning, MinerU requests, or automatic discovery are performed.

## What is being tested

The approved sequence is target verification (P1), then separately approved bounded discovery (P2), then separately approved independent retrieval/reasoning evaluation (P3). This directory implements P1 only. Ten assistant-prepared target articles from five public government-hosted sources are development fixtures, not human-confirmed gold labels. They cover national and local instruments, cross-references/qualifications, and an explicitly historical instrument. Historical content is useful to test rejection, not a current-law recommendation.

`source_targets.json` keeps title, issuer, instrument type, actual legal level, geographic scope, candidate version anchors and source URL. Publication-page dates are not silently equated to commencement dates. Known historical expiry metadata is recorded separately. Unknown/uncertified dates, applicability and source provenance must be settled by an operator before admission.

`verification.py`:

1. Fetches exact allowlisted public HTTPS URLs with TLS validation, public-IP checks, no redirects or automatic retry, a 2 MB response limit and 15 s socket timeout. This is a finite URL verifier, not a search tool or a general URL downloader.
2. Extracts a uniquely identified article bounded by the next article, excluding a following chapter heading. It rejects missing/ambiguous boundaries. A selected phrase must occur inside that article, not elsewhere on the page. Optional complete-quote comparison supports a human-confirmed reference later.
3. Records raw/normalized snapshot hashes, complete extracted article, article hash and normalized-snapshot character offsets. Offsets are not physical PDF pages or live-page anchors. A downstream citation must carry the snapshot identifier and article.
4. Keeps every fetched article `pending_human_confirmation`. An independent, operator-controlled review must bind the exact source/content/version hashes and declare an applicable date interval, geography and allowed project types. The pure admission demonstration also requires project facts to match. It does not write anything into RAG or alter final model outputs.

Externally acquired national law retains its actual legal level. Acquisition channel, legal rank and admission status are different fields. Local applicability is never inferred from retrieval similarity. The confirmation examples in tests are synthetic and are **not** human approvals.

## Run

Python 3.12+, standard library only. From the repository root:

```text
python -m unittest discover -s phase2_public/experiments/external_verification_p1_v1 -p "test_*.py" -v
python phase2_public/experiments/external_verification_p1_v1/run_verification.py --live --out .local_runs/p1_live
python phase2_public/experiments/external_verification_p1_v1/run_verification.py --replay .local_runs/p1_live --out .local_runs/p1_replay
```

Output directories must be new. Replay requires the run report, HTML snapshots and metadata from the original live run. It verifies URL/hash bindings and makes no network call. `--reuse EXISTING_RUN` may be combined with `--live` to reuse successful snapshots, with URL/hash checks; it is not a silent retry. An inaccessible source is reported separately from an article that could not be parsed. No unavailable response is interpreted as absence of applicable law.

## Observed development run, 2026-09-16

- First run: 4/5 URLs returned usable HTML; the former local-government URL returned HTTP 404, leaving 8/10 machine-verified targets.
- The failed URL and failure reason were retained. A government-hosted alternative for the same local instrument was added as an **unconfirmed provenance/version candidate**, not a certified substitute.
- Follow-up reused the four successful snapshots and fetched the alternative once: 5/5 sources available, 10/10 target articles extracted, **0 human confirmations, 0 legal-evidence admissions**.
- Offline replay reproduced all ten article hashes and locators. An earlier replay invoked with an incorrect snapshot path failed closed; its record was retained locally before correcting the invocation.
- 29 offline regression tests passed, including wrong article, changed number/negation, duplicate/missing boundary, stale hashes, wrong/missing local scope, missing project type, invalid review schema and out-of-window/historical dates. Positive admission exists only in a clearly synthetic unit-test record.

These are fixture/transport results, **not Recall@K, MRR, legal accuracy, independent human validation or improvement over the frozen model**. No expert ratings or contract excerpts were used or uploaded. Runtime snapshots are excluded from Git.

## Limitations and next approval point

The plan requires a human-confirmed target list. The prepared list and quoted articles are awaiting that step; P1 must not be described as fully accepted before it is recorded. Human review also needs to check exceptions and cross-referenced provisions; extracting a whole article alone does not resolve its applicability.

The HTML parser deliberately supports a narrow, inspectable article layout. It rejects final articles without a following boundary and does not parse PDF or dynamic JavaScript pages. Phrase matching is a preliminary consistency check, not complete legal-text authentication. A current snapshot does not establish current legal validity.

The network guard is limited to reviewed exact URLs. DNS is checked before the request, but the standard library/proxy performs its own connection resolution: this is not a claim of complete DNS-rebinding resistance. Redirects are blocked rather than followed. Socket timeout is not a strict total run deadline. Do not expose this function as an untrusted arbitrary-URL endpoint.

Production fallback integration, automatic discovery, budgeted per-issue routing, and final-output/Excel citation integration require a later approved stage and separate tests. Keep the evaluated model frozen.
