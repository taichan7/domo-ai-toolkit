#!/usr/bin/env python3
"""report_api.py（pl_report_api｜レポート保存 CE）の特性化テスト。

実行: python3 pl-summary-app/tests/test_report_api.py

なぜこのテストか:
    pl_report_api は Domo Workflows の AI エージェントがツールとして呼ぶデプロイ済みロジックで、
    operation="save" は AppDB へ保存した上で**同一 doc_key の旧版を物理削除**する破壊的操作。
    「重複除去を保存へ畳み込む」設計（reference-app と同じ）なので、安全不変条件を固定する:
      ① 作成した当の文書は絶対に消さない
      ② サーバー createdOn が**厳密に古い**同一 doc_key だけ消す（同時刻・未知時刻・新しい側は保持）
      ③ 掃除失敗でも作成成功は ok:True（重複蓄積を避ける）
      ④ ★必須フィールド（doc_key/store_id/location_name/analysis_html）が欠けた不完全保存は POST 前に
         弾き、**既存の正レポートを巻き添え削除しない**（CI の _validate_document 相当の門番）
      ⑤ generated_at は空だけでなく ISO 不正値も現在時刻へ正規化（画面の降順ソートを壊さない）
    ソースは一切変更しない（デプロイ済み CE バンドルに触れない）。

読み込みの都合:
    report_api.py は関数内で `import codeengine`（Domo 実行環境のみ）するため、各テストで
    sys.modules["codeengine"].send_request をインメモリ代役へ差し替える。
"""
import importlib.util
import json
import os
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("codeengine", types.ModuleType("codeengine"))

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "..", "code-engine", "report_api.py")
_spec = importlib.util.spec_from_file_location("report_api", os.path.abspath(_MODULE_PATH))
ra = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ra  # importlib 読込の定石
_spec.loader.exec_module(ra)

GUID = "11111111-2222-4333-8444-555555555555"
ra.REPORT_COLLECTION_ID = GUID


class _FakeAppDB:
    """codeengine.send_request のインメモリ代役（AppDB シミュレータ）。

    POST create は id と createdOn を採番して格納（createdOn は seq 昇順＝後に作るほど新しい）。
    POST query は content.doc_key 一致を返す。DELETE bulk は id を除去する。
    seed で既存文書（任意の createdOn）を事前投入でき、create_fail / delete_fail で失敗を注入する。
    """

    def __init__(self, seed=None, create_fail=False, delete_fail=False, hide_created=False):
        self.docs = {}
        self.seq = 0
        self.create_fail = create_fail
        self.delete_fail = delete_fail
        self.hide_created = hide_created  # True: 作成直後の文書を query から隠す（read-after-write ラグ再現）
        self.deleted_ids = []
        self.invisible_ids = set()
        for d in seed or []:
            self.docs[d["id"]] = d

    def send_request(self, method, path, body=None):
        m = method.lower()
        base = path.split("?")[0]
        if m == "post" and base.endswith("/documents"):
            if self.create_fail:
                return {}  # id なし応答 → REQUEST_NOT_SAVED
            self.seq += 1
            doc = {"id": f"new{self.seq}", "createdOn": f"2026-10-05T00:00:{self.seq:02d}+00:00",
                   "content": body["content"]}
            self.docs[doc["id"]] = doc
            if self.hide_created:
                self.invisible_ids.add(doc["id"])  # ラグ: 作成直後は query にまだ現れない
            return {"id": doc["id"]}
        if m == "post" and "/documents/query" in base:
            key = body["content.doc_key"]["$eq"]
            # AppDB は documents/query を limit/offset（クエリ文字列）でページングする。fake も同契約を
            # 再現し、_save の複数ページ掃引（BK-016）と作成直後の不可視（BK-007）を検証可能にする。
            params = dict(p.split("=", 1) for p in path.split("?", 1)[1].split("&")) if "?" in path else {}
            limit = int(params.get("limit", "100000"))
            offset = int(params.get("offset", "0"))
            matched = [d for d in self.docs.values()
                       if (d.get("content") or {}).get("doc_key") == key and d["id"] not in self.invisible_ids]
            return matched[offset:offset + limit]
        if m == "delete" and "/documents/bulk" in base:
            if self.delete_fail:
                raise RuntimeError("boom")
            ids = path.split("ids=")[1].split(",")
            for i in ids:
                self.docs.pop(i, None)
                self.deleted_ids.append(i)
            return {"ok": True}
        return None

    def install(self):
        sys.modules["codeengine"].send_request = self.send_request
        return self

    def live_keys(self, doc_key):
        return [d for d in self.docs.values() if (d.get("content") or {}).get("doc_key") == doc_key]


