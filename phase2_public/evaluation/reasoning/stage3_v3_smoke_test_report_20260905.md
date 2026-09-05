# Stage 3 v3 smoke test report

Date: 2026-09-05

Model: `deepseek-v4-flash`

Retrieval: strict Level 1 → Level 2 → Level 3 → Level 4 cascade with BM25+dense hybrid retrieval

External mode: manifest HTTP discovery/verification enabled

Decision boundary: all outputs remain `requires_human_second_review`

## Scope

This run validates the approved recommendation contract v3. A risk recommendation must present, in order:

1. the contract excerpt and locator;
2. the admitted law/article and legal requirement text;
3. the concrete difference between the contract fact and legal requirement;
4. the LLM's handling recommendation for human review.

The smoke set contains five previously reviewed synthetic issues. The 60-item online reasoning batch was not run in this stage.

The approved gate was also replayed offline against all 60 saved Stage 2 responses. This replay made no API calls and did not alter the frozen source files. It produced 59 corrected findings and one blocked record. The blocked record was `SYN-P1-G08-I55`: its saved Stage 2 payload did not contain `findings` as a list, so the gate correctly refused to reconstruct findings from the review table. The resulting distribution was 33 `requires_human_legal_review`, 18 `insufficient_information_needs_human_confirm`, and 8 `no_supported_issue_found_within_review_scope` findings, plus the one blocked record.

## Transport and JSON diagnostics

- Initial limit of 4096 completion tokens: one clean response and four `finish_reason=length` responses.
- Targeted retry at 8192 tokens: `I01`, `G05-I35`, and `G07-I49` became clean `content/strict_json` responses. `G06-I36` still ended with `length`, although the gate safely recovered a parseable reasoning payload.
- Targeted retry of `G06-I36` at 16384 tokens: clean `finish_reason=stop`, `content`, and `strict_json`.
- Final selected results: 5/5 `stop`; 5/5 `content`; 5/5 `strict_json`; 0 gate blocks.

The evidence supports a dynamic retry policy. A truncated response must remain blocked or provisional until a clean JSON response is obtained; the full batch does not need a uniform 16384-token ceiling.

## Final five-case review

| Issue | Final conclusion | Recommendation v3 result | External status | Assessment |
|---|---|---|---|---|
| `SYN-P1-001-I01` | `requires_human_legal_review` | Complete contract–law comparison: 3-day sale period versus the Level 2 minimum of 5 days; wording remains “可能不符合” because trusted runtime confirmation was not supplied. | `pending` | Pass |
| `SYN-P1-G03-I17` | `no_supported_issue_found_within_review_scope` | No over-alert. The 5-day sale period and cost-only fee are described as consistent with the retrieved requirement. | `pending` | Pass |
| `SYN-P1-G05-I35` | `insufficient_information_needs_human_confirm` | The excerpt proves that a qualification certificate was not provided, but it does not include an applicable tender requirement requiring submission at this stage. The model does not equate missing proof with lack of qualification. | `pending` | Pass under the current excerpt; rerun as potential risk when the tender requirement is supplied. |
| `SYN-P1-G06-I36` | `insufficient_information_needs_human_confirm` | Level 4 evidence remains non-applicable until the project location is confirmed. No violation allegation is generated. | `pending` | Pass |
| `SYN-P1-G07-I49` | `insufficient_information_needs_human_confirm` | The evidence boundary is correctly set to `not_supported_by_current_corpus`, but the conclusion is not upgraded to `no_applicable_legal_basis_found_needs_human_confirm`. | `pending` | Conditional: external access occurred, but article-level and full-scope completion were not established. |

## External retrieval finding

Each case attempted external verification through the configured manifest and recorded four HTTP attempts. These attempts demonstrate transport activity, not completed legal research. The external provider returned no normalized article-level candidate, the configured scope was not fully completed, and one source recorded an SSL failure. Accordingly:

- external evidence was not admitted as an independent legal basis;
- a manifest-page miss was not treated as proof that no applicable regulation exists;
- `G07-I49` remained in the information-insufficient state.

This behavior is conservative and consistent with the rule that external supported evidence must contain a specific, locatable legal provision. It also means that the 60-item online batch should not start until either:

1. article-level external retrieval and completion attestation are implemented; or
2. the reviewer explicitly approves `insufficient_information_needs_human_confirm` as the expected temporary outcome when external verification remains incomplete.

## Recommendation

The approved v3 recommendation structure passes the five-case smoke test. The remaining decision is an external-retrieval completion policy issue, not a prompt-format or JSON-gate failure. Keep the 60-item online reasoning batch paused until that boundary is approved.
