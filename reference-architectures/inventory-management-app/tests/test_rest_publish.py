"""Offline tests for scripts/rest_publish_design.py (no network).

Covers the ryuu-mirrored contract:
  (a) file enumeration -- manifest.json first, directories / node_modules /
      manifest.json / manifest.ignore patterns excluded;
  (b) content-type lookup -- right type for html/css/js/png/json, None for .mjs
      (and other extensions absent from the map);
  (c) production guard -- refuses with none of {--confirm, INVENTORY_ALLOW_PRODUCTION,
      sandbox suffix}, permits with each of the three.

Plus the raw-upload URL/header/space-rejection contract and the GET-design read,
all exercised with stubs so nothing touches the network. The module is loaded by
path (hyphenated parent dir), same importlib idiom as tests/test_provisioning.py.
"""

import importlib.util
import json
import os
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("inventory_rest_publish", ROOT / "scripts" / "rest_publish_design.py")
REST = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(REST)


class _FakeResponse:
    """Minimal context-manager response (what urlopen yields)."""

    def __init__(self, body: bytes = b""):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


class _FakeOpener:
    """Captures the urllib.request.Request instead of sending it."""

    def __init__(self):
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        return _FakeResponse(b"ok")


class _FakeClient:
    """Stub DomoClient: just the attributes rest_publish_design reads, plus a
    canned request() so get_design never hits the network."""

    def __init__(self, dev_token="", sid="sid-xyz", instance="maintenance-instance.domo.com", design=None):
        self.dev_token = dev_token
        self.sid = sid
        self.instance = instance
        self.base = f"https://{instance}"
        self._design = design or {}
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        return self._design


def _headers_lower(request):
    return {key.lower(): value for key, value in request.header_items()}


class FileEnumerationTests(unittest.TestCase):
    """(a) manifest.json first; dirs / node_modules / manifest.json / ignore excluded."""

    def _bundle(self, tmp):
        root = pathlib.Path(tmp)
        (root / "sub").mkdir()
        (root / "vendor").mkdir()
        (root / "node_modules" / "dep").mkdir(parents=True)
        (root / "emptydir").mkdir()
        (root / "manifest.json").write_text("{}", encoding="utf-8")
        (root / "index.html").write_text("<html>", encoding="utf-8")
        (root / "app.js").write_text("//", encoding="utf-8")
        (root / "app.js.map").write_text("{}", encoding="utf-8")            # excluded by **/*.map
        (root / "sub" / "util.js").write_text("//", encoding="utf-8")
        (root / "vendor" / "skip.txt").write_text("x", encoding="utf-8")    # excluded by exact ignore
        (root / "node_modules" / "top.js").write_text("//", encoding="utf-8")        # default ignore
        (root / "node_modules" / "dep" / "index.js").write_text("//", encoding="utf-8")  # default ignore
        return root

    def test_enumeration_respects_ignore_dirs_and_lists_manifest_first(self):
        import tempfile
        manifest = {"id": "d1", "version": "3.0.0", "ignore": ["vendor/skip.txt", "**/*.map"]}
        with tempfile.TemporaryDirectory() as tmp:
            root = self._bundle(tmp)
            result = REST.enumerate_upload_paths(root, manifest)

        # manifest.json is first, and appears exactly once.
        self.assertEqual(result[0], "manifest.json")
        self.assertEqual(result.count("manifest.json"), 1)
        # The real files that survive, in sorted order after manifest.json.
        self.assertEqual(result, ["manifest.json", "app.js", "index.html", "sub/util.js"])
        # node_modules (both default patterns), the ignore'd files, and directories are gone.
        for excluded in (
            "node_modules/top.js",
            "node_modules/dep/index.js",
            "vendor/skip.txt",
            "app.js.map",
            "emptydir",
            "sub",
            "vendor",
            "node_modules",
        ):
            self.assertNotIn(excluded, result)

    def test_no_ignore_key_still_excludes_node_modules_and_manifest(self):
        import tempfile
        manifest = {"id": "d1", "version": "1.0.0"}  # no 'ignore' key
        with tempfile.TemporaryDirectory() as tmp:
            root = self._bundle(tmp)
            result = REST.enumerate_upload_paths(root, manifest)
        self.assertEqual(result[0], "manifest.json")
        # Without manifest.ignore, the .map and vendor/skip.txt now upload, but
        # node_modules and manifest.json are still excluded by the defaults.
        self.assertIn("app.js.map", result)
        self.assertIn("vendor/skip.txt", result)
        self.assertFalse(any(p.startswith("node_modules/") for p in result))

    def test_manifest_bytes_match_json_stringify(self):
        # ryuu uploads JSON.stringify(manifest): compact separators, literal UTF-8.
        manifest = {"id": "d1", "version": "2.0.0", "name": "在庫入出庫管理｜開発ガイド"}
        raw = REST.manifest_bytes(manifest)
        self.assertEqual(raw, json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        self.assertNotIn(b", ", raw)   # no spaces after commas
        self.assertIn("在庫".encode("utf-8"), raw)  # non-ASCII emitted literally

    def test_asset_bytes_manifest_vs_file(self):
        import tempfile
        manifest = {"id": "d1", "version": "2.0.0"}
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "app.js").write_text("console.log(1)", encoding="utf-8")
            self.assertEqual(REST.asset_bytes(root, "manifest.json", manifest), REST.manifest_bytes(manifest))
            self.assertEqual(REST.asset_bytes(root, "app.js", manifest), b"console.log(1)")