def _full(key="K", html="report body", store="JPN001", name="銀座店", **extra):
    """必須フィールドを満たす完全なレポート文書（store/company 両ブランチの共通スキーマ）。"""
    doc = {"doc_key": key, "store_id": store, "location_name": name, "analysis_html": html}
    doc.update(extra)
    return doc


def _seed(doc_id, key, created, html="x"):
    return {"id": doc_id, "createdOn": created,
            "content": {"doc_key": key, "generated_at": created, "store_id": "JPN001",
                        "location_name": "銀座店", "analysis_html": html}}


class ManualWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.old_model = ra.MAIN_WORKFLOW_MODEL_ID
        self.old_submodel = ra.SUB_WORKFLOW_MODEL_ID
        ra.MAIN_WORKFLOW_MODEL_ID = GUID
        ra.SUB_WORKFLOW_MODEL_ID = "22222222-2222-4222-8222-222222222222"
        self.calls = []
        self.rows = []
        self.model = {"versions": [{"version": "1.0.9", "active": True},
                                   {"version": "1.0.21", "active": True},
                                   {"version": "9.0.0", "active": False}]}
        self.instance = "11111111-1111-4111-8111-111111111111"
        self.start_error = False
        sys.modules["codeengine"].send_request = self.send

    def tearDown(self):
        ra.MAIN_WORKFLOW_MODEL_ID = self.old_model
        ra.SUB_WORKFLOW_MODEL_ID = self.old_submodel

    def send(self, method, path, body=None):
        self.calls.append((method, path, body))
        if "/instances?" in path:
            return self.rows
        if path.endswith("/instances/message"):
            if self.start_error:
                raise TimeoutError("network timeout")
            return {"id": self.instance, "status": "IN_PROGRESS"}
        if "/instances/" in path:
            return {"id": self.instance, "modelId": GUID, "status": "COMPLETED"}
        if "/versions/" in path:
            return {"savedJson": json.dumps({"designElements": [{"type": "rootNode", "data": {"title": "開始（AI要約）"}}]})}
        if "/models/" in path:
            return self.model
        raise AssertionError(path)

    def test_start_uses_only_embedded_model_latest_active_and_live_start_title(self):
        result = ra.pl_report_api("start", {})
        self.assertTrue(result["ok"])
        self.assertEqual(result["model_version"], "1.0.21")
        self.assertEqual(self.calls[-1], ("post", "api/workflow/v1/instances/message",
                         {"messageName": "開始（AI要約）", "modelId": GUID, "version": "1.0.21", "data": {}}))
        self.assertEqual(result["instance_id"], self.instance)

    def test_start_threads_valid_executor_email_into_workflow_data(self):
        # 実行者メールは Workflow start の data.executor_email に scalar で載る（既存メールの宛先に実行者を追加）。
        result = ra.pl_report_api("start", {"executor_email": "exec@example.com"})
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[-1], ("post", "api/workflow/v1/instances/message",
                         {"messageName": "開始（AI要約）", "modelId": GUID, "version": "1.0.21",
                          "data": {"executor_email": "exec@example.com"}}))

    def test_start_with_empty_executor_email_fires_with_empty_data(self):
        # 空（実行者が解決できなかった場合）は従来どおり data:{} で発火（宛先追加なし＝チーム宛てだけ）。
        result = ra.pl_report_api("start", {"executor_email": ""})
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[-1][2]["data"], {})

    def test_start_drops_malformed_executor_email_but_still_runs(self):
        # 不正アドレスは本人宛て送信だけスキップ（空扱い）＝主機能（レポート生成）は止めない。
        # 不正値は Workflow data へ流さない（AI の Send Email 宛先/本文への混入防止）。制御文字・bidi も弾く。
        for bad in ("not-an-email", "a@b.com, c@d.com", "a@b.com c@d.com", "a@b.com<script>",
                    "no-at-sign.example", "missing-dot@localhost", "a\x00@b.co", "a‮@b.co"):
            with self.subTest(bad=bad):
                self.calls = []
                result = ra.pl_report_api("start", {"executor_email": bad})
                self.assertTrue(result["ok"], bad)
                self.assertEqual(self.calls[-1][2]["data"], {}, bad)  # 不正値は data へ流さない

    def test_start_drops_pattern_valid_but_overlong_executor_email(self):
        # BK-014: 形式は妥当でも MAX_EXECUTOR_EMAIL_LEN 超過は長さ節で drop する（正規表現節とは独立）。
        # 過去のテストは短い形式不正値だけで、長さ節は未到達だった。長さ節を外しても通る回帰を塞ぐ。
        over = "a" * (ra.MAX_EXECUTOR_EMAIL_LEN - 5) + "@b.com"
        self.assertGreater(len(over), ra.MAX_EXECUTOR_EMAIL_LEN)
        self.assertTrue(ra.EMAIL_PATTERN.fullmatch(over))  # 正規表現は通る＝drop 理由は長さのみ
        result = ra.pl_report_api("start", {"executor_email": over})
        self.assertTrue(result["ok"])
        self.assertEqual(self.calls[-1][2]["data"], {})  # 長さ超過は Workflow data へ流さない（Send Email 混入防止）

    def test_start_rejects_executor_email_combined_with_other_keys(self):
        # executor_email 以外のキーは従来どおり拒否（任意キーで別モデルを起動させない）。
        result = ra.pl_report_api("start", {"executor_email": "exec@example.com", "modelId": self.instance})
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")
        self.assertFalse(self.calls)

    def test_existing_running_execution_is_reused_without_a_post(self):
        self.rows = [{"id": self.instance, "modelId": GUID, "status": "IN_PROGRESS", "createdOn": "2026-10-15T00:00:00Z"}]
        result = ra.pl_report_api("start", {})
        self.assertTrue(result["already_running"])
        self.assertEqual(len(self.calls), 1)

    def test_status_prefers_running_over_a_newer_completed_instance(self):
        self.rows = [{"id": self.instance, "modelId": GUID, "status": "IN_PROGRESS", "createdOn": "2026-10-14"},
                     {"id": "other", "modelId": GUID, "status": "COMPLETED", "createdOn": "2026-10-15"}]
        self.assertTrue(ra.pl_report_api("status", {})["running"])

    def test_status_latest_instance_uses_time_not_lexicographic_order(self):
        # BK-012: 精度混在の createdOn を「時刻」として比較する。'…01.500Z'(新) は '…01Z'(旧) より
        # 新しいが、文字列比較だと '.'(0x2E) < 'Z'(0x5A) で順序が逆転し旧を最新と誤選択してしまう。
        self.rows = [
            {"id": "older", "modelId": GUID, "status": "COMPLETED", "createdOn": "2026-10-05T00:00:01Z"},
            {"id": "newer", "modelId": GUID, "status": "COMPLETED", "createdOn": "2026-10-05T00:00:01.500Z"},
        ]
        self.assertEqual(ra.pl_report_api("status", {})["instance_id"], "newer")  # 時刻で新しい方を選ぶ

    def test_empty_history_is_idle_and_status_is_read_only(self):
        self.assertEqual(ra.pl_report_api("status", {})["status"], "IDLE")
        self.assertTrue(all(method == "get" for method, _, _ in self.calls))

    def test_invalid_start_parameters_cannot_select_other_models(self):
        result = ra.pl_report_api("start", {"modelId": self.instance})
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")
        self.assertFalse(self.calls)

    def test_undeployed_placeholder_fails_without_api_calls(self):
        ra.MAIN_WORKFLOW_MODEL_ID = "__MAIN_WORKFLOW_MODEL_ID__"
        self.assertEqual(ra.pl_report_api("start", {})["error"]["code"], "WORKFLOW_NOT_CONFIGURED")
        self.assertFalse(self.calls)

    def test_no_released_version_fails_without_a_post(self):
        self.model = {"versions": [{"version": "1.0.0", "active": False}]}
        self.assertEqual(ra.pl_report_api("start", {})["error"]["code"], "WORKFLOW_NOT_RELEASED")
        self.assertFalse(any(method == "post" for method, _, _ in self.calls))

    def test_ambiguous_start_is_not_retried_or_reported_as_unstarted(self):
        self.start_error = True
        result = ra.pl_report_api("start", {})
        self.assertEqual(result["error"]["code"], "START_UNCONFIRMED")
        self.assertEqual(sum(method == "post" for method, _, _ in self.calls), 1)

    def test_invalid_instance_id_is_rejected_before_network(self):
        self.assertEqual(ra.pl_report_api("status", {"instance_id": "../foreign"})["error"]["code"], "INVALID_INSTANCE_ID")
        self.assertFalse(self.calls)

    def test_other_model_instance_is_rejected(self):
        sys.modules["codeengine"].send_request = lambda *args: {"modelId": self.instance, "status": "COMPLETED"}
        self.assertEqual(ra.pl_report_api("status", {"instance_id": self.instance})["error"]["code"], "INVALID_INSTANCE_ID")

    def test_malformed_status_response_cannot_enable_execution(self):
        self.rows = {"unexpected": []}
        self.assertEqual(ra.pl_report_api("start", {})["error"]["code"], "WORKFLOW_STATUS_ERROR")
        self.assertFalse(any(method == "post" for method, _, _ in self.calls))


