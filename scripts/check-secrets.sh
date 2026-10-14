#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "ERROR: no python executable found on PATH (tried python3, python, py)" >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import re
import subprocess
import sys
from pathlib import Path

raw = subprocess.check_output(["git", "ls-files", "-z"])
files = [p for p in raw.decode().split("\0") if p]

filename_patterns = [
    re.compile(r"(^|/)\.env(\..*)?$"),
    re.compile(r"(^|/)\.sid$"),
    re.compile(r"\.(token|pem|key|p12|pfx)$"),
    re.compile(r"(^|/)credentials\.json$"),
    re.compile(r"(^|/)secrets/"),
    re.compile(r"(^|/)\.domo/"),
    re.compile(r"(^|/)(sid|access_token)\.txt$"),
]

content_patterns = [
    re.compile(r"refreshToken[\"']?\s*[:=]\s*[\"'][A-Za-z0-9._/-]{20,}[\"']?"),
    re.compile(r"X-DOMO-Developer-Token:\s*[A-Za-z0-9._/-]{20,}"),
    re.compile(r"\b(DOMO_TOKEN|SID|ACCESS_TOKEN)\s*=\s*[\"']?[A-Za-z0-9._/-]{20,}[\"']?"),
    re.compile(r"client_secret\s*[:=]\s*[\"'][^\"']{16,}[\"']", re.IGNORECASE),
    re.compile(r"(api[-_]?key|token|password)\s*[:=]\s*[\"'][A-Za-z0-9_./+=-]{16,}[\"']", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH |)PRIVATE KEY-----"),
]
placeholder_words = [
    "your",
    "replace",
    "example",
    "dummy",
    "placeholder",
    "token_here",
    "xxx",
    "todo",
]

errors = []

for file_name in files:
    for pattern in filename_patterns:
        if pattern.search(file_name):
            errors.append(f"tracked secret-like file: {file_name}")
            break

for file_name in files:
    path = Path(file_name)
    try:
        text = path.read_text(errors="ignore")
    except UnicodeDecodeError:
        continue
    except OSError:
        continue

    for pattern in content_patterns:
        matches = list(pattern.finditer(text))
        real_matches = [
            match for match in matches
            if not any(word in match.group(0).lower() for word in placeholder_words)
        ]
        if real_matches:
            errors.append(f"possible secret pattern in: {file_name}")
            break

if errors:
    print("Secret scan failed:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    sys.exit(1)

print("Secret scan passed.")
PY
