"""S-8: the lab. Every bundled schema is run by name and compared with its statement, and between
them the schemas show a read exposed for each reason the verdicts area gives."""

import json
from importlib import resources

import pytest

from conftest import assert_no_copy_left, records, rlsentry

LAB = resources.files("rlsentry") / "lab"

# The reasons the verdicts area gives for an exposed read, in the words a statement uses.
REASONS = {
    "row-level security off",
    "a policy admitting everyone",
    "a policy admitting some rows",
    "a grant on some columns",
    "a request without a key",
}


def names() -> list[str]:
    return sorted(p.name for p in LAB.iterdir() if p.joinpath("statement.json").is_file()) if LAB.is_dir() else []


def statement(name: str) -> dict:
    return json.loads(LAB.joinpath(name, "statement.json").read_text())


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Each lab schema run once by name: its exit code, stderr and the answers its JSON report gives."""
    found = {}
    for name in names():
        report = tmp_path_factory.mktemp(name) / "report.json"
        done = rlsentry("lab", name, "--json", report)
        assert_no_copy_left()
        results = json.loads(report.read_text())["results"] if report.exists() else []
        found[name] = {"exit_code": done.returncode, "stderr": done.stderr, "stdout": done.stdout,
                       "reads": [_answer(r) for r in results]}
    return found


def _answer(r: dict) -> dict:
    """What a statement says of a read, taken from the JSON report."""
    b = r["basis"]
    return {
        "table": f"{r['schema']}.{r['table']}",
        "verdict": r["verdict"],
        "requests": b["requests"] if b else None,
        "rows": None if not b else ("all" if b["rows_read"] == b["rows_held"] else "some"),
        "columns": b["columns"] if b else None,
    }


def _expected(read: dict) -> dict:
    return {k: read.get(k) for k in ("table", "verdict", "requests", "rows", "columns")}


def test_the_list_names_each_schema_with_its_flaw_and_builds_nothing():
    before = records()
    done = rlsentry("lab")
    assert done.returncode == 0, done.stderr
    listed = [line.split(None, 1) for line in done.stdout.splitlines()]
    assert [name for name, _ in listed] == names()
    for name, flaw in listed:
        assert flaw == statement(name)["flaw"], name
        assert "\n" not in statement(name)["flaw"]
    assert "copy built" not in done.stdout
    assert records() == before
    assert_no_copy_left()


def test_an_unknown_lab_schema_stops_naming_the_list():
    done = rlsentry("lab", "no-such-schema")
    assert done.returncode == 2
    assert "no lab schema named no-such-schema" in done.stderr
    assert "rlsentry lab" in done.stderr
    assert_no_copy_left()


@pytest.mark.parametrize("name", names())
def test_each_lab_schema_gives_what_its_statement_says(name, runs):
    st, got = statement(name), runs[name]
    assert got["exit_code"] == st["exit_code"], got["stdout"] + got["stderr"]
    assert got["reads"] == [_expected(r) for r in st["reads"]], got["stdout"] + got["stderr"]
    if st["stop"] is None:
        assert "stopped" not in got["stderr"], got["stderr"]
    else:
        assert st["stop"] in got["stderr"], got["stderr"]


def test_between_them_the_schemas_show_a_read_exposed_for_each_reason(runs):
    assert set(runs) == set(names())
    exposed = {}
    for name in names():
        for read in statement(name)["reads"]:
            assert read["verdict"] in ("exposed", None), f"{name}: the lab of this task expects no protected read"
            if read["verdict"] == "exposed":
                assert read["because"] in REASONS, (name, read["because"])
                exposed.setdefault(read["because"], []).append(read)
    assert set(exposed) == REASONS
    # Each reason is checked against what the run itself showed, where the answer can tell them apart.
    answered = {(n, a["table"]): a for n in names() for a in runs[n]["reads"]}
    for name in names():
        for read in statement(name)["reads"]:
            if read["verdict"] != "exposed":
                continue
            a = answered[(name, read["table"])]
            assert a["verdict"] == "exposed", (name, read["table"])
            if read["because"] == "a request without a key":
                assert a["requests"] == ["no key"], name
            else:
                assert a["requests"] == ["anon key", "no key"], name
            assert (a["columns"] is not None) == (read["because"] == "a grant on some columns"), name
            assert (a["rows"] == "some") == (read["because"] == "a policy admitting some rows"), name
    stops = [n for n in names() if statement(n)["stop"] is not None]
    assert stops, "at least one lab schema shows a stop"
    for n in stops:
        assert runs[n]["exit_code"] == 2 and statement(n)["stop"] in runs[n]["stderr"], n
