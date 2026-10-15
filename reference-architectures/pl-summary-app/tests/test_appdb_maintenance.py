#!/usr/bin/env python3
"""appdb_maintenance.py（AppDB 重複除去 CE）の特性化テスト。

実行: python3 pl-summary-app/tests/test_appdb_maintenance.py

なぜこのテストか:
    このモジュールは Domo Workflows Code Engine 上で稼働する「デプロイ済み」ロジックで、
    唯一の公開関数 dedupe_appdb_documents は AppDB ドキュメントを **物理削除** する破壊的操作。
    取得（ページング）・doc_key グループ化・generated_at 最新1件保持・bulk 分割削除を1関数に
    インライン展開しているため、将来この関数を安全にリファクタリング（またはCE再デプロイ）する
    前提として、現在の分岐挙動——特に「削除しすぎない」安全不変条件——をゴールデン値で厳密に固定する。
    ここではソースは一切変更しない（＝デプロイ済みCEバンドルに触れない・回帰ゼロ）。

    ゴールデンは実際に関数を実行して観測した値をそのまま採用している（＝「あるべき」でなく
    「現にどうなっているか」を固定する特性化テスト）。

読み込みの都合:
    先頭の `import codeengine`（Domo実行環境の標準ライブラリ・ローカルには無い）を通すため、
    exec_module の前に空スタブを sys.modules に登録する。この関数は codeengine.send_request で
    ネットワーク I/O を行うので、各テストで send_request をインメモリ代役に差し替える
    （＝テスト時は実ネットワーク非発生・GET はページを順に返し・DELETE は URL を記録するだけ）。
"""
import importlib.util
import os
import sys
import types
import unittest

# codeengine は Domo Workflows 実行環境にのみ存在する。send_request はテストごとに差し替える。
sys.modules.setdefault("codeengine", types.ModuleType("codeengine"))

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "..", "code-engine", "appdb_maintenance.py")
_spec = importlib.util.spec_from_file_location("appdb_maintenance", os.path.abspath(_MODULE_PATH))
apm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = apm  # importlib 読込の定石（将来 __future__/dataclass 追加でも安全）
_spec.loader.exec_module(apm)

# 出荷時の定数を「テストが _PAGE_SIZE/_DELETE_CHUNK を書き換える前」に捕まえておく
# （挙動テストは縮小定数で回すが、出荷値そのものも別テストで固定するため）。
_PRISTINE_CONSTS = (apm._PAGE_SIZE, apm._DELETE_CHUNK)

# GUID_REGEX を満たす v4 UUID（3ブロック目先頭=4, 4ブロック目先頭=8|9|a|b）。
GUID = "12345678-1234-4234-8234-123456789abc"
_GET_URL = "api/datastores/v1/collections/%s/documents?limit=%d&offset=%d"
_DEL_URL = "api/datastores/v2/collections/%s/documents/bulk?ids=%s"


class _FakeCE:
    """codeengine.send_request のインメモリ代役。

    GET は与えたページ列を順に返し（ページング終端＝短いページで break を再現）、
    DELETE は URL を試行時点で記録する（失敗分も記録＝「試みたが deleted に数えない」を可視化）。
    """

    def __init__(self, pages, delete_fail_on=()):
        self._pages = pages
        self._get_idx = 0
        self._del_idx = 0
        self._fail = set(delete_fail_on)
        self.get_urls = []
        self.delete_urls = []

    def send_request(self, method, url, body=None):
        m = method.lower()
        if m == "get":
            self.get_urls.append(url)
            page = self._pages[self._get_idx] if self._get_idx < len(self._pages) else []
            self._get_idx += 1
            return page
        if m == "delete":
            idx = self._del_idx
            self._del_idx += 1
            self.delete_urls.append(url)  # 記録は raise の前＝失敗チャンクの URL も残る
            if idx in self._fail:
                raise RuntimeError("boom")
            return {"ok": True}
        return None


def _doc(doc_id, key=None, gen=None, with_content=True):
    """テスト用ドキュメント envelope を最小構成で作る。"""
    content = {}
    if key is not None:
        content["doc_key"] = key
    if gen is not None:
        content["generated_at"] = gen
    d = {"id": doc_id}
    if with_content:
        d["content"] = content
    return d


