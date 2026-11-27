"""S-1 (verdicts): when a read is exposed, what its basis and evidence say, the reads that get no
verdict, and the answers that stop the run at once. Every test reads a real copy through PostgREST."""

import socket
import threading

from conftest import run


def test_a_table_with_row_level_security_off_is_exposed(tmp_path):
    done, found = run(tmp_path, {"001.sql": "create table notes (id int primary key, body text);"})
    assert done.returncode == 1, done.stdout + done.stderr
    notes = found["public.notes"]
    assert notes["verdict"] == "exposed"
    assert "rows came back with the anon key and without a key; 2 of the table's 2 rows" in notes["text"]
    assert set(notes["evidence"]) == {"id", "body"}
    assert notes["evidence"]["body"].startswith("rlsentry-fake-notes-")


def test_a_policy_that_lets_everyone_read_is_exposed(tmp_path):
    done, found = run(tmp_path, {"001.sql": (
        "create table posts (id int primary key, title text);\n"
        "alter table posts enable row level security;\n"
        "create policy \"anyone\" on posts for select to anon using (true);"
    )})
    assert done.returncode == 1, done.stdout + done.stderr
    assert found["public.posts"]["verdict"] == "exposed"
    assert found["public.posts"]["evidence"]["title"].startswith("rlsentry-fake-posts-")


def test_a_policy_that_lets_some_rows_through_is_exposed_with_their_count(tmp_path):
    # Seeding holds one row per value the policy names and one holding neither: three rows.
    done, found = run(tmp_path, {"001.sql": (
        "create table posts (id int primary key, status text not null, title text);\n"
        "alter table posts enable row level security;\n"
        "create policy \"published\" on posts for select using (status in ('published', 'featured'));"
    )})
    assert done.returncode == 1, done.stdout + done.stderr
    posts = found["public.posts"]
    assert posts["verdict"] == "exposed"
    assert "2 of the table's 3 rows" in posts["text"]
    assert posts["evidence"]["status"] in ("published", "featured")


def test_a_read_grant_on_some_columns_is_exposed_on_those_columns_only(tmp_path):
    done, found = run(tmp_path, {"001.sql": (
        "create table people (id int primary key, name text, secret text);\n"
        "revoke all on people from anon;\n"
        "grant select (id, name) on people to anon;"
    )})
    assert done.returncode == 1, done.stdout + done.stderr
    people = found["public.people"]
    assert people["verdict"] == "exposed"
    assert "columns read: id, name" in people["text"]
    assert set(people["evidence"]) == {"id", "name"}


def test_a_table_that_lets_in_only_requests_without_a_key_is_exposed(tmp_path):
    done, found = run(tmp_path, {"001.sql": (
        "create table drafts (id int primary key);\n"
        "alter table drafts enable row level security;\n"
        "create policy \"no issuer\" on drafts for select using ((auth.jwt() ->> 'iss') is null);"
    )})
    assert done.returncode == 1, done.stdout + done.stderr
    drafts = found["public.drafts"]
    assert drafts["verdict"] == "exposed"
    assert drafts["text"].startswith("rows came back without a key;")
    assert "with the anon key" not in drafts["text"]


# A column whose domain PostgREST renders through a cast of the migrations' own ("domain
# representation"): the answer holds a value the table does not hold.
SHAPED = """
create domain public.shown_text as text;
create function public.shown(public.shown_text) returns json language sql immutable
  as $$ select to_json('not in the table'::text) $$;
create cast (public.shown_text as json) with function public.shown(public.shown_text) as implicit;
create table b_shaped (id int primary key, v public.shown_text);
"""


def test_an_answer_holding_rows_the_table_does_not_hold_stops_the_run_at_once(tmp_path):
    done, found = run(tmp_path, {
        "001.sql": "create table a_open (id int primary key);",
        "002.sql": SHAPED,
        "003.sql": "create table c_later (id int primary key);",
    })
    assert done.returncode == 2, done.stdout + done.stderr
    assert "b_shaped" not in found
    assert "the read of public.b_shaped with the anon key answered with a row the table does not hold" in done.stderr
    assert "c_later" not in found, "the run stops at once: no table after it is attacked"
    # A run that finds something and then stops exits 2, and still names what was exposed.
    assert found["public.a_open"]["verdict"] == "exposed"
    assert "exposed before the stop: public.a_open" in done.stderr


