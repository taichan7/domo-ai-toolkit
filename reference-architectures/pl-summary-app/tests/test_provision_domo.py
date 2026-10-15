#!/usr/bin/env python3
"""provision_domo.reconcile_app_studio_context の特性化テスト（ネットワーク非依存）。

背景: manifest に alias（trend / dept）を追加しても、埋込済みカードの App Framework
context mapping は自動追随しない。未マッピングの alias は proxy で解決できず、FE は
graceful degrade（トレンド空表示・事業部タブ非表示）に落ちる。本関数は manifest を
正として context mapping を冪等に同期する（2026-09-16 の別インスタンスでの事象の回帰ガード）。

固定する契約:
- 差分なしなら PUT しない（changed:false）。
- 差分ありなら GET→PUT→GET で検証し、mapping/collections を manifest へ揃える。
- dataSetId 空の alias（未 materialize のインスタンス）は送らない。
- PUT 後の検証 GET が不一致なら RuntimeError（中途半端な反映を成功扱いしない）。
- contextId 未解決は警告のみで changed:false（既存 discovery 経路を壊さない）。
"""
import importlib.util
import contextlib
import io
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("provision_domo", ROOT / "scripts" / "provision_domo.py")
provision_domo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision_domo)

CONTEXT_ID = "ctx-1"
MANIFEST = {
    "id": "design-1",
    "datasetsMapping": [
        {"alias": "summary", "dataSetId": "ds-summary", "fields": []},
        {"alias": "trend", "dataSetId": "ds-trend", "fields": []},
        {"alias": "dept", "dataSetId": "", "fields": []},  # 未 materialize は送らない
    ],
    "collectionsMapping": [{"name": "店舗別損益AI要約", "id": "col-1"}],
}


class FakeClient:
    def __init__(self, initial, after_put=None):
        self.initial = initial
        self.after_put = after_put if after_put is not None else initial
        self.calls = []
        self._get_count = 0

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if method == "GET":
            self._get_count += 1
            return self.initial if self._get_count == 1 else self.after_put
        if method == "PUT":
            return None
        raise AssertionError(f"unexpected {method} {path}")


