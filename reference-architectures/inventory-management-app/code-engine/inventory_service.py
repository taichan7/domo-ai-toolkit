"""Domo ネイティブの在庫入出庫サービス（リファレンスアーキテクチャの中核）。

公開するのはディスパッチャ ``inventory_api`` の1つだけ。実装は6つの非公開ヘルパーに
分け、無引数ファクトリ ``_service()`` 内へまとめて top-level から外す。6ヘルパーの
役割は次のとおり:

- ``is_true``            : AppDB の真偽値（bool / "true" / "1"）を統一的に解釈する
- ``resolve_recipient_email`` : 在庫通知の宛先メールを解決する
- ``records``            : AppDB の全 CRUD と標準同期の即時起動を一手に担う
- ``register``           : 入出庫1件の検証・記録・見込み在庫・しきい値イベントを確定する
- ``notify_now``         : 現時点で最も深刻な不足に対し手動で不足通知を起動する（Workflow の
  起動は自動経路と同じく CE が行い、最新の有効版を実行時に解決する）
- ``admin``              : 残高再計算・デモ投入・マスタ保守（ITEM/LOCATION/RULE の CRUD）を担う管理者専用の入口

全レコードは1つの AppDB コレクションに同居し、``record_type`` で種別を区別する。

想定内の業務エラーは、公開用のエラーボディ（``{"code", "message", "details"}`` の dict）を
第1引数に持たせた組込み ``Exception`` として送出する（Code Engine は独自の例外クラスを
持ち込めないため専用クラスを定義しない）。公開ディスパッチャ ``inventory_api`` がその形状を
見て ``{"ok": False, "error": ...}`` に変換し、想定外の例外は ``INTERNAL_ERROR`` に丸める。
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import codeengine


LOGGER = logging.getLogger(__name__)
COLLECTION_ID = "__COLLECTION_RECORDS__"
# 標準同期 DataSet の即時エクスポート起動に使う datastoreId。provisioner が実IDへ差し替える。
# 未設定（プレースホルダのまま）なら sync キックは無操作にフォールバックする。
DATASTORE_ID = "__DATASTORE_ID__"
# 通知Workflowモデルの物理ID。provisioner（provision_domo.py）が実IDへ差し替える。CE が
# モデルの有効版を実行時に解決して起動するため、Workflow を改版・release してもカードの
# 再配線・再埋め込みは不要（版の解決をフロントの配線スナップショットに依存させない）。
# プレースホルダのまま（未設定）なら通知Workflowは起動せず、ALERT_HISTORY へ FAILED を記録する。
WORKFLOW_MODEL_ID = "__WORKFLOW_MODEL_ID__"
# 起動時に送る messageName。Workflow の開始タイル（rootNode）のタイトルと一致させる
# （provisioner の agent_email_workflow_definition が「不足通知を開始」へ設定する）。
WORKFLOW_START_MESSAGE_NAME = "不足通知を開始"
ADMIN_USER_IDS = {"__ADMIN_USER_ID__"}
MAX_QUANTITY = 1_000_000.0
MASTER_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,39}$")
# MANAGE_MASTER が受け付けるマスタ CRUD の action 集合（境界での許可リスト）。RECALCULATE /
# SEED は管理者専用でも「別 operation」として明示的に呼ぶ設計なので、この集合には含めない。
# こうして MANAGE_MASTER 経由で再計算やデモ投入を誤って誘発させない（_admin へ届く action を
# ディスパッチャで絞り込む単一の検証境界）。
MASTER_ACTIONS = ("UPSERT_ITEM", "UPSERT_LOCATION", "UPSERT_RULE", "DELETE_ITEM", "DELETE_LOCATION", "DELETE_RULE", "LIST_MASTERS")
# AppDB の documents/query は1応答あたり最大 10,000 件でページを打ち切る
# （プラットフォーム上限）。_records の query はこの件数を1ページとして limit/offset で
# 全ページを辿るため、生成デモや長期運用で台帳が1万件を超えても全件を集められる。
# テストではここを小さな値に差し替え、複数ページの集約を検証する。
QUERY_PAGE_SIZE = 10_000
# AppDB は「作成(POST documents) を受理した直後」から「query(POST documents/query) の
# インデックスに現れる」までに短い遅延（結果整合性）がある。通常は 1 秒未満だが、SEED の
# ように「多数の作成 → 直後に同じ文書を検索して集計」を1回の呼び出しで畳み掛けると、
# インデックス反映前の query が空振りし INVALID_ITEM や BALANCE の作り込み不足を招く。
# await_queryable はこの窓を「作成した文書がインデックスに現れるまで」の短いバックオフで
# 吸収するための待機予算。CE ランタイムは LAMBDA なので time.sleep がそのまま使える。
# 8 回 × 0.75 秒 ＝ 最悪でも約 5.25 秒（既に見えていれば query 1 回・sleep 0 で即収束）。
APPDB_CONSISTENCY_ATTEMPTS = 8
APPDB_CONSISTENCY_DELAY_SECONDS = 0.75


def _service() -> dict:
    """非公開ヘルパー6種を1スコープに束ねて「名前→関数」の dict で返す内部ファクトリ。

    全ヘルパーをこのファクトリ内に定義して top-level から外し、公開 ``def`` を
    ``inventory_api`` の1つに保つ。ヘルパー同士は素の名前で呼び合い、公開関数は
    ``svc = _service()`` で受けて ``svc["register"]`` のように名前で辿る。

    ディスパッチ対象の6ヘルパー（``_`` 始まり）に加え、通知文面を自動経路（register）と
    手動経路（notify_now）で共有するための内部ユーティリティ（``describe_shortage`` /
    ``current_shortages`` / ``shortage_lines``）と、通知Workflowの起動（``start_notification_workflow``
    ＝最新の有効版を実行時に解決してサーバー側で開始）を同スコープに持つ。これらは dict へは
    返さずディスパッチもしない下請けで、6ヘルパーの契約には含めない。

    Returns:
        ヘルパー名→関数の dict（``is_true`` / ``resolve_recipient_email`` / ``records`` /
        ``register`` / ``notify_now`` / ``admin``）。
    """
    def _is_true(value: Any) -> bool:
        """AppDB の真偽値を統一的に解釈する。

        AppDB へは真偽値が native bool でも "true" / "1" といった文字列でも入り得るため、
        どの表現でも同じく真として扱えるようにする。

        Args:
            value: 判定対象の値（bool・文字列・その他）。

        Returns:
            True 相当（bool の True、または "true" / "1"）なら True。
        """
        return value is True or str(value).strip().lower() in {"true", "1"}


    def _resolve_recipient_email(request: dict, user: dict) -> str:
        """在庫通知の宛先メールアドレスを解決する。

        ``get_execution_information`` はインスタンスによってメールを返さないため、
        Pro Code が People API で解決した ``operator_email`` をリクエストで受け渡す。
        実行コンテキストに有効なアドレスが無い場合のみ、この値へフォールバックする。

        Args:
            request: Pro Code から渡るリクエスト。``operator_email`` を含み得る。
            user: 実行コンテキストから構築した利用者。``email`` を含み得る。

        Returns:
            "@" を含む宛先アドレス。解決できなければ空文字を返す。
        """
        email = str(user.get("email") or "").strip()
        if "@" in email:
            return email  # 実行コンテキストのメールを最優先する。
        return str(request.get("operator_email") or "").strip()


    def _records(command: str, record_type: str = "", *, field: str = "", value: Any = None,
                 record_key: str = "", content: Optional[dict] = None,
                 document_id: str = "") -> Any:
        """AppDB の全 CRUD と標準同期の即時エクスポートを一手に担う。

        これ一つで AppDB の全 CRUD を担い、リファレンスとして追加(create)・
        参照(query/find)・更新(upsert)・物理削除(delete)を実演する。``delete`` は
        ドキュメントIDを指定した不可逆な物理削除で、論理フラグは残さない。
        ``sync`` は AppDB→標準同期 DataSet のエクスポートを即時起動する前倒し実行で、
        追加・更新・削除の直後にダッシュボードへ数秒で反映するために使う（既定の
        約15分間隔スケジュールを待たない）。DataSet へ行を直接書き込む独自同期ではなく、
        あくまで Domo 標準同期の前倒しである。datastoreId 未設定時は無操作で返す。

        Args:
            command: "query" / "find" / "create" / "upsert" / "delete" / "sync" のいずれか。
            record_type: 対象レコード種別（ITEM・BALANCE 等）。sync/delete では不要。
            field: query/find の絞り込みフィールド名（``content.`` は内部で付与）。
            value: field に対応する絞り込み値。
            record_key: create/upsert の一意キー（種別内で一意）。
            content: 書き込む本体、または query/find の追加条件。
            document_id: delete 対象の AppDB ドキュメントID。

        Returns:
            query は行の配列、find は先頭1行 or None、create/upsert は API 応答や
            ("created"/"updated", 本体) のタプル、delete は削除したドキュメントID、
            sync は前倒しエクスポートの応答（未設定時は None）。

        Raises:
            Exception: コレクション未設定、必須の document_id 欠落、未知の command のとき。
                公開エラーボディ（code/message を持つ dict）を第1引数に持つ想定内の業務エラー。
        """
        if command == "sync":
            # datastoreId が未設定（プレースホルダのまま）なら標準同期の前倒し先が無い。無操作で返す。
            if not DATASTORE_ID or DATASTORE_ID.startswith("__"):
                return None
            # 空ボディのエクスポート起動。datastoreId をキーにする点に注意（collectionId ではない）。
            return codeengine.send_request("post", f"api/datastores/v1/export/{DATASTORE_ID}", None)

        if not COLLECTION_ID or COLLECTION_ID.startswith("__"):
            raise Exception({"code": "CONFIGURATION_ERROR", "message": "AppDBコレクションが設定されていません。", "details": {}})

        if command in {"query", "find"}:
            # content の追加条件は AppDB の documents/query が要求する content.<field> 名前空間へ
            # 正規化する（record_type/field と同じ規則）。付与しないと生キー（例 is_shortage）が
            # 格納フィールド content.is_shortage に一致せず、docstring が謳う絞り込みが黙って無効化する。
            # 既に content. 付きのキーは二重付与しない。
            criteria = {
                (key if str(key).startswith("content.") else f"content.{key}"): val
                for key, val in (content or {}).items()
            }
            if record_type:
                criteria["content.record_type"] = record_type
            if field:
                criteria[f"content.{field}"] = value
            # AppDB の documents/query は1応答を最大 QUERY_PAGE_SIZE 件（プラットフォーム上限
            # 10,000 件）で打ち切る。limit/offset を「クエリ文字列」で送り、返却が1ページに満たなく
            # なるまで繰り返して全件を集める（body は絞り込み条件、ページングは query string が契約）。
            # これがないと生成デモや長期運用で台帳が1万件を超えたとき、再計算・SEED の冪等判定・
            # 通知が「見えている先頭の一部」だけで走り、残高や重複判定を静かに誤る。
            # find は先頭1件で足りるため limit=1 の1往復に抑える（余計なページを取りに行かない）。
            page_size = 1 if command == "find" else max(int(QUERY_PAGE_SIZE), 1)
            rows = []
            offset = 0
            while True:
                response = codeengine.send_request(
                    "post",
                    f"api/datastores/v2/collections/{COLLECTION_ID}/documents/query?limit={page_size}&offset={offset}",
                    criteria,
                ) or []
                if isinstance(response, dict):
                    response = response.get("documents") or response.get("items") or response.get("result") or []
                page = [document for document in response if isinstance(document, dict)]
                for document in page:
                    row = dict(document.get("content") if isinstance(document.get("content"), dict) else document)
                    row["_document_id"] = document.get("id")
                    rows.append(row)
                    if command == "find":
                        return row
                # 1ページ未満しか返らなければ最終ページ。それ以外は offset を進めて次ページを取る。
                if len(response) < page_size:
                    break
                offset += page_size
            return (rows[0] if rows else None) if command == "find" else rows

        payload = dict(content or {})
        payload.update({"record_type": record_type, "record_key": record_key})
        if command == "create":
            return codeengine.send_request(
                "post",
                f"api/datastores/v1/collections/{COLLECTION_ID}/documents",
                {"content": payload},
            ) or {}
        if command == "upsert":
            existing = _records("find", record_type, field="record_key", value=record_key)
            if existing:
                document_id = existing.get("_document_id")
                if not document_id:
                    raise Exception({"code": "DOCUMENT_ID_MISSING", "message": "更新対象ドキュメントがありません。", "details": {}})
                merged = {name: item for name, item in existing.items() if not name.startswith("_")}
                merged.update(payload)
                codeengine.send_request(
                    "put",
                    f"api/datastores/v1/collections/{COLLECTION_ID}/documents/{document_id}",
                    {"content": merged},
                )
                return "updated", merged
            _records("create", record_type, record_key=record_key, content=payload)
            return "created", payload
        if command == "delete":
            # AppDB の物理削除(D)。論理フラグを残さずドキュメント自体を消す不可逆操作。
            if not document_id:
                raise Exception({"code": "DOCUMENT_ID_MISSING", "message": "削除対象ドキュメントがありません。", "details": {}})
            codeengine.send_request(
                "delete",
                f"api/datastores/v1/collections/{COLLECTION_ID}/documents/{document_id}",
            )
            return document_id
        raise Exception({"code": "INVALID_STORE_COMMAND", "message": "AppDB操作が正しくありません。", "details": {}})


    def await_queryable(record_type: str, key_field: str, expected_keys) -> dict:
        """作成した文書が query インデックスへ現れるまで待つ、SEED 専用の結果整合性バリア。

        AppDB の作成(POST documents)は即座に受理されるが、query(POST documents/query)の
        インデックスへ反映されるまで短い遅延がある。SEED のように「多数作成→直後に同じ文書を
        検索して集計」を1呼び出しで畳み掛けると、反映前の query が空振りして INVALID_ITEM や
        残高の作り込み不足を招く。この関数は expected_keys が record_type の query に出そろうまで
        最大 APPDB_CONSISTENCY_ATTEMPTS 回、APPDB_CONSISTENCY_DELAY_SECONDS 間隔で待つ。

        待つのは「今回作成したキー」だけにする（既存＝再実行分は先読みクエリで既に可視と
        確認済みなので待たない）。既に全て見えていれば query 1回・sleep 0 で即収束するので、
        冪等な再 SEED に待機コストを課さない。対話経路の _register はこのバリアを通さない——
        本物の INVALID_ITEM は即座に返すべきで、待って隠してはならないため（SEED の一括投入
        でだけ結果整合性の窓を吸収する）。CE ランタイムは LAMBDA なので time.sleep が使える。

        Args:
            record_type: 可視性を待つレコード種別（ITEM / LOCATION / RULE / TRANSACTION）。
            key_field: 各文書を一意に識別する content フィールド名（item_code / request_id 等）。
            expected_keys: 出そろうのを待つキー集合（今回作成した分のみ）。

        Returns:
            {"converged": 全キーが可視になったか(bool), "attempts": query 実行回数(int),
             "missing": 収束打ち切り時に未反映だったキーの一覧(list)} の dict。決して例外は
            投げない（best-effort。収束しなくても呼び出し側が現状の可視分で最終判断する）。
        """
        remaining = {str(key) for key in (expected_keys or set()) if key not in (None, "")}
        if not remaining:
            # 今回作成したものが無い（完全な冪等再実行）＝待つ対象なし。query も sleep もしない。
            return {"converged": True, "attempts": 0, "missing": []}
        attempts = 0
        while True:
            attempts += 1
            seen = {str(row.get(key_field)) for row in _records("query", record_type) if isinstance(row, dict)}
            remaining = {key for key in remaining if key not in seen}
            if not remaining:
                return {"converged": True, "attempts": attempts, "missing": []}
            if attempts >= APPDB_CONSISTENCY_ATTEMPTS:
                # 予算超過。ここで止めて呼び出し側へ返す（raise しない）。未反映キーは診断として持ち帰る。
                return {"converged": False, "attempts": attempts, "missing": sorted(remaining)}
            time.sleep(APPDB_CONSISTENCY_DELAY_SECONDS)

    def require_converged(phase: str, waits: dict) -> None:
        """バリアが予算内に収束しなかったら、明示エラーで SEED を中断する（SEED 専用）。

        await_queryable は best-effort で「収束したか」を返すだけ。反映待ちが待機予算を超えた
        まま先へ進むと、①マスタ側なら直後の _register が INVALID_ITEM を投げて分かりにくい失敗に
        化け、②台帳側なら RECALCULATE が反映前の取引を取りこぼして「残高の作り込み不足」を
        黙って作る（＝失敗モード⑤そのもの・エラーすら出ない最悪形）。どちらも「一部だけ入った
        中途半端な状態」を残すより、明確なリトライ可能エラーで止める方が、非力な AI にも人にも
        親切。未反映キーを details に載せて何を待っていたかを伝える。収束していれば何もしない。

        Args:
            phase: どの段のバリアか（"masters" / "ledger"）。エラー診断に載せる。
            waits: await_queryable の戻り値を名前で束ねた dict（例 {"item": {...}, ...}）。
        """
        stalled = {name: wait["missing"] for name, wait in waits.items() if not wait.get("converged")}
        if stalled:
            raise Exception({
                "code": "APPDB_CONSISTENCY_TIMEOUT",
                "message": "AppDBへの反映待ちがタイムアウトしました。作成したデータがまだ検索に反映されていません。数十秒おいてからSEEDを再実行してください（作成済みデータは冪等に再利用され重複しません）。",
                "details": {"phase": phase, "unqueryable": stalled},
            })


    def num(value: Any) -> str:
        # 整数は小数点を出さず、小数は6桁で丸める。見出し・不足一覧（describe_shortage）だけでなく、
        # 自動経路（_register）・手動経路（_notify_now）が ALERT_HISTORY.notification_body に保存する
        # 監査文面の桁表記も同じ規則で揃える（例: 38.0 ではなく 38）。
        try:
            number = round(float(value), 6)
        except (TypeError, ValueError):
            return "0"
        return str(int(number)) if number == int(number) else str(number)

    # --- 通知整形の共有ユーティリティ（ディスパッチ対象の6ヘルパーではなく、自動経路
    #     _register と手動経路 _notify_now が同じ通知文面を作るための内部関数） ---
    def describe_shortage(row: dict, recovered: bool = False) -> str:
        """不足（または回復）1件を1行の日本語へ整形する共通ルーチン。

        通知メールの見出し（headline）にも、集約する不足一覧（shortage_lines）の各行にも
        同じ整形を使い、自動経路（_register）と手動経路（_notify_now）で表記を揃える。

        Args:
            row: 品目・ロケーション・数量を持つ dict（BALANCE 行、または見出し用の合成 dict）。
            recovered: 回復通知なら True（不足数の代わりに「基準を回復」と示す）。

        Returns:
            「品目（コード） / ロケーション（コード）：現在庫 … ／ 基準在庫 … ／ 不足 …」形式の1行。
        """
        item_code = str(row.get("item_code") or "")
        location_code = str(row.get("location_code") or "")
        where = f"{row.get('item_name') or item_code}（{item_code}） / {row.get('location_name') or location_code}（{location_code}）"
        # BALANCE 行は現在庫を quantity、見出し用の合成 dict は current_quantity で持つ。
        current_value = row.get("current_quantity")
        if current_value is None:
            current_value = row.get("quantity")
        stock = f"現在庫 {num(current_value)} ／ 基準在庫 {num(row.get('minimum_quantity'))}"
        if recovered:
            return f"{where}：{stock}（基準を回復）"
        return f"{where}：{stock} ／ 不足 {num(row.get('shortage_quantity'))}"

    def current_shortages() -> tuple:
        """現時点で通知対象となる不足を不足数の降順で返し、全不足件数も併せて返す。

        「通知対象の不足一覧」の定義（不足あり かつ notification_enabled なルール）を1か所へ
        まとめ、自動経路（_register）と手動経路（_notify_now）で同じ集合を共有する。通知を
        無効化したルールの不足は一覧から外すが、不足の存在自体は全件数（total）として返し、
        「不足はあるが通知先が全て無効」を運用者が区別できるようにする。

        Returns:
            (通知対象の不足行リスト（不足数の降順）, 全不足件数) のタプル。
        """
        shortages = [
            row for row in _records("query", "BALANCE")
            if _is_true(row.get("is_shortage")) and float(row.get("shortage_quantity") or 0) > 0
        ]
        enabled_rule_keys = {
            str(rule.get("rule_key") or "")
            for rule in _records("query", "RULE")
            if _is_true(rule.get("notification_enabled", "true"))
        }
        notifiable = sorted(
            (row for row in shortages if str(row.get("balance_key") or "") in enabled_rule_keys),
            key=lambda row: float(row.get("shortage_quantity") or 0), reverse=True,
        )
        return notifiable, len(shortages)

    def shortage_lines(rows: list, limit: int = 50) -> str:
        """通知対象の不足一覧を1行1件の確定テキストへ整形する（Workflow入力 shortage_lines 用）。

        一覧全体を「確定データ」として AI へ渡すため、AI が DataSet を読み直して件数を推測せずとも
        複数の不足を確実に1通へ集約できる。件数が多い場合は不足数の大きい順に limit 件まで示し、
        残りは「ほかN件」と件数で補って本文の肥大を防ぐ。

        Args:
            rows: 通知対象の不足行（不足数の降順を想定）。
            limit: 明示的に列挙する最大件数。

        Returns:
            改行区切りの不足一覧テキスト（対象が無ければ空文字）。
        """
        lines = [describe_shortage(row) for row in rows[:limit]]
        if len(rows) > limit:
            lines.append(f"ほか {len(rows) - limit} 件の不足があります（不足は全 {len(rows)} 件）。")
        return "\n".join(lines)

    # --- 通知Workflow起動の共有ユーティリティ（自動経路 _register と手動経路 _notify_now が
    #     同じ起動導線を使うための内部関数。ディスパッチもしない＝6ヘルパーの契約外） ---
    def workflow_version_key(value: Any) -> tuple:
        """Workflow 版番号の比較キー。非数値セグメント（1.2.0-beta 等）で ValueError にしない。"""
        parts = []
        for part in str(value or "").split("."):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(-1)
        return tuple(parts)

    def latest_active_version(model: Any) -> str:
        """モデルメタデータから「有効（release 済み）な最新版」の版番号を返す。無ければ空文字。"""
        versions = [
            row for row in (model or {}).get("versions") or []
            if isinstance(row, dict) and row.get("active") and row.get("version")
        ]
        if not versions:
            return ""
        return str(max(versions, key=lambda row: workflow_version_key(row.get("version")))["version"])

    def start_notification_workflow(alert_id: str, payload: dict) -> dict:
        """通知Workflowをサーバー側で起動し、起動結果を ALERT_HISTORY へ確定する。

        なぜフロントから直接起動しないか: ``/domo/workflow/v1/models/{alias}/start`` で起動される
        版は App Studio カードの配線（埋め込み時点のトリガー・スナップショット）が決めるため、
        Workflow を改版するたびにカードの再配線・再埋め込みが必要になる。ここでは CE がモデルの
        有効版を実行時に解決し、``api/workflow/v1/instances/message``（modelId＋version を明示）で
        起動する。よって Workflow を改版・release するだけで最新版が使われ、カード再埋め込みは
        不要になる。

        失敗は例外にせず、ALERT_HISTORY の notification_status（STARTED／FAILED）と error_message、
        および戻り値へ畳む（在庫登録という主要な結果を通知起動の失敗で覆さない）。POST の例外は
        「未起動」と断定できない（タイムアウトでも起動済みの可能性がある）ため、再実行前に通知履歴の
        確認を促す文言を記録する。

        Args:
            alert_id: 監査行（ALERT_HISTORY）の alert_id。起動結果を同じ行へ反映する。
            payload: Workflow の開始入力（event_type／headline／shortage_lines／recipient_email／
                occurred_at の5キー）。開始タイルの入力名と一致させる。

        Returns:
            ``{"started": bool, "instance_id": str, "error": str}``。instance_id は起動できたときだけ。
        """
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        def record(status: str, instance_id: str = "", error: str = "") -> None:
            # 直前に create した監査行（ALERT_HISTORY）を更新する。AppDB の query は作成直後の
            # インデックス反映に短い遅延（結果整合性）があり、そのまま find→upsert すると空振りして
            # 同じ record_key の重複行を作り得る。ここでは見つかるまで短く再試行し、行が見つかったら
            # ドキュメントIDを指定して直接 PUT する（重複行を作らない）。通常は反映済みで即収束。
            existing = {}
            for _ in range(APPDB_CONSISTENCY_ATTEMPTS):
                existing = _records("find", "ALERT_HISTORY", field="alert_id", value=alert_id) or {}
                if existing:
                    break
                time.sleep(APPDB_CONSISTENCY_DELAY_SECONDS)
            document_id = str(existing.get("_document_id") or "")
            if not document_id:
                # 不可視のままなら重複行を作るより状態更新を諦める（PENDINGのまま＝未確認として残る）。
                LOGGER.warning("alert history row not queryable; notification status update skipped: %s", alert_id)
                return
            merged = {name: value for name, value in existing.items() if not name.startswith("_")}
            merged.update({
                "alert_id": alert_id,
                "notification_status": status,
                "workflow_instance_id": str(instance_id or "")[:200],
                # STARTED のときは失敗痕（error_message）を消し、復旧後まで古い理由を引きずらない。
                "error_message": str(error or "")[:300] if status == "FAILED" else "",
                "updated_at": now,
            })
            codeengine.send_request(
                "put",
                f"api/datastores/v1/collections/{COLLECTION_ID}/documents/{document_id}",
                {"content": merged},
            )

        model_id = str(WORKFLOW_MODEL_ID or "").strip()
        if not model_id or model_id.startswith("__"):
            # 配備時に provisioner が実IDへ差し替える契約。未設定は配備不良なので、起動はせず
            # 監査へ理由を残す（黙って通知が消えるより、履歴で確認できる方が安全）。
            message = "通知Workflowを開始できませんでした（接続先が未設定です。管理者へ確認してください）。"
            record("FAILED", "", message)
            return {"started": False, "instance_id": "", "error": message}
        try:
            model = codeengine.send_request("get", f"api/workflow/v1/models/{model_id}") or {}
            version = latest_active_version(model)
            if not version:
                raise Exception("有効なWorkflow版が見つかりません。")
        except Exception as error:
            # 起動前の事前確認で失敗＝未起動が確定している。再試行可能なことを伝える。
            LOGGER.warning("notification workflow preflight failed: %s", error)
            message = "通知Workflowを開始できませんでした（公開版を確認してください）。"
            record("FAILED", "", message)
            return {"started": False, "instance_id": "", "error": message}
        try:
            started = codeengine.send_request("post", "api/workflow/v1/instances/message", {
                "messageName": WORKFLOW_START_MESSAGE_NAME,
                "modelId": model_id,
                "version": version,
                "data": payload,
            }) or {}
            instance_id = str(started.get("id") or "")
            if not instance_id:
                raise Exception("WorkflowインスタンスIDが返りませんでした。")
        except Exception as error:
            # タイムアウト等は未実行とは限らない。自動再送はせず、履歴確認を促す（重複送信の防止）。
            LOGGER.warning("notification workflow start uncertain: %s", error)
            message = "通知Workflowの開始結果を確認できませんでした。通知履歴を確認してください。"
            record("FAILED", "", message)
            return {"started": False, "instance_id": "", "error": message}
        record("STARTED", instance_id)
        return {"started": True, "instance_id": instance_id, "error": ""}

    def _register(request: dict, user: dict) -> dict:
        """入出庫1件を検証して記録し、見込み在庫としきい値イベントまで確定する。

        重複(request_id)判定→種別・品目・ロケーション・数量の検証→取引記録→残高の
        見込み更新→アラート状態遷移→（不足/回復の遷移時のみ）監査証跡（ALERT_HISTORY）の
        作成と通知Workflowの起動、までを一連の副作用として実行する。Workflow の起動は
        フロントに委ねず、ここから ``start_notification_workflow`` で最新の有効版を
        実行時に解決して開始する（カード再埋め込み不要・起動結果は同じ監査行へ確定）。

        Args:
            request: Pro Code から渡る登録要求（request_id・種別・品目・数量など）。
            user: 実行コンテキストから構築した利用者（id・name・isAdmin・email）。

        Returns:
            ok・重複可否・確定した取引・見込み残高・通知判断を含む結果 dict。

        Raises:
            Exception: request_id・種別・品目・ロケーション・数量が不正、権限不足、
                または在庫を超える出庫のとき。公開エラーボディ（code/message を持つ dict）を
                第1引数に持つ想定内の業務エラー。
        """
        request_id = str(request.get("request_id") or "").strip()
        if not request_id or len(request_id) > 100:
            raise Exception({"code": "INVALID_REQUEST_ID", "message": "request_idを100文字以内で指定してください。", "details": {}})
        duplicate = _records("find", "TRANSACTION", field="request_id", value=request_id)
        if duplicate:
            # 冪等リプレイでも内部フィールド(_document_id)は公開しない。LIST_MASTERS と同じ
            # 「AppDB の内部IDを FE 契約に漏らさない」方針に揃える。balance_after は元行から読む。
            transaction = {name: value for name, value in duplicate.items() if not name.startswith("_")}
            # BK-002: AppDB 書込みは非アトミックなので、一度目が TRANSACTION 作成後・BALANCE 投影前に
            # 落ちると投影が古いまま残り、同一 request_id のリプレイがここで早期 return して成功を装い、
            # RECALCULATE が必要なことを誰にも知らせない。そこでリプレイ時に当該キーの BALANCE を
            # 取引正本から再導出して idempotent に再 upsert し、半適用を自己修復する。duplicate 行の
            # balance_after を直接書き戻さないのは重要: 並行オペレータが同キーに後続取引を入れていた
            # 場合、古い時点残高へ巻き戻してしまう。RECALCULATE と同じ順序非依存の総和
            # (signed_quantity の合計・6桁丸め+0.0・archived 除外) で現残高を作り直す。健全なリプレイ
            # では同値を再投影するだけ(=live 残高は不変)。返却 balance は従来どおり時点の balance_after。
            loc = str(duplicate.get("location_code") or "")
            itm = str(duplicate.get("item_code") or "")
            if loc and itm:
                heal_key = f"{loc}|{itm}"
                now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                ledger = [row for row in _records("query", "TRANSACTION", field="item_code", value=itm)
                          if str(row.get("location_code") or "") == loc and not _is_true(row.get("archived"))]
                healed = round(sum(float(row.get("signed_quantity") or 0) for row in ledger), 6) + 0.0
                last_at = max((str(row.get("occurred_at") or row.get("created_at") or "") for row in ledger), default="")
                rule = _records("find", "RULE", field="rule_key", value=heal_key)
                rule_active = bool(rule) and _is_true(rule.get("active", "true"))
                minimum = float((rule or {}).get("minimum_quantity") or 0) if rule_active else 0.0
                is_shortage = minimum > 0 and healed < minimum
                _records("upsert", "BALANCE", record_key=f"BALANCE|{heal_key}", content={
                    "balance_key": heal_key, "item_code": itm, "item_name": duplicate.get("item_name") or itm,
                    "location_code": loc, "location_name": duplicate.get("location_name") or loc,
                    "quantity": healed, "minimum_quantity": minimum,
                    "shortage_quantity": round(max(minimum - healed, 0), 6) + 0.0, "is_shortage": is_shortage,
                    "last_transaction_at": last_at, "updated_at": now,
                })
                # 不足解消済みなら据え置きの SHORTAGE を NORMAL へ掃除する(RECALCULATE と同じ一方向のみ。
                # 逆向きの強制はしない＝未通知の不足で正当な SHORTAGE 通知を握り潰さないため)。
                if not is_shortage:
                    stale_alert = _records("find", "ALERT_STATE", field="balance_key", value=heal_key)
                    if stale_alert and str(stale_alert.get("status")) == "SHORTAGE":
                        _records("upsert", "ALERT_STATE", record_key=f"ALERT_STATE|{heal_key}", content={"status": "NORMAL", "updated_at": now})
            return {"ok": True, "duplicate": True, "transaction": transaction, "balance": {"quantity": duplicate.get("balance_after")}, "notification": {"triggered": False}}

        transaction_type = str(request.get("transaction_type") or "").upper()
        if transaction_type not in {"IN", "OUT"}:
            raise Exception({"code": "INVALID_TRANSACTION_TYPE", "message": "処理種別はIN、OUTのいずれかです。", "details": {}})

        item_code = str(request.get("item_code") or "").strip().upper()
        location_code = str(request.get("location_code") or "").strip().upper()
        item = _records("find", "ITEM", field="item_code", value=item_code)
        location = _records("find", "LOCATION", field="location_code", value=location_code)
        if not item or not (item.get("active") is True or str(item.get("active", "true")).lower() in {"true", "1"}):
            raise Exception({"code": "INVALID_ITEM", "message": "有効な品目が見つかりません。", "details": {}})
        if not location or not (location.get("active") is True or str(location.get("active", "true")).lower() in {"true", "1"}):
            raise Exception({"code": "INVALID_LOCATION", "message": "有効なロケーションが見つかりません。", "details": {}})

        try:
            quantity = float(request.get("quantity"))
        except (TypeError, ValueError) as error:
            raise Exception({"code": "INVALID_QUANTITY", "message": "数量は数値で指定してください。", "details": {}}) from error
        # 入出庫はいずれも正の数量のみ受け付ける（0や負値は常に不正）。
        if not math.isfinite(quantity) or quantity <= 0 or quantity > MAX_QUANTITY:
            raise Exception({"code": "INVALID_QUANTITY", "message": "数量は0より大きく、1,000,000以下で指定してください。", "details": {}})

        signed = -abs(quantity) if transaction_type == "OUT" else abs(quantity)
        balance_key = f"{location_code}|{item_code}"
        balance = _records("find", "BALANCE", field="balance_key", value=balance_key)
        before = float((balance or {}).get("quantity") or 0)
        # 0.01 粒度の小数を足し引きすると浮動小数の残差(例: 0.3-0.1-0.2 が -2.8e-17)が乗る。
        # そのまま after<0 の在庫ガードや after<minimum の不足判定に渡すと、実質ゼロの在庫で
        # 正当な出庫が NEGATIVE_INVENTORY と誤判定されたり、基準ちょうどで幽霊不足が出る。
        # 6桁(業務の最小粒度0.01より十分細かい)で丸めて残差だけを消し、+0.0 で丸め結果の
        # -0.0 を 0.0 に正規化する(FE の数値表示で "-0" と出さないため)。
        after = round(before + signed, 6) + 0.0
        if after < 0:
            raise Exception({"code": "NEGATIVE_INVENTORY", "message": "在庫数を超える出庫は登録できません。", "details": {"available": before, "requested": abs(signed)}})

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        occurred_at = str(request.get("occurred_at") or now)
        transaction_id = f"TRX-{uuid.uuid4()}"
        transaction = {
            "transaction_id": transaction_id, "request_id": request_id, "transaction_type": transaction_type,
            "item_code": item_code, "item_name": item.get("item_name") or item_code,
            "location_code": location_code, "location_name": location.get("location_name") or location_code,
            "quantity": abs(quantity), "signed_quantity": signed, "balance_before": before, "balance_after": after,
            "reason": str(request.get("reason") or "")[:200], "operator_user_id": user["id"],
            "operator_name": user["name"], "source": str(request.get("source") or "DOMO")[:40],
            "occurred_at": occurred_at, "created_at": now,
        }
        _records("create", "TRANSACTION", record_key=f"TRANSACTION|{transaction_id}", content=transaction)

        rule = _records("find", "RULE", field="rule_key", value=balance_key)
        rule_active = bool(rule) and (rule.get("active") is True or str(rule.get("active", "true")).lower() in {"true", "1"})
        minimum = float((rule or {}).get("minimum_quantity") or 0) if rule_active else 0.0
        shortage = minimum > 0 and after < minimum
        # 不足数も after と同じく6桁丸め+0.0で浮動小数残差を消す。丸めないと minimum-after が
        # 3.4000000000000004 のような残差付きで BALANCE/ALERT_HISTORY/通知本文/workflow へ流れ、
        # 監査記録と通知文面に不自然な桁が残る。ここで一度だけ正規化して全出力で共有し、
        # RECALCULATE の再投影(下記 quantity 版)と同一値になる(register≡recalc 不変条件)ようにする。
        shortage_quantity = round(max(minimum - after, 0), 6) + 0.0
        # last_transaction_at は「最新取引の時刻」を意味する。過去日を遡って登録しても既存の最新時刻を
        # 後退させないよう、既存値との大きい方を採り、RECALCULATE の max 集約(occurred_at 昇順の末尾)と揃える。
        existing_last = str((balance or {}).get("last_transaction_at") or "")
        last_transaction_at = occurred_at if occurred_at >= existing_last else existing_last
        projection = {
            "balance_key": balance_key, "item_code": item_code, "item_name": transaction["item_name"],
            "location_code": location_code, "location_name": transaction["location_name"],
            "quantity": after, "minimum_quantity": minimum, "shortage_quantity": shortage_quantity,
            "is_shortage": shortage, "last_transaction_at": last_transaction_at, "updated_at": now,
        }
        projection_status, _ = _records("upsert", "BALANCE", record_key=f"BALANCE|{balance_key}", content=projection)

        previous = _records("find", "ALERT_STATE", field="balance_key", value=balance_key)
        previous_status = str((previous or {}).get("status") or "NORMAL")
        event_type = "SHORTAGE" if shortage and previous_status != "SHORTAGE" else ("RECOVERY" if not shortage and previous_status == "SHORTAGE" else "")
        _records("upsert", "ALERT_STATE", record_key=f"ALERT_STATE|{balance_key}", content={
            "balance_key": balance_key, "status": "SHORTAGE" if shortage else "NORMAL",
            "last_alerted_quantity": after if event_type == "SHORTAGE" else (previous or {}).get("last_alerted_quantity"),
            "last_alerted_at": now if event_type == "SHORTAGE" else (previous or {}).get("last_alerted_at"),
            "last_recovered_at": now if event_type == "RECOVERY" else (previous or {}).get("last_recovered_at"),
            "updated_at": now,
        })

        notification = {"triggered": False, "workflow_ready": False, "workflow_started": False, "reason": "NO_THRESHOLD_TRANSITION"}
        if event_type:
            alert_id = f"ALERT-{uuid.uuid4()}"
            subject = f"在庫{'回復' if event_type == 'RECOVERY' else '不足'}: {transaction['item_name']} / {transaction['location_name']}"
            body = f"現在庫{num(after)}、基準在庫{num(minimum)}、不足数{num(shortage_quantity)}です。"
            notification_enabled = str((rule or {}).get("notification_enabled", "true")).lower() in {"true", "1"}
            recipient_email = _resolve_recipient_email(request, user)
            workflow_ready = notification_enabled and "@" in recipient_email
            notification_status = "PENDING" if workflow_ready else "SKIPPED"
            notification_reason = "THRESHOLD_TRANSITION" if workflow_ready else ("NOTIFICATION_DISABLED" if not notification_enabled else "RECIPIENT_EMAIL_MISSING")
            _records("create", "ALERT_HISTORY", record_key=f"ALERT_HISTORY|{alert_id}", content={
                "alert_id": alert_id, "event_type": event_type, "balance_key": balance_key,
                "item_code": item_code, "item_name": transaction["item_name"], "location_code": location_code,
                "location_name": transaction["location_name"], "current_quantity": after,
                "minimum_quantity": minimum, "shortage_quantity": shortage_quantity,
                "operator_user_id": user["id"], "operator_name": user["name"],
                "notification_status": notification_status, "notification_subject": subject,
                "notification_body": body, "error_message": "" if workflow_ready else notification_reason,
                "created_at": now, "updated_at": now,
            })
            notification = {
                "triggered": workflow_ready,
                "workflow_ready": workflow_ready,
                "workflow_started": False,
                "alert_id": alert_id,
                "reason": notification_reason,
            }
            if workflow_ready:
                # 複数の不足を1通に集約するため、通知対象の全不足を「確定データ」として渡す。
                # headline は今回しきい値を跨いだ品目、shortage_lines は直前に upsert 済みの
                # BALANCE に基づく現時点の通知対象一覧。AI に件数を推測させない。起動は CE が
                # 行い（最新の有効版を実行時に解決）、結果を同じ ALERT_HISTORY 行へ確定する。
                notifiable, _ = current_shortages()
                headline_row = {
                    "item_code": item_code, "item_name": transaction["item_name"],
                    "location_code": location_code, "location_name": transaction["location_name"],
                    "current_quantity": after, "minimum_quantity": minimum, "shortage_quantity": shortage_quantity,
                }
                outcome = start_notification_workflow(alert_id, {
                    "event_type": event_type,
                    "occurred_at": now,
                    "recipient_email": recipient_email,
                    "headline": describe_shortage(headline_row, recovered=(event_type == "RECOVERY")),
                    "shortage_lines": shortage_lines(notifiable),
                })
                notification.update({
                    "workflow_started": outcome["started"],
                    "workflow_instance_id": outcome["instance_id"],
                    "workflow_error": outcome["error"],
                })
        return {"ok": True, "duplicate": False, "transaction": transaction, "balance": projection, "projection_status": projection_status, "notification": notification}


    def _notify_now(request: dict, user: dict) -> dict:
        """現時点で最も深刻な不足に対し、手動で不足通知を起動する。

        ``_register`` が副作用で作る通知ブロックと同じ形を返すため、Pro Code は自動
        （取引直後）経路と、この手動ボタン経路の両方で同じ起動結果（workflow_started／
        workflow_error）を表示できる。Workflow の起動自体はここ（CE）で行い、最新の有効版を
        実行時に解決して ``api/workflow/v1/instances/message`` で開始し、結果を監査証跡
        （ALERT_HISTORY）へ STARTED／FAILED として確定する。

        Args:
            request: Pro Code から渡る要求（宛先解決用の ``operator_email`` を含み得る）。
            user: 実行コンテキストから構築した利用者。

        Returns:
            ok と通知判断（triggered・reason・shortage_count・workflow_started 等）を含む dict。
            不足なし／宛先未解決のときは triggered=False で理由を返す。
        """
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # 通知対象の不足一覧と全不足件数を共有ロジックで取得（自動経路 _register と定義を揃える）。
        # notifiable が空でも total>0 なら「不足はあるが通知先が全て無効」を区別できる。
        notifiable, total = current_shortages()
        if total == 0:
            return {"ok": True, "notification": {"triggered": False, "workflow_ready": False, "workflow_started": False, "reason": "NO_SHORTAGE", "shortage_count": 0}}
        if not notifiable:
            return {"ok": True, "notification": {"triggered": False, "workflow_ready": False, "workflow_started": False, "reason": "NOTIFICATION_DISABLED", "shortage_count": total}}

        recipient_email = _resolve_recipient_email(request, user)
        if "@" not in recipient_email:
            return {"ok": True, "notification": {"triggered": False, "workflow_ready": False, "workflow_started": False, "reason": "RECIPIENT_EMAIL_MISSING", "shortage_count": total}}

        worst = notifiable[0]
        current_quantity = float(worst.get("quantity") or 0)
        minimum_quantity = float(worst.get("minimum_quantity") or 0)
        # 監査(ALERT_HISTORY)の不足数も6桁丸め+0.0で正規化し、_register と桁を揃える
        # (旧バージョンで残差付きに保存された値を読んでも、通知面では自然な桁で見せる)。
        shortage_quantity = round(float(worst.get("shortage_quantity") or max(minimum_quantity - current_quantity, 0)), 6) + 0.0
        item_code = str(worst.get("item_code") or "")
        location_code = str(worst.get("location_code") or "")
        item_name = str(worst.get("item_name") or item_code)
        location_name = str(worst.get("location_name") or location_code)
        others = len(notifiable) - 1  # 監査本文の「ほかN件」は実際に集約する通知対象の残数に合わせる。
        alert_id = f"ALERT-{uuid.uuid4()}"
        subject = f"在庫不足（手動通知）: {item_name} / {location_name}"
        body = f"現在庫{num(current_quantity)}、基準在庫{num(minimum_quantity)}、不足数{num(shortage_quantity)}です。" + (f"ほか{others}件の不足があります。" if others > 0 else "")
        _records("create", "ALERT_HISTORY", record_key=f"ALERT_HISTORY|{alert_id}", content={
            "alert_id": alert_id, "event_type": "MANUAL", "balance_key": str(worst.get("balance_key") or ""),
            "item_code": item_code, "item_name": item_name, "location_code": location_code, "location_name": location_name,
            "current_quantity": current_quantity, "minimum_quantity": minimum_quantity, "shortage_quantity": shortage_quantity,
            "operator_user_id": user["id"], "operator_name": user["name"],
            "notification_status": "PENDING", "notification_subject": subject, "notification_body": body,
            "error_message": "", "created_at": now, "updated_at": now,
        })
        outcome = start_notification_workflow(alert_id, {
            "event_type": "MANUAL",
            "occurred_at": now,
            "recipient_email": recipient_email,
            "headline": describe_shortage(worst),
            "shortage_lines": shortage_lines(notifiable),
        })
        return {"ok": True, "notification": {
            "triggered": True, "workflow_ready": True, "alert_id": alert_id, "reason": "MANUAL_TRIGGER", "shortage_count": total,
            "workflow_started": outcome["started"],
            "workflow_instance_id": outcome["instance_id"],
            "workflow_error": outcome["error"],
        }}


    def _admin(action: str, request: dict, user: dict) -> dict:
        """管理者専用の入口（残高再計算・デモ初期データ投入・マスタ保守）を処理する。

        RECALCULATE は追記専用の取引台帳を唯一の真実として現在庫（BALANCE）を
        総ざらいで再構築する（欠損・不整合の是正用）。マスタ保守（LIST_MASTERS /
        UPSERT_ITEM / UPSERT_LOCATION / UPSERT_RULE / DELETE_ITEM / DELETE_LOCATION /
        DELETE_RULE）は1つの AppDB コレクションに対する ITEM / LOCATION / RULE の CRUD を
        リファレンスとして実演する（冪等な upsert と、依存を連鎖削除する不可逆な物理削除）。
        SEED はマスタと取引のデモ一式を冪等に投入し、初見の環境でもアプリの全画面を
        体験できる状態を作る。いずれも管理者専用で、同じ権限判定を入口で一度だけ行う。

        Args:
            action: RECALCULATE / SEED / LIST_MASTERS / UPSERT_* / DELETE_* のいずれか。
            request: 操作固有の追加パラメータ（SEED の規模指定、マスタの各フィールドなど）。
            user: 実行コンテキストから構築した利用者（管理者判定に使う）。

        Returns:
            操作結果（再計算・投入件数の内訳、LIST は items/locations/rules、
            UPSERT は status/record、DELETE は削除件数の内訳など）を含む dict。

        Raises:
            Exception: 管理者以外、入力（コード・名称・数量）不正、対象マスタ不在、
                または未対応の action のとき。公開エラーボディ（code/message を持つ dict）を
                第1引数に持つ想定内の業務エラー。
        """
        if not user.get("isAdmin"):
            raise Exception({"code": "FORBIDDEN", "message": "この操作には管理者権限が必要です。", "details": {}})
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if action == "RECALCULATE":
            # マスタを件数分だけ個別 find すると AppDB 呼び出しが件数に比例して膨らむため、
            # item / location / rule を一括クエリして辞書化し、集計ループは辞書引きで回す。
            # documents/query は1応答を最大 1万件で打ち切るが、_records の query は limit/offset で
            # 全ページを辿るので、生成デモや長期運用で台帳が1万件を超えても全件を集計できる。
            items_by_code = {str(row.get("item_code") or ""): row for row in _records("query", "ITEM")}
            locations_by_code = {str(row.get("location_code") or ""): row for row in _records("query", "LOCATION")}
            rules_by_key = {str(row.get("rule_key") or ""): row for row in _records("query", "RULE")}
            # 物理削除済みマスタの取引は台帳に残るが archived 印が付く。archived を集計から除くことで、
            # 同じ人手コードでマスタを作り直しても削除前の在庫が蘇らない（_register が削除後に
            # BALANCE を失い before=0 から始めるのと同じ投影に揃える）。マスタ存在ガード（下）だけでは
            # 再作成でマスタが存在扱いに戻り、くぐり抜けられてしまう。
            transactions = sorted(
                (row for row in _records("query", "TRANSACTION") if not _is_true(row.get("archived"))),
                key=lambda row: str(row.get("occurred_at") or row.get("created_at") or ""),
            )
            aggregates: dict = {}
            for row in transactions:
                key = f"{str(row.get('location_code') or '')}|{str(row.get('item_code') or '')}"
                aggregate = aggregates.setdefault(key, {"quantity": 0.0, "last_transaction_at": ""})
                aggregate["quantity"] += float(row.get("signed_quantity") or 0)
                aggregate["last_transaction_at"] = str(row.get("occurred_at") or row.get("created_at") or "")
            rebuilt = 0
            skipped_deleted = 0
            for key, aggregate in aggregates.items():
                location_code, item_code = key.split("|", 1)
                item = items_by_code.get(item_code)
                location = locations_by_code.get(location_code)
                if not item or not location:
                    # archived を経ずにマスタだけ消えた異常系（手動注入など）の防御。残高は再生成
                    # せず（マスタ不在なので item.get で参照する名称も無い）スキップする。取り残された
                    # 派生レコードの掃除は後段の stale パージがまとめて担う。
                    skipped_deleted += 1
                    continue
                rule = rules_by_key.get(key) or {}
                # 停止中(active=false)のルールは _register(line 258-259)と同じく minimum=0 と
                # して扱い、しきい値を沈黙させる。こうしないと再計算だけが停止中ルールの基準を
                # 拾い、取引正本から作り直したはずの残高が _register の投影と食い違う（幽霊の不足）。
                rule_active = bool(rule) and _is_true(rule.get("active", "true"))
                minimum = float(rule.get("minimum_quantity") or 0) if rule_active else 0.0
                # _register(line 239)と同じく累計を6桁で丸め、多数の小数取引を足し込んだ際の
                # 浮動小数残差が BALANCE.quantity に負値や幽霊不足として乗らないようにする。
                # +0.0 は -0.0 の正規化（再計算後も FE 表示を _register と一致させる）。
                quantity = round(aggregate["quantity"], 6) + 0.0
                is_shortage = minimum > 0 and quantity < minimum
                _records("upsert", "BALANCE", record_key=f"BALANCE|{key}", content={
                    "balance_key": key, "item_code": item_code, "item_name": item.get("item_name") or item_code,
                    "location_code": location_code, "location_name": location.get("location_name") or location_code,
                    "quantity": quantity, "minimum_quantity": minimum, "shortage_quantity": round(max(minimum - quantity, 0), 6) + 0.0,
                    "is_shortage": is_shortage,
                    "last_transaction_at": aggregate["last_transaction_at"], "updated_at": now,
                })
                # 不足が解消したのにアラート状態が SHORTAGE のまま据え置かれると、次の回復方向の取引が
                # previous_status=SHORTAGE を読んで「実体のない回復(RECOVERY)」を誤発火する。DELETE_RULE と
                # 同じく、不足解消時にだけ既存の SHORTAGE を NORMAL へ掃除する。逆向き(NORMAL→SHORTAGE の
                # 強制)はしない——不足未通知の残高で、次の取引が正当に発火すべき SHORTAGE 通知を握り潰さないため。
                if not is_shortage:
                    stale_alert = _records("find", "ALERT_STATE", field="balance_key", value=key)
                    if stale_alert and str(stale_alert.get("status")) == "SHORTAGE":
                        _records("upsert", "ALERT_STATE", record_key=f"ALERT_STATE|{key}", content={"status": "NORMAL", "updated_at": now})
                rebuilt += 1
            # マスタ不在の派生レコード（BALANCE / ALERT_STATE）を物理削除して整合を回復する。
            # DELETE_* は同期的に派生を消すが、archived 取引で集計に現れないキーや、何らかの理由で
            # 取り残された派生もここで掃除し「live マスタの無い派生は残さない」不変条件を保証する。
            # live マスタのキーは上の再構築で最新化済みなので触れない。
            stale_purged = 0
            for target_type in ("BALANCE", "ALERT_STATE"):
                for row in _records("query", target_type):
                    key = str(row.get("balance_key") or "")
                    location_code, _, item_code = key.partition("|")
                    master_missing = item_code not in items_by_code or location_code not in locations_by_code
                    if master_missing and row.get("_document_id"):
                        _records("delete", document_id=row["_document_id"])
                        stale_purged += 1
            return {"ok": True, "message": "取引正本から残高を再計算しました。", "transaction_count": len(transactions),
                    "balance_count": rebuilt, "skipped_deleted_master_count": skipped_deleted, "stale_purged_count": stale_purged}

        # ── マスタ保守（ITEM / LOCATION / RULE の CRUD、管理者専用）──
        # 1つの AppDB コレクションに対する CRUD の全面をリファレンスとして見せる: record_key 上での
        # 冪等な create/update（upsert）と、ドキュメント自体を消す不可逆な物理削除である。物理削除は
        # 依存マスタ・派生状態（ルール・現在庫・アラート状態）まで連鎖的に消して孤児を残さない一方、
        # 追記専用の台帳（取引・通知履歴）は監査証跡として意図的に保持する。削除せず一時的に無効化
        # したいときは active=false で upsert する（更新であり可逆）。RECALCULATE は上で return 済み。
        # 以下のマスタ用ヘルパー（code/name/flag）は LIST/UPSERT/DELETE でのみ使い、SEED では使わない。
        def code(field_name: str, raw: Any, label: str) -> str:
            value = str(raw or "").strip().upper()
            if not MASTER_CODE_PATTERN.match(value):
                raise Exception({"code": "INVALID_MASTER_CODE", "message": f"{label}は英数字・ハイフン・アンダースコアの40文字以内で指定してください。", "details": {"field": field_name}})
            return value

        def name(raw: Any, label: str) -> str:
            value = str(raw or "").strip()
            if not value or len(value) > 120:
                raise Exception({"code": "INVALID_MASTER_NAME", "message": f"{label}は1〜120文字で指定してください。", "details": {}})
            return value

        def flag(raw: Any, default: bool = True) -> bool:
            return default if raw is None else _is_true(raw)

        if action == "LIST_MASTERS":
            clean = lambda rows: [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows]
            return {"ok": True, "items": clean(_records("query", "ITEM")), "locations": clean(_records("query", "LOCATION")), "rules": clean(_records("query", "RULE"))}

        if action == "UPSERT_ITEM":
            item_code = code("item_code", request.get("item_code"), "品目コード")
            content = {
                "item_code": item_code, "item_name": name(request.get("item_name"), "品目名"),
                "category": str(request.get("category") or "").strip()[:80],
                "unit": str(request.get("unit") or "").strip()[:40],
                # 先に strip してから既定へフォールバックする。空白のみの qr_value は
                # 真値扱いで既定を飛ばしてしまい、空の qr_value が保存される罠を防ぐ。
                "qr_value": str(request.get("qr_value") or "").strip()[:120] or f"ITEM:{item_code}",
                "active": flag(request.get("active")), "updated_at": now,
            }
            status, record = _records("upsert", "ITEM", record_key=f"ITEM|{item_code}", content=content)
            return {"ok": True, "status": status, "record_type": "ITEM", "record": record}

        if action == "UPSERT_LOCATION":
            location_code = code("location_code", request.get("location_code"), "ロケーションコード")
            content = {
                "location_code": location_code, "location_name": name(request.get("location_name"), "ロケーション名"),
                "zone": str(request.get("zone") or "").strip()[:80],
                # ITEM と同じく、空白のみ入力で既定 LOC:<code> を飛ばさないよう先に strip する。
                "qr_value": str(request.get("qr_value") or "").strip()[:120] or f"LOC:{location_code}",
                "active": flag(request.get("active")), "updated_at": now,
            }
            status, record = _records("upsert", "LOCATION", record_key=f"LOCATION|{location_code}", content=content)
            return {"ok": True, "status": status, "record_type": "LOCATION", "record": record}

        if action == "UPSERT_RULE":
            location_code = code("location_code", request.get("location_code"), "ロケーションコード")
            item_code = code("item_code", request.get("item_code"), "品目コード")
            if not _records("find", "ITEM", field="item_code", value=item_code):
                raise Exception({"code": "INVALID_ITEM", "message": "有効な品目が見つかりません。", "details": {}})
            if not _records("find", "LOCATION", field="location_code", value=location_code):
                raise Exception({"code": "INVALID_LOCATION", "message": "有効なロケーションが見つかりません。", "details": {}})
            try:
                minimum = float(request.get("minimum_quantity"))
            except (TypeError, ValueError) as error:
                raise Exception({"code": "INVALID_MINIMUM_QUANTITY", "message": "基準在庫は数値で指定してください。", "details": {}}) from error
            if not math.isfinite(minimum) or minimum < 0 or minimum > MAX_QUANTITY:
                raise Exception({"code": "INVALID_MINIMUM_QUANTITY", "message": "基準在庫は0以上、1,000,000以下で指定してください。", "details": {}})
            rule_key = f"{location_code}|{item_code}"
            content = {
                "rule_key": rule_key, "location_code": location_code, "item_code": item_code,
                "minimum_quantity": minimum, "notification_enabled": flag(request.get("notification_enabled")),
                "active": flag(request.get("active")), "updated_at": now,
            }
            status, record = _records("upsert", "RULE", record_key=f"RULE|{rule_key}", content=content)
            # ルールの新設・編集・停止は、対になる現在庫(BALANCE)の基準在庫・不足数・不足フラグを即時に
            # 投影し直さないと、次の取引か手動再計算まで NOTIFY_NOW とダッシュボードが古い基準で判断する
            # (DELETE_RULE と同じ「据え置き幽霊」を UPSERT でも作らない)。現在庫そのものは取引台帳由来
            # なので保持する。BALANCE 未生成(取引ゼロ)なら投影対象が無いので何もしない。
            balance = _records("find", "BALANCE", field="balance_key", value=rule_key)
            if balance:
                effective_minimum = minimum if content["active"] else 0.0
                quantity = float(balance.get("quantity") or 0)
                is_shortage = effective_minimum > 0 and quantity < effective_minimum
                _records("upsert", "BALANCE", record_key=f"BALANCE|{rule_key}", content={
                    "minimum_quantity": effective_minimum, "shortage_quantity": round(max(effective_minimum - quantity, 0), 6) + 0.0,
                    "is_shortage": is_shortage, "updated_at": now,
                })
                # 停止・基準緩和などで不足が解消したのにアラート状態が SHORTAGE のまま残ると、次の取引が
                # 誤って RECOVERY を発火する。DELETE_RULE と同じく、不足解消時にだけ既存の SHORTAGE を掃除する。
                # 不足が新たに生じた場合(NORMAL→SHORTAGE)は強制せず、次の取引の通常遷移で通知させる
                # (設定変更では通知を発火しない保守的な方針)。upsert は MERGE なので last_alerted_* は保持。
                if not is_shortage:
                    stale_alert = _records("find", "ALERT_STATE", field="balance_key", value=rule_key)
                    if stale_alert and str(stale_alert.get("status")) == "SHORTAGE":
                        _records("upsert", "ALERT_STATE", record_key=f"ALERT_STATE|{rule_key}", content={"status": "NORMAL", "updated_at": now})
            return {"ok": True, "status": status, "record_type": "RULE", "record": record}

        if action in {"DELETE_ITEM", "DELETE_LOCATION", "DELETE_RULE"}:
            # AppDB の物理削除(D)をリファレンスとして実演する。マスタ本体・依存ルール・
            # 派生状態(残高/アラート状態)は完全に消すが、追記専用の台帳(取引履歴・
            # 通知履歴)は監査証跡として残す。物理削除は不可逆で復元導線は持たない。
            record_type = action.split("_", 1)[1]

            def delete_alert_state(balance_key: str) -> int:
                """balance_key で一意な派生アラート状態を物理削除する(無ければ0)。"""
                row = _records("find", "ALERT_STATE", field="balance_key", value=balance_key)
                document_id = (row or {}).get("_document_id")
                if not document_id:
                    return 0
                _records("delete", document_id=document_id)
                return 1

            def delete_matching(target_type: str, field_name: str, field_value: Any) -> int:
                """指定フィールドに一致する派生レコードを物理削除し件数を返す。"""
                removed = 0
                for row in _records("query", target_type, field=field_name, value=field_value):
                    document_id = row.get("_document_id")
                    if document_id:
                        _records("delete", document_id=document_id)
                        removed += 1
                return removed

            def archive_transactions(field_name: str, field_value: Any) -> int:
                """物理削除するマスタの取引台帳に archived 印を付け、件数を返す。

                取引・通知履歴は監査証跡として物理削除せず残すが、同じ人手コード
                （例: 一度消した ITEM-001）でマスタを作り直したとき、削除前の取引から
                残高が「復活」してはならない。RECALCULATE は archived 取引を集計から
                除外するため、ここで印を付けておくと、再作成後も _register が
                before=0 から始めるのと同じ投影に揃う（マスタ存在ガードだけでは
                再作成でくぐり抜けられるため、archived 印が復活を防ぐ唯一の砦）。
                行そのものと業務項目は保持し、ライフサイクル印だけを追記する。
                """
                archived = 0
                for row in _records("query", "TRANSACTION", field=field_name, value=field_value):
                    if _is_true(row.get("archived")):
                        continue  # 既に archived（再作成→再削除など）は再書込みしない。
                    record_key = row.get("record_key") or f"TRANSACTION|{row.get('transaction_id') or ''}"
                    _records("upsert", "TRANSACTION", record_key=record_key, content={"archived": True, "archived_at": now})
                    archived += 1
                return archived

            if record_type == "RULE":
                location_code = code("location_code", request.get("location_code"), "ロケーションコード")
                item_code = code("item_code", request.get("item_code"), "品目コード")
                record_key = f"RULE|{location_code}|{item_code}"
                master = _records("find", "RULE", field="record_key", value=record_key)
                if not master:
                    raise Exception({"code": "MASTER_NOT_FOUND", "message": "対象のマスタが見つかりません。", "details": {}})
                _records("delete", document_id=master.get("_document_id"))
                # しきい値が消えるため派生のアラート状態も削除する。現在庫(残高)そのものは
                # ルールに依存しないので保持するが、BALANCE が併せ持つ「ルール由来の派生値」
                # (基準在庫・不足数・不足フラグ)を据え置くと、実体のないルールで NOTIFY_NOW と
                # ダッシュボードが不足を報告し続ける。残高は残したままこの3項目だけを 0/false へ
                # 掃除して、ルール消滅＝不足なしという再計算(_admin)側の意味論と即時に一致させる。
                balance_key = f"{location_code}|{item_code}"
                balance = _records("find", "BALANCE", field="balance_key", value=balance_key)
                if balance:
                    _records("upsert", "BALANCE", record_key=f"BALANCE|{balance_key}", content={
                        "minimum_quantity": 0, "shortage_quantity": 0, "is_shortage": False, "updated_at": now,
                    })
                removed = {"RULE": 1, "ALERT_STATE": delete_alert_state(balance_key)}
                return {"ok": True, "status": "deleted", "record_type": "RULE", "deleted": removed}

            if record_type == "ITEM":
                master_field = "item_code"
                master_value = code("item_code", request.get("item_code"), "品目コード")
                record_key = f"ITEM|{master_value}"
            else:
                master_field = "location_code"
                master_value = code("location_code", request.get("location_code"), "ロケーションコード")
                record_key = f"LOCATION|{master_value}"
            master = _records("find", record_type, field="record_key", value=record_key)
            if not master:
                raise Exception({"code": "MASTER_NOT_FOUND", "message": "対象のマスタが見つかりません。", "details": {}})

            removed = {record_type: 0, "RULE": 0, "BALANCE": 0, "ALERT_STATE": 0}
            # 派生残高を辿って balance_key を取得し、残高とアラート状態を対で削除する。
            for balance in _records("query", "BALANCE", field=master_field, value=master_value):
                document_id = balance.get("_document_id")
                if document_id:
                    _records("delete", document_id=document_id)
                    removed["BALANCE"] += 1
                removed["ALERT_STATE"] += delete_alert_state(str(balance.get("balance_key") or ""))
            removed["RULE"] = delete_matching("RULE", master_field, master_value)
            # 追記専用の台帳は残すが、削除したマスタの取引には archived 印を付ける。これにより
            # 同コードでマスタを作り直しても再計算が削除前の在庫を蘇らせない（DELETE_RULE は
            # 残高を残す＝取引の意味も生きているので archived にしない。ITEM/LOCATION の物理削除だけ）。
            removed["TRANSACTION_ARCHIVED"] = archive_transactions(master_field, master_value)
            _records("delete", document_id=master.get("_document_id"))
            removed[record_type] = 1
            return {"ok": True, "status": "deleted", "record_type": record_type, "deleted": removed}

        # ここへ落ちてくる action は SEED のみ。RECALCULATE とマスタ保守（LIST/UPSERT/DELETE）は
        # 上で return 済みで、この関数の呼び出し元はディスパッチャに限られる。ディスパッチャは
        # operation=SEED か、MASTER_ACTIONS で許可リスト検証済みのマスタ action だけを渡すため、
        # 未対応 action（SEED/RECALCULATE を MANAGE_MASTER 経由で送る等）は境界で弾かれ、ここには
        # 到達しない。以降は初見環境向けにデモ一式を冪等投入する。

        # ── 名前付きデモ層（人が読んで意味の分かる少数の実例）────────────────────
        # 代表的な業務シナリオ（受入・払出・不足→復旧のアラート遷移）を
        # 分かりやすい品名で見せる中核データ。アラート履歴を作るため、この層の取引だけは
        # 通常の登録経路 _register を通す（副作用として ALERT_STATE / ALERT_HISTORY を生成）。
        demo_items = [
            ("ITEM-001", "安全手袋", "安全用品", "双"), ("ITEM-002", "保護メガネ", "安全用品", "個"),
            ("ITEM-003", "六角ボルト M8", "締結部品", "本"), ("ITEM-004", "潤滑オイル", "消耗品", "缶"),
            ("ITEM-005", "梱包テープ", "梱包資材", "巻"),
        ]
        demo_locations = [
            ("LOC-01", "中央倉庫", "A"), ("LOC-02", "組立エリア", "B"), ("LOC-03", "保守部品庫", "C"),
            ("LOC-04", "出荷準備場", "D"), ("LOC-05", "検査エリア", "E"), ("LOC-06", "予備倉庫", "F"),
        ]
        demo_rules = [("LOC-01", "ITEM-001", 20), ("LOC-01", "ITEM-002", 10), ("LOC-02", "ITEM-001", 12), ("LOC-02", "ITEM-003", 50), ("LOC-03", "ITEM-004", 8)]
        demo_transactions = [
            ("SEED-001", "IN", "LOC-01", "ITEM-001", 50, 45, "初期受入"), ("SEED-002", "OUT", "LOC-01", "ITEM-001", 12, 1, "作業用払出"),
            ("SEED-003", "IN", "LOC-01", "ITEM-002", 15, 38, "初期受入"), ("SEED-004", "OUT", "LOC-01", "ITEM-002", 8, 1, "現場払出"),
            ("SEED-005", "IN", "LOC-02", "ITEM-003", 150, 42, "初期受入"), ("SEED-006", "OUT", "LOC-02", "ITEM-003", 10, 4, "組立払出"),
            ("SEED-008", "IN", "LOC-02", "ITEM-001", 20, 2, "初期配置"),
            ("SEED-009", "OUT", "LOC-02", "ITEM-001", 9, 0, "作業用払出"), ("SEED-010", "IN", "LOC-03", "ITEM-004", 19, 42, "保守在庫"),
            ("SEED-011", "IN", "LOC-01", "ITEM-005", 32, 35, "梱包資材受入"),
        ]

        # ── 生成デモ層（AIノートのバッチ下限 ≥100 行を満たす現実規模の倉庫）──────────
        # Domo の AI テキスト生成タイルは BATCH 実行のみで「入力 100 行以上」が必須
        # （DP-TGTFR）。品目×ロケーションごとに1行の AI ノートを出すには残高を 100 件以上
        # そろえる必要があるため、実在しそうな SKU を機械生成して 30 品目×6 ロケーションの
        # 小規模倉庫にする。数量・経過日数・最小在庫は index/slot の決定的な式で算出するので、
        # 何度 apply しても同じデータに収束する（冪等）。
        generated_specs = [
            ("防塵マスク", "安全用品", "個"), ("耳栓", "安全用品", "組"), ("安全靴", "安全用品", "足"),
            ("六角ボルト M10", "締結部品", "本"), ("平ワッシャー M8", "締結部品", "個"), ("ナット M8", "締結部品", "個"),
            ("結束バンド", "消耗品", "本"), ("ウエス", "消耗品", "枚"), ("軍手", "安全用品", "双"),
            ("ストレッチフィルム", "梱包資材", "巻"), ("段ボール箱 中", "梱包資材", "枚"), ("気泡緩衝材", "梱包資材", "巻"),
            ("電動ドライバー", "工具", "台"), ("ドリルビットセット", "工具", "組"), ("ノギス", "工具", "個"),
            ("デジタルテスター", "工具", "台"), ("ヒューズ 10A", "電気部品", "個"), ("端子台", "電気部品", "個"),
            ("ビニールテープ", "消耗品", "巻"), ("Oリング", "配管部品", "個"), ("継手 1/2", "配管部品", "個"),
            ("シールテープ", "配管部品", "巻"), ("グリス", "消耗品", "缶"), ("作業用洗剤", "清掃用品", "本"),
            ("モップ", "清掃用品", "本"),
        ]

        # 冪等性のため、既存レコードのキー集合を先読みする。件数分だけ個別 find すると
        # AppDB 呼び出しがシード規模に比例して膨らむため、query 1回ずつで済ませる。
        existing_item_codes = {str(row.get("item_code") or "") for row in _records("query", "ITEM")}
        existing_location_codes = {str(row.get("location_code") or "") for row in _records("query", "LOCATION")}
        existing_rule_keys = {str(row.get("rule_key") or "") for row in _records("query", "RULE")}
        # 物理削除されたマスタを SEED で作り直せるよう、archived 印の付いた SEED 由来取引を先に
        # 物理削除する。ITEM/LOCATION を消すと取引は archived として台帳に残り、RECALCULATE は
        # archived を集計除外する。これを消さないと、下の request_id 重複ガードが archived 取引を
        # 「既存」として素通りさせて再登録せず、かつ RECALCULATE も集計しないため、消したデモ品目を
        # 再 SEED しても残高が復活しない。source が SEED 由来（DEMO_SEED / DEMO_SEED_GENERATED）で
        # archived のものだけを掃除するので、実ユーザーの取引や、まだ削除していない SEED 取引
        # （archived でない＝冪等ガードで素通りさせたい）は触らない。SEED は既知のデモ一式を冪等に
        # 再生成する管理者専用の操作だからこそ許される限定的な掃除。同じ query 走査で生存分の
        # request_id 集合も作り、台帳を二度なめしない。
        seed_sources = {"DEMO_SEED", "DEMO_SEED_GENERATED"}
        purged_archived_seed = 0
        existing_request_ids = set()
        real_activity_keys = set()  # 実運用取引(非SEED由来)のある balance_key。SEED はここを絶対に汚さない。
        for row in _records("query", "TRANSACTION"):
            source = str(row.get("source") or "")
            if _is_true(row.get("archived")) and source in seed_sources and row.get("_document_id"):
                _records("delete", document_id=row["_document_id"])
                purged_archived_seed += 1
                continue
            existing_request_ids.add(str(row.get("request_id") or ""))
            # SEED 由来でない取引が1件でもあるキー（ロケーション|品目）は、実運用データが載っている
            # とみなす。同じデモコード（例: LOC-01|ITEM-001）を実業務で使う配布先で SEED を再実行した
            # とき、そのキーへデモ取引/ルールを注入すると実在庫や基準を黙って書き換えて残高を壊す
            # （request_id が別なので重複ガードもすり抜ける）。よって「実取引のあるキー」を集めて下の
            # デモ注入から除外する。archived な実取引（実マスタを消した痕跡）も実運用の証跡として数え、
            # 一度消したキーをデモで勝手に復活させない。SEED 由来キーはここには入らないので、実取引の
            # ないデモ品目は物理削除後の再 SEED で従来どおり再生成できる（保護するのは実取引のあるキーだけ）。
            if source not in seed_sources:
                key = f"{str(row.get('location_code') or '').strip().upper()}|{str(row.get('item_code') or '').strip().upper()}"
                real_activity_keys.add(key)
        location_names = {code: name for code, name, _ in demo_locations}
        all_location_codes = [code for code, _, _ in demo_locations]
        created = {"masters": 0, "transactions": 0, "purged_archived_seed": purged_archived_seed, "protected_real_keys": len(real_activity_keys)}
        # await_queryable のバリア対象。今回 create したキーだけを集め、既存（＝再実行）分は
        # 先読みクエリで可視と確認済みなので待たない。作成直後の一括 query が反映前に空振りして
        # INVALID_ITEM（マスタ側）や BALANCE 過少（台帳側）を招くのを、下の2バリアで防ぐ。
        seeded_item_codes: set = set()
        seeded_location_codes: set = set()
        seeded_rule_keys: set = set()
        seeded_txn_request_ids: set = set()

        for item_code, item_name, category, unit in demo_items:
            if item_code not in existing_item_codes:
                _records("create", "ITEM", record_key=f"ITEM|{item_code}", content={"item_code": item_code, "item_name": item_name, "category": category, "unit": unit, "qr_value": f"ITEM:{item_code}", "active": True, "updated_at": now})
                created["masters"] += 1
                seeded_item_codes.add(item_code)
        for location_code, location_name, zone in demo_locations:
            if location_code not in existing_location_codes:
                _records("create", "LOCATION", record_key=f"LOCATION|{location_code}", content={"location_code": location_code, "location_name": location_name, "zone": zone, "qr_value": f"LOC:{location_code}", "active": True, "updated_at": now})
                created["masters"] += 1
                seeded_location_codes.add(location_code)
        for location_code, item_code, minimum in demo_rules:
            rule_key = f"{location_code}|{item_code}"
            if rule_key not in existing_rule_keys and rule_key not in real_activity_keys:
                _records("create", "RULE", record_key=f"RULE|{rule_key}", content={"rule_key": rule_key, "location_code": location_code, "item_code": item_code, "minimum_quantity": minimum, "notification_enabled": True, "active": True, "updated_at": now})
                created["masters"] += 1
                seeded_rule_keys.add(rule_key)

        # ── 結果整合性バリア①: デモ取引を _register へ流す前に、直前で作成したマスタが query
        #    インデックスに現れるまで待つ。作成直後の品目/ロケーション検索が反映前に空振りすると、
        #    正当なデモ取引が INVALID_ITEM / INVALID_LOCATION で SEED_FAILED に化ける（失敗モード⑤の
        #    マスタ側）。既存分は待たない＝全て可視なら query 1回で即抜ける。
        master_wait = {
            "item": await_queryable("ITEM", "item_code", seeded_item_codes),
            "location": await_queryable("LOCATION", "location_code", seeded_location_codes),
        }
        # 反映が予算内に間に合わなければ、デモ取引を _register へ流す前に明示エラーで中断する
        # （不可視マスタのまま流すと INVALID_ITEM に化けるため）。リトライで冪等に再開できる。
        require_converged("masters", master_wait)

        seed_base = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
        for request_id, transaction_type, location_code, item_code, quantity, days_ago, reason in demo_transactions:
            # request_id 重複（同一デモの再実行）に加え、そのキーに実運用取引があるときも注入しない。
            if request_id in existing_request_ids or f"{location_code}|{item_code}" in real_activity_keys:
                continue
            result = _register({"request_id": request_id, "transaction_type": transaction_type, "location_code": location_code, "item_code": item_code, "quantity": quantity, "reason": reason, "source": "DEMO_SEED", "occurred_at": (seed_base - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")}, user)
            if not result.get("ok"):
                raise Exception({"code": "SEED_FAILED", "message": f"{request_id}の投入に失敗しました。", "details": result.get("error") or {}})
            created["transactions"] += 1
            seeded_txn_request_ids.add(request_id)

        # 生成層: 品目ごとに 6 ロケーション中 5 か所へ初期在庫を1件ずつ投入する
        # （skip する1か所は index でずらし、全ロケーションがまんべんなく埋まるようにする）。
        # 取引はアラート副作用の不要な初期在庫なので、_register を通さず直接 TRANSACTION を
        # 作成し、最後の RECALCULATE で残高をまとめて再構築する（apply の呼び出し回数を抑える）。
        for index, (item_name, category, unit) in enumerate(generated_specs):
            item_code = f"ITEM-{index + 6:03d}"
            if item_code not in existing_item_codes:
                _records("create", "ITEM", record_key=f"ITEM|{item_code}", content={"item_code": item_code, "item_name": item_name, "category": category, "unit": unit, "qr_value": f"ITEM:{item_code}", "active": True, "updated_at": now})
                created["masters"] += 1
                seeded_item_codes.add(item_code)
            skip_code = all_location_codes[index % len(all_location_codes)]
            placements = [code for code in all_location_codes if code != skip_code]
            for slot, location_code in enumerate(placements):
                quantity = 20 + ((index * 7 + slot * 13) % 80)
                days_ago = (index * 3 + slot * 11) % 60
                request_id = f"GEN-{item_code}-{location_code}"
                gen_key = f"{location_code}|{item_code}"
                # 実運用取引のあるキーには生成デモ在庫を注入しない（実在庫の上書き防止）。
                if request_id not in existing_request_ids and gen_key not in real_activity_keys:
                    occurred_at = (seed_base - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")
                    _records("create", "TRANSACTION", record_key=f"TRANSACTION|{request_id}", content={
                        "transaction_id": request_id, "request_id": request_id, "transaction_type": "IN",
                        "item_code": item_code, "item_name": item_name,
                        "location_code": location_code, "location_name": location_names.get(location_code, location_code),
                        "quantity": float(quantity), "signed_quantity": float(quantity),
                        "balance_before": 0.0, "balance_after": float(quantity),
                        "reason": "初期在庫", "operator_user_id": user["id"], "operator_name": user["name"],
                        "source": "DEMO_SEED_GENERATED", "occurred_at": occurred_at, "created_at": now,
                    })
                    created["transactions"] += 1
                    seeded_txn_request_ids.add(request_id)
                # 主ロケーション(slot 0)にだけ最小在庫ルールを敷く。4件に1件は基準を在庫より
                # 高く設定して「在庫不足」を意図的に作り、不足の色分けと AIノートの注意喚起を見せる。
                if slot == 0:
                    rule_key = f"{location_code}|{item_code}"
                    if rule_key not in existing_rule_keys and rule_key not in real_activity_keys:
                        minimum = quantity + 15 if index % 4 == 0 else max(quantity - 10, 5)
                        _records("create", "RULE", record_key=f"RULE|{rule_key}", content={"rule_key": rule_key, "location_code": location_code, "item_code": item_code, "minimum_quantity": minimum, "notification_enabled": True, "active": True, "updated_at": now})
                        created["masters"] += 1
                        seeded_rule_keys.add(rule_key)

        # ── 結果整合性バリア②: RECALCULATE で残高を作り直す前に、SEED が作成した取引・マスタ・
        #    ルールが query インデックスに出そろうまで待つ。取引が反映前だと signed_quantity が
        #    集計から漏れて BALANCE が過少になり（失敗モード⑤の台帳側）、生成 ITEM が未反映だと
        #    その残高が丸ごと skipped_deleted 扱いで欠け、ルール未反映なら不足フラグが立たない。
        ledger_wait = {
            "item": await_queryable("ITEM", "item_code", seeded_item_codes),
            "location": await_queryable("LOCATION", "location_code", seeded_location_codes),
            "rule": await_queryable("RULE", "rule_key", seeded_rule_keys),
            "transaction": await_queryable("TRANSACTION", "request_id", seeded_txn_request_ids),
        }
        created["appdb_consistency"] = {"masters": master_wait, "ledger": ledger_wait}
        # 反映が間に合わなければ RECALCULATE を走らせない。反映前に集計すると取引を取りこぼした
        # 「残高の作り込み不足」をエラーも出さずに残す（失敗モード⑤の最悪形）。明示エラーで中断し、
        # 再実行を促す（作成済みデータは冪等に再利用されるので重複投入は起きない）。
        require_converged("ledger", ledger_wait)

        recalculation = _admin("RECALCULATE", {}, user)
        return {"ok": True, "message": "デモデータ（現実規模の倉庫）を確認しました。", "created": created, "recalculation": recalculation}

    return {
        "is_true": _is_true,
        "resolve_recipient_email": _resolve_recipient_email,
        "records": _records,
        "register": _register,
        "notify_now": _notify_now,
        "admin": _admin,
    }


def inventory_api(operation: str, request_json: str = "{}") -> dict:
    """Pro Code と管理者操作の双方が使う唯一の公開関数（単一エントリポイント）。

    ``operation``（動詞）で分岐し、実処理は private ヘルパーへ委譲する薄い
    ディスパッチャ。ここで (1) 入力 JSON の正規化、(2) 実行利用者の解決と
    管理者判定、(3) 例外を安定した公開エラーボディへ変換、という横断的関心事を
    一手に引き受け、ヘルパー側は業務ロジックに専念できるようにしている。

    Args:
        operation: 実行する操作名（AUTH / GET_STATE / 取引 / マスタ保守など）。
            大文字小文字・前後空白は正規化する。
        request_json: 操作固有の要求。JSON 文字列または dict を受け付け、
            空・None は空要求として扱う。

    Returns:
        ``ok`` を含む結果 dict。失敗時も送出せず ``ok=False`` とエラー内容を返す。
    """
    try:
        # 非公開ヘルパーは _service ファクトリ内のクロージャに束ねてある。公開関数はここで
        # 一度ファクトリを受け、以降は素の名前（下の局所束縛）で辿る。クロージャは呼び出し時に
        # モジュール定数（COLLECTION_ID など）を参照するため、束ね直しても設定差し替えは尊重される。
        svc = _service()
        _records = svc["records"]
        _register = svc["register"]
        _notify_now = svc["notify_now"]
        _admin = svc["admin"]

        action = str(operation or "").strip().upper()
        if isinstance(request_json, dict):
            request = request_json
        elif request_json in (None, ""):
            request = {}
        else:
            try:
                request = json.loads(request_json)
            except (TypeError, ValueError) as error:
                raise Exception({"code": "INVALID_JSON", "message": "request_jsonの形式が正しくありません。", "details": {}}) from error
        if not isinstance(request, dict):
            raise Exception({"code": "INVALID_REQUEST", "message": "request_jsonはJSONオブジェクトで指定してください。", "details": {}})

        try:
            getter = getattr(codeengine, "get_execution_information", None) or getattr(codeengine, "getExecutionInformation", None)
            info = getter() if getter else {}
        except Exception:
            info = {}
        user_id = str((info or {}).get("userId") or (info or {}).get("user_id") or "")
        if not user_id:
            raise Exception({"code": "AUTHENTICATION_REQUIRED", "message": "Domo利用者を確認できません。", "details": {}})
        user = {
            "id": user_id,
            # 氏名の決め方（本人特定の id は常に実行コンテキスト由来＝サーバー権威・上書き不可）:
            #   ① get_execution_information() の氏名を最優先（信頼度が高い）。
            #   ② それを返さないインスタンスでは、フロントが People API で解決した表示名を
            #      operator_display_name として送るので、それを「表示ラベル」として採用し AppDB に
            #      永続化する（operator_name が空のままで画面がユーザーIDだけになる問題の恒久修正）。
            #      氏名ラベルは詐称し得るが、監査の鍵は operator_user_id（id）なので安全性は不変。
            #   ③ どちらも無ければ空文字（プレースホルダの仮名は作らない）。email も同契約。
            "name": str(
                info.get("userName")
                or info.get("displayName")
                or request.get("operator_display_name")
                or ""
            )[:120],
            "email": str(info.get("userEmail") or info.get("email") or "")[:200],
            "isAdmin": user_id in ADMIN_USER_IDS,
        }

        if action == "AUTH":
            return {"ok": True, "user": user}
        if action == "GET_STATE":
            # find 結果には内部の _document_id が付く。FE へ返す前に取り除き、
            # LIST_MASTERS と同じ「内部フィールドを公開しない」契約に揃える。
            strip_internal = lambda row: {name: value for name, value in row.items() if not name.startswith("_")}
            state: dict = {"ok": True, "user": user}
            if request.get("location_code") and request.get("item_code"):
                key = f"{str(request['location_code']).upper()}|{str(request['item_code']).upper()}"
                balance = _records("find", "BALANCE", field="balance_key", value=key)
                rule = _records("find", "RULE", field="rule_key", value=key)
                state["balance"] = strip_internal(balance) if balance else {"balance_key": key, "quantity": 0}
                state["rule"] = strip_internal(rule) if rule else None
            return state

        # 以降は AppDB を追加・更新・削除する操作。結果を確定してから標準同期を一度だけ
        # 即時キックし、ダッシュボード（DataFlow 入力）へ数秒で反映する。品目ごとではなく
        # 操作ごとに1回だけ呼ぶ（SEED のような一括処理で多重起動しないため）。
        if action == "REGISTER":
            result = _register(request, user)
        elif action == "NOTIFY_NOW":
            result = _notify_now(request, user)
        elif action == "NOTIFICATION_STATUS":
            # 通知履歴の状態を明示更新する監査用の入口。Workflow の起動と STARTED／FAILED の
            # 記録は REGISTER／NOTIFY_NOW の中で CE が行うため、通常の画面導線はここを呼ばない。
            # 運用者が履歴を手動で補正する（調査後の確定など）ための互換面として残す。
            alert_id = str(request.get("alert_id") or "").strip()
            status = str(request.get("status") or "").strip().upper()
            if not alert_id or status not in {"STARTED", "FAILED"}:
                raise Exception({"code": "INVALID_NOTIFICATION_STATUS", "message": "通知状態の更新内容が正しくありません。", "details": {}})
            alert = _records("find", "ALERT_HISTORY", field="alert_id", value=alert_id)
            if not alert:
                raise Exception({"code": "ALERT_NOT_FOUND", "message": "通知履歴が見つかりません。", "details": {}})
            if alert.get("operator_user_id") and str(alert.get("operator_user_id")) != user["id"]:
                raise Exception({"code": "FORBIDDEN", "message": "この通知履歴は更新できません。", "details": {}})
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            _records("upsert", "ALERT_HISTORY", record_key=f"ALERT_HISTORY|{alert_id}", content={
                "alert_id": alert_id,
                "notification_status": status,
                "workflow_instance_id": str(request.get("workflow_instance_id") or "")[:200],
                "error_message": str(request.get("error_message") or "")[:300] if status == "FAILED" else "",
                "updated_at": now,
            })
            result = {"ok": True, "alert_id": alert_id, "notification_status": status}
        elif action in {"RECALCULATE", "SEED"}:
            result = _admin(action, request, user)
        elif action == "MANAGE_MASTER":
            # MANAGE_MASTER はマスタ CRUD 専用の operation。inner action を MASTER_ACTIONS で
            # 境界検証し、マスタ以外（RECALCULATE / SEED など）が _admin の該当枝へ到達しない
            # ようにする（マスタ操作に許す action 集合の限定をこの境界へ集約する）。
            master_action = str(request.get("action") or "").strip().upper()
            if master_action not in MASTER_ACTIONS:
                raise Exception({"code": "UNSUPPORTED_MASTER_ACTION", "message": "actionはUPSERT_ITEM、UPSERT_LOCATION、UPSERT_RULE、DELETE_ITEM、DELETE_LOCATION、DELETE_RULE、LIST_MASTERSのいずれかです。", "details": {}})
            result = _admin(master_action, request, user)
        else:
            raise Exception({"code": "UNSUPPORTED_OPERATION", "message": "operationはAUTH、GET_STATE、REGISTER、NOTIFY_NOW、NOTIFICATION_STATUS、RECALCULATE、SEED、MANAGE_MASTERのいずれかです。", "details": {}})

        # 標準同期の即時キックはあくまで前倒し。失敗しても書込みは確定済みで、次回の
        # スケジュール同期（約15分間隔）が回収するため、ここでの失敗は握りつぶして
        # 業務結果をそのまま返す（同期の成否で在庫操作の成否を左右させない）。
        try:
            _records("sync")
        except Exception:
            LOGGER.warning("standard-sync kick after %s failed; scheduled sync will reconcile", action)
        return result
    except Exception as error:
        # 想定内の業務エラーは、公開用エラーボディ（code/message を持つ dict）を第1引数にして
        # 送出している（独自の例外クラスを使わない方針）。その形状を見て公開エラーへ変換する。
        # それ以外（想定外のバグ等）は details を伏せて INTERNAL_ERROR に丸める。
        body = error.args[0] if error.args else None
        if isinstance(body, dict) and "code" in body and "message" in body:
            return {"ok": False, "error": body}
        LOGGER.exception("Unexpected inventory service error")
        return {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": "処理中にエラーが発生しました。", "details": {}}}