class Watched:
    """An address nothing should reach: it counts every connection made to it."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.sock.settimeout(0.1)
        self.port = self.sock.getsockname()[1]
        self.connections = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def _watch(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except OSError:
                continue
            self.connections += 1
            conn.close()

    def close(self):
        self._stop.set()
        self._thread.join()
        self.sock.close()


def test_a_redirect_is_never_followed_and_stops_the_run(tmp_path):
    watched = Watched()
    try:
        done, found = run(tmp_path, {"001.sql": f"""
create function public.send_away() returns boolean language plpgsql as $$
begin
  perform set_config('response.status', '302', true);
  perform set_config('response.headers', '[{{"Location": "http://127.0.0.1:{watched.port}/stolen"}}]', true);
  return true;
end $$;
create table a_moved (id int primary key);
alter table a_moved enable row level security;
create policy "away" on a_moved for select using (public.send_away());
create table b_later (id int primary key);
"""})
    finally:
        watched.close()
    assert done.returncode == 2, done.stdout + done.stderr
    assert "the read of public.a_moved with the anon key was answered with a redirect (status 302" in done.stderr
    assert watched.connections == 0
    assert "public.a_moved" not in found and "public.b_later" not in found


NO_VERDICT = {
    "001.sql": "create table a_open (id int primary key, body text);",
    # row-level security on and no policy: an empty 200
    "002.sql": "create table b_empty (id int primary key);\nalter table b_empty enable row level security;",
    # a policy reading a table anon may not read: a permission error (401, 42501)
    "003.sql": "create schema private;\ncreate table private.hidden_list (id int);\n"
               "create table c_permission (id int primary key);\nalter table c_permission enable row level security;\n"
               "create policy \"listed\" on c_permission for select using (exists (select 1 from private.hidden_list));",
    # a policy whose function answers 403
    "004.sql": "create function public.forbid() returns boolean language plpgsql as $$ begin "
               "raise sqlstate 'PT403' using message = 'go away'; end $$;\n"
               "create table d_forbidden (id int primary key);\nalter table d_forbidden enable row level security;\n"
               "create policy \"forbid\" on d_forbidden for select using (public.forbid());",
    # no column anon may read
    "005.sql": "create table e_ungranted (id int primary key);\nrevoke all on e_ungranted from anon;",
    # no column at all
    "006.sql": "create table f_no_columns ();",
}


def test_reads_not_shown_exposed_get_no_verdict_and_the_run_stops_after_every_table(tmp_path):
    done, found = run(tmp_path, NO_VERDICT)
    assert done.returncode == 2, done.stdout + done.stderr
    assert list(found) == ["public.a_open", "public.b_empty", "public.c_permission", "public.d_forbidden",
                           "public.e_ungranted", "public.f_no_columns"], "every table is read, in name order"
    assert found["public.a_open"]["verdict"] == "exposed"
    for name in list(found)[1:]:
        assert found[name]["verdict"] is None, name
    assert found["public.b_empty"]["text"] == (
        "anon key: status 200, the answer held no row; no key: status 200, the answer held no row")
    assert "anon key: status 401, error code 42501" in found["public.c_permission"]["text"]
    assert "no key: status 401, error code 42501" in found["public.c_permission"]["text"]
    assert "anon key: status 403" in found["public.d_forbidden"]["text"]
    assert found["public.e_ungranted"]["text"] == "no column it may read; no request sent"
    assert found["public.f_no_columns"]["text"] == "the table has no columns; no request sent"
    for name in list(found)[1:]:
        assert name in done.stderr
    assert "protected verdicts come with anon-read-protected" in done.stderr
    assert "exposed before the stop: public.a_open" in done.stderr


def test_a_read_that_gets_no_answer_in_30_seconds_gets_no_verdict_and_the_rest_are_read(tmp_path):
    done, found = run(tmp_path, {"001.sql": (
        "create table a_slow (id int primary key);\n"
        "alter table a_slow enable row level security;\n"
        "create policy \"slow\" on a_slow for select using ((select pg_sleep(35)) is not null);\n"
        "create table b_open (id int primary key);"
    )})
    assert done.returncode == 2, done.stdout + done.stderr
    assert found["public.a_slow"]["verdict"] is None
    assert found["public.a_slow"]["text"] == "anon key: no answer within 30 s; no key: no answer within 30 s"
    assert found["public.b_open"]["verdict"] == "exposed"
    assert "public.a_slow" in done.stderr
