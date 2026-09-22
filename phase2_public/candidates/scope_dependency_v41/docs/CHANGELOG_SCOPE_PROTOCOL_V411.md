# v4.1.1 — task-mode / response-target single-source repair

Status: isolated candidate; no production promotion, no provider calls.

## Scope of the repair

- `scope_dependency_v41_schema.py` now owns the four mode/target pairs,
  corresponding input stages and permission to use text-only exclusions.
- `review_target` enum, generated mapping table and synthetic examples derive
  from that schema. The prompt explicitly requires copying the caller-provided
  `review_task_contract_v41.expected_review_target`.
- The trusted caller creates that value before inference and binds it into the
  input digest. The gate validates it against schema; it never trusts a modified
  runtime value or repairs the model's response to match it.
- v4.1.x scope validation no longer imports legacy v4 mode definitions or its
  validator. All previous scope, source, geography and relation safeguards stay.
- Valid-enum but wrong-mode responses remain technical/schema blocks, not valid
  legal U, N or R. Empty, malformed or truncated output cannot be reconstructed.
- Review table/Excel display recognizes the current protocol and frozen v4.1
  through a shared, explicit version list, not duplicated exact-version checks.
  Display compatibility does not upgrade historical contracts or legal labels.

## Frozen history and use

The code was developed in a separate worktree from the frozen v4.1 run. This
revision does not replay, relabel or overwrite project outputs, expert scores or
reference answers. Prior contracts fail closed; construct a fresh contract for
a separately approved new invocation rather than silently upgrading old runs.
`scope_dependency_v41` remains the entry flag; the contract version changes to
`scope-dependency-v4.1.1-candidate`.

Synthetic tests cover four valid pairs, twelve wrong pairs, generated prompt
consistency, stale/tampered runtime targets, unknown modes, no normalization
substitution, separation from legacy definitions, unchanged factual-task
safeguards and relation holds even after the target matches. These are software
guards, not independent legal-performance observations. Online verification and
output-budget changes require separately frozen/approved experiments.
