"""The fake rows: every table of an exposed schema, and every table they reference, filled before
the attack, as the migrations' role and so through each table's own checks, triggers and foreign keys.

Catalog-driven, never by reading migration text. The values a table's rules name are the constants
its checks and read policies compare a column against (`<column> <op> <constant>`, and
`<column> in (...)`, which PostgreSQL shows as `= ANY (ARRAY[...])`); for each, one row holds it and
one holds none of them. Every other value is made up, recognisable as fake, and the same for the
same migrations.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field

from . import pg
from .pg import quote_ident, quote_literal

NAMESPACE = uuid.UUID("5b0c8f6e-6a43-4f7e-9d0e-2f1c6b7a9e10")  # rlsentry's own: fake uuids come from it
MIN_ROWS = 2
TRIES = 6

_IDENT = r'(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*)'
_CAST = r'(?:::(?:"[^"]+"|[A-Za-z_][\w.]*)(?:\s+(?:varying|precision|with(?:out)? time zone))?(?:\[\])?)*'
_CONST = r"(?:'(?:[^']|'')*'|-?\d+(?:\.\d+)?|true|false)"
_OP = r"(?:=|<>|!=|<=|>=|<|>)"
_COL_OP_CONST = re.compile(rf"(?<![\w.\"])(?P<col>{_IDENT}){_CAST}\s*{_OP}\s*\(?(?P<val>{_CONST}){_CAST}")
_CONST_OP_COL = re.compile(rf"(?P<val>{_CONST}){_CAST}\s*{_OP}\s*\(?(?P<col>{_IDENT})(?![\w(])")
_COL_IN = re.compile(rf"(?<![\w.\"])(?P<col>{_IDENT}){_CAST}\s*=\s*ANY\s*\(\s*\(?ARRAY\[(?P<list>[^\]]*)\]")
_ONE_CONST = re.compile(_CONST)


@dataclass
class Column:
    name: str
    base: str            # the base type's name, through any domain
    typtype: str         # 'b' base, 'e' enum, 'c' composite, ...
    category: str        # the base type's pg_type.typcategory
    length: int | None   # a character type's length limit
    notnull: bool
    hasdefault: bool
    skip: bool           # generated, or identity always: the table fills it
    labels: list[str] = field(default_factory=list)  # an enum's labels in order


@dataclass
class Table:
    oid: str
    schema: str
    name: str
    columns: list[Column]
    named: dict[str, list[str]]                 # column -> values its rules name
    keys: list[tuple[list[str], str, list[str]]]  # (columns, parent oid, parent columns)

    @property
    def qualified(self) -> str:
        return f"{quote_ident(self.schema)}.{quote_ident(self.name)}"


def named_values(expressions: list[str], columns: set[str]) -> dict[str, list[str]]:
    """The constants each expression compares a column of the table against, in order of appearance."""
    out: dict[str, list[str]] = {}

    def add(col: str, val: str) -> None:
        col = col[1:-1].replace('""', '"') if col.startswith('"') else col
        if col not in columns:
            return
        if val.startswith("'"):
            val = val[1:-1].replace("''", "'")
        values = out.setdefault(col, [])
        if val not in values:
            values.append(val)

    for text in expressions:
        found = []
        for m in _COL_IN.finditer(text):
            for v in _ONE_CONST.finditer(m["list"]):
                found.append((m.start(), m["col"], v.group(0)))
        for pattern in (_COL_OP_CONST, _CONST_OP_COL):
            for m in pattern.finditer(text):
                found.append((m.start(), m["col"], m["val"]))
        for _, col, val in sorted(found, key=lambda f: f[0]):
            add(col, val)
    return out


def _fake(table: Table, column: Column, n: int) -> str | None:
    """A made-up value for row `n` of the column, as a literal's text; None when none fits its type."""
    base, label = column.base, f"rlsentry-fake-{table.name}-{n}"
    if column.typtype == "e":
        return column.labels[n % len(column.labels)] if column.labels else None
    if column.category == "A":
        return "{}"
    if base == "bool":
        return "true" if n % 2 == 0 else "false"
    if column.category == "N":
        return str(n + 1)
    if base == "uuid":
        return str(uuid.uuid5(NAMESPACE, f"{table.schema}.{table.name}.{column.name}.{n}"))
    if column.category == "S" or base in ("citext",):
        if column.length is not None and len(label) > column.length:
            label = str(n)[-column.length:]
        return label
    if base == "date":
        return f"2024-01-{n % 28 + 1:02d}"
    if base in ("timestamp", "timestamptz"):
        return f"2024-01-{n % 28 + 1:02d} 12:00:00+00"
    if base in ("time", "timetz"):
        return f"12:{n % 60:02d}:00"
    if base == "interval":
        return f"{n + 1} days"
    if base in ("json", "jsonb"):
        return json.dumps({"rlsentry": label})
    if base == "bytea":
        return "\\x" + label.encode().hex()
    if base in ("inet", "cidr"):
        return f"192.0.2.{n % 250 + 1}"
    return None


