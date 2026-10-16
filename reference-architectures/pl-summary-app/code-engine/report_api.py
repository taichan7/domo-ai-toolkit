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
# 実行者メールの許可パターン（単一 ASCII アドレスのみ）。local=英数と ._%+- 、domain=英数と .- 、
# TLD=英字2+ の**真の allowlist**。制御文字(NUL/ESC)・ゼロ幅/双方向(bidi)・同形異義(homoglyph)・空白・
# カンマ・引用符・山括弧・複数@ を全て弾き、Workflow の start data 経由で AI の Send Email 宛先/本文へ
# 複数アドレスや HTML・不可視文字が混入するのを防ぐ。
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
MAX_EXECUTOR_EMAIL_LEN = 254
MAX_DOCUMENT_BYTES = 200_000
# bulk 削除は URL 長を抑えるため 100 件ずつに分割する（GUID×100 ≒ 3700 文字）。
DELETE_CHUNK_SIZE = 100
# 保存の必須フィールド（フロントが描画・一覧に使う最低限）。save は破壊的（同一 doc_key の旧版を
# 削除する）ため、これらが欠けた不完全ドキュメントで既存の正レポートを上書き削除しないための門番。
# reference-app の _validate_document が持つ安全性質を軽量版で踏襲する。
REQUIRED_SAVE_FIELDS = ("doc_key", "store_id", "location_name", "analysis_html")
MAIN_WORKFLOW_MODEL_ID = "__MAIN_WORKFLOW_MODEL_ID__"
SUB_WORKFLOW_MODEL_ID = "__SUB_WORKFLOW_MODEL_ID__"
REPORT_COLLECTION_ID = "__REPORT_COLLECTION_ID__"
RUNNING_STATUSES = {"IN_PROGRESS", "RUNNING", "PENDING", "STARTED"}

# The provisioner embeds the discovered business collection for this deployment.
# Caller-supplied collection_id is retained for Workflow compatibility, but may
# only select that collection. An unresolved binding fails before any AppDB I/O.


