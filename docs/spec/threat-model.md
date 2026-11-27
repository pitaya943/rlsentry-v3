# Threat model

This area says whom rlsentry plays when it attacks, what a win for them looks like, and what
rlsentry itself must never be able to do, so that every other area's rules can be traced to a
reason here.

## Scenarios

None of its own. The behaviour that enforces each rule below is written as scenarios in the area
that owns it, under Scenarios once built (see [Which area enforces each rule](#which-area-enforces-each-rule)).

## Rules

Every rule here was decided by `v3-spec`.

### What the attacker holds

- **The anonymous visitor** holds the project's URL and its anon key, and nothing more. Why: this is
  exactly what any browser that loads the project's app receives, so it is the least an outsider
  can be assumed to have, and the flaw behind CVE-2025-48757 needs no more.
- **From `authenticated-attack` on, a logged-in user** also holds a session for an account they
  created themselves through the project's normal sign-up. Why: on most projects anyone may sign up,
  so "logged in" is barely more than anonymous, and the question becomes whether one account can
  reach another's rows.
- The attacker never holds the service-role key, a database password, a direct database
  connection, or access to the machine the project runs on. Why: whoever holds those can already do
  anything, so no policy could stop them and there is nothing for rlsentry to measure.

### What the attacker can send

- Any HTTP request to the project's REST layer that the anon key (or, later, the session) lets them
  send: any method, any table name, any filter, ordering, range or column list, any `Prefer` header,
  any body, and as many requests as they like, in any order. Why: the REST layer is public and
  documented, and nothing in Supabase limits a visitor to the requests the project's own app makes.
- rlsentry does not try every such request. A protected verdict covers the request shapes the
  [verdicts area](verdicts.md#the-bound-of-a-protected-verdict) lists, and when a table's code
  depends on anything else the visitor can change (a header, a cookie, the moment a request is
  sent), the run stops instead of giving a verdict. Why: the requests a visitor can send have no end,
  so a promise about all of them could not be kept; one bounded by a published list can, and
  stopping outside it keeps rule 6 below.
- From `more-surfaces` on, also calls to database functions exposed over the API, and requests to
  storage buckets. Why: they answer to the same key, and a policy gap there leaks just as much.
- The attacker cannot change the project's schema, policies, grants or REST settings. Why: those come
  from the migrations, which the attacker does not write; rlsentry tests what the migrations built.

### What counts as a successful attack

For each operation on a table, the attacker wins when:

- **read**: the answer contains values from at least one row the table really holds, even if only
  some of its columns;
- **insert**: a row the attacker sent is now in the table;
- **update**: a row that was in the table now holds values the attacker sent;
- **delete**: a row that was in the table is gone.

Why: these are the outcomes that harm the project's owner (data seen, data planted, data altered,
data lost), and each can be checked by looking at the table itself, not at what the REST layer
said. A win on one row is a win: a policy that lets some rows through and keeps others out still lets
the visitor reach those rows. The [verdicts](verdicts.md) area turns these into exposed and protected.

### What is not trusted

- **The migrations**, and so every policy, trigger, function, default and extension they create.
  Why: they come from the project being studied, and from `ci-gate` on, from any pull request;
  anyone who can write a migration can write code that runs inside the copy.
- **Every answer the copy gives over HTTP**: status, headers, body, error text. Why: code in the
  migrations can shape them (a policy can call a function that raises any error code with any
  message, or sets the response's status and headers), so they say what that code chose, not what
  the database did.
- **Every value in the copy**, fake rows included, once it has passed through the migrations' code.
  Why: a default or a trigger can put anything into a row, including markup meant to run in a report.

### What rlsentry itself must never do

1. **Reach anything but its own copy, by default.** rlsentry's attempts go only to the REST layer of
   the copy it started in this run, on this machine's loopback interface; it follows no redirect and
   opens no address an answer names. Why: an attack tool that can be steered elsewhere by what it
   reads is itself a weapon, and the copy's answers are not trusted.
2. **Let migration code reach the machine running it.** Nothing a migration contains may run a
   program, read or write a file, or open a network connection outside the copy's own database
   server. Why: the migrations are untrusted code, and a user must be able to study a stranger's
   project without handing that stranger their computer. The mechanism, on each backend:
   - *on both backends*: migrations and seeding run as a database role that is not a superuser and
     holds none of PostgreSQL's roles for running server programs or reading and writing server
     files; no untrusted procedural language is installed; only a fixed list of extensions that
     touch neither files nor the network can be created; the REST layer takes its settings from
     rlsentry alone, never from inside the database. A migration that needs more than this makes the
     run stop with exit `2`, naming the statement. Why: these are the routes by which SQL can leave
     the database, and each is closed by PostgreSQL's own privilege checks rather than by rlsentry
     reading the SQL, which it could misread;
   - *local processes*: the database server listens only on loopback and a socket in a directory
     only this run can reach, and keeps its data in a temporary directory removed when the run ends.
     Why: the server runs as the user's own account, so the privilege rules above are the boundary
     and nothing may widen what that account exposes;
   - *Docker*: in addition, the containers mount nothing from the host, sit on a network of their
     own with no route out, and run as a user other than root. Why: a second wall, so that even a
     flaw in PostgreSQL's privilege checks stays inside a container.
3. **Leave the copy behind.** However the run ends (finished, stopped, failed, interrupted), the copy
   and everything it wrote are destroyed. Why: a copy left running is a database with deliberately
   weak rules listening on the user's machine.
4. **Report a live project's real values.** No report, log or message rlsentry writes holds a value
   read from a real project, ever. Until `live-probe`, `--target` is refused before any connection is
   made; after it, only a project whose owner proves ownership and opts in for that run, with no write
   to its data. Why: a report gets shared, published and attached to pull requests; it must be safe
   to show anyone, so it may hold only rows rlsentry made up.
5. **Let a report run what the copy put in it.** Every value shown in a text, JSON or HTML report is
   shown as data, and the HTML report makes no network request and runs only rlsentry's own script.
   Why: row values are untrusted, and the HTML report is meant to be opened offline and published
   as is.
6. **Say "protected" on anything the copy's code could fake.** Why: a false "protected" is the one
   answer that does real harm, because the person stops looking. The [verdicts](verdicts.md) area
   says which signals count.

### Which area enforces each rule

| Rule | Enforced by |
|---|---|
| What the attacker holds: attempts carry only the anon key (later, the session) | [Attacking a project](attacking.md) |
| What the attacker can send: the requests each operation tries | [Attacking a project](attacking.md), [Verdicts and evidence](verdicts.md) |
| What counts as a successful attack | [Verdicts and evidence](verdicts.md) |
| 1. Reach nothing but its own copy | [Attacking a project](attacking.md), [The throwaway copy](throwaway-copy.md) |
| 2. Migration code never reaches the host | [The throwaway copy](throwaway-copy.md) |
| 3. The copy is always destroyed | [The throwaway copy](throwaway-copy.md) |
| 4. No live project's real values | [Live targets](live-targets.md), [Reports](reports.md) |
| 5. A report runs nothing the copy put in it | [Reports](reports.md) |
| 6. "Protected" only on the database's own account | [Verdicts and evidence](verdicts.md) |

### Who is not in this model

- Someone who already controls the machine running rlsentry, or its PostgreSQL and PostgREST
  installs. Why: they can change the tool itself; nothing it checks could hold.
- Attacks on the project's hosting, sign-in service or network. Why: they are not about the
  project's own rules, and the copy has none of them to attack.

## Not yet built

Nothing here is a scenario of its own: each rule is built and shown by the scenarios of the area
the table above names, marked with the task that builds them.

## Changed by

- `v3-spec`: the first version of this area.
- `anon-read-copy`: no rule changed; the scenarios that enforce rules 1 to 5 for a read now hold
  in the areas that own them, and rule 6's are `anon-read-protected`'s.
