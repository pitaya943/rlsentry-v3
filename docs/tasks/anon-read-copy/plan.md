# anon-read-copy: plan

Five tickets, one after another: each builds on the package the one before left, and builders in
parallel could not see each other's choices in the shared modules. The shape is in
[design.md](design.md).

| Ticket | Serves | Depends on | Risk |
|---|---|---|---|
| [T-01](tickets/T-01.md) package, CLI, versions, the copy built from migrations and always destroyed, the safety boundary, the test suite | S-5 (all but seeding and the reads), S-7, S-10 (harness), S-1 *A migration that fails*, *plain folder*, live target, #23 inputs | none | high |
| [T-02](tickets/T-02.md) seeding, PostgREST, the two reads, the exposed verdict and every stop of a read, exit codes | S-1 (verdicts, attacking), S-2, S-4, S-5 (seeding, grants, two runs), S-6 | T-01 | high |
| [T-03](tickets/T-03.md) the text summary, the JSON report and its schema, escaping, stopped-run reports, reproducible reports | S-1 (reports), S-3 | T-02 | high (raised: its seeding change reaches the evidence) |
| [T-04](tickets/T-04.md) the lab: schemas, statements, `rlsentry lab`, a test of every schema; README; `try-rlsentry` skill | S-8 | T-03 | medium |
| [T-05](tickets/T-05.md) the spec moved to what was built (S-9), the one-definition check and `checks.md` sentence (S-11) | S-9, S-11 | T-04 | low |
| [T-06](tickets/T-06.md) an interrupted run exits 2, as the spec says (fix round 1 for the pull request into main) | S-5 *The copy is gone when a run ends*; verdicts Exit codes | T-05 | medium |

T-01 and T-02 hold the brief's two critical areas (the safety boundary; the exposed verdict and its
evidence): each is designed here before it is built and verified on its own before it lands. T-03
to T-05 are judged with the pull request into `main`.

Every ticket's check fails today: the repository holds no code, no `pyproject.toml` and no
`tests/`, so no command of any ticket can run.