class ReconcileAppStudioContextTest(unittest.TestCase):
    def test_server_normalized_package_binding_is_equivalent(self):
        parameter = {"name": "operation", "alias": "operation", "type": "text", "value": None,
                     "nullable": True, "isList": False, "children": [], "displayName": "operation"}
        binding = {"name": "service", "alias": "plReportApi", "packageId": "pkg-1", "version": "1.0.1",
                   "functionName": "pl_report_api", "parameters": [parameter], "output": {}}
        context = {"mapping": [{"alias": "summary", "dataSetId": "ds-summary", "fields": []},
                               {"alias": "trend", "dataSetId": "ds-trend", "fields": []}],
                   "collections": [{"name": "店舗別損益AI要約", "id": "col-1"}],
                   "packageMapping": [{k: v for k, v in binding.items() if k != "name"}]}
        context["packageMapping"][0]["parameters"] = [{k: v for k, v in parameter.items() if k != "displayName"}]
        client = FakeClient(context)
        result = provision_domo.reconcile_app_studio_context(client, CONTEXT_ID, {**MANIFEST, "packagesMapping": [binding]})
        self.assertFalse(result["changed"])

    def test_missing_context_is_a_blocker_when_ce_is_mapped(self):
        with self.assertRaises(RuntimeError):
            provision_domo.reconcile_app_studio_context(FakeClient({}), "", {**MANIFEST, "packagesMapping": [{"alias": "plReportApi"}]})

    def test_no_diff_does_not_put(self):
        context = {
            "id": CONTEXT_ID,
            "designId": "design-1",
            "designVersion": None,
            "mapping": [
                {"alias": "summary", "dataSetId": "ds-summary", "fields": []},
                {"alias": "trend", "dataSetId": "ds-trend", "fields": []},
            ],
            "collections": [{"name": "店舗別損益AI要約", "id": "col-1"}],
        }
        client = FakeClient(context)
        result = provision_domo.reconcile_app_studio_context(client, CONTEXT_ID, MANIFEST)
        self.assertFalse(result["changed"])
        self.assertEqual([c[0] for c in client.calls], ["GET"])

    def test_adds_missing_alias_and_verifies(self):
        before = {
            "id": CONTEXT_ID,
            "designId": "design-1",
            "designVersion": None,
            "mapping": [{"alias": "summary", "dataSetId": "ds-summary", "fields": []}],
            "collections": [{"name": "店舗別損益AI要約", "id": "col-1"}],
        }
        after = {
            **before,
            "mapping": [
                {"alias": "summary", "dataSetId": "ds-summary", "fields": []},
                {"alias": "trend", "dataSetId": "ds-trend", "fields": []},
            ],
        }
        client = FakeClient(before, after_put=after)
        result = provision_domo.reconcile_app_studio_context(client, CONTEXT_ID, MANIFEST)
        self.assertTrue(result["changed"])
        self.assertEqual([c[0] for c in client.calls], ["GET", "PUT", "GET"])
        payload = client.calls[1][2]
        aliases = sorted(row["alias"] for row in payload["mapping"])
        self.assertEqual(aliases, ["summary", "trend"])  # dataSetId 空の dept は送らない
        self.assertEqual(payload["collections"], [{"name": "店舗別損益AI要約", "id": "col-1"}])
        self.assertEqual(payload["id"], CONTEXT_ID)
        self.assertEqual(payload["designId"], "design-1")

    def test_put_not_persisted_raises(self):
        before = {
            "id": CONTEXT_ID,
            "designId": "design-1",
            "designVersion": None,
            "mapping": [{"alias": "summary", "dataSetId": "ds-summary", "fields": []}],
            "collections": [],
        }
        client = FakeClient(before, after_put=before)  # PUT が効いていない
        with self.assertRaises(RuntimeError):
            provision_domo.reconcile_app_studio_context(client, CONTEXT_ID, MANIFEST)

    def test_missing_context_id_warns_and_skips(self):
        client = FakeClient({})
        result = provision_domo.reconcile_app_studio_context(client, "", MANIFEST)
        self.assertFalse(result["changed"])
        self.assertEqual(client.calls, [])


