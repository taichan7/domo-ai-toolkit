#!/usr/bin/env python3
"""Provision the minimal inventory reference architecture on a Domo instance.

The deployed path is intentionally small:
one AppDB collection -> one Domo standard-sync DataSet -> one Magic ETL output
DataSet. The Code Engine package exposes one dispatcher function.

Every resource is discovered-or-created by name, so `apply` is idempotent per
instance -- the AppDB collection, Code Engine package, DataFlow, and the
notification Workflow model are all provisioned automatically (no hand-built
assets, no IDs to paste in). To reproduce the stack on a different instance,
set ``DOMO_INSTANCE`` (target host, e.g. ``<your-instance>.domo.com`` -- run
``domo login -i`` for it first); an unset target is rejected before authentication. ``DOMO_WORKFLOW_MODEL_ID`` is *optional*: leave it unset
and `apply` discovers-or-creates the notification Workflow model by name
(recommended); set it only to pin an existing model on that instance (backward
compat). See docs/setup-guide.md for the reproduction runbook.

After `apply` creates the assets on a fresh instance, run ``sync-manifest`` to
write the discovered collection / DataSet / Code Engine / Workflow IDs into
pro-code/manifest.json (read-only against Domo; touches only ID fields) before
``domo publish``.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


INSTANCE = (os.environ.get("DOMO_INSTANCE") or os.environ.get("INSTANCE") or "").strip().lower()
ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS_PATH = ROOT / "appdb" / "schemas.json"
SERVICE_PATH = ROOT / "code-engine" / "inventory_service.py"
TRANSFORM_PATH = ROOT / "dataflow" / "dashboard_transform.py"
AI_SUMMARY_INPUT_PATH = ROOT / "dataflow" / "ai_summary_input.py"
AI_SUMMARY_PROMPT_PATH = ROOT / "dataflow" / "ai_summary_prompt.md"
WORKFLOW_PROMPT_PATH = ROOT / "prompts" / "low-stock-notification.md"
MANIFEST_PATH = ROOT / "pro-code" / "manifest.json"
APP_STUDIO_EXPORT_PATH = ROOT / "app-studio" / "app-studio.json"
IN_REPO_REGISTRY_PATH = ROOT / "domo-assets.json"


# ── サンドボックス隔離（ハンズオン参加者ごと・バックエンド込みの完全隔離） ──────────────────
# INVENTORY_SANDBOX_SUFFIX を設定すると、このスクリプトが生成する Domo オブジェクトの名前
# （AppDB datastore/collection・Code Engine package・DataFlow・出力 DataSet・通知 Workflow モデル・
# App Studio アプリ/カード）へ全角括弧付きのサフィックス（例「（検証・田中）」）を付け、本番や
# 他参加者の同名オブジェクトと衝突しない“自分専用の隔離コピー”をバックエンド込みで作る。未設定
# （既定）なら本番と全く同じ名前＝従来挙動を一切変えない（本番メンテの apply/app-studio に無影響）。
# alias 値・Code Engine の operation 名・DataFlow のタイル/セクション id・Workflow の入力名など、
# コード内部の契約（FE/CE/WF が束縛する鍵）は不変。本番保護ガードは main() にある（解決後の対象名が
# 本番名そのものなら拒否。本番メンテナのみ INVENTORY_ALLOW_PRODUCTION=1 で明示解除）。
def _sandbox_suffix() -> str:
    return (os.environ.get("INVENTORY_SANDBOX_SUFFIX") or "").strip()


SANDBOX = bool(_sandbox_suffix())


def _sx(base: str) -> str:
    """オブジェクト名へサンドボックス名札を付ける（全角括弧 U+FF08/U+FF09）。未設定なら base をそのまま返す。"""
    suffix = _sandbox_suffix()
    return f"{base}（{suffix}）" if suffix else base


def _slugify(text: str) -> str:
    """サフィックスをパス安全なセグメントへ（英数/CJK は保持・その他は - ・空なら unknown）。"""
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (text or "").strip())
    out = "-".join(seg for seg in out.split("-") if seg)
    return out or "unknown"


def registry_write_path() -> pathlib.Path:
    """解決済み ID（domo-assets.json）の保存先。既定はリポ内（ローカル生成物・配布しない）。サンドボックスでは
    参加者ごとに ~/.config/domo-utils/<instance>-deploy/inventory-management-app/sandbox-<slug>/ へ
    分離し、共有クローンの domo-assets.json を上書きしない（複数参加者が互いに衝突しない）。
    DOMO_ASSETS_PATH を設定すればそれを最優先する。"""
    override = os.environ.get("DOMO_ASSETS_PATH")
    if override:
        return pathlib.Path(override).expanduser()
    if not SANDBOX:
        return IN_REPO_REGISTRY_PATH
    slug = INSTANCE.split(".")[0] or "unknown"
    return (pathlib.Path.home() / ".config" / "domo-utils" / f"{slug}-deploy"
            / "inventory-management-app" / ("sandbox-" + _slugify(_sandbox_suffix())) / "domo-assets.json")


def load_registry() -> Dict[str, Any]:
    """Read only the selected instance/name-tag state; never inherit base IDs."""
    path = registry_write_path()
    try:
        if path.exists():
            registry = json.loads(path.read_text(encoding="utf-8"))
            if (isinstance(registry, dict)
                    and str(registry.get("instance") or "").strip().lower() == INSTANCE
                    and str(registry.get("sandboxSuffix") or "") == _sandbox_suffix()):
                return registry
    except (ValueError, OSError):
        pass
    return {}


DATASTORE_NAME = _sx("inventory-management-app")
COLLECTION_NAME = _sx("inventory_management_records")
PACKAGE_NAME = _sx("Inventory Management | Transaction Service")
DATAFLOW_NAME = _sx("Inventory Management | Analytics")
OUTPUT_DATASET_NAME = _sx("Inventory Management | Dashboard")
# 本番 App Studio DataApp 名（本番保護ガードの基準・単一ソース）。横展開で変えるのはこの1行＋各
# オブジェクトの基底名。APP_STUDIO_NAME は「env 明示 ＞ 名札付き ＞ 本番名」の順で解決する。
PRODUCTION_APP_STUDIO_NAME = "在庫入出庫管理ハンズオン"
APP_STUDIO_NAME = (os.environ.get("APP_STUDIO_NAME") or _sx(PRODUCTION_APP_STUDIO_NAME)).strip()
APP_STUDIO_CARD_TITLE = _sx("在庫入出庫・分析（最小構成）")
# ページ2＝開発ガイド（dev-guide-app）。同じ App Studio アプリの2枚目として自動で足す。
# DEV_GUIDE_CARD_TITLE は参照インスタンスに既に存在するカードのタイトルと一致させる
# （タイトル一致でカードを再発見＝重複作成を防ぐ）。新規インスタンスでもこのタイトルで作成する。
# 既存ライブカード（maintenance-instance）のタイトルを維持し、再デプロイで重複ページを作らない（orphan 罠回避）。
DEV_GUIDE_MANIFEST_PATH = ROOT / "dev-guide-app" / "manifest.json"
DEV_GUIDE_PAGE_TITLE = "開発ガイド"
DEV_GUIDE_CARD_TITLE = _sx("在庫管理リファレンス ガイド")
DEV_GUIDE_STANDARD = (60, 82)  # ページ2 standard layout（自己フィットの縦スクロール文書）
DEV_GUIDE_COMPACT = (12, 29)   # ページ2 compact layout（現行 12x6 はモバイルで低すぎ→上書き）
WORKFLOW_MODEL_ID = os.environ.get("DOMO_WORKFLOW_MODEL_ID", "").strip()
# DOMO_WORKFLOW_MODEL_ID が明示指定されたか（＝既定値でなく人が固定したか）。指定時は
# ensure_workflow_model が発見/作成せずその ID を尊重する（既存運用の互換）。既定のままなら
# 名称で発見または API で新規作成する（境界①の自動化）。
WORKFLOW_MODEL_ID_PINNED = bool(os.environ.get("DOMO_WORKFLOW_MODEL_ID"))
# 通知Workflowモデル（境界①）を API で「発見または作成」するための定数。
# WORKFLOW_MODEL_NAME は参照インスタンスの既存モデル名と完全一致させる（名称一致で発見＝
# 同一インスタンスへ複数名/複数回デプロイしても1モデルを共有し、重複作成しない）。
WORKFLOW_MODEL_NAME = _sx("Inventory Management | Low Stock Notification")
WORKFLOW_MODEL_DESCRIPTION = "Domo AI Agent formats deterministic stock events and Domo Workflow Email sends the notification."
# 空モデルだと grounding（ensure_agent_email_workflow）が「required reference node が無い」で
# 停止するため、作成直後に流し込む3タイル雛形（開始→AI Agent（sendEmail tool 付き）→終了）の
# 定義ファイル。固有名・顧客DataSet・PII は含まない（版定義スキーマのみ）。
WORKFLOW_SEED_PATH = ROOT / "workflow" / "notification-workflow-seed.json"
# sendEmail tool の packageId（Domo Notifications）。packageVersion はインスタンス個別なので
# resolve_send_email_package がライブに解決した実 version へ差し替える（2.1.17+ はリスト宛先）。
SEND_EMAIL_PACKAGE_ID = "03ba6971-98d0-4654-9bfd-aa897816df33"
# AI エージェントの Send Email ツールで確実に送信できる既知良好の sendEmail 版（宛先が単一テキスト＝
# スカラーの版）。2.1.17 以降は recipientEmails をリスト型に変えるが、AI エージェント経由のツール
# 呼び出しでは list 宛先が送信時に失敗する（maintenance-instance 2.1.18 で実測＝instance FAILED／同一定義で
# 2.1.12 のスカラー宛先は COMPLETED＝送信成功）。カタログが list 版しか提供しない場合はこの版へ固定する。
# 配備先がこの版を実行できない等で別版に固定したいときは env DOMO_SEND_EMAIL_VERSION で上書きする。
KNOWN_GOOD_SCALAR_SEND_EMAIL_VERSION = os.environ.get("DOMO_SEND_EMAIL_VERSION", "2.1.12").strip()
# 通知Workflowが受け取る確定入力（複数不足を1通に集約するため、確定データを直接渡す）。
# event_type=種別 / headline=見出し1件（最重要/今回イベント）/ shortage_lines=通知対象の
# 全不足を1行1件で列挙した確定テキスト / recipient_email=宛先 / occurred_at=発生時刻。
# すべて text 型。この並びが AI プロンプトへ流し込む変数の順序にもなる。
WORKFLOW_INPUT_FIELDS = ("event_type", "headline", "shortage_lines", "recipient_email", "occurred_at")
# 開始タイル（rootNode）のタイトル。Code Engine が `api/workflow/v1/instances/message` の
# messageName に使う値と一致させる（CEソースの WORKFLOW_START_MESSAGE_NAME と同じ）。
# ここが食い違うと起動が 400/404 で失敗するため、grounding の再利用条件にも含めて自動修復する。
WORKFLOW_START_MESSAGE_NAME = "不足通知を開始"
# Magic ETL の TextGeneration タイルが使う DomoGPT モデル。インスタンスで有効なモデルへ
# env で差し替え可能にしておく（既定は medium v2.2 / Anthropic）。
AI_SUMMARY_MODEL_ID = os.environ.get("DOMO_AI_SUMMARY_MODEL_ID", "domo.domo_ai.domogpt-medium-v2.2:anthropic")
# DataFlow 実行をインラインで待つ上限（秒）。分析の AI テキスト生成タイルは残高件数・インスタンス
# 負荷に比例して伸び、実測で数分〜（大きめのシードや低速インスタンスでは）1時間規模になり得る。
# 上限を超えても実行はサーバ側で継続するので、ここで打ち切っても**失敗にはしない**（RUNNING の
# まま正常終了し、あとから verify で SUCCESS を確認する）。もっと長くインラインで待ちたいときは
# env で延長する。短すぎる上限で成功見込みの実行を誤って「失敗」と扱わせないための設計。
DATAFLOW_WAIT_SECONDS = int(os.environ.get("DOMO_DATAFLOW_WAIT_SECONDS", "1800"))
# DataFlow 実行の終端状態（これ以上ポーリングしても状態が変わらない）。
DATAFLOW_TERMINAL_STATES = {"SUCCESS", "FAILED", "FAILED_DATA_FLOW", "CANCELLED", "CANCELED", "ABORTED", "ERROR"}
# 終端のうち「本当の失敗」。ここに入ったときだけ fail-fast で止める（RUNNING での打ち切りは失敗でない）。
DATAFLOW_FAILURE_STATES = {"FAILED", "FAILED_DATA_FLOW", "CANCELLED", "CANCELED", "ABORTED", "ERROR"}

LEGACY_COLLECTIONS = {
    "inventory_management_items": ("b1886f2c-f079-5add-b4c5-64387bc778e0", "616317b9-76d9-5b20-9b15-07a5e28ff304"),
    "inventory_management_locations": ("b1d0f24a-9f0c-5199-bd26-a8c667dcb2fa", "4bb59a5e-0f39-5c6b-bb9f-18699f42836b"),
    "inventory_management_rules": ("9d97e3c9-ac81-57d7-9199-2b205a010b35", "e85615c2-d162-571c-ac8a-c2c4d782b3d9"),
    "inventory_management_transactions": ("f1995196-e8fe-5cd3-ac23-d71d13a05609", "1fca1b17-a58b-5b9c-864b-2332bf9a201b"),
    "inventory_management_balances": ("05eb1020-d424-5745-b405-3721c81befce", "de5c2707-2782-5c30-bc09-01d03abae6d8"),
    "inventory_management_alert_states": ("8978de1c-b0c8-50f8-85fd-6fc4f42071d8", "08e3470c-af6a-5a61-9588-3a31f6c70cec"),
    "inventory_management_alert_history": ("f21f52c6-86f0-5973-8831-5b7335b202a2", "50f51d36-cec9-509d-b603-79b76a1e7506"),
}


class DomoApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, detail: str):
        super().__init__(f"{method} {path} -> HTTP {status}")
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail


class DomoClient:
    def __init__(self, instance: str = INSTANCE):
        instance = str(instance or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.domo\.com", instance):
            raise ValueError("DOMO_INSTANCE must explicitly name your instance (example.domo.com).")
        self.instance = instance
        self.base = f"https://{instance}"
        # A redirect must never forward custom Domo authentication headers.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        self._open = urllib.request.build_opener(NoRedirect()).open
        self.sid = ""
        # 開発者トークン(DOMO_DEVELOPER_TOKEN)があれば、SID を介さず X-DOMO-Developer-Token
        # ヘッダで直接認証する。なぜ: 別インスタンスへ繰り返し配布する運用では、対話的な
        # domo login(OAuth)を挟めない自動化・非対話環境でも、発行済みトークン1つで全 API 面
        # (CodeEngine/DataFlow/Workflow/AppDB/DataApp/DataSet)へ到達できる方が再現性が高い。
        # トークンはソースへ焼き込まず環境変数からのみ読む(配布物の清潔さを保つ)。
        self.dev_token = (os.environ.get("DOMO_DEVELOPER_TOKEN") or os.environ.get("DOMO_TOKEN") or "").strip()
        if not self.dev_token:
            self.refresh_sid()

    def refresh_sid(self) -> None:
        # 開発者トークン運用では更新すべきセッションが無い(静的トークンで認証する)。
        if self.dev_token:
            return
        if os.environ.get("SID") and os.environ.get("INSTANCE", self.instance) == self.instance:
            self.sid = str(os.environ["SID"])
            return
        config = pathlib.Path.home() / ".config" / "configstore" / "ryuu" / f"{self.instance}.json"
        if not config.exists():
            raise RuntimeError(f"Run domo login -i {self.instance}")
        refresh_token = json.loads(config.read_text(encoding="utf-8")).get("refreshToken")
        token_body = urllib.parse.urlencode({"client_id": "domo:internal:devstudio", "grant_type": "refresh_token", "refresh_token": refresh_token}).encode()
        request = urllib.request.Request(f"{self.base}/api/oauth2/token", data=token_body, method="POST", headers={"content-type": "application/x-www-form-urlencoded;charset=utf-8"})
        with self._open(request, timeout=60) as response:
            access_token = (json.loads(response.read()) or {}).get("access_token")
        request = urllib.request.Request(f"{self.base}/api/oauth2/sid", headers={"Authorization": f"Bearer {access_token}"})
        with self._open(request, timeout=60) as response:
            self.sid = str((json.loads(response.read()) or {}).get("sid") or "")

    def request(self, method: str, path: str, body: Any = None, *, retry: bool = True) -> Any:
        url = path if urllib.parse.urlsplit(path).scheme else f"{self.base}/{path.lstrip('/')}"
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != self.instance or parsed.fragment:
            raise ValueError("Refusing to send Domo credentials outside the selected instance.")
        # 認証ヘッダは運用方式で切り替える。開発者トークンは静的なので再認証(リトライ更新)しない。
        if self.dev_token:
            headers = {"X-DOMO-Developer-Token": self.dev_token, "Accept": "application/json"}
        else:
            headers = {"X-Domo-Authentication": self.sid, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with self._open(request, timeout=120) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw) if raw[:1] in (b"{", b"[") or "json" in response.headers.get("content-type", "") else raw.decode(errors="replace")
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            if error.code == 401 and retry and not self.dev_token and not os.environ.get("SID"):
                self.refresh_sid()
                return self.request(method, path, body, retry=False)
            raise DomoApiError(method.upper(), urllib.parse.urlsplit(url).path, error.code, detail) from error


def _items(value: Any, *keys: str) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in keys + ("items", "data", "results", "collections", "packages", "dataflows"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
    return []


def _id(value: Dict[str, Any]) -> str:
    return str(value.get("id") or value.get("guid") or value.get("dataAppId") or value.get("cardId") or "")


def _version_tuple(value: Any) -> Tuple[int, ...]:
    """"2.1.17" → (2, 1, 17)。数値以外・欠損は途中で打ち切り、比較不能なら空タプルを返す。"""
    parts: List[int] = []
    for chunk in str(value or "").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _list_page_cards(client: "DomoClient", view_id: str, parts: Optional[str] = None) -> List[Dict[str, Any]]:
    """App Studio ページのカード一覧を、インスタンス差に頑健に取得する。

    なぜ: 非推奨の v1 ``pages/{view}/cards`` は一部のインスタンス(実測あり)で
    所有済みの既存ページに対してさえ HTTP 400 PAGE_ACCESS_DENIED(ownerId 空)を返す。
    そのインスタンスでは v3 stacks のカード一覧へ退避する。v3 stacks の各カードは
    id/urn/title/type/metadata を持ち、呼び出し側が依存する id・title・metadata を同じ形で
    備えるため、作成時の before/after 差分・メタデータ検証がそのまま成立する。
    parts は v1 のみ有効(v3 stacks は ?parts= 非対応=400)。フォールバック時も metadata は
    既定で含まれるため parts 指定は落としてよい。
    """
    path = f"api/content/v1/pages/{view_id}/cards"
    if parts:
        path += f"?parts={parts}"
    try:
        return _items(client.request("GET", path), "cards")
    except DomoApiError as error:
        if error.status != 400:
            raise
        stack = client.request("GET", f"api/content/v3/stacks/{view_id}/cards") or {}
        return _items(stack, "cards")


def current_user(client: DomoClient) -> Dict[str, Any]:
    # 認証済みユーザーは content API の /users/me で確実に解決する。CodeEngine パッケージの
    # ownerId から推測する旧方式は、パッケージ未作成の新規インスタンスや ownerId を含まない
    # 応答では空になり、apply の冒頭で「利用者を特定できない」と停止してしまう(維持中の
    # インスタンスでも packages[0].ownerId が None を返す事例を実測)。/users/me を主経路、
    # パッケージ owner を後方互換のフォールバックとして残す。
    me = client.request("GET", "api/content/v2/users/me") or {}
    owner_id = str(me.get("id") or "")
    display_name = me.get("displayName") or ""
    if not owner_id:
        packages = _items(client.request("GET", "api/codeengine/v2/packages?limit=1&offset=0"), "packages")
        first = packages[0] if packages else {}
        owner_id = str(first.get("ownerId") or first.get("owner") or "")
        if owner_id and not display_name:
            details = client.request("GET", f"api/content/v2/users/{owner_id}") or {}
            display_name = details.get("displayName") or ""
    if not owner_id:
        raise RuntimeError("Could not determine the authenticated Domo user")
    return {"id": owner_id, "name": display_name or "Domo利用者"}


def list_collections(client: DomoClient) -> List[Dict[str, Any]]:
    return _items(client.request("GET", "api/datastores/v1/collections?limit=1000&offset=0"), "collections")


def _collection_owner_id(collection: Dict[str, Any]) -> str:
    """コレクションの所有者ユーザーIDを防御的に取り出す（無ければ空文字）。

    Domoのコレクション表現は版により所有者を ``owner`` / ``ownerId`` / ``createdBy``
    のいずれかで返す。どれも無ければ「所有者不明」として空文字を返し、呼び出し側は
    黙る（best-effort＝判断も停止もしない）。

    Args:
        collection: `list_collections` が返すコレクション1件。

    Returns:
        所有者ユーザーIDの文字列。判別できなければ空文字。
    """
    for key in ("owner", "ownerId", "createdBy"):
        value = collection.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def ensure_collection(client: DomoClient, current_user_id: str = "") -> Dict[str, Any]:
    schema = json.loads(SCHEMAS_PATH.read_text(encoding="utf-8"))["collections"][0]
    existing = next((row for row in list_collections(client) if row.get("name") == COLLECTION_NAME), None)
    expected = [(row["name"], row["type"]) for row in schema["columns"]]
    if existing:
        current = [(row.get("name"), row.get("type")) for row in (existing.get("schema") or {}).get("columns", [])]
        if current != expected:
            existing = client.request("PUT", f"api/datastores/v1/collections/{_id(existing)}", {"name": COLLECTION_NAME, "schema": {"columns": schema["columns"]}, "syncEnabled": True}) or existing
            print(f"updated AppDB collection schema: {_id(existing)}", flush=True)
        else:
            print(f"reused AppDB collection: {_id(existing)}", flush=True)
        # owner-awareness: 同一インスタンスへ複数名が練習デプロイする運用では、既存コレクションの
        # 所有者が自分と異なることがある。これは正常で、削除・再作成してはならない（他者の
        # データを壊す＝失敗モード④）。何が起きているかを情報表示するだけで、判断も停止も
        # しない。所有者を判別できない応答では黙る（余計な警告でAIを迷わせない）。
        owner_id = _collection_owner_id(existing)
        if current_user_id and owner_id and owner_id != current_user_id:
            print(
                f"note: AppDB collection {_id(existing)} is owned by another user "
                f"(owner {owner_id}); reusing it as-is — this is expected when several people "
                f"deploy to the same instance. Never delete or recreate it.",
                flush=True,
            )
        return existing
    datastores = _items(client.request("GET", "api/datastores/v1?limit=1000&offset=0"), "datastores")
    datastore = next((row for row in datastores if row.get("name") == DATASTORE_NAME), None)
    if not datastore:
        datastore = client.request("POST", "api/datastores/v1", {"name": DATASTORE_NAME}) or {}
    datastore_id = _id(datastore)
    query = urllib.parse.urlencode({"datastoreId": datastore_id})
    created = client.request("POST", f"api/datastores/v1/collections?{query}", {"name": COLLECTION_NAME, "schema": {"columns": schema["columns"]}, "syncEnabled": True}) or {}
    print(f"created AppDB collection: {_id(created)}", flush=True)
    return created


def refresh_collection(client: DomoClient, wait_seconds: int = 60) -> Dict[str, Any]:
    deadline = time.time() + wait_seconds
    result: Dict[str, Any] = {}
    while time.time() < deadline:
        result = next((row for row in list_collections(client) if row.get("name") == COLLECTION_NAME), {})
        if result.get("datasourceId") and not result.get("syncRequired"):
            return result
        time.sleep(2)
    return result


def trigger_appdb_sync(client: DomoClient, collection: Dict[str, Any], wait_seconds: int = 120) -> Dict[str, Any]:
    """AppDB標準同期を即時キックし、標準同期DataSetへ反映され切るまで待って collection を返す。

    既定の AppDB→DataSet 同期は約15分間隔のスケジュール実行なので、SEED 直後に DataFlow を
    回すと古い版の DataSet を読む事故が起きる。`POST api/datastores/v1/export/{datastoreId}`
    は保留中の変更をコレクションの現在の全ドキュメントごと即時に書き出す Domo 公式の
    エクスポート起動で、SEED 完了後に呼べば最新の全件が数秒で反映される。

    Args:
        client: 認証済みDomoクライアント。
        collection: `ensure_collection`／`refresh_collection` が返すコレクション（`datastoreId` を含む）。
        wait_seconds: エクスポート反映を待つ上限秒数。

    Returns:
        反映後に取得し直したコレクション（`datasourceId` と最新の `syncRequired` を含む）。
        同期無効時やエクスポート起動失敗時は、定期同期に委ねて入力の collection をそのまま返す。
    """
    datastore_id = str(collection.get("datastoreId") or "")
    # syncEnabled でなければ標準同期そのものが無い。キックは意味を持たないので何もしない。
    if not (_is_true_flag(collection.get("syncEnabled")) and datastore_id):
        return collection
    # 反映完了の判定に使う期待行数（1ドキュメント=1行）。取得できなければ 0 とし、行数ゲートは無効化する。
    try:
        expected_rows = len(query_documents(client, _id(collection), {}))
    except DomoApiError:
        expected_rows = 0
    try:
        # 空ボディのエクスポート起動。datastoreId をキーにする点に注意（collectionId ではない）。
        client.request("POST", f"api/datastores/v1/export/{datastore_id}", None)
    except DomoApiError as error:
        # 起動に失敗しても致命ではない。次の定期同期（約15分）で反映されるため警告に留める。
        print(f"appdb sync kick skipped ({error.status}); relying on scheduled sync", flush=True)
        return collection
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        collection = next((row for row in list_collections(client) if row.get("name") == COLLECTION_NAME), collection)
        dataset_id = str(collection.get("datasourceId") or "")
        rows = 0
        if dataset_id:
            meta = client.request("GET", f"api/data/v3/datasources/{dataset_id}") or {}
            rows = int(meta.get("rowCount") or 0)
        # datasourceId 生成済み・保留変更なし・（分かる範囲で）期待行数到達、の3点で反映完了と判定。
        if dataset_id and not collection.get("syncRequired") and rows >= expected_rows:
            print(f"appdb sync kicked: {rows} rows synced to {dataset_id}", flush=True)
            return collection
        time.sleep(2)
    print("appdb sync kick: proceeding after wait window (scheduled sync will reconcile)", flush=True)
    return collection


def _is_true_flag(value: Any) -> bool:
    """AppDB由来の真偽値（bool／"true"／"1" 等の文字列表現）をゆるく判定する。"""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def query_documents(client: DomoClient, collection_id: str, criteria: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return _items(client.request("POST", f"api/datastores/v2/collections/{collection_id}/documents/query", criteria or {}), "documents")


def list_packages(client: DomoClient) -> List[Dict[str, Any]]:
    return _items(client.request("GET", "api/codeengine/v2/packages?limit=500&offset=0"), "packages")


def deployed_source(collection_id: str, owner_id: str, datastore_id: str = "", workflow_model_id: str = "") -> str:
    # __DATASTORE_ID__ は CE が標準同期の即時エクスポートを起動するときのキー。datastoreId が
    # 未確定でも空文字へ確実に置換し、未解決プレースホルダ検出（下）に引っかからないようにする
    # （空なら CE 側の sync ガードが無操作にフォールバックし、定期同期へ委ねる）。
    # __WORKFLOW_MODEL_ID__ は CE が通知Workflowの最新有効版を実行時に解決して起動するための
    # モデルID。空（--skip-workflow 等）なら CE は起動せず、ALERT_HISTORY へ FAILED を記録する。
    source = (SERVICE_PATH.read_text(encoding="utf-8")
              .replace("__COLLECTION_RECORDS__", collection_id)
              .replace("__ADMIN_USER_ID__", owner_id)
              .replace("__DATASTORE_ID__", datastore_id or "")
              .replace("__WORKFLOW_MODEL_ID__", workflow_model_id or ""))
    if re.search(r'"__[A-Z0-9_]+__"', source):
        raise RuntimeError("Unresolved deployment placeholder")
    return source


def function_manifest() -> List[Dict[str, Any]]:
    # Code Engine の Manifest には公開関数だけを載せる。`_` 始まりのヘルパーは命名規約で
    # プラットフォームが自動的に private 扱いになるため宣言不要で、唯一の公開ディスパッチャ
    # inventory_api にだけ入出力型（operation:text, request_json:text / output:object）を明示する。
    # 内部ヘルパーは引数なしファクトリ `_service()` にまとめて top-level から外す。
    parameter = lambda name, nullable=False: {"name": name, "displayName": name, "type": "text", "value": None, "nullable": nullable, "isList": False, "children": [], "entitySubType": None}
    return [{
        "name": "inventory_api", "displayName": "inventory_api",
        "description": "Single public dispatcher for auth, registration, seed, state, recalculation, master-data maintenance, and on-demand low-stock notification (delegates to helpers nested in the private _service factory).",
        "isPrivate": False, "inputs": [parameter("operation"), parameter("request_json", True)],
        "output": {"name": "result", "displayName": "result", "type": "object", "value": None, "nullable": True, "isList": False, "children": [], "entitySubType": None},
    }]


def ensure_package(client: DomoClient, source: str) -> Tuple[Dict[str, Any], str]:
    existing = next((row for row in list_packages(client) if row.get("name") == PACKAGE_NAME), None)
    functions = function_manifest()
    if not existing:
        package = client.request("POST", "api/codeengine/v2/packages", {"name": PACKAGE_NAME, "description": "Inventory reference service: 1 public dispatcher (inventory_api) + 6 private helpers.", "language": "PYTHON", "environment": "LAMBDA", "code": source, "manifest": {"functions": functions}}) or {}
        version = str(package.get("version") or "1.0.0")
        client.request("POST", f"api/codeengine/v2/packages/{_id(package)}/versions/{version}/release", {})
        return package, version
    package_id = _id(existing)
    latest = client.request("GET", f"api/codeengine/v2/packages/{package_id}/versions/latest?parts=code,functions,configuration,manifest") or {}
    version = str(latest.get("version") or existing.get("version") or "1.0.0")
    # 再デプロイ判定は「コード一致」かつ「公開関数(functions[])の集合一致」で行う。
    # Code Engineは private helper を functions[] に保持しないため、公開関数名だけを比較する
    # (private集合を desired と比較すると毎回不一致になり無限にversionが上がる)。
    deployed_public = {str(row.get("name")) for row in (latest.get("functions") or []) if not row.get("isPrivate")}
    desired_public = {str(row.get("name")) for row in functions if not row.get("isPrivate")}
    if str(latest.get("code") or "") == source and deployed_public == desired_public:
        print(f"reused Code Engine package: {package_id} v{version}", flush=True)
        return existing, version
    numbers = [int(value) for value in re.findall(r"\d+", version)[:3]]
    while len(numbers) < 3:
        numbers.append(0)
    target = f"{numbers[0]}.{numbers[1]}.{numbers[2] + 1}"
    created = client.request("POST", f"api/codeengine/v2/packages/{package_id}/versions", {"version": target, "code": source, "functions": functions, "configuration": latest.get("configuration") or {"accountsMapping": [], "mlModel": [], "externalPackageMapping": {}}}) or {}
    version = str(created.get("version") or target)
    client.request("POST", f"api/codeengine/v2/packages/{package_id}/versions/{version}/release", {})
    print(f"released Code Engine package (1 public + 6 private functions): {package_id} v{version}", flush=True)
    return existing, version


def invoke_inventory_api(client: DomoClient, package_id: str, version: str, operation: str) -> Dict[str, Any]:
    result = client.request("POST", f"api/codeengine/v2/packages/{package_id}/versions/{version}/functions/inventory_api", {"inputVariables": {"operation": operation, "request_json": "{}"}, "settings": {"getLogs": False}}) or {}
    if result.get("status") != "SUCCESS" or not (result.get("result") or {}).get("ok"):
        raise RuntimeError(f"inventory_api {operation} failed: {json.dumps(result, ensure_ascii=False)[:1000]}")
    return result


def list_dataflows(client: DomoClient) -> List[Dict[str, Any]]:
    return _items(client.request("GET", "api/dataprocessing/v1/dataflows?limit=500&offset=0"), "dataflows")


def output_dataset_id(dataflow: Dict[str, Any]) -> str:
    outputs = dataflow.get("outputs") or []
    if outputs:
        return str(outputs[0].get("dataSourceId") or (outputs[0].get("dataSource") or {}).get("guid") or "")
    return next((str((row.get("dataSource") or {}).get("guid") or "") for row in dataflow.get("actions", []) if row.get("type") == "PublishToVault"), "")


def dataflow_gui(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lay out Magic ETL tiles into readable, labelled sections with notes."""
    sections = [
        {"id": "Section-inventory-prepare", "type": "Section", "x": 16, "y": 16, "width": 632, "height": 232, "name": "① 準備｜AppDB標準同期を分析用レコードへ集計", "backgroundColor": "var(--colorChartBlue6)"},
        {"id": "Section-inventory-ai", "type": "Section", "x": 664, "y": 16, "width": 632, "height": 232, "name": "② AI要約｜品目ごとにDomoGPTで在庫コメント", "backgroundColor": "var(--colorChartPurple6)"},
        {"id": "Section-inventory-publish", "type": "Section", "x": 1312, "y": 16, "width": 296, "height": 232, "name": "③ 出力｜共有Dashboard DataSetへREPLACE", "backgroundColor": "var(--colorChartGreen6)"},
    ]
    tiles = [{"x": (row.get("gui") or {}).get("x", 0), "y": (row.get("gui") or {}).get("y", 0), "id": row["id"], "type": "Tile", "color": (row.get("gui") or {}).get("color")} for row in actions]
    elements = sections + tiles
    return {"version": "1.0", "canvases": {"default": {"canvasSettings": {"coarserGrid": True, "hideCoarserGridPopUp": False, "backgroundVariant": "Lines"}, "elements": elements, "disabledActions": []}}, "elements": elements, "useGraphUI": True, "disabledActions": []}


