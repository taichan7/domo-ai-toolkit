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

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("provision_workflows", ROOT / "scripts" / "provision_workflows.py")
pw = importlib.util.module_from_spec(_spec)
sys.modules["provision_workflows"] = pw
_spec.loader.exec_module(pw)

# 保守用インスタンス（snapshot）に焼かれている GUID。顧客配備ではこれが残ってはならない。
SNAP_COLLECTION = "ca132957-d14d-4fa0-9c69-3e6721d27141"
SNAP_SUMMARY_DS = "e05581f1-d70a-474d-91f3-f5a2080c9d05"
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
