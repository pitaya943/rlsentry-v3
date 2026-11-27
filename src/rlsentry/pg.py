"""A minimal PostgreSQL client: the simple query protocol over the copy's Unix socket.

rlsentry talks to its copy through this instead of `psql`, because `psql` acts on backslash
commands (`\\!`, `\\copy`, `\\o`) inside a migration file, and those run on the machine, outside
the database; the server's own protocol carries SQL only. Authentication is `trust` on a socket
in a directory only the run can reach, so no password exchange is needed.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field


class PgError(Exception):
    """An ErrorResponse from the server; `fields` holds its fields by their one-letter code."""

    def __init__(self, fields: dict[str, str]):
        self.fields = fields
        super().__init__(fields.get("M", "unknown error"))

    @property
    def code(self) -> str:
        return self.fields.get("C", "")

    @property
    def message(self) -> str:
        return self.fields.get("M", "")

    @property
    def position(self) -> int | None:
        return int(self.fields["P"]) if "P" in self.fields else None


@dataclass
class Result:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[str | None, ...]] = field(default_factory=list)


class Connection:
    def __init__(self, socket_dir: str, port: int, user: str, database: str = "postgres"):
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(f"{socket_dir}/.s.PGSQL.{port}")
        params = b"".join(
            k.encode() + b"\0" + v.encode() + b"\0"
            for k, v in (
                ("user", user),
                ("database", database),
                ("client_encoding", "UTF8"),
                ("application_name", "rlsentry"),
            )
        )
        body = struct.pack("!i", 196608) + params + b"\0"
        self._sock.sendall(struct.pack("!i", len(body) + 4) + body)
        self._buf = b""
        while True:
            kind, payload = self._read()
            if kind == b"R":
                (auth,) = struct.unpack("!i", payload[:4])
                if auth != 0:
                    raise PgError({"M": f"the copy asked for authentication method {auth}"})
            elif kind == b"E":
                raise PgError(_fields(payload))
            elif kind == b"Z":
                return

    def close(self) -> None:
        try:
            self._sock.sendall(b"X\0\0\0\4")
        except OSError:
            pass
        self._sock.close()

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def execute(self, sql: str) -> Result:
        """Run one simple query (which may hold several statements); the last result is returned."""
        body = sql.encode() + b"\0"
        self._sock.sendall(b"Q" + struct.pack("!i", len(body) + 4) + body)
        result = Result()
        error: PgError | None = None
        while True:
            kind, payload = self._read()
            if kind == b"T":
                result = Result(columns=_row_description(payload))
            elif kind == b"D":
                result.rows.append(_data_row(payload))
            elif kind == b"E":
                error = PgError(_fields(payload))
            elif kind == b"G":
                # COPY FROM STDIN: a migration cannot feed it data over this protocol.
                msg = b"COPY FROM STDIN is not supported in a migration\0"
                self._sock.sendall(b"f" + struct.pack("!i", len(msg) + 4) + msg)
            elif kind == b"Z":
                if error:
                    raise error
                return result
            # C (complete), N (notice), S (parameter), I (empty), H/d/c (copy out) are ignored.

    def rows(self, sql: str) -> list[tuple[str | None, ...]]:
        return self.execute(sql).rows

    def _read(self) -> tuple[bytes, bytes]:
        while len(self._buf) < 5:
            self._fill()
        kind = self._buf[:1]
        (length,) = struct.unpack("!i", self._buf[1:5])
        while len(self._buf) < 1 + length:
            self._fill()
        payload = self._buf[5 : 1 + length]
        self._buf = self._buf[1 + length :]
        return kind, payload

    def _fill(self) -> None:
        chunk = self._sock.recv(65536)
        if not chunk:
            raise PgError({"M": "the copy closed the connection"})
        self._buf += chunk


def _fields(payload: bytes) -> dict[str, str]:
    out = {}
    for part in payload.split(b"\0"):
        if part:
            out[chr(part[0])] = part[1:].decode("utf-8", "replace")
    return out


def _row_description(payload: bytes) -> list[str]:
    (n,) = struct.unpack("!h", payload[:2])
    pos, names = 2, []
    for _ in range(n):
        end = payload.index(b"\0", pos)
        names.append(payload[pos:end].decode())
        pos = end + 1 + 18
    return names


def _data_row(payload: bytes) -> tuple[str | None, ...]:
    (n,) = struct.unpack("!h", payload[:2])
    pos, values = 2, []
    for _ in range(n):
        (length,) = struct.unpack("!i", payload[pos : pos + 4])
        pos += 4
        if length == -1:
            values.append(None)
        else:
            values.append(payload[pos : pos + length].decode("utf-8", "replace"))
            pos += length
    return tuple(values)


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