class ValidateTest(unittest.TestCase):
    def setUp(self):
        _FakeAppDB().install()

    def test_validate_ok(self):
        out = ra.pl_report_api("validate", {"collection_id": GUID, "doc_key": "JPN001-2025-10-Actual"})
        self.assertTrue(out["ok"])
        self.assertEqual(out["doc_key"], "JPN001-2025-10-Actual")

    def test_validate_bad_guid(self):
        self.assertEqual(ra.pl_report_api("validate", {"collection_id": "nope", "doc_key": "x"})["error"]["code"],
                         "INVALID_COLLECTION_ID")

    def test_validate_missing_doc_key(self):
        self.assertEqual(ra.pl_report_api("validate", {"collection_id": GUID})["error"]["code"], "MISSING_DOC_KEY")

    def test_foreign_collection_never_reaches_appdb(self):
        for operation in ("validate", "save"):
            with self.subTest(operation=operation), patch.object(sys.modules["codeengine"], "send_request") as send:
                result = ra.pl_report_api(operation, {
                    "collection_id": "99999999-2222-4333-8444-555555555555",
                    "doc_key": "other", "document": _full(),
                })
                self.assertEqual(result["error"]["code"], "COLLECTION_NOT_ALLOWED")
                send.assert_not_called()

    def test_unconfigured_collection_fails_before_io(self):
        with patch.object(ra, "REPORT_COLLECTION_ID", "__REPORT_COLLECTION_ID__"), \
             patch.object(sys.modules["codeengine"], "send_request") as send:
            result = ra.pl_report_api("save", {"collection_id": GUID, "document": _full()})
            self.assertEqual(result["error"]["code"], "COLLECTION_NOT_CONFIGURED")
            send.assert_not_called()



