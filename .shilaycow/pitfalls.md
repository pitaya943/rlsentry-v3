# Pitfalls

Lessons from earlier work in this repository. Read before building.

## A "protected" rule that holds only for the attempts it happens to list

- What happened: in `v3-spec` T-01 the verdict rules said protected after a narrow set of
  attempts, and a verifier found, on a real PostgreSQL 16, a request outside that set that the
  visitor could send and that succeeded: column-only grants hidden behind a refused `select *`
  ([verdict 1](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211268769)); an
  update refused by `WITH CHECK` that another value passes (same verdict); an unfiltered update
  refused because one row fails `WITH CHECK` while a filtered update of another row succeeds
  ([verdict 2](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211365081)).
- How to avoid it: a protected verdict is a claim about every request the threat model lets the
  visitor send, not about the requests rlsentry chose. For each protected rule, list the request
  shapes the visitor can vary (columns named, values sent, filter or none, one row or many) and say
  for each why rlsentry's attempts cover it or why the database's answer to one shape implies the
  answer to the others; where neither holds, rlsentry must try that shape too or stop.
- Count: 2 (one task, two verdicts)
- Sources: https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211268769, https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211365081
