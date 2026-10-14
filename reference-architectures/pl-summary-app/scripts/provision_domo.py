#!/usr/bin/env python3
"""Provision the pl-summary data layer on a Domo instance (idempotent).

The data layer this script stands up, in dependency order:

  1. seed DataSet   -- a tiny AppDB collection (1 doc) pushed through Domo
                       standard-sync, used only as the Magic ETL flow's input.
                       The flow's Python tile synthesises the P/L data and
                       ignores the input rows, so any readable DataSet serves;
                       a dedicated seed keeps the stack self-contained and
                       reproducible on a fresh instance.
  2. Code Engine    -- appdb_maintenance.py -> one public dedupe function
                       (dedupe_appdb_documents). Instance-independent: the
                       collection GUID is a required argument, not baked in.
  3. AppDB collection -- 店舗別損益AI要約 (syncEnabled:false). The long-form
                       analysis_html reports are written here by the WF-01 + consolidated sub-WF
                       workflow layer (provisioned by scripts/provision_workflows.py).
                       The Pro Code app reads it for the サマリー tab.
  4. DataFlow       -- DF｜店舗別損益データフロー (Magic ETL v2), rebuilt from the
                       captured dataflow/2042.json. Emits two output DataSets
                       (明細 / 要約) carrying the short-form AI summaries produced
                       by its two TextGeneration tiles. These two DataSets drive
                       the bulk of the Pro Code app (KPIs, charts, short notes).

To reproduce the stack on another instance set DOMO_INSTANCE (target host, e.g.
``<your-instance>.domo.com``) and authenticate one of two ways:
  * DOMO_DEVELOPER_TOKEN -- an instance developer token (no interactive login;
    best for repeatable, non-interactive distribution), or
  * ``domo login -i <host>`` first, so the CLI refresh token is available.
Both instance and model default to the maintained reference instance when unset,
so committing this file leaks no per-customer IDs.

After ``apply`` creates the assets on a fresh instance, run ``sync-manifest`` to
write the discovered DataSet / collection IDs into pro-code/manifest.json before
``domo publish``, then ``app-studio`` to embed the Pro Code card. The long-form
analysis_html workflow layer is provisioned by ``scripts/provision_workflows.py``.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple


INSTANCE = os.environ.get("DOMO_INSTANCE", "maintenance-instance.domo.com")

# --------------------------------------------------------------------------- #
# サンドボックス隔離（ハンズオン参加者ごと・バックエンド完全隔離）
# provision_workflows.py と**同一の名札** PL_SANDBOX_SUFFIX を読む。設定すると、seed データストア/
# コレクション・AppDB 業務コレクション・dedupe CE・DataFlow・4出力データセット・App Studio DataApp/
# カードの名前すべてにサフィックス（検証・氏名）が付き、同一インスタンス（maintenance-instance）上で本番や他参加者と
# 衝突しない。WF 層（provision_workflows.py）が同じ名札で保存CE・統合サブWF・WF-01・業務コレクション名を
# 揃えるので、バックエンド全体が1つの名札で隔離される。未設定（既定）なら従来挙動を一切変えない。
# dedupe 公開関数名・データセット alias（summary/detail/trend/dept）は契約として不変（_sx で包まない）。
# --------------------------------------------------------------------------- #
MAINTENANCE_INSTANCE = "maintenance-instance.domo.com"   # 配布元の保守・検証用共有インスタンス（顧客環境ではない）


def _sandbox_suffix() -> str:
    return (os.environ.get("PL_SANDBOX_SUFFIX") or "").strip()


def _sx(base: str) -> str:
    s = _sandbox_suffix()
    return f"{base}（{s}）" if s else base


SANDBOX = bool(_sandbox_suffix())


def _slugify(text: str) -> str:
    """サフィックスをパス安全なセグメントへ（英数と -_ 以外は -・空なら unknown）。"""
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (text or "").strip())
    out = "-".join(seg for seg in out.split("-") if seg)
    return out or "unknown"


def _norm_instance() -> str:
    return INSTANCE.lower().rstrip("/")


def _allow_production() -> bool:
    return os.environ.get("PL_ALLOW_PRODUCTION", "").strip().lower() in ("1", "true", "yes")


def _guard_production_write(action: str) -> None:
    """apply / app-studio / embed-guide（Domo への書込み）用の本番保護ガード。

    保守用共有インスタンス（maintenance-instance）で名札なしに本番名のオブジェクトを作成/更新するのを防ぐ。
    名札（PL_SANDBOX_SUFFIX）を付ければ全オブジェクト名が一意化され安全に通る。顧客が自分の
    インスタンスへ配備する場合（INSTANCE != maintenance-instance）は対象外＝従来どおり動く。"""
    if _norm_instance() == MAINTENANCE_INSTANCE and not SANDBOX and not _allow_production():
        raise SystemExit(
            f"PL_SANDBOX_SUFFIX が未設定のまま保守用インスタンス（maintenance-instance）の本番オブジェクトを "
            f"`{action}` で作成/書き換えようとしています。ハンズオンでは名札を付けてください"
            "（本番や他参加者と別名になり衝突しません）:\n"
            "  export PL_SANDBOX_SUFFIX='検証・<あなたの氏名>'\n"
            "顧客が自分の環境へ配備する場合は、まず自分のインスタンスを指定してください"
            "（export DOMO_INSTANCE=<your-instance>.domo.com・既定の maintenance-instance は配布元の保守用）。\n"
            "⚠本番メンテナが本番を更新する場合のみ PL_ALLOW_PRODUCTION=1 を明示してください（本番を上書きします）。")


ROOT = pathlib.Path(__file__).resolve().parents[1]
DATAFLOW_TEMPLATE_PATH = ROOT / "dataflow" / "2042.json"
SERVICE_PATH = ROOT / "code-engine" / "appdb_maintenance.py"
MANIFEST_PATH = ROOT / "pro-code" / "manifest.json"
REGISTRY_PATH = ROOT / "domo-assets.json"
# App Studio 上のアプリ名／カード名（名称で発見 or 作成する。顧客固有IDは持たない）。名札ありで一意化。
APP_STUDIO_NAME = _sx(os.environ.get("DOMO_PL_APP_STUDIO_NAME", "店舗別損益AIインサイト"))
APP_STUDIO_CARD_TITLE = _sx(os.environ.get("DOMO_PL_APP_STUDIO_CARD_TITLE", "店舗別損益AIインサイト（最小構成）"))
# ページ2＝開発ガイド（dev-guide-app）。同じ App Studio DataApp の2枚目として埋め込む（embed-guide）。
# dev-guide-app は純静的 Pro Code（データ接続なし）。ページ1（業務アプリ本体）には一切触れない。
GUIDE_MANIFEST_PATH = ROOT / "dev-guide-app" / "manifest.json"
GUIDE_PAGE_TITLE = (os.environ.get("DOMO_PL_GUIDE_PAGE_TITLE") or "開発ガイド").strip()
GUIDE_CARD_TITLE = _sx((os.environ.get("DOMO_PL_GUIDE_CARD_TITLE") or "店舗別損益｜開発ガイド").strip())


def _registry_path() -> pathlib.Path:
    """解決 ID（App/Page/Card/proxy/context）の保存先。サンドボックスでは参加者ごとに分離する
    （同一マシンでも互いの domo-assets.json を上書きしない・本番ピン留めも読まない）。"""
    override = os.environ.get("DOMO_ASSETS_PATH")
    if override:
        return pathlib.Path(override).expanduser()
    if SANDBOX:
        return ROOT / ("sandbox-" + _slugify(_sandbox_suffix())) / "domo-assets.json"
    return REGISTRY_PATH

# 全て「名称で発見 or 作成」する。既定値は維持中の参照インスタンス(maintenance-instance)の値で、
# 別インスタンスでも同じ名前で発見/作成されるため、この定数群に顧客固有IDは一切入らない。
SEED_DATASTORE_NAME = _sx(os.environ.get("DOMO_PL_SEED_DATASTORE", "pl-summary-app"))
SEED_COLLECTION_NAME = _sx(os.environ.get("DOMO_PL_SEED_COLLECTION", "pl_summary_seed"))
BUSINESS_COLLECTION_NAME = _sx("店舗別損益AI要約")
PACKAGE_NAME = _sx(os.environ.get("DOMO_PL_PACKAGE_NAME", "Store PL AI Insights | AppDB Maintenance"))
DEDUPE_FUNCTION_NAME = "dedupe_appdb_documents"  # ⚠契約（公開関数名）＝名札でも不変。_sx で包まない。
DATAFLOW_NAME = _sx("DF｜店舗別損益データフロー")
DETAIL_OUTPUT_NAME = _sx("OUT｜P/L明細（店舗×勘定×月）")
SUMMARY_OUTPUT_NAME = _sx("OUT｜P/L要約（店舗×月）")
# live 化で追加した集計出力（Pro-Code のトレンド/事業部別が直接 live 参照する）。
# 名前は dataflow/2042.json の PublishToVault dataSourceName と厳密一致させること。
TREND_OUTPUT_NAME = _sx("OUT｜P/Lトレンド（店舗×月）")
DEPT_OUTPUT_NAME = _sx("OUT｜P/L事業部別（部門×月）")
# Magic ETL の TextGeneration タイルが使う DomoGPT モデル。インスタンスで有効なモデルへ env で
# 差し替え可能。既定は medium v2.2 / Anthropic(別デモの移植でこのインスタンスでの有効性を実証済み)。
AI_SUMMARY_MODEL_ID = os.environ.get("DOMO_AI_SUMMARY_MODEL_ID", "domo.domo_ai.domogpt-medium-v2.2:anthropic")


class DomoApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, detail: str):
        super().__init__(f"{method} {path} -> HTTP {status}: {detail[:500]}")
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail


class DomoClient:
    def __init__(self, instance: str = INSTANCE):
        self.instance = instance
        self.base = f"https://{instance}"
        self.sid = ""
        # 開発者トークン(DOMO_DEVELOPER_TOKEN)があれば SID を介さず X-DOMO-Developer-Token
        # ヘッダで直接認証する。非対話・自動配布では発行済みトークン1つで全 API 面へ到達できる
        # 方が再現性が高い。トークンはソースへ焼き込まず環境変数からのみ読む。
        self.dev_token = os.environ.get("DOMO_DEVELOPER_TOKEN", "").strip()
        if not self.dev_token:
            self.refresh_sid()

    def refresh_sid(self) -> None:
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
        with urllib.request.urlopen(request, timeout=60) as response:
            access_token = (json.loads(response.read()) or {}).get("access_token")
        request = urllib.request.Request(f"{self.base}/api/oauth2/sid", headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            self.sid = str((json.loads(response.read()) or {}).get("sid") or "")

    def request(self, method: str, path: str, body: Any = None, *, retry: bool = True) -> Any:
        url = path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"
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
            with urllib.request.urlopen(request, timeout=180) as response:
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
        for key in keys + ("items", "data", "results", "collections", "packages", "dataflows", "datastores"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
    return []


def _id(value: Dict[str, Any]) -> str:
    return str(value.get("id") or value.get("guid") or value.get("dataAppId") or value.get("cardId") or "")


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


def _is_true_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def current_user(client: DomoClient) -> Dict[str, Any]:
    me = client.request("GET", "api/content/v2/users/me") or {}
    owner_id = str(me.get("id") or "")
    if not owner_id:
        raise RuntimeError("Could not determine the authenticated Domo user")
    return {"id": owner_id, "name": me.get("displayName") or "Domo利用者"}


# --------------------------------------------------------------------------- #
# AppDB collections
# --------------------------------------------------------------------------- #
def list_collections(client: DomoClient) -> List[Dict[str, Any]]:
    return _items(client.request("GET", "api/datastores/v1/collections?limit=1000&offset=0"), "collections")


def _ensure_datastore(client: DomoClient, name: str) -> str:
    datastores = _items(client.request("GET", "api/datastores/v1?limit=1000&offset=0"), "datastores")
    datastore = next((row for row in datastores if row.get("name") == name), None)
    if not datastore:
        datastore = client.request("POST", "api/datastores/v1", {"name": name}) or {}
    return _id(datastore)


def ensure_seed_collection(client: DomoClient) -> Dict[str, Any]:
    """1ドキュメントの種DataSet用コレクションを発見/作成する(syncEnabled:true)。

    Magic ETL の LoadFromVault は有効な入力DataSetを必須とするが、当該フローの Python タイルは
    入力行を使わず P/L データを合成する。ゆえに任意の可読DataSetで足りるが、専用の種を持つ方が
    スタックが自己完結し新規インスタンスで確実に再現できる。
    """
    existing = next((row for row in list_collections(client) if row.get("name") == SEED_COLLECTION_NAME), None)
    if not existing:
        datastore_id = _ensure_datastore(client, SEED_DATASTORE_NAME)
        query = urllib.parse.urlencode({"datastoreId": datastore_id})
        existing = client.request("POST", f"api/datastores/v1/collections?{query}", {"name": SEED_COLLECTION_NAME, "schema": {"columns": [{"name": "seed", "type": "STRING"}]}, "syncEnabled": True}) or {}
        print(f"created seed collection: {_id(existing)}", flush=True)
    else:
        print(f"reused seed collection: {_id(existing)}", flush=True)
    # 1ドキュメントだけ確保(空なら投入する)。種の中身は無関係なので冪等に1件あればよい。
    docs = _items(client.request("POST", f"api/datastores/v2/collections/{_id(existing)}/documents/query", {}), "documents")
    if not docs:
        client.request("POST", f"api/datastores/v1/collections/{_id(existing)}/documents", {"content": {"seed": "pl-summary-seed"}})
    return existing


def ensure_business_collection(client: DomoClient) -> Dict[str, Any]:
    """分析レポート(analysis_html)保存用の業務コレクションを発見/作成する(syncEnabled:false)。

    書き込むのは WF-01/02/03(UI補助境界)で、このスクリプトは器だけ用意する。Pro Code の
    サマリータブがここを generated_at 降順で読む。ドキュメントは content 任意項目のスキーマレス。
    """
    existing = next((row for row in list_collections(client) if row.get("name") == BUSINESS_COLLECTION_NAME), None)
    if existing:
        print(f"reused AppDB collection: {_id(existing)}", flush=True)
        return existing
    datastore_id = _ensure_datastore(client, SEED_DATASTORE_NAME)
    query = urllib.parse.urlencode({"datastoreId": datastore_id})
    created = client.request("POST", f"api/datastores/v1/collections?{query}", {"name": BUSINESS_COLLECTION_NAME, "schema": {"columns": []}, "syncEnabled": False}) or {}
    print(f"created AppDB collection: {_id(created)}", flush=True)
    return created


def trigger_appdb_sync(client: DomoClient, collection: Dict[str, Any], collection_name: str, wait_seconds: int = 120) -> Dict[str, Any]:
    """AppDB標準同期を即時キックし、標準同期DataSetへ反映され切るまで待つ(datastoreIdキー)。"""
    datastore_id = str(collection.get("datastoreId") or "")
    if not (_is_true_flag(collection.get("syncEnabled")) and datastore_id):
        return collection
    try:
        client.request("POST", f"api/datastores/v1/export/{datastore_id}", None)
    except DomoApiError as error:
        print(f"appdb sync kick skipped ({error.status}); relying on scheduled sync", flush=True)
        return collection
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        collection = next((row for row in list_collections(client) if row.get("name") == collection_name), collection)
        dataset_id = str(collection.get("datasourceId") or "")
        if dataset_id and not collection.get("syncRequired"):
            meta = client.request("GET", f"api/data/v3/datasources/{dataset_id}") or {}
            print(f"appdb sync kicked: {int(meta.get('rowCount') or 0)} rows synced to {dataset_id}", flush=True)
            return collection
        time.sleep(2)
    print("appdb sync kick: proceeding after wait window (scheduled sync will reconcile)", flush=True)
    return collection


def resolve_seed_dataset(client: DomoClient, wait_seconds: int = 60) -> Tuple[Dict[str, Any], str]:
    collection = ensure_seed_collection(client)
    deadline = time.time() + wait_seconds
    while time.time() < deadline and not collection.get("datasourceId"):
        collection = next((row for row in list_collections(client) if row.get("name") == SEED_COLLECTION_NAME), collection)
        if collection.get("datasourceId"):
            break
        time.sleep(2)
    collection = trigger_appdb_sync(client, collection, SEED_COLLECTION_NAME, wait_seconds)
    return collection, str(collection.get("datasourceId") or "")


# --------------------------------------------------------------------------- #
# Code Engine
# --------------------------------------------------------------------------- #
def list_packages(client: DomoClient) -> List[Dict[str, Any]]:
    return _items(client.request("GET", "api/codeengine/v2/packages?limit=500&offset=0"), "packages")


def dedupe_function_manifest() -> List[Dict[str, Any]]:
    # 公開関数は dedupe_appdb_documents 1本のみ。`_` 始まりのヘルパーは命名規約で自動 private に
    # なるため Manifest 宣言不要。入力 collection_id(text) / 出力 object を明示する。
    return [{
        "name": DEDUPE_FUNCTION_NAME, "displayName": DEDUPE_FUNCTION_NAME,
        "description": "Keep only the newest document per content.doc_key in an AppDB collection (by content.generated_at string-desc); bulk-delete the rest.",
        "isPrivate": False,
        "inputs": [{"name": "collection_id", "displayName": "collection_id", "type": "text", "value": None, "nullable": False, "isList": False, "children": [], "entitySubType": None}],
        "output": {"name": "result", "displayName": "result", "type": "object", "value": None, "nullable": True, "isList": False, "children": [], "entitySubType": None},
    }]


def ensure_package(client: DomoClient) -> Tuple[Dict[str, Any], str]:
    source = SERVICE_PATH.read_text(encoding="utf-8")
    functions = dedupe_function_manifest()
    existing = next((row for row in list_packages(client) if row.get("name") == PACKAGE_NAME), None)
    if not existing:
        package = client.request("POST", "api/codeengine/v2/packages", {"name": PACKAGE_NAME, "description": "P/L summary AppDB maintenance: 1 public dedupe function (dedupe_appdb_documents).", "language": "PYTHON", "environment": "LAMBDA", "code": source, "manifest": {"functions": functions}}) or {}
        version = str(package.get("version") or "1.0.0")
        client.request("POST", f"api/codeengine/v2/packages/{_id(package)}/versions/{version}/release", {})
        print(f"created Code Engine package: {_id(package)} v{version}", flush=True)
        return package, version
    package_id = _id(existing)
    latest = client.request("GET", f"api/codeengine/v2/packages/{package_id}/versions/latest?parts=code,functions,configuration") or {}
    version = str(latest.get("version") or existing.get("version") or "1.0.0")
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
    print(f"released Code Engine package: {package_id} v{version}", flush=True)
    return existing, version


# --------------------------------------------------------------------------- #
# DataFlow (Magic ETL v2) rebuilt from captured 2042.json
# --------------------------------------------------------------------------- #
def list_dataflows(client: DomoClient) -> List[Dict[str, Any]]:
    return _items(client.request("GET", "api/dataprocessing/v1/dataflows?limit=500&offset=0"), "dataflows")


def _flow_output_ids(dataflow: Dict[str, Any]) -> Dict[str, str]:
    """出力 dataSourceName -> 物理DataSet GUID を返す(明細/要約を名前で対応付ける)。"""
    result: Dict[str, str] = {}
    for row in dataflow.get("outputs") or []:
        name = str(row.get("dataSourceName") or "")
        guid = str(row.get("dataSourceId") or "")
        if name and guid:
            result[name] = guid
    # フォールバック: PublishToVault アクションの dataSource.guid からも拾う。
    for action in dataflow.get("actions") or []:
        if action.get("type") == "PublishToVault":
            ds = action.get("dataSource") or {}
            name, guid = str(ds.get("name") or ""), str(ds.get("guid") or "")
            if name and guid:
                result.setdefault(name, guid)
    return result


def dataflow_create_body(seed_dataset_id: str, existing_outputs: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """captured 2042.json から作成/更新用ボディを組み立てる。

    - 入力(LoadFromVault / inputs[]) の dataSourceId を種DataSetへ張り替える。
    - 出力(PublishToVault / outputs[]) の GUID は、既存フロー更新時は既存DataSetを指し、
      新規作成時は None で採番させる(明細/要約を dataSourceName で対応付け)。
    - TextGeneration タイルの modelId を移植先で有効なモデルへ差し替える。
    サーバ採番のトップレベル項目(id/created/lastExecution 等)はホワイトリスト方式で持ち込まない。
    """
    existing_outputs = existing_outputs or {}
    template = json.loads(DATAFLOW_TEMPLATE_PATH.read_text(encoding="utf-8"))
    actions = copy.deepcopy(template.get("actions") or [])
    for action in actions:
        atype = action.get("type")
        if atype == "LoadFromVault":
            action["dataSourceId"] = seed_dataset_id
        elif atype == "PublishToVault":
            ds = action.get("dataSource") or {}
            ds["name"] = _sx(str(ds.get("name") or ""))   # 名札ありは出力名も一意化（非sandbox では base＝不変）
            ds["guid"] = existing_outputs.get(ds["name"], "") or None
            action["dataSource"] = ds
        elif atype == "TextGeneration":
            action["modelId"] = AI_SUMMARY_MODEL_ID

    inputs = []
    for row in template.get("inputs") or []:
        row = dict(row)
        row["dataSourceId"] = seed_dataset_id
        inputs.append(row)

    outputs = []
    for row in template.get("outputs") or []:
        name = _sx(str(row.get("dataSourceName") or ""))   # 名札ありは出力名も一意化（非sandbox では base＝不変）
        outputs.append({
            "onboardFlowId": None,
            "dataSourceId": existing_outputs.get(name, "") or None,
            "dataSourceName": name,
            "versionChainType": row.get("versionChainType") or "REPLACE",
        })

    return {
        "name": DATAFLOW_NAME,
        "description": "店舗別損益デモ: 1つの入力から Python 合成 → 明細/要約の2 DataSet を出力し、店舗別・全社の短文AIサマリーを TextGeneration タイルで生成する。",
        "runState": "ENABLED",
        "actions": actions,
        "gui": template.get("gui") or {},
        "inputs": inputs,
        "outputs": outputs,
        "engineProperties": template.get("engineProperties") or {"kettle.mode": "STRICT"},
        "settings": template.get("settings") or {"sqlDialect": "MAGIC"},
        "enabled": True,
        "paused": False,
        "triggeredByInput": False,
        "databaseType": template.get("databaseType") or "MAGIC",
        "magic": True,
    }


def ensure_dataflow(client: DomoClient, seed_dataset_id: str) -> Dict[str, Any]:
    existing = next((row for row in list_dataflows(client) if row.get("name") == DATAFLOW_NAME), None)
    if not existing:
        created = client.request("POST", "api/dataprocessing/v1/dataflows", dataflow_create_body(seed_dataset_id)) or {}
        created = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(created)}") or created
        print(f"created DataFlow: {_id(created)}", flush=True)
        return created
    dataflow_id = _id(existing)
    current = client.request("GET", f"api/dataprocessing/v1/dataflows/{dataflow_id}") or existing
    desired = dataflow_create_body(seed_dataset_id, _flow_output_ids(current))
    current.update(desired)
    updated = client.request("PUT", f"api/dataprocessing/v1/dataflows/{dataflow_id}", current) or current
    updated = client.request("GET", f"api/dataprocessing/v1/dataflows/{dataflow_id}") or updated
    print(f"updated DataFlow: {dataflow_id}", flush=True)
    return updated


def trigger_dataflow(client: DomoClient, dataflow: Dict[str, Any]) -> Tuple[str, str]:
    dataflow_id = _id(dataflow)
    response = client.request("POST", f"api/dataprocessing/v1/dataflows/{dataflow_id}/executions", {}) or {}
    execution_id = str(response.get("id") or response.get("executionId") or response.get("dapDataFlowExecutionId") or "")
    # TextGeneration タイルは店舗数に比例して数分かかる。終端状態で即 break するので、
    # 余裕をもって待ち上限を長めに取り、成功見込みの実行を誤って打ち切らない。
    deadline = time.time() + 1200
    state = "RUNNING"
    while execution_id and time.time() < deadline:
        execution = client.request("GET", f"api/dataprocessing/v1/dataflows/{dataflow_id}/executions/{execution_id}") or {}
        state = str(execution.get("state") or execution.get("status") or "RUNNING").upper()
        if state in {"SUCCESS", "FAILED", "FAILED_DATA_FLOW", "CANCELLED", "CANCELED", "ABORTED"}:
            break
        time.sleep(5)
    print(f"DataFlow execution {execution_id}: {state}", flush=True)
    if state != "SUCCESS":
        raise RuntimeError(f"DataFlow execution {execution_id} ended in {state}")
    return state, execution_id


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def apply(client: DomoClient, run_dataflow: bool) -> Dict[str, Any]:
    _guard_production_write("apply")
    user = current_user(client)
    seed_collection, seed_dataset_id = resolve_seed_dataset(client)
    if not seed_dataset_id:
        raise RuntimeError("Seed DataSet was not minted by standard sync; cannot create the DataFlow input")
    package, version = ensure_package(client)
    business = ensure_business_collection(client)
    dataflow = ensure_dataflow(client, seed_dataset_id)
    state, execution_id = "NOT_RUN", ""
    if run_dataflow:
        state, execution_id = trigger_dataflow(client, dataflow)
        dataflow = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(dataflow)}") or dataflow
    outputs = _flow_output_ids(dataflow)
    result = {
        "instance": INSTANCE,
        "ownerUserId": user["id"],
        "seedCollection": {"name": SEED_COLLECTION_NAME, "id": _id(seed_collection), "datasetId": seed_dataset_id},
        "codeEngine": {"name": PACKAGE_NAME, "id": _id(package), "version": version, "publicFunctionCount": 1},
        "businessCollection": {"name": BUSINESS_COLLECTION_NAME, "id": _id(business)},
        "dataflow": {"name": DATAFLOW_NAME, "id": _id(dataflow), "lastExecutionId": execution_id, "lastExecutionState": state},
        "summaryDataset": {"name": SUMMARY_OUTPUT_NAME, "id": outputs.get(SUMMARY_OUTPUT_NAME, "")},
        "detailDataset": {"name": DETAIL_OUTPUT_NAME, "id": outputs.get(DETAIL_OUTPUT_NAME, "")},
        "aiSummaryModelId": AI_SUMMARY_MODEL_ID,
    }
    print("ASSET_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def sync_manifest(client: DomoClient) -> Dict[str, Any]:
    """pro-code/manifest.json の alias→物理ID を現インスタンスの実資産へ合わせる(read-only 発見)。

    書き換えるのは datasetsMapping(summary/detail) と collectionsMapping[0].id の3ID欄のみ。
    alias / collection name / version / size は温存する。IDが一致していれば書き込まず差分ゼロで終了。
    """
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    flow_row = next((row for row in list_dataflows(client) if row.get("name") == DATAFLOW_NAME), {})
    dataflow = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(flow_row)}") if flow_row else {}
    outputs = _flow_output_ids(dataflow or {})
    business = next((row for row in list_collections(client) if row.get("name") == BUSINESS_COLLECTION_NAME), {})

    changes: Dict[str, Any] = {}

    def _bind(container: Optional[Dict[str, Any]], key: str, value: str, label: str) -> None:
        if container is not None and value and container.get(key) != value:
            changes[label] = {"from": container.get(key), "to": value}
            container[key] = value

    alias_to_output = {
        "summary": SUMMARY_OUTPUT_NAME,
        "detail": DETAIL_OUTPUT_NAME,
        "trend": TREND_OUTPUT_NAME,
        "dept": DEPT_OUTPUT_NAME,
    }
    for row in manifest.get("datasetsMapping") or []:
        out_name = alias_to_output.get(row.get("alias"))
        if out_name:
            _bind(row, "dataSetId", outputs.get(out_name, ""), "dataset." + row.get("alias"))
    collections_mapping = manifest.get("collectionsMapping") or []
    _bind(collections_mapping[0] if collections_mapping else None, "id", _id(business), "collection.id")

    if changes:
        MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {
        "instance": INSTANCE,
        "changed": bool(changes),
        "changes": changes,
        "resolved": {
            "summaryDataset": outputs.get(SUMMARY_OUTPUT_NAME, ""),
            "detailDataset": outputs.get(DETAIL_OUTPUT_NAME, ""),
            "trendDataset": outputs.get(TREND_OUTPUT_NAME, ""),
            "deptDataset": outputs.get(DEPT_OUTPUT_NAME, ""),
            "collection": _id(business),
        },
    }
    print("MANIFEST_SYNC_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def verify(client: DomoClient) -> Dict[str, Any]:
    seed = next((row for row in list_collections(client) if row.get("name") == SEED_COLLECTION_NAME), {})
    business = next((row for row in list_collections(client) if row.get("name") == BUSINESS_COLLECTION_NAME), {})
    package = next((row for row in list_packages(client) if row.get("name") == PACKAGE_NAME), {})
    latest = client.request("GET", f"api/codeengine/v2/packages/{_id(package)}/versions/latest?parts=functions") if package else {}
    flow_row = next((row for row in list_dataflows(client) if row.get("name") == DATAFLOW_NAME), {})
    dataflow = client.request("GET", f"api/dataprocessing/v1/dataflows/{_id(flow_row)}") if flow_row else {}
    outputs = _flow_output_ids(dataflow or {})
    summary_id = outputs.get(SUMMARY_OUTPUT_NAME, "")
    detail_id = outputs.get(DETAIL_OUTPUT_NAME, "")
    trend_id = outputs.get(TREND_OUTPUT_NAME, "")
    dept_id = outputs.get(DEPT_OUTPUT_NAME, "")

    def _rows(dataset_id: str) -> int:
        if not dataset_id:
            return 0
        meta = client.request("GET", f"api/data/v3/datasources/{dataset_id}") or {}
        return int(meta.get("rowCount") or 0)

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_ds = {row.get("alias"): str(row.get("dataSetId") or "") for row in manifest.get("datasetsMapping") or []}
    manifest_collection = str(((manifest.get("collectionsMapping") or [{}])[0]).get("id") or "")

    result = {
        "instance": INSTANCE,
        "seedDatasetId": str(seed.get("datasourceId") or ""),
        "businessCollectionId": _id(business),
        "codeEngineId": _id(package),
        "codeEngineFunctionCount": len((latest or {}).get("functions") or []),
        "dataflowId": _id(dataflow),
        "dataflowInputCount": len((dataflow or {}).get("inputs") or []),
        "dataflowTileCount": len((dataflow or {}).get("actions") or []),
        "summaryDatasetId": summary_id, "summaryRowCount": _rows(summary_id),
        "detailDatasetId": detail_id, "detailRowCount": _rows(detail_id),
        "trendDatasetId": trend_id, "trendRowCount": _rows(trend_id),
        "deptDatasetId": dept_id, "deptRowCount": _rows(dept_id),
        "manifestSummaryDatasetId": manifest_ds.get("summary", ""),
        "manifestDetailDatasetId": manifest_ds.get("detail", ""),
        "manifestCollectionId": manifest_collection,
    }
    result["ok"] = bool(
        result["seedDatasetId"] and result["businessCollectionId"]
        and result["codeEngineId"] and result["codeEngineFunctionCount"] == 1
        and result["dataflowId"] and result["dataflowInputCount"] == 1
        and summary_id and detail_id
        and result["summaryRowCount"] > 0 and result["detailRowCount"] > 0
        and result["manifestSummaryDatasetId"] == summary_id
        and result["manifestDetailDatasetId"] == detail_id
        and result["manifestCollectionId"] == result["businessCollectionId"]
    )
    print("VERIFY_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


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


def configure_app_studio_layout(client: DomoClient, view_id: str, card_id: str) -> None:
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
    target_sizes = {"standard": (60, 82), "compact": (12, 29)}
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


def reconcile_app_studio_context(client: DomoClient, context_id: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    """既存 App Studio context の Dataset/AppDB mapping を manifest へ冪等に合わせる。

    なぜ: Pro-Code の manifest に alias を追加しても、埋込済みカードの App Framework context は
    自動追随しない(``domo publish`` は "Mapping has changed. Check current cards for potential
    miss-mappings." と警告するだけ)。未マッピングの alias は proxy で解決できず、FE は graceful
    degrade(トレンド空表示・事業部タブ非表示)に落ちるため、明示的に同期する。
    contextId が未解決(registry 未使用の discovery 経路など)のときは、同期対象が特定できないので
    警告のみで続行する(既存フローを壊さない)。
    """
    if not context_id:
        print("warning: App Studio contextId is unknown; skipped context mapping reconcile", flush=True)
        return {"changed": False, "mapping": [], "collections": []}
    current = client.request("GET", f"domoapps/apps/v2/contexts/{context_id}") or {}
    desired_mapping = [
        {"dataSetId": str(row.get("dataSetId") or ""), "alias": str(row.get("alias") or ""),
         "fields": row.get("fields") or []}
        for row in manifest.get("datasetsMapping") or [] if row.get("dataSetId") and row.get("alias")
    ]
    desired_collections = [
        {"name": str(row.get("name") or ""), "id": str(row.get("id") or "")}
        for row in manifest.get("collectionsMapping") or [] if row.get("name") and row.get("id")
    ]

    def _mapping_key(row: Dict[str, Any]) -> Tuple[str, str]:
        return str(row.get("alias") or ""), str(row.get("dataSetId") or "")

    def _collection_key(row: Dict[str, Any]) -> Tuple[str, str]:
        return str(row.get("name") or row.get("alias") or ""), str(row.get("id") or "")

    mapping_changed = sorted(map(_mapping_key, current.get("mapping") or [])) != sorted(map(_mapping_key, desired_mapping))
    collections_changed = sorted(map(_collection_key, current.get("collections") or [])) != sorted(map(_collection_key, desired_collections))
    if not mapping_changed and not collections_changed:
        return {"changed": False, "mapping": desired_mapping, "collections": desired_collections}

    payload = {
        "id": context_id,
        "designId": str(current.get("designId") or manifest.get("id") or ""),
        "designVersion": current.get("designVersion"),
        "mapping": desired_mapping,
        "collections": desired_collections,
        "packageMapping": current.get("packageMapping") or [],
        "workflowMapping": current.get("workflowMapping") or [],
        "accountMapping": current.get("accountMapping") or [],
        "actionMapping": current.get("actionMapping") or [],
        "isDisabled": bool(current.get("isDisabled")),
    }
    client.request("PUT", f"domoapps/apps/v2/contexts/{context_id}", payload)
    updated = client.request("GET", f"domoapps/apps/v2/contexts/{context_id}") or {}
    if sorted(map(_mapping_key, updated.get("mapping") or [])) != sorted(map(_mapping_key, desired_mapping)):
        raise RuntimeError("App Studio context dataset mapping did not persist")
    print(f"updated App Studio context mappings: {context_id}", flush=True)
    return {"changed": True, "mapping": desired_mapping, "collections": desired_collections}


def app_studio(client: DomoClient) -> Dict[str, Any]:
    _guard_production_write("app-studio")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    design_id = str(manifest.get("id") or "")
    registry = json.loads(_registry_path().read_text(encoding="utf-8")) if _registry_path().exists() else {}
    registered = registry.get("appStudio") or {}
    app_id = str(registered.get("appId") or "")
    registered_view_id = str(registered.get("viewId") or "")
    registered_card_id = str(registered.get("cardId") or "")
    proxy_id = str(registered.get("proxyId") or "")
    context_id = str(registered.get("contextId") or "")
    registry_pinned = bool(app_id)

    if registry_pinned:
        try:
            details = client.request("GET", f"api/content/v1/dataapps/{app_id}") or {}
        except DomoApiError as error:
            if error.status == 404:
                # 配布時の domo-assets.json は参照インスタンスの appId が入っている。対象インスタンスで
                # 未上書きのまま実行すると参照IDへのGETが404になる。ここで重複作成に走らず停止し、
                # 何をすべきか（自分のIDへ上書き or appStudio を空にして発見/作成）をメッセージで示す。
                raise RuntimeError(
                    f"Registered App Studio app {app_id} is missing on this instance; refusing to create a duplicate. "
                    "Overwrite domo-assets.json appStudio with this instance's App/Page/Card/context IDs (runbook STEP 5), "
                    "or clear appStudio to allow discovery/creation."
                ) from error
            raise
        print(f"reused registered App Studio app: {app_id}", flush=True)
    else:
        apps = _items(client.request("GET", "api/content/v1/dataapps?limit=500&offset=0"), "dataapps", "apps")
        app = next((row for row in apps if row.get("title") == APP_STUDIO_NAME or row.get("name") == APP_STUDIO_NAME), None)
        if not app:
            created = client.request("POST", "api/content/v1/dataapps", {"title": APP_STUDIO_NAME, "description": "店舗別損益の AI 要約を表示する最小構成の Domo ネイティブ参照アプリ。"}) or {}
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
    if registry_pinned:
        existing_card = next((row for row in cards if _id(row) == registered_card_id), None)
        if not existing_card:
            # App は一致したが登録 cardId がページ上に無い。埋め込んだカードの実IDと domo-assets.json の
            # cardId が食い違うのが典型。停止して、正しいカードIDへ上書きするよう促す。
            raise RuntimeError(
                f"Registered App Studio card {registered_card_id} is missing from page {view_id}; refusing to create a duplicate. "
                "Update domo-assets.json appStudio.cardId (and viewId) to the card actually embedded on this instance (runbook STEP 5)."
            )
    else:
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
    reconcile_app_studio_context(client, context_id, manifest)
    design = client.request("GET", f"api/apps/v1/designs/{design_id}?parts=versions") or {}
    # タイトル一致でカードを再利用した経路では context_id が空のまま残る。空IDで
    # contexts GET を叩くと 403/404 になるため、id がある時だけ問い合わせる(未設定は
    # FOLLOW_LATEST=バージョン空を意味する)。inventory 側の同修正と対応。
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
    print("APP_STUDIO_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result



def add_dataapp_view(client: DomoClient, app_id: str, page_title: str) -> str:
    """DataApp にページ（view）を1枚追加し、新しい viewId を返す（既存ページ＝ページ1 には触れない）。"""
    before = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
    before_ids = {str(v.get("viewId") or v.get("id") or "") for v in (before.get("views") or [])}
    resp = client.request("POST", f"api/content/v1/dataapps/{app_id}/views", {
        "type": "dataappview", "title": page_title, "hasLayout": True,
        "appPageDataSourceId": "null",  # Domo API 仕様（文字列 'null'。create_app_studio_card と同値）
    }) or {}
    view = resp.get("view") if isinstance(resp, dict) else None
    new_view_id = str((view or {}).get("pageId") or (view or {}).get("id") or "")
    if not new_view_id:
        after = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
        after_ids = [str(v.get("viewId") or v.get("id") or "") for v in (after.get("views") or [])]
        fresh = [v for v in after_ids if v not in before_ids]
        if len(fresh) != 1:
            raise RuntimeError("ページ追加POSTで新ビューを一意特定できませんでした。"
                               "App Studio で手動でページ2を作成してから再実行してください（カード名で採用します）。")
        new_view_id = fresh[0]
    print(f"created DataApp view (page 2): {new_view_id}", flush=True)
    return new_view_id


def embed_guide(client: DomoClient) -> Dict[str, Any]:
    """開発ガイド（dev-guide-app）を App Studio DataApp の「ページ2＝開発ガイド」として冪等に埋め込む。

    再利用順（重複を作らない）: ① registry の appStudioGuide が在れば再利用 → ② landing 以外のビューで
    カード名 GUIDE_CARD_TITLE か guide design を持つものを採用 → ③ ページを足してカードを埋め込む。
    どの分岐でも layout を全面ピンに整え直すので繰り返し実行して安全。**ページ1（本体カード）には触れない。**
    純静的 Pro Code（datasetsMapping 空）なので context mapping の同期は不要（create+layout のみ）。
    """
    _guard_production_write("embed-guide")
    guide = json.loads(GUIDE_MANIFEST_PATH.read_text(encoding="utf-8"))
    guide_design = str(guide.get("id") or "")
    if not guide_design:
        raise SystemExit("dev-guide-app/manifest.json に design id がありません。"
                         "先に `cd dev-guide-app && domo publish` を実行してください。")
    try:
        client.request("GET", f"api/apps/v1/designs/{guide_design}")  # 未公開なら明確に失敗
    except DomoApiError as error:
        if error.status == 404:
            raise SystemExit(f"開発ガイド design {guide_design} がこのインスタンスで未公開です。"
                             "`cd dev-guide-app && domo publish` の後に再実行してください。")
        raise

    # DataApp の解決（app_studio と同じ: registry の appId → 無ければ APP_STUDIO_NAME で厳密発見）。
    registry = json.loads(_registry_path().read_text(encoding="utf-8")) if _registry_path().exists() else {}
    app_id = str((registry.get("appStudio") or {}).get("appId") or "")
    if not app_id:
        apps = _items(client.request("GET", "api/content/v1/dataapps?limit=500&offset=0"), "dataapps", "apps")
        app = next((row for row in apps if row.get("title") == APP_STUDIO_NAME or row.get("name") == APP_STUDIO_NAME), None)
        if not app:
            raise SystemExit(f"App Studio アプリ『{APP_STUDIO_NAME}』が見つかりません。"
                             "先に `app-studio` でページ1（本体カード）を埋め込んでから embed-guide を実行してください。")
        app_id = _id(app)
    details = client.request("GET", f"api/content/v1/dataapps/{app_id}?includeHiddenViews=true") or {}
    if isinstance(details, list):
        details = details[0]
    views = details.get("views") or details.get("pages") or []
    landing_view = str(details.get("landingViewId") or (views[0].get("id") if views else "") or "")
    view_ids = [str(v.get("viewId") or v.get("id") or "") for v in (details.get("views") or [])]

    registered = registry.get("appStudioGuide") or {}
    view_id = str(registered.get("viewId") or "")
    card_id = str(registered.get("cardId") or "")
    proxy_id = str(registered.get("proxyId") or "")
    context_id = str(registered.get("contextId") or "")

    # ① レジストリ再利用（ページ・カードがまだ在れば）
    if view_id and view_id in view_ids and any(_id(r) == card_id for r in _list_page_cards(client, view_id)):
        print(f"reused guide page 2: view {view_id} card {card_id}", flush=True)
    else:
        view_id = card_id = proxy_id = context_id = ""
        # ② landing 以外のビューで、カード名 or guide design を持つものを採用
        for vid in view_ids:
            if vid == landing_view:
                continue
            match = next((r for r in _list_page_cards(client, vid, parts="metadata,properties,chartMetadata")
                          if r.get("title") == GUIDE_CARD_TITLE
                          or str(r.get("designId") or r.get("design") or "") == guide_design), None)
            if match:
                view_id, card_id = vid, _id(match)
                print(f"adopted guide page 2: view {view_id} card {card_id}", flush=True)
                break
        # ③ 新規作成（ページを足してカードを埋め込む）
        if not card_id:
            view_id = add_dataapp_view(client, app_id, GUIDE_PAGE_TITLE)
            created = create_app_studio_card(client, view_id, guide, GUIDE_CARD_TITLE)
            card_id, proxy_id, context_id = created["cardId"], created["proxyId"], created["contextId"]
            print(f"created guide page 2: view {view_id} card {card_id}", flush=True)

    configure_app_studio_layout(client, view_id, card_id)
    result = {
        "appStudioGuide": {
            "appId": app_id, "viewId": view_id, "cardId": card_id,
            "cardTitle": GUIDE_CARD_TITLE, "pageTitle": GUIDE_PAGE_TITLE,
            "proxyId": proxy_id, "contextId": context_id, "designId": guide_design,
            "landingViewId": landing_view, "url": f"/app-studio/{app_id}",
        },
    }
    # 解決した guide ページ情報を registry へ書き戻す（再実行で確実に再利用。gitignore 済み・配布されない）。
    try:
        reg_path = _registry_path()
        reg = json.loads(reg_path.read_text(encoding="utf-8")) if reg_path.exists() else {}
        reg["appStudioGuide"] = result["appStudioGuide"]
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"warning: registry 書き戻しに失敗（続行）: {error}", flush=True)
    print("GUIDE_RESULT=" + json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("apply", "sync-manifest", "verify", "app-studio", "embed-guide"))
    parser.add_argument("--skip-dataflow-run", action="store_true", help="DataFlow を作成/更新のみで実行しない")
    args = parser.parse_args()
    client = DomoClient()
    if args.command == "apply":
        apply(client, not args.skip_dataflow_run)
        return 0
    if args.command == "sync-manifest":
        sync_manifest(client)
        return 0
    if args.command == "app-studio":
        app_studio(client)
        return 0
    if args.command == "embed-guide":
        embed_guide(client)
        return 0
    return 0 if verify(client).get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
