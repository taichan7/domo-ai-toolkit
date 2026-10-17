#!/usr/bin/env python3
"""Reusable, SAFE REST publisher for a pl-summary Pro Code design.

(Re)publish a Pro Code bundle WITHOUT the ``domo publish`` CLI and WITHOUT an
interactive OAuth browser login, and WITHOUT touching ryuu's machine-shared
"current instance" pointer. Authentication reuses the SID (or developer token)
that ``provision_domo.py``'s ``DomoClient`` already mints from the ryuu
configstore refresh token for the explicit ``DOMO_INSTANCE`` -- the same
mechanism that lets read-only ``verify`` work against the OAuth-only
``maintenance-instance`` instance. Because the target instance is explicit, this is safe
to run while other agents share the ryuu CLI (unlike ``domo publish``, which
publishes to ryuu's current-instance singleton).

Mechanism mirrors ryuu-client's ``domoapps-client.js`` (same contract as
inventory-management-app/scripts/rest_publish_design.py):

* ``DESIGNS_BASE_URL = /api/apps/v1/designs``
* ``uploadAsset``: ``POST {base}/{designId}/versions/{version}/assets?path={relpath}``
  with the RAW file bytes and a ``Content-Type`` derived from the extension
  (``CONTENT_TYPE_MAP`` below, case-sensitive, reproduced verbatim from ryuu).
* ``uploadAllAssets``: upload ``manifest.json`` FIRST (body = re-serialized
  manifest), THEN every ``glob('**/*')`` file minus ``node_modules``, each
  ``manifest.ignore`` pattern, directories, and ``manifest.json`` itself.
* ``getDesign``: ``GET {base}/{id}?parts=versions`` -> ``{latestVersion, ...}``.

SAFETY: publishing overwrites the live design version, so this refuses to touch
a PRODUCTION / reference design (``PL_SANDBOX_SUFFIX`` unset) unless the operator
opts in with ``PL_ALLOW_PRODUCTION`` in {1,true,yes} or ``--confirm``. A sandbox
participant (``PL_SANDBOX_SUFFIX`` set) must mint their own per-participant
design (strip ``id`` → Domo allocates a new one) rather than overwrite a shared
reference design. Filenames with spaces are rejected (like ryuu).

CLI:
    DOMO_INSTANCE=maintenance-instance.domo.com \
        python3 scripts/rest_publish_design.py [--dir pro-code] [--confirm]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
APP_ROOT = SCRIPT_DIR.parent  # pl-summary-app
DEFAULT_BUNDLE_DIR = APP_ROOT / "pro-code"
PROVISION_PATH = SCRIPT_DIR / "provision_domo.py"

# DESIGNS_BASE_URL from ryuu endpoints.js (leading slash dropped so it composes
# with client.base and client.request()'s lstrip('/')).
DESIGNS_BASE_PATH = "api/apps/v1/designs"

# pl-summary の参照（本番）デザイン id。名札付き（サンドボックス）実行でこれらを指す publish は
# 共有参照デザインのライブ版を上書きする事故になる。サンドボックスの正順は「id を外した配布コピー
# から publish して自分専用デザインを採番する」ため、名札付きでこれらを指す publish は
# --confirm / PL_ALLOW_PRODUCTION 無しでは拒否する（result-based 判定）。
REFERENCE_DESIGN_IDS = frozenset({
    "f891df58-0258-52d6-a1a0-517affb748a4",  # pro-code: Store PL AI Insights
    "531a3c0f-bf42-500c-a4ce-87b60c743414",  # dev-guide-app
})

# Verbatim from ryuu models/constants/content.js. Lookup is case-sensitive and
# NOT lower-cased, exactly like ryuu (`extension in CONTENT_TYPE_MAP`): an
# extension absent here (e.g. ``mjs``, or an upper-cased ``PNG``) uploads with no
# Content-Type and then serves 0 bytes live.
CONTENT_TYPE_MAP: Dict[str, str] = {
    "css": "text/css",
    "html": "text/html",
    "js": "application/javascript",
    "map": "application/javascript",
    "json": "application/json",
    "jsx": "application/javascript",
    "py": "application/python",
    "ts": "application/typescript",
    "tsx": "application/typescript",
    "vue": "application/vue",
    "dockerfile": "application/dockerfile",
    "graphql": "application/graphql",
    "md": "text/markdown",
    "sass": "text/sass",
    "sh": "application/shell",
    "sql": "application/sql",
    "toml": "application/toml",
    "xml": "application/xml",
    "yaml": "application/yaml",
    "yml": "application/yaml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "eps": "image/eps+xml",
}

# ryuu uploadAllAssets defaultIgnore (nested + top-level node_modules).
DEFAULT_IGNORE: List[str] = ["**/*/node_modules/**/*", "node_modules/**/*"]


def _load_provision() -> Any:
    """Load scripts/provision_domo.py by path (hyphenated parent dir blocks a
    plain ``import``). No network at import -- DomoClient is instantiated on demand."""
    spec = importlib.util.spec_from_file_location("pl_provision", PROVISION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


PROVISION = _load_provision()
DomoApiError = PROVISION.DomoApiError


def content_type_for(path: str) -> Optional[str]:
    """ryuu Content-Type for ``path``'s extension (case-sensitive), or None."""
    match = re.search(r"\.(\w+)$", str(path))
    if not match:
        return None
    return CONTENT_TYPE_MAP.get(match.group(1))


