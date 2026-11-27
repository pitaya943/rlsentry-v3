"""S-5 (seeding, grants, two runs at once) and S-6: the copy holds fake rows before the attack."""

import json

from conftest import assert_no_copy_left, outcomes, run, start_rlsentry, write
from rlsentry import inputs, versions
from rlsentry.copy import Copy

RULES = """
create table authors (id uuid primary key, name text not null);
create table posts (
  id int primary key,
  author uuid not null references authors,
  status text not null check (status in ('draft', 'published', 'hidden')),
  title text check (char_length(title) > 3)
);
alter table posts enable row level security;
create policy "published only" on posts for select using (status = 'published');
"""


def seeded(tmp_path, files, queries):
    project = inputs.resolve(str(write(tmp_path, files)))
    programs, found = versions.check()
    with Copy(project, programs, found) as copy:
        with copy.connect() as admin:
            return [admin.rows(q) for q in queries]


ROWS = ["select id::text, name from public.authors order by 1",
        "select id::text, author::text, status, title from public.posts order by 1"]


def test_every_table_is_seeded_with_the_values_its_rules_name(tmp_path):
    authors, posts = seeded(tmp_path / "one", {"001.sql": RULES}, ROWS)
    assert len(authors) >= 2 and len(posts) >= 2
    assert all(name.startswith("rlsentry-fake-authors-") for _, name in authors)
    assert {author for _, author, _, _ in posts} <= {id for id, _ in authors}, "every child row points at a parent"
    statuses = [status for _, _, status, _ in posts]
    assert "published" in statuses and any(s != "published" for s in statuses)
    assert set(statuses) == {"draft", "published", "hidden"}, "each value the check names is held"
    # The same migrations give the same rows.
    assert seeded(tmp_path / "two", {"001.sql": RULES}, ROWS) == [authors, posts]
    assert_no_copy_left()


def test_a_table_created_without_grants_is_read_as_on_supabase(tmp_path):
    # Supabase's default privileges grant every new table in public to anon.
    done, found = run(tmp_path, {"001.sql": "create table plain (id int primary key, v text);"})
    assert done.returncode == 1, done.stdout + done.stderr
    assert found["public.plain"]["verdict"] == "exposed"


def test_two_runs_at_once_do_not_meet(tmp_path):
    one = start_rlsentry(write(tmp_path / "one", {"001.sql": "create table alpha (id int primary key);"}))
    two = start_rlsentry(write(tmp_path / "two", {
        "001.sql": "create table beta (id int primary key);\nalter table beta enable row level security;"}))
    out_one, err_one = one.communicate(timeout=180)
    out_two, err_two = two.communicate(timeout=180)
    assert one.returncode == 1, err_one
    assert two.returncode == 2, err_two
    assert list(outcomes(out_one)) == ["public.alpha"] and outcomes(out_one)["public.alpha"]["verdict"] == "exposed"
    assert list(outcomes(out_two)) == ["public.beta"] and outcomes(out_two)["public.beta"]["verdict"] is None
    assert "beta" not in out_one + err_one and "alpha" not in out_two + err_two
    assert_no_copy_left()


PROFILES = """
create table public.profiles (
  id uuid not null references auth.users on delete cascade primary key,
  username text unique,
  updated_at timestamptz default now()
);
alter table public.profiles enable row level security;
create policy "Public profiles are viewable by everyone." on profiles for select using (true);
create table public.memberships (
  user_id uuid not null references auth.users (id),
  team text not null,
  primary key (user_id, team)
);
"""


def test_tables_that_reference_supabases_users_are_seeded(tmp_path):
    users, profiles, memberships = seeded(tmp_path / "copy", {"001.sql": PROFILES}, [
        "select id::text, email from auth.users order by 1",
        "select id::text from public.profiles order by 1",
        "select user_id::text from public.memberships order by 1",
    ])
    ids = {id for id, _ in users}
    assert len(users) >= 2 and all(email.startswith("rlsentry-fake-users-") for _, email in users)
    assert len(profiles) >= 2 and {id for (id,) in profiles} <= ids
    assert len(memberships) >= 2 and {id for (id,) in memberships} <= ids

    done, found = run(tmp_path, {"001.sql": PROFILES})
    assert done.returncode == 1, done.stdout + done.stderr
    assert found["public.profiles"]["verdict"] == "exposed"
    assert found["public.memberships"]["verdict"] == "exposed"
    assert found["public.profiles"]["evidence"]["id"] in ids
    assert json.dumps(found).count("rlsentry-fake") >= 1