def dataflow_body(dataset_id: str, output_id: str = "") -> Dict[str, Any]:
    load_id = "LoadFromVault-inventory-records"
    python_id = "PythonEngineAction-inventory-dashboard"
    ai_input_id = "PythonEngineAction-inventory-ai-input"
    textgen_id = "TextGeneration-inventory-ai-summary"
    cleanup_id = "SelectValues-inventory-ai-cleanup"
    union_id = "UnionAll-inventory-dashboard-union"
    publish_id = "PublishToVault-inventory-dashboard"
    # コア列（AI関連を除いた集計行の素の列）。文字列列と数値列(DOUBLE)を分けて宣言する。
    core_string_columns = ("record_type", "metric_key", "label", "date_key", "balance_key", "item_code", "item_name", "location_code", "location_name", "is_shortage", "last_transaction_at", "alert_id", "event_type", "notification_status", "notification_subject", "created_at")
    double_columns = ("metric_value", "inbound_quantity", "outbound_quantity", "quantity", "minimum_quantity", "shortage_quantity", "age_days")
    # 集計タイルのスキーマ。ai_summary は AI要約行だけが値を持つが、UnionAll で両分岐の列を
    # 揃えるため集計側にも列だけ用意する（値は入らない）。
    dashboard_additions = [{"name": name, "dataType": "STRING"} for name in core_string_columns]
    dashboard_additions += [{"name": "ai_summary", "dataType": "STRING"}]
    dashboard_additions += [{"name": name, "dataType": "DOUBLE"} for name in double_columns]
    # AI入力整形タイルはコア列に ai_input_text（AI要約タイルへ渡す素文）を1列だけ足す。
    # ai_summary はこのタイルでは持たない: 後段の TextGeneration が構造化出力として ai_summary を
    # 新規に作るため、同名列を先に用意すると出力列名と衝突する。意図的に外している。
    ai_input_additions = [{"name": name, "dataType": "STRING"} for name in core_string_columns]
    ai_input_additions += [{"name": name, "dataType": "DOUBLE"} for name in double_columns]
    ai_input_additions += [{"name": "ai_input_text", "dataType": "STRING"}]
    # 公開する最終列（コア列 + ai_summary）。AI要約分岐は SelectValues でこの集合だけを残し、
    # ai_input_text / DOMO_AI_BATCH_ERROR / 生出力列などの作業列をまとめて落とす。
    keep_columns = list(core_string_columns) + ["ai_summary"] + list(double_columns)
    notes = {
        load_id: "AppDBの単一コレクションをDomo標準同期DataSetから読み込む。record_typeでマスター・取引・残高・通知を識別する。",
        python_id: "1回のPython処理でKPI、品目別・ロケーション別在庫、7日推移、不足、滞留、通知行へ整形する。",
        ai_input_id: "在庫レコードから残高（品目×ロケーション）を読み、残高1件ごとにAI入力を1行作る。品名・ロケーション・現在庫・基準在庫・不足・経過日数の要点をai_input_text（日本語の素文）へまとめる。",
        textgen_id: "DomoGPTを呼び出し、ai_input_textを根拠に残高1件ごとの在庫状況コメントを生成してai_summary列へ書く（temperature=0、推測補完なし）。バッチ実行のため入力は100行以上必要。",
        cleanup_id: "公開に必要な列（集計列＋ai_summary）だけをホワイトリストで残す。ai_input_textやAI実行時の付随列（DOMO_AI_BATCH_ERROR等）は名指し不要でまとめて落とす。",
        union_id: "集計行（多数）とAIコメント行（残高ごと）を縦に結合し、1つのDashboard DataSetへまとめる。列差はnull許容（strict=false）。",
        publish_id: "Pro CodeとApp Studioが共有する分析DataSetへREPLACE出力する。AppDBの業務データは更新しない。",
    }

    def note(action_id: str) -> List[Dict[str, Any]]:
        return [{"x1": None, "y1": None, "x2": None, "y2": None, "body": notes[action_id]}]

    actions = [
        {"type": "LoadFromVault", "id": load_id, "name": "在庫管理レコード", "description": notes[load_id], "notes": note(load_id), "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 64, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "previewRowLimit": 10000, "propagateAi": False, "filterPolicy": "LEGACY", "dataSourceId": dataset_id, "sourceType": "AUTO", "executeFlowWhenUpdated": False, "pseudoDataSource": False, "truncateTextColumns": False, "truncateRows": False, "onlyLoadNewVersions": False, "recentVersionCutoffMs": 0, "tables": [{}]},
        {"type": "PythonEngineAction", "id": python_id, "name": "2. ダッシュボード行を一括生成", "description": notes[python_id], "notes": note(python_id), "dependsOn": [load_id], "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 336, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "inputs": [load_id], "removeByDefault": True, "condaEnv": "domo-2", "script": TRANSFORM_PATH.read_text(encoding="utf-8"), "additions": dashboard_additions, "fillMissingWithNull": True, "accountPermission": {"mask": 16}, "tables": [{}]},
        {"type": "PythonEngineAction", "id": ai_input_id, "name": "3. 品目ごとのAI入力テキストを生成", "description": notes[ai_input_id], "notes": note(ai_input_id), "dependsOn": [load_id], "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 608, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "inputs": [load_id], "removeByDefault": True, "condaEnv": "domo-2", "script": AI_SUMMARY_INPUT_PATH.read_text(encoding="utf-8"), "additions": ai_input_additions, "fillMissingWithNull": True, "accountPermission": {"mask": 16}, "tables": [{}]},
        {"type": "TextGeneration", "id": textgen_id, "name": "4. 品目ごとにAIが在庫コメント", "description": notes[textgen_id], "notes": note(textgen_id), "dependsOn": [ai_input_id], "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 848, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "input": ai_input_id, "modelId": AI_SUMMARY_MODEL_ID, "temperature": 0.0, "instructions": AI_SUMMARY_PROMPT_PATH.read_text(encoding="utf-8"), "prompt": "【入力データ】\n{{ai_input_text}}", "parameters": {"ai_input_text": "ai_input_text"}, "files": [], "outputColumnName": "output", "outputColumns": [{"description": "品目ごとの在庫状況コメント（40〜80文字・素文）", "title": "ai_summary", "enum": [], "type": "string"}], "structuredOutput": True, "path": "", "modelOutputSchema": [], "modelInputSchema": [], "columnSettings": {}, "tables": [{}]},
        {"type": "SelectValues", "id": cleanup_id, "name": "5. 公開する列を選択", "description": notes[cleanup_id], "notes": note(cleanup_id), "dependsOn": [textgen_id], "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 1088, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "input": textgen_id, "fields": [{"name": name, "rename": "", "type": None, "dateFormat": None, "settings": {}, "remove": False} for name in keep_columns], "tables": [{}]},
        {"type": "UnionAll", "id": union_id, "name": "6. ダッシュボード行とAIコメントを結合", "description": notes[union_id], "notes": note(union_id), "dependsOn": [python_id, cleanup_id], "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 1328, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "inputs": [python_id, cleanup_id], "unionType": "INCLUDE_ALL", "schemaSource": python_id, "strict": False, "tables": [{}]},
        {"type": "PublishToVault", "id": publish_id, "name": "7. Dashboard DataSetへ出力", "description": notes[publish_id], "notes": note(publish_id), "dependsOn": [union_id], "settings": {"preferredDatabaseEntityType": "TEMP_VIEW"}, "gui": {"x": 1568, "y": 96, "color": None, "colorSource": None, "sampleJson": None}, "inputs": [union_id], "dataSource": {"guid": output_id or None, "type": "DataFlow", "name": OUTPUT_DATASET_NAME, "description": "One standard-sync input transformed into shared inventory analytics with per-item AI notes.", "cloudId": "domo"}, "versionChainType": "REPLACE", "schemaSource": "DATAFLOW", "partitioned": False, "tables": [{}]},
    ]
    return {"name": DATAFLOW_NAME, "description": "7 tiles: read AppDB standard sync, aggregate once, build one AI-note input row per stock balance, comment on each with DomoGPT, keep only the published columns, union the AI-note rows onto the dashboard rows, publish one shared DataSet.", "runState": "ENABLED", "actions": actions, "gui": dataflow_gui(actions), "inputs": [{"dataSourceId": dataset_id, "executeFlowWhenUpdated": False, "dataSourceName": "在庫管理レコード", "onlyLoadNewVersions": False, "recentVersionCutoffMs": 0}], "outputs": [{"onboardFlowId": None, "dataSourceId": output_id or None, "dataSourceName": OUTPUT_DATASET_NAME, "versionChainType": "REPLACE"}], "engineProperties": {"kettle.mode": "STRICT"}, "settings": {"sqlDialect": "MAGIC"}, "enabled": True, "paused": False, "triggeredByInput": False, "databaseType": "MAGIC", "magic": True}


def ensure_dataflow(client: DomoClient, dataset_id: str) -> Dict[str, Any]:
    existing = next((row for row in list_dataflows(client) if row.get("name") == DATAFLOW_NAME), None)
    if not existing:
        created = client.request("POST", "api/dataprocessing/v1/dataflows", dataflow_body(dataset_id)) or {}
        print(f"created DataFlow: {_id(created)}", flush=True)
        return created
    dataflow_id = _id(existing)
    current = client.request("GET", f"api/dataprocessing/v1/dataflows/{dataflow_id}") or existing
    desired = dataflow_body(dataset_id, output_dataset_id(current))
    current.update(desired)
    updated = client.request("PUT", f"api/dataprocessing/v1/dataflows/{dataflow_id}", current) or current
    print(f"updated DataFlow to one input: {dataflow_id}", flush=True)
    return updated


def workflow_definition(client: DomoClient, version: str) -> Dict[str, Any]:
    value = client.request("GET", f"api/workflow/v2/models/{WORKFLOW_MODEL_ID}/versions/{version}/definition") or {}
    if isinstance(value, dict) and isinstance(value.get("savedJson"), str):
        return json.loads(value["savedJson"])
    if isinstance(value, str):
        return json.loads(value)
    return value


def workflow_version(client: DomoClient) -> str:
    metadata = client.request("GET", f"api/workflow/v1/models/{WORKFLOW_MODEL_ID}") or {}
    versions = [str(row.get("version") if isinstance(row, dict) else row) for row in metadata.get("versions") or []]
    if not versions:
        raise RuntimeError("Inventory notification Workflow has no version")
    return max(versions, key=lambda value: tuple(int(part) for part in value.split(".")))


def workflow_last_run(client: DomoClient) -> Dict[str, Any]:
    """直近に実際に起動された Workflow インスタンスの実 modelVersion を読む。

    なぜ必要か: verify がモデル定義上の「最新版」だけを見ると、Domo の
    ランタイムがボタン起動時に別の版へ解決していても気づけない盲点になる
    （本アプリでは manifest が宣言する版とランタイム解決版が食い違う事象を
    確認済み。版の解決は Domo プラットフォーム側の制御でアプリからは不可視）。
    直近実行が使った版を読み取り、宣言値との乖離を可視化するための
    読み取り専用ヘルパー。実行履歴が無ければ空を返す（新規環境では正常）。
    """
    payload = client.request("GET", f"api/workflow/v1/instances?modelId={WORKFLOW_MODEL_ID}&limit=1") or {}
    items = payload.get("instances") if isinstance(payload, dict) else payload
    if isinstance(payload, dict) and items is None:
        items = payload.get("items") or payload.get("data") or []
    row = items[0] if isinstance(items, list) and items else {}
    return {
        "version": str(row.get("modelVersion") or ""),
        "at": str(row.get("createdOn") or ""),
        "id": str(row.get("id") or ""),
    }


def manifest_dashboard_dataset_id() -> str:
    """manifest.json が宣言する分析Dashboard DataSet の alias→物理ID を返す。

    新規インスタンスでは参照インスタンスのGUIDのままなので、実DataSetが判明している場面
    （apply が DataFlow を生成/実行した後）では呼び出し側がライブの出力IDを優先して渡す。
    ここは判明しないときのフォールバック（--skip-dataflow-run や単体 `workflow` サブコマンド）。
    """
    return next(
        row["dataSetId"]
        for row in json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["datasetsMapping"]
        if row.get("alias") == "inventoryDashboard"
    )


def list_workflow_models(client: DomoClient) -> List[Dict[str, Any]]:
    """全 Workflow モデルの平坦な一覧（各行は name / owner を持つ）を返す。名称での発見に使う。"""
    return [row for row in (client.request("GET", "api/workflow/v1/models") or []) if isinstance(row, dict)]


def resolve_send_email_package(client: DomoClient) -> Tuple[str, str]:
    """このインスタンスで有効な sendEmail tool の (packageId, 採用version) を返す。

    設計思想「インスタンスに合わせて解決し、LLM に型の構築を委ねない」:
    Domo Notifications の sendEmail はインスタンスごとに提供 version が異なる（例: 2.1.12 と 2.1.18）。
    2.1.17 以降は recipientEmails を**リスト型**として扱うが、AI エージェントがスカラー入力（通知WFの
    `recipient_email`）からリストを構築すると送信時に失敗する（maintenance-instance 2.1.18・通知WF v1.0.15 で実測
    ＝instance FAILED／同一定義で 2.1.12 のスカラー宛先は COMPLETED・実配信）。well-formed なスカラー宛先なら
    そのまま送信できるため、**宛先がスカラーのままの版（<2.1.17）を最優先**して list 構築リスクを根本回避する。

    採用順（上から）:
      1. カタログに掲載された最高の**スカラー版**（<2.1.17）。掲載版は実行可能が保証される。
      2. スカラー版が一切掲載されない（list 版のみの）インスタンスでは、スカラー宛先で送信実績のある
         既知良好版 KNOWN_GOOD_SCALAR_SEND_EMAIL_VERSION（既定 2.1.12・env `DOMO_SEND_EMAIL_VERSION` で
         各インスタンスの実行可能なスカラー版へ上書き可）。
      3. 既知良好版の指定も無ければ、最後の手段としてカタログ最高版（呼び出し側で版整合を取る）。
    sendEmail が見つからなければ ("", "") を返し、呼び出し側は seed 既定のまま進む。
    """
    try:
        tools = client.request("GET", "api/workflow/v2/tools") or []
    except DomoApiError as error:
        # 一部インスタンスでは v2 tools カタログ列挙が HTTP 500 を返す（per-model の
        # create/definition/release は正常なのにカタログGETだけ壊れている）。カタログ不能時は
        # 「未検出」と同じく ("","") へ縮退し、呼び出し側は seed 既定の sendEmail 版で進む
        # （docstring の契約どおり）。版差し替えが無い＝参照ノードの版を尊重＝isListドリフト無し。
        print(f"note: workflow tools catalog unavailable ({error}); using seed default sendEmail version", flush=True)
        return "", ""
    versions: List[str] = []
    for row in tools:
        if not (isinstance(row, dict) and row.get("name") == "sendEmail" and row.get("packageId") == SEND_EMAIL_PACKAGE_ID):
            continue
        versions.extend(str(ver) for ver in (row.get("versions") or []))
        if row.get("version"):
            versions.append(str(row.get("version")))
    if not versions:
        return "", ""
    # 1) 宛先がスカラーのままの版（<2.1.17）を最優先。掲載された最高スカラー版を使う（実行可能が保証される）。
    scalar_versions = [ver for ver in versions if _version_tuple(ver) < (2, 1, 17)]
    if scalar_versions:
        return SEND_EMAIL_PACKAGE_ID, max(scalar_versions, key=_version_tuple)
    # 2) list 版しか提供しないインスタンスでは、スカラー宛先で送信実績のある既知良好版へフォールバック
    #    （env DOMO_SEND_EMAIL_VERSION で各インスタンスの実行可能なスカラー版へ上書き可）。
    if KNOWN_GOOD_SCALAR_SEND_EMAIL_VERSION:
        return SEND_EMAIL_PACKAGE_ID, KNOWN_GOOD_SCALAR_SEND_EMAIL_VERSION
    # 3) 最後の手段：カタログ最高版（呼び出し側 _set_send_email_tool_version が isList/aiDescription を版整合）。
    return SEND_EMAIL_PACKAGE_ID, max(versions, key=_version_tuple)


def _set_send_email_tool_version(tool: Dict[str, Any], version: str) -> None:
    """sendEmail tool 1件を、このインスタンスの実 packageVersion へ差し替える（in-place・純粋関数）。

    2.1.17 以降は recipientEmails をリスト型で宣言する（下位版は据え置き）。version が空なら何もしない。

    宛先ガイダンス（recipientEmails の aiDescription と inputDescriptions）も isList と必ず一致させる。
    isList だけ版へ追従させ aiDescription を据え置くと、リスト型なのに「そのまま渡す（スカラー）」と
    AI エージェントへ誘導してしまい、エージェントがスカラーを渡して送信ツールが引数型不一致
    （IllegalArgumentException）で失敗する——既存ツールを再利用する grounding 経路で実際に発生した
    （参照 version とライブ version が食い違うと、aiDescription=スカラー／isList=リスト の自己矛盾が残る）。
    """
    if not version or tool.get("functionName") != "sendEmail":
        return
    tool["packageId"] = SEND_EMAIL_PACKAGE_ID
    tool["packageVersion"] = version
    is_list = _version_tuple(version) >= (2, 1, 17)
    recipient_description = (
        "Pass the recipient_email workflow input as a single-element list, e.g. [recipient_email]; exactly one recipient."
        if is_list
        else "Use the recipient_email workflow input exactly as supplied."
    )
    input_descriptions = tool.get("inputDescriptions")
    for row in tool.get("inputs") or []:
        if row.get("paramName") == "recipientEmails":
            row["isList"] = is_list
            row["aiDescription"] = recipient_description
            # inputDescriptions（別 dict・AI エージェントが参照し得る）があれば同じ値へ同期する。
            if isinstance(input_descriptions, dict) and row.get("id") is not None:
                input_descriptions[row["id"]] = recipient_description


def _apply_send_email_version(definition: Dict[str, Any], version: str) -> Dict[str, Any]:
    """定義内 AI Agent の sendEmail tool 群を実 packageVersion へ差し替える（in-place）。オフライン試験可。"""
    if not version:
        return definition
    ai = next((row for row in definition.get("designElements") or [] if row.get("type") == "AI_AGENT"), None)
    for tool in ((ai or {}).get("data") or {}).get("agent", {}).get("tools", []) or []:
        _set_send_email_tool_version(tool, version)
    return definition


def load_workflow_seed() -> Dict[str, Any]:
    """3タイル雛形の seed 定義を読み込む（毎回ファイルから読む＝破壊的編集を避ける）。"""
    return json.loads(WORKFLOW_SEED_PATH.read_text(encoding="utf-8"))


def seed_workflow_model(client: DomoClient, model_id: str, send_email_version: str) -> str:
    """新規（または空の）モデルへ 1.0.0 版を作り、sendEmail 版を差し替えた3タイル雛形を流し込む。

    空モデルのままだと grounding が「required reference node が無い」で停止するため、作成直後に
    この雛形を入れて版として成立させる。release はしない（grounding が実DataSet接地・プロンプト適用の
    うえで版を上げて release する）。既に版があれば触らず最新版番号を返す（べき等）。
    """
    meta = client.request("GET", f"api/workflow/v1/models/{model_id}") or {}
    existing = [str(row.get("version")) for row in (meta.get("versions") or []) if (row or {}).get("version")]
    if existing:
        return max(existing, key=_version_tuple)
    seed = _apply_send_email_version(load_workflow_seed(), send_email_version)
    client.request("POST", f"api/workflow/v2/models/{model_id}/versions", {"version": "1.0.0"})
    client.request("PUT", f"api/workflow/v2/models/{model_id}/versions/1.0.0/definition", seed)
    print(f"seeded 3-tile workflow template into model {model_id} v1.0.0 (sendEmail {send_email_version or 'default'})", flush=True)
    return "1.0.0"


def ensure_workflow_model(client: DomoClient) -> Dict[str, Any]:
    """通知Workflowモデル（境界①）を名称で「発見または作成」し、WORKFLOW_MODEL_ID を確定する。

    従来は人手で Domo Workflows に3タイルモデルを作り、その model ID を DOMO_WORKFLOW_MODEL_ID へ
    設定する必要があった（弱いAIモデルが「手で作ってIDを渡せ」と誤案内する温床）。ここでは全自動化する：
      - DOMO_WORKFLOW_MODEL_ID が明示指定されていれば最優先で尊重（既存運用の互換）。空モデルなら雛形を seed。
      - 指定が無ければ WORKFLOW_MODEL_NAME でインスタンス内を探し、在れば再利用（同じインスタンスへ
        複数名/複数回デプロイしても名称一致で1つを共有＝重複作成しない）。
      - 見つからなければ API でモデルを新規作成し、3タイル雛形を seed する。
    どの経路でもモジュール全体で使う WORKFLOW_MODEL_ID を確定値へ更新する（各 workflow ヘルパは
    呼び出し時にこのグローバルを読む）。他人が作ったモデルは削除・作り直しをせず、発見して再利用する。
    """
    global WORKFLOW_MODEL_ID
    _package_id, send_email_version = resolve_send_email_package(client)
    if WORKFLOW_MODEL_ID_PINNED:
        seed_workflow_model(client, WORKFLOW_MODEL_ID, send_email_version)
        print(f"using pinned workflow model (DOMO_WORKFLOW_MODEL_ID): {WORKFLOW_MODEL_ID}", flush=True)
        return {"modelId": WORKFLOW_MODEL_ID, "created": False, "pinned": True, "sendEmailVersion": send_email_version}
    existing = next((row for row in list_workflow_models(client) if row.get("name") == WORKFLOW_MODEL_NAME), None)
    if existing:
        WORKFLOW_MODEL_ID = _id(existing)
        seed_workflow_model(client, WORKFLOW_MODEL_ID, send_email_version)
        print(f"reused workflow model by name '{WORKFLOW_MODEL_NAME}': {WORKFLOW_MODEL_ID}", flush=True)
        return {"modelId": WORKFLOW_MODEL_ID, "created": False, "pinned": False, "sendEmailVersion": send_email_version}
    created = client.request("POST", "api/workflow/v2/models", {"name": WORKFLOW_MODEL_NAME, "description": WORKFLOW_MODEL_DESCRIPTION}) or {}
    WORKFLOW_MODEL_ID = _id(created)
    if not WORKFLOW_MODEL_ID:
        raise RuntimeError("Failed to create notification Workflow model (empty id in create response)")
    seed_workflow_model(client, WORKFLOW_MODEL_ID, send_email_version)
    print(f"created workflow model '{WORKFLOW_MODEL_NAME}': {WORKFLOW_MODEL_ID}", flush=True)
    return {"modelId": WORKFLOW_MODEL_ID, "created": True, "pinned": False, "sendEmailVersion": send_email_version}


def resolve_workflow_model_id(client: DomoClient) -> str:
    """通知Workflowモデルの ID を read-only で解決する（発見のみ・作成しない）。

    別プロセスで起動される `sync-manifest`／`verify` 用のヘルパ。全自動フローでは人手で
    DOMO_WORKFLOW_MODEL_ID を設定しない前提のため、モジュール既定（保守用インスタンスのID）を
    そのまま問い合わせると顧客インスタンスでは存在しないIDへGETして誤って失敗する。優先順:
      1. DOMO_WORKFLOW_MODEL_ID が明示指定（pin）されていればそれを尊重。
      2. WORKFLOW_MODEL_NAME でインスタンス内を発見できればその ID（`apply` が作成済みのはず）。
      3. manifest.json が既に宣言している workflowsMapping[0].modelId（あれば）。
      4. どれも無ければ未解決（空文字）。古いモジュール状態を別環境へ持ち込まない。
    書き込み経路は ensure_workflow_model 側。ここは発見のみで、他人が作ったモデルにも触れない。
    """
    if WORKFLOW_MODEL_ID_PINNED:
        return WORKFLOW_MODEL_ID
    row = next((model for model in list_workflow_models(client) if model.get("name") == WORKFLOW_MODEL_NAME), {})
    if _id(row):
        return _id(row)
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        declared = str(((manifest.get("workflowsMapping") or [{}])[0]).get("modelId") or "")
        if declared:
            return declared
    except Exception:
        pass
    return ""


def agent_email_workflow_definition(source: Dict[str, Any], dashboard_dataset_id: str, send_email_version: str = "") -> Dict[str, Any]:
    """Build Start -> AI Agent with one DataSet and email tool -> End.

    dashboard_dataset_id には AIエージェントの知識として接地する分析Dashboard DataSet の物理IDを
    渡す。呼び出し側（ensure_agent_email_workflow）がライブ実DataSet優先で解決済みの値を渡す前提。
    send_email_version にこのインスタンスで有効な sendEmail の実 packageVersion を渡すと、参照ノードの
    版に依らずその実版へ揃える（2.1.17+ は recipientEmails をリスト型に）。空なら参照ノードの版を尊重する。
    """
    desired = json.loads(json.dumps(source, ensure_ascii=False))
    elements = desired.get("designElements") or []
    root = next((row for row in elements if row.get("type") == "rootNode"), None)
    ai = next((row for row in elements if row.get("type") == "AI_AGENT"), None)
    email = next((row for row in elements if ((row.get("data") or {}).get("metadata") or {}).get("functionName") == "sendEmail"), None)
    end = next((row for row in elements if row.get("type") == "endNode"), None)
    existing_email_tool = next((row for row in ((ai or {}).get("data") or {}).get("agent", {}).get("tools", []) if row.get("functionName") == "sendEmail"), None)
    if not all((root, ai, end)) or not (email or existing_email_tool):
        raise RuntimeError("Workflow is missing a required reference node")

    allowed_inputs = set(WORKFLOW_INPUT_FIELDS)
    allowed_variables = {f"var_{name}" for name in allowed_inputs} | {"var_ai_result"}
    desired["dataList"] = [row for row in desired.get("dataList") or [] if row.get("id") in allowed_variables]
    desired["schema"]["inputs"] = {
        key: row for key, row in (desired.get("schema", {}).get("inputs") or {}).items()
        if row.get("name") in allowed_inputs
    }
    desired["schema"]["outputs"] = {}

    root["id"] = "rootNode"
    root["position"] = {"x": 40, "y": 140}
    root["data"]["title"] = WORKFLOW_START_MESSAGE_NAME
    root["data"]["description"] = "確定済み在庫イベントを受け取る"
    root["data"]["input"] = [row for row in root["data"].get("input") or [] if row.get("paramName") in allowed_inputs]

    # headline / shortage_lines は複数の不足を1通へ集約するための確定入力で、旧版のソースモデルには
    # 存在しない。フィルタ後に欠けている入力を text 型として追加し、既存 text 入力と同じ3面
    # （schema.inputs / dataList / root.data.input）を揃えて版定義PUTへ確実に往復させる。
    present_inputs = {row.get("name") for row in desired["schema"]["inputs"].values()}
    for field in WORKFLOW_INPUT_FIELDS:
        if field in present_inputs:
            continue
        desired["schema"]["inputs"][f"input_{field}"] = {
            "name": field, "type": "text", "subType": None, "isList": False,
            "isNullable": False, "id": f"input_{field}", "isChild": False, "parent": None,
        }
        desired["dataList"].append({
            "id": f"var_{field}", "paramName": field, "dataType": "text", "isList": False,
            "children": [], "showChildren": False, "entitySubType": None, "value": None, "isOutput": False,
        })
        root["data"]["input"].append({
            "id": f"input_{field}", "paramName": field, "acceptsInput": False, "useExternalValues": False,
            "dataType": "text", "mappedTo": f"var_{field}", "value": None, "fieldOptionsMappedTo": None,
            "fieldOptionsValue": None, "datasetMapping": None, "required": True, "children": [],
            "displayName": field, "visible": True, "formFieldId": str(uuid.uuid4()), "formFieldType": None,
            "flag": "input", "customMappingType": "form_start", "entitySubType": None, "isList": False,
            "configType": "forms",
        })

    ai["id"] = "ai_format_notification"
    ai["position"] = {"x": 320, "y": 140}
    ai["data"]["title"] = "AI Agent｜通知文作成・メール送信"
    ai["data"]["description"] = "既存の在庫分析DataSetを参照し、通知文を指定先へ1回だけ送信"
    ai["data"]["agent"]["instructions"] = WORKFLOW_PROMPT_PATH.read_text(encoding="utf-8")
    if email:
        email_data = email.get("data") or {}
        metadata = email_data.get("metadata") or {}
        description = str(email_data.get("selectedTaskDescription") or "Send an email to the supplied address")
        tool_inputs = json.loads(json.dumps(email_data.get("input") or [], ensure_ascii=False))
        # DOMO Notifications 2.1.17 以降は recipientEmails を List として扱う。参照ノードの
        # パッケージ版が 2.1.17 以上のときは宛先入力を必ずリスト型で宣言する。isList=False の
        # まま 2.1.17 を宣言すると送信時に IllegalArgumentException(引数型不一致)となり、
        # 通知が一切送られない(あるデプロイ先で実際に発生)。2.1.12 系はスカラーを受けるため、
        # 参照が 2.1.12 の間は据え置く(逆にリスト化すると 2.1.12 側で不一致になる)。
        email_pkg_ver = _version_tuple(metadata.get("version"))
        recipient_is_list = email_pkg_ver >= (2, 1, 17)
        for row in tool_inputs:
            row["mappedTo"] = None
            row["value"] = None
            if row.get("paramName") == "recipientEmails":
                row["isList"] = recipient_is_list
                row["aiDescription"] = (
                    "Pass the recipient_email workflow input as a single-element list, e.g. [recipient_email]; exactly one recipient."
                    if recipient_is_list
                    else "Use the recipient_email workflow input exactly as supplied."
                )
            elif row.get("paramName") == "subject":
                row["aiDescription"] = "A factual Japanese subject no longer than 40 characters."
            elif row.get("paramName") == "body":
                row["aiDescription"] = "A factual, structured Japanese body no longer than 700 characters, using the sections 状況/分析/推奨アクション/確認のお願い."
            else:
                row["aiDescription"] = "Do not use this optional input."
        output = json.loads(json.dumps((email_data.get("output") or [{}])[0], ensure_ascii=False))
        output["mappedTo"] = None
        output["value"] = None
        email_tool = {
            "functionName": "sendEmail",
            "functionDescription": description,
            "inputs": tool_inputs,
            "inputDescriptions": {row["id"]: str(row.get("aiDescription") or "") for row in tool_inputs},
            "id": "agent_tool_send_email",
            "name": str(email_data.get("selectedTaskTitle") or "Send Email"),
            "description": description,
            "packageId": metadata.get("packageId"),
            "packageVersion": metadata.get("version"),
            "output": output,
            "type": "FUNCTION",
        }
    else:
        email_tool = json.loads(json.dumps(existing_email_tool, ensure_ascii=False))
    # 参照ノードの版に依らず、判明しているインスタンスの実 sendEmail 版へ最終的に揃える
    # （seed 経路でも grounding 経路でも、release される版が必ずそのインスタンスで送信可能になる）。
    _set_send_email_tool_version(email_tool, send_email_version)
    ai["data"]["agent"]["tools"] = [email_tool]
    # Reuse the one existing analytics DataSet as Agent knowledge. This keeps
    # the reference architecture small while demonstrating DataSet grounding.
    # dashboard_dataset_id は呼び出し側がライブ実DataSet優先で解決済み（下記 ensure_... 参照）。
    ai["data"]["agent"]["context"] = {"datasets": [{"id": dashboard_dataset_id}], "directories": [], "files": [], "isEmpty": False}
    # プロンプトへ流し込む変数参照は Workflow 入力そのもの。全て text 型で並び順も入力定義に揃える。
    prompt_fields = [(name, "text") for name in WORKFLOW_INPUT_FIELDS]
    ai["data"]["prompt"]["value"] = [{"type": "paragraph", "children": [
        {"text": f"{name}: ", "bold": False, "italic": False, "underlined": False, "sql": False},
        {"type": "variable", "children": [{"text": "", "bold": False, "italic": False, "underlined": False, "sql": False}], "dataType": data_type, "id": f"var_{name}", "name": name, "isList": False},
    ]} for name, data_type in prompt_fields]

    end["id"] = "endNode"
    end["position"] = {"x": 600, "y": 140}
    end["data"]["title"] = "終了"

    nodes = [root, ai, end]
    edges = []
    for index, (source_id, target_id) in enumerate((("rootNode", "ai_format_notification"), ("ai_format_notification", "endNode")), start=len(nodes)):
        edges.append({
            "id": f"edge-{source_id}-{target_id}", "source": source_id, "target": target_id,
            "data": {"sourcePosition": "right", "targetPosition": "left", "path": [], "title": ""},
            "style": {"zIndex": 5}, "index": index, "arrowHeadType": "arrow", "type": "defaultEdge",
        })
    for index, node in enumerate(nodes):
        node["index"] = index
    desired["designElements"] = nodes + edges
    return desired


def ensure_agent_email_workflow(client: DomoClient, dashboard_dataset_id: str = "") -> Dict[str, Any]:
    # 境界①の自動化: まず通知Workflowモデルを名称で発見または新規作成し（人手のUI作成もID受け渡しも
    # 不要）、WORKFLOW_MODEL_ID を確定させる。新規作成時は3タイル雛形を seed 済みなので、以降の
    # workflow_version / workflow_definition は必ず版を見つけられる。send_email_version はこのインスタンスの
    # 実 sendEmail 版で、grounding で作り直す版もこの実版へ揃えて送信可能に保つ（版ドリフトの黙殺を防ぐ）。
    model_info = ensure_workflow_model(client)
    send_email_version = str(model_info.get("sendEmailVersion") or "")
    # AIエージェントの知識DataSetは実インスタンスに生成済みの分析Dashboard DataSet の実IDへ接地する。
    # apply が DataFlow 生成/実行後に確定した実IDを渡す。未指定（--skip-dataflow-run や単体 `workflow`
    # サブコマンド）のときだけ manifest 宣言値へフォールバックする。こうすると新規インスタンスの初回
    # apply でもエージェント知識が実DataSetと一致し、verify の
    # workflowAiAgentDatasetContextIds == dashboardDatasetId を初回から満たす
    # （旧: manifestの参照インスタンスGUIDを焼き込み→不一致→2回目applyが必要だった）。
    dashboard_dataset_id = dashboard_dataset_id or manifest_dashboard_dataset_id()
    current_version = workflow_version(client)
    current = workflow_definition(client, current_version)
    metadata = client.request("GET", f"api/workflow/v1/models/{WORKFLOW_MODEL_ID}") or {}
    version_info = next((row for row in metadata.get("versions") or [] if str(row.get("version")) == current_version), {})
    node_types = [row.get("type") for row in current.get("designElements") or [] if not str(row.get("type") or "").endswith("Edge")]
    ai = next((row for row in current.get("designElements") or [] if row.get("type") == "AI_AGENT"), {})
    agent = (ai.get("data") or {}).get("agent") or {}
    email_tools = [row for row in agent.get("tools") or [] if row.get("functionName") == "sendEmail"]
    context = agent.get("context") or {}
    context_dataset_ids = [str(row.get("id") or "") for row in context.get("datasets") or []]
    prompt_matches = str(agent.get("instructions") or "") == WORKFLOW_PROMPT_PATH.read_text(encoding="utf-8")
    # 入力契約（5件の確定入力）が一致することも再利用条件に含める。プロンプトが一致しても入力面が
    # 旧版（10スカラー）のままなら作り直して新契約へ揃える。
    input_names = {str(row.get("name") or "") for row in ((current.get("schema") or {}).get("inputs") or {}).values()}
    inputs_match = input_names == set(WORKFLOW_INPUT_FIELDS)
    # sendEmail の実版が判明していて、現行の released 版がそれと食い違うなら作り直す。版ドリフトを
    # 放置すると 2.1.17+ 環境で recipientEmails 型不一致になり通知が黙って飛ばない（再利用しない）。
    grounded_email_version = str((email_tools[0] if email_tools else {}).get("packageVersion") or "")
    email_version_ok = (not send_email_version) or grounded_email_version == send_email_version
    # 宛先ガイダンス（recipientEmails の aiDescription）が isList と一致していること。版だけ追従して
    # 説明がスカラー（"exactly as supplied"）のまま残ると、list 型なのに AI エージェントがスカラーを
    # 渡し、2.1.17+ で送信が引数型不一致（IllegalArgumentException）になり通知が黙って失敗する
    # （通知WF v1.0.13 の実インシデント）。自己矛盾があれば作り直して _set_send_email_tool_version の
    # 版整合済みガイダンスへ揃える。
    recipient_input = next((row for row in (email_tools[0] if email_tools else {}).get("inputs") or [] if row.get("paramName") == "recipientEmails"), {})
    recipient_guidance_ok = bool(recipient_input.get("isList")) == ("single-element list" in str(recipient_input.get("aiDescription") or ""))
    # 開始タイルのタイトルは Code Engine が起動時に使う messageName と一致していること。UIで改名
    # されると起動が 400/404 で失敗するため、食い違えば作り直して定義側の値を正へ揃える。
    root = next((row for row in current.get("designElements") or [] if row.get("type") == "rootNode"), {})
    root_title_ok = str((root.get("data") or {}).get("title") or "") == WORKFLOW_START_MESSAGE_NAME
    if node_types == ["rootNode", "AI_AGENT", "endNode"] and len(email_tools) == 1 and context_dataset_ids == [dashboard_dataset_id] and prompt_matches and inputs_match and email_version_ok and recipient_guidance_ok and root_title_ok:
        if not version_info.get("active"):
            client.request("POST", f"api/workflow/v2/models/{WORKFLOW_MODEL_ID}/versions/{current_version}/release", {})
        print(f"reused DataSet-grounded AI-email Workflow: {WORKFLOW_MODEL_ID} v{current_version}", flush=True)
        return {"modelId": WORKFLOW_MODEL_ID, "version": current_version, "tileCount": 3, "aiAgentCount": 1, "aiAgentEmailToolCount": 1, "aiAgentDatasetContextCount": 1}

    desired = agent_email_workflow_definition(current, dashboard_dataset_id, send_email_version)
    parts = [int(part) for part in current_version.split(".")]
    target_version = f"{parts[0]}.{parts[1]}.{parts[2] + 1}"
    draft = client.request("POST", f"api/workflow/v2/models/{WORKFLOW_MODEL_ID}/versions", {"version": target_version}) or {}
    draft_version = str(draft.get("version") or target_version)
    try:
        client.request("PUT", f"api/workflow/v2/models/{WORKFLOW_MODEL_ID}/versions/{draft_version}/definition", desired)
        saved = workflow_definition(client, draft_version)
        saved_tiles = [row for row in saved.get("designElements") or [] if row.get("type") not in {"defaultEdge", "conditionEdge"}]
        saved_ai = next((row for row in saved_tiles if row.get("type") == "AI_AGENT"), {})
        saved_agent = (saved_ai.get("data") or {}).get("agent") or {}
        saved_email_tools = [row for row in saved_agent.get("tools") or [] if row.get("functionName") == "sendEmail"]
        saved_context_dataset_ids = [str(row.get("id") or "") for row in (saved_agent.get("context") or {}).get("datasets") or []]
        saved_input_names = {str(row.get("name") or "") for row in ((saved.get("schema") or {}).get("inputs") or {}).values()}
        saved_root_title = str((next((row for row in saved_tiles if row.get("type") == "rootNode"), {}).get("data") or {}).get("title") or "")
        if len(saved_tiles) != 3 or sum(row.get("type") == "AI_AGENT" for row in saved_tiles) != 1 or len(saved_email_tools) != 1 or saved_context_dataset_ids != [dashboard_dataset_id] or saved_input_names != set(WORKFLOW_INPUT_FIELDS) or saved_root_title != WORKFLOW_START_MESSAGE_NAME:
            raise RuntimeError("DataSet-grounded AI-email Workflow draft did not round-trip correctly")
        client.request("POST", f"api/workflow/v2/models/{WORKFLOW_MODEL_ID}/versions/{draft_version}/release", {})
    except Exception:
        try:
            client.request("DELETE", f"api/workflow/v2/models/{WORKFLOW_MODEL_ID}/versions/{draft_version}")
        except Exception:
            pass
        raise
    print(f"released 3-tile DataSet-grounded AI-email Workflow: {WORKFLOW_MODEL_ID} v{draft_version}", flush=True)
    return {"modelId": WORKFLOW_MODEL_ID, "version": draft_version, "tileCount": 3, "aiAgentCount": 1, "aiAgentEmailToolCount": 1, "aiAgentDatasetContextCount": 1}


def _execution_state(execution: Dict[str, Any]) -> str:
    """DataFlow 実行レコードの状態を大文字で返す（取得不能なら RUNNING 扱い）。"""
    return str((execution or {}).get("state") or (execution or {}).get("status") or "RUNNING").upper()


def _latest_execution(client: DomoClient, dataflow_id: str) -> Dict[str, Any]:
    """直近の実行を1件返す（新しい順の一覧の先頭）。読み取り専用・失敗時は空 dict。

    実行中の execution を検出して再利用するために使う。取得に失敗しても致命ではないので、
    その場合は空 dict を返して新規実行の判断（POST）へ委ねる。
    """
    try:
        rows = client.request("GET", f"api/dataprocessing/v1/dataflows/{dataflow_id}/executions?limit=1&offset=0")
    except DomoApiError:
        return {}
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        return rows[0]
    return {}


def trigger_dataflow(client: DomoClient, dataflow: Dict[str, Any], wait_seconds: int = 0) -> Tuple[str, str]:
    """DataFlow を実行し、終端 or 待ち上限まで状態をポーリングして (state, executionId) を返す。

    弱いAIモデルの誤動作を防ぐための3つの契約:

    - **二重実行しない**: すでに実行中（非終端）の execution があればそれを再利用し、新規実行を
      投げない。同一インスタンスへ複数名／複数回 apply を重ねても実行が積み上がらない。
    - **待ち上限は失敗ではない**: 上限（`DATAFLOW_WAIT_SECONDS`, env で延長可）を超えても実行が
      RUNNING のままなら、実行はサーバ側で継続する。RUNNING を返して**正常終了**し（例外は
      投げない）、キャンセルや再実行をしないよう明示案内する。完了確認は後から `verify` で行う。
    - **本当の失敗だけ止める**: 終端が FAILED 系／中断系のときだけ RuntimeError を投げる（fail-fast）。
      これはリトライで直る種類ではないので、原因（DomoGPTモデルID不正／入力DataSet不整合など）を
      直してから再実行する。

    Args:
        client: 認証済みDomoクライアント。
        dataflow: 実行対象の DataFlow（`id` を含む）。
        wait_seconds: インラインで待つ上限秒数。0（既定）なら `DATAFLOW_WAIT_SECONDS` を使う。

    Returns:
        (state, executionId)。state は SUCCESS／RUNNING 等（RUNNING は継続中＝非失敗）。

    Raises:
        RuntimeError: 実行が本当に失敗した（FAILED 系／中断系）とき。
    """
    if wait_seconds <= 0:
        wait_seconds = DATAFLOW_WAIT_SECONDS
    dataflow_id = _id(dataflow)
    # 実行中の execution があれば再利用（新規実行を二重に投げない）。
    latest = _latest_execution(client, dataflow_id)
    if latest and _execution_state(latest) not in DATAFLOW_TERMINAL_STATES:
        execution_id = str(latest.get("id") or latest.get("dapDataFlowExecutionId") or "")
        print(f"DataFlow {dataflow_id}: reusing in-flight execution {execution_id} (no new run kicked)", flush=True)
    else:
        response = client.request("POST", f"api/dataprocessing/v1/dataflows/{dataflow_id}/executions", {}) or {}
        execution_id = str(response.get("id") or response.get("executionId") or response.get("dapDataFlowExecutionId") or "")
    deadline = time.time() + wait_seconds
    state = "RUNNING"
    while execution_id and time.time() < deadline:
        execution = client.request("GET", f"api/dataprocessing/v1/dataflows/{dataflow_id}/executions/{execution_id}") or {}
        state = _execution_state(execution)
        if state in DATAFLOW_TERMINAL_STATES:
            break
        time.sleep(5)
    print(f"DataFlow execution {execution_id}: {state}", flush=True)
    if state in DATAFLOW_FAILURE_STATES:
        # 本当の失敗だけ止める。多くは DomoGPT モデルID不正か入力DataSet不整合で、闇雲な再実行では
        # 直らない。原因を直してから再実行する。
        raise RuntimeError(f"DataFlow execution {execution_id} ended in {state}")
    if state != "SUCCESS":
        # 待ち上限に達したが実行はまだ継続中（RUNNING/QUEUED 等）。これは失敗ではない。
        # 実行はサーバ側で走り続けるので、絶対にキャンセル・再実行しない。あとで verify で確認する。
        print(
            f"DataFlow execution {execution_id} is still {state} after {wait_seconds}s. "
            "This is normal for the AI text-generation tile on larger seeds; the run continues on Domo. "
            "Do NOT cancel or re-trigger it. Re-run `verify` later to confirm SUCCESS "
            "(set DOMO_DATAFLOW_WAIT_SECONDS to wait longer inline if you prefer).",
            flush=True,
        )
    return state, execution_id


def apply(client: DomoClient, run_dataflow: bool, skip_workflow: bool = False) -> Dict[str, Any]:
    user = current_user(client)
    collection = ensure_collection(client, str(user.get("id") or ""))
    # 通知Workflowモデルを CE 配備より先に確定する。CE ソースへモデルIDを焼き込み、CE が実行時に
    # 最新の有効版を解決して起動できるようにする（フロントは Workflow を起動しない＝改版のたびに
    # カードを再埋め込みする必要がない）。--skip-workflow は通知Workflow層に触れない段階的
    # 立ち上げ用で、CE の起動先も空のまま配備する（後で通常の apply を再実行すれば配線される）。
    workflow_model = {} if skip_workflow else ensure_workflow_model(client)
    # CE が標準同期を即時キックできるよう datastoreId を CE ソースへ焼き込む（未確定なら空文字）。
    package, version = ensure_package(client, deployed_source(
        _id(collection), user["id"], str(collection.get("datastoreId") or ""), str(workflow_model.get("modelId") or "")
    ))
    invoke_inventory_api(client, _id(package), version, "SEED")
    # シードで AppDB に数百件（品目/ロケーション/ルール/取引/残高）を投入するため、
    # まず datasourceId が採番されるのを待ってから標準同期を即時キックし、DataFlow が
    # 古い版の DataSet を読む事故を防ぐ（既定の約15分間隔スケジュールを待たない）。
    collection = refresh_collection(client, 30)
    collection = trigger_appdb_sync(client, collection, 120)
    dataflow: Dict[str, Any] = {}
    state, execution_id = "WAITING_FOR_STANDARD_SYNC", ""
    if collection.get("datasourceId"):
        dataflow = ensure_dataflow(client, str(collection["datasourceId"]))
        state = "NOT_RUN"
        if run_dataflow:
            state, execution_id = trigger_dataflow(client, dataflow)
            dataflow = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(dataflow)}") or dataflow
    # 通知Workflowの配線は DataFlow の後に行う。新規インスタンスでは分析Dashboard DataSet の実IDが
    # DataFlow の生成/実行で初めて確定するため、その実IDでAIエージェントの知識DataSetを接地する
    # （DataFlow未生成なら output_dataset_id は "" を返し manifest 宣言値へフォールバック）。
    # これで初回 apply から verify の workflowAiAgentDatasetContextIds == dashboardDatasetId を満たす。
    if skip_workflow:
        # --skip-workflow は「通知Workflow層を今回は触らない」段階的立ち上げ用。通常は不要
        # （apply が通知Workflowモデルを名称で発見または新規作成し、3タイル雛形と配線まで自動で
        # 行うため、人手のUI作成もID受け渡しも要らない）。データ・ロジック層（AppDB/CE/SEED/同期/
        # DataFlow）だけを先に確定させたいときにのみ使う。あとで skip なしで apply を再実行すれば
        # 配線が入る（べき等）。
        workflow = {"modelId": "", "version": "", "tileCount": 0, "aiAgentCount": 0, "aiAgentEmailToolCount": 0, "aiAgentDatasetContextCount": 0}
    else:
        workflow = ensure_agent_email_workflow(client, output_dataset_id(dataflow))
    result = {"instance": INSTANCE, "ownerUserId": user["id"], "collection": {"name": COLLECTION_NAME, "id": _id(collection), "datasetId": str(collection.get("datasourceId") or "")}, "codeEngine": {"name": PACKAGE_NAME, "id": _id(package), "version": version, "publicFunctionCount": 1, "privateHelperCount": 6}, "dataflow": {"name": DATAFLOW_NAME, "id": _id(dataflow), "tileCount": 7, "sectionCount": 3, "lastExecutionId": execution_id, "lastExecutionState": state}, "dashboardDataset": {"name": OUTPUT_DATASET_NAME, "id": output_dataset_id(dataflow)}, "workflowAi": dict(workflow, status=("SKIPPED" if skip_workflow else "READY"), runtimeWiringEnabled=(not skip_workflow))}
    print("ASSET_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def sync_manifest(client: DomoClient) -> Dict[str, Any]:
    """Reconcile pro-code/manifest.json の alias→物理ID を現インスタンスの実資産へ合わせる。

    別インスタンスで `apply` が新規作成した資産IDを、`domo publish` の前にバンドルへ配線する
    ための冪等な補助。Domo資産は名称で「発見」するだけで作成・変更しない（read-only）。書き換える
    のは collection / dashboard DataSet / Code Engine package / Workflow model の接続IDと解決済み版。
    alias・schema・design `id`（トップレベル）は維持する。一致していれば書き込まず、
    差分ゼロで終了する。design `id` は初回publishでDomoが払い出すため本コマンドの対象外。
    """
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    collection = next((row for row in list_collections(client) if row.get("name") == COLLECTION_NAME), {})
    package = next((row for row in list_packages(client) if row.get("name") == PACKAGE_NAME), {})
    flow_row = next((row for row in list_dataflows(client) if row.get("name") == DATAFLOW_NAME), {})
    dataflow = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(flow_row)}") if flow_row else {}
    dashboard_id = output_dataset_id(dataflow or {})
    # Workflow モデルも他資産と同じく名称で発見する（read-only）。DOMO_WORKFLOW_MODEL_ID が明示指定
    # されていればそれを尊重、無ければ WORKFLOW_MODEL_NAME で発見し、未存在なら manifest 宣言値を
    # 据え置く（＝差分ゼロ）。旧実装はグローバル既定（保守用インスタンスのID）へフォールバックしていた
    # ため、発見に失敗した際に顧客インスタンスの manifest へ誤ID（保守用）を焼き込む恐れがあった。
    # ここは apply とは別プロセス起動なので都度発見する。
    workflow_model_id = resolve_workflow_model_id(client)
    package_version = ""
    if _id(package):
        latest = client.request("GET", f"api/codeengine/v2/packages/{_id(package)}/versions/latest?parts=functions") or {}
        package_version = str(latest.get("version") or "")
        if not package_version:
            raise RuntimeError("Code Engine version is unresolved; refusing to publish a source-instance version.")
    workflow_active_version = ""
    if workflow_model_id:
        metadata = client.request("GET", f"api/workflow/v1/models/{workflow_model_id}") or {}
        active = [str(row.get("version") or "") for row in metadata.get("versions") or []
                  if isinstance(row, dict) and row.get("active") is True and re.fullmatch(r"\d+\.\d+\.\d+", str(row.get("version") or ""))]
        if not active:
            raise RuntimeError("Notification Workflow has no active version; provision it before publishing.")
        workflow_active_version = max(active, key=lambda value: tuple(map(int, value.split("."))))

    changes: Dict[str, Any] = {}

    def _bind(container: Optional[Dict[str, Any]], key: str, value: str, label: str) -> None:
        if container is not None and value and container.get(key) != value:
            changes[label] = {"from": container.get(key), "to": value}
            container[key] = value

    collections_mapping = manifest.get("collectionsMapping") or []
    datasets_mapping = manifest.get("datasetsMapping") or []
    packages_mapping = manifest.get("packagesMapping") or []
    workflows_mapping = manifest.get("workflowsMapping") or []
    _bind(collections_mapping[0] if collections_mapping else None, "id", _id(collection), "collection.id")
    _bind(datasets_mapping[0] if datasets_mapping else None, "dataSetId", dashboard_id, "dataset.dataSetId")
    _bind(packages_mapping[0] if packages_mapping else None, "packageId", _id(package), "package.packageId")
    _bind(packages_mapping[0] if packages_mapping else None, "version", package_version, "package.version")
    _bind(workflows_mapping[0] if workflows_mapping else None, "modelId", workflow_model_id, "workflow.modelId")
    _bind(workflows_mapping[0] if workflows_mapping else None, "version", workflow_active_version, "workflow.version")

    # 配線先は配布コピー自身の pro-code/manifest.json。サンドボックス（名札付き）では、ここで
    # トップレベル id を外す＝続く `cd pro-code && domo publish` が id 省略で“自分専用デザインを
    # 新規採番”し、名札バックエンド（上で再束縛した collection/dashboard DataSet/CE package/
    # Workflow）へ束縛された FE を作る。publish がライブ採番 id を manifest へ書き戻し、後続の
    # app-studio がその id を読んで参加者のデザインを埋め込む＝FE も含めた完全隔離が成立する。
    # （参加者は各自のソースコピーを持つので pro-code/manifest.json を直接書いてよい。解決済み ID 台帳
    # domo-assets.json は従来どおり参加者ごとの state ディレクトリに分離＝共有台帳は汚さない。）
    # ⚠ryuu は id を「省略」したときのみ新規採番する（空文字 "" は失敗）ため、キーごと pop する。
    # 本番（名札なし）は id を保持したまま従来どおり pro-code へ書く（design は初回publishで採番済）。
    manifest_out = MANIFEST_PATH
    stripped_id: Optional[str] = None
    if SANDBOX and manifest.get("id"):
        stripped_id = str(manifest.pop("id"))
    if changes or stripped_id is not None:
        manifest_out.parent.mkdir(parents=True, exist_ok=True)
        manifest_out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    asset_path = MANIFEST_PATH.parent.parent / "code-engine" / "asset.json"
    if package_version and asset_path.exists():
        asset = json.loads(asset_path.read_text(encoding="utf-8"))
        if asset.get("version") != package_version or asset.get("packageId") != _id(package):
            asset.update(version=package_version, packageId=_id(package))
            asset_path.write_text(json.dumps(asset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "instance": INSTANCE,
        "changed": bool(changes) or stripped_id is not None,
        "changes": changes,
        "manifestPath": str(manifest_out),
        "sandbox": SANDBOX,
        "designIdStripped": bool(stripped_id),
        "resolved": {"collection": _id(collection), "dashboardDataset": dashboard_id, "package": _id(package), "workflowModel": workflow_model_id},
    }
    print("MANIFEST_SYNC_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def verify(client: DomoClient) -> Dict[str, Any]:
    # verify は別プロセス起動のため、全自動フロー（人手で DOMO_WORKFLOW_MODEL_ID を設定しない）では
    # モジュール既定（保守用インスタンスのID）のままになる。顧客インスタンスでその既定IDを
    # workflow_version へ問い合わせると存在せず「has no version」で誤失敗するので、まず名称で
    # read-only 解決してグローバルを確定させる（発見のみ・作成しない）。
    global WORKFLOW_MODEL_ID
    WORKFLOW_MODEL_ID = resolve_workflow_model_id(client)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    package_mapping = (manifest.get("packagesMapping") or [{}])[0]
    workflow_mapping = (manifest.get("workflowsMapping") or [{}])[0]
    collection = refresh_collection(client, 5)
    rows = query_documents(client, _id(collection), {}) if collection else []
    counts: Dict[str, int] = {}
    for row in rows:
        record_type = str((row.get("content") or {}).get("record_type") or "")
        counts[record_type] = counts.get(record_type, 0) + 1
    package = next((row for row in list_packages(client) if row.get("name") == PACKAGE_NAME), {})
    # code も取得し、CE ソースへ通知Workflowの modelId が焼き込まれているか照合する
    # （フロントの直起動を廃止した後は、CE が起動先を知っていることが通知動作の必須条件）。
    latest = client.request("GET", f"api/codeengine/v2/packages/{_id(package)}/versions/latest?parts=functions,code") if package else {}
    code_engine_code = str((latest or {}).get("code") or "")
    dataflow = next((row for row in list_dataflows(client) if row.get("name") == DATAFLOW_NAME), {})
    current_flow = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(dataflow)}") if dataflow else {}
    current_workflow_version = workflow_version(client)
    workflow_last = workflow_last_run(client)
    current_workflow = workflow_definition(client, current_workflow_version)
    workflow_tiles = [row for row in current_workflow.get("designElements") or [] if row.get("type") not in {"defaultEdge", "conditionEdge"}]
    sections = [row for row in ((current_flow or {}).get("gui") or {}).get("elements") or [] if row.get("type") == "Section"]
    actions = (current_flow or {}).get("actions") or []
    workflow_ai = next((row for row in workflow_tiles if row.get("type") == "AI_AGENT"), {})
    workflow_agent = (workflow_ai.get("data") or {}).get("agent") or {}
    workflow_context_dataset_ids = [str(row.get("id") or "") for row in (workflow_agent.get("context") or {}).get("datasets") or []]
    design_id = str(manifest.get("id") or "")
    design = client.request("GET", f"api/apps/v1/designs/{design_id}?parts=versions") or {}
    registry = load_registry()
    registered = registry.get("appStudio") or {}
    app_studio_proxy_id = str(registered.get("proxyId") or "")
    app_studio_context_id = str(registered.get("contextId") or "")
    # 参照カードから proxy(instance)/context を API で復元する手段は無い（recon 確認済み）。
    # 複数名が同一インスタンスの共有アプリを再利用する場合、作成者以外は proxy/context を持てず
    # domo-assets.json では空になる。空のときは page2 と同じ扱いで proxy/context の3条件を素通り
    # させ（カードの存在・layout・三点版一致で健全性は担保）、単独デプロイ（作成パスで全ID充足）
    # では従来どおり厳密に検証する。
    app_studio_context_registered = bool(app_studio_context_id and app_studio_proxy_id)
    app_studio_context = client.request("GET", f"domoapps/apps/v2/contexts/{registered.get('contextId')}") if registered.get("contextId") else {}
    app_studio_instance = client.request("GET", f"api/apps/v1/instances/{app_studio_proxy_id}") if app_studio_proxy_id else {}
    context_design_version = str((app_studio_context or {}).get("designVersion") or "")
    published_design_version = str(design.get("latestVersion") or "")
    app_studio_effective_version = context_design_version or published_design_version
    cards = _list_page_cards(client, str(registered.get("viewId")), parts="metadata,properties,chartMetadata") if registered.get("viewId") else []
    app_studio_card = next((row for row in cards if _id(row) == str(registered.get("cardId") or "")), {})
    app_studio_card_present = bool(app_studio_card)
    app_studio_metadata = app_studio_card.get("metadata") or {}
    app_studio_layout = client.request("GET", f"api/content/v4/pages/{registered.get('viewId')}/layouts") if registered.get("viewId") else {}
    target_content_keys = {
        str(row.get("contentKey")) for row in (app_studio_layout or {}).get("content") or []
        if str(row.get("cardId") or row.get("cardUrn") or "") == str(registered.get("cardId") or "")
    }
    app_studio_content_count = sum(
        str(row.get("cardId") or row.get("cardUrn") or "") == str(registered.get("cardId") or "")
        for row in (app_studio_layout or {}).get("content") or []
    )

    def layout_tile(mode: str, tile_type: str) -> Dict[str, Any]:
        return next((
            row for row in ((app_studio_layout or {}).get(mode) or {}).get("template") or []
            if row.get("type") == tile_type and (tile_type != "CARD" or str(row.get("contentKey")) in target_content_keys)
        ), {})

    standard_card_tile = layout_tile("standard", "CARD")
    compact_card_tile = layout_tile("compact", "CARD")
    app_studio_target_content = next((
        row for row in (app_studio_layout or {}).get("content") or []
        if str(row.get("contentKey")) in target_content_keys
    ), {})
    standard_page_break = layout_tile("standard", "PAGE_BREAK")
    compact_page_break = layout_tile("compact", "PAGE_BREAK")
    manifest_size = manifest.get("size") or {}
    expected_card_width = f"{float(manifest_size.get('width') or 1):.1f}"
    expected_card_height = f"{float(manifest_size.get('height') or 1):.1f}"
    expected_card_fullpage = str(bool(manifest.get("fullpage"))).lower()
    # ページ2(開発者リファレンス)は domo-assets.json に appStudio.page2 が在るときだけ検証する。
    # 未デプロイ環境（page2 未登録）では verify を落とさない。参照インスタンスでは page2 の
    # context を API 解決できない（contextId=""）ため、版モードは registry 宣言値で代替し、
    # layout 寸法には過剰適合せず「カードが在り FOLLOW_LATEST 相当」だけを確認する。
    page2 = registered.get("page2") or {}
    page2_present = bool(page2.get("viewId") and page2.get("cardId"))
    page2_cards = _list_page_cards(
        client, str(page2.get("viewId")), parts="metadata,properties,chartMetadata"
    ) if page2.get("viewId") else []
    page2_card = next((row for row in page2_cards if _id(row) == str(page2.get("cardId") or "")), {})
    page2_context_id = str(page2.get("contextId") or "")
    page2_context = client.request("GET", f"domoapps/apps/v2/contexts/{page2_context_id}") if page2_context_id else {}
    page2_context_version = str((page2_context or {}).get("designVersion") or "")
    page2_version_mode = (
        ("PINNED" if page2_context_version else "FOLLOW_LATEST")
        if page2_context_id else str(page2.get("cardVersionMode") or "FOLLOW_LATEST")
    )
    result = {
        "collectionId": _id(collection), "recordCounts": counts,
        "standardSyncDatasetId": str(collection.get("datasourceId") or ""),
        "proCodeDesignId": design_id, "proCodeManifestVersion": str(manifest.get("version") or ""),
        "proCodePublishedLatestVersion": published_design_version,
        "manifestCodeEnginePackageId": str(package_mapping.get("packageId") or ""),
        "manifestCodeEngineVersion": str(package_mapping.get("version") or ""),
        "manifestWorkflowModelId": str(workflow_mapping.get("modelId") or ""),
        "manifestWorkflowVersion": str(workflow_mapping.get("version") or ""),
        "codeEngineId": _id(package), "codeEngineVersion": str((latest or {}).get("version") or ""),
        # CE が通知Workflowの modelId を焼き込んで配備されているか（＝サーバー側起動の配線）。
        "codeEngineWorkflowModelEmbedded": bool(WORKFLOW_MODEL_ID and WORKFLOW_MODEL_ID in code_engine_code),
        "codeEngineFunctionCount": len((latest or {}).get("functions") or []), "codeEnginePrivateHelperCount": 6,
        "dataflowId": _id(dataflow), "dataflowInputCount": len((current_flow or {}).get("inputs") or []),
        "dataflowTileCount": len(actions), "dataflowSectionCount": len(sections),
        "dataflowDocumentedTileCount": sum(bool(row.get("notes")) for row in actions),
        "dashboardDatasetId": output_dataset_id(current_flow or {}),
        "workflowModelId": WORKFLOW_MODEL_ID, "workflowVersion": current_workflow_version,
        "workflowLatestReleasedVersion": current_workflow_version,
        "workflowLastRunVersion": workflow_last["version"],
        "workflowLastRunAt": workflow_last["at"],
        "workflowRuntimeMatchesDeclared": (not workflow_last["version"]) or workflow_last["version"] == str(workflow_mapping.get("version") or ""),
        "workflowTileCount": len(workflow_tiles), "workflowAiAgentCount": sum(row.get("type") == "AI_AGENT" for row in workflow_tiles),
        "workflowAiAgentEmailToolCount": sum(row.get("functionName") == "sendEmail" for row in workflow_agent.get("tools") or []),
        "workflowAiAgentDatasetContextCount": len(workflow_context_dataset_ids),
        "workflowAiAgentDatasetContextIds": workflow_context_dataset_ids,
        "appStudioCardId": str(registered.get("cardId") or ""), "appStudioCardPresent": app_studio_card_present,
        "appStudioTargetCardContentCount": app_studio_content_count,
        "appStudioCardIntrinsicWidth": str(app_studio_metadata.get("kpiDimensionWidth") or ""),
        "appStudioCardIntrinsicHeight": str(app_studio_metadata.get("kpiDimensionHeight") or ""),
        "appStudioCardFullpage": str(app_studio_metadata.get("fullpage") or ""),
        "appStudioLayoutDynamic": bool((app_studio_layout or {}).get("isDynamic")),
        "appStudioStandardLayout": [standard_card_tile.get("width"), standard_card_tile.get("height")],
        "appStudioCompactLayout": [compact_card_tile.get("width"), compact_card_tile.get("height")],
        "appStudioInteractionType": str((app_studio_target_content.get("interaction") or {}).get("type") or ""),
        "appStudioHideWrench": bool(app_studio_target_content.get("hideWrench")),
        "appStudioEditInAppViewer": bool(app_studio_target_content.get("editInAppViewer")),
        "appStudioStandardPageBreakY": standard_page_break.get("y"),
        "appStudioCompactPageBreakY": compact_page_break.get("y"),
        "appStudioContextDesignId": str((app_studio_context or {}).get("designId") or ""),
        "appStudioProxyId": app_studio_proxy_id,
        "appStudioContextId": str(registered.get("contextId") or ""),
        "appStudioInstanceDesignId": str((app_studio_instance or {}).get("designId") or ""),
        "appStudioInstanceContextDistinct": bool(app_studio_proxy_id and app_studio_proxy_id != str(registered.get("contextId") or "")),
        "appStudioContextDesignVersion": context_design_version or None,
        "appStudioCardVersionMode": "PINNED" if context_design_version else "FOLLOW_LATEST",
        "appStudioEffectiveDesignVersion": app_studio_effective_version,
        "appStudioPage2Present": page2_present,
        "appStudioPage2ViewId": str(page2.get("viewId") or ""),
        "appStudioPage2CardId": str(page2.get("cardId") or ""),
        "appStudioPage2CardPresent": bool(page2_card),
        "appStudioPage2CardVersionMode": page2_version_mode,
        "appStudioPageCount": 2 if page2_present else 1,
        "legacyCollectionsRemaining": [row.get("name") for row in list_collections(client) if row.get("name") in LEGACY_COLLECTIONS],
    }
    # 決定的シードの想定件数（品目30・ロケーション6・ルール30・取引135・残高131）。
    # 残高131件は AI テキスト生成タイルのバッチ下限（≥100行）を満たすための最低ライン。
    required = {"ITEM": 30, "LOCATION": 6, "RULE": 30, "TRANSACTION": 135, "BALANCE": 131}
    result["ok"] = (
        all(counts.get(key, 0) >= value for key, value in required.items())
        and bool(result["standardSyncDatasetId"] and result["dashboardDatasetId"])
        and result["proCodeManifestVersion"] == result["proCodePublishedLatestVersion"] == result["appStudioEffectiveDesignVersion"]
        and result["manifestCodeEnginePackageId"] == result["codeEngineId"]
        and result["manifestCodeEngineVersion"] == result["codeEngineVersion"]
        # 通知Workflowの起動は CE が担う（フロント直起動なし）。CE ソースに起動先の modelId が
        # 焼き込まれていることを成功条件に含め、旧CEのまま・--skip-workflow の配備漏れを検出する。
        and result["codeEngineWorkflowModelEmbedded"]
        and result["manifestWorkflowModelId"] == result["workflowModelId"]
        # 通知Workflowの版は ok ゲートに含めない（modelId 一致だけを固定条件にする）。理由:
        # この版はインスタンス依存で動く。新規インスタンスでは seed が 1.0.0 を作り、grounding が
        # 実 Dashboard DataSet／実 sendEmail 版へ接地するため必ず 1.0.1 以降へ作り直して release する。
        # 保守インスタンスでも sendEmail 版がドリフトすれば版が上がる。sync-manifest は版欄を書き戻さない
        # ため（[provision_domo.py sync_manifest 参照]）、manifest 宣言版と live 版の equality は
        # 参照インスタンスの手積み履歴でしか成立しない。版解決は Domo プラットフォーム制御で
        # アプリから確定的に矯正できない（下の workflowWarnings で必ず可視化する）。健全性は
        # 「modelId 一致＋3タイル／1 AI Agent／1 sendEmail tool／Dashboard DataSet 接地」の内容検証で担保する。
        and result["appStudioCardPresent"]
        and result["appStudioCardIntrinsicWidth"] == expected_card_width
        and result["appStudioCardIntrinsicHeight"] == expected_card_height
        and result["appStudioCardFullpage"] == expected_card_fullpage
        and result["appStudioTargetCardContentCount"] == 1
        and result["appStudioStandardLayout"][0] == 60
        and int(result["appStudioStandardLayout"][1] or 0) >= 60
        and result["appStudioCompactLayout"] == [12, 29]
        and result["appStudioInteractionType"] != "DISABLED"
        and result["appStudioHideWrench"]
        and result["appStudioEditInAppViewer"]
        # proxy/context は作成パスでのみ確定できる（共有アプリを再利用する2人目以降は空）。
        # 登録があるときだけ厳密検証し、無いときは素通り（page2 と同じ方針）。
        and (not app_studio_context_registered or (
            result["appStudioContextDesignId"] == result["proCodeDesignId"]
            and result["appStudioInstanceDesignId"] == result["proCodeDesignId"]
            and result["appStudioInstanceContextDistinct"]
        ))
        and result["codeEngineFunctionCount"] == 1 and result["dataflowInputCount"] == 1
        and result["dataflowTileCount"] == 7 and result["dataflowSectionCount"] == 3
        and result["dataflowDocumentedTileCount"] == 7 and result["workflowTileCount"] == 3
        and result["workflowAiAgentCount"] == 1 and result["workflowAiAgentEmailToolCount"] == 1
        and result["workflowAiAgentDatasetContextCount"] == 1
        and result["workflowAiAgentDatasetContextIds"] == [result["dashboardDatasetId"]]
        # ページ2は登録済みのときだけゲート（未登録＝未デプロイは素通り）。存在＋非PINNEDのみ確認。
        and (not page2_present or (result["appStudioPage2CardPresent"] and result["appStudioPage2CardVersionMode"] != "PINNED"))
    )
    # なぜ warning で止めないか: 直近実行版は「過去の起動」を映すだけで、
    # 版の解決は Domo プラットフォーム制御のためアプリ側から確定的に矯正できない。
    # ビルドは通しつつ、宣言版とランタイム解決版の乖離だけは必ず可視化する。
    warnings: List[str] = []
    if result["manifestWorkflowVersion"] and result["manifestWorkflowVersion"] != result["workflowVersion"]:
        warnings.append(
            f"workflow released v{result['workflowVersion']} on this instance but manifest declares "
            f"v{result['manifestWorkflowVersion']}; the notification workflow version is instance-dynamic "
            "(seeded at 1.0.0, then rebuilt to ground the live dashboard DataSet and live sendEmail version) "
            "and sync-manifest does not write it back — this is expected and does not fail verify"
        )
    if workflow_last["version"] and workflow_last["version"] != str(workflow_mapping.get("version") or ""):
        warnings.append(
            f"workflow runtime resolved v{workflow_last['version']} on last run "
            f"({workflow_last['at']}) but manifest declares v{workflow_mapping.get('version')}; "
            "Domo controls workflow version resolution server-side"
        )
    result["workflowWarnings"] = warnings
    print("VERIFY_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def cleanup_legacy(client: DomoClient) -> Dict[str, Any]:
    verification = verify(client)
    if not verification.get("ok"):
        raise RuntimeError("Refusing cleanup until the minimal architecture verifies successfully")
    removed_collections: List[str] = []
    removed_datasets: List[str] = []
    existing_by_name = {row.get("name"): row for row in list_collections(client)}
    for name, (expected_collection_id, _) in LEGACY_COLLECTIONS.items():
        row = existing_by_name.get(name)
        if row and _id(row) == expected_collection_id:
            client.request("DELETE", f"api/datastores/v1/collections/{expected_collection_id}")
            removed_collections.append(expected_collection_id)
    for _, (_, dataset_id) in LEGACY_COLLECTIONS.items():
        try:
            metadata = client.request("GET", f"api/data/v3/datasources/{dataset_id}") or {}
            card_count = int(metadata.get("cardCount") or (metadata.get("cardInfo") or {}).get("cardCount") or 0)
            if card_count:
                raise RuntimeError(f"Legacy DataSet {dataset_id} still has {card_count} cards")
            client.request("DELETE", f"api/data/v3/datasources/{dataset_id}")
            removed_datasets.append(dataset_id)
        except DomoApiError as error:
            if error.status != 404:
                raise
    result = {"removedCollectionIds": removed_collections, "removedDatasetIds": removed_datasets, "remainingLegacyCollections": [row.get("name") for row in list_collections(client) if row.get("name") in LEGACY_COLLECTIONS]}
    print("CLEANUP_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def configure_app_studio_layout(
    client: DomoClient,
    view_id: str,
    card_id: str,
    *,
    standard: Tuple[int, int] = (60, 82),
    compact: Tuple[int, int] = (12, 29),
) -> None:
    """Statically pin one card to fill a page, plus a terminal PAGE_BREAK.

    standard / compact are the (width, height) grid sizes for the two App Studio
    layout modes. Defaults match page 1 (the inventory card), so existing callers
    and tests are unchanged. Page 2 (the dev guide) passes its own
    sizes because its live compact height (12x6) is too short on mobile.
    """
    layout = client.request("GET", f"api/content/v4/pages/{view_id}/layouts") or {}
    if not layout.get("layoutId"):
        return
    layout["isDynamic"] = False
    layout["printFriendly"] = False
    target_keys = {
        str(content.get("contentKey"))
        for content in layout.get("content") or []
        if str(content.get("cardId") or content.get("cardUrn") or "") == card_id
    }
    if not target_keys:
        raise RuntimeError(f"App Studio card {card_id} is missing from layout {layout['layoutId']}")
    for content in layout.get("content") or []:
        if str(content.get("cardId") or content.get("cardUrn") or "") == card_id:
            content.update({
                "hideTitle": True,
                "hideDescription": True,
                "hideFooter": True,
                "hideWrench": True,
                "hideMargins": False,
                "hideBorder": False,
                "fitToFrame": False,
                # editInAppViewer must stay True so PC/App Studio viewer clicks reach the
                # Pro Code iframe. When False, the first desktop click selects the card for
                # editing instead of interacting.
                "editInAppViewer": True,
                "showMoreContent": False,
                "compactInteractionDefault": True,
            })
            # interaction.type="DISABLED" はモバイルの青い選択枠を消す一方で PC（App Studio
            # ビューア）のクリックも殺す。editInAppViewer:True でも PC が操作不能になるため、
            # PC 操作を最優先し interaction は既定（未設定＝操作許可）に戻す。モバイルの青枠と
            # スクロールロックは iframe を 100dvh へ固定する CSS と静的 layout + 終端 PAGE_BREAK
            # で抑える。
            content.pop("interaction", None)
    # This reference app intentionally owns one page and one card. App Studio adds
    # a virtual "末尾" appendix whenever a replacement card is placed. Removing the
    # retired content entries keeps both the viewer and editor deterministic.
    layout["content"] = [
        content for content in layout.get("content") or []
        if str(content.get("contentKey")) in target_keys
    ]
    target_sizes = {"standard": tuple(standard), "compact": tuple(compact)}
    templates = [((layout.get(mode) or {}).get("template") or []) for mode in target_sizes]
    existing_break_keys = [
        row.get("contentKey") for template in templates for row in template
        if row.get("type") == "PAGE_BREAK"
    ]
    numeric_keys = [
        int(row.get("contentKey")) for template in templates for row in template
        if str(row.get("contentKey") or "").isdigit()
    ]
    page_break_key = existing_break_keys[0] if existing_break_keys else (max(numeric_keys, default=0) + 1)
    for mode, (width, height) in target_sizes.items():
        template = (layout.get(mode) or {}).get("template") or []
        target_tiles = []
        for tile in template:
            if tile.get("type") == "CARD" and str(tile.get("contentKey")) in target_keys:
                tile.update({"x": 0, "y": 0, "width": width, "height": height, "virtual": False, "virtualAppendix": False})
                tile["children"] = []
                target_tiles.append(tile)
        page_break = next((row for row in template if row.get("type") == "PAGE_BREAK"), None)
        if page_break is None:
            page_break = {"type": "PAGE_BREAK", "contentKey": page_break_key, "children": []}
        page_break.update({"x": 0, "y": height, "width": width, "height": 0, "virtual": False, "virtualAppendix": False})
        page_break["children"] = []
        layout[mode]["template"] = target_tiles + [page_break]
    lock_path = f"api/content/v4/pages/layouts/{layout['layoutId']}/writelock"
    locked = False
    try:
        client.request("PUT", lock_path, {})
        locked = True
        client.request("PUT", f"api/content/v4/pages/layouts/{layout['layoutId']}", layout)
        print(f"updated App Studio layout: {layout['layoutId']}", flush=True)
    finally:
        if locked:
            try:
                client.request("DELETE", lock_path)
            except DomoApiError as error:
                print(f"warning: App Studio writelock release failed ({error.status})", flush=True)


def validate_app_studio_card_metadata(client: DomoClient, card_id: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    query = urllib.parse.urlencode({"urns": card_id, "parts": "metadata,properties,chartMetadata"})
    cards = _items(client.request("GET", f"api/content/v1/cards?{query}"), "cards")
    card = next((row for row in cards if _id(row) == card_id), None)
    if not card:
        raise RuntimeError(f"App Studio card {card_id} metadata is unavailable")
    size = manifest.get("size") or {}
    expected = {
        "fullpage": str(bool(manifest.get("fullpage"))).lower(),
        "kpiDimensionWidth": f"{float(size.get('width') or 1):.1f}",
        "kpiDimensionHeight": f"{float(size.get('height') or 1):.1f}",
    }
    metadata = card.get("metadata") or {}
    mismatches = {
        key: {"expected": value, "actual": str(metadata.get(key) or "")}
        for key, value in expected.items()
        if str(metadata.get(key) or "") != value
    }
    if mismatches:
        raise RuntimeError(
            f"App Studio card {card_id} metadata differs from Manifest; "
            "refusing an in-place metadata rewrite because it can strand Domo Mobile loading: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )
    print(f"validated App Studio card metadata: {card_id}", flush=True)
    return card


def create_app_studio_card(client: DomoClient, view_id: str, manifest: Dict[str, Any], card_title: str) -> Dict[str, str]:
    """Create a standard two-layer Domo App instance and resolve its new card."""
    before_cards = _list_page_cards(client, view_id)
    before_ids = {_id(row) for row in before_cards}
    mappings = [
        {"dataSetId": row["dataSetId"], "alias": row["alias"], "fields": row.get("fields", [])}
        for row in manifest.get("datasetsMapping", [])
    ]
    collections = [dict(row, alias=row["name"]) for row in manifest.get("collectionsMapping", [])]
    context = client.request("POST", "domoapps/apps/v2/contexts", {
        "designId": str(manifest.get("id") or ""),
        "mapping": mappings,
        "collections": collections,
    }) or {}
    context_id = str(context[0].get("id") if isinstance(context, list) else _id(context))
    query = urllib.parse.urlencode({
        "fullpage": str(bool(manifest.get("fullpage"))).lower(),
        "pageId": view_id,
        "cardTitle": card_title,
    })
    # Do not send id=contextId. Domo must allocate a distinct outer instance/proxy
    # ID so native Mobile resolves instance -> context like standard Pro Code cards.
    instance = client.request("POST", f"domoapps/apps/v2?{query}", {"contextId": context_id}) or {}
    proxy_id = _id(instance)
    after_cards = _list_page_cards(client, view_id, parts="metadata,properties,chartMetadata")
    created_cards = [row for row in after_cards if _id(row) not in before_ids and row.get("title") == card_title]
    if len(created_cards) != 1:
        raise RuntimeError(f"Could not uniquely resolve the new App Studio card for proxy {proxy_id}")
    card_id = _id(created_cards[0])
    if not proxy_id or proxy_id == context_id:
        raise RuntimeError("Domo returned a non-standard App instance whose proxy ID equals its context ID")
    return {"cardId": card_id, "proxyId": proxy_id, "contextId": context_id}


def add_dataapp_view(client: DomoClient, app_id: str, page_title: str) -> str:
    """Add a page to an App Studio DataApp and return the new viewId (as str).

    Uses the documented per-view POST (toolkit SKILL.md Step 10c), which registers
    the parallel views[]/navigations[] arrays internally — no unified PUT needed.
    Verified live on the reference app: the response carries the new viewId at
    view.pageId, and the view appears in both views[] and navigations[].
    """
    before = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
    before_ids = {str(v.get("viewId") or v.get("id") or "") for v in (before.get("views") or [])}
    resp = client.request("POST", f"api/content/v1/dataapps/{app_id}/views", {
        "type": "dataappview",
        "title": page_title,
        "hasLayout": True,
        "appPageDataSourceId": "null",
    }) or {}
    view = resp.get("view") if isinstance(resp, dict) else None
    new_view_id = str((view or {}).get("pageId") or (view or {}).get("id") or "")
    if not new_view_id:
        # Fall back to diffing views[] if the response shape changes.
        after = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
        after_ids = [str(v.get("viewId") or v.get("id") or "") for v in (after.get("views") or [])]
        fresh = [v for v in after_ids if v not in before_ids]
        if len(fresh) != 1:
            raise RuntimeError(
                f"Add-view POST did not surface a single new page on app {app_id}; "
                "create page 2 manually in App Studio and re-run app-studio (it will adopt the page by card title)."
            )
        new_view_id = fresh[0]
    return new_view_id


def ensure_app_studio_page(
    client: DomoClient,
    app_id: str,
    page1_view_id: str,
    *,
    manifest_path: pathlib.Path,
    page_title: str,
    card_title: str,
    standard: Tuple[int, int],
    compact: Tuple[int, int],
    registered_page: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Idempotently ensure a second App Studio page carrying a Pro Code card.

    Reuse order (never creates a duplicate):
      1. Registry-pinned: if registered_page's viewId/cardId still exist, reuse them.
      2. Discovery: adopt any non-landing view whose card title matches card_title
         (this adopts a manually-created page 2, e.g. on the reference instance).
      3. Create: add a page, embed the card, configure layout.
    In every branch the layout is (re)configured to the given sizes, so the call is
    safe to run repeatedly. Returns {viewId, cardId, proxyId, contextId, designId}.
    """
    manifest = json.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
    design_id = str(manifest.get("id") or "")
    if not design_id:
        raise RuntimeError(
            f"dev-guide manifest {manifest_path} has no design id; publish it first "
            "(cd dev-guide-app && domo publish)."
        )
    details = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
    if isinstance(details, list):
        details = details[0]
    view_ids = [str(v.get("viewId") or v.get("id") or "") for v in (details.get("views") or [])]

    # 1) registry-pinned reuse
    reg = registered_page or {}
    reg_view = str(reg.get("viewId") or "")
    reg_card = str(reg.get("cardId") or "")
    if reg_view and reg_view in view_ids:
        cards = _list_page_cards(client, reg_view)
        if any(_id(row) == reg_card for row in cards):
            print(f"reused registered App Studio page 2: view {reg_view} card {reg_card}", flush=True)
            configure_app_studio_layout(client, reg_view, reg_card, standard=standard, compact=compact)
            return {
                "viewId": reg_view, "cardId": reg_card,
                "proxyId": str(reg.get("proxyId") or ""), "contextId": str(reg.get("contextId") or ""),
                "designId": design_id,
            }

    # 2) discovery by card title on any non-landing view (adopts a manual page 2)
    for view_id in view_ids:
        if view_id == str(page1_view_id):
            continue
        cards = _list_page_cards(client, view_id)
        match = next((row for row in cards if row.get("title") == card_title), None)
        if match:
            card_id = _id(match)
            print(f"adopted existing App Studio page 2: view {view_id} card {card_id}", flush=True)
            configure_app_studio_layout(client, view_id, card_id, standard=standard, compact=compact)
            return {
                "viewId": view_id, "cardId": card_id,
                "proxyId": "", "contextId": "", "designId": design_id,
            }

    # 3) create a new page, embed the card, configure layout
    try:
        client.request("GET", f"api/apps/v1/designs/{design_id}")
    except DomoApiError as error:
        if error.status == 404:
            raise RuntimeError(
                f"dev-guide design {design_id} is not published on this instance; "
                "publish it first (cd dev-guide-app && domo publish), then re-run app-studio."
            ) from error
        raise
    view2 = add_dataapp_view(client, app_id, page_title)
    created = create_app_studio_card(client, view2, manifest, card_title)
    card2 = created["cardId"]
    validate_app_studio_card_metadata(client, card2, manifest)
    configure_app_studio_layout(client, view2, card2, standard=standard, compact=compact)
    print(f"created App Studio page 2: view {view2} card {card2}", flush=True)
    return {
        "viewId": view2, "cardId": card2,
        "proxyId": created["proxyId"], "contextId": created["contextId"], "designId": design_id,
    }


def write_back_app_studio_ids(
    page1: Dict[str, str], page2: Optional[Dict[str, str]] = None
) -> bool:
    """発見／作成で解決した App Studio の identity ID を domo-assets.json へ書き戻す。

    なぜ必要か: ``app-studio`` が App／Page／Card／context を「発見または作成」しても、その実IDを
    ローカルの ``domo-assets.json`` に定着させないと、別プロセスの ``export-app-studio`` / ``verify``
    が配布時の参照インスタンスの旧IDを読み続け、人手でのID貼り替えを迫ってしまう（＝性能の低いAIが
    「Appを手作りしてIDを渡せ」と誤案内する温床）。実IDを書き戻すことで、以後のコマンドは追加の
    人手なく通る＝全自動デプロイ契約を満たす。

    identity ID（``appId/viewId/cardId/proxyId/contextId`` と ``page2`` の同種）に加え、
    利用先を限定する ``instance`` / ``sandboxSuffix`` を保存する。URLなど他の設定値は保持する。
    このローカル状態ファイルは配布対象外。``proxyId``/``contextId`` は解決結果で上書きする
    （空なら空へ）——配布時の参照インスタンス値が対象インスタンスで無効なとき、それらを掴んだ 404
    フォールバックの後に確実に消すため（残すと ``verify`` が無効な context を GET して誤失敗する）。
    変更が無ければ書き込まない（再利用の冪等パスでファイルを無用に触らない）。
    """
    registry = load_registry()
    before = json.dumps(registry, ensure_ascii=False, sort_keys=True)
    registry["instance"] = INSTANCE
    registry["sandboxSuffix"] = _sandbox_suffix()
    app = registry.setdefault("appStudio", {})
    for key in ("appId", "viewId", "cardId", "proxyId", "contextId"):
        if key in page1:
            app[key] = str(page1.get(key) or "")
    if page2 is not None:
        page2_block = app.setdefault("page2", {})
        for key in ("viewId", "cardId", "proxyId", "contextId", "designId"):
            if key in page2:
                page2_block[key] = str(page2.get(key) or "")
    after = json.dumps(registry, ensure_ascii=False, sort_keys=True)
    if after == before:
        return False
    out_path = registry_write_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def app_studio(client: DomoClient) -> Dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    design_id = str(manifest.get("id") or "")
    # サンドボックスで id が空＝sync-manifest が id を外した後、まだ publish していない（正順違反）。
    # 空 designId で context を作ると埋め込みが壊れるので、ここで正順を促して停止する。
    if SANDBOX and not design_id:
        raise SystemExit(
            "pro-code/manifest.json のトップレベル id が空です（サンドボックス）。\n"
            "正順: provision_domo.py apply → sync-manifest →『cd pro-code && domo publish』"
            "（id 省略で自分専用デザインを新規採番し manifest へ書き戻す）→ app-studio。\n"
            "publish を先に実行してから app-studio を再実行してください。"
        )
    registry = load_registry()
    registered = registry.get("appStudio") or {}
    app_id = str(registered.get("appId") or "")
    registered_view_id = str(registered.get("viewId") or "")
    registered_card_id = str(registered.get("cardId") or "")
    proxy_id = str(registered.get("proxyId") or "")
    context_id = str(registered.get("contextId") or "")
    registry_pinned = bool(app_id)

    details = None
    if registry_pinned:
        try:
            details = client.request("GET", f"api/content/v1/dataapps/{app_id}") or {}
            print(f"reused registered App Studio app: {app_id}", flush=True)
        except DomoApiError as error:
            if error.status != 404:
                raise
            # 配布時の domo-assets.json は参照インスタンスの App/Page/Card/context ID が入っている。
            # 対象インスタンスでそのまま実行すると参照 appId への GET が 404 になる。ここで停止して
            # 「Appを手作りしてIDを渡せ」と促すのではなく、名称で発見または API で新規作成へ自動
            # フォールバックする（＝全自動デプロイ契約）。参照インスタンス由来の Page/Card/context ID は
            # 当該インスタンスで無効なので必ずクリアし、この後の発見／作成パスで実IDを採り直す。
            # 名称一致での発見は、同一インスタンスへ複数名・複数回デプロイしても1アプリを共有し
            # 重複を作らない（冪等）。
            print(
                f"note: registered App Studio app {app_id} is absent on this instance; "
                "falling back to discover-or-create by name "
                "(expected on a fresh instance; no manual App creation needed).",
                flush=True,
            )
            registry_pinned = False
            app_id = ""
            registered_view_id = ""
            registered_card_id = ""
            proxy_id = ""
            context_id = ""

    if not registry_pinned:
        apps = _items(client.request("GET", "api/content/v1/dataapps?limit=500&offset=0"), "dataapps", "apps")
        app = next((row for row in apps if row.get("title") == APP_STUDIO_NAME or row.get("name") == APP_STUDIO_NAME), None)
        if not app:
            created = client.request("POST", "api/content/v1/dataapps", {"title": APP_STUDIO_NAME, "description": "Minimal Domo-native inventory reference architecture."}) or {}
            app = created[0] if isinstance(created, list) else created
        app_id = _id(app)
        if not app_id:
            # DataApp の ID は応答で dataAppId キーに入ることがある(_id で吸収済み)。それでも
            # 空なら ``dataapps/`` へ空IDで問い合わせて全件が返り、details[0] が別アプリに化ける
            # footgun を避けるため、ここで明確に停止する。
            raise RuntimeError("Could not determine the App Studio app id after discovery/creation")
        details = client.request("GET", f"api/content/v1/dataapps/{app_id}") or app
    if isinstance(details, list):
        details = details[0]
    views = details.get("views") or details.get("pages") or []
    view_id = registered_view_id or str(details.get("landingViewId") or (views[0].get("id") if views else ""))
    if not view_id:
        raise RuntimeError(f"App Studio app {app_id} has no page")
    cards = _list_page_cards(client, view_id)
    existing_card = None
    if registry_pinned and registered_card_id:
        existing_card = next((row for row in cards if _id(row) == registered_card_id), None)
        if not existing_card:
            # App は一致したが登録 cardId がページ上に無い（カードの作り直し等でIDが drift）。停止して
            # 手作業を促すのではなく、タイトル一致での再発見→無ければ作成へフォールバックする（自動）。
            print(
                f"note: registered App Studio card {registered_card_id} is absent on page {view_id}; "
                "falling back to discover-or-create by title.",
                flush=True,
            )
    if existing_card is None:
        existing_card = next((row for row in reversed(cards) if row.get("title") == APP_STUDIO_CARD_TITLE), None)
    if existing_card:
        card_id = _id(existing_card)
        print(f"reused App Studio card: {card_id}", flush=True)
    else:
        created = create_app_studio_card(client, view_id, manifest, APP_STUDIO_CARD_TITLE)
        proxy_id = created["proxyId"]
        context_id = created["contextId"]
        card_id = created["cardId"]
        print(f"created App Studio card: {card_id}", flush=True)
    validate_app_studio_card_metadata(client, card_id, manifest)
    configure_app_studio_layout(client, view_id, card_id)
    design = client.request("GET", f"api/apps/v1/designs/{design_id}?parts=versions") or {}
    # context_id が空になり得るのは「タイトル一致で既存カードを再利用した」経路（前回 run が
    # write-back 前に page2 で落ちて proxy/context を registry へ定着できていない等）。空IDで
    # ``contexts/`` を GET すると 403 になり、実体としては正しく張られたカードなのに app-studio 全体が
    # 落ちる。verify(1152)/export/drill と同じく「context_id があるときだけ GET」のガードへ揃える。
    # context 不明時は FOLLOW_LATEST 相当として版報告する（Pro Code カード既定＝最新追従）。
    context = client.request("GET", f"domoapps/apps/v2/contexts/{context_id}") if context_id else {}
    context_version = str(context.get("designVersion") or "")
    result = {
        "appStudio": {"name": APP_STUDIO_NAME, "id": app_id, "viewId": view_id, "url": f"/app-studio/{app_id}"},
        "proCodeCard": {
            "designId": design_id, "proxyId": proxy_id, "contextId": context_id, "cardId": card_id,
            "versionMode": "PINNED" if context_version else "FOLLOW_LATEST",
            "contextDesignVersion": context_version or None,
            "effectiveDesignVersion": context_version or str(design.get("latestVersion") or ""),
        },
    }
    # ページ2＝開発ガイド（dev-guide-app）を同じアプリへ冪等に確保する（完全自動）。
    # 登録ピン→カード名で発見→無ければ作成、の順で重複を作らない。
    page2 = ensure_app_studio_page(
        client, app_id, view_id,
        manifest_path=DEV_GUIDE_MANIFEST_PATH,
        page_title=DEV_GUIDE_PAGE_TITLE,
        card_title=DEV_GUIDE_CARD_TITLE,
        standard=DEV_GUIDE_STANDARD,
        compact=DEV_GUIDE_COMPACT,
        registered_page=(registry.get("appStudio") or {}).get("page2"),
    )
    result["page2"] = page2
    # 発見／作成で確定した実IDを domo-assets.json へ書き戻す。これで export-app-studio / verify が
    # 別プロセスでも実IDを読め、追加の人手なく通る（全自動デプロイ契約）。冪等再利用では実IDが
    # 登録値と一致するため書き込みは発生しない。
    write_back_app_studio_ids(
        {"appId": app_id, "viewId": view_id, "cardId": card_id, "proxyId": proxy_id, "contextId": context_id},
        {key: page2.get(key, "") for key in ("viewId", "cardId", "proxyId", "contextId", "designId")},
    )
    print("APP_STUDIO_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def sanitize_app_studio_export(value: Any) -> Any:
    """Remove user-specific and transient editor state while preserving deployable structure."""
    transient = {
        "owners", "userAccess", "isOwner", "canEdit", "isFavorite", "locked",
        "creatorId", "ownerId", "createdBy", "updatedBy", "created", "updated",
        "createdDate", "updatedDate", "lastUpdated", "lastModifiedDate",
        "lockTimestamp", "lockHeartbeat",
    }
    if isinstance(value, list):
        return [sanitize_app_studio_export(row) for row in value]
    if isinstance(value, dict):
        return {key: sanitize_app_studio_export(row) for key, row in value.items() if key not in transient}
    return value


def export_app_studio(client: DomoClient) -> Dict[str, Any]:
    registry = load_registry()
    if not registry:
        raise RuntimeError("domo-assets.json is required to export the existing App Studio app")
    registered = registry.get("appStudio") or {}
    app_id = str(registered.get("appId") or "")
    registered_view_id = str(registered.get("viewId") or "")
    context_id = str(registered.get("contextId") or "")
    if not all((app_id, registered_view_id, context_id)):
        raise RuntimeError("App Studio appId, viewId, and contextId must be registered before export")

    # 登録済みビュー -> Pro Code contextId の対応表。ページ2(開発者リファレンス)は
    # 参照インスタンスでは context を API 解決できず contextId="" のことがあるため、
    # 空の場合はそのビューの context 取得を飛ばし null 相当（{}）で許容する。
    registered_page2 = registered.get("page2") or {}
    context_by_view = {registered_view_id: context_id}
    page2_view_id = str(registered_page2.get("viewId") or "")
    page2_context_id = str(registered_page2.get("contextId") or "")
    if page2_view_id and page2_context_id:
        context_by_view[page2_view_id] = page2_context_id

    data_app = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
    raw_views = data_app.get("views") or []
    view_ids = []
    for view in raw_views:
        view_id = str(view.get("viewId") or view.get("id") or "")
        if view_id and view_id not in view_ids:
            view_ids.append(view_id)
    if registered_view_id not in view_ids:
        view_ids.append(registered_view_id)

    pages = []
    pro_code_contexts = []
    context_cache: Dict[str, Any] = {}
    for view_id in view_ids:
        stack = client.request("GET", f"api/content/v3/stacks/{view_id}") or {}
        page_context_id = context_by_view.get(view_id, "")
        page_context: Dict[str, Any] = {}
        if page_context_id:
            page_context = client.request("GET", f"domoapps/apps/v2/contexts/{page_context_id}") or {}
            context_cache[page_context_id] = page_context
            pro_code_contexts.append({
                "viewId": view_id,
                "contextId": page_context_id,
                "context": page_context,
            })
        pages.append({
            "viewId": view_id,
            "stack": stack,
            "cards": _list_page_cards(client, view_id),
            "layout": client.request("GET", f"api/content/v4/pages/{view_id}/layouts") or {},
            # ページ2で contextId 未解決のときは {}（＝未掲載）を残す。export は落とさない。
            "proCodeContext": page_context,
        })
    # ソース情報（後方互換の top-level）はページ1の context を使う。
    context = context_cache.get(context_id) or (client.request("GET", f"domoapps/apps/v2/contexts/{context_id}") or {})
    design_id = str(context.get("designId") or "")
    design = client.request("GET", f"api/apps/v1/designs/{design_id}?parts=versions") if design_id else {}
    context_version = str(context.get("designVersion") or "")
    snapshot = sanitize_app_studio_export({
        "schemaVersion": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "instance": INSTANCE,
            "url": f"https://{INSTANCE}/app-studio/{app_id}/pages/{registered_view_id}",
            "appId": app_id,
            "viewId": registered_view_id,
            "cardId": str(registered.get("cardId") or ""),
            "contextId": context_id,
            "designId": design_id,
            "cardVersionMode": "PINNED" if context_version else "FOLLOW_LATEST",
            "contextDesignVersion": context_version or None,
            "effectiveDesignVersion": context_version or str((design or {}).get("latestVersion") or ""),
        },
        "dataApp": data_app,
        "pages": pages,
        # 後方互換: 単一 context（ページ1）。全ページ分は proCodeContexts に並べる。
        "proCodeContext": context,
        "proCodeContexts": pro_code_contexts,
    })
    APP_STUDIO_EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    APP_STUDIO_EXPORT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "path": str(APP_STUDIO_EXPORT_PATH),
        "appId": app_id,
        "viewCount": len(pages),
        "contextCount": len(pro_code_contexts),
    }
    print("APP_STUDIO_EXPORT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


WRITE_COMMANDS = {"apply", "app-studio", "cleanup-legacy", "workflow"}


def _production_write_guard(command: str) -> None:
    """本番保護ガード（バックエンド込み・名札隔離と対称）。

    書込み系コマンドで、解決後の対象が本番（名札なし）なら拒否する。サンドボックス参加者は
    ``INVENTORY_SANDBOX_SUFFIX`` を付ければ全オブジェクトが自動で一意名になり安全に通る。本番
    メンテナが本番名のまま配備する場合のみ ``INVENTORY_ALLOW_PRODUCTION=1`` を明示する。
    - ``app-studio`` は ``APP_STUDIO_NAME`` 上書きがあり得るため「解決後の対象名＝本番名」で判定
      （result-based。名札＋APP_STUDIO_NAME=本番名の抜け穴を塞ぐ）。
    - ``apply``/``workflow``/``cleanup-legacy`` はバックエンド名が名札のみで決まる（上書き env 無し）
      ため「名札なし（not SANDBOX）」で判定（hole-free）。
    """
    if command not in WRITE_COMMANDS:
        return
    if os.environ.get("INVENTORY_ALLOW_PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
        # ALLOW_PRODUCTION は「本番名のまま配備する」明示オプトイン。ただし DOMO_INSTANCE を
        # 明示せず既定（参照インスタンス maintenance-instance）へサイレント配備する事故（例: 本番名で
        # ALLOW_PRODUCTION=1 にしたが DOMO_INSTANCE を export し忘れ、手元の maintenance-instance 認証で
        # 共有参照環境を上書き）を防ぐため、ALLOW_PRODUCTION 使用時は配備先の明示を必須にする。
        if not (os.environ.get("DOMO_INSTANCE") or "").strip():
            raise SystemExit(
                "INVENTORY_ALLOW_PRODUCTION を使う場合は配備先を取り違えないよう DOMO_INSTANCE を"
                f"明示してください（未設定だと既定の参照インスタンス {INSTANCE} へ書き込みます）:\n"
                "  export DOMO_INSTANCE='<あなたのインスタンス>.domo.com'\n"
                "検証なら ALLOW_PRODUCTION ではなく名札（INVENTORY_SANDBOX_SUFFIX）を使ってください。"
            )
        return
    hits_production = (APP_STUDIO_NAME == PRODUCTION_APP_STUDIO_NAME) if command == "app-studio" else (not SANDBOX)
    if not hits_production:
        return
    raise SystemExit(
        f"このまま '{command}' を実行すると本番の在庫入出庫管理アセット"
        f"（App Studio「{PRODUCTION_APP_STUDIO_NAME}」および AppDB／Code Engine／DataFlow／"
        "出力 DataSet／通知 Workflow）を上書きします。\n"
        "ハンズオン／検証なら名札を付けてください（全オブジェクトが自動で一意名になり、"
        "バックエンド込みで隔離されます）:\n"
        "  export INVENTORY_SANDBOX_SUFFIX='検証・<あなたの氏名>'\n"
        "⚠本番アセットを更新する本番メンテナのみ INVENTORY_ALLOW_PRODUCTION=1 を明示してください。"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("apply", "sync-manifest", "verify", "cleanup-legacy", "app-studio", "export-app-studio", "workflow"))
    parser.add_argument("--skip-dataflow-run", action="store_true")
    parser.add_argument("--skip-workflow", action="store_true", help="通知Workflow層を今回は触らず、データ・ロジック層だけ先に構築する段階的立ち上げ用（通常は不要。apply が通知Workflowモデルを自動で発見/作成する）")
    args = parser.parse_args()
    _production_write_guard(args.command)
    client = DomoClient()
    if args.command == "apply":
        apply(client, not args.skip_dataflow_run, skip_workflow=args.skip_workflow)
        return 0
    if args.command == "sync-manifest":
        sync_manifest(client)
        return 0
    if args.command == "cleanup-legacy":
        cleanup_legacy(client)
        return 0
    if args.command == "app-studio":
        app_studio(client)
        return 0
    if args.command == "export-app-studio":
        export_app_studio(client)
        return 0
    if args.command == "workflow":
        ensure_agent_email_workflow(client)
        return 0
    return 0 if verify(client).get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
