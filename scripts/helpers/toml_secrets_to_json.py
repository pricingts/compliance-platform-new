"""Convert a Streamlit-Cloud TOML credentials section into a JSON string.

Streamlit Cloud stores ``google_sheets_credentials`` as a TOML ``[section]``
whose keys map 1:1 to the service-account JSON fields. The Gmail smoke
test expects the same data as a single-line JSON string in the
``GOOGLE_APPLICATION_CREDENTIALS_JSON`` environment variable.

Usage from the project root (macOS clipboard):

    # 1. In Streamlit Cloud → Secrets, copy the full
    #    [google_sheets_credentials] block (section header + all fields).
    # 2. Run:
    pbpaste | python3 scripts/helpers/toml_secrets_to_json.py | pbcopy
    # 3. Now the single-line JSON is on your clipboard. Paste it:
    export GOOGLE_APPLICATION_CREDENTIALS_JSON="$(pbpaste)"

The script accepts either the section header + fields or only the fields
(in case you forgot to include the ``[header]`` line). It always emits
exactly one JSON object per run.
"""
from __future__ import annotations

import json
import sys

try:
    import tomllib
except ImportError:  # Python < 3.11 fallback.
    import tomli as tomllib  # type: ignore[import-not-found]


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print("ERROR: no TOML on stdin.", file=sys.stderr)
        return 2

    if not raw.lstrip().startswith("["):
        raw = "[creds]\n" + raw

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as exc:
        print(f"ERROR: invalid TOML: {exc}", file=sys.stderr)
        return 2

    if not data:
        print("ERROR: no sections found in TOML input.", file=sys.stderr)
        return 2

    section = next(iter(data.values()))
    if not isinstance(section, dict):
        print("ERROR: first TOML section is not a table.", file=sys.stderr)
        return 2

    print(json.dumps(section, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