class ContentTypeTests(unittest.TestCase):
    """(b) content-type lookup for the common extensions and the .mjs 0-byte gotcha."""

    def test_known_extensions(self):
        self.assertEqual(REST.content_type_for("index.html"), "text/html")
        self.assertEqual(REST.content_type_for("app.css"), "text/css")
        self.assertEqual(REST.content_type_for("app.js"), "application/javascript")
        self.assertEqual(REST.content_type_for("logo.png"), "image/png")
        self.assertEqual(REST.content_type_for("manifest.json"), "application/json")

    def test_mjs_and_other_absent_extensions_return_none(self):
        self.assertIsNone(REST.content_type_for("module.mjs"))        # the headline gotcha
        self.assertIsNone(REST.content_type_for("README"))            # no extension
        self.assertIsNone(REST.content_type_for("vendor/ryuu.js-4.6.0.LICENSE"))  # LICENSE not mapped
        self.assertIsNone(REST.content_type_for("IMAGE.PNG"))         # case-sensitive, like ryuu

    def test_map_matches_ryuu_source_values(self):
        # Spot-check a few less-common entries reproduced verbatim from ryuu.
        self.assertEqual(REST.content_type_for("a.svg"), "image/svg+xml")
        self.assertEqual(REST.content_type_for("a.map"), "application/javascript")
        self.assertEqual(REST.content_type_for("a.yml"), "application/yaml")


class ProductionGuardTests(unittest.TestCase):
    """(c) refuse with none of the three opt-ins; permit with each one."""

    def test_refuses_production_without_any_optin(self):
        with self.assertRaises(SystemExit):
            REST.production_publish_guard(confirm=False, sandbox=False, allow_production=False)

    def test_confirm_flag_permits(self):
        REST.production_publish_guard(confirm=True, sandbox=False, allow_production=False)  # no raise

    def test_sandbox_suffix_permits(self):
        # 名札付きでも参照デザイン id を指していなければ（＝自分専用デザイン）通る。
        REST.production_publish_guard(confirm=False, sandbox=True, allow_production=False)  # no raise

    def test_allow_production_env_permits(self):
        REST.production_publish_guard(confirm=False, sandbox=False, allow_production=True)  # no raise

    def test_sandbox_refuses_reference_design_id(self):
        # result-based: 名札付きで参照（本番）デザイン id を指す publish は、共有参照デザインの
        # 上書き事故ゆえ拒否する（input-based の抜け穴＝「名札さえあれば何でも通す」を塞ぐ）。
        self.assertTrue(REST.REFERENCE_DESIGN_IDS, "reference ids must be declared")
        for ref_id in REST.REFERENCE_DESIGN_IDS:
            with self.assertRaises(SystemExit, msg=f"sandbox publish to reference id {ref_id} must refuse"):
                REST.production_publish_guard(confirm=False, sandbox=True, allow_production=False, design_id=ref_id)

    def test_sandbox_permits_own_minted_design_id(self):
        # 名札付きでも、参照 id でない（＝自分で採番した）design への publish は通る＝再 publish 可。
        minted = "11111111-2222-3333-4444-555555555555"
        self.assertNotIn(minted, REST.REFERENCE_DESIGN_IDS)
        REST.production_publish_guard(confirm=False, sandbox=True, allow_production=False, design_id=minted)  # no raise

    def test_reference_design_id_overridable_by_maintainer(self):
        # 参照デザイン自体を更新する本番メンテナは --confirm / ALLOW_PRODUCTION で明示解除できる。
        ref_id = next(iter(REST.REFERENCE_DESIGN_IDS))
        REST.production_publish_guard(confirm=True, sandbox=True, allow_production=False, design_id=ref_id)  # no raise
        REST.production_publish_guard(confirm=False, sandbox=True, allow_production=True, design_id=ref_id)  # no raise

    def test_env_wiring_is_read_live(self):
        # Prove the defaults actually read INVENTORY_SANDBOX_SUFFIX / INVENTORY_ALLOW_PRODUCTION.
        saved = {k: os.environ.get(k) for k in ("INVENTORY_SANDBOX_SUFFIX", "INVENTORY_ALLOW_PRODUCTION")}

        def restore():
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.addCleanup(restore)

        os.environ.pop("INVENTORY_SANDBOX_SUFFIX", None)
        os.environ.pop("INVENTORY_ALLOW_PRODUCTION", None)
        with self.assertRaises(SystemExit):
            REST.production_publish_guard(confirm=False)

        os.environ["INVENTORY_SANDBOX_SUFFIX"] = "検証・テスト"
        REST.production_publish_guard(confirm=False)  # sandbox auto-detected -> no raise

        os.environ.pop("INVENTORY_SANDBOX_SUFFIX", None)
        os.environ["INVENTORY_ALLOW_PRODUCTION"] = "yes"
        REST.production_publish_guard(confirm=False)  # env opt-in -> no raise


