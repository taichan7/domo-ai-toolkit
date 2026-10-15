import contextlib
import importlib.util
import io
import json
import pathlib
import unittest
import tempfile
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("inventory_provision", ROOT / "scripts" / "provision_domo.py")
PROVISION = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(PROVISION)


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        response = self.responses.get((method, path))
        if isinstance(response, Exception):
            raise response
        if callable(response):
            return response(body)
        return response


class AppStudioProvisioningTests(unittest.TestCase):
    def _enter(self, context):
        value = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return value

    def setUp(self):
        # Test data is synthetic and independent of a maintainer's local registry.
        tmp = self._enter(tempfile.TemporaryDirectory())
        base = pathlib.Path(tmp)
        self.registry = {
            "appId": "900001", "viewId": "900002", "cardId": "900003",
            "proxyId": "proxy-test", "contextId": "context-test",
            "page2": {"viewId": "900004", "cardId": "900005", "contextId": ""},
        }
        registry = base / "domo-assets.json"
        registry.write_text(json.dumps({"instance": PROVISION.INSTANCE,
            "appStudio": self.registry, "proCode": {"designId": "design-test"}}))
        self._enter(patch.object(PROVISION, "IN_REPO_REGISTRY_PATH", registry))
        for attribute in ("MANIFEST_PATH", "DEV_GUIDE_MANIFEST_PATH"):
            source = getattr(PROVISION, attribute)
            manifest = json.loads(source.read_text(encoding="utf-8"))
            manifest.setdefault("id", "design-test-" + attribute.lower())
            target = base / (attribute.lower() + ".json")
            target.write_text(json.dumps(manifest, ensure_ascii=False))
            self._enter(patch.object(PROVISION, attribute, target))

    def _stub_write_back(self):
        """write_back_app_studio_ids を記録スタブへ差し替え、実 domo-assets.json への書込を防ぐ。

        app_studio() は末尾で解決IDを書き戻すため、素で走らせると実ファイルを書き換えうる。
        テストでは呼び出し引数だけ記録し、戻り値 False（＝変更なし相当）で疎通させる。
        """
        recorded = []
        original = PROVISION.write_back_app_studio_ids
        PROVISION.write_back_app_studio_ids = lambda *a, **k: recorded.append((a, k)) or False
        self.addCleanup(setattr, PROVISION, "write_back_app_studio_ids", original)
        return recorded

    def test_registered_app_and_card_are_reused_without_post(self):
        app_id = self.registry["appId"]
        view_id = self.registry["viewId"]
        card_id = self.registry["cardId"]
        page2 = self.registry["page2"]
        view2 = page2["viewId"]
        card2 = page2["cardId"]
        client = FakeClient({
            ("GET", f"api/content/v1/dataapps/{app_id}"): {"landingViewId": view_id, "views": [{"id": view_id}]},
            ("GET", f"api/content/v1/pages/{view_id}/cards"): [{"id": card_id, "title": PROVISION.APP_STUDIO_CARD_TITLE}],
            ("GET", f"api/content/v1/cards?urns={card_id}&parts=metadata%2Cproperties%2CchartMetadata"): [{
                "id": card_id,
                "metadata": {"fullpage": "false", "kpiDimensionWidth": "1.0", "kpiDimensionHeight": "1.0"},
            }],
            ("GET", f"api/content/v4/pages/{view_id}/layouts"): {},
            # 再利用カードの context は非空（domo-assets.json に実IDあり）。実 Domo は dict を返すので
            # ここも dict を返す（未モックだと FakeClient が None を返し context.get で落ちるため）。
            ("GET", f"domoapps/apps/v2/contexts/{self.registry['contextId']}"): {"designVersion": None},
            # ページ2は登録ピン経由で再利用（POST/作成なし）。
            ("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true"): {
                "views": [{"viewId": view_id}, {"viewId": view2}],
            },
            ("GET", f"api/content/v1/pages/{view2}/cards"): [{"id": card2, "title": PROVISION.DEV_GUIDE_CARD_TITLE}],
            ("GET", f"api/content/v4/pages/{view2}/layouts"): {},
        })

        # 実 domo-assets.json を触らせない（冪等再利用では書き戻しは発生しない想定だが防御的に固定）。
        recorded = self._stub_write_back()

        result = PROVISION.app_studio(client)

        self.assertEqual(result["appStudio"]["id"], app_id)
        self.assertEqual(result["proCodeCard"]["cardId"], card_id)
        self.assertEqual(result["page2"]["viewId"], view2)
        self.assertEqual(result["page2"]["cardId"], card2)
        self.assertFalse(any(method == "POST" for method, _, _ in client.calls))
        # 再利用でも書き戻しは呼ばれる（内部で「変更なし＝非書込」を判定する）。
        self.assertEqual(len(recorded), 1)
        self.assertEqual(recorded[0][0][0]["appId"], app_id)

    def test_card_metadata_mismatch_refuses_in_place_rewrite(self):
        card_id = "card-1"
        manifest = {"size": {"width": 1, "height": 1}}
        client = FakeClient({
            ("GET", f"api/content/v1/cards?urns={card_id}&parts=metadata%2Cproperties%2CchartMetadata"): [{
                "id": card_id,
                "metadata": {"chartType": "domoapp", "fullpage": "true", "kpiDimensionWidth": "8.0", "kpiDimensionHeight": "6.0"},
            }],
        })

        with self.assertRaisesRegex(RuntimeError, "refusing an in-place metadata rewrite"):
            PROVISION.validate_app_studio_card_metadata(client, card_id, manifest)

        self.assertFalse(any(method == "PUT" for method, _, _ in client.calls))

    def test_missing_registered_app_self_heals_by_discovery(self):
        # 削除済みの台帳IDから、同じ配備先に存在する同名アプリを再発見する。
        pinned_app = self.registry["appId"]
        disc_app = "discovered-app"
        disc_view = "discovered-view-1"
        disc_view2 = "discovered-view-2"
        disc_card = "discovered-card-1"
        disc_card2 = "discovered-card-2"
        design_id = json.loads(PROVISION.MANIFEST_PATH.read_text(encoding="utf-8"))["id"]
        error = PROVISION.DomoApiError("GET", f"api/content/v1/dataapps/{pinned_app}", 404, "not found")
        client = FakeClient({
            # 1) ピン留め appId は当該インスタンスに無い（404）。
            ("GET", f"api/content/v1/dataapps/{pinned_app}"): error,
            # 2) 名称で発見（同僚が作成済みの共有アプリ）→ 重複作成しない。
            ("GET", "api/content/v1/dataapps?limit=500&offset=0"): {
                "dataapps": [{"id": disc_app, "title": PROVISION.APP_STUDIO_NAME}],
            },
            ("GET", f"api/content/v1/dataapps/{disc_app}"): {
                "landingViewId": disc_view, "views": [{"id": disc_view}],
            },
            # ページ1カードはタイトル一致で再発見（作成しない）。
            ("GET", f"api/content/v1/pages/{disc_view}/cards"): [
                {"id": disc_card, "title": PROVISION.APP_STUDIO_CARD_TITLE},
            ],
            ("GET", f"api/content/v1/cards?urns={disc_card}&parts=metadata%2Cproperties%2CchartMetadata"): [{
                "id": disc_card,
                "metadata": {"fullpage": "false", "kpiDimensionWidth": "1.0", "kpiDimensionHeight": "1.0"},
            }],
            ("GET", f"api/content/v4/pages/{disc_view}/layouts"): {},
            ("GET", f"api/apps/v1/designs/{design_id}?parts=versions"): {},
            # ページ2＝開発者リファレンスも非ランディングビューでタイトル一致採用（作成しない）。
            ("GET", f"api/content/v1/dataapps/{disc_app}?includeHiddenViews=true"): {
                "views": [{"viewId": disc_view}, {"viewId": disc_view2}],
            },
            ("GET", f"api/content/v1/pages/{disc_view2}/cards"): [
                {"id": disc_card2, "title": PROVISION.DEV_GUIDE_CARD_TITLE},
            ],
            ("GET", f"api/content/v4/pages/{disc_view2}/layouts"): {},
        })

        recorded = self._stub_write_back()

        result = PROVISION.app_studio(client)

        # 停止せず（RuntimeError なし）、発見した共有アプリ／カードを再利用する。
        self.assertEqual(result["appStudio"]["id"], disc_app)
        self.assertEqual(result["proCodeCard"]["cardId"], disc_card)
        self.assertEqual(result["page2"]["cardId"], disc_card2)
        # 重複作成をしない＝POST が一切走らない（発見のみ）。
        self.assertFalse(any(method == "POST" for method, _, _ in client.calls))
        # 解決した実IDを書き戻す。参照インスタンス由来の proxy/context は復元不能なので空へクリア。
        self.assertEqual(len(recorded), 1)
        page1_args = recorded[0][0][0]
        self.assertEqual(page1_args["appId"], disc_app)
        self.assertEqual(page1_args["viewId"], disc_view)
        self.assertEqual(page1_args["cardId"], disc_card)
        self.assertEqual(page1_args["proxyId"], "")
        self.assertEqual(page1_args["contextId"], "")

    def test_mobile_layout_matches_static_reference_contract(self):
        view_id = "view-1"
        card_id = "card-1"
        layout = {
            "layoutId": "layout-1",
            "content": [{"contentKey": "3", "cardId": card_id}],
            "standard": {"template": [{"type": "CARD", "contentKey": "3"}]},
            "compact": {"template": [{"type": "CARD", "contentKey": "3"}]},
        }
        stored = {}
        client = FakeClient({
            ("GET", f"api/content/v4/pages/{view_id}/layouts"): layout,
            ("PUT", "api/content/v4/pages/layouts/layout-1"): lambda body: stored.update(body) or body,
        })

        PROVISION.configure_app_studio_layout(client, view_id, card_id)

        self.assertEqual(stored["standard"]["template"][0]["width"], 60)
        self.assertEqual(stored["standard"]["template"][0]["height"], 82)
        self.assertEqual(stored["compact"]["template"][0]["width"], 12)
        self.assertEqual(stored["compact"]["template"][0]["height"], 29)
        self.assertFalse(stored["isDynamic"])
        self.assertEqual(stored["standard"]["template"][1]["type"], "PAGE_BREAK")
        self.assertEqual(stored["standard"]["template"][1]["y"], 82)
        self.assertEqual(stored["compact"]["template"][1]["type"], "PAGE_BREAK")
        self.assertEqual(stored["compact"]["template"][1]["y"], 29)
        self.assertFalse(stored["content"][0]["fitToFrame"])
        self.assertTrue(stored["content"][0]["compactInteractionDefault"])
        # PC操作を最優先し interaction は既定（未設定＝操作許可）へ戻す。
        # interaction:DISABLED はモバイル青枠だけでなくPCのクリックも殺すため設定しない。
        self.assertNotIn("interaction", stored["content"][0])
        self.assertTrue(stored["content"][0]["hideWrench"])
        self.assertTrue(stored["content"][0]["editInAppViewer"])
        self.assertFalse(stored["content"][0]["hideMargins"])
        self.assertFalse(stored["content"][0]["hideBorder"])
        self.assertFalse(stored["printFriendly"])
        self.assertEqual(len(stored["content"]), 1)
        self.assertIn(("PUT", "api/content/v4/pages/layouts/layout-1/writelock", {}), client.calls)
        self.assertIn(("DELETE", "api/content/v4/pages/layouts/layout-1/writelock", None), client.calls)

    def test_card_creation_uses_distinct_server_generated_proxy(self):
        view_id = "view-1"
        title = "在庫入出庫・分析（Domo Mobile）"
        manifest = {
            "id": "design-1",
            "fullpage": False,
            "datasetsMapping": [],
            "collectionsMapping": [],
        }
        placement_path = "domoapps/apps/v2?" + PROVISION.urllib.parse.urlencode({
            "fullpage": "false",
            "pageId": view_id,
            "cardTitle": title,
        })

        def placement(body):
            self.assertEqual(body, {"contextId": "context-1"})
            return {"id": "proxy-1"}

        client = FakeClient({
            ("GET", f"api/content/v1/pages/{view_id}/cards"): [],
            ("POST", "domoapps/apps/v2/contexts"): {"id": "context-1"},
            ("POST", placement_path): placement,
            ("GET", f"api/content/v1/pages/{view_id}/cards?parts=metadata,properties,chartMetadata"): [
                {"id": "card-1", "title": title},
            ],
        })

        result = PROVISION.create_app_studio_card(client, view_id, manifest, title)

        self.assertEqual(result, {"cardId": "card-1", "proxyId": "proxy-1", "contextId": "context-1"})

    def test_layout_sizes_are_parameterized(self):
        # サイズはキーワード引数から流れる（ページ2は在庫ページと別サイズで呼べる）。
        view_id = "view-1"
        card_id = "card-1"
        layout = {
            "layoutId": "layout-1",
            "content": [{"contentKey": "3", "cardId": card_id}],
            "standard": {"template": [{"type": "CARD", "contentKey": "3"}]},
            "compact": {"template": [{"type": "CARD", "contentKey": "3"}]},
        }
        stored = {}
        client = FakeClient({
            ("GET", f"api/content/v4/pages/{view_id}/layouts"): layout,
            ("PUT", "api/content/v4/pages/layouts/layout-1"): lambda body: stored.update(body) or body,
        })

        PROVISION.configure_app_studio_layout(client, view_id, card_id, standard=(50, 70), compact=(10, 20))

        self.assertEqual(stored["standard"]["template"][0]["width"], 50)
        self.assertEqual(stored["standard"]["template"][0]["height"], 70)
        self.assertEqual(stored["standard"]["template"][1]["y"], 70)
        self.assertEqual(stored["compact"]["template"][0]["width"], 10)
        self.assertEqual(stored["compact"]["template"][0]["height"], 20)
        self.assertEqual(stored["compact"]["template"][1]["y"], 20)

    def test_page2_adopts_existing_card_by_title_without_post(self):
        # 登録ピンが無くても、非ランディングビューに同タイトルのカードが在れば採用（POSTなし）。
        app_id = "app-x"
        view1 = "v1"
        view2 = "v2"
        card2 = "c2"
        client = FakeClient({
            ("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true"): {
                "views": [{"viewId": view1}, {"viewId": view2}],
            },
            ("GET", f"api/content/v1/pages/{view2}/cards"): [{"id": card2, "title": PROVISION.DEV_GUIDE_CARD_TITLE}],
            ("GET", f"api/content/v4/pages/{view2}/layouts"): {},
        })

        result = PROVISION.ensure_app_studio_page(
            client, app_id, view1,
            manifest_path=PROVISION.DEV_GUIDE_MANIFEST_PATH,
            page_title=PROVISION.DEV_GUIDE_PAGE_TITLE,
            card_title=PROVISION.DEV_GUIDE_CARD_TITLE,
            standard=PROVISION.DEV_GUIDE_STANDARD,
            compact=PROVISION.DEV_GUIDE_COMPACT,
            registered_page=None,
        )

        self.assertEqual(result["viewId"], view2)
        self.assertEqual(result["cardId"], card2)
        self.assertFalse(any(method == "POST" for method, _, _ in client.calls))

    def test_page2_creates_page_when_absent(self):
        # 登録も既存カードも無ければ、add-view POST でページ2を作成しカードを埋め込む。
        app_id = "app-x"
        view1 = "v1"
        new_view = "v2"
        design_id = json.loads(PROVISION.DEV_GUIDE_MANIFEST_PATH.read_text(encoding="utf-8"))["id"]
        title = PROVISION.DEV_GUIDE_CARD_TITLE
        placement_path = "domoapps/apps/v2?" + PROVISION.urllib.parse.urlencode({
            "fullpage": "false",
            "pageId": new_view,
            "cardTitle": title,
        })
        validate_path = "api/content/v1/cards?" + PROVISION.urllib.parse.urlencode({
            "urns": "card2",
            "parts": "metadata,properties,chartMetadata",
        })
        client = FakeClient({
            ("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true"): {"views": [{"viewId": view1}]},
            ("GET", f"api/apps/v1/designs/{design_id}"): {"id": design_id},
            ("POST", f"api/content/v1/dataapps/{app_id}/views"): {"view": {"pageId": new_view}},
            ("GET", f"api/content/v1/pages/{new_view}/cards"): [],
            ("POST", "domoapps/apps/v2/contexts"): {"id": "ctx2"},
            ("POST", placement_path): {"id": "proxy2"},
            ("GET", f"api/content/v1/pages/{new_view}/cards?parts=metadata,properties,chartMetadata"): [
                {"id": "card2", "title": title},
            ],
            ("GET", validate_path): [{
                "id": "card2",
                "metadata": {"fullpage": "false", "kpiDimensionWidth": "1.0", "kpiDimensionHeight": "1.0"},
            }],
            ("GET", f"api/content/v4/pages/{new_view}/layouts"): {},
        })

        result = PROVISION.ensure_app_studio_page(
            client, app_id, view1,
            manifest_path=PROVISION.DEV_GUIDE_MANIFEST_PATH,
            page_title=PROVISION.DEV_GUIDE_PAGE_TITLE,
            card_title=title,
            standard=PROVISION.DEV_GUIDE_STANDARD,
            compact=PROVISION.DEV_GUIDE_COMPACT,
            registered_page=None,
        )

        self.assertEqual(result["viewId"], new_view)
        self.assertEqual(result["cardId"], "card2")
        self.assertEqual(result["proxyId"], "proxy2")
        self.assertEqual(result["contextId"], "ctx2")
        self.assertEqual(result["designId"], design_id)
        self.assertTrue(any(
            method == "POST" and path == f"api/content/v1/dataapps/{app_id}/views"
            for method, path, _ in client.calls
        ))

    def test_app_studio_export_removes_user_and_lock_state(self):
        cleaned = PROVISION.sanitize_app_studio_export({
            "title": "在庫入出庫管理",
            "owners": [{"id": "user-1"}],
            "nested": {"lockTimestamp": 123, "theme": {"name": "default"}},
        })

        self.assertEqual(cleaned, {"title": "在庫入出庫管理", "nested": {"theme": {"name": "default"}}})

    def test_export_emits_per_page_contexts_tolerating_empty_page2(self):
        # ページ2の contextId が空でも export は落ちず、pages[] にページ2を含み、
        # proCodeContexts は解決できたページ(=ページ1)だけを並べる。
        import tempfile
        registry = json.loads(PROVISION.IN_REPO_REGISTRY_PATH.read_text(encoding="utf-8"))
        reg = registry["appStudio"]
        app_id = reg["appId"]
        view1 = reg["viewId"]
        ctx1 = reg["contextId"]
        view2 = reg["page2"]["viewId"]
        p1_design = registry["proCode"]["designId"]
        client = FakeClient({
            ("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true"): {"views": [{"viewId": view1}, {"viewId": view2}]},
            ("GET", f"api/content/v3/stacks/{view1}"): {},
            ("GET", f"api/content/v1/pages/{view1}/cards"): [],
            ("GET", f"api/content/v4/pages/{view1}/layouts"): {},
            ("GET", f"api/content/v3/stacks/{view2}"): {},
            ("GET", f"api/content/v1/pages/{view2}/cards"): [],
            ("GET", f"api/content/v4/pages/{view2}/layouts"): {},
            ("GET", f"domoapps/apps/v2/contexts/{ctx1}"): {"designId": p1_design, "designVersion": ""},
            ("GET", f"api/apps/v1/designs/{p1_design}?parts=versions"): {"latestVersion": "9.9.9"},
        })
        original = PROVISION.APP_STUDIO_EXPORT_PATH
        with tempfile.TemporaryDirectory() as tmp:
            PROVISION.APP_STUDIO_EXPORT_PATH = pathlib.Path(tmp) / "app-studio.json"
            try:
                result = PROVISION.export_app_studio(client)
                snapshot = json.loads(PROVISION.APP_STUDIO_EXPORT_PATH.read_text(encoding="utf-8"))
            finally:
                PROVISION.APP_STUDIO_EXPORT_PATH = original

        self.assertEqual(result["viewCount"], 2)
        self.assertEqual(result["contextCount"], 1)  # ページ2は contextId 空→未掲載
        self.assertEqual(len(snapshot["pages"]), 2)
        page2_entry = next(page for page in snapshot["pages"] if page["viewId"] == view2)
        self.assertEqual(page2_entry["proCodeContext"], {})
        self.assertEqual(len(snapshot["proCodeContexts"]), 1)
        self.assertEqual(snapshot["proCodeContexts"][0]["viewId"], view1)

    def test_write_back_persists_resolved_ids_and_preserves_config(self):
        # 発見／作成で確定したIDを domo-assets.json へ書き戻す。identity ID だけ更新し、url など
        # 設定値・他ブロックは保持。proxy/context は空でも上書き（無効な参照値を確実に消す）。
        import tempfile
        seed = {
            "appStudio": {
                "appId": "old-app", "viewId": "old-view", "cardId": "old-card",
                "proxyId": "old-proxy", "contextId": "old-context",
                "url": "https://example.domo.com/app-studio/old-app",
                "hideWrench": True,
                "page2": {"viewId": "old-v2", "cardId": "old-c2", "proxyId": "old-p2",
                          "contextId": "old-ctx2", "designId": "old-design2",
                          "url": "https://example.domo.com/app-studio/old-app/pages/old-v2"},
            },
            "proCode": {"version": "9.9.9"},
        }
        original = PROVISION.IN_REPO_REGISTRY_PATH
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "domo-assets.json"
            path.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            PROVISION.IN_REPO_REGISTRY_PATH = path
            try:
                changed = PROVISION.write_back_app_studio_ids(
                    {"appId": "new-app", "viewId": "new-view", "cardId": "new-card",
                     "proxyId": "", "contextId": ""},
                    {"viewId": "new-v2", "cardId": "new-c2", "proxyId": "new-p2",
                     "contextId": "new-ctx2", "designId": "new-design2"},
                )
                written = json.loads(path.read_text(encoding="utf-8"))
                # 変更なしなら再書込しない（冪等パスでファイルを触らない）。
                unchanged = PROVISION.write_back_app_studio_ids(
                    {"appId": "new-app", "viewId": "new-view", "cardId": "new-card",
                     "proxyId": "", "contextId": ""},
                    {"viewId": "new-v2", "cardId": "new-c2", "proxyId": "new-p2",
                     "contextId": "new-ctx2", "designId": "new-design2"},
                )
            finally:
                PROVISION.IN_REPO_REGISTRY_PATH = original

        self.assertTrue(changed)
        self.assertFalse(unchanged)
        app = written["appStudio"]
        self.assertEqual(app["appId"], "new-app")
        self.assertEqual(app["viewId"], "new-view")
        self.assertEqual(app["cardId"], "new-card")
        self.assertEqual(app["proxyId"], "")     # 空で上書き＝無効な参照値を消す
        self.assertEqual(app["contextId"], "")
        self.assertEqual(app["hideWrench"], True)  # 設定値は保持
        self.assertEqual(app["url"], seed["appStudio"]["url"])  # url は触らない
        self.assertEqual(app["page2"]["cardId"], "new-c2")
        self.assertEqual(app["page2"]["designId"], "new-design2")
        self.assertEqual(app["page2"]["url"], seed["appStudio"]["page2"]["url"])  # 保持
        self.assertEqual(written["proCode"], {"version": "9.9.9"})  # 他ブロック不変

    """`trigger_appdb_sync` の即時同期起動と反映待ちの契約を固定する。"""

    def _collection(self, **overrides):
        base = {
            "id": "coll1",
            "name": PROVISION.COLLECTION_NAME,
            "datastoreId": "ds1",
            "datasourceId": "dsrc1",
            "syncEnabled": True,
            "syncRequired": True,
        }
        base.update(overrides)
        return base

    def test_kicks_export_and_returns_after_propagation(self):
        # 反映後（syncRequired=false・行数到達）のコレクションを list が返す状態にする。
        synced = self._collection(syncRequired=False)
        client = FakeClient({
            ("POST", "api/datastores/v2/collections/coll1/documents/query"): {"documents": [{}, {}, {}]},
            ("POST", "api/datastores/v1/export/ds1"): None,
            ("GET", "api/datastores/v1/collections?limit=1000&offset=0"): [synced],
            ("GET", "api/data/v3/datasources/dsrc1"): {"rowCount": 3},
        })

        result = PROVISION.trigger_appdb_sync(client, self._collection(), wait_seconds=5)

        # datastoreId をキーにしたエクスポート起動が1度だけ呼ばれる（DataSetへの直接書込みはしない）。
        self.assertIn(("POST", "api/datastores/v1/export/ds1", None), client.calls)
        self.assertFalse(result.get("syncRequired"))

    def test_skips_when_sync_disabled(self):
        client = FakeClient({})

        result = PROVISION.trigger_appdb_sync(client, self._collection(syncEnabled=False), wait_seconds=5)

        # 同期無効ならキックは意味を持たない。エクスポートPOSTを一切呼ばず入力をそのまま返す。
        self.assertFalse(any(path.startswith("api/datastores/v1/export/") for _, path, _ in client.calls))
        self.assertFalse(client.calls)
        self.assertEqual(result.get("syncEnabled"), False)

    def test_degrades_gracefully_when_export_fails(self):
        error = PROVISION.DomoApiError("POST", "api/datastores/v1/export/ds1", 500, "boom")
        client = FakeClient({
            ("POST", "api/datastores/v2/collections/coll1/documents/query"): {"documents": [{}]},
            ("POST", "api/datastores/v1/export/ds1"): error,
        })

        # エクスポート起動が失敗しても例外を投げず、定期同期に委ねて入力の collection を返す。
        result = PROVISION.trigger_appdb_sync(client, self._collection(), wait_seconds=5)

        self.assertEqual(result.get("datasourceId"), "dsrc1")
        # 反映待ちループには入らない（datasources のポーリングGETを呼ばない）。
        self.assertFalse(any(path.startswith("api/data/v3/datasources/") for _, path, _ in client.calls))