def _catalog(admin: pg.Connection, oids: list[str]) -> dict[str, Table]:
    [(text,)] = admin.rows(
        "select pg_catalog.json_agg(pg_catalog.json_build_object("
        " 'oid', c.oid::pg_catalog.text, 'schema', n.nspname, 'name', c.relname,"
        " 'columns', (select pg_catalog.json_agg(pg_catalog.json_build_object("
        "     'name', a.attname, 'type', a.atttypid::pg_catalog.text, 'typmod', a.atttypmod,"
        "     'notnull', a.attnotnull, 'hasdefault', a.atthasdef,"
        "     'skip', a.attgenerated <> '' or a.attidentity = 'a') order by a.attnum)"
        "   from pg_catalog.pg_attribute a where a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped),"
        " 'rules', (select pg_catalog.json_agg(e order by k, nm) from ("
        "     select 1 as k, co.conname::pg_catalog.text as nm, pg_catalog.pg_get_constraintdef(co.oid) as e"
        "     from pg_catalog.pg_constraint co where co.conrelid = c.oid and co.contype = 'c'"
        "     union all select 2, p.polname::pg_catalog.text, pg_catalog.pg_get_expr(p.polqual, p.polrelid)"
        "     from pg_catalog.pg_policy p where p.polrelid = c.oid and p.polqual is not null"
        "     and p.polcmd in ('r', '*')) r),"
        " 'keys', (select pg_catalog.json_agg(pg_catalog.json_build_array("
        "     (select pg_catalog.json_agg(a.attname order by i.ord) from pg_catalog.unnest(co.conkey) with ordinality i(num, ord)"
        "      join pg_catalog.pg_attribute a on a.attrelid = co.conrelid and a.attnum = i.num),"
        "     co.confrelid::pg_catalog.text,"
        "     (select pg_catalog.json_agg(a.attname order by i.ord) from pg_catalog.unnest(co.confkey) with ordinality i(num, ord)"
        "      join pg_catalog.pg_attribute a on a.attrelid = co.confrelid and a.attnum = i.num))"
        "     order by co.conname)"
        "   from pg_catalog.pg_constraint co where co.conrelid = c.oid and co.contype = 'f')"
        ") order by c.oid) "
        "from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid = c.relnamespace "
        "where c.oid in (" + ", ".join(oids) + ")"
    )
    types: dict[str, tuple] = {}
    out = {}
    for t in json.loads(text or "[]"):
        columns = []
        for a in t["columns"] or []:
            base, typtype, category, length, labels = _base_type(admin, a["type"], a["typmod"], types)
            columns.append(Column(a["name"], base, typtype, category, length, a["notnull"], a["hasdefault"],
                                  a["skip"], labels))
        table = Table(t["oid"], t["schema"], t["name"], columns, {},
                      [(k[0], k[1], k[2]) for k in t["keys"] or []])
        table.named = named_values(t["rules"] or [], {c.name for c in columns})
        out[t["oid"]] = table
    return out


