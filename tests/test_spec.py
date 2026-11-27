"""The spec defines each term once: under Terms in docs/spec/index.md, and nowhere else."""

from __future__ import annotations

import re
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "docs" / "spec"

TERM = re.compile(r"\*\*(.+?)\*\*:")
DEFINITION = re.compile(r"^\s*- \*\*(.+?)\*\*:")


def terms(index: Path) -> set[str]:
    """Every term the Terms section of the index defines, as `**term**:`."""
    found, inside = set(), False
    for line in index.read_text().splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Terms"
        elif inside:
            found.update(t.lower() for t in TERM.findall(line))
    return found


def restatements(spec: Path) -> list[str]:
    """Each line `- **term**: ...` outside the index that defines one of the index's terms again."""
    defined = terms(spec / "index.md")
    problems = []
    for path in sorted(spec.rglob("*.md")):
        if path == spec / "index.md":
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            match = DEFINITION.match(line)
            if match and match.group(1).lower() in defined:
                problems.append(f"{path.relative_to(spec.parent.parent)}:{number}: defines the term "
                                f"'{match.group(1)}', which docs/spec/index.md defines under Terms")
    return problems


def test_no_term_of_the_index_is_defined_again_in_another_file_of_the_spec():
    assert terms(SPEC / "index.md"), "found no term under Terms in docs/spec/index.md"
    problems = restatements(SPEC)
    assert not problems, "\n".join(problems)


def test_a_term_defined_again_elsewhere_is_named_with_its_file(tmp_path):
    spec = tmp_path / "docs" / "spec"
    spec.mkdir(parents=True)
    (spec / "index.md").write_text("# x\n\n## Terms\n\n- **the copy**: one meaning.\n\n## Other\n\n"
                                   "- **elsewhere**: not a term.\n")
    (spec / "area.md").write_text("# area\n\n- **The copy**: another meaning.\n- **elsewhere**: fine.\n"
                                  "- **The copy** is named here without being defined.\n")
    assert restatements(spec) == [
        "docs/spec/area.md:3: defines the term 'The copy', which docs/spec/index.md defines under Terms"
    ]
