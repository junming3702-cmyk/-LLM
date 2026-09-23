# Scope routing and processing-hold presentation v4.1.2

Status: isolated candidate; no production promotion. Parent commit:
`eee002346818bfd06076b7f8ae7e71aeb0ffe009`.

## Two separately attributable changes

1. `material_aliases_v412`: finite recognition of 合同履行阶段、合同履行期间、
   后续实际履行、中标后实际履行 in the material detail only. Recognition records
   text offsets and source fields. It does not use a model's explanation to
   manufacture a material match. Existing explicit exclusions, task mode,
   dependency flags, claim bindings and mixed-material checks still apply.
   Present-tense promise omissions, dates, negations and applicability wording
   are guarded against being relabelled as merely future performance.
2. `processing_presentation_v412`: scope/protocol/evidence-binding holds get
   processing-specific wording in findings, summary, Markdown and Excel rows.
   Scope review is not displayed as an established decisive legal gap. A
   simultaneous real blocking gap remains separately visible. The previous
   generated presentation and all raw fields remain preserved. No legal
   decision or dependency classification is changed by this switch.

Both switches default to false and apply only through the explicit gate API.
The response wire schema and generated prompt are unchanged at v4.1.1.

## Reproduction

```text
python src/run_offline_regression_suite.py --package . --output <new-private-directory>
python experiments/scope_routing_v412/run_offline_replay.py --records <private-result-1.json> <private-result-2.json> --output <new-private-replay-directory>
```

The replay disables sockets and refuses output overwrite. R0 enables neither
option; R1 recognition only; R2 presentation only; R3 both. R0 must reproduce
the historical gate exactly. Presentation-only must preserve legal outcomes
and routing, and source hashes must remain unchanged.

## Validation and limitations

328 test methods/function groups passed, including 18 new groups and their
subcases. These are software checks, not independent legal cases. Tests cover
true blocking gaps, mixed dependencies, missing quote bindings, wrong task
targets, malformed output, explicit opt-in, original preservation and public
handoff views. The first environment attempt could not import openpyxl and
executed no tests; a second attempt used an already installed library location.
No new package installation or API call was needed.

The private replay demonstrates a narrowly repaired recognizer miss and an
unchanged blocking-gap control; it cannot establish general semantic accuracy.
The finite recognizer may still require human review for unfamiliar phrasing.
An unrelated context-only online diagnostic uses the frozen parent v4.1.1:
its observations must not be reported as effects of this candidate.
