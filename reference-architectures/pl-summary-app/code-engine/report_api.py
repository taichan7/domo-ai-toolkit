"""店舗別損益AI要約のレポート保存 Code Engine（単一公開関数 ``pl_report_api``）。

Workflow の AI エージェントが**ツール**として呼び出す。``operation="save"`` は AI が作成した
レポート（フラット JSON）を AppDB コレクションへ保存し、**同じ ``doc_key`` の古いドキュメントだけ**を
削除する（重複除去を保存処理に内包する）。これにより、従来 WF-01 の先頭に置いていた独立した
重複除去ノード（``dedupe_appdb_documents``）が不要になる。reference-app と同じ
「AI エージェントが CE ツールで検証・保存まで完結する」構成に揃えたもの。

``pl_report_api(operation, request)``:
- ``operation="save"``: ``request = {collection_id, document}``（document は入れ子でも、
  collection_id を除いた平坦な request でもよい）。レポートを保存し、同一 ``doc_key`` の
  旧版（サーバー ``createdOn`` が今回より厳密に古いもの）だけを削除する。
- ``operation="validate"``: ``request = {collection_id, doc_key}``。保存前に識別子だけを
  軽く検証する（AI が生成前に接続先と doc_key を確認するための補助。必須ではない）。

想定内の業務エラーは、公開用エラーボディ（``{"code","message","details"}`` の dict）を第1引数に
持たせた組込み ``Exception`` として送出する（Code Engine は独自の例外クラスを持ち込めない）。
公開ディスパッチャ ``pl_report_api`` がその形状を見て ``{"ok": False, "error": ...}`` に変換し、
想定外の例外は ``INTERNAL_ERROR`` に丸める。1件の不備が Workflow ステップ全体を失敗させず、AI は
理由を受け取って終了できる。

認証トークンは不要（Domo Code Engine ランタイムが ``codeengine`` モジュール経由で認証を注入する）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

# Domo が将来 v4 以外の UUID を発行しても誤拒否しない（GUID 形状チェックが主ガード）。
GUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
MAX_DOCUMENT_BYTES = 200_000
# bulk 削除は URL 長を抑えるため 100 件ずつに分割する（GUID×100 ≒ 3700 文字）。
DELETE_CHUNK_SIZE = 100
# 保存の必須フィールド（フロントが描画・一覧に使う最低限）。save は破壊的（同一 doc_key の旧版を
# 削除する）ため、これらが欠けた不完全ドキュメントで既存の正レポートを上書き削除しないための門番。
# reference-app の _validate_document が持つ安全性質を軽量版で踏襲する。
REQUIRED_SAVE_FIELDS = ("doc_key", "store_id", "location_name", "analysis_html")

# 【信頼境界メモ（意図的設計）】collection_id は呼び出し側（Workflow 変数経由で AI ツール引数）から
# 受け取り、GUID 形状のみ検証する。reference-app はコレクションIDを配備時に
# RUNTIME_CONFIG へ固定（fail-closed）するが、本アプリは「CE はインスタンス非依存・collection_id は
# Workflow 変数から渡す」ことを配布容易性のための設計判断として採用している（AGENT.md「移植」節）。
# したがってコレクション固定は行わない（移植先では WF-01 の CollectionId 変数だけ差し替えれば動く）。


def _service() -> dict:
    """非公開ヘルパーを1スコープに束ねて「操作名→関数」の dict で返す内部ファクトリ。

    全ヘルパーをこのファクトリ内に定義して top-level から外し、公開 ``def`` を
    ``pl_report_api`` の1つに保つ（reference-app の ``report_api`` と同じ構成）。
    """

    def _valid_iso_timestamp(value: str) -> bool:
        """generated_at が ISO8601 として解釈できるか（不正値を画面の日時降順ソートへ流さない）。"""
        if not value:
            return False
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except (TypeError, ValueError):
            return False

    def _documents(value: Any) -> List[Dict[str, Any]]:
        """AppDB query の list / wrapped response を同じ形へ正規化する。"""
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            for key in ("documents", "data", "items", "results"):
                if isinstance(value.get(key), list):
                    return [row for row in value[key] if isinstance(row, dict)]
        return []

    def _coerce_document(document: Any) -> Dict[str, Any]:
        """AI ツール引数の軽微な形揺れを、安全な保存用 dict へ決定的に整える。

        - 文字列で来たら JSON パースする。
        - ``{"document": {...}}`` の入れ子なら中身を取り出す。
        - 単一キー ``{"content": {...}}`` ラッパで来たら中身を取り出す（AppDB の content ラッパは
          保存時にこちらで付与するため、二重 content を防ぐ）。
        - ``doc_key`` は必須。``generated_at`` が無ければ現在時刻（UTC ISO8601）を補完する。
        """
        if isinstance(document, str):
            try:
                document = json.loads(document)
            except json.JSONDecodeError as exc:
                raise Exception({"code": "INVALID_DOCUMENT",
                                 "message": "document はJSONオブジェクトで指定してください",
                                 "details": {}}) from exc
        if isinstance(document, dict) and isinstance(document.get("document"), dict):
            document = document["document"]
        if isinstance(document, dict) and len(document) == 1 and isinstance(document.get("content"), dict):
            document = document["content"]
        if not isinstance(document, dict):
            raise Exception({"code": "INVALID_DOCUMENT",
                             "message": "document はJSONオブジェクトで指定してください", "details": {}})
        key = str(document.get("doc_key") or "").strip()
        if not key:
            raise Exception({"code": "MISSING_DOC_KEY",
                             "message": "doc_key は必須です", "details": {}})
        document["doc_key"] = key
        # 空だけでなく「非空だが ISO 不正」も現在時刻へ正規化する（画面は generated_at 降順表示）。
        raw_generated = str(document.get("generated_at") or "").strip()
        document["generated_at"] = raw_generated if _valid_iso_timestamp(raw_generated) else datetime.now(timezone.utc).isoformat()
        return document

    def _require_report_fields(document: Dict[str, Any]) -> None:
        """保存前の門番: フロントが描画・一覧に使う必須フィールドの非空を保証する。

        save は破壊的（同一 doc_key の旧版を削除する）。不完全・空のドキュメントを「最新」として
        保存すると、直後の重複除去が既存の正レポートを巻き添えに削除し、画面が空の analysis_html に
        置き換わる。この門番で不完全保存を POST 前に弾き、既存レポートを保護する。
        """
        missing = [name for name in REQUIRED_SAVE_FIELDS if not str(document.get(name) or "").strip()]
        if missing:
            raise Exception({"code": "MISSING_FIELDS",
                             "message": "レポートの必須項目が不足しています: " + ", ".join(missing),
                             "details": {"missing": missing}})

    def _require_collection(request: Dict[str, Any]) -> str:
        collection_id = str(request.get("collection_id") or "").strip()
        if not GUID_PATTERN.match(collection_id):
            raise Exception({"code": "INVALID_COLLECTION_ID",
                             "message": "collection_id の形式が正しくありません", "details": {}})
        return collection_id

    def _validate(request: Dict[str, Any]) -> Dict[str, Any]:
        """保存前に識別子だけを軽く検証する（operation="validate"）。"""
        collection_id = _require_collection(request)
        doc_key = str(request.get("doc_key") or "").strip()
        if not doc_key:
            raise Exception({"code": "MISSING_DOC_KEY", "message": "doc_key は必須です", "details": {}})
        return {"ok": True, "collection_id": collection_id, "doc_key": doc_key}

    def _save(request: Dict[str, Any]) -> Dict[str, Any]:
        """レポートを保存し、同じ doc_key の旧版だけを削除する（operation="save"）。

        作成成功後に、サーバー ``createdOn`` が今回より**厳密に古い**同一 doc_key の文書だけを
        削除する。同時刻/未知時刻は保持し、AI 制御の ``generated_at`` では消さない（並行実行時に
        「全員が自分以外を削除」して全滅する事故を防ぐ）。作成後の照会・削除に失敗しても作成自体は
        成功しているため ``ok:True``（cleanup_incomplete）を返し、再試行による同一 doc_key の重複
        蓄積を避ける。旧版照会はページングして取りこぼさない。
        """
        import codeengine  # Domo Code Engine ランタイムでのみ提供される

        collection_id = _require_collection(request)
        document: Any = request.get("document")
        if not isinstance(document, (dict, str)):
            # 平坦フォールバック: 保存先/操作/分岐などの非ドキュメント・ルーティングキーは文書に混ぜない
            # （report_type 等が AppDB へ漏れてスキーマがドリフトしないようにする）。
            document = {name: value for name, value in request.items()
                        if name not in ("collection_id", "operation", "report_type")}
        report = _coerce_document(document)
        _require_report_fields(report)  # 不完全ドキュメントで既存の正レポートを上書き削除しない門番
        encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_DOCUMENT_BYTES:
            raise Exception({"code": "DOCUMENT_TOO_LARGE", "message": "document が大きすぎます", "details": {}})

        created = codeengine.send_request(
            "post", f"api/datastores/v1/collections/{collection_id}/documents",
            {"content": report},
        ) or {}
        created_id = str(created.get("id") or "") if isinstance(created, dict) else ""
        if not created_id:
            raise Exception({"code": "REQUEST_NOT_SAVED",
                             "message": "レポートを保存できませんでした。少し待ってから再度お試しください。",
                             "details": {}})

        key = report["doc_key"]
        try:
            matching: List[Dict[str, Any]] = []
            offset, page = 0, 1000
            while True:
                batch = _documents(codeengine.send_request(
                    "post",
                    f"api/datastores/v2/collections/{collection_id}/documents/query?limit={page}&offset={offset}",
                    {"content.doc_key": {"$eq": key}},
                ))
                matching.extend(row for row in batch
                                if str((row.get("content") or {}).get("doc_key") or "") == key)
                if len(batch) < page or offset >= 20000:
                    break
                offset += page

            def server_time(row: Dict[str, Any]):
                try:
                    value = datetime.fromisoformat(str(row.get("createdOn") or "").replace("Z", "+00:00"))
                    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    return None

            observed = next((row for row in matching if str(row.get("id")) == created_id), created)
            created_time = server_time(observed)
            stale_ids = [str(row["id"]) for row in matching
                         if row.get("id") and str(row["id"]) != created_id
                         and created_time is not None and server_time(row) is not None
                         and server_time(row) < created_time]
            deleted = 0
            for start in range(0, len(stale_ids), DELETE_CHUNK_SIZE):
                chunk = stale_ids[start:start + DELETE_CHUNK_SIZE]
                codeengine.send_request(
                    "delete",
                    f"api/datastores/v2/collections/{collection_id}/documents/bulk?ids={','.join(chunk)}",
                )
                deleted += len(chunk)
        except Exception:
            # 作成は成功済み。掃除失敗で全体を失敗にせず、次回 save に委ねる。
            return {"ok": True, "collection_id": collection_id, "doc_key": key,
                    "document_id": created_id, "deleted_stale": 0, "remaining": 1,
                    "cleanup_incomplete": True}

        observed_now = any(str(row.get("id")) == created_id for row in matching)
        return {"ok": True, "collection_id": collection_id, "doc_key": key,
                "document_id": created_id, "matching_after_create": len(matching),
                "deleted_stale": deleted,
                "remaining": max(1, len(matching) - deleted + (0 if observed_now else 1)),
                # read-after-write 即時整合でない場合、直後照会に新版が無いことがある（計数は参考値）。
                "consistency_pending": not observed_now}

    return {"validate": _validate, "save": _save}


def pl_report_api(operation: str = "save", request: Any = None) -> Dict[str, Any]:
    """店舗別損益AIレポートの検証(validate)・保存(save)を担う唯一の公開関数。

    ``operation``（動詞）で分岐し、実処理は ``_service()`` の非公開ヘルパーへ委譲する薄い
    ディスパッチャ。要求 JSON の正規化、操作の解決（空・不明なら request の形から推定）、例外を
    安定した公開エラーボディへ変換する横断的関心事をここで一手に引き受ける。

    Args:
        operation: "save"（既定）または "validate"。大文字小文字・前後空白は正規化する。
        request: 操作固有の要求（JSON 文字列または dict）。save は ``{collection_id, document}``
            （document は入れ子でも平坦でも可）、validate は ``{collection_id, doc_key}``。

    Returns:
        ``ok`` を含む結果 dict。失敗時も送出せず ``ok=False`` とエラー内容を返す。

    @domoWorkflows {output: "object"}
    """
    try:
        svc = _service()
        action = str(operation or "").strip().lower()
        req = request
        if isinstance(req, str):
            if req.strip():
                try:
                    req = json.loads(req)
                except json.JSONDecodeError as exc:
                    raise Exception({"code": "INVALID_REQUEST",
                                     "message": "request は有効なJSON文字列またはオブジェクトで指定してください。",
                                     "details": {}}) from exc
            else:
                req = {}
        if req is None:
            req = {}
        if not isinstance(req, dict):
            raise Exception({"code": "INVALID_REQUEST",
                             "message": "request はJSONオブジェクトで指定してください。", "details": {}})

        if action not in ("validate", "save"):
            if action:
                raise Exception({"code": "INVALID_OPERATION",
                                 "message": "operation は validate / save のいずれかを指定してください。",
                                 "details": {}})
            # operation が空のときだけ request の形から推定する（AI ツールの固定値未指定対策）。
            # 本体シグナル（document キー、または collection_id/doc_key/operation 以外の実データ項目）が
            # あれば save、識別子だけ（{collection_id, doc_key}）なら validate。doc_key の有無だけで
            # save に倒すと、validate の正規リクエストが破壊的 save へ誤誘導されるため含めない。
            body_signal = ("document" in req
                           or any(key not in ("collection_id", "doc_key", "operation") for key in req))
            action = "save" if body_signal else "validate"

        return svc[action](req)
    except Exception as error:
        body = error.args[0] if error.args else None
        if isinstance(body, dict) and "code" in body and "message" in body:
            return {"ok": False, "error": body}
        return {"ok": False, "error": {"code": "INTERNAL_ERROR",
                                       "message": "処理中にエラーが発生しました。", "details": {}}}