class CurrentArchitectureVerification(unittest.TestCase):
    COLLECTION = "11111111-2222-4333-8444-555555555555"

    def verify(self, *, code_collection=None, missing_alias=None, wrong_alias=None, legacy_only=False):
        mod = provision_domo
        names = {"summary": mod.SUMMARY_OUTPUT_NAME, "detail": mod.DETAIL_OUTPUT_NAME,
                 "trend": mod.TREND_OUTPUT_NAME, "dept": mod.DEPT_OUTPUT_NAME}
        flow = {"id": "flow-test", "inputs": [{"dataSourceId": "input-test"}], "actions": [],
                "outputs": [{"dataSourceName": name, "dataSourceId": "ds-" + alias}
                            for alias, name in names.items() if alias != missing_alias]}
        manifest = {"collectionsMapping": [{"id": self.COLLECTION}],
                    "datasetsMapping": [{"alias": alias, "dataSetId": "wrong" if alias == wrong_alias else "ds-" + alias} for alias in names],
                    "packagesMapping": [{"alias": "plReportApi", "packageId": "pkg-report", "version": "1.0.4"}]}

        class Client:
            def request(self, method, path):
                if "dataflows/flow-test" in path:
                    return flow
                if "packages/pkg-report/versions/1.0.4?" in path:
                    return {"functions": [{"name": "pl_report_api", "isPrivate": False}],
                            "code": 'REPORT_COLLECTION_ID = "' + (code_collection or CurrentArchitectureVerification.COLLECTION) + '"\n'}
                if "api/data/v3/datasources/" in path:
                    return {"rowCount": 10}
                raise AssertionError(path)

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            path = pathlib.Path(tmp) / "manifest.json"
            path.write_text(json.dumps(manifest))
            stack.enter_context(patch.object(mod, "MANIFEST_PATH", path))
            stack.enter_context(patch.object(mod, "list_collections", return_value=[{"id": self.COLLECTION, "name": mod.BUSINESS_COLLECTION_NAME}]))
            packages = [{"id": "legacy-only", "name": mod.PACKAGE_NAME}] if legacy_only else [{"id": "pkg-report"}]
            stack.enter_context(patch.object(mod, "list_packages", return_value=packages))
            stack.enter_context(patch.object(mod, "list_dataflows", return_value=[{"id": "flow-test", "name": mod.DATAFLOW_NAME}]))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            return mod.verify(Client())

    def test_verifies_active_report_api_and_existing_input_without_legacy_assets(self):
        result = self.verify()
        self.assertTrue(result["ok"])
        self.assertEqual(result["codeEngineId"], "pkg-report")
        self.assertEqual(result["seedMode"], "existing-flow-input")

    def test_legacy_package_cannot_substitute_for_the_active_report_api(self):
        self.assertFalse(self.verify(legacy_only=True)["ok"])

    def test_report_api_bound_to_a_foreign_collection_fails(self):
        self.assertFalse(self.verify(code_collection="foreign-collection")["ok"])

    def test_missing_or_wrong_trend_and_department_bindings_fail(self):
        for alias in ("trend", "dept"):
            with self.subTest(alias=alias):
                self.assertFalse(self.verify(missing_alias=alias)["ok"])
                self.assertFalse(self.verify(wrong_alias=alias)["ok"])

    def test_data_provisioning_does_not_create_unused_legacy_ce(self):
        mod = provision_domo
        with contextlib.ExitStack() as stack:
            for name, value in (("_guard_production_write", None), ("current_user", {"id": "test-user"}),
                                ("resolve_seed_dataset", ({"id": "seed-test"}, "ds-seed")),
                                ("ensure_business_collection", {"id": self.COLLECTION}),
                                ("ensure_dataflow", {"id": "flow-test"})):
                stack.enter_context(patch.object(mod, name, return_value=value))
            legacy = stack.enter_context(patch.object(mod, "ensure_package"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            result = mod.apply(object(), False)
        legacy.assert_not_called()
        self.assertEqual(result["codeEngine"]["status"], "deferred-to-workflow-provisioner")


class RegistryScopeTest(unittest.TestCase):
    def test_registry_roundtrip_requires_instance_and_name_tag(self):
        mod = provision_domo
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(mod, "_registry_path", return_value=pathlib.Path(tmp) / "state.json"), \
             patch.object(mod, "INSTANCE", "tenant.domo.com"), \
             patch.object(mod, "_sandbox_suffix", return_value="participant"):
            mod._write_registry({"appStudio": {"appId": "own-app"}})
            own = mod._read_registry()
            self.assertEqual(own["appStudio"]["appId"], "own-app")
            for key, value in (("instance", "other.domo.com"), ("sandboxSuffix", "another-participant")):
                mod._registry_path().write_text(json.dumps(dict(own, **{key: value})))
                self.assertEqual(mod._read_registry(), {})
            mod._registry_path().write_text('[]')
            self.assertEqual(mod._read_registry(), {})


class AppIdentityTest(unittest.TestCase):
    def test_recovers_only_the_exact_card_not_a_same_design_preview(self):
        class Client:
            def request(self, method, path, body=None):
                if path.startswith("api/apps"):
                    return {"referencingCards": [{"id": "other-card", "domoapp": {"id": "preview"}},
                                                {"id": "card-1", "domoapp": {"id": "proxy-1"}}]}
                assert path == "domoapps/apps/v2/proxy-1"
                return {"designId": "design-1", "context": {"id": "ctx-1", "designId": "design-1"}}
        self.assertEqual(provision_domo.resolve_app_studio_identity(Client(), {"id": "design-1"}, "card-1"),
                         {"proxyId": "proxy-1", "contextId": "ctx-1"})


if __name__ == "__main__":
    unittest.main()
