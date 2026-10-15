"""Characterize the backend-inclusive sandbox isolation + production guard.

provision_domo.py reads INVENTORY_SANDBOX_SUFFIX / APP_STUDIO_NAME at import time
(module constants) and INVENTORY_ALLOW_PRODUCTION / DOMO_ASSETS_PATH at call time.
So each case runs inside `env_module(...)`, which sets exactly the given env, execs
a FRESH module copy, and keeps the env live for the duration of the `with` block
(the guard and registry_write_path read os.environ when called). Offline only: no
Domo, no token — it inspects module constants and calls the pure guard helper.

Pins (mirrors the handson-sandbox-distribution pattern):
  1. default (no nameplate) => names byte-identical to production, state in-repo.
  2. a nameplate tags EVERY backend/surface object name (（suffix）全角括弧).
  3. code contracts (Workflow input names, page/layout constants) stay invariant.
  4. state path is per-participant (sandbox-<slug>/), honoring DOMO_ASSETS_PATH.
  5. the production guard is RESULT-based: it refuses the production name even
     when a suffix is set but APP_STUDIO_NAME is forced to the production name,
     and INVENTORY_ALLOW_PRODUCTION=1 unlocks it.
"""
import contextlib
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "provision_domo.py"


class _FakeClient:
    """sync_manifest 用の最小 client。発見系はモジュール関数を空へ差し替えるので request は未使用。"""

    def request(self, *args, **kwargs):  # pragma: no cover - defensive
        return {}


def _stub_discovery(mod):
    """sync_manifest の資産発見（client 依存）を空へ差し替え、manifest 書き出し挙動だけを分離検証する。"""
    mod.list_collections = lambda client: []
    mod.list_packages = lambda client: []
    mod.list_dataflows = lambda client: []
    mod.resolve_workflow_model_id = lambda client: ""
    mod.output_dataset_id = lambda flow: ""

_ENV_KEYS = (
    "INVENTORY_SANDBOX_SUFFIX",
    "INVENTORY_ALLOW_PRODUCTION",
    "APP_STUDIO_NAME",
    "DOMO_ASSETS_PATH",
    "DOMO_INSTANCE",
)