class RawUploadContractTests(unittest.TestCase):
    """Raw POST URL/headers mirror ryuu uploadAsset; SID vs dev-token; space reject."""

    def test_upload_url_and_sid_header(self):
        client = _FakeClient(dev_token="", sid="sid-xyz")
        opener = _FakeOpener()
        REST.upload_asset(client, "design-1", "3.0.0", "sub/util.js", b"//", opener=opener)
        request = opener.requests[0]
        self.assertEqual(
            request.full_url,
            "https://maintenance-instance.domo.com/api/apps/v1/designs/design-1/versions/3.0.0/assets?path=sub/util.js",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b"//")
        headers = _headers_lower(request)
        self.assertEqual(headers.get("x-domo-authentication"), "sid-xyz")
        self.assertNotIn("x-domo-developer-token", headers)
        self.assertEqual(headers.get("content-type"), "application/javascript")

    def test_upload_prefers_developer_token_and_omits_content_type_for_mjs(self):
        client = _FakeClient(dev_token="dev-123", sid="sid-xyz")
        opener = _FakeOpener()
        REST.upload_asset(client, "design-1", "3.0.0", "worker.mjs", b"x", opener=opener)
        headers = _headers_lower(opener.requests[0])
        self.assertEqual(headers.get("x-domo-developer-token"), "dev-123")
        self.assertNotIn("x-domo-authentication", headers)
        # .mjs is absent from the map -> no Content-Type (serves 0 bytes live).
        self.assertNotIn("content-type", headers)

    def test_upload_quotes_non_ascii_path_but_keeps_slash(self):
        client = _FakeClient()
        opener = _FakeOpener()
        REST.upload_asset(client, "d", "1.0.0", "assets/ロゴ.png", b"x", opener=opener)
        # slash inside the relpath is preserved (safe='/'); the non-ASCII is percent-encoded.
        self.assertTrue(opener.requests[0].full_url.endswith("?path=assets/%E3%83%AD%E3%82%B4.png"))

    def test_upload_rejects_spaces_like_ryuu(self):
        client = _FakeClient()
        opener = _FakeOpener()
        with self.assertRaises(ValueError):
            REST.upload_asset(client, "d", "1.0.0", "bad name.js", b"x", opener=opener)
        self.assertEqual(opener.requests, [])  # nothing attempted

    def test_get_design_reads_versions_part(self):
        client = _FakeClient(design={"latestVersion": "2.0.0", "versions": ["1.0.0", "2.0.0"]})
        self.assertEqual(REST.latest_version(client, "design-1"), "2.0.0")
        self.assertIn(("GET", "api/apps/v1/designs/design-1?parts=versions", None), client.calls)


class ConstantsTests(unittest.TestCase):
    def test_endpoint_and_default_ignore_match_ryuu(self):
        self.assertEqual(REST.DESIGNS_BASE_PATH, "api/apps/v1/designs")
        self.assertEqual(REST.DEFAULT_IGNORE, ["**/*/node_modules/**/*", "node_modules/**/*"])


if __name__ == "__main__":
    unittest.main()
