"""Magic ETL Python tile: build one AI-note input row per stock balance.

読み取り: 標準同期の在庫 DataSet（読み込みタイル「在庫管理レコード」）。
ここから残高レコード（record_type='BALANCE'、品目×ロケーション単位）だけを抜き出す。
出力: 残高1件につき record_type='AI_NOTE' の1行。ai_input_text にその品目・
ロケーションの在庫状況を日本語の素文でまとめ、後段の TextGeneration タイルが
1行ずつ短い助言ノートへ変換する（品目カードに添える一言コメント）。

なぜ「品目ごと」か（重要な設計判断）:
Domo の AI テキスト生成タイルは BATCH 実行のみで、入力が 100 行未満だと失敗する
（DP-TGTFR「バッチテキスト生成には少なくとも100行が必要」）。したがって「在庫全体を
1行に要約する」設計は batch-only インスタンスでは実現できない（100行入れれば100行出る）。
そこで残高（品目×ロケーション）を1行=1ノートに割り当てる per-entity パターンを採る。
これは batch-only の AI テキスト生成に対する移植可能な正攻法（1入力=1出力を保てる）。
デモでは残高が 100 件以上になるようシードしてあるため、このタイルの出力も 100 行を超える。

なぜ集計タイルと分けるか: 集計（ダッシュボード行）と AI 入力整形は責務が異なる。
1タイル1責務にした方が教材として読みやすく、TextGeneration へ渡す入力を
「1行=1品目・ai_input_text の1カラム」に保てる。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

try:
    import domomagic as dm
except ImportError:  # ローカル単体テストで build_ai_input を直接呼べるようにする。
    dm = None


# 読み込みタイルの表示名。read_dataframe はこの名前で標準同期 DataSet を読む安定契約。
LOAD_TILE_NAME = "在庫管理レコード"

# 出力スキーマ = 集計行と同じコア列 + ai_input_text（AIへ渡す素文）。
# ai_summary はここでは持たない: 後段の TextGeneration が構造化出力として ai_summary 列を
# 新規に作るため、同名列を先に出すと出力列名と衝突する。UnionAll では集計側が ai_summary を
# 持ち、AI側は TextGeneration 生成分で列が揃うので、両分岐とも最終的に同じ列集合になる。
BASE_COLUMNS = [
    "record_type", "metric_key", "label", "metric_value", "date_key",
    "inbound_quantity", "outbound_quantity", "balance_key", "item_code",
    "item_name", "location_code", "location_name", "quantity",
    "minimum_quantity", "shortage_quantity", "is_shortage",
    "last_transaction_at", "age_days", "alert_id", "event_type",
    "notification_status", "notification_subject", "created_at",
]
OUTPUT_COLUMNS = BASE_COLUMNS + ["ai_input_text"]

# AI へ渡す前に float へ正規化する数値列。Magic ETL のタイルスキーマで DOUBLE 宣言のため、
# None のままだと列 dtype が object になり DOUBLE への自動変換が拒否される（DP-UNSUTYCO）。
NUMERIC_COLUMNS = ("metric_value", "inbound_quantity", "outbound_quantity", "quantity", "minimum_quantity", "shortage_quantity", "age_days")


def _frame(value):
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _column(frame, name, default=None):
    if name in frame.columns:
        return frame[name]
    return pd.Series([default] * len(frame), index=frame.index)


def _num(value) -> float:
    """単一値を欠損に強い float へ正規化する（"", None, NaN → 0.0）。"""
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0.0).iloc[0])


def _fmt(value) -> str:
    """整数なら整数表記、そうでなければ小数を素直に文字列化する。"""
    number = _num(value)
    return str(int(number)) if number == int(number) else str(number)


def _is_true(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _age_days(last_transaction_at, current) -> int | None:
    """最終入出庫からの経過日数。日付が無ければ None（＝不明）。"""
    parsed = pd.to_datetime(pd.Series([last_transaction_at]), errors="coerce", utc=True).iloc[0]
    if pd.isna(parsed):
        return None
    return int((pd.Timestamp(current) - parsed).days)


def _digest(row, current) -> str:
    """1件の残高から、AI に渡す日本語の素文（数行）を組み立てる。"""
    item_name = str(row.get("item_name") or row.get("item_code") or "未設定")
    item_code = str(row.get("item_code") or "")
    place = str(row.get("location_name") or row.get("location_code") or "")
    quantity = _fmt(row.get("quantity"))
    minimum = _num(row.get("minimum_quantity"))
    shortage = _fmt(row.get("shortage_quantity"))
    is_shortage = _is_true(row.get("is_shortage"))

    lines = [
        f"品目: {item_name}（{item_code}）" if item_code else f"品目: {item_name}",
        f"ロケーション: {place}" if place else "ロケーション: 未設定",
        f"現在庫: {quantity}",
    ]
    # 最小在庫ルールが無い(=0)品目は基準値を書かない。あるものだけ基準と過不足を渡す。
    if minimum > 0:
        lines.append(f"基準在庫: {_fmt(minimum)}")
        lines.append(f"状態: 在庫不足（不足 {shortage}）" if is_shortage else "状態: 適正")
    else:
        lines.append("状態: 基準未設定")

    age = _age_days(row.get("last_transaction_at"), current)
    if age is not None:
        lines.append(f"最終入出庫からの経過: {age}日")
    return "\n".join(lines)


def build_ai_input(records, now=None):
    """在庫レコードから、残高1件につき1行の AI ノート入力を組み立てる。

    Args:
        records: 読み込みタイルの出力 DataFrame（record_type で種別を識別）。
        now: 生成時刻（省略時は現在UTC）。テストで固定するために引数化している。

    Returns:
        record_type='AI_NOTE' の行を残高件数ぶん持つ DataFrame（列は OUTPUT_COLUMNS）。
        各行の ai_input_text にその品目・ロケーションの在庫状況を日本語の素文で格納する。
    """
    df = _frame(records)
    record_types = _column(df, "record_type", "").astype(str).str.upper()
    balances = df[record_types == "BALANCE"].copy()
    current = now or datetime.now(timezone.utc)

    rows = []
    for _, balance in balances.iterrows():
        row = {column: None for column in OUTPUT_COLUMNS}
        row["record_type"] = "AI_NOTE"
        # 品目カードへノートを突き合わせられるよう、識別に使う列は残高からそのまま引き継ぐ。
        for name in ("balance_key", "item_code", "item_name", "location_code", "location_name",
                     "quantity", "minimum_quantity", "shortage_quantity", "is_shortage", "last_transaction_at"):
            row[name] = balance.get(name)
        row["label"] = str(balance.get("item_name") or balance.get("item_code") or "在庫")
        row["created_at"] = current.isoformat()
        row["ai_input_text"] = _digest(balance, current)
        rows.append(row)

    output = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    for numeric_column in NUMERIC_COLUMNS:
        output[numeric_column] = pd.to_numeric(_column(output, numeric_column), errors="coerce")
    return output


def run_domo_tile():
    if dm is None:
        raise RuntimeError("domomagic is available only inside a Domo Python tile")
    records = dm.read_dataframe(LOAD_TILE_NAME)
    dm.write_dataframe(build_ai_input(records))


if dm is not None:
    run_domo_tile()
