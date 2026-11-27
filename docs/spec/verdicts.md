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

- A missing grant protects an operation only when the catalog shows `anon` holds that privilege on
  neither the table nor any of its columns. Why: PostgreSQL grants read, insert and update on single
  columns as well as on the whole table; a visitor refused a whole-row attempt for lacking the table
  grant can still read, write or change the columns granted to it, so that refusal says nothing
  about them.
- When `anon` holds a privilege on some columns only, every attempt for that operation names exactly
  those columns (a read asks for them, an insert or update sends values only for them), and it is
  judged by the rules below like any other attempt. Why: those columns are what the visitor can
  actually reach; an attempt naming others is refused by the grant before any policy is asked, so it
  shows nothing about the policies.
- Delete has no column privilege; its grant is the table's alone.

### Read

- **Exposed** when the attempt's answer holds at least one row, and every row in it matches, on the
  columns it holds, a row the direct view finds in the table. The evidence is one of those rows as
  the direct view holds it, limited to the columns the visitor read. The basis says how many of the
  table's rows the visitor got and, when its read grant covers only some columns, which ones. Why:
  rows the table really holds are the leak itself; a row the table does not hold could only come from
  code that shaped the answer, so it is no evidence, and the run stops instead.
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

### Insert

- **Exposed** when the direct view finds, after the attempt, a row that was not in the table before
  it and that came from the attempt. The evidence is that row as stored. Why: only the stored row
  shows the write landed; a success status can come from a trigger that dropped it.
- **Protected** when the log shows the attempt refused with `42501` by PostgreSQL's row-level security
  check (the row failed the insert policies) or by its privilege check while the catalog shows `anon`
  holds the insert privilege on neither the table nor any of its columns, and the direct view finds
  no new row. Why: these are the two refusals that mean "the visitor may not create this row"; any
  other refusal (a constraint, a trigger, a unique key) only says this particular row was
  unacceptable.
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
- The first attempt carries no filter. Why: a filter can only narrow the rows a statement reaches,
  and PostgreSQL lets a statement with a filter reach only rows its read policies admit, so a table
  whose only policy allows writing would look protected to an attempt by key, while one without a
  filter reaches every row the write policies admit.
- Every update attempt sends, in some column the visitor may update, a value no row holds, besides
  any value the value search is testing; when the visitor may update no other column, a row that
  already holds the tested value is one that try cannot change, and the try says nothing about it.
  So an update attempt **reached no row** when it ended without error and every row it could change
  is unchanged; a delete attempt, when it ended without error and every row is still there. Why: no
  signal the REST layer relays counts rows, and a row the attempt reached is a row the direct view
  sees changed.
- **Protected** when the direct view finds every row unchanged and either:
  - the log shows the attempt refused with `42501` by PostgreSQL's privilege check while the catalog
    shows `anon` holds the privilege on neither the table nor any of its columns (for delete, on the
    table); or
  - the attempt reached no row, the direct view found rows in the table, the attempt carried no
    filter of its own, and PostgreSQL says row-level security applies to that statement; or
  - the attempt without a filter was refused, and every row then tried on its own (below) is
    protected.

  Why: row-level security hides rows from an update or delete the way it hides them from a read,
  silently, so the silent case needs the same four facts as an empty read. A refusal by row-level
  security is not enough on its own, as the next rule says.
- **A statement refused as a whole says nothing about each row.** When an attempt without a filter
  is refused by anything other than the privilege check (row-level security's check on a new row, a
  constraint, a trigger), rlsentry tries each row of the table on its own: a filter on that row's
  values in the columns the visitor may read, picking out that row or the fewest rows the visitor can
  name together. Each such try is judged like the first attempt, and after a refusal by row-level
  security an update's value search runs on that row. The row is protected when its try is refused
  by row-level security for every value tried, or reached no row while PostgreSQL says row-level
  security applies to it. When `anon` may read none of the table's columns, the visitor can send no
  filter at all, so the refused attempt without one is the only request it has, and it stands for
  every row. Why: PostgreSQL refuses a whole statement when any one row it reaches is refused, so one
  row the visitor may not change can hide every row it may; a row refused alone is refused in every
  statement that reaches it, and a row hidden from a filtered try is reachable only without a
  filter, which was refused.
- After an update is refused by row-level security, the value search tries further new values, as
  for insert; the update is protected only when every value it tries is refused by row-level
  security or the privilege check and every row is still unchanged. Why: a policy whose check admits
  only certain new values still lets whoever sends those values rewrite the rows, in every other
  column too. A delete writes no new row, so no policy can refuse it for its values and it has no
  value search.
- A refusal of any other kind, on the first attempt or on a row tried alone, is never protected; as
  for insert, what follows is for `anon-write`'s brief, and if no verdict can be shown the run stops.

### Request shapes

A protected verdict is a claim about every request the
[threat model](threat-model.md#what-the-attacker-can-send) lets the visitor send for that operation,
not about the requests rlsentry chose. For each way the visitor can vary a request, this table says
why rlsentry's attempts answer for it. A rule added later to this area adds its row here. Why: a rule
that is true only of the attempts it lists says protected on tables a different request opens.

| Operation | The visitor varies | Why the attempts answer for it |
|---|---|---|
| all | the columns named | [Grants](#grants): attempts name exactly the columns `anon` may use, and a missing grant protects only when it holds none. |
| read | filter, range, order | Each can only narrow an answer, and the attempt carries none, so it holds every row any of them could return. |
| insert, update | the values sent | The value search, after a refusal by row-level security. |
| insert | rows per request | Each row is checked on its own and one refused row refuses the request, so a row refused alone is refused in any request; each attempt sends one row. |
| update, delete | filter or none | The first attempt has none: a filter only narrows the rows reached and adds the read policies to them. |
| update, delete | which rows | A statement refused as a whole is followed by a try of each row on its own, as above. |
| update | an insert that turns into an update on a duplicate key | PostgreSQL requires the existing row to be readable and passes the change through the update policies, so it reaches only rows a filtered update reaches, and the tries of each row answer for it. |

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

Given a table on which `anon` holds the read privilege on neither the table nor any of its columns,
when the user runs rlsentry,
then its read is protected, and the basis names the missing grant.
Shown by: a test checks the verdict and that the basis names the grant.

### Read a table whose read grant covers only some columns (`anon-read`)

Given a table with row-level security off on which `anon` holds no table read grant but holds the
read privilege on some of its columns,
when the user runs rlsentry,
then its read is exposed, the basis names the columns the visitor read, the evidence holds only
those columns, and the command exits `1`.
Shown by: a test on a lab schema with such column grants checks the verdict, the columns named in
the basis and the evidence, and the exit code.

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
