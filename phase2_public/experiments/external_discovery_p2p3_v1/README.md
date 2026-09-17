# P2 bounded article discovery / P3 prospective evaluation

An **isolated opt-in experiment**, not a replacement for the expert-rated production model.
No original expert outputs, prompts, legal corpus or human responses are changed.

## Implemented P2 path

`preliminary insufficient → one bounded recheck → route by regime/type/jurisdiction → read approved exact-URL snapshots → discover matching articles → quarantine → separate human sidecar → hash/locator/version/scope gate → eligible evidence snapshot → controlled reasoning + citation gate`

- **Discovery mode is `operator-curated`**: an operator finds official detail pages; catalogue entries record the search provenance. Code discovers articles inside these pages without reading P1 target IDs, anchors or gold labels. This is NOT an autonomous search-engine/NPC search API, nor an exhaustive law search.
- Existing P1 sources plus two public official-page candidates are available. Catalogue metadata are proposals, not legal status certifications. CECN/news/practice notes are not eligible independent evidence sources.
- Ranking uses public topic occurrence count; it is an exploratory external candidate ranker, **not a replacement for local BM25+dense hybrid retrieval**. It has no claimed retrieval accuracy yet.
- At most four relevant detail pages per round; zero automatic search-engine requests, redirects or retries. Up to 15 seconds per fetch and 60 seconds for a round, with killable network child processes. Cache hits issue no request. Cancellation cleanup can add a small process-shutdown overhead.
- TLS stays verified, DNS must resolve to public addresses, response bodies are capped at 2 MB and HTML-only, exact URLs are allowlisted. Redirects are blocked, not followed. This inherits P1's operator-controlled URL assumption; it is not a hardened arbitrary-URL public service and does not claim complete DNS-rebinding protection.
- Snapshots are content-addressed and checked against URL/raw/text/article hashes and exact locator spans. Hashes provide integrity, **not publisher authenticity**; provenance still needs human confirmation. A changed response requires a new cache/run directory.
- Candidates retain actual normative level independently of acquisition channel. External national law is not relabelled Level 4.
- Default admission is zero. Human sidecars bind candidate ID, source/quote hashes, title/version, time window, jurisdiction, project type, procurement regime, material facts and review of conditions/exceptions/cross-references. Human admission applies only to that exact context/window.
- Optional experiment-scoped approval additionally binds scope ID, task-spec hash, registered issue IDs and their jurisdiction/type/regime/date hashes. It cannot be reused under a different case ID or by changing that case's registered project context. Full article `evidence_id` is deterministic from source ID, article and quote hash; it is generated for all candidates, without using labels.
- Discovery does not turn no hit, HTTP error, empty page, missing facts or pending confirmation into `valid`. It preserves `insufficient_information_needs_human_confirm` until a separately gated reasoning run has a supported basis.
- `citation_gate` blocks unadmitted/unknown citations and unsupported conclusions. It is a narrow boundary check, **not the full production reasoning gate or an Excel export integration**. Production/hybrid runner integration and A/B/C execution adapters remain pending P3 reference lock and subsequent verification.

## Run (repository root; standard-library Python)

```powershell
python -m unittest discover -s phase2_public/experiments/external_discovery_p2p3_v1 -p "test_*.py"
python phase2_public/experiments/external_discovery_p2p3_v1/run_p2.py --live --out .local_runs/p2_live --cache .local_runs/p2_cache --terms 资质 分包 施工 --regime construction_contract --project-type construction --jurisdiction 四川省 --as-of 2026-09-17
```

For offline replay use the same cache, a **new** output directory and omit `--live`.
`--reviews` accepts a separately controlled human sidecar. Web pages and LLM outputs must never fill this parameter.
`run_p2.py` outputs a candidate report and an **unfilled** sidecar template; it never modifies the corpus.
`export_review_pack.py` prepares human-readable Markdown with full article quotations/locators.

`run_llm_smoke.py` sends three explicitly marked **development** probes only after the operator supplies `--authorized-public-synthetic` and an environment-file path. It requests `deepseek-v4-flash`, temperature 0, max_tokens 2048. It logs requested/returned model, finish reason, usage and channel diagnostics. It selects parsable `reasoning_content` first, otherwise `content`, then runs the citation gate. Credentials and private reasoning text are not persisted. It uses a dedicated probe prompt, not the frozen production prompt. No automatic retry.

## P3 registration history (before the controlled execution below)

`p3_tasks.pending.json` preserves the **initial 30 AI-authored proposals**, distinct from the legacy 60-query set and expert case inputs. They include near-neighbour cases within families and share some development laws: not law-disjoint and not 30 independent projects. Subsequent operator approvals are stored separately and privately; the public proposal file alone is not proof of human approval. They must not be used for tuning while intended as a holdout.

`p3_evaluation.py --prepare PRIVATE_NEW_DIR` snapshots the proposals and exports an unfilled human label file plus a review document. The snapshot is a draft registration, **not a retrospective claim of preregistration or human label lock**.

Before formal A/B/C execution:

1. Human confirms the reference articles (with hashes/versions), applicability, conditions and outcomes.
2. Lock identical task inputs and baseline corpus. If creating controlled local gaps, predeclare the same withholding mask in A/B/C; report separately from naturally missing evidence.
3. Register A local four-layer, B local + legacy fixed access, C local + new article discovery, with matching model/prompt/parameters/time policy. Implement and validate the three execution adapters without exposing reference labels to reasoning.
4. Freeze external snapshots and admit human-confirmed evidence under the same policy; count C's added human effort. Measure network health separately from replay performance.
5. Only then calculate evidence Recall@5, MRR, supported rescues, applicability precision, safety, citation traceability and effort/latency. Report per-family/category descriptive results; no independence or causal efficiency claims.

