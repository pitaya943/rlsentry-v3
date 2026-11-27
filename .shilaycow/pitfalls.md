# Pitfalls

Lessons from earlier work in this repository. Read before building.

## A "protected" rule that holds only for the attempts it happens to list

- What happened: in `v3-spec` T-01 the verdict rules said protected after a narrow set of
  attempts, and each verifier found, on a real PostgreSQL 16, a request outside that set that the
  visitor could send and that succeeded: column-only grants behind a refused `select *`; an update
  refused by `WITH CHECK` that another value passes; an unfiltered update refused by one row while a
  filtered one lands; a policy reading a request header; an update a trigger drops unless a chosen
  value is sent; PostgREST's `db-pre-request` hook rewriting the claims from a header (#6).
- How to avoid it: a protected verdict is a claim about every request shape on the published list
  (the bound, owner decision D-1 in #7), not only about the requests rlsentry happened to try. For
  each protected rule, list the request shapes the visitor can vary and say for each why rlsentry's
  attempts cover it or why the database's answer to one shape implies the answer to the others;
  where neither holds, rlsentry must try that shape too or stop. Documentation alone has failed to
  hold this class three times: guard it in code, with a test that replays every instance above.
- Count: 5
- Sources: https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211268769, https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211365081, https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211528147, https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211823557, https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7212110573, https://github.com/pitaya943/rlsentry-v3/issues/5#issuecomment-7212581941

## A fact stated in two places goes out of step when one changes

- What happened: `v3-spec` redefined "protected" in `verdicts.md` while `index.md` kept the old
  meaning (defect 5, #6); `checks.md` recorded a check's output that the next commit made wrong
  (#19's gap, #20).
- How to avoid it: give each definition or changing fact one owner and link to it from everywhere
  else; do not restate it, and do not paste output that depends on the repository's state. When a
  definition changes, grep `docs/` for every restatement in the same commit.
- Count: 2
- Sources: https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211528147, https://github.com/pitaya943/rlsentry-v3/pull/19#issuecomment-7212533244, https://github.com/pitaya943/rlsentry-v3/issues/5#issuecomment-7212581941

## A claim about PostgreSQL, PostgREST or Supabase written without running it

- What happened: `verdicts.md` said the `row_security = off` re-run is refused exactly when a
  policy stands between `anon` and the rows; on PostgreSQL 16 it is refused whenever RLS is on
  (#21). A scenario expected an exposed read in a second schema that the copy's own grants would
  refuse at the schema (#22).
- How to avoid it: before a rule or a scenario's Then rests on what the database or REST layer
  does, run it on the versions the copy uses and keep the probe as a test; a claim that could not
  be run is marked as such and goes to the owner, not into a rule.
- Count: 2
- Sources: https://github.com/pitaya943/rlsentry-v3/pull/19#issuecomment-7212533244, https://github.com/pitaya943/rlsentry-v3/issues/5#issuecomment-7212581941

## A guard added against a false protected stops the common case

- What happened: closing defect 4 made the pre-attack check follow every default, so
  `created_at default now()`, on nearly every Supabase table, would stop every run (defect 7, #6).
- How to avoid it: when adding a stop condition, run it on the most common real-project table
  shapes (the dashboard's default table, an `updated_at` trigger, an `auth.uid()` policy) and say
  in the trail that it does not stop them.
- Count: 1
- Sources: https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211823557, https://github.com/pitaya943/rlsentry-v3/issues/5#issuecomment-7212581941
