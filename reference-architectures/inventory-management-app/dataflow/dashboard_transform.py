"""Magic ETL Python tile for the unified inventory dashboard DataSet."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

try:
    import domomagic as dm
except ImportError:  # Allows local unit tests of build_dashboard.
    dm = None


OUTPUT_COLUMNS = [
    "record_type", "metric_key", "label", "metric_value", "date_key",
    "inbound_quantity", "outbound_quantity", "balance_key", "item_code",
    "item_name", "location_code", "location_name", "quantity",
    "minimum_quantity", "shortage_quantity", "is_shortage",
    "last_transaction_at", "age_days", "alert_id", "event_type",
    "notification_status", "notification_subject", "created_at",
    # ai_summary は後段の AI要約タイルが AI_NOTE 行に埋める列。集計行では常に
    # 空(None)。UnionAll で集計行と AI_NOTE 行の列を揃えるため、両分岐が同じスキーマ
    # を持てるよう集計側にも列だけを用意しておく（値は入れない）。
    "ai_summary",
]


# ダッシュボードの表示ウィンドウ定数。FE(config.js の analytics.*)と同じ値を持ち、
# ここ（集計DataFlow）が「正準の定義」。片方だけ変えると DataFlow 到達時と FE 側の
# フォールバック集計(domo-access.js buildDashboardRows)とで数字が食い違うため、両者は
# 必ず同値に保つ。対応: TREND_WINDOW_DAYS↔trendWindowDays /
# DORMANT_THRESHOLD_DAYS↔dormantThresholdDays / ALERT_HISTORY_LIMIT↔alertHistoryLimit。
TREND_WINDOW_DAYS = 7        # 入出庫トレンドを直近何日ぶん表示するか
DORMANT_THRESHOLD_DAYS = 30  # 最終取引からこの日数を超えた在庫を「滞留」と見なす
ALERT_HISTORY_LIMIT = 100    # 通知履歴(ALERT)をダッシュボードへ載せる最新件数の上限


def _frame(value):
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _column(frame, name, default=None):
    if name in frame.columns:
        return frame[name]
    return pd.Series([default] * len(frame), index=frame.index)


def _number(frame, name):
    return pd.to_numeric(_column(frame, name, 0), errors="coerce").fillna(0.0)


def _append(rows, record_type, **values):
    row = {column: None for column in OUTPUT_COLUMNS}
    row.update(values)
    row["record_type"] = record_type
    rows.append(row)


def _join_distinct(values):
    """検索ハンドル用に、空でない値を挿入順・重複排除でスペース連結する(無ければ None)。"""
    seen = []
    for value in values:
        text = "" if value is None else str(value).strip()
        if text and text not in seen:
            seen.append(text)
    return " ".join(seen) or None


def build_dashboard(records, now=None):
    """Build dashboard rows from the one standard-sync AppDB DataSet."""
    records = _frame(records)
    record_types = _column(records, "record_type", "").astype(str).str.upper()
    transactions = records[record_types == "TRANSACTION"].copy()
    # 物理削除(ITEM/LOCATION)されたマスタの取引には CE が archived 印を付け、canonical な
    # RECALCULATE(inventory_service.py) はそれを残高集計から除外する。本日入出庫KPIと7日トレンドも
    # 同じ基準で archived を落とし、残高由来KPI(在庫は既に消滅)とフロー由来KPIが同一画面で食い違わない
    # ようにする。archived 列が未同期の環境でも _column の既定("")で全行 active 扱いとなり無害。
    if len(transactions):
        archived_flag = _column(transactions, "archived", "").astype(str).str.lower().isin(["true", "1"])
        transactions = transactions[~archived_flag].copy()
    balances = records[record_types == "BALANCE"].copy()
    alerts = records[record_types == "ALERT_HISTORY"].copy()
    current = now or datetime.now(timezone.utc)
    rows = []

    balance_quantities = _number(balances, "quantity")
    shortages = balances[
        _column(balances, "is_shortage", False).astype(str).str.lower().isin(["true", "1"])
    ].copy()
    unique_items = _column(balances, "item_code", "").replace("", pd.NA).dropna().nunique()
    occurred = pd.to_datetime(_column(transactions, "occurred_at", None), errors="coerce", utc=True)
    today_mask = occurred.dt.date == current.date() if len(occurred) else pd.Series([], dtype=bool)
    transaction_types = _column(transactions, "transaction_type", "").astype(str).str.upper()
    today_in_count = int((today_mask & (transaction_types == "IN")).sum()) if len(occurred) else 0
    today_out_count = int((today_mask & (transaction_types == "OUT")).sum()) if len(occurred) else 0

    for key, label, value in (
        ("TOTAL_QUANTITY", "総在庫数", float(balance_quantities.sum())),
        ("ITEM_COUNT", "在庫品目", int(unique_items)),
        ("SHORTAGE_COUNT", "在庫不足", int(len(shortages))),
        ("TODAY_IN_COUNT", "本日の入庫", today_in_count),
        ("TODAY_OUT_COUNT", "本日の出庫", today_out_count),
    ):
        _append(rows, "KPI", metric_key=key, label=label, metric_value=value)

    if len(balances):
        # 表示ラベルは名称優先・コード次点・最後に「未設定」で多段フォールバックする。
        # item_name が NULL/NaN の残高でもラベルが "nan"/"None" にならないよう、判定前に
        # fillna("") で空文字へ正規化してから空判定する（.astype(str) は NaN を "nan" に
        # 変換してしまい、素の != "" では非空扱いになって NaN がそのまま残るため）。
        item_code_label = _column(balances, "item_code", "").fillna("").astype(str).str.strip()
        item_name_label = _column(balances, "item_name", "").fillna("").astype(str).str.strip()
        item_names = item_name_label.where(item_name_label != "", item_code_label)
        item_names = item_names.where(item_names != "", "未設定")
        # 表示は label(名称)のみ。検索ヒット用にコード・名称も併せて載せる（見た目は不変で、
        # 在庫のある品目をコード(例: ITEM-11)で検索してもヒットするようにするため）。
        item_frame = pd.DataFrame({"label": item_names, "quantity": balance_quantities, "code": item_code_label, "name": item_name_label})
        item_groups = item_frame.groupby("label", dropna=False)
        for label, value in item_groups["quantity"].sum().sort_values(ascending=False).items():
            group = item_groups.get_group(label)
            _append(rows, "ITEM_STOCK", label=str(label), metric_value=float(value),
                    item_code=_join_distinct(group["code"]), item_name=_join_distinct(group["name"]))

        location_code_label = _column(balances, "location_code", "").fillna("").astype(str).str.strip()
        location_name_label = _column(balances, "location_name", "").fillna("").astype(str).str.strip()
        location_names = location_name_label.where(location_name_label != "", location_code_label)
        location_names = location_names.where(location_names != "", "未設定")
        location_frame = pd.DataFrame({"label": location_names, "quantity": balance_quantities, "code": location_code_label, "name": location_name_label})
        location_groups = location_frame.groupby("label", dropna=False)
        for label, value in location_groups["quantity"].sum().sort_values(ascending=False).items():
            group = location_groups.get_group(label)
            _append(rows, "LOCATION", label=str(label), metric_value=float(value),
                    location_code=_join_distinct(group["code"]), location_name=_join_distinct(group["name"]))

    for _, row in shortages.iterrows():
        _append(rows, "SHORTAGE", **{name: row.get(name) for name in OUTPUT_COLUMNS if name in row.index and name != "record_type"})

    last_dates = pd.to_datetime(_column(balances, "last_transaction_at", None), errors="coerce", utc=True)
    if len(last_dates):
        ages = (pd.Timestamp(current) - last_dates).dt.days
        for index in balances.index[ages > DORMANT_THRESHOLD_DAYS]:
            row = balances.loc[index]
            _append(rows, "DORMANT", age_days=int(ages.loc[index]), **{name: row.get(name) for name in OUTPUT_COLUMNS if name in row.index and name not in {"record_type", "age_days"}})

    start = current.date() - timedelta(days=TREND_WINDOW_DAYS - 1)
    trend = {(start + timedelta(days=offset)).isoformat(): {"in": 0.0, "out": 0.0} for offset in range(TREND_WINDOW_DAYS)}
    for index, row in transactions.iterrows():
        parsed = occurred.loc[index] if index in occurred.index else pd.NaT
        if pd.isna(parsed):
            continue
        key = parsed.date().isoformat()
        if key not in trend:
            continue
        quantity = float(pd.to_numeric(pd.Series([row.get("quantity", 0)]), errors="coerce").fillna(0).iloc[0])
        transaction_type = str(row.get("transaction_type", "")).upper()
        # 入出庫トレンドは実際の入庫(IN)・出庫(OUT)の「流量」だけを積む。
        # 未知の種別は流量として数えない（想定外データが混ざっても数字が歪まないようにする）。
        if transaction_type == "OUT":
            trend[key]["out"] += quantity
        elif transaction_type == "IN":
            trend[key]["in"] += quantity
    for key, values in trend.items():
        _append(rows, "TREND", date_key=key, inbound_quantity=values["in"], outbound_quantity=values["out"])

    if len(alerts):
        # created_at 降順で最新 ALERT_HISTORY_LIMIT 件だけを載せる。created_at が同値のとき
        # （同一バッチ生成・同一秒など）は alert_id 昇順で決定的に並べ、既定の不安定ソートで
        # 順序が揺れて最新N件のキャップ境界に載る/落ちるが実行ごとに食い違うのを防ぐ。
        # フロントのフォールバック集計（domo-access.js）も同じタイブレークで最新集合を一致させる。
        sorted_alerts = (
            alerts.assign(
                _sort=pd.to_datetime(_column(alerts, "created_at", None), errors="coerce", utc=True),
                _tie=_column(alerts, "alert_id", "").astype(str),
            )
            .sort_values(["_sort", "_tie"], ascending=[False, True], kind="stable")
            .head(ALERT_HISTORY_LIMIT)
        )
        for _, row in sorted_alerts.iterrows():
            _append(rows, "ALERT", **{name: row.get(name) for name in OUTPUT_COLUMNS if name in row.index and name != "record_type"})

    output = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    for numeric_column in ("metric_value", "inbound_quantity", "outbound_quantity", "quantity", "minimum_quantity", "shortage_quantity", "age_days"):
        output[numeric_column] = pd.to_numeric(output[numeric_column], errors="coerce")
    return output


def run_domo_tile():
    if dm is None:
        raise RuntimeError("domomagic is available only inside a Domo Python tile")
    records = dm.read_dataframe("在庫管理レコード")
    result = build_dashboard(records)
    dm.write_dataframe(result)


if dm is not None:
    run_domo_tile()
