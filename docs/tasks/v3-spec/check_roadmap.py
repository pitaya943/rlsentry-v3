#!/usr/bin/env python3
"""Check a roadmap by the rules the shilaycow harness's state.py applies (brief S-5).

Usage: python3 docs/tasks/v3-spec/check_roadmap.py [path]   (default: docs/roadmap.json)

Prints each problem and exits 1, or prints the first open task and what anon-read depends on
and exits 0.
"""
import json
import sys

FIELDS = {"slug": str, "goal": str, "depends_on": list, "pr": (str, type(None)), "done": bool}


def problems(tasks):
    found = []
    for n, task in enumerate(tasks, 1):
        if not isinstance(task, dict):
            found.append(f"entry {n} is not an object")
            continue
        for field, kind in FIELDS.items():
            if not isinstance(task.get(field), kind):
                found.append(f"entry {n} needs '{field}'")
    if found:
        return found
    deps = {t["slug"]: t["depends_on"] for t in tasks}
    done = {t["slug"] for t in tasks if t["done"]}
    if len(deps) != len(tasks):
        found.append("a slug is listed twice")
    for t in tasks:
        unknown = [d for d in t["depends_on"] if d not in deps]
        if unknown:
            found.append(f"'{t['slug']}' depends on unknown {', '.join(unknown)}")
        if t["done"] and not t["pr"]:
            found.append(f"'{t['slug']}' is done but names no pull request")
        if t["done"]:
            open_deps = [d for d in t["depends_on"] if d in deps and d not in done]
            if open_deps:
                found.append(f"'{t['slug']}' is done but depends on {', '.join(open_deps)}, not done")

    def loop_from(slug, path):
        if slug in path:
            return path[path.index(slug):] + [slug]
        for d in deps.get(slug, []):
            if (loop := loop_from(d, path + [slug])):
                return loop
        return None

    loop = next((l for s in deps if (l := loop_from(s, []))), None)
    if loop:
        found.append(f"the dependencies loop: {' -> '.join(loop)}")
    return found


def main(path):
    try:
        with open(path) as f:
            tasks = json.load(f)["tasks"]
        assert isinstance(tasks, list)
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as e:
        print(f"{path}: not an object with a list 'tasks' ({e})")
        return 1
    found = problems(tasks)
    if found:
        for p in found:
            print(f"{path}: {p}")
        return 1
    done = {t["slug"] for t in tasks if t["done"]}
    first = next((t["slug"] for t in tasks if not t["done"] and set(t["depends_on"]) <= done), None)
    anon_read = next((t for t in tasks if t["slug"] == "anon-read"), None)
    print(f"{path}: no problems")
    print(f"first open task: {first}")
    print(f"anon-read depends on: {', '.join(anon_read['depends_on']) if anon_read else '(no anon-read task)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "docs/roadmap.json"))
