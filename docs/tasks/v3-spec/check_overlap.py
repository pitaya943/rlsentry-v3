#!/usr/bin/env python3
"""Find runs of 12 or more consecutive words shared between v3's spec and v2's (brief S-6).

Usage: python3 docs/tasks/v3-spec/check_overlap.py <v2 clone> [v3 spec dir]   (default: docs/spec)

Compares every .md file of the v3 spec folder with every docs/spec/*.md of the v2 clone (check it
out at 21ae616 first). Both sides are lowercased, stripped of markdown syntax and punctuation, and
lose the Given, When, Then or And that opens a scenario line, so the words on either side join.
Prints each shared run and exits 1, or prints that none was found and exits 0.
"""
import pathlib
import re
import subprocess
import sys

RUN = 12
OPENERS = {"given", "when", "then", "and"}


def words(text):
    text = re.sub(r"\]\([^)]*\)", "]", text)          # a link keeps its text, loses its target
    text = re.sub(r"<[^>]+>", " ", text)              # html tags
    out = []
    for line in text.lower().splitlines():
        line = re.sub(r"['’]", "", line)         # don't -> dont
        line_words = re.findall(r"[a-z0-9]+", line)   # every other mark is markdown or punctuation
        if line_words and line_words[0] in OPENERS:
            line_words = line_words[1:]
        out.extend(line_words)
    return out


def shared_runs(a, b):
    """Maximal runs of a (as word lists) of at least RUN words that also occur in b."""
    grams = {tuple(b[i:i + RUN]) for i in range(len(b) - RUN + 1)}
    hits = [i for i in range(len(a) - RUN + 1) if tuple(a[i:i + RUN]) in grams]
    runs, start, end = [], None, None
    for i in hits:
        if start is not None and i <= end - RUN + 1:
            end = i + RUN
        else:
            if start is not None:
                runs.append(a[start:end])
            start, end = i, i + RUN
    if start is not None:
        runs.append(a[start:end])
    return runs


def main(v2_clone, v3_dir):
    v2_files = sorted(pathlib.Path(v2_clone, "docs", "spec").glob("*.md"))
    v3_files = sorted(pathlib.Path(v3_dir).rglob("*.md"))
    if not v2_files or not v3_files:
        print(f"nothing to compare: {len(v3_files)} v3 files, {len(v2_files)} v2 files")
        return 2
    commit = subprocess.run(["git", "-C", v2_clone, "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip() or "unknown commit"
    print(f"v3 {v3_dir} against v2 docs/spec at {commit}")
    v2_words = {f: words(f.read_text()) for f in v2_files}
    found = 0
    for v3 in v3_files:
        mine = words(v3.read_text())
        for v2, theirs in v2_words.items():
            for run in shared_runs(mine, theirs):
                found += 1
                print(f"{v3} ~ v2 {v2.relative_to(v2_clone)}: {len(run)} words: {' '.join(run)}")
    print(f"compared {len(v3_files)} v3 files with {len(v2_files)} v2 files; "
          f"{found} shared run(s) of {RUN} or more words")
    return 1 if found else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "docs/spec"))