def _glob_to_regex(pattern: str) -> "re.Pattern[str]":
    """Translate a node-glob ignore pattern to an anchored regex (``**/`` spans
    0+ segments, ``*`` within one segment, ``?`` one non-separator char)."""
    pattern = pattern.replace("\\", "/")
    i, n, out = 0, len(pattern), []
    while i < n:
        char = pattern[i]
        if char == "*":
            if pattern[i:i + 2] == "**":
                j = i
                while j < n and pattern[j] == "*":
                    j += 1
                if j < n and pattern[j] == "/":
                    out.append("(?:.*/)?")
                    i = j + 1
                else:
                    out.append(".*")
                    i = j
            else:
                out.append("[^/]*")
                i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _ignored(relpath: str, regexes: List["re.Pattern[str]"]) -> bool:
    return any(rx.match(relpath) for rx in regexes)


def enumerate_upload_paths(bundle_dir: Any, manifest: Dict[str, Any]) -> List[str]:
    """Ordered relative upload paths: ``manifest.json`` first, then every other
    file (sorted), excluding directories, node_modules, each ``manifest.ignore``
    pattern, and ``manifest.json`` itself (mirrors ryuu ``uploadAllAssets``)."""
    bundle = pathlib.Path(bundle_dir)
    patterns = list(DEFAULT_IGNORE) + list(manifest.get("ignore") or [])
    regexes = [_glob_to_regex(pattern) for pattern in patterns]
    rest: List[str] = []
    for path in bundle.rglob("*"):
        if not path.is_file():
            continue
        relpath = path.relative_to(bundle).as_posix()
        if relpath == "manifest.json":
            continue
        if _ignored(relpath, regexes):
            continue
        rest.append(relpath)
    rest.sort()
    return ["manifest.json"] + rest


def manifest_bytes(manifest: Dict[str, Any]) -> bytes:
    """Serialize the manifest like ryuu (``JSON.stringify``): compact, literal
    non-ASCII (not \\uXXXX-escaped)."""
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def asset_bytes(bundle_dir: Any, relpath: str, manifest: Dict[str, Any]) -> bytes:
    if relpath == "manifest.json":
        return manifest_bytes(manifest)
    return (pathlib.Path(bundle_dir) / relpath).read_bytes()


def auth_header(client: Any) -> Dict[str, str]:
    """ryuu getAuthHeader shape: developer token takes precedence over SID."""
    if getattr(client, "dev_token", ""):
        return {"X-DOMO-Developer-Token": client.dev_token}
    return {"X-Domo-Authentication": client.sid}


