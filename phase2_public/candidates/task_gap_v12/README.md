# v12 task-gap protocol candidate — not the production prompt

This candidate extends the existing v11 legal-reasoning prompt with the
schema-generated `task_gap_protocol_v1.prompt_addendum()`. It does **not**
replace `prompts/system_prompt_final.md` or alter the historical QX30/REAL45
results. The exact addendum and gate field names share the constants in
`src/task_gap_protocol_v1.py`.

## Change against the v11 candidate

| Boundary | v11 | v12 candidate |
|---|---|---|
| Legal U explanation | Free-text decisive-gap test | Finding-level `legal_u_basis` with eight required fields, bound to locked question and dependency |
| Missingness evidence | Model describes the gap | Caller builds `task_gap_audit` **before** model inference; source/input hashes bind each row |
| Unattested U | Could be delivered after old gate | Held as `unverified_decisive_gap`; the same test applies to U created by the gate |
| OCR/input failure | Prompt said not to call it legal U | Processing/task-route hold is enforced; neither U nor N is fabricated |
| Visibility/text-only task | Might pass through legal gate | Routes outside legal verdict; source-bound observations are assessed separately |
| Award result | Excluded from input | Remains excluded; it is not a per-issue N reference |

`legal_u_basis` is required **only** for legal U. Its fields are `claim_id`,
`question_verbatim`, `dependency_key`, `missing_material`, `material_status`,
`reason`, `counterfactual_impact`, and `next_check`. The model cannot mark its
own gap audit row `validated=true`; that value is supplied and hash-bound by
the caller. `task_gap_audit` is an input audit, not a gold answer. Current
automatic legal-gap attestation is deliberately narrow; other U claims must
be checked against additional source/package evidence, not automatically
relabelled N.

## Formative QX30 check

`experiments/qx30_task_gap_v12_controlled.py` reuses the exact historical
final-inference user texts and legal evidence. The offline arm replays the old
v11 raw response against the candidate gate without API calls. The online arm
adds this protocol to the v11 base prompt, with the same DeepSeek model,
temperature, reasoning effort, and token limit. It is a **multi-component**
intervention (prompt + input gap ledger + gate + task routing), not a
single-factor gain estimate. QX30 participated in development and is not an
independent holdout. Source-bound QX tasks are replayed separately in the
private local-run directory because their validation anchors contain real
project excerpts and must not be published with the model code.

All private project inputs, model responses, outputs, and secrets stay in
ignored E-drive local-run directories; only code and this protocol note belong
in the public model repository.
