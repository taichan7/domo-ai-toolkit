#!/usr/bin/env python3
"""provision_workflows.py の「ゼロから配備（provision）」経路の特性化テスト（オフライン・ネットワーク不要）。

配布の正しさの契約を固定する: 顧客インスタンスへ配備するとき、保守用インスタンス（maintenance-instance）の
GUID を**焼き込まず**、対象環境の実 ID へ再束縛し、レイアウトは崩れない。ライブ API はこのテストでは
叩かず（`request` をスタブ）、純粋なビルド/再束縛/発見ロジックの分岐を網羅する。

実行: python3 tests/test_provision_workflows.py
"""
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("provision_workflows", ROOT / "scripts" / "provision_workflows.py")
pw = importlib.util.module_from_spec(_spec)
sys.modules["provision_workflows"] = pw
_spec.loader.exec_module(pw)

# 保守用インスタンス（snapshot）に焼かれている GUID。顧客配備ではこれが残ってはならない。
SNAP_COLLECTION = "2693a918-74c0-5160-bffe-75275cf39489"
SNAP_SUMMARY_DS = "37754c30-644a-5f64-95fa-a161552c90b3"
# 配備先（顧客）の実 ID を模した別値。
NEW_COLLECTION = "11111111-aaaa-bbbb-cccc-222222222222"
NEW_SUMMARY_DS = "33333333-dddd-eeee-ffff-444444444444"
NEW_SUB_MODEL = "99999999-9999-9999-9999-999999999999"


def _subflow_refs(definition):
    return sorted({(e.get("data") or {}).get("modelId")
                   for e in definition["designElements"] if e.get("type") == "SUB_FLOW"})


def _report_types(definition):
    out = []
    for e in definition["designElements"]:
        if e.get("type") == "SUB_FLOW":
            out.append(next((i.get("value") for i in (e.get("data") or {}).get("input") or []
                             if i.get("paramName") == "report_type"), None))
    return sorted(out)


def _collection_values(definition):
    return [v.get("value") for v in definition.get("dataList") or [] if v.get("id") == pw.VAR_COLLECTION]


def _query_ds_values(definition):
    return [(e.get("data") or {}).get("dataset", {}).get("value")
            for e in definition["designElements"] if e.get("type") == "DATASET_QUERY_TASK"]


class BuildWf01FromScratch(unittest.TestCase):
    """新規（空）顧客インスタンス: snapshot を seed に、全束縛を実 ID へ再束縛する。"""

    def setUp(self):
        self._orig_sub = pw.SUBFLOW_MODEL_ID

    def tearDown(self):
        pw.SUBFLOW_MODEL_ID = self._orig_sub

    def test_rebinds_all_instance_specific_ids(self):
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", NEW_COLLECTION, NEW_SUMMARY_DS, wf01_created_new=True)
        self.assertEqual(_collection_values(d), [NEW_COLLECTION])
        self.assertEqual(set(_query_ds_values(d)), {NEW_SUMMARY_DS})
        self.assertEqual(_subflow_refs(d), [NEW_SUB_MODEL], "SUB_FLOW は新規作成した統合サブWFを指すべき")
        self.assertEqual(_report_types(d), ["company", "store"], "両ブランチ(店舗/全社)が report_type を保持")

    def test_no_maintenance_instance_guids_leak(self):
        import json
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", NEW_COLLECTION, NEW_SUMMARY_DS, wf01_created_new=True)
        blob = json.dumps(d, ensure_ascii=False)
        self.assertNotIn(SNAP_COLLECTION, blob, "保守用コレクション GUID が顧客配備に焼き込まれている")
        self.assertNotIn(SNAP_SUMMARY_DS, blob, "保守用データセット GUID が顧客配備に焼き込まれている")

    def test_layout_is_clean_and_ci_shaped(self):
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", NEW_COLLECTION, NEW_SUMMARY_DS, wf01_created_new=True)
        self.assertEqual(pw.validate_layout(d), [], "レイアウト検証(重なり/経路貫通)は0件であるべき")
        els = d["designElements"]
        self.assertEqual(sum(1 for e in els if e.get("type") == "endNode"), 2, "CI流は終了ノード2つ")
        self.assertEqual(sum(1 for e in els if e.get("type") == "intermediateCatchEventNode"), 1, "店舗ループに待機タイマー1つ")
        self.assertFalse(any((e.get("data") or {}).get("metadata", {}).get("packageId") == pw.DEDUPE_CE_PACKAGE_ID for e in els),
                         "重複除去 CE ノードは撤去済みであるべき")

    def test_sets_global_subflow_model_id_for_wiring(self):
        pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", NEW_COLLECTION, NEW_SUMMARY_DS, wf01_created_new=True)
        self.assertEqual(pw.SUBFLOW_MODEL_ID, NEW_SUB_MODEL,
                         "_ensure_subflow_input が読むグローバルを変換前に確定させるべき")


