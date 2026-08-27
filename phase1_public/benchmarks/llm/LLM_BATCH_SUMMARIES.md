# LLM reasoning batch summaries

These summaries report behaviour of the local Phase 1 regression batches.
Raw runtime payloads and real-project outputs are intentionally excluded from
the public release.

| Batch | Prompt snapshot | Model | Valid JSON | Gate outcome | Main conclusion distribution |
|---|---|---|---:|---:|---|
| v1 | pre-v5 | deepseek-chat | 60/60 | 60 corrected | 60 insufficient_information |
| v2 | v5 applicability | deepseek-chat | 60/60 after one retry | all corrected | 56 requires_human_legal_review; 4 insufficient_information |
| v3 | v8 substantive recommendation | deepseek-chat | 58/60 | 55 corrected; 5 blocked | 41 requires_human_legal_review; 6 no_supported_issue_found; 8 insufficient_information |
| v4 | v9 final | deepseek-chat | 60/60 | all corrected | 39 requires_human_legal_review; 8 no_supported_issue_found; 13 insufficient_information |
| v5 | v9 final | deepseek-v4-flash | 57/60 | 49 corrected; 11 blocked | 36 requires_human_legal_review; 5 no_supported_issue_found; 8 insufficient_information |

The v4-to-v5 comparison is not a prompt-only A/B test because the model also
changed. The deterministic gate remains the final safety boundary.

## Response-channel diagnostic

Three previously invalid responses were re-tested with the rule:

final response = parseable reasoning_content when present; otherwise content.

All 3/3 became valid JSON. All had finish_reason=stop; no direct truncation
signal was observed. The evidence points to response-channel selection and JSON
normalisation rather than a proven max_tokens failure.
