# Full 60-item external-first reasoning protocol

## Purpose

The full 60-item online evaluation must not generate a final LLM review before
all external work triggered for that issue has completed. This protocol applies
to both external discovery and external verification.

## Required order

1. Run strict local Level 1 → Level 2 → Level 3 → Level 4 retrieval.
2. Derive issue-bound external discovery and verification triggers.
3. Execute external article-level retrieval over the configured source scope.
4. Record the executed scope, source URLs, issuer, version/effective status,
   retrieval time, article locator, verbatim legal quote and content hash.
5. Mark a requested mode complete only when its configured scope is covered by
   provider execution or a bound human-attested manual search record.
6. Apply jurisdiction, project-type, temporal and evidence-admission checks.
7. Call `deepseek-v4-flash` for final reasoning only after the pre-final gate
   returns `ready_for_final_llm=true`.
8. Apply the deterministic post-LLM schema/abstention gate and generate the
   Markdown and Excel review outputs.

## Fail-closed behavior

The following states must not call the final LLM or create a human-deliverable
review row:

- `manifest_lookup` without article-level search completion;
- `pending`, `pending_provider` or `pending_human_scope_attestation`;
- network, provider or normalization failure;
- incomplete configured-source coverage;
- a claimed manual search without `human_attested=true` and a non-empty bound
  `scope_attestation_id`.

The runner stores such a case only under `.pending_external/` with
`run_status=waiting_for_external_retrieval`. If any issue remains pending, it
writes only `manifest.in_progress.json`, does not write the final batch
`manifest.json`, and exits non-zero.

## Current provider limitation

`manifest_http` is a finite allowlisted page fetcher. It records transport and
can match an explicitly configured article target, but it deliberately cannot
attest exhaustive search completion. It is therefore suitable for smoke and
diagnostic work, not by itself for the final 60-item external-first run.

Before the full run, configure a provider or reviewed external-search registry
that can produce article-level candidates and a defensible scope-completion
record. External candidates remain non-independent until human source and
applicability confirmation; completing retrieval does not automatically admit
them as legal evidence.

## Acceptance checks

The full batch is ready for human delivery only when:

- every item has `run_status=completed`;
- every triggered external mode has `external_search_completed=true`;
- `pending_external_count=0`;
- every final response passes response-channel diagnostics and strict JSON
  parsing;
- every finding passes the post-LLM gate;
- the batch manifest, Markdown table and Excel workbook are generated only from
  completed cases.