The original evaluator validates three-arm coverage/controls and human lock, then calculates macro **evidence** Recall@5 (not hit rate), reciprocal rank over the supplied ranking, outcome agreement, safety and traceability counts. Zero-relevant tasks are excluded from retrieval denominators. The controlled execution runner and additional offline analyzer are described below. Legal-grounding/precision/efficiency claims still require appropriate adjudication/effort records; do not fabricate them from software tests.

## Materializing an issued approval

`freeze_admission.py` requires an out-of-band user admission file, an approved task snapshot, exact article bindings and original source caches. It creates a **new private directory** with scoped review sidecars, frozen source snapshots, an approved library, locked evaluator labels and positive/negative gate checks. It does not generate its own consent, overwrite the pending files or modify the production corpus.

When an operator approves only the registered experiment date, the `valid_from` / `verified_through` pair denotes a **single-day approved case window**, not the statute's commencement or repeal dates. Unknown statutory dates remain null. Historical/future use fails closed. Library membership never bypasses a fresh per-case applicability check, and evaluation references must not be injected into the retrieved ranking.

The initial scoped integration checks passed for eight admitted article snapshots. See `ADMISSION_INTEGRATION_20260917.md` for that historical checkpoint; execution subsequently progressed as described below. No repeated task/source approval is required for these same private frozen records; changes in task content, legal source version or scope require a new record.

## Data boundary

Public repository: model code, synthetic engineering fixtures, pending synthetic tasks, public source catalogue and an aggregate engineering report only.
Private E-drive locations: keys, raw/API logs, sidecars, human labels, expert data, paper materials and review records. `.local_runs/` is ignored. P1 stage approval does not retroactively fill source/version dates or approve new P3 references.

## Controlled execution follow-up

`controlled_execution.py` now enforces prescribed source/article availability
before ranking, reads both P1 and P3 immutable snapshots, and maps admitted
articles to the production evidence schema through a strict whitelist. The
source sidecar is rechecked for each case; reviewer identities, source-to-task
reference mappings and expected conclusions never enter the LLM payload.
Literal private/local URLs fail before DNS. Supplementary materials cannot be
promoted to independent law even by a mistakenly permissive sidecar.

Eight injected fault cases are executed separately with eligible positive
controls, zero actual HTTP requests and no legal-accuracy claim. Page-instruction
quarantine is not a demonstration of general LLM prompt-injection resistance.
`prepare_execution.py` v2 retains the approved facts while exposing the task
stage explicitly; historical v1 private artifacts are not overwritten. This
transformation does not constitute new human adjudication.

`run_controlled_reasoning.py` implements a shared local preliminary generation,
then at most one external recheck after successful preliminary insufficient
information. It can compare the historical fixed-access manifest, a new
source-matched access-only control, and bounded article discovery. These are
implemented-system comparisons, **not evidence that discovery beats a strong
alternative ranker**. The historical URL-only manifest is explicitly weak; no
article targets are fabricated to make it look operational.

Natural-corpus and predeclared artificial article-gap conditions use separate
run directories. Prescribed candidate-availability tests remain constrained in
both conditions. Actual removed chunks are logged; the original corpus is never
modified. Online calls are DeepSeek reasoning only; legal sources use frozen
snapshot replay, not new live verification. Failures remain in the denominator,
and automatic retries are disabled. All arms use identical decision parameters
and share the same local generation, so arm observations are paired rather than
independent samples. References are only for a separate offline evaluator.

The runtime requires an explicit authorization switch, a separate preflight
manifest, scoped approved source reviews and original snapshot roots. These
private materials and live API outputs must never be committed to this repo.

## Completed execution and metadata contract

The private corrected runs each completed 22 legal tasks, separately for natural
corpus and controlled-gap conditions. Eight fault probes are a separate software
test stratum, not legal cases. The first integration-diagnostic run is retained;
it is not silently replaced with the corrected runs. A fact-only v3 preparation
retains explicit task stage and the registered project-type code. Reference
labels remain offline and are not put into reasoning requests.

The optional `external_scope_bridge` is disabled by default. In this controlled
runner only, an admitted external article can use its exact case-day approval
window after fresh identity/context/source/hash checks. That window is not a
statutory commencement date. Required issuer, title, version, retrieval metadata
and source locators are retained. This does not weaken the production default.

`analyse_p3_controlled.py` and `render_p3_controlled.py` under
`experiments/scope_boundary_v1` validate the two conditions and report raw versus
gated outcomes, paired changes, request usage and conditional external ranking.
A correct outcome label is not proof of a correct legal basis. Alternative
citations and procurement-regime applicability remain separately reviewable.
Conditional external Recall/MRR must not be presented as full-system retrieval
metrics or pooled with the legacy 60-query/REAL45 sets.

`result_contract.py` derives delivery status from the actual final response and
`p3_one_shot_audit`, not inherited preliminary-run flags. It distinguishes an
external reasoning request being dispatched from completing successfully. For
historical runs, its CLI writes a new hash-linked metadata-only projection,
without rewriting answers, evidence or source files and without model calls.
Future controlled runs apply the same contract before saving results. This is a
reporting-integrity fix, not a reasoning accuracy improvement.
