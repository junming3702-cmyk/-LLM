# Isolated official-source candidate preparation

This is source preparation, not a production corpus release and not a completed
C0/C1 effectiveness experiment. It does not modify the original corpus, prompts,
expert references or historical outputs. Source snapshots and private results
belong outside this public repository.

## Tools

- `acquire_sources.py`: exact public-government URLs from the catalogue; verified
  TLS, public destination checks, no redirects, request-size limit, bounded
  subprocess deadline, one request per selected source and no automatic retry.
  Failure status is retained. No credentials, contract or expert input is used.
- `build_candidate_index.py`: offline extraction of complete sequential articles
  or numbered items, explicit document/page/footer boundaries, title/version
  anchors, exact source spans, raw/text hashes and a separate lexical index.
- `validate_candidate_index.py`: independently reconstructs every candidate from
  its snapshot spans, checks index postings, document identities, attachment
  pages, candidate eligibility and the unchanged C0 hash.

Each CLI requires explicit paths; use `--help`. All outputs require new paths,
not overwrite flags. The acquisition CLI requires the ARS PDF preflight script
path when PDF sources are present. A zero process exit code is not a page-trust
decision: a PASS verdict, matching hash, positive equal page counts and absence
of repair warnings are required.

Run the offline synthetic tests with:

```text
python -m unittest discover -s phase2_public/experiments/corpus_extension_v1 -p "test_*.py" -v
```

Set temporary-output paths outside the repository if local policy requires it.
The tests perform no HTTP/LLM calls or reads of contracts/expert data.

## Deliberate eligibility boundary

All extracted rows have `corpus_partition=quarantine`,
`legal_evidence_eligibility=not_admitted_candidate`, `human_confirmed=false` and
`independent_legal_evidence=false`. A successful parser or an official domain
does not certify current legal validity, project applicability or human review.
Do not pass this index directly to the production retriever or rename it as an
admitted corpus. A later admission ledger must bind actual source/version/scope
decisions; no automatic human certification is provided here.

Keep the actual instrument type distinct from both acquisition channel and
four-level retrieval order. Central administrative normative notices and
judicial interpretations are not silently labelled Level 3 departmental
regulations or Level 4 local regulations. Their level remains unassigned here.
Normative notice items such as `二、` are not fabricated as `第二条`.

Provincial re-publication does not itself make a central instrument local. Nor
does a central attachment make the provincial covering instrument nationwide.
Selected physical pages must correspond to one explicitly bounded instrument.
Page numbers refer to the downloaded container PDF, not a guessed standalone
document. The complete snapshot remains available for inspection.

## Version and task boundaries

- A webpage publication date is not a legal effective date. Conflicting webpage
  metadata is retained as a verification issue; body clauses are not silently
  overwritten by page fields.
- Historical company qualification requirements require cross-checks against
  later cancellation policies; company licences and individual professional
  registration are different requirements.
- A judicial interpretation's temporal/court-acceptance scope cannot be reduced
  to the project's tender date. A court remedy is not automatically a tender
  rejection rule.
- Adding government-procurement law does not prove that a particular project is
  governed by that procurement regime.
- National scope is not universal applicability. Scope-companion candidate IDs
  preserve links to definitions, exceptions and scope articles without certifying
  those conditions for a real project.

The catalogue/specs are public acquisition and extraction configuration, not an
expert-approved manifest of the complete current law. A targeted official check
that finds no repeal is not proof that no later change exists.

## Effect attribution

Keep geography/task policy comparisons fixed at C0. For a later corpus-only
comparison, freeze one explicit method configuration and vary C0 versus a
separately admitted C1. Hold external recheck, source-role guards, model, prompt,
ranking parameters and failure policy constant. Candidate extraction success,
unit counts and locator roundtrips are engineering outcomes, not Recall@5, MRR,
legal accuracy or a new expert validation. No benchmark labels are read by any
of these tools.
