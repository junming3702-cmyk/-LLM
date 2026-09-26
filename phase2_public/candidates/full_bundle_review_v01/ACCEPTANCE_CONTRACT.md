# Construction tendering bundle review: acceptance contract (candidate v0.1)

This candidate is a **pre-review aid**, not a decision on bid validity, award, or legal compliance. It does not replace the frozen REAL45, QX or expert-study outputs.

## Unit of intake

One identified construction project. The caller declares every input file and its role in `bundle_manifest.json`: at least one issued tender document and at least one **final submitted bid** document. Evaluation records, award notices, working drafts and unrelated projects are excluded from the inference input. A declaration of “final” is a provenance statement to verify, not something inferred from a filename.

The original PDF/DOCX is authoritative. Parsed Markdown and block locators are intermediate evidence. PDF pages without reliable text/coordinates stay unreviewed; a DOCX paragraph locator is **not** a physical page number. MinerU and PaddleOCR remain conditional enhancement routes governed by their existing quality gates. A zero candidate count never means a clean file.

## Two tasks, three checks

| Task | Check | Required comparison |
|---|---|---|
| Tender drafting review | `tender_clause_legality` | Tender wording ↔ applicable legal provision, with legal applicability and version uncertainty disclosed. |
| Final-bid review | `bid_responsiveness` | Issued tender requirement ↔ identified final-bid wording; an unmatched candidate is a search gap, not proof of omission or disqualification. |
| Final-bid review | `bid_standalone_legality` | Bid wording ↔ applicable legal provision; performance/authenticity outside a text-only scope is flagged separately. |

Every candidate retains a task ID, raw quote, document hash, document/block locator, optional page, paired requirement/response, retrieval query, matching status, and reviewed/unreviewed coverage. The legal RAG supplies Level 1→4 evidence under the existing gate; a tender requirement is **not** itself an independent legal source. A final finding must show the exact tender/bid text and their difference, the legal/tender basis, missing evidence, and a concrete action for human review. All deliverables carry `requires_human_second_review`. No automatic rejection or award decision is permitted.

The three-layer claim-completion/handoff protocol is a **supplement** to the substantive risk result. It may report completed checks, decisive gaps, out-of-scope items and handoff state. Its `ready_for_*` statuses do not mean legal correctness; protocol failures do not transform a risk into N/U. The bridge must preserve the raw legacy response and the raw protocol response.

## Acceptance and evidence boundaries

Stage 1 accepts a strict bundle manifest, preserves originals, records each document's extraction quality, unreviewed physical pages, unstable DOCX page locators and an explicit coverage denominator. Stage 2 adds candidate discovery, cross-document matching with ambiguity, and a runnable bridge to the existing strict-hierarchy retrieval/LLM/gate and Excel exporter. A synthetic, fixed annotation may estimate item-discovery and pairing coverage **for that development fixture only**. Automatic coverage counters are operational diagnostics, not independent recall.

No new-project end-to-end effectiveness, legal accuracy, workload/time saving, or cross-industry generalisation is claimed here. REAL45 remains developmental regression/failure analysis. Independent full-document testing requires a previously unseen complete construction project and a pre-output human item inventory; that is Stage 3 and is intentionally deferred.