class SaveDedupeTest(unittest.TestCase):
    def test_first_save_deletes_nothing(self):
        db = _FakeAppDB().install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="v1")})
        self.assertTrue(out["ok"])
        self.assertEqual(out["deleted_stale"], 0)
        self.assertEqual(len(db.live_keys("K")), 1)

    def test_save_deletes_only_strictly_older_same_key(self):
        # ★中核: 既存の古い同一 key を1件消し、作成した当の文書は残す。
        db = _FakeAppDB(seed=[_seed("old", "K", "2026-10-01T00:00:00+00:00", "old")]).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="new")})
        self.assertTrue(out["ok"])
        self.assertEqual(out["deleted_stale"], 1)
        live = db.live_keys("K")
        self.assertEqual([d["content"]["analysis_html"] for d in live], ["new"])  # 新しい1件だけ
        self.assertIn("old", db.deleted_ids)

    def test_different_key_untouched(self):
        db = _FakeAppDB(seed=[_seed("other", "OTHER", "2026-10-01T00:00:00+00:00")]).install()
        ra.pl_report_api("save", {"collection_id": GUID, "document": _full(key="K")})
        self.assertEqual(len(db.live_keys("OTHER")), 1)
        self.assertEqual(db.deleted_ids, [])

    def test_same_createdOn_not_deleted(self):
        # 安全不変条件: createdOn が厳密に古いものだけ削除。同時刻は保持（並行saveの全滅防止）。
        same = "2026-10-05T00:00:01+00:00"  # FakeAppDB の最初の create と同じ createdOn
        db = _FakeAppDB(seed=[{"id": "tie", "createdOn": same,
                               "content": {"doc_key": "K", "analysis_html": "tie"}}]).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="new")})
        self.assertEqual(out["deleted_stale"], 0)  # 同時刻は消さない
        self.assertEqual(len(db.live_keys("K")), 2)

    def test_newer_existing_not_deleted(self):
        # 既存が新しければ消さない（厳密 older のみ）。将来時刻の既存文書は保持。
        db = _FakeAppDB(seed=[_seed("future", "K", "2099-01-01T00:00:00+00:00", "future")]).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="new")})
        self.assertEqual(out["deleted_stale"], 0)
        self.assertEqual(len(db.live_keys("K")), 2)

    def test_save_under_read_after_write_lag_keeps_all_and_flags_pending(self):
        # BK-007: 直後照会に新版がまだ現れないラグ下では、作成文書も旧版も消さない
        # （observed=created フォールバック→POST 応答に createdOn 無し→created_time=None→
        # stale 判定が成立しない）。consistency_pending=True を表面化し、旧版の掃除は後続 save に委ねる。
        older = [_seed("old1", "K", "2026-10-01T00:00:00+00:00", "a"),
                 _seed("old2", "K", "2026-10-02T00:00:00+00:00", "b")]
        db = _FakeAppDB(seed=older, hide_created=True).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="new")})
        self.assertTrue(out["ok"])
        self.assertTrue(out["consistency_pending"])   # observed_now=False を表面化
        self.assertEqual(out["deleted_stale"], 0)      # ラグ中は何も消さない（旧版も作成文書も）
        self.assertEqual(db.deleted_ids, [])           # 作成した当の文書は絶対に消さない（不変条件①）
        self.assertEqual(len(db.live_keys("K")), 3)    # old1・old2・新規（隠れているが格納済み）

    def test_save_prunes_older_same_key_across_query_pages(self):
        # BK-016: 同一 key の旧版が1ページ（1000件）を超えても、_save は offset を進めて全ページを
        # 掃引し、厳密に古い全件を削除して作成文書だけ残す（fake も limit/offset を honor する）。
        older = [_seed(f"old{i}", "K", "2026-10-01T00:00:00+00:00", "x") for i in range(1100)]
        db = _FakeAppDB(seed=older).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="new")})
        self.assertTrue(out["ok"])
        self.assertEqual(out["deleted_stale"], 1100)   # 1000+100 を2ページ掃引で全件刈る
        self.assertFalse(out["consistency_pending"])   # 作成文書は照会に現れる
        live = db.live_keys("K")
        self.assertEqual([d["content"]["analysis_html"] for d in live], ["new"])  # 作成文書だけ残る