@contextlib.contextmanager
def env_module(**env):
    """Exec a fresh copy of provision_domo.py under exactly `env` (others cleared),
    and keep that env live for the whole `with` block so call-time reads see it."""
    saved = {k: os.environ.get(k) for k in _ENV_KEYS}
    try:
        for k in _ENV_KEYS:
            os.environ.pop(k, None)
        for k, v in env.items():
            os.environ[k] = v
        spec = importlib.util.spec_from_file_location("prov_sandbox_probe", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


SUFFIX = "検証・田中"
PAREN = "（" + SUFFIX + "）"
BACKEND_NAME_ATTRS = (
    "DATASTORE_NAME", "COLLECTION_NAME", "PACKAGE_NAME", "DATAFLOW_NAME",
    "OUTPUT_DATASET_NAME", "WORKFLOW_MODEL_NAME", "APP_STUDIO_NAME",
    "APP_STUDIO_CARD_TITLE", "DEV_GUIDE_CARD_TITLE",
)
WRITE_COMMANDS = ("apply", "app-studio", "workflow", "cleanup-legacy")
READ_COMMANDS = ("verify", "sync-manifest", "export-app-studio")


class DefaultsUnchanged(unittest.TestCase):
    def test_no_nameplate_is_byte_identical_to_production(self):
        with env_module() as m:
            self.assertFalse(m.SANDBOX)
            self.assertEqual(m.DATASTORE_NAME, "inventory-management-app")
            self.assertEqual(m.COLLECTION_NAME, "inventory_management_records")
            self.assertEqual(m.PACKAGE_NAME, "Inventory Management | Transaction Service")
            self.assertEqual(m.DATAFLOW_NAME, "Inventory Management | Analytics")
            self.assertEqual(m.OUTPUT_DATASET_NAME, "Inventory Management | Dashboard")
            self.assertEqual(m.WORKFLOW_MODEL_NAME, "Inventory Management | Low Stock Notification")
            self.assertEqual(m.APP_STUDIO_NAME, m.PRODUCTION_APP_STUDIO_NAME)
            self.assertEqual(m.APP_STUDIO_NAME, "在庫入出庫管理ハンズオン")
            self.assertEqual(m.APP_STUDIO_CARD_TITLE, "在庫入出庫・分析（最小構成）")
            self.assertEqual(m.DEV_GUIDE_CARD_TITLE, "在庫管理リファレンス ガイド")
            self.assertEqual(m.registry_write_path(), m.IN_REPO_REGISTRY_PATH)


class NameplateTagsEveryObject(unittest.TestCase):
    def test_suffix_tags_all_backend_and_surface_names(self):
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX) as m:
            self.assertTrue(m.SANDBOX)
            for attr in BACKEND_NAME_ATTRS:
                value = getattr(m, attr)
                self.assertTrue(value.endswith(PAREN), attr + " not nameplated: " + value)
            self.assertNotEqual(m.APP_STUDIO_NAME, m.PRODUCTION_APP_STUDIO_NAME)

    def test_contract_names_and_layout_are_invariant(self):
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX) as m:
            self.assertEqual(
                m.WORKFLOW_INPUT_FIELDS,
                ("event_type", "headline", "shortage_lines", "recipient_email", "occurred_at"),
            )
            self.assertTrue(m.COLLECTION_NAME.startswith("inventory_management_records"))
            self.assertTrue(m.OUTPUT_DATASET_NAME.startswith("Inventory Management | Dashboard"))
            self.assertEqual(m.DEV_GUIDE_PAGE_TITLE, "開発ガイド")
            self.assertEqual(m.DEV_GUIDE_STANDARD, (60, 82))
            self.assertEqual(m.DEV_GUIDE_COMPACT, (12, 29))


class StateIsolation(unittest.TestCase):
    def test_new_sandbox_never_inherits_the_same_instance_base_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp) / "base.json"
            own = pathlib.Path(tmp) / "participant.json"
            base.write_text(json.dumps({"instance": "tenant.domo.com", "appStudio": {"appId": "base-app"}}))
            with env_module(DOMO_INSTANCE="tenant.domo.com", INVENTORY_SANDBOX_SUFFIX=SUFFIX, DOMO_ASSETS_PATH=str(own)) as mod:
                mod.IN_REPO_REGISTRY_PATH = base
                self.assertEqual(mod.load_registry(), {})

    def test_new_registry_roundtrips_scope_and_rejects_foreign_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            own = pathlib.Path(tmp) / "participant.json"
            with env_module(DOMO_INSTANCE="tenant.domo.com", INVENTORY_SANDBOX_SUFFIX=SUFFIX, DOMO_ASSETS_PATH=str(own)) as mod:
                self.assertTrue(mod.write_back_app_studio_ids({"appId": "own-app"}))
                self.assertEqual(mod.load_registry()["appStudio"]["appId"], "own-app")
                data = json.loads(own.read_text())
                self.assertEqual(data["instance"], "tenant.domo.com")
                self.assertEqual(data["sandboxSuffix"], SUFFIX)
                for key, value in (("instance", "other.domo.com"), ("sandboxSuffix", "another-participant")):
                    foreign = dict(data, **{key: value})
                    own.write_text(json.dumps(foreign))
                    self.assertEqual(mod.load_registry(), {})

    def test_state_path_is_participant_scoped(self):
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX) as m:
            p = str(m.registry_write_path())
            self.assertIn("/sandbox-", p)
            self.assertTrue(p.endswith("domo-assets.json"))
            self.assertNotEqual(m.registry_write_path(), m.IN_REPO_REGISTRY_PATH)

    def test_domo_assets_path_override_wins(self):
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX, DOMO_ASSETS_PATH="/tmp/probe/da.json") as m:
            self.assertEqual(str(m.registry_write_path()), "/tmp/probe/da.json")


