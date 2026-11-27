"""Cutting a migration file into the statements it holds, as the Supabase CLI does before running them.

Running statement by statement lets a failure name the exact statement, which the server's own
error does not always point at (a refused `COPY ... TO '<file>'` carries no position). The cut
honours quotes, dollar quotes, comments and `BEGIN ATOMIC ... END` bodies. If it ever cut in the
wrong place, the piece would fail in the copy and the run would stop: a wrong cut never builds a
database the migrations did not describe.
"""

from __future__ import annotations

import re

_TAG = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")


def _ident_char(c: str) -> bool:
    return c.isalnum() or c in "_$"


def split(text: str) -> list[tuple[int, str]]:
    """Return (line where the statement starts, statement text without its `;`), skipping empty ones."""
    out: list[tuple[int, str]] = []
    i, n, start = 0, len(text), 0
    words: list[str] = []  # last two words outside quotes, lower case
    atomic = 0  # depth inside BEGIN ATOMIC ... END
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "-" and nxt == "-":
            j = text.find("\n", i)
            i = n if j < 0 else j + 1
        elif c == "/" and nxt == "*":
            depth, i = 1, i + 2
            while i < n and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
        elif c == "'":
            backslash = i > 0 and text[i - 1] in "eE" and (i < 2 or not _ident_char(text[i - 2]))
            i += 1
            while i < n:
                if backslash and text[i] == "\\":
                    i += 2
                elif text[i] == "'":
                    if text.startswith("''", i):
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
        elif c == '"':
            i += 1
            while i < n:
                if text.startswith('""', i):
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
        elif c == "$" and (i == 0 or not _ident_char(text[i - 1])) and (m := _TAG.match(text, i)):
            tag = m.group(0)
            j = text.find(tag, m.end())
            i = n if j < 0 else j + len(tag)
        elif c.isalpha() or c == "_":
            j = i
            while j < n and _ident_char(text[j]):
                j += 1
            word = text[i:j].lower()
            if atomic:
                if word == "case":
                    atomic += 1
                elif word == "end":
                    atomic -= 1
            elif word == "atomic" and words[-1:] == ["begin"]:
                atomic = 1
            words = (words + [word])[-2:]
            i = j
        elif c == ";" and not atomic:
            _add(out, text, start, i)
            start, i, words = i + 1, i + 1, []
        else:
            i += 1
    _add(out, text, start, n)
    return out


def _add(out: list[tuple[int, str]], text: str, start: int, end: int) -> None:
    """Keep a statement, its leading comments dropped, with the line its code starts on."""
    i = start
    while i < end:
        if text[i].isspace():
            i += 1
        elif text.startswith("--", i):
            j = text.find("\n", i, end)
            i = end if j < 0 else j + 1
        elif text.startswith("/*", i):
            depth, i = 1, i + 2
            while i < end and depth:
                if text.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif text.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
        else:
            break
    if i < end:
        out.append((text.count("\n", 0, i) + 1, text[i:end].strip()))
