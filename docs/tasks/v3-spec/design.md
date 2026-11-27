# v3-spec: design decisions

## D-1: what "protected" promises (owner, #7)

Decided by the owner in https://github.com/pitaya943/rlsentry-v3/issues/7#issuecomment-7211637933,
option 1 of that issue: a bounded promise, with refusal outside the bound.

- "Protected" means: every request shape on a published list was tried and refused. The list is
  the verdicts area's Request shapes table (columns, values, filter or none, rows, upsert, and
  whatever else that table names).
- Before attacking, rlsentry reads the table's policies (and what they call, as far as it can see).
  When a policy depends on an input outside that list (request headers, cookies,
  `current_setting('request.*')`, or a function it cannot see into), rlsentry gives no verdict for
  that table and operation: the run stops with exit 2 and names the input.
- `index.md` and `verdicts.md` state this one bounded meaning; no other statement of what
  protected means remains.
- Inside the bound a false protected must not happen; the report and the spec say where the bound
  is.