def upload_asset(
    client: Any,
    design_id: str,
    version: str,
    relpath: str,
    data: bytes,
    *,
    opener: Any = None,
) -> bytes:
    """RAW POST of one asset's bytes (NOT via client.request(), which JSON-encodes)."""
    if " " in relpath:
        raise ValueError(f"Spaces in file names not allowed. Please rename {relpath}")
    opener = opener or getattr(client, "_open", urllib.request.urlopen)
    headers = dict(auth_header(client))
    content_type = content_type_for(relpath)
    if content_type:
        headers["Content-Type"] = content_type
    url = (
        f"{client.base}/{DESIGNS_BASE_PATH}/{design_id}"
        f"/versions/{version}/assets?path={urllib.parse.quote(relpath)}"
    )
    request = urllib.request.Request(url=url, data=data, method="POST", headers=headers)
    try:
        with opener(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        error.read()  # discard potentially sensitive server content
        print(f"ERROR uploading {relpath}: HTTP {error.code}", file=sys.stderr, flush=True)
        raise


def get_design(client: Any, design_id: str) -> Dict[str, Any]:
    return client.request("GET", f"{DESIGNS_BASE_PATH}/{design_id}?parts=versions") or {}


def latest_version(client: Any, design_id: str) -> str:
    try:
        return str(get_design(client, design_id).get("latestVersion") or "")
    except DomoApiError as error:
        print(f"(could not read existing design {design_id}: {error})", flush=True)
        return ""


def _sandbox_active() -> bool:
    return bool((os.environ.get("PL_SANDBOX_SUFFIX") or "").strip())


def _allow_production_env() -> bool:
    return (os.environ.get("PL_ALLOW_PRODUCTION") or "").strip().lower() in ("1", "true", "yes")


def production_publish_guard(
    confirm: bool = False,
    *,
    sandbox: Optional[bool] = None,
    allow_production: Optional[bool] = None,
    target_label: str = "",
    design_id: str = "",
) -> None:
    """Refuse to overwrite a PRODUCTION / reference design unless explicitly opted in."""
    if sandbox is None:
        sandbox = _sandbox_active()
    if allow_production is None:
        allow_production = _allow_production_env()
    opted_in = confirm or allow_production
    if sandbox and str(design_id) in REFERENCE_DESIGN_IDS and not opted_in:
        target = f"（{target_label}）" if target_label else ""
        raise SystemExit(
            f"名札付き（サンドボックス）で参照デザイン{target}を publish しようとしています＝共有参照"
            "デザインのライブ版を上書きする事故です。\n"
            "配布コピーの manifest.json からトップレベルの \"id\" を外してから publish してください"
            "（Domo が新しい design を払い出します）。\n"
            "⚠参照デザイン自体を更新する本番メンテナのみ PL_ALLOW_PRODUCTION=1 または --confirm を明示してください。"
        )
    if sandbox or opted_in:
        return
    target = f"（{target_label}）" if target_label else ""
    raise SystemExit(
        f"このまま publish すると本番の Pro Code デザイン{target}のライブ版を上書きします。\n"
        "ハンズオン／検証なら名札を付けてください:\n"
        "  export PL_SANDBOX_SUFFIX='検証・<あなたの氏名>'\n"
        "⚠本番デザインを更新する本番メンテナのみ PL_ALLOW_PRODUCTION=1 または --confirm を明示してください。"
    )


def publish_design(
    client: Any,
    bundle_dir: Any,
    manifest: Dict[str, Any],
    paths: List[str],
    *,
    opener: Any = None,
) -> None:
    """Upload every path in order (manifest.json first) via raw POSTs."""
    design_id = str(manifest["id"])
    version = str(manifest["version"])
    for relpath in paths:
        data = asset_bytes(bundle_dir, relpath, manifest)
        upload_asset(client, design_id, version, relpath, data, opener=opener)
        content_type = content_type_for(relpath) or "(no content-type -> 0-byte live!)"
        print(f"  uploaded {relpath} ({len(data)} bytes) [{content_type}]", flush=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Safe REST (re)publisher for a pl-summary Pro Code design.")
    parser.add_argument("--dir", default=str(DEFAULT_BUNDLE_DIR), help="Pro Code bundle dir (default: pro-code).")
    parser.add_argument("--confirm", action="store_true", help="Explicitly allow publishing to a production design.")
    args = parser.parse_args(argv)

    bundle_dir = pathlib.Path(args.dir).expanduser().resolve()
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"manifest.json not found in {bundle_dir}", file=sys.stderr, flush=True)
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    design_id = str(manifest.get("id") or "")
    version = str(manifest.get("version") or "")
    if not design_id or not version:
        print("manifest.json must declare both 'id' and 'version'", file=sys.stderr, flush=True)
        return 2

    # Guard BEFORE any network (SID mint happens at DomoClient()).
    production_publish_guard(
        args.confirm,
        target_label=f"{manifest.get('name') or design_id} / id {design_id}",
        design_id=design_id,
    )

    paths = enumerate_upload_paths(bundle_dir, manifest)
    spaced = [relpath for relpath in paths if " " in relpath]
    if spaced:
        print(f"Spaces in file names not allowed (like ryuu). Please rename: {spaced}", file=sys.stderr, flush=True)
        return 2

    print(f"instance:   {PROVISION.INSTANCE}")
    print(f"design id:  {design_id}")
    print(f"version:    {version}")
    print(f"bundle dir: {bundle_dir}")
    print(f"files to upload ({len(paths)}, manifest.json first):")
    for relpath in paths:
        content_type = content_type_for(relpath) or "(no content-type -> 0-byte live!)"
        print(f"  {relpath}  [{content_type}]")

    client = PROVISION.DomoClient()  # requires an explicit target instance (DOMO_INSTANCE)
    auth_mode = "developer-token" if getattr(client, "dev_token", "") else "SID (ryuu refresh token)"
    print(f"auth:       {auth_mode}")

    before = latest_version(client, design_id)
    print(f"BEFORE latestVersion: {before or '(design not found)'}")

    try:
        publish_design(client, bundle_dir, manifest, paths)
    except urllib.error.HTTPError:
        return 1  # body already printed by upload_asset

    after = latest_version(client, design_id)
    print(f"AFTER latestVersion:  {after or '(design not found)'}")
    print(f"latestVersion == manifest.version ({version}): {after == version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