class SafetyGateTest(unittest.TestCase):
    """★ Finding 1: 不完全ドキュメントの保存は既存の正レポートを巻き添え削除しない。"""

    def test_incomplete_document_rejected(self):
        _FakeAppDB().install()
        for bad in ({"doc_key": "K"},  # 本体なし（旧挙動では空スタブ保存されていた）
                    _full(html=""),      # analysis_html 空
                    {"doc_key": "K", "store_id": "JPN001", "analysis_html": "x"},  # location_name 欠落
                    {"doc_key": "K", "location_name": "銀座店", "analysis_html": "x"}):  # store_id 欠落
            out = ra.pl_report_api("save", {"collection_id": GUID, "document": bad})
            self.assertFalse(out["ok"], bad)
            self.assertEqual(out["error"]["code"], "MISSING_FIELDS", bad)

    def test_incomplete_save_does_not_delete_existing_good_report(self):
        # 既存の良いレポートがある状態で不完全保存を試みても、既存は消えない（破壊的削除が走らない）。
        db = _FakeAppDB(seed=[_seed("good", "K", "2026-10-01T00:00:00+00:00", "GOOD REPORT")]).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": {"doc_key": "K"}})
        self.assertFalse(out["ok"])
        self.assertEqual(db.deleted_ids, [])  # 何も削除していない
        live = db.live_keys("K")
        self.assertEqual([d["content"]["analysis_html"] for d in live], ["GOOD REPORT"])  # 既存の正レポート健在


