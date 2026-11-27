"""Turning what the user names into an ordered list of migration files and the exposed schemas."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from .stops import Stop

# Supabase's default for `[api] schemas` when a project's configuration does not say.
DEFAULT_SCHEMAS = ["public", "graphql_public"]


@dataclass
class Project:
    name: str
    migrations: list[Path]
    exposed_schemas: list[str]
    notes: list[str] = field(default_factory=list)


def resolve(arg: str) -> Project:
    folder = Path(arg)
    if not folder.is_dir():
        raise Stop(f"{arg} is not a folder")
    notes = []
    supabase = folder / "supabase"
    if (supabase / "migrations").is_dir():
        source = supabase / "migrations"
        notes.append(f"using the migrations in {source} (a Supabase project's folder)")
    else:
        source = folder
    files = sorted((p for p in source.iterdir() if p.suffix == ".sql" and p.is_file()), key=lambda p: p.name)
    if not files:
        raise Stop(f"no .sql file in {source}")
    seen: dict[str, Path] = {}
    for p in files:
        other = seen.get(p.name.lower())
        if other is not None:
            raise Stop(
                f"two migrations have names that differ only in case, so their order is unclear: "
                f"{other.name} and {p.name}"
            )
        seen[p.name.lower()] = p
    return Project(
        name=str(folder),
        migrations=files,
        exposed_schemas=_exposed_schemas(supabase / "config.toml"),
        notes=notes,
    )


def _exposed_schemas(config: Path) -> list[str]:
    if not config.is_file():
        return list(DEFAULT_SCHEMAS)
    try:
        data = tomllib.loads(config.read_text())
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise Stop(f"{config} could not be read: {e}") from None
    schemas = data.get("api", {}).get("schemas")
    if schemas is None:
        return list(DEFAULT_SCHEMAS)
    if not isinstance(schemas, list) or not all(isinstance(s, str) and s for s in schemas):
        raise Stop(f"{config}: [api] schemas must be a list of schema names")
    return list(dict.fromkeys(schemas))
