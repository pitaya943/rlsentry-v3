# Verdicts and evidence

This area decides, once for every later task and every report, when an operation on a table is
exposed, when it is protected, what each answer must rest on, and what happens when neither can be
shown.

## Scenarios

None hold yet: nothing is built. The read scenarios `anon-read` builds are under
[Not yet built](#not-yet-built).

## Rules

Every rule here was decided by `v3-spec`. The scenarios for insert, update and delete are written
by `anon-write`'s brief; the rules they follow are these.

### Two verdicts, and nothing between them

- Each table gets one verdict per operation: exposed or protected. Each comes with a basis, and an
  exposed one with evidence. Why: a person reading a report, and a script reading its exit code, both
  need an answer they can act on; a third answer like "unclear" would let a real hole hide behind it.
- When the run cannot show either verdict for a table and operation, the run stops: it attacks
  nothing further, exits `2`, and its message names the table, the operation and which signal was
  missing or contradicted. Why: guessing "protected" breaks the one promise the tool makes, guessing
  "exposed" teaches the user to ignore it, and carrying on would produce a report that looks
  complete when it is not.
- Every verdict rests on the attempt rlsentry actually sent, never on reading the policies' SQL. Why:
  policies call functions, read other tables and depend on defaults; only running them says what
  they do.
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
  statement's entry can stand in for it. For a refusal it holds the error code and the place in
  PostgreSQL's own source that raised it: its privilege check, or its row-level security check.
  Why: a function, trigger or policy can raise error `42501` with any message, but the place an
  error was raised is recorded by PostgreSQL itself; an error raised from SQL or PL/pgSQL is logged
  as raised there, never from the privilege or row-security check.
- **What the copy's catalog and data say**, read through the direct view: whether the table has
  row-level security on, whether `anon` holds the grant for the operation, what rows the table holds
  before and after the attempt, and whether row-level security applies to the attempt's own
  statement. The last is asked by running that same statement in the copy as `anon` with row-level
  security switched off for the session, inside a transaction that is rolled back: PostgreSQL refuses
  it with its own error that the query would be affected by a row-level security policy on that table
  exactly when a policy stands between `anon` and the rows. Why: it is PostgreSQL's own answer to
  "did a policy decide this?", not rlsentry's reading of the policies.

### Read

- **Exposed** when the attempt's answer holds at least one row, and every row in it is a row the
  direct view finds in the table. The evidence is one of those rows as the direct view holds it, and
  the basis says how many of the table's rows the visitor got. Why: rows the table really holds are
  the leak itself; a row the table does not hold could only come from code that shaped the answer, so
  it is no evidence, and the run stops instead.
- **Protected by a missing grant** when the log shows the attempt refused with `42501` by
  PostgreSQL's privilege check, and the catalog shows `anon` lacks the read grant on the table. The
  basis names the missing grant.
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

### Insert

- **Exposed** when the direct view finds, after the attempt, a row that was not in the table before
  it and that came from the attempt. The evidence is that row as stored. Why: only the stored row
  shows the write landed; a success status can come from a trigger that dropped it.
- **Protected** when the log shows the attempt refused with `42501` by PostgreSQL's row-level security
  check (the row failed the insert policies) or by its privilege check while the catalog shows `anon`
  lacks the insert grant, and the direct view finds no new row. Why: these are the two refusals that
  mean "the visitor may not create this row"; any other refusal (a constraint, a trigger, a unique
  key) only says this particular row was unacceptable.
- After a refusal by row-level security, the value search tries further rows; the insert is protected
  only when every row it tries is refused by row-level security or the privilege check. Why: a policy
  that admits only certain values is still open to whoever sends those values.
- A refusal of any other kind is never protected: what rlsentry may clear and try again is for
  `anon-write`'s brief; if no verdict can be shown after that, the run stops.

### Update and delete

The two follow the same rules; only the change looked for differs.

- **Exposed** when the direct view finds, after the attempt, a row that was in the table changed to
  the values the attempt sent (update), or gone (delete). The evidence is the row before and after
  (update) or the row removed (delete). Why: the table itself is the only proof a write landed.
- **Protected** when the direct view finds every row unchanged and either:
  - the log shows the attempt refused with `42501` by PostgreSQL's row-level security check (an
    update's new row failed the policies) or by its privilege check while the catalog shows `anon`
    lacks the grant; or
  - the attempt's statement ran without error and reached no row, the direct view found rows in the
    table, the attempt carried no filter of its own, and PostgreSQL says row-level security applies to
    that statement.

  Why: row-level security hides rows from an update or delete the way it hides them from a read,
  silently, so the silent case needs the same four facts as an empty read.
- An update or delete is judged protected only from an attempt with no filter. Why: a filter naming
  a row needs the visitor to be able to see that row, so a table whose only policy allows writing
  would look protected to an attempt by key, while an attempt without a filter changes every row.

### Exit codes

| Code | Means |
|---|---|
| `0` | The run finished and no operation on any table was exposed. |
| `1` | The run finished and at least one operation was exposed. |
| `2` | The run could not build the copy, could not attack it (a verdict could not be shown, or the command was refused, `--target` included), or could not finish (interrupted, or the copy failed). The message says which. |

- `2` wins over `1`: a run that found something exposed and then stopped exits `2`, and its message
  still names what was exposed. Why: `1` tells a script the whole project was checked; a run that
  stopped part way has not checked it, and one code for every unfinished run keeps scripts simple.

## Not yet built

Each scenario below is built by `anon-read`. "Shown by" says how a person or a test sees it hold.

### Read a table that has row-level security off (`anon-read`)

Given a project with a table that has row-level security off,
when the user runs rlsentry on its migrations,
then the table's read is exposed, the basis says the visitor read every one of its rows, one fake
row is shown as evidence, and the command exits `1`.
Shown by: a test runs rlsentry on a lab schema with such a table and checks the verdict, that the
evidence row is one of the rows the copy was seeded with, and the exit code.

### Read a table whose policy lets everyone read (`anon-read`)

Given a table with row-level security on and a read policy for `anon` that admits every row,
when the user runs rlsentry,
then its read is exposed, with a fake row as evidence, and the command exits `1`.
Shown by: a test on a lab schema with such a policy checks the verdict, the evidence and the exit
code.

### Read a table whose policy lets some rows through (`anon-read`)

Given a table whose read policy admits only rows with a certain value, and seeded rows both with and
without it,
when the user runs rlsentry,
then its read is exposed, the basis says how many of the table's rows the visitor got, and the
evidence is one of the admitted rows.
Shown by: a test checks the verdict, the count against the rows seeded, and that the evidence row
holds the admitted value.

### Read a table whose policies admit no anonymous visitor (`anon-read`)

Given a table with row-level security on and no read policy that admits `anon`,
when the user runs rlsentry,
then its read is protected, the basis says row-level security kept out every one of its seeded
rows, and if nothing else is exposed the command exits `0`.
Shown by: a test checks the verdict, the basis and the exit code; and a person reads in the copy's
log that the attempt's statement ran and that PostgreSQL refused the same statement with row-level
security switched off.

### Read a table the anonymous visitor holds no grant on (`anon-read`)

Given a table whose read grant has been taken from `anon`,
when the user runs rlsentry,
then its read is protected, and the basis names the missing grant.
Shown by: a test checks the verdict and that the basis names the grant.

### An empty answer the database does not explain stops the run (`anon-read`)

Given a table the anonymous visitor gets no rows from while something other than a policy is the
reason (for example, the table holds no rows when it is read),
when the user runs rlsentry,
then no verdict is given for that read, the run stops, its message names the table and which fact
was missing, and the command exits `2`.
Shown by: a test on a schema built so that the table is empty when read checks that no verdict is
reported, the message, and the exit code.

### A refusal that only imitates the database stops the run (`anon-read`)

Given a table whose read policy calls a function that raises a permission error with the same code
and message the database itself would use,
when the user runs rlsentry,
then the read is not marked protected; the run stops, naming the table and saying the refusal did
not come from the database's own checks, and the command exits `2`.
Shown by: a test on a lab schema with such a function checks that no protected verdict appears, the
message, and the exit code.

### An answer holding rows the table does not hold stops the run (`anon-read`)

Given a table whose read answer is shaped by code in the migrations to hold rows the table does not
hold,
when the user runs rlsentry,
then the read is neither exposed nor protected; the run stops, naming the table, and the command
exits `2`.
Shown by: a test on a schema built to do this checks that no verdict is reported and the exit code.

### A redirect is never followed (`anon-read`)

Given a table whose read policy makes the REST layer answer with a redirect to another address,
when the user runs rlsentry,
then no request goes to that address, the run stops, its message says the read was answered with a
redirect, and the command exits `2`.
Shown by: a test that points the redirect at an address it watches, and checks that nothing arrives
there, the message, and the exit code.

### A run that finds something and then stops exits 2 (`anon-read`)

Given a project with one table whose read is exposed and, attacked after it, another whose read
cannot be shown either way,
when the user runs rlsentry,
then the message names the exposed table and the table that stopped the run, and the command exits
`2`, not `1`.
Shown by: a test on such a schema checks the message and the exit code.

## Changed by

- `v3-spec`: the first version of this area.