def _service() -> dict:
    """非公開ヘルパーを1スコープに束ねて「操作名→関数」の dict で返す内部ファクトリ。

    全ヘルパーをこのファクトリ内に定義して top-level から外し、公開 ``def`` を
    ``pl_report_api`` の1つに保つ（reference-app の ``report_api`` と同じ構成）。
    """

    def _workflow_model() -> str:
        if not GUID_PATTERN.fullmatch(MAIN_WORKFLOW_MODEL_ID) or not GUID_PATTERN.fullmatch(SUB_WORKFLOW_MODEL_ID):
            raise Exception({"code": "WORKFLOW_NOT_CONFIGURED",
                             "message": "Workflowの接続先が未設定です。管理者へ確認してください。",
                             "details": {}})
        return MAIN_WORKFLOW_MODEL_ID

    def _workflow_status(request: Dict[str, Any]) -> Dict[str, Any]:
        import codeengine
        model_id = _workflow_model()
        instance_id = str(request.get("instance_id") or "").strip()
        if instance_id:
            if not GUID_PATTERN.fullmatch(instance_id):
                raise Exception({"code": "INVALID_INSTANCE_ID", "message": "実行IDが不正です。", "details": {}})
            row = codeengine.send_request("get", f"api/workflow/v1/instances/{instance_id}")
            if not isinstance(row, dict) or row.get("modelId") != model_id:
                raise Exception({"code": "INVALID_INSTANCE_ID", "message": "このアプリの実行ではありません。", "details": {}})
        else:
            rows = codeengine.send_request(
                "get", f"api/workflow/v1/instances?modelId={model_id}&limit=100&offset=0")
            if not isinstance(rows, list):
                raise Exception({"code": "WORKFLOW_STATUS_ERROR", "message": "実行状況を確認できません。", "details": {}})
            owned = [r for r in rows if isinstance(r, dict) and r.get("modelId") == model_id]
            running = [r for r in owned if str(r.get("status") or "").upper() in RUNNING_STATUSES]
            row = max(running or owned, key=lambda r: str(r.get("createdOn") or ""), default={})
        status = str(row.get("status") or ("IDLE" if not row else "")).upper()
        if not status:
            raise Exception({"code": "WORKFLOW_STATUS_ERROR", "message": "実行状況を確認できません。", "details": {}})
        return {"ok": True, "instance_id": str(row.get("id") or ""), "status": status,
                "progress_path": f"/workflows/instances/{SUB_WORKFLOW_MODEL_ID}/",
                "model_version": str(row.get("modelVersion") or ""),
                "created_on": str(row.get("createdOn") or ""),
                "completed_on": str(row.get("completedOn") or ""),
                "running": status in RUNNING_STATUSES}

    def _workflow_start(request: Dict[str, Any]) -> Dict[str, Any]:
        import codeengine
        # 実行者本人の通知のため executor_email だけは受理する（既存メールの宛先に実行者を1人加える
        # 用途のみ）。それ以外のキーは従来どおり拒否し、実行対象・入力のサーバー側固定を保つ
        # （任意キーが Workflow trigger の data へ漏れないようにする）。
        unexpected = set(request) - {"executor_email"}
        if unexpected:
            raise Exception({"code": "INVALID_REQUEST",
                             "message": "実行対象・入力はサーバー側で固定されています。executor_email 以外は指定できません。",
                             "details": {}})
        executor_email = str(request.get("executor_email") or "").strip()
        # 実行者通知は任意の付加機能。形式不正・長すぎる値は本人宛て送信だけをスキップ（空扱い）し、
        # レポート生成（主機能）は止めない＝FE の best-effort／プロンプトの skip-if-invalid と整合。
        # 厳格 allowlist を通らない値は Workflow data へ流さない（AI の Send Email 宛先/本文への混入も防ぐ）。
        if executor_email and (len(executor_email) > MAX_EXECUTOR_EMAIL_LEN
                               or not EMAIL_PATTERN.fullmatch(executor_email)):
            executor_email = ""
        current = _workflow_status({})
        if current["running"]:
            return dict(current, already_running=True)
        model_id = _workflow_model()
        model = codeengine.send_request("get", f"api/workflow/v1/models/{model_id}")
        active = [v for v in (model.get("versions") or []) if isinstance(v, dict) and v.get("active") is True]
        if not active:
            raise Exception({"code": "WORKFLOW_NOT_RELEASED", "message": "公開済みのWorkflowがありません。", "details": {}})
        version = str(max(active, key=lambda v: tuple(int(p) for p in str(v.get("version") or "0.0.0").split(".")))["version"])
        definition = codeengine.send_request("get", f"api/workflow/v1/models/{model_id}/versions/{version}") or {}
        if isinstance(definition.get("savedJson"), str):
            definition = json.loads(definition["savedJson"])
        starts = [e for e in definition.get("designElements") or [] if e.get("type") == "rootNode"]
        message_name = str((starts[0].get("data") or {}).get("title") or "") if len(starts) == 1 else ""
        if not message_name:
            raise Exception({"code": "WORKFLOW_START_ERROR", "message": "Workflowの開始設定を確認してください。", "details": {}})
        try:
            started = codeengine.send_request("post", "api/workflow/v1/instances/message",
                                             {"messageName": message_name, "modelId": model_id,
                                              "version": version,
                                              "data": {"executor_email": executor_email} if executor_email else {}})
            if not isinstance(started, dict) or not GUID_PATTERN.fullmatch(str(started.get("id") or "")):
                raise ValueError("missing workflow instance id")
        except Exception as error:
            raise Exception({"code": "START_UNCONFIRMED",
                             "message": "開始結果を確認できませんでした。再実行せず「実行状況を確認」で状態を確認してください。",
                             "details": {}}) from error
        return {"ok": True, "instance_id": str(started["id"]), "status": str(started.get("status") or "IN_PROGRESS"),
                "progress_path": f"/workflows/instances/{SUB_WORKFLOW_MODEL_ID}/",
                "model_version": version, "running": True, "already_running": False}

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
        if not GUID_PATTERN.fullmatch(collection_id):
            raise Exception({"code": "INVALID_COLLECTION_ID",
                             "message": "collection_id の形式が正しくありません", "details": {}})
        if not GUID_PATTERN.fullmatch(REPORT_COLLECTION_ID):
            raise Exception({"code": "COLLECTION_NOT_CONFIGURED",
                             "message": "保存先が未設定です。配備設定を確認してください。", "details": {}})
        if collection_id.lower() != REPORT_COLLECTION_ID.lower():
            raise Exception({"code": "COLLECTION_NOT_ALLOWED",
                             "message": "このアプリの保存先以外は指定できません。", "details": {}})
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
                        if name not in ("collection_id", "operation", "report_type", "executor_email")}
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

    return {"validate": _validate, "save": _save, "start": _workflow_start, "status": _workflow_status}


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

        if action not in svc:
            if action:
                raise Exception({"code": "INVALID_OPERATION",
                                 "message": "operation は validate / save / start / status のいずれかを指定してください。",
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
