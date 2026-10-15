#!/usr/bin/env python3
"""provision_domo.reconcile_app_studio_context の特性化テスト（ネットワーク非依存）。

背景: manifest に alias（trend / dept）を追加しても、埋込済みカードの App Framework
context mapping は自動追随しない。未マッピングの alias は proxy で解決できず、FE は
graceful degrade（トレンド空表示・事業部タブ非表示）に落ちる。本関数は manifest を
正として context mapping を冪等に同期する（2026-09-16 の music-yamaha-dx 事象の回帰ガード）。

固定する契約:
- 差分なしなら PUT しない（changed:false）。
- 差分ありなら GET→PUT→GET で検証し、mapping/collections を manifest へ揃える。
- dataSetId 空の alias（未 materialize のインスタンス）は送らない。
- PUT 後の検証 GET が不一致なら RuntimeError（中途半端な反映を成功扱いしない）。
- contextId 未解決は警告のみで changed:false（既存 discovery 経路を壊さない）。
"""
import importlib.util
import pathlib
import unittest

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
