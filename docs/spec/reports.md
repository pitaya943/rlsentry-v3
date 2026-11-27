# Reports

This area says what a run tells the person who ran it and the script that called it: the text
summary, the JSON report and its published schema, and, later, the HTML report.

## Scenarios

None hold yet: nothing is built. The scenarios `anon-read` builds are under
[Not yet built](#not-yet-built).

## Rules

Every rule here was decided by `v3-spec`.

### One set of facts, several forms

- Every form of report holds the same facts: for each table in an exposed schema and each operation
  attacked, its verdict, basis and, when exposed, evidence; the tables not reachable over the REST
  layer; whether the run finished, and if not, why it stopped; the exit code; the versions of
  rlsentry, PostgreSQL and PostgREST; the exposed schemas; and the bound a protected verdict covers.
  Why: a person and a script reading the same run must not reach different conclusions, and a form
  that held more than the others would be the only one some readers trusted.
- The text summary is printed on standard output; messages about the run's progress and its stop go
  to standard error. The JSON report is written to a file only when the user asks for one. Why: a
  script can then read the summary or the report without parsing progress lines.
- A run that stopped writes the same report, with what it found up to the stop and the reason it
  stopped. No table that was not judged appears with a verdict. Why: what was found is still true,
  and the reader needs the stop's reason to fix it; leaving unjudged tables without a verdict keeps
  the two-verdict rule ([verdicts](verdicts.md#two-verdicts-and-nothing-between-them)).

### Values from the copy are data

- Every value from the copy (evidence rows, and table, column and policy names, which the migrations
  chose) is shown as data in every form: in the text summary, control characters and terminal escape
  sequences are shown as visible escapes, never sent to the terminal; in the JSON report every value
  is a JSON string or number, never spliced into the report's structure. Why: the copy's values are
  untrusted ([threat model](threat-model.md#what-is-not-trusted)), and a value that moves the cursor
  or recolours the terminal could make a printed exposed look protected.
- A report holds only rows rlsentry made up in the copy. Why: threat model rule 4.

### The JSON report and its schema

- The JSON report follows a JSON Schema published with rlsentry, and names the version of the schema
  it follows. A change that removes or renames a field, or changes what one means, is a new major
  version; adding a field is a new minor version. Why: scripts and the HTML report read it, and a
  script must be able to tell whether it still understands a report.
- The report records the time of the run and nothing else that differs between two runs on the same
  migrations. Why: two runs can then be compared to find what changed in the project.

### The HTML report

- Built by `html-report`: one file per run, every style and script inside it, no request to the
  network when it is opened, the same facts as the JSON report and never more, so it opens offline
  and can be published as a Claude Artifact unchanged. It shows every value from the copy as text and
  runs only rlsentry's own script. Why: threat model rule 5, and a report meant to be shared must be
  safe to open anywhere.

## Not yet built

Each scenario below is built by the task it is marked with. "Shown by" says how a person or a test
sees it hold. The HTML report is `html-report`'s: each run can also write one self-contained HTML
report that opens offline and can be published as a Claude Artifact unchanged.

### Read the text summary (`anon-read`)

Given a run on a project with one exposed and one protected read,
when it finishes,
then the summary shows, one line per table and operation, the table with its schema, the verdict
and the basis, then the exposed table's evidence row, then the exit code and what it means.
Shown by: a test checks the summary's lines against the run's verdicts; a person reads it and finds
which table is exposed and why without opening anything else.

### Read the JSON report from a script (`anon-read`)

Given a run on a project, with a JSON report asked for,
when it finishes,
then the file is valid against the published schema, names the schema's version, and holds the same
verdicts, bases, evidence, exit code, versions, exposed schemas and tables not reachable as the
summary.
Shown by: a test validates the file against the schema and compares its facts with the summary.

### A stopped run still reports what it found (`anon-read`)

Given a run that found one exposed read and then stopped on another table,
when it exits,
then the summary and the JSON report both hold the exposed verdict, say the run stopped, name the
table and the reason, give no verdict to the tables not judged, and give the exit code `2`.
Shown by: a test on such a schema checks both forms.

### A row value cannot take over the terminal (`anon-read`)

Given a table whose column default puts a terminal escape sequence and markup into every row, and
whose read is exposed,
when the user runs rlsentry in a terminal,
then the summary shows the escape sequence as visible characters and the markup as text, and the
JSON report holds them as plain strings.
Shown by: a test checks the summary's bytes hold no escape character and the JSON value equals the
stored value; a person runs it in a terminal and sees nothing recoloured or moved.

### The basis of a protected read says where the promise ends (`anon-read`)

Given a run with a protected read,
when the user reads its basis in either form,
then it says the verdict covers the request shapes the verdicts area lists, one operation at a time,
against the rows the copy held, and both with the anon key and without a key.
Shown by: a test checks the basis's wording in both forms.

## Changed by

- `v3-spec`: the first version of this area.