class RebindGuards(unittest.TestCase):
    """束縛が解決できないとき（空）に snapshot 値を上書き破壊しない（loud fail は cmd_provision 側）。"""

    def setUp(self):
        self._orig_sub = pw.SUBFLOW_MODEL_ID

    def tearDown(self):
        pw.SUBFLOW_MODEL_ID = self._orig_sub

    def test_empty_collection_preserves_snapshot_value(self):
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", "", NEW_SUMMARY_DS, wf01_created_new=True)
        self.assertEqual(_collection_values(d), [SNAP_COLLECTION], "空の解決値で CollectionId を潰してはならない")

    def test_empty_summary_preserves_snapshot_value(self):
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", NEW_COLLECTION, "", wf01_created_new=True)
        self.assertEqual(set(_query_ds_values(d)), {SNAP_SUMMARY_DS}, "空の解決値で dataset.value を潰してはならない")


class BuildWf01FromLive(unittest.TestCase):
    """既存インスタンス: ライブ定義を変換（created_new=False）。snapshot を live のスタブで差し替えて検証。"""

    def setUp(self):
        self._orig = (pw.get_definition, pw.highest_version, pw.SUBFLOW_MODEL_ID)
        import json
        base = json.loads((ROOT / "workflow" / "WF-01_main_loop.json").read_text(encoding="utf-8"))
        if isinstance(base.get("savedJson"), str):
            base = json.loads(base["savedJson"])
        pw.get_definition = lambda mid, ver: __import__("copy").deepcopy(base)
        pw.highest_version = lambda mid: "1.0.20"

    def tearDown(self):
        pw.get_definition, pw.highest_version, pw.SUBFLOW_MODEL_ID = self._orig

    def test_live_transform_matches_scratch_bindings(self):
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.5", NEW_COLLECTION, NEW_SUMMARY_DS, wf01_created_new=False)
        self.assertEqual(_collection_values(d), [NEW_COLLECTION])
        self.assertEqual(set(_query_ds_values(d)), {NEW_SUMMARY_DS})
        self.assertEqual(_subflow_refs(d), [NEW_SUB_MODEL])
        self.assertEqual(pw.validate_layout(d), [])


