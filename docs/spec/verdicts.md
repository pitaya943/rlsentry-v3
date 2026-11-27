# Verdicts and evidence

This area decides, once for every later task and every report, when an operation on a table is
exposed, when it is protected, what each answer must rest on, and what happens when neither can be
shown.

## Scenarios

"Shown by" names the test that shows a scenario hold; every test builds a real copy and sends real
requests.

### Read a table that has row-level security off

Given a project with a table that has row-level security off,
when the user runs rlsentry on its migrations,
then the table's read is exposed, the basis says the visitor read every one of its rows, one fake
row is shown as evidence, and the command exits `1`.
Shown by: `tests/test_verdicts.py::test_a_table_with_row_level_security_off_is_exposed`, which
checks the count, that the evidence row holds the fake values the copy was seeded with, and the
exit code; the lab's `rls-left-off` shows the same.

### Read a table whose policy lets everyone read

Given a table with row-level security on and a read policy for `anon` that admits every row,
when the user runs rlsentry,
then its read is exposed, with a fake row as evidence, and the command exits `1`.
Shown by: `tests/test_verdicts.py::test_a_policy_that_lets_everyone_read_is_exposed`.

### Read a table whose policy lets some rows through

Given a table whose read policy admits only rows with a certain value, and seeded rows both with and
without it,
when the user runs rlsentry,
then its read is exposed, the basis says how many of the table's rows the visitor got, and the
evidence is one of the admitted rows.
Shown by: `tests/test_verdicts.py::test_a_policy_that_lets_some_rows_through_is_exposed_with_their_count`,
which checks the count against the rows seeded and that the evidence holds the admitted value.

### Read a table whose read grant covers only some columns

Given a table with row-level security off on which `anon` holds no table read grant but holds the
read privilege on some of its columns,
when the user runs rlsentry,
then its read is exposed, the basis names the columns the visitor read, the evidence holds only
those columns, and the command exits `1`.
Shown by: `tests/test_verdicts.py::test_a_read_grant_on_some_columns_is_exposed_on_those_columns_only`.

### An answer holding rows the table does not hold stops the run

Given a table whose read answer is shaped by code in the migrations to hold rows the table does not
hold,
when the user runs rlsentry,
then the read is neither exposed nor protected; the run stops, naming the table, and the command
exits `2`.
Shown by: `tests/test_verdicts.py::test_an_answer_holding_rows_the_table_does_not_hold_stops_the_run_at_once`,
whose answer is shaped by a cast the migrations define.

### A redirect is never followed

Given a table whose read policy makes the REST layer answer with a redirect to another address,
when the user runs rlsentry,
then no request goes to that address, the run stops, its message says the read was answered with a
redirect, and the command exits `2`.
Shown by: `tests/test_verdicts.py::test_a_redirect_is_never_followed_and_stops_the_run`, which points
the redirect at an address it watches and sees nothing arrive there.

### A run that finds something and then stops exits 2

Given a project with one table whose read is exposed and, attacked after it, another whose read
cannot be shown either way,
when the user runs rlsentry,
then the message names the exposed table and the table that stopped the run, and the command exits
`2`, not `1`.
Shown by: `tests/test_verdicts.py::test_reads_not_shown_exposed_get_no_verdict_and_the_run_stops_after_every_table`
and `tests/test_reports.py::test_a_stopped_run_still_reports_what_it_found_in_both_forms`.

## Rules

