"""The `rlsentry` command: the order of a run, and its exit code."""

from __future__ import annotations

import argparse
import signal
import sys

from . import inputs, versions
from .copy import Copy
from .pg import quote_literal
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


def _run(arg: str) -> int:
    project = inputs.resolve(arg)
    for note in project.notes:
        say(note)
    programs, found = versions.check()
    with Copy(project, programs, found, say=say) as copy:
        with copy.connect() as admin:
            tables = admin.rows(
                "select n.nspname, c.relname, c.relrowsecurity "
                "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where c.relkind in ('r', 'p') and not c.relispartition "
                "and n.nspname in (" + ", ".join(map(quote_literal, project.exposed_schemas)) + ") "
                'order by n.nspname collate "C", c.relname collate "C"'
            )
        out = [
            f"copy built from {len(project.migrations)} migration(s) on "
            f"PostgreSQL {copy.versions.postgres} and PostgREST {copy.versions.postgrest}",
            f"exposed schemas: {', '.join(project.exposed_schemas)}",
            f"tables in them: {len(tables)}",
        ]
        for schema, table, rls in tables:
            out.append(f"  {schema}.{table} (row-level security {'on' if rls == 't' else 'off'})")
        out.append("nothing was attacked: reading the tables as the anonymous visitor is not built yet")
        print(printable("\n".join(out)), flush=True)
    return 0


def main_exit() -> None:
    sys.exit(main())