class ProductionGuard(unittest.TestCase):
    def test_no_nameplate_blocks_every_write_command(self):
        with env_module() as m:
            for cmd in WRITE_COMMANDS:
                with self.assertRaises(SystemExit, msg=cmd + " should be blocked"):
                    m._production_write_guard(cmd)

    def test_read_only_commands_are_exempt(self):
        with env_module() as m:
            for cmd in READ_COMMANDS:
                m._production_write_guard(cmd)  # must not raise

    def test_nameplate_passes_the_guard(self):
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX) as m:
            for cmd in WRITE_COMMANDS:
                m._production_write_guard(cmd)  # must not raise

    def test_result_based_hole_is_closed(self):
        # Nameplate set AND APP_STUDIO_NAME forced to the production name:
        # app-studio must STILL be blocked (an input-presence check would miss this).
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX, APP_STUDIO_NAME="在庫入出庫管理ハンズオン") as m:
            self.assertEqual(m.APP_STUDIO_NAME, m.PRODUCTION_APP_STUDIO_NAME)
            with self.assertRaises(SystemExit):
                m._production_write_guard("app-studio")
            # Backend writes still pass because their names are tagged by the suffix.
            m._production_write_guard("apply")

    def test_allow_production_unlocks_for_maintainer(self):
        # ALLOW_PRODUCTION は配備先を取り違えないよう DOMO_INSTANCE の明示を要求する。
        # 明示したメンテナ経路は全書込コマンドが通る。
        with env_module(INVENTORY_ALLOW_PRODUCTION="1", DOMO_INSTANCE="my-instance.domo.com") as m:
            for cmd in WRITE_COMMANDS:
                m._production_write_guard(cmd)  # must not raise

    def test_allow_production_requires_explicit_instance(self):
        # ALLOW_PRODUCTION=1 だが DOMO_INSTANCE 未設定（＝既定の参照インスタンス maintenance-instance へ
        # サイレント配備する事故）は拒否する。override フラグがあっても配備先の明示は必須。
        with env_module(INVENTORY_ALLOW_PRODUCTION="1") as m:
            self.assertFalse((os.environ.get("DOMO_INSTANCE") or "").strip())
            for cmd in WRITE_COMMANDS:
                with self.assertRaises(SystemExit, msg=cmd + " must refuse ALLOW_PRODUCTION without explicit DOMO_INSTANCE"):
                    m._production_write_guard(cmd)
            # 読取専用コマンドはそもそもガード対象外（配備先未明示でも素通り）。
            for cmd in READ_COMMANDS:
                m._production_write_guard(cmd)  # must not raise


