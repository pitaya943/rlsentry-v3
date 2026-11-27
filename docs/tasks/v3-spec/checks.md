# v3-spec: the two checks

Both run from the repository root with Python 3.10+ and nothing else installed (brief, How to try
it, steps 4 and 5).

## Roadmap (S-5)

    python3 docs/tasks/v3-spec/check_roadmap.py            # or give another roadmap file's path

It applies `state.py`'s rules (every task has `slug`, `goal`, `depends_on`, `pr`, `done`; no slug
twice; no unknown dependency; no loop; a done task has a `pr`) and the brief's one more (no done
task depends on one not done). On a problem it prints each, prefixed with the roadmap's path, and
exits 1. Otherwise it exits 0 after three lines: `<path>: no problems`, `first open task: <slug>`
with the first task not done whose dependencies are done, and `anon-read depends on: <slugs>` with
that task's `depends_on`, or `(no anon-read task)` when the roadmap has no task of that slug. Both
slugs are read from the roadmap at the time it runs, so they change as the roadmap does.

## Overlap with v2 (S-6)

    git clone https://github.com/pitaya943/rlsentry-v2 /tmp/rlsentry-v2
    git -C /tmp/rlsentry-v2 checkout 21ae616
    python3 docs/tasks/v3-spec/check_overlap.py /tmp/rlsentry-v2 > docs/tasks/v3-spec/overlap.txt

It compares every `.md` of `docs/spec/` with v2's `docs/spec/*.md` after lowercasing, dropping
markdown syntax and punctuation, and dropping a scenario line's opening Given, When, Then or And.
It prints each shared run of 12 or more words and exits 1, or exits 0 when there is none. Its
saved output on this branch is [`overlap.txt`](overlap.txt).