class CurrentUserResolutionTests(unittest.TestCase):
    """`current_user` は /users/me を主経路に、パッケージ owner を後方互換フォールバックとする。"""

    def test_resolves_from_users_me_without_package_probe(self):
        client = FakeClient({
            ("GET", "api/content/v2/users/me"): {"id": 1549238191, "displayName": "在庫 太郎"},
        })

        user = PROVISION.current_user(client)

        # id は文字列化して返す。displayName をそのまま名前に使う。
        self.assertEqual(user, {"id": "1549238191", "name": "在庫 太郎"})
        # /users/me で解決できたらパッケージ一覧の推測へは降りない。
        self.assertFalse(any(path.startswith("api/codeengine/v2/packages") for _, path, _ in client.calls))

    def test_falls_back_to_package_owner_when_me_is_empty(self):
        # /users/me が空(旧テナントや権限差)の場合のみ、パッケージ owner から解決する。
        client = FakeClient({
            ("GET", "api/content/v2/users/me"): {},
            ("GET", "api/codeengine/v2/packages?limit=1&offset=0"): {"packages": [{"ownerId": 42}]},
            ("GET", "api/content/v2/users/42"): {"displayName": "予備 花子"},
        })

        user = PROVISION.current_user(client)

        self.assertEqual(user, {"id": "42", "name": "予備 花子"})

    def test_raises_when_user_cannot_be_determined(self):
        # /users/me もパッケージ owner も空なら、apply を続行せず明示的に停止する。
        client = FakeClient({
            ("GET", "api/content/v2/users/me"): {},
            ("GET", "api/codeengine/v2/packages?limit=1&offset=0"): {"packages": []},
        })

        with self.assertRaisesRegex(RuntimeError, "Could not determine the authenticated Domo user"):
            PROVISION.current_user(client)