class SandboxFeManifestWiring(unittest.TestCase):
    """FE 完全隔離: サンドボックス sync-manifest は配布コピーの pro-code/manifest.json を直接配線し、
    トップレベル id を外す（＝続く `domo publish` が自分専用デザインを新規採番）。本番は id を保持。"""

    def _run_sync(self, mod, manifest_obj):
        with tempfile.TemporaryDirectory() as d:
            manifest_path = pathlib.Path(d) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            mod.MANIFEST_PATH = manifest_path
            _stub_discovery(mod)
            result = mod.sync_manifest(_FakeClient())
            written = json.loads(manifest_path.read_text(encoding="utf-8"))
            return result, written, manifest_path

    def test_sandbox_strips_top_level_id_and_writes_pro_code_manifest(self):
        seed = {"id": "e4e7b1d1-5c98-5cad-bd3c-ae902908a2af", "version": "1.0.0",
                "collectionsMapping": [{"name": "c", "id": "old"}],
                "datasetsMapping": [{"alias": "d", "dataSetId": "old", "fields": []}]}
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX) as m:
            result, written, manifest_path = self._run_sync(m, seed)
            self.assertTrue(result["sandbox"])
            self.assertTrue(result["designIdStripped"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["manifestPath"], str(manifest_path))  # 配布コピー自身へ書く
            self.assertNotIn("id", written)  # ryuu は id 省略で新規採番（空文字では失敗）＝キーごと除去

    def test_production_retains_top_level_id(self):
        seed = {"id": "e4e7b1d1-5c98-5cad-bd3c-ae902908a2af", "version": "1.0.0",
                "collectionsMapping": [{"name": "c", "id": "x"}],
                "datasetsMapping": [{"alias": "d", "dataSetId": "x", "fields": []}]}
        with env_module() as m:  # 名札なし＝本番
            result, written, _ = self._run_sync(m, seed)
            self.assertFalse(result["sandbox"])
            self.assertFalse(result["designIdStripped"])
            self.assertEqual(written.get("id"), seed["id"])  # design id は保持（初回publishで採番済）

    def test_app_studio_refuses_when_sandbox_id_not_yet_minted(self):
        # id を外した直後（publish 前）に app-studio を回すのは正順違反＝明確に停止する。
        seed = {"version": "1.0.0", "collectionsMapping": [], "datasetsMapping": []}
        with env_module(INVENTORY_SANDBOX_SUFFIX=SUFFIX) as m:
            with tempfile.TemporaryDirectory() as d:
                manifest_path = pathlib.Path(d) / "manifest.json"
                manifest_path.write_text(json.dumps(seed, ensure_ascii=False) + "\n", encoding="utf-8")
                m.MANIFEST_PATH = manifest_path
                with self.assertRaises(SystemExit):
                    m.app_studio(_FakeClient())

    def _version_fixture(self, mod, root, ce_version="1.0.0", active=True):
        bundle = root / "pro-code"
        assets = root / "code-engine"
        bundle.mkdir()
        assets.mkdir()
        mod.MANIFEST_PATH = bundle / "manifest.json"
        manifest = {"version": "2.0.0", "packagesMapping": [{"alias": "inventoryApi", "packageId": "old", "version": "9.9.9"}],
                    "workflowsMapping": [{"alias": "lowStockNotification", "modelId": "old", "version": "9.9.9"}]}
        mod.MANIFEST_PATH.write_text(json.dumps(manifest))
        (assets / "asset.json").write_text(json.dumps({"packageId": "old", "version": "9.9.9"}))
        _stub_discovery(mod)
        mod.list_packages = lambda client: [{"name": mod.PACKAGE_NAME, "id": "pkg-new"}]
        mod.resolve_workflow_model_id = lambda client: "wf-new"

        class Client:
            def request(self, method, path):
                if "codeengine" in path:
                    return {"version": ce_version}
                return {"versions": [{"version": "1.0.0", "active": active}, {"version": "99.0.0", "active": False}]}

        return Client(), manifest, assets / "asset.json"

    def test_fresh_instance_versions_replace_source_versions_and_asset_metadata(self):
        with env_module() as mod, tempfile.TemporaryDirectory() as tmp:
            client, _, asset_path = self._version_fixture(mod, pathlib.Path(tmp))
            mod.sync_manifest(client)
            written = json.loads(mod.MANIFEST_PATH.read_text())
            self.assertEqual(written["packagesMapping"][0]["version"], "1.0.0")
            self.assertEqual(written["workflowsMapping"][0]["version"], "1.0.0")
            self.assertEqual(json.loads(asset_path.read_text()), {"packageId": "pkg-new", "version": "1.0.0"})

    def test_unresolved_versions_abort_before_writing_any_binding(self):
        for ce_version, active in (("", True), ("1.0.0", False)):
            with self.subTest(ce_version=ce_version, active=active), env_module() as mod, tempfile.TemporaryDirectory() as tmp:
                client, manifest, _ = self._version_fixture(mod, pathlib.Path(tmp), ce_version, active)
                before = mod.MANIFEST_PATH.read_bytes()
                with self.assertRaises(RuntimeError):
                    mod.sync_manifest(client)
                self.assertEqual(mod.MANIFEST_PATH.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
