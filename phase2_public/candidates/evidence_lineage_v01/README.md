# Evidence lineage and task identification (opt-in Phase 2 candidate)

This candidate records **where** an evidence item stopped, rather than
calling every missing citation a retrieval failure. It also checks an already
locked review task *before* an LLM call. It does not change the frozen
three-layer protocol, Phase 1 index, historical results, legal conclusions or
expert answers. It is not production-enabled.

## The seven-link ledger

For each explicitly named diagnostic law target, `audit_run.py` reads a frozen
run and the corresponding immutable source snapshots, and records:

1. Original source: source ID and file hash from the catalog; a physically
   available file is marked verified **only** after a matching SHA-256 check.
2. Parse: an exact extracted record must have the same source ID, article and
   file hash and contain the indexed chunk text. This does not prove that an
   OCR page coordinate is correct.
3. Index: exact chunk ID in the supplied corpus snapshot. A run-manifest hash
   can prove that the snapshot is the one used in the historical run.
4. Retrieval: exact candidate ID and completed level/phase search, including
   a separate triage-selection state. Cascade-skipped/failed searches are not
   counted as unsuccessful retrieval.
5. Final input: the *actual saved final API user message*, not merely the
   mutable `runtime_input` copy. Quote and file-hash identity are checked.
6. Applicability/admission: inapplicable, unknown/invalid, supplementary-only
   and eligible upstream metadata remain distinct. No legal status is invented.
7. Output citation: raw and gated citation IDs are reported separately. A
   missing citation is not automatically an error; a law may simply not be
   needed for the bounded answer.

A source not in a complete supplied catalog, an article not indexed, an
indexed-but-unretrieved chunk, a retrieved-but-unselected chunk, a selected
chunk lost before the final request, a delivered but inapplicable law, and an
admitted law with a declared comparison gap are **different diagnostic
states**. The last is a model-declared gap unless independently reviewed;
metadata admission is not proof of legal correctness. In historical runs that
lack an original-document manifest or extracted block mapping, those fields
remain unknown. The tender-document excerpt has a separate trace and is not
pretended to be a verifiable original PDF page.

Targets supplied after a run may come from a human reference, but must never
be included in an LLM request. A source absent from the supplied catalog is
not asserted absent from the full legal universe. No blanket external-search
repair is attempted.

## Offline diagnostic

Use Python 3.10+ and a **new private output path outside the public repo**:

```text
python audit_run.py --result <frozen-result.json> --corpus <corpus_chunks.jsonl> \
  --catalog <index_catalog.json> --extracted-dir <law_extracted> \
  --source-root <law_sources> --run-manifest <frozen-run-manifest.json> \
  --target-id <exact-chunk-id> --output <new-private-trace.json>
```

The output is created exclusively (`x` mode); no historical file is edited.
The output contains IDs, hashes and locators, not law or contract text. If a
frozen manifest is absent or its corpus hash differs, the run/corpus identity
is unverified or conflicted, respectively. Do not claim a historical
retrieval miss from an unbound current corpus.

## Pre-inference guard

`task_scope.audit_task` examines the locked question, explicit exclusions and
required claim dependencies. A phrase such as “不核验实际业绩真实性” is a negative
scope cue, not a positive authenticity task. It cannot silently remove a
required dependency; conflicts, quotations, double negations and ambiguous
conditions go to scope review. This is a finite conservative pattern guard,
not a general Chinese-language parser.

`preflight.audit_preflight` compares issue-specific selected chunks with the
actual JSON user message and blocks a missing, altered or extra law, task
change, duplicate ID or unresolved task-scope contradiction. It never adds a
law, rewrites a question or manufactures a legal conclusion.

`preflight.capture_selected_from_retrieval` must run immediately after a
completed issue-specific retrieval/triage event and **before** final packet
construction. It retains a read-only copy/hash of that event, all selected
IDs, exact quotes, original file hashes and separate discovery-only roles.
The guard re-derives selection from that event and checks the locked task and
final request. A selection manifest invented from the final context is not a
valid upstream proof. The candidate retriever now propagates `source_id`,
`file_hash` and extraction fields into its candidate records for this reason.

`guarded_runtime.preflight_directory` verifies every frozen request hash in a
prepared three-layer directory. Without a separate upstream-selection
manifest it reports `internal_binding_only`, **not** end-to-end ready. Its CLI
is preflight-only and never calls the provider. The `run_guarded` Python
function requires a per-case upstream selection manifest, blocks if any case
fails, and only then delegates to the unchanged three-layer client. Do not
use it for an experimental comparison without a new protocol/input version
and appropriate data authorisation. Historical request directories do not
gain an upstream selection record retroactively.

## Validation and interpretation

`python -m unittest -v test_lineage.py` runs fictional, offline guards for the
seven links, distinct break categories, packet identity, negated scope cues,
mandatory dependencies and pre-inference blocking. These are software tests,
not an independent legal benchmark, an accuracy improvement or proof of
professional labour savings. Frozen Stage B, REAL45, QX and paper metrics are
unchanged. Private real-case diagnostics are not part of the public repo.