class AgentWorkflowDatasetGroundingTests(unittest.TestCase):
    """Finding 2 回帰: 通知Workflowの知識DataSetは、新規インスタンスでも実DataSet IDへ接地する。

    旧実装は manifest.json（参照インスタンスのGUID）を builder 内で読み、apply の早い段階で
    DataFlow 生成前に Workflow を配線していた。新規インスタンスでは Dashboard DataSet の実IDが
    未確定なため接地先が食い違い、verify の workflowAiAgentDatasetContextIds == dashboardDatasetId が
    2回目の apply まで満たせなかった。修正後は DataFlow 確定後の実IDを渡し、未確定時のみ manifest へ
    フォールバックする。
    """

    @staticmethod
    def _minimal_workflow_source():
        # builder が触る最小限のノード（Start / AI Agent＋sendEmail tool / End）だけを持つ器。
        return {
            "dataList": [],
            "schema": {"inputs": {}, "outputs": {}},
            "designElements": [
                {"type": "rootNode", "id": "r", "data": {"title": "", "description": "", "input": []}},
                {"type": "AI_AGENT", "id": "a", "data": {
                    "title": "", "description": "",
                    "agent": {"instructions": "", "context": {}, "tools": [{"functionName": "sendEmail", "id": "t"}]},
                    "prompt": {"value": []},
                }},
                {"type": "endNode", "id": "e", "data": {"title": ""}},
            ],
        }

    def test_manifest_dashboard_dataset_id_matches_manifest(self):
        # フォールバック用ヘルパは manifest 宣言の inventoryDashboard alias→物理ID を返す。
        manifest = json.loads((ROOT / "pro-code" / "manifest.json").read_text(encoding="utf-8"))
        expected = next(row["dataSetId"] for row in manifest["datasetsMapping"] if row.get("alias") == "inventoryDashboard")
        self.assertEqual(PROVISION.manifest_dashboard_dataset_id(), expected)

    def test_builder_grounds_context_to_passed_dataset_id(self):
        # 渡した実DataSet IDがそのままAIエージェントの知識contextへ入る（manifest値を読まない）。
        out = PROVISION.agent_email_workflow_definition(self._minimal_workflow_source(), "live-dataset-xyz")
        ai = next(node for node in out["designElements"] if node.get("type") == "AI_AGENT")
        self.assertEqual(ai["data"]["agent"]["context"]["datasets"], [{"id": "live-dataset-xyz"}])

    def test_workflow_start_message_name_matches_ce_constant_builder_and_seed(self):
        # 通知Workflowの起動は CE が messageName（開始タイルのタイトル）を送るため、次の3か所が
        # 一致していなければ起動は 400/404 で失敗する: ①CEソースの WORKFLOW_START_MESSAGE_NAME、
        # ②定義ビルダーが書く rootNode の title、③通知seedの rootNode title。
        source = (ROOT / "code-engine" / "inventory_service.py").read_text(encoding="utf-8")
        self.assertIn(f'WORKFLOW_START_MESSAGE_NAME = "{PROVISION.WORKFLOW_START_MESSAGE_NAME}"', source)
        seed = json.loads(PROVISION.WORKFLOW_SEED_PATH.read_text(encoding="utf-8"))
        seed_root = next(row for row in seed["designElements"] if row.get("type") == "rootNode")
        self.assertEqual(seed_root["data"]["title"], PROVISION.WORKFLOW_START_MESSAGE_NAME)
        built = PROVISION.agent_email_workflow_definition(self._minimal_workflow_source(), "live-dataset-xyz")
        built_root = next(row for row in built["designElements"] if row.get("type") == "rootNode")
        self.assertEqual(built_root["data"]["title"], PROVISION.WORKFLOW_START_MESSAGE_NAME)

    def test_builder_injects_exactly_the_consolidated_input_contract(self):
        # 集約通知の入力契約＝5項目(event_type/headline/shortage_lines/recipient_email/occurred_at)を
        # 3面(schema.inputs / dataList / root.data.input)すべてに揃えて注入する。旧版ソースには
        # headline/shortage_lines が無いため、欠けている入力を text 型で補い、余計な旧スカラーは残さない。
        expected = set(PROVISION.WORKFLOW_INPUT_FIELDS)
        self.assertEqual(len(expected), 5)
        out = PROVISION.agent_email_workflow_definition(self._minimal_workflow_source(), "live-dataset-xyz")
        schema_names = {row.get("name") for row in out["schema"]["inputs"].values()}
        datalist_names = {row.get("paramName") for row in out["dataList"] if row.get("id", "").startswith("var_")}
        root = next(node for node in out["designElements"] if node.get("type") == "rootNode")
        root_names = {row.get("paramName") for row in root["data"]["input"]}
        self.assertEqual(schema_names, expected)
        self.assertTrue(expected.issubset(datalist_names))   # var_ai_result 等の内部変数は許容
        self.assertEqual(root_names, expected)
        # 新規注入した2入力は text 型・必須で往復する。
        headline = next(row for row in out["schema"]["inputs"].values() if row.get("name") == "headline")
        self.assertEqual(headline["type"], "text")
        self.assertFalse(headline["isNullable"])
        # AIプロンプトは5入力すべてを変数として綴じ込む（削除済みの旧スカラーは綴じない）。
        ai = next(node for node in out["designElements"] if node.get("type") == "AI_AGENT")
        prompt_text = json.dumps(ai["data"]["prompt"]["value"], ensure_ascii=False)
        for field in expected:
            self.assertIn(field, prompt_text)
        for removed in ("item_code", "minimum_quantity", "shortage_quantity", "location_name"):
            self.assertNotIn(removed, prompt_text)

    def test_apply_wires_workflow_after_dataflow_with_live_dataset_id(self):
        # apply() の協調関数を差し替え、呼び出し順と Workflow へ渡る DataSet ID を捕捉する。
        calls = []
        captured = {}
        live_dataset_id = "live-9999-abcd"
        names = (
            "current_user", "ensure_collection", "ensure_workflow_model", "ensure_package", "deployed_source",
            "invoke_inventory_api", "refresh_collection", "trigger_appdb_sync",
            "ensure_dataflow", "trigger_dataflow", "ensure_agent_email_workflow", "output_dataset_id",
        )
        original = {name: getattr(PROVISION, name) for name in names}

        def record(label, value):
            calls.append(label)
            return value

        try:
            PROVISION.current_user = lambda c: {"id": "1", "name": "n"}
            PROVISION.ensure_collection = lambda c, uid="": record("ensure_collection", {"id": "col", "datastoreId": "ds", "datasourceId": "src"})
            # 通知Workflowモデルは CE 配備より先に確定する（CE ソースへ modelId を焼き込むため）。
            PROVISION.ensure_workflow_model = lambda c: record("ensure_workflow_model", {"modelId": "wm-1"})
            PROVISION.deployed_source = lambda *a, **k: ""
            PROVISION.ensure_package = lambda c, src: record("ensure_package", ({"id": "pkg"}, "1.0.0"))
            PROVISION.invoke_inventory_api = lambda c, pid, ver, op: record(f"invoke:{op}", None)
            PROVISION.refresh_collection = lambda c, t: record("refresh_collection", {"id": "col", "datasourceId": "src", "datastoreId": "ds"})
            PROVISION.trigger_appdb_sync = lambda c, col, t: record("trigger_appdb_sync", col)
            PROVISION.ensure_dataflow = lambda c, sid: record("ensure_dataflow", {"id": "2246"})
            PROVISION.trigger_dataflow = lambda c, df: record("trigger_dataflow", ("SUCCESS", "exec1"))
            PROVISION.output_dataset_id = lambda df: live_dataset_id

            def fake_ensure_wf(c, dashboard_dataset_id=""):
                calls.append("ensure_agent_email_workflow")
                captured["dashboard_dataset_id"] = dashboard_dataset_id
                return {"modelId": "m", "version": "1.0.9", "tileCount": 3, "aiAgentCount": 1, "aiAgentEmailToolCount": 1, "aiAgentDatasetContextCount": 1}

            PROVISION.ensure_agent_email_workflow = fake_ensure_wf

            client = FakeClient({("GET", "api/dataprocessing/v1/dataflows/2246"): {"id": "2246"}})
            PROVISION.apply(client, run_dataflow=True)
        finally:
            for name, fn in original.items():
                setattr(PROVISION, name, fn)

        # 核: 通知Workflowモデルの確定 → CE 配備（CE ソースへ modelId を焼き込む）の順序。
        self.assertLess(calls.index("ensure_workflow_model"), calls.index("ensure_package"))
        # 核: DataFlow 生成 → Workflow 配線 の順序。
        self.assertLess(calls.index("ensure_dataflow"), calls.index("ensure_agent_email_workflow"))
        # 核: Workflow へ渡るのは manifest 宣言値でなくライブ実DataSet ID。
        self.assertEqual(captured["dashboard_dataset_id"], live_dataset_id)

    def test_apply_passes_empty_id_when_no_datasource_so_workflow_falls_back(self):
        # 縮退枝: 標準同期が datasourceId をまだ払い出していない場合、DataFlow は生成されず
        # output_dataset_id({}) は "" を返す。apply は Workflow を無条件配線するため、この "" が
        # ensure_agent_email_workflow へ渡り、内部で manifest_dashboard_dataset_id() へフォールバックする。
        # （冪等な apply→verify→再apply モデルが最終的に実IDへ収束させる想定の設計挙動）。
        calls = []
        captured = {}
        # ここでは output_dataset_id は本物を使い、空DataFlow({}) が "" を返す実経路を通す。
        names = (
            "current_user", "ensure_collection", "ensure_workflow_model", "ensure_package", "deployed_source",
            "invoke_inventory_api", "refresh_collection", "trigger_appdb_sync",
            "ensure_dataflow", "trigger_dataflow", "ensure_agent_email_workflow",
        )
        original = {name: getattr(PROVISION, name) for name in names}

        def record(label, value):
            calls.append(label)
            return value

        try:
            PROVISION.current_user = lambda c: {"id": "1", "name": "n"}
            # datasourceId を最後まで払い出さない collection を返す。
            PROVISION.ensure_collection = lambda c, uid="": record("ensure_collection", {"id": "col", "datastoreId": "ds"})
            PROVISION.ensure_workflow_model = lambda c: record("ensure_workflow_model", {"modelId": "wm-1"})
            PROVISION.deployed_source = lambda *a, **k: ""
            PROVISION.ensure_package = lambda c, src: record("ensure_package", ({"id": "pkg"}, "1.0.0"))
            PROVISION.invoke_inventory_api = lambda c, pid, ver, op: record(f"invoke:{op}", None)
            PROVISION.refresh_collection = lambda c, t: record("refresh_collection", {"id": "col", "datastoreId": "ds"})
            PROVISION.trigger_appdb_sync = lambda c, col, t: record("trigger_appdb_sync", {"id": "col", "datastoreId": "ds"})
            PROVISION.ensure_dataflow = lambda c, sid: record("ensure_dataflow", {"id": "2246"})
            PROVISION.trigger_dataflow = lambda c, df: record("trigger_dataflow", ("SUCCESS", "exec1"))

            def fake_ensure_wf(c, dashboard_dataset_id=""):
                calls.append("ensure_agent_email_workflow")
                captured["dashboard_dataset_id"] = dashboard_dataset_id
                return {"modelId": "m", "version": "1.0.9", "tileCount": 3, "aiAgentCount": 1, "aiAgentEmailToolCount": 1, "aiAgentDatasetContextCount": 1}

            PROVISION.ensure_agent_email_workflow = fake_ensure_wf

            client = FakeClient({})
            PROVISION.apply(client, run_dataflow=True)
        finally:
            for name, fn in original.items():
                setattr(PROVISION, name, fn)

        # datasourceId 不在なので DataFlow 生成枝はスキップされる。
        self.assertNotIn("ensure_dataflow", calls)
        # それでも Workflow は無条件に配線される（縮退でも通知配線は保つ）。
        self.assertIn("ensure_agent_email_workflow", calls)
        # 渡るIDは空文字＝ensure_agent_email_workflow 側で manifest へフォールバックするトリガ。
        self.assertEqual(captured["dashboard_dataset_id"], "")

    def test_deployed_source_embeds_workflow_model_id_without_leaving_placeholders(self):
        # CE はサーバー側で通知Workflowを起動するため、その起動先 modelId をソースへ焼き込む。
        # 空（--skip-workflow）でもプレースホルダを残さない（CE 側は「未設定」として fail-soft する）。
        source = PROVISION.deployed_source("col-1", "user-1", "ds-1", "wm-1")
        self.assertIn('WORKFLOW_MODEL_ID = "wm-1"', source)
        self.assertNotIn("__WORKFLOW_MODEL_ID__", source)
        empty = PROVISION.deployed_source("col-1", "user-1", "ds-1", "")
        self.assertIn('WORKFLOW_MODEL_ID = ""', empty)
        self.assertNotIn("__WORKFLOW_MODEL_ID__", empty)