class DiscoverOrCreate(unittest.TestCase):
    """ensure_model / resolve_collection_id の発見・作成分岐（request をスタブ）。"""

    def setUp(self):
        self._orig_request = pw.request
        self.calls = []

    def tearDown(self):
        pw.request = self._orig_request

    def test_ensure_model_found_reuses_without_post(self):
        def fake(method, path, body=None):
            self.calls.append((method, path))
            if method == "GET" and path.startswith("api/workflow/v1/models?"):
                return {"models": [{"id": "existing-123", "name": "WF-X"}]}
            raise AssertionError(f"unexpected call {method} {path}")
        pw.request = fake
        mid, found = pw.ensure_model("WF-X", "desc", apply=True)
        self.assertEqual((mid, found), ("existing-123", True))
        self.assertFalse(any(m == "POST" for m, _ in self.calls), "既存発見時は POST しない（重複作成しない）")

    def test_ensure_model_not_found_creates_on_apply(self):
        def fake(method, path, body=None):
            if method == "GET":
                return {"models": [{"id": "other", "name": "別物"}]}
            if method == "POST" and path == "api/workflow/v2/models":
                return {"id": "new-456"}
            raise AssertionError(f"unexpected call {method} {path}")
        pw.request = fake
        mid, found = pw.ensure_model("WF-NEW", "desc", apply=True)
        self.assertEqual((mid, found), ("new-456", False), "未存在+apply は作成し found=False(=新規なので版1.0.0を建てる)")

    def test_ensure_model_not_found_dryrun_no_create(self):
        pw.request = lambda method, path, body=None: {"models": []} if method == "GET" else (_ for _ in ()).throw(AssertionError("POST in dry-run"))
        mid, found = pw.ensure_model("WF-NEW", "desc", apply=False)
        self.assertEqual((mid, found), ("", False), "未存在+dry-run は作成しない")

    def test_resolve_collection_id_by_name(self):
        def fake(method, path, body=None):
            if method == "GET" and path.startswith("api/datastores/v1/collections"):
                return {"collections": [{"id": "col-A", "name": "別コレクション"},
                                        {"id": "col-B", "name": pw.BUSINESS_COLLECTION_NAME}]}
            raise AssertionError(f"unexpected call {method} {path}")
        pw.request = fake
        self.assertEqual(pw.resolve_collection_id(), "col-B")

    def test_resolve_collection_id_missing_returns_empty(self):
        pw.request = lambda method, path, body=None: {"collections": [{"id": "x", "name": "無関係"}]}
        self.assertEqual(pw.resolve_collection_id(), "", "未存在は空文字（cmd_provision が apply 時に loud fail する）")

    def test_resolve_collection_id_paginates_beyond_first_page(self):
        # BK-004: 業務コレクションが1ページ目(1000件)より後ろにあっても全ページを辿って発見する
        # （単一ページ打ち切りだと取りこぼし→空文字→apply で誤って再作成しかねない）。
        page1 = [{"id": f"c{i}", "name": f"other-{i}"} for i in range(1000)]
        def fake(method, path, body=None):
            if method == "GET" and path == "api/datastores/v1/collections?limit=1000&offset=0":
                return {"collections": page1}
            if method == "GET" and path == "api/datastores/v1/collections?limit=1000&offset=1000":
                return {"collections": [{"id": "col-B", "name": pw.BUSINESS_COLLECTION_NAME}]}
            raise AssertionError(f"unexpected call {method} {path}")
        pw.request = fake
        self.assertEqual(pw.resolve_collection_id(), "col-B")  # 2ページ目の既存を発見


class ManualTriggerSafety(unittest.TestCase):
    def setUp(self):
        self.old_request = pw.request
        self.calls = []
        self.rows = [{"id": "timer-1", "modelId": NEW_SUB_MODEL, "type": "TIMER", "deletedAt": None},
                     {"id": "manual-1", "modelId": NEW_SUB_MODEL, "type": "MANUAL", "deletedAt": None},
                     {"id": "test-1", "modelId": NEW_SUB_MODEL, "type": "TEST", "deletedAt": None}]
        def request(method, path, body=None):
            self.calls.append((method, path))
            if method == "DELETE":
                self.rows[0]["deletedAt"] = "2026-10-15"
                return None
            if "/triggers/model/" in path:
                return self.rows
            return self.rows[0]
        pw.request = request

    def tearDown(self):
        pw.request = self.old_request

    def test_deletes_only_timer_and_verifies_it_is_gone(self):
        result = pw.ensure_manual_only(NEW_SUB_MODEL, True)
        self.assertEqual(result["removedCount"], 1)
        self.assertEqual(result["scheduleCount"], 0)
        self.assertEqual([p for m, p in self.calls if m == "DELETE"], ["api/workflow/v2/triggers/timer-1"])

    def test_dry_run_does_not_delete(self):
        self.assertEqual(pw.ensure_manual_only(NEW_SUB_MODEL, False)["scheduleCount"], 1)
        self.assertFalse(any(m == "DELETE" for m, _ in self.calls))

    def test_foreign_trigger_aborts_without_writes(self):
        self.rows[0]["modelId"] = "foreign-model"
        with self.assertRaises(RuntimeError):
            pw.ensure_manual_only(NEW_SUB_MODEL, True)
        self.assertFalse(any(m == "DELETE" for m, _ in self.calls))

    def test_missing_deleted_marker_is_not_a_success(self):
        pw.request = lambda method, path, body=None: self.rows if "/model/" in path else self.rows[0]
        with self.assertRaises(RuntimeError):
            pw.ensure_manual_only(NEW_SUB_MODEL, True)