def _base_type(admin: pg.Connection, oid: str, typmod: int, cache: dict) -> tuple:
    if oid not in cache:
        [(text,)] = admin.rows(
            "with recursive d(oid, base, mod) as ("
            f" select t.oid, t.typbasetype, t.typtypmod from pg_catalog.pg_type t where t.oid = {int(oid)}"
            " union all select t.oid, t.typbasetype, t.typtypmod from pg_catalog.pg_type t join d on t.oid = d.base"
            ") select pg_catalog.json_build_array(t.typname, t.typtype, t.typcategory, d.mod,"
            " (select pg_catalog.json_agg(e.enumlabel order by e.enumsortorder) from pg_catalog.pg_enum e where e.enumtypid = t.oid))"
            " from d join pg_catalog.pg_type t on t.oid = d.oid where d.base = 0"
        )
        cache[oid] = json.loads(text)
    name, typtype, category, domain_mod, labels = cache[oid]
    mod = typmod if typmod >= 0 else domain_mod
    length = mod - 4 if category == "S" and mod is not None and mod >= 4 else None
    return name, typtype, category, length, labels or []


def _order(tables: dict[str, Table], first: str) -> list[Table]:
    """Parents before children (`first`, Supabase's users table, before all); a cycle is broken in name order."""
    done: list[str] = [first] if first in tables else []
    left = sorted((o for o in tables if o != first), key=lambda o: (tables[o].schema, tables[o].name))
    while left:
        ready = [o for o in left if all(p in done or p == o or p not in tables for _, p, _ in tables[o].keys)]
        pick = ready[0] if ready else left[0]
        done.append(pick)
        left.remove(pick)
    return [tables[o] for o in done]


def _closure(admin: pg.Connection, oids: list[str]) -> list[str]:
    """The tables named and every table their foreign keys reach."""
    seen, todo = set(oids), list(oids)
    while todo:
        rows = admin.rows(
            "select distinct confrelid::pg_catalog.text from pg_catalog.pg_constraint "
            f"where contype = 'f' and conrelid in ({', '.join(todo)})"
        )
        todo = [r[0] for r in rows if r[0] not in seen]
        seen.update(todo)
    return sorted(seen, key=int)


def _rows_of(admin: pg.Connection, table: Table, columns: list[str]) -> list[tuple]:
    """A parent's key values as text, in a fixed order, for its children to point at."""
    exprs = ", ".join(f"pg_catalog.format('%s', {quote_ident(c)})" for c in columns)
    rows = admin.rows(f"select {exprs} from {table.qualified}")
    return sorted(rows, key=lambda r: tuple("" if v is None else v for v in r))


def _variants(table: Table, n: int, parents: dict) -> list[dict[str, str | None]]:
    """Row `n` of the table, then the rows tried in its place when its checks or triggers refuse it."""
    from_keys: list[dict[str, str | None]] = []
    for shift in range(TRIES):
        values: dict[str, str | None] = {}
        for cols, parent, pcols in table.keys:
            rows = parents.get((parent, tuple(pcols)))
            if not rows:
                continue  # left to its default or null; a required key then refuses the row
            row = rows[(n + shift) % len(rows)]
            values.update(zip(cols, row))
        from_keys.append(values)
    variants = []
    for attempt in range(TRIES):
        keyed = from_keys[attempt]
        row: dict[str, str | None] = {}
        for c in table.columns:
            if c.skip:
                continue
            if c.name in keyed:
                row[c.name] = keyed[c.name]
                continue
            named = table.named.get(c.name, [])
            if n < len(named):
                row[c.name] = named[n]
            elif attempt >= 3 and named:  # a check allows only the named values: hold one of them
                row[c.name] = named[(n + attempt) % len(named)]
            elif attempt >= 2 and c.hasdefault:
                continue  # the column's own default
            elif attempt >= 4 and not c.notnull:
                row[c.name] = None
            else:
                row[c.name] = _fake(table, c, n + 1000 * attempt)
                if row[c.name] is None:
                    del row[c.name]
        variants.append(row)
    return variants