class DocumentShapeTest(unittest.TestCase):
    def setUp(self):
        self.db = _FakeAppDB().install()

    def test_string_json_document(self):
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": json.dumps(_full(html="s"))})
        self.assertTrue(out["ok"])

    def test_nested_document_wrapper(self):
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": {"document": _full(html="n")}})
        self.assertTrue(out["ok"])

    def test_content_wrapper_unwrapped_and_stored_flat(self):
        ra.pl_report_api("save", {"collection_id": GUID, "document": {"content": _full(html="c")}})
        stored = self.db.live_keys("K")[0]["content"]
        self.assertIn("doc_key", stored)  # content ラッパは剥がしてフラット保存（二重 content を防ぐ）
        self.assertEqual(stored["analysis_html"], "c")

    def test_flat_request_without_document_key(self):
        out = ra.pl_report_api("save", dict({"collection_id": GUID}, **_full(html="flat")))
        self.assertTrue(out["ok"])

    def test_report_type_not_leaked_via_flat_fallback(self):
        # Finding 4: 平坦フォールバックでも routing/PII キー(report_type/operation/collection_id/executor_email)は
        # 文書へ混ぜない（executor_email は実行時 PII。AppDB の共有レポートへ永続化させない）。
        ra.pl_report_api("save", dict({"collection_id": GUID, "report_type": "store", "operation": "save",
                                       "executor_email": "exec@example.com"}, **_full(html="x")))
        stored = self.db.live_keys("K")[0]["content"]
        for leaked in ("report_type", "operation", "collection_id", "executor_email"):
            self.assertNotIn(leaked, stored)

    def test_routing_and_pii_keys_dropped_from_nested_document(self):
        # BK-011: 入れ子 document パスでも flat パスと同じく routing/PII キーを落とす（defense-in-depth）。
        # 従来は flat 分岐だけ strip し、dict を直接渡す通常経路は未保護だった。
        doc = dict(_full(html="p"), executor_email="exec@example.com", report_type="store",
                   operation="save", collection_id=GUID)
        ra.pl_report_api("save", {"collection_id": GUID, "document": doc})
        stored = self.db.live_keys("K")[0]["content"]
        for leaked in ("report_type", "operation", "collection_id", "executor_email"):
            self.assertNotIn(leaked, stored)
        self.assertEqual(stored["analysis_html"], "p")   # 正当なフィールドは残る
        self.assertEqual(stored["store_id"], "JPN001")   # store_id 等の本文は維持

    def test_generated_at_autofilled_when_empty(self):
        ra.pl_report_api("save", {"collection_id": GUID, "document": _full()})
        self.assertTrue(self.db.live_keys("K")[0]["content"]["generated_at"])  # 欠落時は自動補完

    def test_generated_at_invalid_replaced(self):
        # Finding 5: 非空だが ISO 不正な generated_at は現在時刻へ置換（降順ソートを壊さない）。
        ra.pl_report_api("save", {"collection_id": GUID, "document": _full(generated_at="yesterday")})
        gen = self.db.live_keys("K")[0]["content"]["generated_at"]
        self.assertNotEqual(gen, "yesterday")
        # 置換後は ISO としてパースできる
        from datetime import datetime
        datetime.fromisoformat(gen.replace("Z", "+00:00"))