class ReportCollectionBinding(unittest.TestCase):
    def test_new_package_embeds_the_discovered_collection(self):
        calls = []

        def request(method, path, body=None):
            calls.append((method, path, body))
            if path.startswith("api/datastores/v1/collections?"):
                return [{"id": NEW_COLLECTION, "name": pw.BUSINESS_COLLECTION_NAME}]
            if path.startswith("api/codeengine/v2/packages?"):
                return []
            if method == "POST" and path == "api/codeengine/v2/packages":
                return {"id": "created-package", "version": "1.0.0"}
            return {}

        with patch.object(pw, "request", side_effect=request):
            pw.ensure_report_api_package(True, NEW_SUB_MODEL, NEW_SUMMARY_DS)
        source = next(body["code"] for method, path, body in calls
                      if method == "POST" and path == "api/codeengine/v2/packages")
        self.assertIn('REPORT_COLLECTION_ID = "' + NEW_COLLECTION + '"', source)
        self.assertNotIn("__REPORT_COLLECTION_ID__", source)

    def test_missing_collection_aborts_before_package_creation(self):
        with patch.object(pw, "request", return_value=[]) as request:
            with self.assertRaisesRegex(RuntimeError, "AppDB"):
                pw.ensure_report_api_package(True, NEW_SUB_MODEL, NEW_SUMMARY_DS)
        self.assertTrue(all(call.args[0] == "GET" for call in request.call_args_list))


