# Contract sample annotation protocol｜Phase 2 public release

## Scope

The annotation unit is one review finding inside a full or partial project contract-document bundle. The bundle may contain tender/contract clauses, schedules, appendices, specifications, payment terms, qualification requirements, amendments and cross-referenced documents. No private contract file is included by this protocol; the queue remains empty until an anonymized, synthetic or public sample is deliberately supplied.

The purpose is to create a small gold set for evaluating whether `LLM + RAG` can generate a supported and traceable compliance finding. It is not to train an automated legal decision-maker.

The expanded pool is stored as `contract_review_gold_pool_v1.jsonl`. It contains 3 previously accepted synthetic rows and 57 new synthetic candidates. The new candidates carry `human_review_status=pending` and `annotation_state=candidate_pending_human_confirmation`; they must not be counted as final gold until a human reviewer confirms or revises them.

## Annotation sequence

1. Assign `sample_id`, `project_id`, `document_id` and a stable document location. Use page, paragraph, clause, table or section identifiers available in the source. If a location cannot be established, label the finding `out_of_scope_or_unverifiable` rather than inventing one.
2. Quote the minimum document excerpt needed to understand the issue. Preserve the original wording and do not silently normalize legal terms.
3. State the risk as a review finding. Use conditional wording such as “may be inconsistent with” or “evidence is insufficient to verify”, not “the bid must be rejected”.
4. Retrieve candidate legal chunks from `rag_index/corpus_chunks.jsonl`. Record the exact `chunk_id` and displayed `article`/`source_locator`. A source from `supplement`, `warning` or `verification` partitions must remain visibly marked.
5. Set `evidence_boundary` according to the strongest support actually present. If the legal source is only a supplementary or verification-pending document, do not upgrade it to `supported_by_primary_local_source`.
6. Record a recommended human action, such as “confirm applicable version and issuing authority”, “check the referenced appendix”, “ask procurement counsel to review”, or “no action beyond recordkeeping”. Do not encode a bid/no-bid or award outcome.
7. Set `human_review_status` only after a human reviewer has accepted, revised, rejected or declared the finding insufficient. `pending` is the default for an unreviewed model proposal.

## Label boundaries

- `potential_non_compliance`: the clause appears inconsistent with a cited rule, subject to version and applicability checks.
- `missing_or_insufficient_evidence`: the contract bundle lacks an exhibit, approval, qualification record or other evidence needed to verify a requirement.
- `internal_inconsistency`: two documents, clauses, dates, amounts or definitions in the same bundle conflict.
- `ambiguity_or_unclear_obligation`: the wording does not make the party, action, threshold, timing or evidence requirement sufficiently clear.
- `temporal_or_version_uncertainty`: the result depends on a date, amendment or effective-status question not resolved by the current corpus.
- `cross_document_link_missing_or_inconsistent`: a clause refers to another file or appendix that is missing, mismatched or not traceable.
- `out_of_scope_or_unverifiable`: the issue requires facts or specialist legal judgment not represented in the current text-only MVP.
- `no_issue_identified`: a human reviewer found no supported issue for the inspected unit; this does not mean the whole project is compliant.

## Review protocol

For a small reproducible gold set, annotate independently first, then adjudicate disagreements. The adjudicator must preserve both the original finding and the final corrected finding in the audit trail. At minimum, compare document-location accuracy, legal-chunk citation accuracy, risk-category agreement, evidence-boundary agreement and whether the statement stays within the “assist human review” boundary.

## Privacy and provenance

Use public regulatory text plus anonymized, synthetic or small public-domain contract examples. Record only the provenance and hash of each sample. Do not place personal identifiers, confidential tender prices or unredacted company information in the Phase 2 workspace.