def _insert(conn: pg.Connection, table: Table, row: dict[str, str | None]) -> bool:
    if row:
        cols = ", ".join(quote_ident(c) for c in row)
        vals = ", ".join("null" if v is None else quote_literal(v) for v in row.values())
        sql = f"insert into {table.qualified} ({cols}) values ({vals})"
    else:
        sql = f"insert into {table.qualified} default values"
    try:
        conn.execute(sql)
        return True
    except pg.PgError:
        return False


# What a value read from the clock while seeding becomes, so that two runs hold the same rows.
CLOCK = {"timestamptz": "2024-02-01 00:00:00+00", "timestamp": "2024-02-01 00:00:00", "date": "2024-02-01"}


def _pin_clock(admin: pg.Connection, tables: list[Table], since: str) -> None:
    """Every date or time value a trigger or default took from the clock while seeding is set to a
    fixed one, as the superuser with triggers off, so the update itself reads no clock.

    A clock reading is told by when it falls: a timestamptz between the start of seeding and now; a
    date or a timestamp within a day of that, since its time zone is the session's. A value seeding
    chose is never one: a made-up value is from 2024, and a value a rule names is left as it is
    however near the day it falls, since the verdict rests on it. A row whose checks refuse the update
    is left as it is, and so is a column of a foreign key, which triggers off would no longer guard."""
    keyed = {(t.oid, c) for t in tables for cols, _, _ in t.keys for c in cols}
    keyed |= {(parent, c) for t in tables for _, parent, pcols in t.keys for c in pcols}
    admin.execute("set session_replication_role = replica")
    try:
        for table in tables:
            for c in table.columns:
                if c.skip or c.base not in CLOCK or (table.oid, c.name) in keyed:
                    continue
                col, base = quote_ident(c.name), f"pg_catalog.{c.base}"
                slack = "" if c.base == "timestamptz" else " interval '1 day'"
                window = (f"{col}::{base} between ({quote_literal(since)}::pg_catalog.timestamptz"
                          f"{' -' + slack if slack else ''})::{base} "
                          f"and (pg_catalog.clock_timestamp(){' +' + slack if slack else ''})::{base}")
                named = table.named.get(c.name, [])
                if named:  # a literal that is not of the type makes the update fail: nothing is pinned
                    window += (f" and {col}::{base} <> all (array["
                               + ", ".join(f"{quote_literal(v)}::{base}" for v in named) + "])")
                try:
                    admin.execute(
                        f"update {table.qualified} set {col} = {quote_literal(CLOCK[c.base])} where {window}"
                    )
                except pg.PgError:
                    pass
    finally:
        admin.execute("reset session_replication_role")


def fill(admin: pg.Connection, migrations: pg.Connection, oids: list[str], users_oid: str) -> None:
    """Fill the tables `oids` (and every table their keys reach), `users_oid` first, as `migrations`."""
    [(since,)] = admin.rows("select pg_catalog.clock_timestamp()::pg_catalog.text")
    tables = _catalog(admin, _closure(admin, sorted(set(oids) | {users_oid}, key=int)))
    parents: dict[tuple, list[tuple]] = {}
    needed = {(p, tuple(pc)) for t in tables.values() for _, p, pc in t.keys}
    for table in _order(tables, users_oid):
        count = max([MIN_ROWS] + [len(v) + 1 for v in table.named.values()])
        for n in range(count):
            for row in _variants(table, n, parents):
                if _insert(migrations, table, row):
                    break
        for parent, pcols in needed:
            if parent == table.oid:
                parents[(parent, pcols)] = _rows_of(admin, table, list(pcols))
    _pin_clock(admin, list(tables.values()), since)
