import importlib.util
import pathlib
import re
import unittest
from datetime import datetime, timedelta, timezone

try:
    import pandas as pd
except ImportError:
    pd = None


TRANSFORM = None
if pd is not None:
    MODULE_PATH = pathlib.Path(__file__).parents[1] / "dataflow" / "dashboard_transform.py"
    SPEC = importlib.util.spec_from_file_location("dashboard_transform_under_test", MODULE_PATH)
    TRANSFORM = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(TRANSFORM)


@unittest.skipIf(pd is None, "pandas is provided by the Domo Python tile runtime")
class DashboardTransformTest(unittest.TestCase):
    def test_builds_kpi_shortage_dormant_and_trend_rows(self):
        records = pd.DataFrame([
            {"record_type": "BALANCE", "balance_key": "LOC-01|ITEM-001", "item_code": "ITEM-001", "item_name": "安全手袋", "location_code": "LOC-01", "location_name": "中央倉庫", "quantity": 7, "minimum_quantity": 10, "shortage_quantity": 3, "is_shortage": True, "last_transaction_at": "2026-08-07T01:00:00Z"},
            {"record_type": "BALANCE", "balance_key": "LOC-02|ITEM-002", "item_code": "ITEM-002", "item_name": "保護メガネ", "location_code": "LOC-02", "location_name": "組立エリア", "quantity": 20, "minimum_quantity": 5, "shortage_quantity": 0, "is_shortage": False, "last_transaction_at": "2026-06-01T01:00:00Z"},
            {"record_type": "TRANSACTION", "transaction_type": "IN", "quantity": 10, "occurred_at": "2026-08-07T01:00:00Z"},
            {"record_type": "TRANSACTION", "transaction_type": "OUT", "quantity": 3, "occurred_at": "2026-08-07T02:00:00Z"},
        ])
        result = TRANSFORM.build_dashboard(records, now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc))
        self.assertEqual(set(result[result.record_type == "KPI"].metric_key), {"TOTAL_QUANTITY", "ITEM_COUNT", "SHORTAGE_COUNT", "TODAY_IN_COUNT", "TODAY_OUT_COUNT"})
        # KPI は種別が揃うだけでなく値も正しいこと。総在庫=7+20、品目数=2、不足=1件、
        # 本日の入出庫は「件数」(数量合算ではない)で IN/OUT 各1件。
        kpi = result[result.record_type == "KPI"].set_index("metric_key").metric_value
        self.assertEqual(kpi["TOTAL_QUANTITY"], 27.0)
        self.assertEqual(kpi["ITEM_COUNT"], 2)
        self.assertEqual(kpi["SHORTAGE_COUNT"], 1)
        self.assertEqual(kpi["TODAY_IN_COUNT"], 1)
        self.assertEqual(kpi["TODAY_OUT_COUNT"], 1)
        self.assertEqual(len(result[result.record_type == "ITEM_STOCK"]), 2)
        self.assertEqual(len(result[result.record_type == "SHORTAGE"]), 1)
        self.assertEqual(len(result[result.record_type == "DORMANT"]), 1)
        today = result[(result.record_type == "TREND") & (result.date_key == "2026-08-07")].iloc[0]
        self.assertEqual(today.inbound_quantity, 10)
        self.assertEqual(today.outbound_quantity, 3)

    def test_item_and_location_rows_aggregate_quantity_and_sort_descending(self):
        # 品目別・棚別は残高数量を名称で合算し、多い順(降順)に並べる。ダッシュボードの
        # 棒グラフが「在庫の多い順」で読めるよう、集計側で並びまで確定させる契約。
        records = pd.DataFrame([
            {"record_type": "BALANCE", "balance_key": "LOC-01|ITEM-001", "item_code": "ITEM-001", "item_name": "安全手袋", "location_code": "LOC-01", "location_name": "中央倉庫", "quantity": 4, "minimum_quantity": 10, "shortage_quantity": 6, "is_shortage": True, "last_transaction_at": "2026-08-07T01:00:00Z"},
            {"record_type": "BALANCE", "balance_key": "LOC-02|ITEM-001", "item_code": "ITEM-001", "item_name": "安全手袋", "location_code": "LOC-02", "location_name": "組立エリア", "quantity": 3, "minimum_quantity": 0, "shortage_quantity": 0, "is_shortage": False, "last_transaction_at": "2026-08-07T01:00:00Z"},
            {"record_type": "BALANCE", "balance_key": "LOC-02|ITEM-002", "item_code": "ITEM-002", "item_name": "保護メガネ", "location_code": "LOC-02", "location_name": "組立エリア", "quantity": 20, "minimum_quantity": 5, "shortage_quantity": 0, "is_shortage": False, "last_transaction_at": "2026-08-07T01:00:00Z"},
        ])
        result = TRANSFORM.build_dashboard(records, now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc))
        # 棚別: 組立エリア=3+20=23、中央倉庫=4 → 降順で組立エリアが先頭。
        locations = result[result.record_type == "LOCATION"]
        self.assertEqual(list(locations.label), ["組立エリア", "中央倉庫"])
        self.assertEqual(list(locations.metric_value), [23.0, 4.0])
        # 品目別: 安全手袋=4+3=7、保護メガネ=20 → 降順で保護メガネが先頭。
        items = result[result.record_type == "ITEM_STOCK"]
        self.assertEqual(list(items.label), ["保護メガネ", "安全手袋"])
        self.assertEqual(list(items.metric_value), [20.0, 7.0])


    def test_item_and_location_rows_carry_codes_and_names_for_search(self):
        # ITEM_STOCK / LOCATION は表示ラベル(名称)で集約するが、コードでも検索できるよう
        # コード・名称を併せて載せる。同一ラベルへ複数コードが集約された場合は重複なく併記する。
        # (在庫のある品目をコードで検索してもヒットしなかった不具合の回帰ガード。表示は label のみ。)
        records = pd.DataFrame([
            {"record_type": "BALANCE", "balance_key": "LOC-02|ITEM-11", "item_code": "ITEM-11", "item_name": "オリーブオイル", "location_code": "LOC-02", "location_name": "組立エリア", "quantity": 5, "is_shortage": False},
        ])
        result = TRANSFORM.build_dashboard(records, now=datetime(2026, 8, 11, tzinfo=timezone.utc))
        item = result[result.record_type == "ITEM_STOCK"].iloc[0]
        self.assertEqual(item.label, "オリーブオイル")
        self.assertEqual(item.item_code, "ITEM-11")
        self.assertEqual(item.item_name, "オリーブオイル")
        location = result[result.record_type == "LOCATION"].iloc[0]
        self.assertEqual(location.label, "組立エリア")
        self.assertEqual(location.location_code, "LOC-02")
        self.assertEqual(location.location_name, "組立エリア")


    def test_empty_inputs_still_return_dashboard_contract(self):
        result = TRANSFORM.build_dashboard(None, now=datetime(2026, 8, 7, tzinfo=timezone.utc))
        self.assertEqual(list(result.columns), TRANSFORM.OUTPUT_COLUMNS)
        self.assertEqual(len(result[result.record_type == "KPI"]), 5)
        self.assertEqual(len(result[result.record_type == "TREND"]), 7)

    def test_unknown_type_is_excluded_from_inbound_outbound_trend(self):
        # 7日トレンドは入庫(IN)・出庫(OUT)の「流量」だけを積む。想定外の種別が混ざっても
        # 入庫・出庫のどちらにも数えない（データ不整合で数字が歪まないことの退行ガード）。
        records = pd.DataFrame([
            {"record_type": "TRANSACTION", "transaction_type": "IN", "quantity": 10, "occurred_at": "2026-08-07T01:00:00Z"},
            {"record_type": "TRANSACTION", "transaction_type": "OUT", "quantity": 3, "occurred_at": "2026-08-07T02:00:00Z"},
            {"record_type": "TRANSACTION", "transaction_type": "UNKNOWN", "quantity": 5, "occurred_at": "2026-08-07T03:00:00Z"},
        ])
        result = TRANSFORM.build_dashboard(records, now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc))
        today = result[(result.record_type == "TREND") & (result.date_key == "2026-08-07")].iloc[0]
        # 想定外種別の 5 が入庫へ混ざれば 15 になる。混ざっていないことを確認。
        self.assertEqual(today.inbound_quantity, 10)
        self.assertEqual(today.outbound_quantity, 3)

    def test_archived_transactions_excluded_from_today_kpi_and_trend(self):
        # 物理削除(ITEM/LOCATION)されたマスタの取引には CE が archived 印を付け、canonical な
        # RECALCULATE は残高集計から除外する。本日入出庫KPI・7日トレンドも同じ基準で archived を
        # 除外し、残高由来KPI(在庫は既に消滅)とフロー由来KPIが同一画面で食い違わないようにする。
        records = pd.DataFrame([
            # archived 済み取引（削除マスタの当日フロー）は KPI・トレンドから除外されるべき。
            {"record_type": "TRANSACTION", "transaction_type": "IN", "quantity": 50, "occurred_at": "2026-08-07T01:00:00Z", "archived": True},
            {"record_type": "TRANSACTION", "transaction_type": "OUT", "quantity": 20, "occurred_at": "2026-08-07T02:00:00Z", "archived": "true"},
            # 生存取引（archived 印なし）だけが計上される。
            {"record_type": "TRANSACTION", "transaction_type": "IN", "quantity": 8, "occurred_at": "2026-08-07T03:00:00Z"},
            {"record_type": "TRANSACTION", "transaction_type": "OUT", "quantity": 2, "occurred_at": "2026-08-07T04:00:00Z", "archived": "false"},
        ])
        result = TRANSFORM.build_dashboard(records, now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc))

        def kpi(key):
            return result[(result.record_type == "KPI") & (result.metric_key == key)].iloc[0].metric_value

        # archived の IN/OUT を数えれば本日入庫=2/出庫=2 になる。生存分だけの 1/1 であること。
        self.assertEqual(kpi("TODAY_IN_COUNT"), 1)
        self.assertEqual(kpi("TODAY_OUT_COUNT"), 1)
        today = result[(result.record_type == "TREND") & (result.date_key == "2026-08-07")].iloc[0]
        # archived の 50/20 が混ざれば 58/22 になる。生存分だけの 8/2 であること。
        self.assertEqual(today.inbound_quantity, 8)
        self.assertEqual(today.outbound_quantity, 2)

    def test_alert_rows_are_capped_at_100_and_newest_first(self):
        # 通知履歴(ALERT_HISTORY)は運用で増え続ける。ダッシュボードは created_at 降順で
        # 最新100件だけを載せ、古い履歴で行数が際限なく膨らむのを防ぐ。
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rows = [
            {
                "record_type": "ALERT_HISTORY", "alert_id": f"ALERT-{index:03d}",
                "event_type": "SHORTAGE", "notification_status": "PENDING",
                "notification_subject": "在庫不足", "current_quantity": index,
                "created_at": (base + timedelta(minutes=index)).isoformat().replace("+00:00", "Z"),
            }
            for index in range(120)
        ]
        result = TRANSFORM.build_dashboard(pd.DataFrame(rows), now=datetime(2026, 8, 7, tzinfo=timezone.utc))
        alerts = result[result.record_type == "ALERT"]
        self.assertEqual(len(alerts), 100)  # 120件でも100件でキャップ
        ids = list(alerts.alert_id)
        self.assertEqual(ids[0], "ALERT-119")   # 最新(created_at 最大)が先頭
        self.assertEqual(ids[-1], "ALERT-020")  # 最新100件目
        self.assertNotIn("ALERT-000", ids)      # 最古20件(000〜019)は落ちる

    def test_alert_rows_tie_break_by_alert_id_when_created_at_equal(self):
        # created_at が同値のとき（同一バッチ生成・同一秒など）は alert_id 昇順で決定的に並べ、
        # 不安定ソートで順序が実行ごとに揺れないことを保証する。フロントのフォールバック集計
        # （domo-access.js）も同じタイブレークを持ち、最新N件の集合・並びを一致させる。
        newest = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        older = datetime(2026, 2, 1, 9, 0, 0, tzinfo=timezone.utc)
        rows = [
            {"record_type": "ALERT_HISTORY", "alert_id": "ALERT-B", "event_type": "SHORTAGE",
             "notification_status": "SENT", "created_at": newest.isoformat().replace("+00:00", "Z")},
            {"record_type": "ALERT_HISTORY", "alert_id": "ALERT-A", "event_type": "SHORTAGE",
             "notification_status": "SENT", "created_at": newest.isoformat().replace("+00:00", "Z")},
            {"record_type": "ALERT_HISTORY", "alert_id": "ALERT-Z", "event_type": "SHORTAGE",
             "notification_status": "SENT", "created_at": older.isoformat().replace("+00:00", "Z")},
        ]
        result = TRANSFORM.build_dashboard(pd.DataFrame(rows), now=datetime(2026, 8, 7, tzinfo=timezone.utc))
        ids = list(result[result.record_type == "ALERT"].alert_id)
        # 新しい created_at グループが先（降順）、その中は alert_id 昇順、最後に古いグループ。
        self.assertEqual(ids, ["ALERT-A", "ALERT-B", "ALERT-Z"])


    def test_null_or_blank_names_fall_back_to_code_then_unset_label(self):
        # item_name/location_name が NULL/NaN/空でも、表示ラベルが "nan"/"None" として
        # 出てはならない。名称→コード→「未設定」の多段フォールバックになることを確認する
        # （.astype(str) が NaN を "nan" に変換する罠への回帰ガード）。
        records = pd.DataFrame([
            {"record_type": "BALANCE", "balance_key": "L1|I1", "item_code": "ITEM-001", "item_name": None, "location_code": "LOC-01", "location_name": "中央倉庫", "quantity": 5},
            {"record_type": "BALANCE", "balance_key": "L2|I2", "item_code": "ITEM-002", "item_name": "", "location_code": "LOC-02", "location_name": float("nan"), "quantity": 3},
            {"record_type": "BALANCE", "balance_key": "L3|I3", "item_code": None, "item_name": float("nan"), "location_code": "", "location_name": None, "quantity": 2},
        ])
        result = TRANSFORM.build_dashboard(records, now=datetime(2026, 8, 7, 12, tzinfo=timezone.utc))
        item_labels = set(result[result.record_type == "ITEM_STOCK"].label)
        location_labels = set(result[result.record_type == "LOCATION"].label)
        # NULL/空の名称が "nan"/"None" のまま出ていないこと。
        self.assertNotIn("nan", item_labels)
        self.assertNotIn("None", item_labels)
        self.assertNotIn("nan", location_labels)
        self.assertNotIn("None", location_labels)
        # 名称欠落はコードへ、コードも欠落なら「未設定」へ落ちる。
        self.assertEqual(item_labels, {"ITEM-001", "ITEM-002", "未設定"})
        self.assertEqual(location_labels, {"中央倉庫", "LOC-02", "未設定"})

    def test_alert_history_limit_matches_frontend_config(self):
        # ダッシュボードに載せる通知履歴(ALERT)の件数上限は、正準の集計DataFlow(ここ)と
        # FE フォールバック集計(config.js の analytics.alertHistoryLimit)で必ず同値に保つ。
        # 片方だけ変えると取得経路(DataFlow到達 vs フォールバック)でダッシュボードのALERT行集合が
        # 食い違う。過去に 100(DataFlow)≠30(config) のドリフトがあったため、値の一致をテストで固定する。
        config_path = pathlib.Path(__file__).parents[1] / "pro-code" / "config.js"
        config_source = config_path.read_text(encoding="utf-8")
        match = re.search(r"alertHistoryLimit:\s*(\d+)", config_source)
        self.assertIsNotNone(match, "config.js に alertHistoryLimit が見つからない")
        self.assertEqual(int(match.group(1)), TRANSFORM.ALERT_HISTORY_LIMIT)


if __name__ == "__main__":
    unittest.main()
