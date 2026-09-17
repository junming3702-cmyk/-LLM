## N/U question-boundary candidate (nu-question-boundary-v1.1)
This opt-in section supersedes older blanket rules equating 'no concrete
fact-law difference' with U, or equating N with certified overall compliance.
Keep all source/provenance, local applicability and human review safeguards.

N means no supported issue found in the SUPPLIED review question, after an
adequate, evidence-grounded bounded check. It does not prove authenticity,
actual submission, future performance, universal legality or exhaustive search.
U means the supplied question cannot be answered because a DECISIVE fact,
applicable rule, comparison value, required document or readable evidence is
missing. Confirmed missing material in an examined package AND material not
provided in the current input both remain U, distinguished in explanation.
Do not promote document absence alone to R. A supported substantive numerical
or prohibitory conflict may remain R; do not disguise such a conflict as N.

First separate clause/statement wording, documentary completeness and actual
conduct. Authenticity or future execution is not automatically decisive for
wording pre-review. If a document merely states an obligation, do not demand
proof of its future execution merely to assess that wording. Conversely,
do not silently narrow a completeness, qualification or factual-verification
question into a wording-only question to obtain N. Legal consequences need
not be proved when the question concerns only textual compatibility.

For N, identify at least one completed check grounded in an actually supplied
applicable independent legal provision. A general/unrelated clause, no hit,
or only supplementary material is NOT enough. If the decisive law is absent,
keep U even if there is no detected conflict. Preserve conditions, exceptions,
negations, subject and stage. Different wording or a broader set is not by
itself a legal conflict or proof of legality. Do not invent a required document.

Earlier triage 'missing_elements' are candidate questions, not independently
confirmed decisive gaps. Reassess their relevance to the supplied question,
without changing the executed retrieval audit or denying a real evidence gap.

For EACH finding add decision_basis exactly as follows:
{
  "review_question": "copy project_context.review_question exactly",
  "review_target": "textual_pre_review | document_response | document_completeness | actual_conduct",
  "answerability": "sufficient | decisive_gap",
  "completed_checks": [
    {"check": "specific check completed", "document_quote": "exact supplied excerpt substring",
     "document_locator": "one exact supplied source locator",
     "legal_chunk_ids": ["actually cited independent chunk id"],
     "comparison": "explain document vs supplied rule for this check"}
  ],
  "gaps": [
    {"kind": "required_document_missing | input_evidence_missing | unreadable_evidence | comparison_value_missing | key_legal_source_missing | decisive_applicability_missing | authenticity_unverified | future_performance_unverified | other_outside_question",
     "detail": "specific unavailable item", "blocks_current_question": true,
     "reason": "why its absence prevents this question, or why it is outside the question"}
  ],
  "bounded_conclusion": "substantive conclusion limited to this question"
}
Use document_response for assessing what a supplied response document states;
it does not by itself establish actual submission or performance. Keep missing
required response material decisive, and never rename a completeness question.
completed_checks may be empty for U, but not for N. Every genuine U needs a
specific gap, not merely 'cannot form a conflict'. Generic follow-up requests
must not be labelled key-source/input gaps unless necessary for this question.
For authenticity/future-performance outside textual pre-review, set
blocks_current_question=false with a specific reason; never use false to hide
a decisive gap. Unknown actual facts remain decisive in actual-conduct tasks.
Use compliance_relation=explicitly_satisfied for a positive matched comparison,
or no_supported_conflict_within_scope for a sufficient bounded non-conflict
check. Missing/non-applicable liability elements do not themselves imply U.
Keep the canonical N/R/U conclusion codes, one finding per supplied issue,
the required fact-law comparison and concrete human follow-up. No final bid
rejection/award decision. All output remains requires_human_second_review.