Every rule here was decided by `v3-spec`, except those that name `anon-read-copy`, which decided
them. A rule marked "from `anon-read-protected`" is agreed and not built yet: until that task, a
read is exposed or gets no verdict, never protected. The rules decide exposed for every operation
and protected for a read; when a write is protected is `anon-write`'s to decide (see
[Insert, update and delete](#insert-update-and-delete)).

### Two verdicts, and nothing between them

- Each table gets one verdict per operation: exposed or protected. Each comes with a basis, and an
  exposed one with evidence. Why: a person reading a report, and a script reading its exit code, both
  need an answer they can act on; a third answer like "unclear" would let a real hole hide behind it.
- When the run cannot show either verdict for a table and operation, that table and operation get
  no verdict and the run ends with exit `2`, its message naming the table, the operation and which
  signal was missing or contradicted; [When a run stops](#when-a-run-stops) says which stops end
  the run at once and which leave the remaining tables to be attacked first. Why: guessing "protected" breaks the one promise the tool makes, guessing
  "exposed" teaches the user to ignore it, and carrying on would produce a report that looks
  complete when it is not.
- Every verdict rests on the attempts rlsentry actually sent, never on reading the policies' SQL.
  Reading what a table's code depends on ([The bound of a protected verdict](#the-bound-of-a-protected-verdict))
  can stop a run, never give a verdict. Why: policies call functions, read other tables and depend
  on defaults; only running them says what they let through. What they read is plain in the catalog,
  and a mistake in reading it costs a stop, never a false answer.
- Nothing else writes to the copy while an attempt is judged, and each attempt is judged against the
  table as the direct view saw it just before. Why: a change from anywhere else could pass for the
  attempt's effect, or hide it.

### Signals that never count

None of these, alone or together, ever makes a verdict: the HTTP status; an empty body or `[]`; the
error code or message the REST layer relays; a row count in a header; anything after a redirect,
which is never followed. Why: code in the migrations can produce every one of them, as the
[threat model](threat-model.md#what-is-not-trusted) says. A redirect, or an answer that contradicts
the direct view, makes the run stop.

### The database's own account

Only two sources count as the database's own account of an attempt. Why: migration SQL can write
neither of them.

- **The server log of the attempt's statement**, matched to that one attempt so that no other
  statement's entry can stand in for it. For a refusal it holds the error code, the place in
  PostgreSQL's own source that raised it (its privilege check, or its row-level security check),
  and the table the refusal names, which must be the attempted table. Why: a function, trigger or
  policy can raise error `42501` with any message, but the place an error was raised is recorded by
  PostgreSQL itself; an error raised from SQL or PL/pgSQL is logged as raised there, never from the
  privilege or row-security check. And a policy that reads another table the visitor may not read
  makes PostgreSQL's own privilege check refuse the attempt about that other table, which says
  nothing about the attempted one.
- **What the copy's catalog and data say**, read through the direct view: whether the table has
  row-level security on, whether `anon` holds the grant for the operation, what rows the table holds
  before and after the attempt, and whether row-level security applies to the attempt's own
  statement. The last is asked by running that same statement in the copy as `anon` with row-level
  security switched off for the session, inside a transaction that is rolled back: PostgreSQL refuses
  it with its own error that the query would be affected by a row-level security policy on that table
  exactly when a policy stands between `anon` and the rows. Why: it is PostgreSQL's own answer to
  "did a policy decide this?", not rlsentry's reading of the policies.

### Grants

- A missing grant protects a read only when the catalog shows `anon` holds the read privilege on
  neither the table nor any of its columns. Why: PostgreSQL grants read on single columns as well as
  on the whole table; a visitor refused a whole-row read for lacking the table grant can still read
  the columns granted to it, so that refusal says nothing about them.
- When `anon` holds a privilege on some columns only, every attempt for that operation names exactly
  those columns (a read asks for them, an insert or update sends values only for them). Why: those
  columns are what the visitor can actually reach; an attempt naming others is refused by the grant
  before any policy is asked, so it shows nothing about the policies.

### Read

- **Exposed** when the attempt's answer holds at least one row, and every row in it matches, on the
  columns it holds, a row the direct view finds in the table. The evidence is one of those rows as
  the direct view holds it, limited to the columns the visitor read. The basis says how many of the
  table's rows the visitor got and, when its read grant covers only some columns, which ones. Why:
  rows the table really holds are the leak itself; a row the table does not hold could only come from
  code that shaped the answer, so it is no evidence, and the run stops instead.
- From `anon-read-protected`, a read is protected on the two rules below. Until then a read that
  neither request shows exposed gets no verdict, and the run's message says that protected verdicts
  come with `anon-read-protected` (`anon-read-copy`).
- **Protected by a missing grant** when the log shows the attempt refused with `42501` by
  PostgreSQL's privilege check on this table, and the catalog shows `anon` holds the read privilege
  on neither the table nor any of its columns. The basis names the missing grant.
- **Protected by row-level security** when the answer holds no row and no error, and all of these
  hold:
  1. the direct view found at least one row in the table at the moment of the attempt;
  2. the attempt carried no filter, range or limit of its own;
  3. the log shows the attempt's statement ran against this table and ended without error;
  4. PostgreSQL says row-level security applies to that statement (the check above).

  The basis says how many rows the policies kept out. Why: an empty answer from row-level security
  looks exactly like an empty table; together these show rows existed (1), nothing rlsentry asked for
  excluded them (2), the request really reached the table (3), and what stood in the way was a policy
  (4). Without all four, the run stops.
- A read verdict covers the rows the copy held. Why: a policy that admits only some values can only
  be seen letting rows through if such rows exist, so seeding fills each table with rows built from
  the values its policies and definitions name (a rule of [the throwaway copy](throwaway-copy.md)),
  and the basis of a protected read says it covers those rows.

### Insert, update and delete

- **Exposed** when the direct view finds, after the attempt, a row that was not in the table before
  it and that came from the attempt (insert); a row that was in the table changed to the values the
  attempt sent (update); or a row that was in the table gone (delete). The evidence is that row as
  stored, the row before and after, or the row removed. Why: only the table itself shows a write
  landed; a success status can come from a trigger that dropped the write.
- When an insert, an update or a delete is **protected** is not decided here: `anon-write`'s brief
  decides it, against running code, under [the bound](#the-bound-of-a-protected-verdict) below, and
  must include the cases listed under
  [Not yet built](#write-cases-anon-write-must-include-anon-write). Until then rlsentry attacks no
  write (`anon-read-copy` and `anon-read-protected` build reads only), so no write is ever reported protected. Why: four reviews of this area found, on a real
  PostgreSQL, a way past each write rule written ahead of code; the owner moved those rules to the
  task that can test them (`v3-spec`, issue #8).

### The bound of a protected verdict

Protected is a bounded promise: every request shape in the table below was tried, against the rows
the copy held, and each was refused or kept from every row. Inside that bound a false protected must
not happen; where a table's code could let through a request outside it, rlsentry gives no verdict.
A rule added later to this area adds its row to the table. The rows for insert, update and delete
name the shapes a protected write must answer for; how it answers for them is `anon-write`'s to
decide, and no write is protected before then. Why: the requests a visitor can send are
open-ended (any header, any value, at any time), so no finite set of attempts covers them all; a
promise with a published edge can be kept, and the reader can see where it ends. The owner chose
this meaning (`v3-spec`, decision D-1).

| Operation | The visitor varies | Why the attempts answer for it |
|---|---|---|
| all | the columns named | [Grants](#grants): attempts name exactly the columns `anon` may use, and a missing grant protects a read only when it holds none. |
| read | filter, range, order | Each can only narrow an answer, and the attempt carries none, so it holds every row any of them could return. |
| insert, update | the values sent | For `anon-write`'s rules to answer for. |
| insert | rows per request | For `anon-write`'s rules to answer for. |
| update, delete | filter or none | For `anon-write`'s rules to answer for. |
| update, delete | which rows | For `anon-write`'s rules to answer for. |
| update | an insert that turns into an update on a duplicate key | For `anon-write`'s rules to answer for. |
| all | the key: the anon key, or none | [Attacking a project](attacking.md#what-each-attempt-carries): every operation is attempted both ways, and is protected only when both attempts are. |
| all | the schema selected by `Accept-Profile` or `Content-Profile` | [Attacking a project](attacking.md#what-each-attempt-carries): a table is reached only under its own schema's name, which every attempt on it selects, so the search path is the visitor's too. |
| all | the REST layer's own settings and per-request code (`pgrst.*`, settings on a role) | [The throwaway copy](throwaway-copy.md#the-rest-layers-settings-come-from-rlsentry-alone): none a migration makes takes effect in the copy, and when the migrations make any the run stops. |
| all | anything else: request headers (`Prefer` included), cookies, method, path, the time it is sent | Not varied. The check below finds whether what decides access reads any of it; when it does, there is no verdict. |
| all | requests to other tables first, then this one | Not in the bound: each operation is judged alone, against the rows the copy held. |

- From `anon-read-protected`: **before attacking an operation on a table, rlsentry reads what
  decides access for it**, through
  the direct view, and follows every function, view and table that reaches, to the end:
  - for every operation, the policies that apply to `anon` on that table for that operation and for
    read (a write reaches only rows the read policies admit);
  - for insert, update and delete, also the table's checks, and its triggers and rules for that
    operation: in a trigger, the conditions on every path to raising an error or returning no row;
    in a rule, its condition and what it does instead;
  - a value a column default (identity included) or a trigger puts into a row, only when one of the
    above reads that column.

  What decides nothing is not read: a default or a trigger that only fills a column nothing above
  reads, such as `created_at` set by `now()` or `updated_at` set by a trigger. When rlsentry cannot
  tell which of a trigger's statements decide, it counts them all. Why: a value that only fills a
  column changes what the row holds, not whether the attempt is refused or which rows it reaches, so
  a visitor gains nothing by changing it; counting it would stop almost every project (Supabase's
  dashboard gives every new table `created_at default now()`), where the owner accepted stopping only
  on unusual tables (D-1, #7). A mistake in telling the two apart must cost a stop, never a false
  protected, so a doubt counts as deciding.

  The operation gets a verdict only when all that decides access depends on nothing but:
  - the row's own columns and the values the attempt sends; not its system columns such as `xmin`
    or `ctid`, which every write changes;
  - the role: `current_user`, `current_role` and `session_user`, the same for every request;
  - the claims, read with `current_setting` named by a literal `request.jwt.claims` or
    `request.jwt.claim.<name>`: the key is signed, the visitor cannot change it without a secret
    the [threat model](threat-model.md#what-the-attacker-holds) says they never hold, so the claims
    are either the anon key's or, with no key, the role alone, and the attempts are sent both ways
    ([Attacking a project](attacking.md#what-each-attempt-carries) says which claims may be read);
  - the rows of other tables as the copy holds them;
  - constants, and PostgreSQL's own functions and operators that PostgreSQL marks immutable, whose
    result depends on their arguments alone.

  Anything else makes the run stop before that operation is attacked, with exit `2`; the message
  names the table, the operation, the policy, check, trigger, rule or function, and what it reads.
  That covers any other request setting (`request.headers`, `request.cookies`, `request.method`,
  `request.path`), any other setting, the clock, randomness, a sequence, the client's address and
  PostgreSQL's other functions not marked immutable, and any function whose body rlsentry cannot
  follow: one written in a language other than SQL or PL/pgSQL, or one that builds SQL text and runs
  it. Why: the visitor can change each of these from one request to the next (a header in each
  request, the moment it is sent), and rlsentry varies none of them, so code that reads one may let
  through a request it never sent. A trigger that decides counts as much as a policy: an update
  policy that admits every row, behind a trigger that drops the change unless a header is sent,
  reaches no row for rlsentry's attempt and every row for the visitor who sends the header. How a
  function made by the migrations is marked is not trusted, since a migration can mark one immutable while it reads a
  header, so rlsentry follows its body; PostgreSQL's own functions carry the marks PostgreSQL gave
  them, which a migration, not being a superuser, cannot change.
- The basis of every protected verdict says that it covers the request shapes of this table, one
  operation at a time, against the rows the copy held. Why: the reader must see where the promise
  ends, in the report itself, not only here.

### When a run stops

Decided by `anon-read-copy`. A stop ends the run with exit `2`, after the report of what it found.

- These end the run at once, attacking no further table, because they mean the copy itself cannot be
  trusted: an answer holding a row the table does not hold; a redirect; a migration that fails; a
  PostgreSQL or PostgREST outside the accepted series
  ([the throwaway copy](throwaway-copy.md#what-the-copy-is-made-of)); a setting a migration puts on
  the REST layer or the roles it passes through
  ([the throwaway copy](throwaway-copy.md#the-rest-layers-settings-come-from-rlsentry-alone)).
- These leave that one table without a verdict while the remaining tables are still attacked, and
  the run ends with exit `2` once every table is tried: a read neither request shows exposed (an
  empty `200`, a `401` or `403`, a permission error, any other answer); a request that gets no answer
  within 30 seconds; a table in a schema whose use is not granted to `anon`; a table on which `anon`
  may read no column, for which no request is sent; a table with no columns.
- For each table without a verdict, every form of report gives, per request, the HTTP status, the
  PostgreSQL error code when there is one, and the reason ([reports](reports.md)).

Why: a stop of the first kind would make any later verdict rest on a copy that is not the project's;
one of the second kind says nothing about the next table, so the user still learns every exposed
read in one run.

### Exit codes

| Code | Means |
|---|---|
| `0` | The run finished and no operation on any table was exposed. |
| `1` | The run finished and at least one operation was exposed. |
| `2` | The run could not build the copy, could not attack it (a verdict could not be shown, a table's code reads something outside [the bound](#the-bound-of-a-protected-verdict), or the command was refused, `--target` included), or could not finish (interrupted, or the copy failed). The message says which. |

- `2` wins over `1`: a run that found something exposed and then stopped exits `2`, and its message
  still names what was exposed. Why: `1` tells a script the whole project was checked; a run that
  stopped part way has not checked it, and one code for every unfinished run keeps scripts simple.

## Not yet built

Each scenario below is built by the task it is marked with: the read scenarios by
`anon-read-protected`, in full; the write cases by `anon-write`, whose brief writes them in full.
"Shown by" says how a person or a test sees a scenario hold.

### Read a table whose policies admit no anonymous visitor (`anon-read-protected`)

Given a table with row-level security on and no read policy that admits `anon`,
when the user runs rlsentry,
then its read is protected, the basis says row-level security kept out every one of its seeded
rows, and if nothing else is exposed the command exits `0`.
Shown by: a test checks the verdict, the basis and the exit code; and a person reads in the copy's
log that the attempt's statement ran and that PostgreSQL refused the same statement with row-level
security switched off.

### Read a table the anonymous visitor holds no grant on (`anon-read-protected`)

Given a table on which `anon` holds the read privilege on neither the table nor any of its columns,
when the user runs rlsentry,
then its read is protected, and the basis names the missing grant.
Shown by: a test checks the verdict and that the basis names the grant.

### An empty answer the database does not explain stops the run (`anon-read-protected`)

Given a table the anonymous visitor gets no rows from while something other than a policy is the
reason (for example, the table holds no rows when it is read),
when the user runs rlsentry,
then no verdict is given for that read, the run stops, its message names the table and which fact
was missing, and the command exits `2`.
Shown by: a test on a schema built so that the table is empty when read checks that no verdict is
reported, the message, and the exit code.

### A refusal that only imitates the database stops the run (`anon-read-protected`)

Given a table whose read policy calls a function that raises a permission error with the same code
and message the database itself would use,
when the user runs rlsentry,
then the read is not marked protected; the run stops, naming the table and saying the refusal did
not come from the database's own checks, and the command exits `2`.
Shown by: a test on a lab schema with such a function checks that no protected verdict appears, the
message, and the exit code.

### A read policy that depends on a request header stops the run (`anon-read-protected`)

Given a table whose read policy admits a row only when the request carries a certain header value,
when the user runs rlsentry,
then the read is neither exposed nor protected; the run stops before attacking it, its message names
the table, the policy and the header setting it reads, and the command exits `2`.
Shown by: a test on a lab schema with such a policy checks that no verdict is reported, the message,
and the exit code; and a person sends the same read with that header to the copy and sees a row come
back, which is why protected would have been wrong.

### A column filled with the time does not stop the run (`anon-read-protected`)

Given a table with a column filled by default with the current time, and a read policy that reads
only the row's other columns,
when the user runs rlsentry,
then the read gets a verdict like any other table's, and the run does not stop on that default.
Shown by: a test on a lab schema with such a table (the shape Supabase's dashboard gives a new
table) checks that a read verdict is reported and the exit code is `0` or `1`, not `2`.

### Write cases `anon-write` must include (`anon-write`)

Each was found by a review of this area on a real PostgreSQL 16, as a write a visitor could make
while a rule written ahead of code said protected; `anon-write`'s brief writes each in full.

- A write refused for lacking the table grant, while `anon` holds the privilege on some columns and
  writes them ([review 1](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211268769)).
- An update refused by the policy's check on the new row, while another value passes it
  ([review 1](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211268769)).
- An update without a filter refused because of one row, while an update filtered to another row
  lands ([review 2](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211365081)).
- An update a trigger or rule silently drops unless the new row holds a value the visitor chooses
  ([review 4](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7211823557)).

## Changed by

- `v3-spec`: the first version of this area.
- `anon-read-copy`: the exposed read and the stops of a read; the scenarios it built moved up to
  Scenarios; the rest of the read scenarios marked `anon-read-protected`.