class WorkflowModelAutomationTests(unittest.TestCase):
    """境界①の自動化: 通知Workflowモデルを人手UIでなくAPIで発見/作成し、sendEmail版を実インスタンス値へ揃える。

    弱いAIモデルが「Workflowを手で作ってmodel IDを渡せ」と誤案内する温床（境界①）を潰すための層。
    ここではオフラインで（FakeClientで）以下を固める:
      - sendEmail版の解決（インスタンスごとに提供版が違う）と 2.1.17+ の recipientEmails=list 閾値。
      - 名称での「発見または作成」＝同じインスタンスへ複数回/複数名がデプロイしても重複を作らない。
      - read-only 解決（sync-manifest / verify が別プロセスでも誤IDを問い合わせない）。
    モジュールグローバル（WORKFLOW_MODEL_ID / _PINNED）を触るテストは setUp/tearDown で復元する。
    """

    def setUp(self):
        self._saved_id = PROVISION.WORKFLOW_MODEL_ID
        self._saved_pinned = PROVISION.WORKFLOW_MODEL_ID_PINNED

    def tearDown(self):
        PROVISION.WORKFLOW_MODEL_ID = self._saved_id
        PROVISION.WORKFLOW_MODEL_ID_PINNED = self._saved_pinned

    # --- sendEmail 版解決 -------------------------------------------------
    def test_resolve_send_email_uses_highest_scalar_version(self):
        # カタログ最高がスカラー宛先版(<2.1.17)なら、その最高版を使う。
        client = FakeClient({("GET", "api/workflow/v2/tools"): [
            {"name": "sendEmail", "packageId": PROVISION.SEND_EMAIL_PACKAGE_ID, "versions": ["2.1.12", "2.1.16", "2.1.9"]},
            {"name": "somethingElse", "packageId": "other", "versions": ["9.9.9"]},
        ]})
        pkg, version = PROVISION.resolve_send_email_package(client)
        self.assertEqual(pkg, PROVISION.SEND_EMAIL_PACKAGE_ID)
        self.assertEqual(version, "2.1.16")

    def test_resolve_send_email_prefers_advertised_scalar_over_higher_list(self):
        # 設計思想: カタログに list 版(最高)とスカラー版が混在するときは、非掲載の既知良好版へ賭けず、
        # 掲載された最高スカラー版(実行可能が保証される)を使う。これにより顧客インスタンスでも堅牢。
        client = FakeClient({("GET", "api/workflow/v2/tools"): [
            {"name": "sendEmail", "packageId": PROVISION.SEND_EMAIL_PACKAGE_ID, "versions": ["2.1.16", "2.1.18"]},
        ]})
        pkg, version = PROVISION.resolve_send_email_package(client)
        self.assertEqual(pkg, PROVISION.SEND_EMAIL_PACKAGE_ID)
        self.assertEqual(version, "2.1.16")  # not the hardcoded fallback, not the 2.1.18 list version

    def test_resolve_send_email_pins_scalar_when_only_list_versions(self):
        # カタログが list 宛先版(2.1.17+)しか提供しない場合、AI エージェント経由では list 宛先が
        # 送信失敗するため、宛先がスカラーの既知良好版へ固定する（通知WF v1.0.13/2.1.18 の実インシデント対応）。
        client = FakeClient({("GET", "api/workflow/v2/tools"): [
            {"name": "sendEmail", "packageId": PROVISION.SEND_EMAIL_PACKAGE_ID, "versions": ["2.1.17", "2.1.18"]},
        ]})
        pkg, version = PROVISION.resolve_send_email_package(client)
        self.assertEqual(pkg, PROVISION.SEND_EMAIL_PACKAGE_ID)
        self.assertEqual(version, PROVISION.KNOWN_GOOD_SCALAR_SEND_EMAIL_VERSION)
        self.assertLess(PROVISION._version_tuple(version), (2, 1, 17))

    def test_resolve_send_email_reads_scalar_version_field(self):
        client = FakeClient({("GET", "api/workflow/v2/tools"): [
            {"name": "sendEmail", "packageId": PROVISION.SEND_EMAIL_PACKAGE_ID, "version": "2.1.12"},
        ]})
        self.assertEqual(PROVISION.resolve_send_email_package(client), (PROVISION.SEND_EMAIL_PACKAGE_ID, "2.1.12"))

    def test_resolve_send_email_absent_returns_empty(self):
        # 見つからなければ ("","")。呼び出し側は seed 既定の版のまま進む（版差し替えを一切しない）。
        client = FakeClient({("GET", "api/workflow/v2/tools"): []})
        self.assertEqual(PROVISION.resolve_send_email_package(client), ("", ""))

    # --- sendEmail tool 版の in-place 差し替え ----------------------------
    def test_set_send_email_marks_recipient_list_at_2_1_17(self):
        tool = {"functionName": "sendEmail", "inputDescriptions": {"email_recipient": "Use the recipient_email workflow input exactly as supplied."},
                "inputs": [{"id": "email_recipient", "paramName": "recipientEmails", "isList": False, "aiDescription": "Use the recipient_email workflow input exactly as supplied."}]}
        PROVISION._set_send_email_tool_version(tool, "2.1.17")
        self.assertEqual(tool["packageVersion"], "2.1.17")
        self.assertEqual(tool["packageId"], PROVISION.SEND_EMAIL_PACKAGE_ID)
        recipient = tool["inputs"][0]
        self.assertTrue(recipient["isList"])
        # isList だけでなく宛先ガイダンスもリスト型へ揃える（スカラー誘導の自己矛盾を残さない）。
        self.assertIn("single-element list", recipient["aiDescription"])
        self.assertIn("single-element list", tool["inputDescriptions"]["email_recipient"])

    def test_set_send_email_keeps_scalar_below_2_1_17(self):
        tool = {"functionName": "sendEmail", "inputDescriptions": {"email_recipient": "Pass the recipient_email workflow input as a single-element list, e.g. [recipient_email]; exactly one recipient."},
                "inputs": [{"id": "email_recipient", "paramName": "recipientEmails", "isList": True, "aiDescription": "Pass the recipient_email workflow input as a single-element list, e.g. [recipient_email]; exactly one recipient."}]}
        PROVISION._set_send_email_tool_version(tool, "2.1.12")
        recipient = tool["inputs"][0]
        self.assertFalse(recipient["isList"])
        self.assertEqual(recipient["aiDescription"], "Use the recipient_email workflow input exactly as supplied.")
        self.assertEqual(tool["inputDescriptions"]["email_recipient"], "Use the recipient_email workflow input exactly as supplied.")

    def test_set_send_email_fixes_scalar_description_on_list_version(self):
        # 回帰: 既存ツールが scalar の aiDescription を持ったまま version 2.1.18(リスト型)へ揃えると、
        # 旧実装は isList=True だけ設定し aiDescription=「そのまま渡す(スカラー)」を残したため、
        # エージェントがスカラーを渡して送信が引数型不一致(IllegalArgumentException)で失敗した
        # （通知WF v1.0.13 の実インシデント）。_set_ は isList と宛先ガイダンスを必ず同時に版整合させる。
        tool = {"functionName": "sendEmail", "inputDescriptions": {"email_recipient": "Use the recipient_email workflow input exactly as supplied."},
                "inputs": [{"id": "email_recipient", "paramName": "recipientEmails", "isList": False, "aiDescription": "Use the recipient_email workflow input exactly as supplied."}]}
        PROVISION._set_send_email_tool_version(tool, "2.1.18")
        recipient = tool["inputs"][0]
        self.assertTrue(recipient["isList"])
        self.assertIn("single-element list", recipient["aiDescription"])
        self.assertIn("single-element list", tool["inputDescriptions"]["email_recipient"])

    def test_set_send_email_noops_on_empty_version_or_other_tool(self):
        untouched = {"functionName": "sendEmail", "inputs": [{"paramName": "recipientEmails", "isList": False}]}
        PROVISION._set_send_email_tool_version(untouched, "")
        self.assertNotIn("packageVersion", untouched)  # 空版なら一切触らない
        other = {"functionName": "createDataset", "inputs": []}
        PROVISION._set_send_email_tool_version(other, "2.1.17")
        self.assertNotIn("packageVersion", other)      # sendEmail 以外は対象外

    def test_apply_send_email_version_walks_agent_tools(self):
        definition = {"designElements": [
            {"type": "AI_AGENT", "data": {"agent": {"tools": [
                {"functionName": "sendEmail", "inputs": [{"paramName": "recipientEmails", "isList": False}]},
            ]}}},
        ]}
        PROVISION._apply_send_email_version(definition, "2.1.17")
        tool = definition["designElements"][0]["data"]["agent"]["tools"][0]
        self.assertEqual(tool["packageVersion"], "2.1.17")
        self.assertTrue(tool["inputs"][0]["isList"])

    # --- seed（空モデルへ 1.0.0 雛形を流し込む） --------------------------
    def test_seed_reuses_existing_version_without_writing(self):
        # 既に版があるモデルには触らない（べき等）。POST/PUT を一切呼ばず最新版番号を返す。
        client = FakeClient({("GET", "api/workflow/v1/models/m1"): {"versions": [{"version": "1.0.0"}, {"version": "1.0.3"}]}})
        self.assertEqual(PROVISION.seed_workflow_model(client, "m1", "2.1.17"), "1.0.3")
        self.assertFalse([c for c in client.calls if c[0] in {"POST", "PUT"}])

    def test_seed_creates_version_and_substitutes_email_version(self):
        # 空モデルには 1.0.0 を作り、実 sendEmail 版を差し込んだ3タイル雛形を PUT する。
        put_bodies = []
        client = FakeClient({
            ("GET", "api/workflow/v1/models/m2"): {"versions": []},
            ("POST", "api/workflow/v2/models/m2/versions"): {"version": "1.0.0"},
            ("PUT", "api/workflow/v2/models/m2/versions/1.0.0/definition"): lambda body: put_bodies.append(body) or {},
        })
        self.assertEqual(PROVISION.seed_workflow_model(client, "m2", "2.1.17"), "1.0.0")
        self.assertEqual(len(put_bodies), 1)
        ai = next(node for node in put_bodies[0]["designElements"] if node.get("type") == "AI_AGENT")
        email = next(t for t in ai["data"]["agent"]["tools"] if t.get("functionName") == "sendEmail")
        self.assertEqual(email["packageVersion"], "2.1.17")
        recipient = next(i for i in email["inputs"] if i.get("paramName") == "recipientEmails")
        self.assertTrue(recipient["isList"])

    # --- ensure_workflow_model（発見または作成・グローバル確定） ----------
    def test_ensure_model_pinned_never_creates(self):
        PROVISION.WORKFLOW_MODEL_ID = "pinned-x"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = True
        client = FakeClient({
            ("GET", "api/workflow/v2/tools"): [],
            ("GET", "api/workflow/v1/models/pinned-x"): {"versions": [{"version": "1.0.0"}]},
        })
        info = PROVISION.ensure_workflow_model(client)
        self.assertEqual((info["modelId"], info["pinned"], info["created"]), ("pinned-x", True, False))
        self.assertFalse([c for c in client.calls if c == ("POST", "api/workflow/v2/models", {"name": PROVISION.WORKFLOW_MODEL_NAME, "description": PROVISION.WORKFLOW_MODEL_DESCRIPTION})])

    def test_ensure_model_reuses_by_name_and_sets_global(self):
        # 同一インスタンスへ複数回/複数名がデプロイ: 名称一致で既存モデルを共有し重複を作らない。
        PROVISION.WORKFLOW_MODEL_ID = "stale-default"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = False
        client = FakeClient({
            ("GET", "api/workflow/v2/tools"): [],
            ("GET", "api/workflow/v1/models"): [{"name": PROVISION.WORKFLOW_MODEL_NAME, "id": "found-1"}],
            ("GET", "api/workflow/v1/models/found-1"): {"versions": [{"version": "1.0.2"}]},
        })
        info = PROVISION.ensure_workflow_model(client)
        self.assertEqual((info["modelId"], info["created"]), ("found-1", False))
        self.assertEqual(PROVISION.WORKFLOW_MODEL_ID, "found-1")  # グローバル確定
        self.assertFalse([c for c in client.calls if c[0] == "POST" and c[1] == "api/workflow/v2/models"])

    def test_ensure_model_creates_when_absent_and_seeds(self):
        PROVISION.WORKFLOW_MODEL_ID = "stale-default"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = False
        client = FakeClient({
            ("GET", "api/workflow/v2/tools"): [],
            ("GET", "api/workflow/v1/models"): [{"name": "someone-elses-model", "id": "other"}],
            ("POST", "api/workflow/v2/models"): {"id": "new-1"},
            ("GET", "api/workflow/v1/models/new-1"): {"versions": []},
            ("POST", "api/workflow/v2/models/new-1/versions"): {"version": "1.0.0"},
            ("PUT", "api/workflow/v2/models/new-1/versions/1.0.0/definition"): {},
        })
        info = PROVISION.ensure_workflow_model(client)
        self.assertEqual((info["modelId"], info["created"]), ("new-1", True))
        self.assertEqual(PROVISION.WORKFLOW_MODEL_ID, "new-1")
        self.assertTrue([c for c in client.calls if c[0] == "POST" and c[1] == "api/workflow/v2/models"])

    def test_ensure_model_raises_on_empty_create_id(self):
        PROVISION.WORKFLOW_MODEL_ID_PINNED = False
        client = FakeClient({
            ("GET", "api/workflow/v2/tools"): [],
            ("GET", "api/workflow/v1/models"): [],
            ("POST", "api/workflow/v2/models"): {},  # id が空 → 誤アセット解決を避けて即 raise
        })
        with self.assertRaises(RuntimeError):
            PROVISION.ensure_workflow_model(client)

    # --- resolve_workflow_model_id（read-only・作成しない） ---------------
    def test_resolve_id_pinned_returns_pin(self):
        PROVISION.WORKFLOW_MODEL_ID = "pin-1"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = True
        client = FakeClient({})  # pin 時はAPIを引かない
        self.assertEqual(PROVISION.resolve_workflow_model_id(client), "pin-1")

    def test_resolve_id_discovers_by_name(self):
        PROVISION.WORKFLOW_MODEL_ID = "stale-default"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = False
        client = FakeClient({("GET", "api/workflow/v1/models"): [
            {"name": "unrelated", "id": "x"},
            {"name": PROVISION.WORKFLOW_MODEL_NAME, "id": "found-9"},
        ]})
        self.assertEqual(PROVISION.resolve_workflow_model_id(client), "found-9")

    def test_resolve_id_falls_back_to_manifest_over_stale_default(self):
        # 名称で発見できないとき、モジュール既定（保守用ID）でなく manifest 宣言値を返す。
        # ＝顧客 manifest へ保守用IDを焼き込む事故を防ぐ安全なフォールバック。
        declared = "published-workflow-on-selected-instance"
        PROVISION.WORKFLOW_MODEL_ID = "SENTINEL-must-not-be-returned"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = False
        client = FakeClient({("GET", "api/workflow/v1/models"): []})
        with tempfile.TemporaryDirectory() as tmp:
            manifest = pathlib.Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"workflowsMapping": [{"modelId": declared}]}))
            with patch.object(PROVISION, "MANIFEST_PATH", manifest):
                resolved = PROVISION.resolve_workflow_model_id(client)
        self.assertEqual(resolved, declared)
        self.assertNotEqual(resolved, "SENTINEL-must-not-be-returned")

    def test_unbound_manifest_does_not_reuse_stale_module_state(self):
        PROVISION.WORKFLOW_MODEL_ID = "stale-other-instance"
        PROVISION.WORKFLOW_MODEL_ID_PINNED = False
        with tempfile.TemporaryDirectory() as tmp:
            manifest = pathlib.Path(tmp) / "manifest.json"
            manifest.write_text('{"workflowsMapping": [{"modelId": ""}]}')
            with patch.object(PROVISION, "MANIFEST_PATH", manifest):
                resolved = PROVISION.resolve_workflow_model_id(FakeClient({}))
        self.assertEqual(resolved, "")


