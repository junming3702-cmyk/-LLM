# Paired protocol regression utilities

These opt-in utilities compare the frozen v4.1.1 scope-dependency candidate
with the three-layer handoff candidate. They do not promote either candidate,
modify the corpus, or load expert/reference workbooks. Prepared requests and all
real outputs must stay outside the repository.

## Safety and design boundaries

- Verify the actual serialized common evidence packet is identical between
  arms, not just the experimenter's claimed hash.
- Reject nested historical model predictions and reference-label fields.
- Verify task claims, exclusions, source spans and law-admission flags match
  each arm's protocol view of the common packet.
- Both arms use the same model parameters. Different prompt/schema and input
  representation overhead remain part of the protocol-bundle comparison.
- Strictly deserialize final `content` before either gate. Do not promote
  reasoning fragments, normalize substantive judgments, or invent missing keys.
- Preserve raw responses and raw-versus-mechanically-normalized gate states.
- At most one call per prepared case. No automatic retry, no implicit resume.
- Keep failed and interrupted runs. An asymmetric-input run is not a formal
  paired comparison, regardless of whether its results look favorable.
- Protocol validity and review readiness are not legal accuracy or human
  handoff effectiveness. Development-exposed cases are not independent holdouts.

The runner requires a prepared lock, per-arm requests, and separately authorized
API access. The credential file remains outside git. The expected request
format is documented directly in `validate_pair`; all evidence-bearing input
is in `common_evidence_packet`, with arm-specific binding/registry material in
`protocol_context`.

```text
python -m unittest discover -p "test_*.py"
python runner.py --out <private-frozen-run> --env-file <private-env-file> --workers 3
```

`assessment.py` supports an explicitly separate offline assessment of saved
responses, preserving their original scoring record. `summarize.py` produces
descriptive, all-attempt protocol and processing counters; it never computes
legal accuracy or expert agreement.

## Implementation record

The initial preparation adapter retained historical missing-fact predictions in
one arm's nested retrieval logs. That live batch was stopped and excluded from
formal comparison. The corrected runner enforces common-wire equality and
nested-field denial before any request. A second issue involved the legacy
gate's JSON-object input contract; strict final-channel deserialization now
occurs consistently before both gates.

12 local tests cover strict JSON parsing and input-parity safeguards. A new
online run is not implied by these offline checks. No real contract text, law
snapshots, expert data, response logs, identifying paths or credentials are
included in this public package.
