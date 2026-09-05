# Full-60 one-shot external recheck protocol v1

## Purpose

This protocol governs the 60-item synthetic-gold online reasoning run. It
keeps the strict local hierarchy as the primary experiment and uses external
retrieval only as a single recheck of a locally derived information-insufficient
result.

## Per-issue execution order

1. Run strict local retrieval in Level 1 → Level 2 → Level 3 → Level 4 order.
2. Run the first `deepseek-v4-flash` reasoning pass using local evidence only.
3. Apply the deterministic post-LLM gate. This produces a preliminary result
   that is retained for audit but is not yet delivered.
4. If the preliminary canonical conclusion is not
   `insufficient_information_needs_human_confirm`, do not call external
   retrieval and deliver the gated local result.
5. If the preliminary conclusion is
   `insufficient_information_needs_human_confirm`, call the configured external
   discovery provider exactly once. Do not dispatch a second verification call
   in the same recheck.
6. If the recheck adds independently admissible, source-verified article
   evidence, run one revised LLM reasoning pass and apply the deterministic
   gate again.
7. If the recheck adds no independently admissible evidence, do not ask the LLM
   to reinterpret absent or unverified material. Reapply the deterministic gate
   to the gated preliminary response with the external audit attached and keep
   `insufficient_information_needs_human_confirm` as the final conclusion.

## Non-upgrading external outcomes

The following outcomes cannot upgrade the preliminary conclusion:

- manifest-page lookup without admitted article evidence;
- network or provider failure;
- `pending` or partial-scope retrieval;
- completed no-hit from this limited recheck;
- candidates awaiting human source confirmation;
- CECN-only contextual or supplementary material.

These outcomes remain visible in `external_retrieval_audit`. They do not prove
that no applicable law exists and therefore do not justify
`no_applicable_legal_basis_found_needs_human_confirm` in this experiment.

## Audit requirements

Each result records:

- preliminary LLM response and preliminary gated response;
- whether the one-shot recheck was eligible and attempted;
- provider, call count, HTTP status, search status, scope and candidates;
- whether independently admissible external evidence was added;
- whether a revised reasoning pass was run;
- preliminary and final canonical conclusion types.

All delivered outcomes retain
`overall_review_status=requires_human_second_review` and do not make an
automatic award, rejection, invalid-bid or final legal decision.
