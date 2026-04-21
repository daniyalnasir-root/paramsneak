# paramsneak

Mass-assignment probe that hands you a working PoC curl per stuck field.

You captured a `POST /api/users` from Burp. You suspect the API quietly accepts extra keys it shouldn't. `paramsneak` re-sends the create one extra field at a time, watches what the response (or a GET-back) echoes, and prints a copy-paste curl for each field that the server happily accepted. The output is the proof, not a report about the proof.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: active](https://img.shields.io/badge/status-active-brightgreen.svg)](#)

## Overview

Mass assignment is the bug where the create endpoint takes a JSON or form body and lets the developer's ORM bind every key into the model — including ones the request schema never advertised. `role`, `is_admin`, `balance`, `tenant_id`, `verified`. Most APIs are fine. The ones that aren't quietly grant admin to anyone who knows to send the field.

The drudgery is in re-sending the same create request a dozen times with a different extra each time, scraping the response to see what stuck, and writing it up cleanly. `paramsneak` does all three. It parses the curl as captured, walks a built-in list of common privilege/state keys (or your own), sends each variation, checks for echo in the create response and optionally re-fetches the resource to confirm the field stuck server-side, then emits a numbered list of working PoC curls at the end.

The output is two things stacked: a per-attempt log (`▷` per probe, `└─` for what stuck and where) and a final `>>` block of ready-to-paste curls. Pipe the curls straight into your report.

## Features

- Parses captured curl with `-H`, `-X`, `-d/--data-raw`, `--json`, supports both form and JSON bodies
- Built-in dictionary of 16 high-signal mass-assignment keys (`role=admin`, `is_staff=true`, `balance=99999`, `tenant_id=1`, etc.); override with `--fields k1=v1,k2=v2`
- Auto-extracts the new resource id with a configurable regex, then verifies stuck fields server-side via the optional `--get-back` template
- Emits one copy-paste curl per stuck field, body merged correctly for both JSON and form encodings
- Conservative stuck-detection: requires both the key and value to appear in proximity; avoids the false positive where the value alone happened to live in some other field

## Installation

```bash
git clone https://github.com/daniyalnasir-root/paramsneak.git
cd paramsneak
python3 cli.py -h
```

No pip install. Standard library only.

## Usage

```bash
# JSON body, default field dictionary
python3 cli.py \
    --curl "curl -X POST https://app.example.com/api/users \
            -H 'Content-Type: application/json' \
            -H 'Cookie: sess=xyz' \
            --data-raw '{\"name\":\"alice\",\"email\":\"alice@example.com\"}'"

# Form body, custom field list, GET-back to confirm role stuck server-side
python3 cli.py \
    --curl @./create.curl \
    --fields "role=admin,plan=enterprise,quota=999999" \
    --get-back "https://app.example.com/api/users/{id}" \
    --id-pattern '"user_id"\s*:\s*"?([^",}\s]+)'
```

## Command Line Options

| Flag | Required | Description |
|------|----------|-------------|
| `--curl` | yes | Curl command string, or `@path/to/file` |
| `--fields` | no | Comma-separated `key=value` list (default: built-in privilege/state set) |
| `--get-back` | no | URL template with `{id}` for server-side stuck-confirmation |
| `--id-pattern` | no | Regex with one capture group, applied to the create response (default `"id":"..."`) |
| `--timeout` | no | Per-request timeout in seconds (default 10) |

## Output Example

```
$ python3 cli.py --curl "curl -X POST https://httpbin.org/anything \
                         -H 'Content-Type: application/json' \
                         --data-raw '{\"name\":\"alice\"}'" \
                 --fields "role=admin,is_admin=true,balance=99999"

target: POST https://httpbin.org/anything
body kind: json
fields under test: 3

► sending baseline create...
  └─ 200  540B  464ms
  └─ no id extracted

▷ role=admin       →  200  581B  362ms
  └─ echoed in CREATE response
▷ is_admin=true    →  200  581B  356ms
  └─ echoed in CREATE response
▷ balance=99999    →  200  581B  401ms
  └─ echoed in CREATE response

>> PoC curls for 3 stuck field(s)
............................................................
>> role=admin  (create)
   curl -X POST https://httpbin.org/anything ... -d '{"name":"alice","role":"admin"}'
```

Full unabridged output of two runs lives in [`examples/`](examples/).

## Legal Disclaimer

This tool is for authorized security testing and educational use only.
Run it only against systems you own or have explicit written permission to test.
The author accepts no liability for misuse. Unauthorized use may violate
local, state, or federal law.

## Author

**Daniyal Nasir** &nbsp;|&nbsp; Penetration Tester &nbsp;|&nbsp; VAPT Consultant &nbsp;|&nbsp; Bug Bounty Hunter &nbsp;|&nbsp; Doha, Qatar

Ten years of hands-on offensive security work; OSCP, LPT, CPENT, CEH, CISA, CISM, and CASP+ certified.

LinkedIn: https://www.linkedin.com/in/daniyalnasir
Website:  https://www.daniyalnasir.com

## License

MIT, see [LICENSE](LICENSE).
