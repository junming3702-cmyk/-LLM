"""Candidate-only prompt extension. Production prompt remains unmodified."""
from task_gate_v2_prompt import build_prompt as v2_prompt

VERSION='scope-citation-v3-candidate'
ADDENDUM='''

## Scope/citation v3 candidate — exact fragments, never approximate citations
Read negation in the supplied review question. An explicit exclusion such as
"不核验…真实性" is not a positive instruction to authenticate that material.
Keep genuine positive factual tasks and missing decisive rules/facts blocking.
Machine-derived scope is not human approval. Do not rewrite the review question.

Each completed check must copy exact supplied text and one exact declared
locator. For a single-source quote omit document_fragments entirely.
Never rephrase a date, normalize a number, remove a negation, join
pages silently, or use ellipses as if they were verbatim source text.
For discontiguous evidence use document_fragments (2–8 entries), each exactly:
{"document_quote":"verbatim substring","document_locator":"one exact locator"}.
For that check document_quote must equal the fragment quotes joined with a
single newline, and document_locator must equal their locators joined with
semicolons in the same order. These fields are a display join, not a claim of
one contiguous source quote. Prefer separate checks for independent claims.
If a quote is ambiguous or cannot be bound, report the processing limitation;
do not invent a matching quote. Fragment binding alone does not prove a legal
conclusion. Applicable independent law, adequate facts and human review remain
required. Preserve U for genuine decisive gaps; never force N for a better score.
'''

def build_prompt(base):
    return v2_prompt(base)+ADDENDUM
