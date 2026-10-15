#!/usr/bin/env python3
"""Check public distribution files, without printing credential values.

Run alongside check-secrets.sh. Only Git-tracked files are release inputs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import zlib

PUBLIC_DOMO_HOSTS = {"api", "public", "developer", "developers", "knowledge", "learn", "www", "connectors",
                     "support", "domo-support", "community-forums", "dojo", "domohelp"}
EXAMPLE_HOST = re.compile(r"(?:your|source|target|destination|maintenance|example|mycompany|company|customer|publisher|subscriber|demo|tenant|acme|instance|test|my-instance|other)(?:-[a-z0-9]+)?$")
DOMO_HOST = re.compile(r"(?<![\w-])([a-z0-9](?:[a-z0-9-]*[a-z0-9])?)\.domo\.com\b", re.I)
FORBIDDEN = {"domo-assets.json", ".sid", ".domo", "credentials.json", "secrets.env",
             "sid.txt", "access_token.txt", "__pycache__", ".DS_Store", "secrets"}


def sanitize_png(data):
    """Remove non-rendering text/EXIF/time; preserve pixels and color management."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature")
    output = bytearray(data[:8])
    offset, ended = 8, False
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + length + 12
        if end > len(data):
            raise ValueError("truncated PNG chunk")
        kind = data[offset + 4:offset + 8]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        if zlib.crc32(data[offset + 4:end - 4]) & 0xffffffff != crc:
            raise ValueError("invalid PNG checksum")
        if kind not in {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}:
            output.extend(data[offset:end])
        offset = end
        if kind == b"IEND":
            ended = True
            break
    if not ended or offset != len(data):
        raise ValueError("invalid PNG ending")
    return bytes(output)


def violations(rel, data):
    problems = []
    p = Path(rel)
    if p.suffix.lower() == ".png":
        try:
            if sanitize_png(data) != data:
                problems.append(f"{rel}: non-rendering PNG metadata in distribution")
        except ValueError:
            problems.append(f"{rel}: invalid PNG")
    if (set(p.parts) & FORBIDDEN or any(part.startswith("sandbox-") for part in p.parts)
            or (p.name.startswith(".env") and not p.name.endswith(".example"))
            or p.suffix.lower() in {".token", ".key", ".pem", ".p12", ".pfx", ".pyc", ".zip"}):
        problems.append(f"{rel}: deployment state or credential-like path")
    if p.parts[0] in {"handoffs", "tasks"}:
        problems.append(f"{rel}: internal coordination file is not public toolkit content")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return problems
    if any(host.lower() not in PUBLIC_DOMO_HOSTS and not EXAMPLE_HOST.fullmatch(host.lower())
           for host in DOMO_HOST.findall(text)):
        problems.append(f"{rel}: non-example Domo instance hostname")
    if re.search(r"(?<![\w/])/Users/[a-z]|(?<![\w/])/home/[a-z]", text):
        problems.append(f"{rel}: private absolute home path")
    if rel.endswith(("/pro-code/manifest.json", "/dev-guide-app/manifest.json")):
        try:
            manifest = json.loads(text)
        except json.JSONDecodeError:
            return problems + [f"{rel}: invalid JSON manifest"]
        if "id" in manifest:
            problems.append(f"{rel}: design ID must be omitted before distribution")
        for section, key in (("datasetsMapping", "dataSetId"), ("collectionsMapping", "id"),
                             ("packagesMapping", "packageId"), ("workflowsMapping", "modelId")):
            if any(item.get(key) for item in manifest.get(section) or []):
                problems.append(f"{rel}: tenant binding in {section}")
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    paths = [p for p in raw.decode().split("\0") if p]
    problems = []
    for rel in paths:
        p = root / rel
        if not p.exists():
            problems.append(f"{rel}: tracked file missing")
        elif p.is_symlink() or not p.resolve().is_relative_to(root):
            problems.append(f"{rel}: symlink or path outside distribution")
        else:
            problems.extend(violations(rel, p.read_bytes()))
    manifest_path = root / ".domokit-manifest.json"
    if manifest_path.is_file() and not manifest_path.is_symlink():
        try:
            manifest = json.loads(manifest_path.read_text())
            managed = manifest["files"]
            if not isinstance(managed, dict):
                raise ValueError("files must be an object")
        except (OSError, ValueError, KeyError, TypeError):
            problems.append(".domokit-manifest.json: invalid managed file table")
            managed = {}
        for rel, digest in managed.items():
            p = root / rel
            if (Path(rel).is_absolute() or ".." in Path(rel).parts or "\\" in rel
                    or ".git" in Path(rel).parts or not p.resolve().is_relative_to(root)):
                problems.append(".domokit-manifest.json: unsafe managed path")
            elif rel not in paths or not p.is_file():
                problems.append(f"{rel}: managed file missing or untracked")
            elif not isinstance(digest, str) or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
                problems.append(f"{rel}: managed content hash does not match")
    if problems:
        print("Public distribution check failed:", file=sys.stderr)
        print("\n".join(problems), file=sys.stderr)
        return 1
    print(f"Public distribution check passed ({len(paths)} tracked files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
