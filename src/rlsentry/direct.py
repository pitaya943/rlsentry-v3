"""The direct view: what the copy's catalog and tables hold, read as its superuser.

It calls no function and reads no view the migrations made. A value is rendered with PostgreSQL's
own `to_json` (as PostgREST renders it) only when its type, through any domain and array, is owned by
the superuser, since only then can no cast the migrations made be called; any other value (an enum
or a composite type of theirs) is shown through its type's output function, as a string.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import pg
from .pg import quote_ident, quote_literal

SETUP_TABLES = (("auth", "users"),)
OWN_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast", "rlsentry")


@dataclass
class TableFacts:
    oid: str
    schema: str
    name: str
    columns: list[str]     # every column, in order
    readable: list[str]    # the columns anon may read
    whole_table: bool      # anon holds the table's read grant
    schema_usage: bool     # anon may use the table's schema


def _schemas(names: list[str]) -> str:
    return ", ".join(map(quote_literal, names))


def tables(admin: pg.Connection, schemas: list[str]) -> list[TableFacts]:
    """Every table of the exposed schemas, in schema-qualified name order (partitions through their parent)."""
    [(text,)] = admin.rows(
        "select pg_catalog.json_agg(pg_catalog.json_build_array(c.oid::pg_catalog.text, n.nspname, c.relname,"
        " (select pg_catalog.json_agg(pg_catalog.json_build_array(a.attname,"
        "     pg_catalog.has_column_privilege('anon', c.oid, a.attnum, 'SELECT')) order by a.attnum)"
        "  from pg_catalog.pg_attribute a where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped),"
        " pg_catalog.has_table_privilege('anon', c.oid, 'SELECT'),"
        " pg_catalog.has_schema_privilege('anon', n.oid, 'USAGE'))"
        ' order by n.nspname collate "C", c.relname collate "C") '
        "from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
        "where c.relkind in ('r', 'p') and not c.relispartition "
        f"and n.nspname in ({_schemas(schemas)})"
    )
    out = []
    for oid, schema, name, cols, whole, usage in json.loads(text or "[]"):
        cols = cols or []
        out.append(TableFacts(oid, schema, name, [c for c, _ in cols], [c for c, ok in cols if ok], whole, usage))
    return out


def not_reachable(admin: pg.Connection, schemas: list[str]) -> list[str]:
    """Tables the migrations made in schemas the API does not expose."""
    own = " ".join(f"and not (n.nspname = {quote_literal(s)} and c.relname = {quote_literal(t)})" for s, t in SETUP_TABLES)
    rows = admin.rows(
        "select n.nspname || '.' || c.relname from pg_catalog.pg_class c "
        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
        "where c.relkind in ('r', 'p') and not c.relispartition "
        f"and n.nspname not in ({_schemas(schemas + list(OWN_SCHEMAS))}) {own} "
        'order by n.nspname collate "C", c.relname collate "C"'
    )
    return [r[0] for r in rows]


def partitions(admin: pg.Connection, schemas: list[str]) -> dict[str, list[str]]:
    rows = admin.rows(
        "select pn.nspname || '.' || p.relname, n.nspname || '.' || c.relname "
        "from pg_catalog.pg_inherits i join pg_catalog.pg_class c on c.oid = i.inhrelid "
        "join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
        "join pg_catalog.pg_class p on p.oid = i.inhparent join pg_catalog.pg_namespace pn on pn.oid = p.relnamespace "
        f"where c.relispartition and pn.nspname in ({_schemas(schemas)}) "
        'order by pn.nspname collate "C", p.relname collate "C", n.nspname collate "C", c.relname collate "C"'
    )
    out: dict[str, list[str]] = {}
    for parent, part in rows:
        out.setdefault(parent, []).append(part)
    return out


def table_oids(admin: pg.Connection, schemas: list[str]) -> list[str]:
    return [t.oid for t in tables(admin, schemas)]


def users_oid(admin: pg.Connection) -> str:
    return admin.rows("select 'auth.users'::pg_catalog.regclass::pg_catalog.oid::pg_catalog.text")[0][0]


def rows(admin: pg.Connection, table: TableFacts, columns: list[str]) -> list[dict]:
    """The table's rows on `columns`, each value as the JSON text PostgREST would render it."""
    safe = dict(admin.rows(
        "with recursive d(attname, t, depth) as ("
        f" select a.attname, a.atttypid, 0 from pg_catalog.pg_attribute a where a.attrelid = {int(table.oid)}"
        "  and a.attnum > 0 and not a.attisdropped"
        " union all select d.attname, x.next, d.depth + 1 from d, pg_catalog.pg_type ty,"
        "  lateral (values (case when ty.typtype = 'd' then ty.typbasetype else ty.typelem end)) x(next)"
        "  where ty.oid = d.t and x.next <> 0 and d.depth < 16"
        ") select d.attname, pg_catalog.bool_and(ty.typowner = (select r.oid from pg_catalog.pg_roles r where r.rolname = current_user))::pg_catalog.text "
        "from d join pg_catalog.pg_type ty on ty.oid = d.t group by d.attname"
    ))
    exprs = []
    for c in columns:
        col = quote_ident(c)
        if safe.get(c) == "true":
            exprs.append(f"pg_catalog.to_json({col})::pg_catalog.text")
        else:
            exprs.append(f"case when pg_catalog.num_nulls({col}) = 1 then null "
                         f"else pg_catalog.to_json(pg_catalog.format('%s', {col}))::pg_catalog.text end")
    found = admin.rows(f"select {', '.join(exprs)} from {quote_ident(table.schema)}.{quote_ident(table.name)}")
    out = [{c: ("null" if v is None else v) for c, v in zip(columns, row)} for row in found]
    return sorted(out, key=lambda r: json.dumps(r, sort_keys=True))
