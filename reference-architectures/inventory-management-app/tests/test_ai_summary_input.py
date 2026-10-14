import importlib.util
import pathlib
import unittest
from datetime import datetime, timezone

try:
    import pandas as pd
except ImportError:
    pd = None


MODULE = None
if pd is not None:
    MODULE_PATH = pathlib.Path(__file__).parents[1] / "dataflow" / "ai_summary_input.py"
    SPEC = importlib.util.spec_from_file_location("ai_summary_input_under_test", MODULE_PATH)
    MODULE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MODULE)


NOW = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)


@unittest.skipIf(pd is None, "pandas is provided by the Domo Python tile runtime")
class AiNoteInputTest(unittest.TestCase):
    def _records(self):
        # 読み込みタイルの出力（AppDB全レコード）を最小構成で再現する。
        # BALANCE 以外（ITEM/TRANSACTION 等）は AI ノートの対象外であることを確かめるため混ぜる。
        return pd.DataFrame([
            {"record_type": "ITEM", "item_code": "ITEM-001", "item_name": "安全手袋"},
            {"record_type": "TRANSACTION", "item_code": "ITEM-001", "quantity": 12},
            {"record_type": "BALANCE", "balance_key": "LOC-01|ITEM-001", "item_code": "ITEM-001", "item_name": "安全手袋",
             "location_code": "LOC-01", "location_name": "中央倉庫", "quantity": 7, "minimum_quantity": 20,
             "shortage_quantity": 13, "is_shortage": True, "last_transaction_at": "2026-08-08T09:00:00Z"},
            {"record_type": "BALANCE", "balance_key": "LOC-02|ITEM-003", "item_code": "ITEM-003", "item_name": "六角ボルト M8",
             "location_code": "LOC-02", "location_name": "組立エリア", "quantity": 145, "minimum_quantity": 50,
             "shortage_quantity": 0, "is_shortage": False, "last_transaction_at": "2026-06-20T09:00:00Z"},
            {"record_type": "BALANCE", "balance_key": "LOC-03|ITEM-009", "item_code": "ITEM-009", "item_name": "軍手",
             "location_code": "LOC-03", "location_name": "保守部品庫", "quantity": 30, "minimum_quantity": 0,
             "shortage_quantity": 0, "is_shortage": False, "last_transaction_at": "2026-08-01T09:00:00Z"},
        ])

    def test_emits_one_ai_note_row_per_balance_with_expected_columns(self):
        result = MODULE.build_ai_input(self._records(), now=NOW)
        self.assertEqual(list(result.columns), MODULE.OUTPUT_COLUMNS)
        # BALANCE は3件なので AI ノートもちょうど3件。ITEM/TRANSACTION は除外される。
        self.assertEqual(len(result), 3)
        self.assertTrue((result["record_type"] == "AI_NOTE").all())
        # ai_summary はこのタイルでは持たない（後段の TextGeneration が新規に作る列）。
        self.assertNotIn("ai_summary", result.columns)

    def test_identity_columns_are_carried_from_balance(self):
        result = MODULE.build_ai_input(self._records(), now=NOW)
        first = result[result["balance_key"] == "LOC-01|ITEM-001"].iloc[0]
        # 品目カードへノートを突き合わせられるよう、識別列が残高から引き継がれること。
        self.assertEqual(first["item_code"], "ITEM-001")
        self.assertEqual(first["item_name"], "安全手袋")
        self.assertEqual(first["location_name"], "中央倉庫")

    def test_shortage_item_digest_states_shortage_and_numbers(self):
        result = MODULE.build_ai_input(self._records(), now=NOW)
        text = result[result["balance_key"] == "LOC-01|ITEM-001"].iloc[0]["ai_input_text"]
        self.assertIn("安全手袋", text)
        self.assertIn("中央倉庫", text)
        self.assertIn("現在庫: 7", text)
        self.assertIn("基準在庫: 20", text)
        self.assertIn("在庫不足（不足 13）", text)
        self.assertIn("最終入出庫からの経過: 1日", text)

    def test_healthy_item_digest_states_appropriate(self):
        result = MODULE.build_ai_input(self._records(), now=NOW)
        text = result[result["balance_key"] == "LOC-02|ITEM-003"].iloc[0]["ai_input_text"]
        self.assertIn("状態: 適正", text)
        self.assertNotIn("在庫不足", text)

    def test_item_without_rule_states_baseline_unset(self):
        result = MODULE.build_ai_input(self._records(), now=NOW)
        text = result[result["balance_key"] == "LOC-03|ITEM-009"].iloc[0]["ai_input_text"]
        self.assertIn("状態: 基準未設定", text)
        # 基準未設定の品目には基準在庫行を出さない。
        self.assertNotIn("基準在庫:", text)

    def test_balance_without_last_transaction_omits_age_line(self):
        # なぜこのテストか: 共通フィクスチャ _records() は全 BALANCE に last_transaction_at を
        # 与えるため、「最終入出庫日が無い」経路（新規ロケーションや初期在庫で取引履歴ゼロ）を
        # 一度も通らない。_age_days は日付欠落時 None を返し、_digest はそのとき「経過」行を
        # 出さない契約（source L84-85 / L111-113）。取引履歴の無い品目カードに 0日 や不正な
        # 経過表示が漏れない現挙動を固定する。
        records = pd.DataFrame([
            {"record_type": "BALANCE", "balance_key": "LOC-04|ITEM-010", "item_code": "ITEM-010",
             "item_name": "予備部品", "location_code": "LOC-04", "location_name": "予備庫",
             "quantity": 5, "minimum_quantity": 0, "shortage_quantity": 0, "is_shortage": False},
        ])
        result = MODULE.build_ai_input(records, now=NOW)
        self.assertEqual(len(result), 1)
        text = result.iloc[0]["ai_input_text"]
        # 最終入出庫日が無いので「経過」行は出さない（0日と誤表示しない）。
        self.assertNotIn("経過", text)
        # 日付が無ければ _age_days は None（＝不明）を返す。
        self.assertIsNone(MODULE._age_days(None, NOW))

    def test_numeric_columns_are_float_typed(self):
        result = MODULE.build_ai_input(self._records(), now=NOW)
        # DOUBLE 宣言の列は float でなければ Magic ETL が型不一致で失敗する（DP-UNSUTYCO）。
        for column in MODULE.NUMERIC_COLUMNS:
            self.assertEqual(str(result[column].dtype), "float64")

    def test_empty_records_return_zero_rows_with_contract_columns(self):
        result = MODULE.build_ai_input(None, now=NOW)
        self.assertEqual(list(result.columns), MODULE.OUTPUT_COLUMNS)
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
