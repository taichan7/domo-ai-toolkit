#!/usr/bin/env python3
"""Check that every relative Markdown link in this repo resolves.

Usage: python3 scripts/check-links.py   (exit 1 on any broken link)
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
# Illustrative example targets that are intentionally not real files.
IGNORE = {"target", "file.md", "docs/y.md"}


def main() -> int:
    broken: list[str] = []
    for md in sorted(ROOT.rglob("*.md")):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        text = md.read_text(encoding="utf-8", errors="ignore")
        for m in LINK_RE.finditer(text):
            url = m.group(1).split("#")[0].strip()
            if not url or url.startswith(("http://", "https://", "mailto:", "#")):
                continue
            if url in IGNORE:
                continue
            if not (md.parent / url).resolve().exists():
                broken.append(f"{md.relative_to(ROOT)}: {url}")
    if broken:
        print(f"Broken relative links: {len(broken)}", file=sys.stderr)
        for b in broken:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print("All relative Markdown links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
