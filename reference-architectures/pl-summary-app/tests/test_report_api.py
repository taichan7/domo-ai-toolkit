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

sys.modules.setdefault("codeengine", types.ModuleType("codeengine"))

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "..", "code-engine", "report_api.py")
_spec = importlib.util.spec_from_file_location("report_api", os.path.abspath(_MODULE_PATH))
ra = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = ra  # importlib 読込の定石
_spec.loader.exec_module(ra)

GUID = "ca132957-d14d-4fa0-9c69-3e6721d27141"


class _FakeAppDB:
    """codeengine.send_request のインメモリ代役（AppDB シミュレータ）。

    POST create は id と createdOn を採番して格納（createdOn は seq 昇順＝後に作るほど新しい）。
    POST query は content.doc_key 一致を返す。DELETE bulk は id を除去する。
    seed で既存文書（任意の createdOn）を事前投入でき、create_fail / delete_fail で失敗を注入する。
    """

    def __init__(self, seed=None, create_fail=False, delete_fail=False):
        self.docs = {}
        self.seq = 0
        self.create_fail = create_fail
        self.delete_fail = delete_fail
        self.deleted_ids = []
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
            return {"id": doc["id"]}
        if m == "post" and "/documents/query" in base:
            key = body["content.doc_key"]["$eq"]
            return [d for d in self.docs.values() if (d.get("content") or {}).get("doc_key") == key]
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
        # Finding 4: 平坦フォールバックでも routing キー(report_type/operation)は文書へ混ぜない。
        ra.pl_report_api("save", dict({"collection_id": GUID, "report_type": "store", "operation": "save"},
                                      **_full(html="x")))
        stored = self.db.live_keys("K")[0]["content"]
        self.assertNotIn("report_type", stored)
        self.assertNotIn("operation", stored)
        self.assertNotIn("collection_id", stored)

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
