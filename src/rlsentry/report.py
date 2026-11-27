"""The one result object of a run. Every form of report is rendered from it, and from nothing else.

T-02 renders it as a plain list of outcomes; the summary and the JSON report are T-03's.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .stops import printable

EXIT_NONE_EXPOSED = 0
EXIT_EXPOSED = 1
EXIT_STOPPED = 2
PROTECTED_LATER = "protected verdicts come with anon-read-protected"


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
    postgres: str = ""
    postgrest: str = ""
    migrations: int = 0
    exposed_schemas: list[str] = field(default_factory=list)
    not_reachable: list[str] = field(default_factory=list)   # tables in schemas the API does not expose
    partitions: dict[str, list[str]] = field(default_factory=dict)  # parent -> partitions reached through it
    outcomes: list[Outcome] = field(default_factory=list)
    finished: bool = False
    stop: Stopped | None = None

    @property
    def without_verdict(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.verdict is None]

    @property
    def exit_code(self) -> int:
        if self.stop is not None or not self.finished or self.without_verdict:
            return EXIT_STOPPED
        return EXIT_EXPOSED if any(o.verdict == "exposed" for o in self.outcomes) else EXIT_NONE_EXPOSED


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


def plain(result: Result) -> str:
    """The plain list of outcomes (T-03 shapes the summary)."""
    out = [
        f"copy built from {result.migrations} migration(s) on "
        f"PostgreSQL {result.postgres} and PostgREST {result.postgrest}",
        f"exposed schemas: {', '.join(result.exposed_schemas)}",
    ]
    for o in result.outcomes:
        if o.verdict == "exposed":
            out.append(f"{o.operation} {o.name}: exposed; basis: {describe_basis(o.basis)}")
            out.append(f"  evidence: {json.dumps(o.evidence, ensure_ascii=False)}")
        else:
            out.append(f"{o.operation} {o.name}: no verdict; {describe_no_verdict(o)}")
    for parent, parts in result.partitions.items():
        out.append(f"partitions of {parent}, reached through it: {', '.join(parts)}")
    for name in result.not_reachable:
        out.append(f"not reachable over the REST layer with these settings: {name}")
    return printable("\n".join(out))


def stop_message(result: Result) -> str | None:
    """What the run says on standard error when it ends with exit 2 after the attack began."""
    exposed = [o.name for o in result.outcomes if o.verdict == "exposed"]
    found = f"exposed before the stop: {', '.join(exposed)}. " if exposed else ""
    if result.stop is not None:
        return f"{found}stopped: {result.stop.reason}"
    if result.without_verdict:
        listed = "; ".join(f"{o.name} {o.operation} ({describe_no_verdict(o)})" for o in result.without_verdict)
        return f"{found}stopped: no verdict for {listed}. These reads were not shown exposed; {PROTECTED_LATER}"
    return None