class ErrorAndDispatchTest(unittest.TestCase):
    def test_save_missing_doc_key(self):
        _FakeAppDB().install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": {"analysis_html": "x"}})
        self.assertFalse(out["ok"])
        self.assertEqual(out["error"]["code"], "MISSING_DOC_KEY")

    def test_save_bad_guid(self):
        _FakeAppDB().install()
        self.assertEqual(ra.pl_report_api("save", {"collection_id": "nope", "document": _full()})["error"]["code"],
                         "INVALID_COLLECTION_ID")

    def test_document_too_large(self):
        _FakeAppDB().install()
        big = _full(html="a" * (ra.MAX_DOCUMENT_BYTES + 10))
        self.assertEqual(ra.pl_report_api("save", {"collection_id": GUID, "document": big})["error"]["code"],
                         "DOCUMENT_TOO_LARGE")

    def test_create_no_id_is_not_saved(self):
        _FakeAppDB(create_fail=True).install()
        self.assertEqual(ra.pl_report_api("save", {"collection_id": GUID, "document": _full()})["error"]["code"],
                         "REQUEST_NOT_SAVED")

    def test_cleanup_failure_still_ok(self):
        # 作成は成功・掃除(delete)が失敗 → ok:True cleanup_incomplete（重複蓄積を避ける）。
        db = _FakeAppDB(seed=[_seed("old", "K", "2026-10-01T00:00:00+00:00")], delete_fail=True).install()
        out = ra.pl_report_api("save", {"collection_id": GUID, "document": _full(html="new")})
        self.assertTrue(out["ok"])
        self.assertTrue(out.get("cleanup_incomplete"))

    def test_operation_inference_save(self):
        _FakeAppDB().install()
        out = ra.pl_report_api(request=dict({"collection_id": GUID}, **_full(html="d")))
        self.assertTrue(out["ok"])  # operation 空 + 本体フィールドあり → save 推定

    def test_operation_inference_identifier_only_is_validate(self):
        # ★ Finding 2: {collection_id, doc_key} のみ（operation 空）は validate（破壊的 save に倒さない）。
        db = _FakeAppDB(seed=[_seed("good", "K", "2026-10-01T00:00:00+00:00", "GOOD")]).install()
        out = ra.pl_report_api("", {"collection_id": GUID, "doc_key": "K"})
        self.assertTrue(out["ok"])
        self.assertEqual(out.get("doc_key"), "K")  # validate の戻り
        self.assertEqual(db.deleted_ids, [])  # 何も作らない・消さない
        self.assertEqual(len(db.live_keys("K")), 1)

    def test_bad_operation(self):
        _FakeAppDB().install()
        self.assertEqual(ra.pl_report_api("generate", {"collection_id": GUID})["error"]["code"], "INVALID_OPERATION")

    def test_request_as_string_json(self):
        _FakeAppDB().install()
        out = ra.pl_report_api("save", json.dumps({"collection_id": GUID, "document": _full()}))
        self.assertTrue(out["ok"])

    def test_request_bad_json_string(self):
        _FakeAppDB().install()
        self.assertEqual(ra.pl_report_api("save", "{not json")["error"]["code"], "INVALID_REQUEST")


if __name__ == "__main__":
    unittest.main(verbosity=2)
