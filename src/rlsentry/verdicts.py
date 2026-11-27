"""Judging one read from its two answers and the direct view (this task's half: exposed, or none).

| Answer | Result |
|---|---|
| a redirect (`3xx`) | a stop, at once |
| `200` with at least one row, each matching a row the direct view holds | that request got rows |
| `200` with a row the direct view does not hold | a stop, at once |
| anything else | that request did not show the read exposed |
"""

from __future__ import annotations

import json

from .attack import Answer
from .report import Attempt, Basis, Outcome
from .stops import Stop, printable


def _parse(body: bytes | str):
    # Numbers kept as their text, so the answer and the direct view are compared exactly.
    return json.loads(body, parse_float=str, parse_int=str)


def _key(row: dict) -> str:
    return json.dumps(row, sort_keys=True)


def _exact(direct_row: dict[str, str]) -> dict:
    return {c: _parse(v) for c, v in direct_row.items()}


def judge_answer(name: str, answer: Answer, direct: list[dict]) -> tuple[Attempt, set[int]]:
    """One answer against the rows the direct view saw just before it was sent: the attempt, and
    which of those rows it got. Raises `Stop` for a redirect or a row the table does not hold."""
    attempt = Attempt(answer.key, answer.status)
    if answer.status is None:
        attempt.reason = answer.error
        return attempt, set()
    if 300 <= answer.status < 400:
        to = f" to {printable(answer.location)!r}" if answer.location else ""
        raise Stop(
            f"the read of {name} with the {answer.key} was answered with a redirect (status "
            f"{answer.status}{to}); rlsentry follows no redirect, and an answer that sends the visitor "
            "elsewhere is not the copy's",
            table=name,
        )
    try:
        body = _parse(answer.body)
    except ValueError:
        body = None
    if answer.status != 200:
        if isinstance(body, dict) and isinstance(body.get("code"), str):
            attempt.error_code = body["code"]
        attempt.reason = "the REST layer did not answer with rows"
        return attempt, set()
    if not isinstance(body, list) or not all(isinstance(r, dict) for r in body):
        attempt.reason = "the answer was not a list of rows"
        return attempt, set()
    if not body:
        attempt.reason = "the answer held no row"
        return attempt, set()
    index = {_key(_exact(row)): i for i, row in enumerate(direct)}
    got = set()
    for row in body:
        i = index.get(_key(row))
        if i is None:
            raise Stop(
                f"the read of {name} with the {answer.key} answered with a row the table does not hold "
                f"({printable(json.dumps(row, ensure_ascii=False))}); code in the migrations shaped the "
                "answer, so it is no evidence",
                table=name,
            )
        got.add(i)
    attempt.rows = len(body)
    return attempt, got


def judge(schema: str, table: str, judged: list[tuple[Attempt, set[int], list[dict[str, str]]]],
          columns: list[str] | None) -> Outcome:
    """Exposed when either request got rows the table holds; otherwise no verdict.
    `judged` holds, per request, its attempt, the rows it got and the direct view it was judged on
    (each value as JSON text)."""
    outcome = Outcome(schema, table, attempts=[a for a, _, _ in judged])
    with_rows = [(a, got, direct) for a, got, direct in judged if got]
    if not with_rows:
        return outcome
    rows = {}
    for _, got, direct in with_rows:
        for i in got:
            rows[_key(direct[i])] = direct[i]
    held = max(len(direct) for _, _, direct in with_rows)
    outcome.verdict = "exposed"
    outcome.basis = Basis([a.key for a, _, _ in with_rows], len(rows), held, columns)
    outcome.evidence = {c: json.loads(v) for c, v in rows[min(rows)].items()}
    return outcome
