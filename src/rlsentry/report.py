"""The one result object of a run, and the two forms rendered from it and from nothing else: the
text summary (standard output) and the JSON report (a file, when asked for), which follows the
published `report.schema.json`.

Every value from the copy (names the migrations chose, evidence rows, answers) is data: the summary
shows control characters as visible escapes, and the JSON report holds values as JSON values and
is written as ASCII, so neither form can send an escape sequence to a terminal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import metadata, resources
from pathlib import Path

EXIT_NONE_EXPOSED = 0
EXIT_EXPOSED = 1
EXIT_STOPPED = 2
PROTECTED_LATER = "protected verdicts come with anon-read-protected"
EXIT_MEANINGS = {
    EXIT_NONE_EXPOSED: "no read was shown exposed, and every table got a verdict",
    EXIT_EXPOSED: "at least one read is exposed, and every table got a verdict",
    EXIT_STOPPED: "the run stopped: some table got no verdict",
}


def schema() -> dict:
    """The published schema of the JSON report."""
    return json.loads(resources.files("rlsentry").joinpath("report.schema.json").read_text())


SCHEMA_VERSION = schema()["properties"]["schema_version"]["const"]


def rlsentry_version() -> str:
    return metadata.version("rlsentry")


@dataclass
class Attempt:
    """One request of a read: what came back. `rows` is set when it held rows the table holds;
    otherwise `reason` says why it did not show the read exposed."""
    key: str                      # "anon key" or "no key"
    status: int | None            # the HTTP status; None when no answer came
    error_code: str | None = None  # the PostgreSQL error code the answer named, if any
    rows: int | None = None
    reason: str | None = None


@dataclass
class Basis:
    requests: list[str]           # which requests got rows: "anon key", "no key"
    rows_read: int                # how many of the table's rows the visitor got
    rows_held: int                # how many rows the table held
    columns: list[str] | None     # the columns read, when the read grant covers only some


@dataclass
class Outcome:
    schema: str
    table: str
    operation: str = "read"
    verdict: str | None = None    # "exposed", or None: no verdict
    basis: Basis | None = None
    evidence: dict | None = None  # one row as the direct view holds it, on the columns read
    attempts: list[Attempt] = field(default_factory=list)
    reason: str | None = None     # for no verdict: why, when it is not in the attempts

    @property
    def name(self) -> str:
        return f"{self.schema}.{self.table}"


@dataclass
class Stopped:
    reason: str
    table: str | None = None


@dataclass
class Result:
    ran_at: str = ""              # the time of the run, UTC; the only fact that differs between two runs
    rlsentry: str = field(default_factory=rlsentry_version)
    postgres: str = ""
    postgrest: str = ""
    migrations: int = 0
    exposed_schemas: list[str] = field(default_factory=list)
    not_reachable: list[str] = field(default_factory=list)   # tables in schemas the API does not expose
    partitions: dict[str, list[str]] = field(default_factory=dict)  # parent -> partitions reached through it
    outcomes: list[Outcome] = field(default_factory=list)
    finished: bool = False
    stop: Stopped | None = None   # a stop that ended the run at once

    @property
    def without_verdict(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.verdict is None]

    @property
    def exposed(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.verdict == "exposed"]

    @property
    def exit_code(self) -> int:
        if self.stop is not None or not self.finished or self.without_verdict:
            return EXIT_STOPPED
        return EXIT_EXPOSED if self.exposed else EXIT_NONE_EXPOSED

    @property
    def stopped_because(self) -> str | None:
        """Why the run ends with exit 2, or None when it does not."""
        if self.stop is not None:
            return self.stop.reason
        if self.without_verdict:
            listed = "; ".join(f"{o.name} {o.operation} ({describe_no_verdict(o)})" for o in self.without_verdict)
            return f"no verdict for {listed}. These reads were not shown exposed; {PROTECTED_LATER}"
        if not self.finished:
            return "the run did not finish"
        return None


def _attempt_text(a: Attempt) -> str:
    if a.status is None:
        return f"{a.key}: {a.reason}"
    code = f", error code {a.error_code}" if a.error_code else ""
    return f"{a.key}: status {a.status}{code}, {a.reason}"


def describe_no_verdict(o: Outcome) -> str:
    if o.reason:
        return o.reason
    return "; ".join(_attempt_text(a) for a in o.attempts)


def describe_basis(b: Basis) -> str:
    who = " and ".join(("with the anon key" if r == "anon key" else "without a key") for r in b.requests)
    text = f"rows came back {who}; {b.rows_read} of the table's {b.rows_held} rows"
    if b.columns is not None:
        text += f"; columns read: {', '.join(b.columns)}"
    return text


def shown(text: str) -> str:
    """One line of the summary: every character that is not printable, newlines and tabs too, shown
    as a visible escape, so a value from the copy can neither act on the terminal nor forge a line."""
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in text)


def _row_text(row: dict) -> str:
    """A row as JSON that stays valid JSON and holds no character that is not printable."""
    text = json.dumps(row, ensure_ascii=False)
    return "".join(c if c.isprintable() else f"\\u{ord(c):04x}" for c in text)


def summary(result: Result) -> str:
    """The text summary: one line per table and operation, each exposed read's evidence row, the
    tables reached through a parent or not at all, why the run stopped, and the exit code."""
    out = [
        f"rlsentry {result.rlsentry}: copy built from {result.migrations} migration(s) on "
        f"PostgreSQL {result.postgres} and PostgREST {result.postgrest}",
        f"exposed schemas: {', '.join(result.exposed_schemas)}",
    ]
    for o in result.outcomes:
        if o.verdict == "exposed":
            out.append(f"{o.operation} {o.name}: exposed; basis: {describe_basis(o.basis)}")
            out.append(f"  evidence: {_row_text(o.evidence)}")
        else:
            out.append(f"{o.operation} {o.name}: no verdict; {describe_no_verdict(o)}")
    for parent, parts in result.partitions.items():
        out.append(f"partitions of {parent}, reached through it: {', '.join(parts)}")
    for name in result.not_reachable:
        out.append(f"not reachable over the REST layer with these settings: {name}")
    why = result.stopped_because
    if why is not None:
        at = f" at {result.stop.table}" if result.stop is not None and result.stop.table else ""
        out.append(f"stopped{at}: {why}")
    out.append(f"exit {result.exit_code}: {EXIT_MEANINGS[result.exit_code]}")
    return "\n".join(shown(line) for line in out)


def stop_message(result: Result) -> str | None:
    """What the run says on standard error when it ends with exit 2 after the attack began."""
    why = result.stopped_because
    if why is None:
        return None
    exposed = [o.name for o in result.exposed]
    found = f"exposed before the stop: {', '.join(exposed)}. " if exposed else ""
    return f"{found}stopped: {why}"


def as_json(result: Result) -> dict:
    """The JSON report, as `report.schema.json` describes it."""
    def basis(b: Basis | None):
        if b is None:
            return None
        return {"requests": b.requests, "rows_read": b.rows_read, "rows_held": b.rows_held,
                "columns": b.columns, "text": describe_basis(b)}

    return {
        "schema_version": SCHEMA_VERSION,
        "ran_at": result.ran_at,
        "versions": {"rlsentry": result.rlsentry, "postgresql": result.postgres, "postgrest": result.postgrest},
        "migrations": result.migrations,
        "exposed_schemas": result.exposed_schemas,
        "results": [{
            "schema": o.schema,
            "table": o.table,
            "operation": o.operation,
            "verdict": o.verdict,
            "basis": basis(o.basis),
            "evidence": o.evidence,
            "attempts": [{"key": a.key, "status": a.status, "error_code": a.error_code, "rows": a.rows,
                          "reason": a.reason} for a in o.attempts],
            "reason": None if o.verdict else describe_no_verdict(o),
        } for o in result.outcomes],
        "partitions": [{"parent": p, "partitions": parts} for p, parts in result.partitions.items()],
        "not_reachable": result.not_reachable,
        "finished": result.finished,
        "stop": None if result.stopped_because is None else {
            "reason": result.stopped_because,
            "table": result.stop.table if result.stop is not None else None,
        },
        "exit_code": result.exit_code,
        "exit_meaning": EXIT_MEANINGS[result.exit_code],
    }


def write_json(result: Result, path: Path) -> None:
    # ASCII only: a value holding an escape character is written as \u001b, never as the byte.
    path.write_text(json.dumps(as_json(result), indent=2, ensure_ascii=True) + "\n")