class ExecutorEmailThreading(unittest.TestCase):
    """実行者メール executor_email が WF-02 入力／WF-01 start フォーム・SUB_FLOW 入力に通る（既存宛先に実行者を追加）。"""

    def setUp(self):
        # send_email_tool() のパッケージ版 GET をオフライン化（ファイル版を使う）。build/scratch は元々ネット不要。
        self._orig = (pw.SUBFLOW_MODEL_ID, pw.request)
        pw.request = lambda *a, **k: {}

    def tearDown(self):
        pw.SUBFLOW_MODEL_ID, pw.request = self._orig

    def test_subflow_declares_optional_executor_email_input(self):
        d = pw.subflow_definition("pkg", "1.0.0")
        schema = d["schema"]["inputs"]
        self.assertIn(pw.INPUT_EXECUTOR_EMAIL_ID, schema)
        self.assertEqual(schema[pw.INPUT_EXECUTOR_EMAIL_ID]["name"], "executor_email")
        self.assertTrue(schema[pw.INPUT_EXECUTOR_EMAIL_ID]["isNullable"], "任意＝店舗ブランチ呼び出しを壊さない")
        self.assertIn(pw.VAR_EXECUTOR_EMAIL, [v["id"] for v in d["dataList"]])
        root = next(e for e in d["designElements"] if e.get("type") == "rootNode")
        exec_input = next(i for i in root["data"]["input"] if i["paramName"] == "executor_email")
        self.assertFalse(exec_input["required"], "executor_email フォーム入力は required=False")

    def test_company_ai_surfaces_executor_email_store_does_not(self):
        import json
        d = pw.subflow_definition("pkg", "1.0.0")
        company = next(e for e in d["designElements"] if e.get("id") == "ai_company")
        store = next(e for e in d["designElements"] if e.get("id") == "ai_store")
        self.assertIn("executor_email", json.dumps(company["data"]["prompt"]["value"], ensure_ascii=False))
        self.assertNotIn("executor_email", json.dumps(store["data"]["prompt"]["value"], ensure_ascii=False))

    def test_company_send_email_recipientEmails_guides_to_executor(self):
        d = pw.subflow_definition("pkg", "1.0.0")
        company = next(e for e in d["designElements"] if e.get("id") == "ai_company")
        send = next(t for t in company["data"]["agent"]["tools"] if t.get("functionName") == "sendEmail")
        rc = next(f for f in send["inputs"] if f["paramName"] == "recipientEmails")
        self.assertIn("executor_email", str(rc.get("aiDescription") or ""))

    def test_wf01_start_form_and_company_subflow_pass_executor_email(self):
        d = pw.build_wf01_definition(NEW_SUB_MODEL, "1.0.0", NEW_COLLECTION, NEW_SUMMARY_DS, wf01_created_new=True)
        root = next(e for e in d["designElements"] if e.get("type") == "rootNode")
        self.assertIn("executor_email", [i.get("paramName") for i in root["data"].get("input") or []])
        self.assertIn(pw.VAR_EXECUTOR_EMAIL, [v.get("id") for v in d.get("dataList") or []])
        # F1: message-start の data.executor_email が束縛されるよう schema.inputs にも宣言（rootNode.input と対）。
        wf01_schema = (d.get("schema") or {}).get("inputs") or {}
        self.assertIn(pw.INPUT_EXECUTOR_EMAIL_ID, wf01_schema, "WF-01 schema.inputs に executor_email が必要")
        self.assertTrue(wf01_schema[pw.INPUT_EXECUTOR_EMAIL_ID]["isNullable"])
        company_sub = next(e for e in d["designElements"] if e.get("type") == "SUB_FLOW"
                           and next((i.get("value") for i in e["data"].get("input") or []
                                     if i.get("paramName") == "report_type"), None) == "company")
        exec_in = next(i for i in company_sub["data"]["input"] if i.get("paramName") == "executor_email")
        self.assertEqual(exec_in["mappedTo"], pw.VAR_EXECUTOR_EMAIL)
        self.assertEqual(pw.validate_layout(d), [], "executor_email 追加後もレイアウトは崩れない")


class PinnedSubflowVersionGuard(unittest.TestCase):
    """BK-005: released 親へ *ピンする* サブ版は active(released) 必須。active_version が draft へ
    フォールバックするのに対し、ピン用途の active_version_for_pin は active 皆無なら release を促して止める。"""

    def setUp(self):
        self._orig = pw.request

    def tearDown(self):
        pw.request = self._orig

    def _meta(self, versions):
        pw.request = lambda method, path, body=None: {"versions": versions}

    def test_returns_highest_active_version_not_higher_draft(self):
        self._meta([{"version": "1.0.0", "active": True}, {"version": "1.0.3", "active": True},
                    {"version": "2.0.0", "active": False}])  # 2.0.0 は未 release の draft
        self.assertEqual(pw.active_version_for_pin("m"), "1.0.3")  # active の最大を選ぶ（draft は無視）

    def test_raises_when_no_active_version_where_lax_resolver_would_pin_a_draft(self):
        self._meta([{"version": "1.0.0", "active": False}, {"version": "1.0.1", "active": False}])  # draft のみ
        self.assertEqual(pw.active_version("m")[0], "1.0.1")  # 緩い版は未 release の draft へフォールバック
        with self.assertRaises(RuntimeError):
            pw.active_version_for_pin("m")  # ピン用途は draft を返さず明示停止（divergence）


if __name__ == "__main__":
    unittest.main(verbosity=2)
