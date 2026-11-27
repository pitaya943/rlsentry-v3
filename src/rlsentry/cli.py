"""The `rlsentry` command: the order of a run, and its exit code."""

from __future__ import annotations

import argparse
import signal
import sys

from . import attack, direct, inputs, verdicts, versions
from .copy import Copy
from .report import Outcome, Result, Stopped, plain, stop_message
from .stops import Stop, printable

EXIT_STOPPED = 2
EXIT_INTERRUPTED = 130


class Terminated(BaseException):
    """SIGTERM, raised where the run is so the copy is destroyed on the way out."""


def _on_sigterm(signum, frame):
    raise Terminated()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rlsentry",
        description="Build a throwaway copy of a Supabase project from its migrations and attack it "
        "as the anonymous visitor.",
    )
    p.add_argument("project", nargs="?", help="a Supabase project's folder, or a folder of .sql files")
    p.add_argument("--target", metavar="URL", help="a live project: refused, not available yet")
    return p


def say(message: str) -> None:
    print(f"rlsentry: {printable(message)}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.target is not None:
        # Refused before anything else: the URL is never parsed, looked up or connected to.
        say("live targets are not available yet: --target is refused, and nothing was built or sent")
        return EXIT_STOPPED
    if args.project is None:
        _parser().print_usage(sys.stderr)
        say("name a project's folder")
        return EXIT_STOPPED
    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return _run(args.project)
    except Stop as stop:
        say(f"stopped: {stop.reason}")
        return EXIT_STOPPED
    except (KeyboardInterrupt, Terminated):
        say("interrupted: the copy was destroyed")
        return EXIT_INTERRUPTED
    except Exception as e:  # never exit 1 (exposed) or 0 on a failure of rlsentry's own
        say(f"failed: {type(e).__name__}: {e}; the copy was destroyed")
        return EXIT_STOPPED


def _run(arg: str) -> int:
    project = inputs.resolve(arg)
    for note in project.notes:
        say(note)
    programs, found = versions.check()
    with Copy(project, programs, found, say=say) as copy:
        result = Result(migrations=len(project.migrations), exposed_schemas=project.exposed_schemas,
                        postgres=copy.versions.postgres, postgrest=copy.versions.postgrest)
        try:
            _attack(copy, project, result)
            result.finished = True
        except Stop as stop:
            result.stop = Stopped(stop.reason, stop.table)
        print(plain(result), flush=True)
        message = stop_message(result)
        if message:
            say(message)
    return result.exit_code


def _attack(copy: Copy, project, result: Result) -> None:
    """Every table of an exposed schema, in schema-qualified name order, read with the anon key and
    with no key; a stop that means the copy cannot be trusted ends it at once."""
    key = attack.anon_key(copy.jwt_secret)
    with copy.connect() as admin:
        result.not_reachable = direct.not_reachable(admin, project.exposed_schemas)
        result.partitions = direct.partitions(admin, project.exposed_schemas)
        for table in direct.tables(admin, project.exposed_schemas):
            outcome = Outcome(table.schema, table.name)
            if not table.columns:
                outcome.reason = "the table has no columns; no request sent"
            elif not table.schema_usage:
                outcome.reason = (f"anon is not granted usage on schema {table.schema}, which Supabase "
                                  "grants only on public; no request sent")
            elif not table.readable:
                outcome.reason = "no column it may read; no request sent"
            else:
                partial = None if table.readable == table.columns else table.readable
                judged = []
                for token in (key, None):
                    rows = direct.rows(admin, table, table.readable)  # the table just before this request
                    answer = attack.read(copy.rest_port, table.schema, table.name, table.readable, token)
                    attempt, got = verdicts.judge_answer(f"{table.schema}.{table.name}", answer, rows)
                    judged.append((attempt, got, rows))
                outcome = verdicts.judge(table.schema, table.name, judged, partial)
            result.outcomes.append(outcome)


def main_exit() -> None:
    sys.exit(main())
