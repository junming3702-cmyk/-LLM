# Scope/dependency v4 — candidate, offline only

## Implemented

- Explicit caller-supplied scope specification with exact input/question binding.
- Fixed modes: clause design, text-response comparison, actual submission and
  actual conduct. Positive factual tasks cannot use text-only exclusions.
- Required subclaims and dependency keys; a gap must name the affected subclaim.
  Undeclared dependencies trigger a scope-contract failure, not a successful
  legal abstention and not automatic clearance.
- Excluded submission-package completeness, authenticity and performance items
  remain visible. Exclusion requires an explicit input lock, false blocking flag,
  no affected current claim, compatible type and conservative text checks.
- Mixed amendments, interpretation priority and unreadability remain blocking.
  Unknown wording is not cleared. No general Chinese semantic parser is claimed.
- Text observations require exact source provenance but no law citation. They
  cannot count as legal-subclaim coverage. Legal comparisons require admissible
  supplied law and precise source binding; every required claim needs coverage.
- Model U is not automatically converted to N. Legal applicability safeguards,
  source-role restrictions and human second review remain in force.
- Mocked final-reasoning integration plus paired synthetic guard tests.

## Deliberate limits

Structural validation cannot prove that a cited rule entails a conclusion, that
an LLM's dependency assignment is semantically correct, or that a document set
is complete. Known law/fact gaps are not automatically waived as unused legal
branches. Conditional-rule deactivation needs evidence and a separately reviewed
branch design; it is not implemented by this candidate.

The required-claim specification is trusted application configuration; hashes
detect changes but do not authenticate an operator. A badly authored scope lock
can still encode a wrong task. Human review and paired negative controls are
needed before any broader use.

The source, runtime admission and all source-role safeguards are unchanged.
No retrieval expansion, law corpus update, OCR rerun, parameter change, new
provider call, reference-label edit, or expert score update occurs here.

## Validation interpretation

Counts in `OFFLINE_VALIDATION_V4.json` are software test methods/function groups,
not cases, projects, expert ratings or accuracy samples. Earlier attempt logs
are retained locally. Synthetic cases test policy invariants; live prompt
behavior still needs a separate approval-gated evaluation.

## Future paired semantic probes (not executed)

1. Text response vs actual submission with the same missing submission package.
2. Explicitly inactive template requirement vs active project-specific threshold.
3. Merely unknown full amendment history vs a supplied clause-changing amendment.
4. Conditional rule not used vs the same conditional rule essential to a claim.
5. Exact factual observation plus applicable law vs facts alone.
6. Missing comparison value vs a known, source-bound value satisfying the rule.
7. Out-of-scope signature authentication vs an explicit signature-validity task.
8. Correct province/time applicability vs a conflicting or unknown jurisdiction.

Freeze expected dependency behavior before inference. Evaluate harmful release,
unnecessary abstention, grounded observation retention and dependency alignment
separately. Do not set improvement in N/U agreement as a release criterion.
