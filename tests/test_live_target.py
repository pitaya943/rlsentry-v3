"""S-5 (live targets): --target is refused before any connection or name lookup."""

import socket
import threading

from conftest import assert_no_copy_left, records, rlsentry, write
from rlsentry import cli


def test_a_live_target_is_refused_and_the_watched_address_gets_nothing(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.2)
    port = listener.getsockname()[1]
    arrived = []
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            try:
                arrived.append(listener.accept())
            except socket.timeout:
                pass

    watcher = threading.Thread(target=watch)
    watcher.start()
    before = records()
    folder = write(tmp_path / "p", {"001.sql": "create table t (id int);"})
    try:
        done = rlsentry("--target", f"http://127.0.0.1:{port}", "--", folder)
        bare = rlsentry("--target", f"http://127.0.0.1:{port}")
    finally:
        stop.set()
        watcher.join()
        listener.close()
    for d in (done, bare):
        assert d.returncode == 2
        assert "live targets are not available yet" in d.stderr
        assert "copy built" not in d.stdout
    assert arrived == []
    assert records() == before
    assert_no_copy_left()


def test_a_live_target_makes_no_name_lookup(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: calls.append(("getaddrinfo", a)))
    monkeypatch.setattr(socket, "gethostbyname", lambda *a, **k: calls.append(("gethostbyname", a)))
    monkeypatch.setattr(socket.socket, "connect", lambda self, *a: calls.append(("connect", a)))
    folder = write(tmp_path / "p", {"001.sql": "create table t (id int);"})
    code = cli.main(["--target", "https://watched-project.supabase.co", str(folder)])
    assert code == 2
    assert calls == []
    assert "live targets are not available yet" in capsys.readouterr().err
