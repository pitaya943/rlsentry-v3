"""The HTTP requests of an attack, and the anon key they carry.

Each read goes to the copy's REST layer on loopback only, selects the table's own schema with
`Accept-Profile`, asks for exactly the columns `anon` may read with no filter, order or limit, and is
sent twice: with the copy's anon key and with no key. `http.client` follows no redirect; a request
gets 30 seconds.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
from dataclasses import dataclass
from urllib.parse import quote

TIMEOUT = 30.0
KEYS = ("anon key", "no key")

# The claims Supabase puts in a project's anon key; the reference, issue time and expiry are made up,
# and fixed, so two runs send the same requests.
ANON_CLAIMS = {"iss": "supabase", "ref": "rlsentrycopy000000000", "role": "anon", "iat": 1700000000, "exp": 4102444800}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def anon_key(secret: str) -> str:
    """An HS256 token signed with the copy's own secret."""
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(ANON_CLAIMS, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


@dataclass
class Answer:
    key: str                  # "anon key" or "no key"
    status: int | None        # None when no answer came
    body: bytes = b""
    location: str | None = None
    error: str | None = None  # why no answer came (a timeout, a refused connection)


def _select(columns: list[str]) -> str:
    return ",".join('"' + c.replace('"', '\\"') + '"' for c in columns)


def read(port: int, schema: str, table: str, columns: list[str], key: str | None) -> Answer:
    """One read of the table: GET with exactly `columns`, the anon key `key` or none."""
    which = KEYS[0] if key else KEYS[1]
    path = f"/{quote(table, safe='')}?select={quote(_select(columns), safe=',')}"
    headers = {"Accept": "application/json", "Accept-Profile": schema}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=TIMEOUT)
    try:
        conn.request("GET", path, headers=headers)
        response = conn.getresponse()
        return Answer(which, response.status, response.read(), response.getheader("Location"))
    except TimeoutError:
        return Answer(which, None, error=f"no answer within {TIMEOUT:.0f} s")
    except OSError as e:
        return Answer(which, None, error=f"the request failed: {e}")
    finally:
        conn.close()