class DedupeAppdbDocumentsTest(unittest.TestCase):
    """破壊的 dedup の分岐と「削除しすぎない」安全不変条件を固定する。"""

    def setUp(self):
        # 各テストは既定（縮小前）の定数から開始する。個別テストで必要なら上書きする。
        apm._PAGE_SIZE, apm._DELETE_CHUNK = _PRISTINE_CONSTS

    def _install(self, pages, delete_fail_on=(), page_size=None, delete_chunk=None):
        if page_size is not None:
            apm._PAGE_SIZE = page_size
        if delete_chunk is not None:
            apm._DELETE_CHUNK = delete_chunk
        fake = _FakeCE(pages, delete_fail_on)
        # Bind the fake to the imported module, not a process-global runtime
        # object another app's test collection may have replaced.
        apm.codeengine = types.SimpleNamespace(send_request=fake.send_request)
        return fake

    def test_pristine_constants(self):
        # 出荷時のページサイズ／削除チャンクを固定（変更はレビュー対象＝ここで検知）。
        self.assertEqual(_PRISTINE_CONSTS, (5000, 100))

    def test_invalid_collection_id_raises_before_any_request(self):
        # 検証は取得より前。空・非GUID・バージョン桁違い(3ブロック目先頭が4でない)は ValueError。
        fake = self._install([[]])
        for bad in ["", "not-a-guid", "12345678-1234-1234-8234-123456789abc"]:
            with self.assertRaises(ValueError):
                apm.dedupe_appdb_documents(bad)
        # 早期 raise なので send_request は一度も呼ばれない。
        self.assertEqual(fake.get_urls, [])
        self.assertEqual(fake.delete_urls, [])

    def test_no_duplicates_deletes_nothing(self):
        # doc_key が全て別 → どのグループも1件 → 削除ゼロ（remaining=total）。
        fake = self._install([[_doc("a", "k1", "2025-01-01"), _doc("b", "k2", "2025-01-02")]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["total_before"], 2)
        self.assertEqual(out["unique_keys"], 2)
        self.assertEqual(out["delete_candidates"], 0)
        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["remaining"], 2)
        self.assertTrue(out["success"])
        self.assertEqual(fake.delete_urls, [])

    def test_keeps_latest_generated_at_and_deletes_rest(self):
        # ★中核: 同一 doc_key は generated_at 最新1件を残し、古い方だけ削除する。
        # old=1月, new=3月, mid=2月 → 残すのは new、削除は降順で [mid, old]。
        fake = self._install([[
            _doc("old", "k1", "2025-01-01"),
            _doc("new", "k1", "2025-03-01"),
            _doc("mid", "k1", "2025-02-01"),
        ]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["unique_keys"], 1)
        self.assertEqual(out["delete_candidates"], 2)
        self.assertEqual(out["deleted"], 2)
        self.assertEqual(out["remaining"], 1)
        # 削除対象は new を除いた [mid, old]（＝最新は必ず生き残る）。
        self.assertEqual(fake.delete_urls, [_DEL_URL % (GUID, "mid,old")])

    def test_no_doc_key_docs_are_isolated_never_deleted(self):
        # doc_key を持たない不正データは __nokey__{id} で単独グループ化＝互いに重複扱いしない。
        fake = self._install([[_doc("a", None, None), _doc("b", None, None)]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["unique_keys"], 2)
        self.assertEqual(out["delete_candidates"], 0)
        self.assertEqual(out["remaining"], 2)
        self.assertEqual(fake.delete_urls, [])

    def test_stale_without_id_is_not_deleted(self):
        # 安全不変条件: 古い側でも id が無ければ削除候補に入れない（`if doc_id:` ガード）。
        # 同一 key で keep(2月, id有) と stale(1月, id=None) → 候補0（削除できないものは触らない）。
        fake = self._install([[
            _doc("keep", "k1", "2025-02-01"),
            {"id": None, "content": {"doc_key": "k1", "generated_at": "2025-01-01"}},
        ]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["unique_keys"], 1)
        self.assertEqual(out["delete_candidates"], 0)
        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["remaining"], 2)
        self.assertEqual(fake.delete_urls, [])

    def test_content_missing_treated_as_no_key(self):
        # content キーごと無いドキュメントも __nokey__{id} 扱い＝別々グループ・削除なし。
        fake = self._install([[{"id": "x"}, {"id": "y"}]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["unique_keys"], 2)
        self.assertEqual(out["delete_candidates"], 0)
        self.assertEqual(out["remaining"], 2)

    def test_chunking_splits_deletes_by_chunk_size(self):
        # 削除は _DELETE_CHUNK 件ずつ分割。6件同一keyでchunk=2→残1・候補5→[d4,d3][d2,d1][d0]。
        fake = self._install(
            [[_doc(f"d{i}", "k1", f"2025-01-{i + 1:02d}") for i in range(6)]],
            delete_chunk=2,
        )
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["delete_candidates"], 5)
        self.assertEqual(out["deleted"], 5)
        self.assertEqual(out["remaining"], 1)
        self.assertEqual(
            fake.delete_urls,
            [
                _DEL_URL % (GUID, "d4,d3"),
                _DEL_URL % (GUID, "d2,d1"),
                _DEL_URL % (GUID, "d0"),
            ],
        )

    def test_chunk_failure_continues_and_preserves_latest(self):
        # ★安全不変条件: 途中チャンクが失敗しても継続。最新1件は削除候補に入らないので常に残る。
        # 2番目のチャンク(d2,d1)が raise → 3チャンク全て試行するが deleted は成功分のみ=3。
        fake = self._install(
            [[_doc(f"d{i}", "k1", f"2025-01-{i + 1:02d}") for i in range(6)]],
            delete_fail_on={1},
            delete_chunk=2,
        )
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["delete_candidates"], 5)
        self.assertEqual(out["deleted"], 3)  # 失敗チャンク(2件)は数えない
        self.assertEqual(out["remaining"], 3)
        self.assertTrue(out["success"])  # 部分失敗でも success=True（最新は保持済み）
        # 失敗チャンクも「試行」はする（URL は3本記録される）。
        self.assertEqual(
            fake.delete_urls,
            [
                _DEL_URL % (GUID, "d4,d3"),
                _DEL_URL % (GUID, "d2,d1"),
                _DEL_URL % (GUID, "d0"),
            ],
        )

    def test_paging_terminates_and_dedupes_across_pages(self):
        # ページング: page_size=2 で (2,2,1) の3ページ → 短いページ(1<2)で break。
        # ページを跨いで同一 key を集約し、最新 p3a を残し 4件削除（chunk=100 なので1本）。
        fake = self._install(
            [
                [_doc("p1a", "k1", "2025-01-01"), _doc("p1b", "k1", "2025-01-02")],
                [_doc("p2a", "k1", "2025-01-03"), _doc("p2b", "k1", "2025-01-04")],
                [_doc("p3a", "k1", "2025-01-05")],
            ],
            page_size=2,
        )
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["total_before"], 5)
        self.assertEqual(out["delete_candidates"], 4)
        self.assertEqual(out["deleted"], 4)
        self.assertEqual(out["remaining"], 1)
        # GET は3ページ分だけ（4回目は呼ばない＝3ページ目が短いので break）。
        self.assertEqual(
            fake.get_urls,
            [
                _GET_URL % (GUID, 2, 0),
                _GET_URL % (GUID, 2, 2),
                _GET_URL % (GUID, 2, 4),
            ],
        )
        self.assertEqual(fake.delete_urls, [_DEL_URL % (GUID, "p2b,p2a,p1b,p1a")])

    def test_empty_collection(self):
        # 空コレクションは全カウント0・削除なし・GET は1回で終端。
        fake = self._install([[]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["total_before"], 0)
        self.assertEqual(out["unique_keys"], 0)
        self.assertEqual(out["delete_candidates"], 0)
        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["remaining"], 0)
        self.assertEqual(fake.get_urls, [_GET_URL % (GUID, 5000, 0)])
        self.assertEqual(fake.delete_urls, [])

    def test_tie_generated_at_keeps_first_seen(self):
        # generated_at が同値の場合は安定ソートで先着を残す（first を保持し second を削除）。
        fake = self._install([[
            _doc("first", "k1", "2025-01-01"),
            _doc("second", "k1", "2025-01-01"),
        ]])
        out = apm.dedupe_appdb_documents(GUID)
        self.assertEqual(out["delete_candidates"], 1)
        self.assertEqual(out["deleted"], 1)
        self.assertEqual(out["remaining"], 1)
        self.assertEqual(fake.delete_urls, [_DEL_URL % (GUID, "second")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