class _FakeClock:
    """時間を進めない決定論的クロック。trigger_dataflow の待ちループを実時間なしで回すため、
    time.time()/time.sleep() を差し替える（sleep で仮想時間だけ進める）。"""

    def __init__(self, start=1000.0):
        self.t = start

    def time(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


class DataFlowRunToleranceTests(unittest.TestCase):
    """Inc2: DataFlow 長時間耐性。待ち上限の打ち切りを「失敗」にせず、本当の失敗だけ止め、
    実行中の execution を二重に投げない（反復/複数名デプロイ安全）ことを検証する。"""

    DF = {"id": "42"}
    LIST = ("GET", "api/dataprocessing/v1/dataflows/42/executions?limit=1&offset=0")
    POST = ("POST", "api/dataprocessing/v1/dataflows/42/executions")

    def _poll(self, execution_id):
        return ("GET", f"api/dataprocessing/v1/dataflows/42/executions/{execution_id}")

    def test_running_at_deadline_returns_running_without_raising(self):
        # 待ち上限を超えても RUNNING のままなら失敗にせず RUNNING を返す（例外を投げない）。
        client = FakeClient({
            self.LIST: [{"id": "old", "state": "SUCCESS"}],  # 直近は終端 → 新規実行
            self.POST: {"id": "run-1"},
            self._poll("run-1"): {"state": "RUNNING"},
        })
        orig = PROVISION.time
        PROVISION.time = _FakeClock()
        try:
            state, exec_id = PROVISION.trigger_dataflow(client, self.DF, wait_seconds=20)
        finally:
            PROVISION.time = orig
        self.assertEqual(state, "RUNNING")
        self.assertEqual(exec_id, "run-1")

    def test_success_returns_success(self):
        client = FakeClient({
            self.LIST: [{"id": "old", "state": "SUCCESS"}],
            self.POST: {"id": "run-2"},
            self._poll("run-2"): {"state": "SUCCESS"},
        })
        self.assertEqual(PROVISION.trigger_dataflow(client, self.DF, wait_seconds=20), ("SUCCESS", "run-2"))

    def test_terminal_failure_raises(self):
        client = FakeClient({
            self.LIST: [],
            self.POST: {"id": "run-3"},
            self._poll("run-3"): {"state": "FAILED_DATA_FLOW"},
        })
        with self.assertRaises(RuntimeError):
            PROVISION.trigger_dataflow(client, self.DF, wait_seconds=20)

    def test_reuses_in_flight_execution_without_posting(self):
        # 実行中（非終端）の execution があれば再利用し、新規実行を POST しない。
        def _post_forbidden(_body):
            raise AssertionError("must not POST a new execution while one is in flight")

        client = FakeClient({
            self.LIST: [{"id": "777", "state": "RUNNING"}],
            self.POST: _post_forbidden,
            self._poll("777"): {"state": "SUCCESS"},
        })
        state, exec_id = PROVISION.trigger_dataflow(client, self.DF, wait_seconds=20)
        self.assertEqual((state, exec_id), ("SUCCESS", "777"))
        self.assertEqual([c for c in client.calls if c[0] == "POST"], [])

    def test_posts_new_run_when_latest_execution_is_terminal(self):
        # 直近が終端（失敗含む）なら再利用せず新規実行を投げる。
        client = FakeClient({
            self.LIST: [{"id": "old", "state": "FAILED"}],
            self.POST: {"id": "fresh"},
            self._poll("fresh"): {"state": "SUCCESS"},
        })
        state, exec_id = PROVISION.trigger_dataflow(client, self.DF, wait_seconds=20)
        self.assertEqual((state, exec_id), ("SUCCESS", "fresh"))
        self.assertIn((self.POST[0], self.POST[1], {}), client.calls)

    def test_list_failure_falls_back_to_post(self):
        # 実行一覧の取得に失敗しても致命でない（空扱い → 新規実行）。
        client = FakeClient({
            self.LIST: PROVISION.DomoApiError("GET", self.LIST[1], 500, "boom"),
            self.POST: {"id": "run-x"},
            self._poll("run-x"): {"state": "SUCCESS"},
        })
        self.assertEqual(PROVISION.trigger_dataflow(client, self.DF, wait_seconds=20), ("SUCCESS", "run-x"))


class CollectionOwnerAwarenessTests(unittest.TestCase):
    """`ensure_collection` の owner-awareness 情報ログ（同一インスタンスへ複数名がデプロイする運用）。

    既存コレクションを再利用するとき、所有者が自分と異なれば「他者所有だが再利用する
    （削除・再作成しない）」旨を情報表示する。所有者が同じ／不明なら黙る。いずれの場合も
    再利用は共通（PUT を出さない＝スキーマ一致）で、判断や停止はしない（best-effort）。
    """

    COLLECTIONS = ("GET", "api/datastores/v1/collections?limit=1000&offset=0")

    def _client_with_owner(self, owner_field):
        # 期待スキーマと完全一致する既存コレクションを返し、再利用枝（PUT なし）へ入れる。
        schema = json.loads(PROVISION.SCHEMAS_PATH.read_text(encoding="utf-8"))["collections"][0]
        existing = {"id": "col-1", "name": PROVISION.COLLECTION_NAME, "schema": {"columns": schema["columns"]}}
        existing.update(owner_field)
        return FakeClient({self.COLLECTIONS: {"collections": [existing]}})

    def _run(self, client, current_user_id):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            result = PROVISION.ensure_collection(client, current_user_id)
        return result, buffer.getvalue()

    def test_owner_helper_reads_defensively(self):
        self.assertEqual(PROVISION._collection_owner_id({"owner": 42}), "42")
        self.assertEqual(PROVISION._collection_owner_id({"ownerId": "u-9"}), "u-9")
        self.assertEqual(PROVISION._collection_owner_id({"createdBy": "u-7"}), "u-7")
        self.assertEqual(PROVISION._collection_owner_id({}), "")

    def test_note_printed_when_owner_differs(self):
        client = self._client_with_owner({"owner": "colleague-2"})
        result, out = self._run(client, current_user_id="me-1")
        self.assertEqual(PROVISION._id(result), "col-1")
        self.assertIn("owned by another user", out)
        self.assertIn("colleague-2", out)
        self.assertIn("reused AppDB collection", out)  # 再利用枝を通っている
        self.assertFalse(any(method == "PUT" for method, _, _ in client.calls))

    def test_silent_when_owner_matches(self):
        client = self._client_with_owner({"owner": "me-1"})
        _, out = self._run(client, current_user_id="me-1")
        self.assertNotIn("owned by another user", out)

    def test_silent_when_owner_unknown(self):
        client = self._client_with_owner({})  # 所有者フィールドなし
        _, out = self._run(client, current_user_id="me-1")
        self.assertNotIn("owned by another user", out)


if __name__ == "__main__":
    unittest.main()
