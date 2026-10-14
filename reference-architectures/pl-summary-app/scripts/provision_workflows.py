#!/usr/bin/env python3
"""店舗別損益AIデモの Workflow 層を配備する（reference-app と同じ設計）。

このスクリプトは「AIエージェントが Code Engine ツールで保存まで完結する」構成へ揃えるための
配備ツール。2通りの使い方がある:

  A. **ゼロから配備（`provision`）**＝空の顧客インスタンス向け。CE パッケージ・統合サブWF・WF-01 を
     **名前で発見→無ければ新規作成**し（inventory / CI の provision_platform.py 相当）、保守用
     インスタンスの GUID を焼き込まないよう CollectionId とクエリ対象データセットを対象環境の実 ID へ
     **再束縛**する。前提: 先に `scripts/provision_domo.py` でデータ層（コレクション・データセット・
     manifest 同期）を作っておくこと。既存インスタンスでは各資産を発見して再利用するので、保守にも使える。
  B. **統合形への移行（`ce`/`subflow`/`mainflow`/`delete-wf03`）**＝既存 maintenance-instance デモ
     （WF-01/WF-02/WF-03 がある状態）を統合形へ移行する保守経路。既存のモデル GUID は env
     （`PL_WF01_MODEL_ID` / `PL_SUBFLOW_MODEL_ID` / `PL_WF03_MODEL_ID`）で差し替え可。重複除去 CE の
     `PL_DEDUPE_CE_PACKAGE_ID`・メール宛先 `PL_EMAIL_PERSON_RECIPIENTS` も env。重複除去ノードが
     無いインスタンスでは撤去は no-op（安全）。

構築するもの:
  1. Code Engine パッケージ `店舗別損益AI要約｜レポートAPI`（公開1関数 ``pl_report_api``）。
     ``save`` が AppDB 保存＋同一 doc_key の旧版削除を内包する（重複除去を保存へ畳み込む）。
  2. 統合サブ Workflow（既存 WF-02 モデルを再利用）:
       開始 → 待機（AI負荷平準化）→ レポート種別？ → 店舗AI / 全社AI → 終了。
     旧 WF-02（店舗）と WF-03（全社）を `report_type` 分岐の1本に統合する。両AIは ``pl_report_api``
     を保存ツールとして呼ぶ（全社AIは従来どおり Send Email も保持）。
  3. メイン Workflow（WF-01）の改修: 先頭の「AppDB重複除去」CEノードを撤去（重複除去は保存へ移動）、
     店舗ループに待機タイマーを追加、2つの SUB_FLOW 呼び出しを統合モデルへ張り替え（report_type を付与）。
  4. 不要になった旧 WF-03 モデルの削除（サブコマンド delete-wf03）。

安全規約: 定義は必ず draft 作成 → PUT → GET round-trip 検証 → release の順。検証失敗時は release
しない（旧 active 版は無傷）。`--dry-run` は PUT せず、組み立てた定義をファイルへ書き出すだけ。

認証: 環境変数 INSTANCE＋SID、または DOMO_DEVELOPER_TOKEN（SID より優先）。SID は
`domo login -i <instance>` 後に docs/setup-guide.md のセッションSID取得手順で設定する（ワークスペース非依存）。
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional, Tuple


INSTANCE = (os.environ.get("INSTANCE") or os.environ.get("DOMO_INSTANCE") or "maintenance-instance.domo.com").strip()
SID = (os.environ.get("SID") or "").strip()
TOKEN = (os.environ.get("DOMO_DEVELOPER_TOKEN") or "").strip()


# --------------------------------------------------------------------------- #
# サンドボックス隔離（ハンズオン参加者ごと・バックエンド完全隔離）
# PL_SANDBOX_SUFFIX を1個設定すると、保存CE・統合サブWF・WF-01・AppDB 業務コレクション名の
# すべてにサフィックス（検証・氏名）が付き、同一インスタンス（maintenance-instance）上で本番や他参加者と
# 衝突しない。provision_domo.py と同じ PL_SANDBOX_SUFFIX を読む（データ層＝DataFlow/4出力/AppDB/
# dedupe CE と、ここ＝WF層で名前が揃う＝バックエンド全体が1つの名札で隔離される）。未設定（既定）
# なら従来挙動を一切変えない。公開関数名 pl_report_api・report_type・doc_key・データセット alias
# （summary/detail/trend/dept）・WF内部変数IDは契約として不変（_sx で包まない）。
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


def _guard_provision_write() -> None:
    """provision --apply（名称ベース・サンドボックス対応）用の本番保護ガード。

    保守用共有インスタンス（maintenance-instance）で名札なしに本番名のワークフロー層を作成/更新するのを防ぐ。
    名札（PL_SANDBOX_SUFFIX）を付ければ全オブジェクト名が一意化され安全に通る。顧客が自分の
    インスタンスへ配備する場合（INSTANCE != maintenance-instance）は対象外＝従来どおり動く。"""
    if _norm_instance() == MAINTENANCE_INSTANCE and not SANDBOX and not _allow_production():
        raise SystemExit(
            "PL_SANDBOX_SUFFIX が未設定のまま保守用インスタンス（maintenance-instance）の本番ワークフロー層を"
            "配備しようとしています。ハンズオンでは名札を付けてください（本番や他参加者と別名になり衝突しません）:\n"
            "  export PL_SANDBOX_SUFFIX='検証・<あなたの氏名>'\n"
            "顧客が自分の環境へ配備する場合は、まず自分のインスタンスを指定してください"
            "（export DOMO_INSTANCE=<your-instance>.domo.com・既定の maintenance-instance は配布元の保守用）。\n"
            "⚠本番メンテナが本番名のまま配備する場合のみ PL_ALLOW_PRODUCTION=1 を明示してください（本番を上書きします）。")


def _guard_maintenance_write(cmd: str) -> None:
    """ce/subflow/mainflow/delete-wf03（固定の本番モデルID対象）用のガード。

    これらは `PL_WF01_MODEL_ID` 等で固定した既存モデルを直接書き換えるためサンドボックスで隔離できない。
    よって名札運用では `provision`（名称で自分専用の CE/WF を発見/作成）へ誘導し、maintenance-instance では
    本番メンテナのみ `PL_ALLOW_PRODUCTION=1` で許可する。"""
    if SANDBOX:
        raise SystemExit(
            f"`{cmd}` は固定の本番モデルID（WF-01／統合サブWF／保存CE）を対象にするため、サンドボックスでは使えません。\n"
            f"PL_SANDBOX_SUFFIX を設定したサンドボックス運用では `provision` を使ってください"
            f"（CE・統合サブWF・WF-01 を名称で発見/新規作成し、自分専用のスタックを配備します）。")
    if _norm_instance() == MAINTENANCE_INSTANCE and not _allow_production():
        raise SystemExit(
            f"保守用インスタンス（maintenance-instance）の本番ワークフロー層を `{cmd}` で書き換えます。\n"
            f"⚠本番メンテナのみ PL_ALLOW_PRODUCTION=1 を明示してください。")


ROOT = pathlib.Path(__file__).resolve().parents[1]
CE_PATH = ROOT / "code-engine" / "report_api.py"
STORE_PROMPT_PATH = ROOT / "prompts" / "prompt_wf02_store.md"
COMPANY_PROMPT_PATH = ROOT / "prompts" / "prompt_wf03_summary.md"
SEND_EMAIL_TOOL_PATH = ROOT / "workflow" / "send_email_tool.json"
MANIFEST_PATH = ROOT / "pro-code" / "manifest.json"

# --- 既存のライブ資産 ID（maintenance-instance の現行デモ）。別インスタンスでは env で差し替える。 ---
WF01_MODEL_ID = os.environ.get("PL_WF01_MODEL_ID", "d60ac21b-e1c7-4e6d-bffd-e904e39ac27d")
SUBFLOW_MODEL_ID = os.environ.get("PL_SUBFLOW_MODEL_ID", "cf3b78c2-eed1-4f55-a7d5-8004a36fbe39")  # 旧 WF-02 を再利用
WF03_MODEL_ID = os.environ.get("PL_WF03_MODEL_ID", "d35c9b64-af04-478a-84e3-bd6bd63644c9")  # 削除対象
SUBFLOW_NAME = _sx(os.environ.get("PL_SUBFLOW_NAME", "WF-02｜店舗損益AIレポート生成（店舗/全社）"))
WF01_MODEL_NAME = _sx(os.environ.get("PL_WF01_MODEL_NAME", "WF-01｜店舗損益AIメイン (Loop→Sub)"))
BUSINESS_COLLECTION_NAME = _sx(os.environ.get("PL_BUSINESS_COLLECTION", "店舗別損益AI要約"))
SNAPSHOT_WF01_PATH = ROOT / "workflow" / "WF-01_main_loop.json"  # 新規インスタンス用の seed（インスタンス非依存へ再束縛）
REPORT_API_PACKAGE_NAME = _sx(os.environ.get("PL_REPORT_API_PKG", "店舗別損益AI要約｜レポートAPI"))
FUNCTION_NAME = "pl_report_api"  # ⚠契約（公開関数名）＝名札でも不変。_sx で包まない。

# --- 統合サブ Workflow の内部変数 ID（既存テンプレート由来。prompt.value が参照するため固定）。---
VAR_COLLECTION = "lZNswzDwqxbJuDs"      # CollectionId（text）
VAR_PROMPT = "qCugVmcafngJTgJ"          # AiPromptText（text・両ブランチ共通の入力テキスト）
VAR_REPORT_TYPE = "var_report_type"     # report_type（text・分岐キー）
VAR_STORE_RESULT = "CvZsFxVZMOqYtMv"    # 店舗AIの結果（object）
VAR_COMPANY_RESULT = "var_company_result"  # 全社AIの結果（object）
INPUT_COLLECTION_ID = "input_CollectionId"
INPUT_PROMPT_ID = "input_AiPromptText"
INPUT_REPORT_TYPE_ID = "input_report_type"

# 待機（タイマー）秒数。reference-app を踏襲（子=5秒 / 親ループ=15秒）。
# 親ループの15秒は WF-02 を wait:False で非同期投入する際の同時実行数を抑え、AI 書込みの
# 一時失敗（従来 10〜15% 取りこぼし→2回実行で収束）を平準化する。デモ速度と信頼性のレバー。
CHILD_SETTLE_SECONDS = int(os.environ.get("PL_CHILD_SETTLE_SECONDS", "5"))
PARENT_INTERVAL_SECONDS = int(os.environ.get("PL_PARENT_INTERVAL_SECONDS", "15"))

# AI エージェントの参照データセット（manifest の alias→ID）。空 context だと AI_AGENT は実行失敗する。
CONTEXT_DATASET_ALIASES: Tuple[str, ...] = ("summary", "detail")

# 旧 WF-01 の先頭に組み込まれていた重複除去 CE（撤去対象）の識別子。別インスタンスでは env で差替、
# 一致ノードが無ければ撤去は no-op（新規/撤去済みインスタンスでも安全）。
DEDUPE_CE_PACKAGE_ID = os.environ.get("PL_DEDUPE_CE_PACKAGE_ID", "4c3f8e59-5fe7-4bb2-b0cd-0959b5efae25")
# 全社ブランチのメール宛先（カンマ区切りの Domo person ID）。配布物には焼き込まず env で注入する。
EMAIL_PERSON_RECIPIENTS = os.environ.get("PL_EMAIL_PERSON_RECIPIENTS", "").strip()


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def request(method: str, path: str, body: Any = None) -> Any:
    url = path if path.startswith("http") else f"https://{INSTANCE}/{path.lstrip('/')}"
    if TOKEN:
        headers = {"X-DOMO-Developer-Token": TOKEN, "Accept": "application/json"}
    elif SID:
        headers = {"X-Domo-Authentication": SID, "Accept": "application/json"}
    else:
        raise SystemExit("認証情報がありません。DOMO_DEVELOPER_TOKEN または SID を環境変数で設定してください（取得は docs/setup-guide.md 参照）。")
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            raw = response.read()
            if not raw:
                return None
            if raw[:1] in (b"{", b"[") or "json" in response.headers.get("content-type", ""):
                return json.loads(raw)
            return raw.decode(errors="replace")
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"{method.upper()} {urllib.parse.urlsplit(url).path} -> HTTP {error.code}: {detail[:500]}") from error


def items(value: Any, *keys: str) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in keys + ("items", "data", "results", "packages", "models", "versions"):
            if isinstance(value.get(key), list):
                return [row for row in value[key] if isinstance(row, dict)]
    return []


def gen_id() -> str:
    return uuid.uuid4().hex[:15]


def asset_id(row: Dict[str, Any]) -> str:
    return str(row.get("id") or row.get("guid") or "")


def version_key(value: str) -> Tuple[int, int, int]:
    parts = [int(p) for p in re.findall(r"\d+", str(value))[:3]]
    return tuple((parts + [0, 0, 0])[:3])


def next_patch(value: str) -> str:
    major, minor, patch = version_key(value)
    return f"{major}.{minor}.{patch + 1}"


def model_meta(model_id: str) -> Dict[str, Any]:
    return request("GET", f"api/workflow/v1/models/{model_id}") or {}


def active_version(model_id: str) -> Tuple[str, str]:
    versions = [r for r in model_meta(model_id).get("versions") or [] if isinstance(r, dict)]
    active = [r for r in versions if r.get("active")]
    row = max(active or versions, key=lambda r: version_key(str(r.get("version") or "0.0.0")), default={})
    return str(row.get("version") or ""), str(row.get("manualTriggerId") or "")


def highest_version(model_id: str) -> str:
    versions = [str(r.get("version") or "0.0.0") for r in model_meta(model_id).get("versions") or []]
    return max(versions, key=version_key) if versions else "1.0.0"


def list_models() -> List[Dict[str, Any]]:
    offset, page, rows = 0, 1000, []
    while True:
        batch = items(request("GET", f"api/workflow/v1/models?limit={page}&offset={offset}"), "models")
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page


def ensure_model(name: str, description: str, apply: bool) -> Tuple[str, bool]:
    """Workflow モデルを**名前で発見、無ければ新規作成**する（inventory の ensure_workflow_model 相当）。

    戻り値 `(model_id, found)`。`found=True` は既存を再利用（他人作成でも削除・作り直ししない）。
    `found=False` は未存在（＝呼び出し側は snapshot を seed に版 1.0.0 を建てる）。dry-run で未存在なら
    `("", False)` を返す（PUT しないので id 不要・ビルドは snapshot seed で成立する）。これにより新規
    （空）顧客インスタンスでもゼロからモデルを建てられる。
    """
    found = next((m for m in list_models() if m.get("name") == name), None)
    if found:
        return asset_id(found), True
    if not apply:
        return "", False
    created = request("POST", "api/workflow/v2/models", {"name": name, "description": description}) or {}
    mid = asset_id(created)
    if not mid:
        raise RuntimeError(f"Workflow モデル作成の応答に id がありません: {name}")
    print(f"  created workflow model by name '{name}': {mid}", flush=True)
    return mid, False


def resolve_collection_id() -> str:
    """AppDB 業務コレクション（店舗別損益AI要約）を名前で発見して UUID を返す（インスタンス非依存）。"""
    cols = items(request("GET", "api/datastores/v1/collections?limit=1000&offset=0"), "collections")
    row = next((c for c in cols if c.get("name") == BUSINESS_COLLECTION_NAME), {})
    return asset_id(row)


def put_version_create_aware(model_id: str, definition: Dict[str, Any], label: str,
                             apply: bool, release: bool, created_new: bool) -> str:
    """新規モデルは最初の版 1.0.0 を、既存モデルは次 patch を作って PUT→round-trip 検証→（任意）release。"""
    if not apply:
        print(f"  [dry-run] {label}: PUT せず（--apply で実行）", flush=True)
        return ""
    versions = model_meta(model_id).get("versions") or []
    target = "1.0.0" if (created_new or not versions) else next_patch(highest_version(model_id))
    request("POST", f"api/workflow/v2/models/{model_id}/versions", {"version": target})
    request("PUT", f"api/workflow/v2/models/{model_id}/versions/{target}/definition", definition)
    verify_roundtrip(model_id, target, definition, f"{label} v{target}")
    if release:
        request("POST", f"api/workflow/v2/models/{model_id}/versions/{target}/release", {})
        print(f"  released {label} v{target}", flush=True)
    else:
        print(f"  draft {label} v{target}（未 release）", flush=True)
    return target


def get_definition(model_id: str, version: str) -> Dict[str, Any]:
    definition = request("GET", f"api/workflow/v2/models/{model_id}/versions/{version}/definition") or {}
    if isinstance(definition.get("savedJson"), str):
        definition = json.loads(definition["savedJson"])
    return copy.deepcopy(definition)


def dataset_ids() -> Dict[str, str]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {str(r.get("alias") or ""): str(r.get("dataSetId") or "") for r in manifest.get("datasetsMapping") or []}


def build_instructions(md_path: pathlib.Path) -> str:
    """正本 .md → システムプロンプト文字列。先頭の blockquote 注記（> 行）を除去する。"""
    text = md_path.read_text(encoding="utf-8")
    kept = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    out = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"


# --------------------------------------------------------------------------- #
# Code Engine: pl_report_api（公開1関数）
# --------------------------------------------------------------------------- #
def function_manifest() -> List[Dict[str, Any]]:
    object_output = {"name": "result", "displayName": "result", "type": "object", "value": None,
                     "nullable": True, "isList": False, "children": [], "entitySubType": None}
    return [{
        "name": FUNCTION_NAME, "displayName": FUNCTION_NAME,
        "description": "店舗別損益AIレポートの検証(validate)・保存(save)の単一入口。save は AppDB 保存＋同一 doc_key の旧版削除を内包する。",
        "isPrivate": False,
        "inputs": [
            {"name": "operation", "displayName": "operation", "type": "text", "value": None,
             "nullable": True, "isList": False, "children": [], "entitySubType": None},
            {"name": "request", "displayName": "request", "type": "object", "value": None,
             "nullable": True, "isList": False, "children": [], "entitySubType": None},
        ],
        "output": copy.deepcopy(object_output),
    }]


def ensure_report_api_package(apply: bool) -> Tuple[str, str]:
    source = CE_PATH.read_text(encoding="utf-8")
    packages = items(request("GET", "api/codeengine/v2/packages?limit=1000&offset=0"), "packages")
    package = next((r for r in packages if r.get("name") == REPORT_API_PACKAGE_NAME), None)
    if not package:
        if not apply:
            return "", ""
        created = request("POST", "api/codeengine/v2/packages", {
            "name": REPORT_API_PACKAGE_NAME,
            "description": "店舗別損益AIレポートの保存API（pl_report_api）。保存に重複除去を内包。",
            "language": "PYTHON", "environment": "LAMBDA", "code": source,
            "manifest": {"functions": function_manifest()},
        }) or {}
        version = str(created.get("version") or "1.0.0")
        request("POST", f"api/codeengine/v2/packages/{asset_id(created)}/versions/{version}/release", {})
        print(f"created Code Engine: {REPORT_API_PACKAGE_NAME} v{version}", flush=True)
        return asset_id(created), version

    package_id = asset_id(package)
    latest = request("GET", f"api/codeengine/v2/packages/{package_id}/versions/latest?parts=code,functions,configuration") or {}
    version = str(latest.get("version") or package.get("version") or "1.0.0")
    deployed_public = {str(r.get("name")) for r in (latest.get("functions") or []) if not r.get("isPrivate")}
    desired_public = {str(r.get("name")) for r in function_manifest() if not r.get("isPrivate")}
    if str(latest.get("code") or "") == source and deployed_public == desired_public:
        print(f"reused Code Engine: {REPORT_API_PACKAGE_NAME} v{version}", flush=True)
        return package_id, version
    if not apply:
        return package_id, version
    all_versions = items(request("GET", f"api/codeengine/v2/packages/{package_id}/versions?limit=1000&offset=0"), "versions")
    highest = max([version] + [str(v.get("version") or "") for v in all_versions if v.get("version")], key=version_key)
    target = next_patch(highest)
    created = request("POST", f"api/codeengine/v2/packages/{package_id}/versions", {
        "version": target, "code": source, "functions": function_manifest(),
        "configuration": latest.get("configuration") or {"accountsMapping": [], "mlModel": [], "externalPackageMapping": {}},
    }) or {}
    version = str(created.get("version") or target)
    request("POST", f"api/codeengine/v2/packages/{package_id}/versions/{version}/release", {})
    print(f"released Code Engine: {REPORT_API_PACKAGE_NAME} v{version}", flush=True)
    return package_id, version


# --------------------------------------------------------------------------- #
# Workflow node builders（control-flow は reference-app の実証済みシェイプ）
# --------------------------------------------------------------------------- #
def wf_var(var_id: str, param_name: str, data_type: str = "text", is_list: bool = False) -> Dict[str, Any]:
    return {"id": var_id, "paramName": param_name, "dataType": data_type, "isList": is_list,
            "children": [], "showChildren": False, "entitySubType": None, "value": None, "isOutput": False}


def form_input(input_id: str, param_name: str, var_id: str) -> Dict[str, Any]:
    return {"id": input_id, "paramName": param_name, "acceptsInput": False, "useExternalValues": False,
            "dataType": "text", "mappedTo": var_id, "value": None, "fieldOptionsMappedTo": None,
            "fieldOptionsValue": None, "datasetMapping": None, "required": True, "children": [],
            "displayName": param_name, "visible": True, "formFieldId": str(uuid.uuid4()), "formFieldType": None,
            "flag": "input", "customMappingType": "form_start", "entitySubType": None, "isList": False,
            "configType": "forms"}


def root_node(title: str) -> Dict[str, Any]:
    return {"id": "rootNode", "position": {"x": 360, "y": 40}, "data": {
        "dimensions": {"width": 200, "height": 60}, "title": title, "description": "",
        "type": "Start", "_designNode": "rootNode", "isFormStart": True,
        "input": [form_input(INPUT_COLLECTION_ID, "CollectionId", VAR_COLLECTION),
                  form_input(INPUT_PROMPT_ID, "AiPromptText", VAR_PROMPT),
                  form_input(INPUT_REPORT_TYPE_ID, "report_type", VAR_REPORT_TYPE)],
        "output": [], "formId": str(uuid.uuid4()), "formTitle": "null", "formDescription": "null",
    }, "style": {"zIndex": 4, "outline": "none"}, "index": 0, "type": "rootNode"}


def end_node(x: int, index: int, node_id: str = "endNode", y: int = 640) -> Dict[str, Any]:
    return {"id": node_id, "position": {"x": x, "y": y}, "data": {
        "dimensions": {"width": 200, "height": 60}, "title": "終了", "description": "",
        "_designNode": "endNode", "terminating": False,
    }, "style": {"zIndex": 4, "outline": "none"}, "index": index, "type": "endNode"}


def edge(source: str, target: str, index: int) -> Dict[str, Any]:
    return {"id": f"edge-{source}-{target}", "source": source, "target": target,
            "data": {"sourcePosition": "right", "targetPosition": "left", "path": [], "title": ""},
            "style": {"zIndex": 5}, "index": index, "arrowHeadType": "arrow", "type": "defaultEdge"}


def timer_node(node_id: str, seconds: int, x: int, y: int, index: int, title: str) -> Dict[str, Any]:
    """ISO-8601 duration タイマー（intermediateCatchEventNode）。実証済みシェイプ。"""
    return {"id": node_id, "position": {"x": x, "y": y}, "data": {
        "dimensions": {"width": 200, "height": 60}, "title": title, "description": "",
        "_designNode": "intermediateCatchEventNode", "configType": "timer", "input": [{
            "id": gen_id(), "paramName": "setting", "dataType": "duration", "mappedTo": None,
            "value": f"PT{seconds}S", "required": True, "isList": False, "children": [],
            "displayName": "設定", "visible": True, "flag": "input", "customMappingType": None,
            "configType": None, "entitySubType": None, "aiDescription": None,
        }], "interrupting": True,
    }, "style": {"zIndex": 4, "outline": "none"}, "index": index, "type": "intermediateCatchEventNode"}


def gateway_node(node_id: str, title: str, x: int, y: int, index: int) -> Dict[str, Any]:
    return {"id": node_id, "position": {"x": x, "y": y}, "data": {
        "dimensions": {"width": 200, "height": 60}, "title": title, "description": "",
        "_designNode": "conditionalGatewayNode", "inclusive": False,
    }, "style": {"zIndex": 3, "outline": "none"}, "index": index, "type": "conditionalGatewayNode"}


def condition_edge(source: str, target: str, index: int, *, title: str, node_id: str,
                   position: Dict[str, int], path: List[List[int]], advanced: bool = False,
                   source_position: str = "right", target_position: str = "left",
                   entry_position: str = "right", exit_position: str = "left",
                   split_index: int = 1) -> Dict[str, Any]:
    return {"id": f"edge-{source}-{target}", "source": source, "target": target, "data": {
        "sourcePosition": source_position, "targetPosition": target_position, "path": path,
        "entryPosition": entry_position, "exitPosition": exit_position, "description": "", "title": title,
        "type": "Advanced" if advanced else "Default", "nodeId": node_id, "position": position,
        "dimensions": {"width": 200, "height": 40}, "splitIndex": split_index, "_designNode": "condition",
    }, "style": {}, "index": index, "arrowHeadType": "arrow", "type": "conditionEdge"}


def report_type_rule(value: str) -> List[Dict[str, Any]]:
    """`= report_type = "<value>"` の FEEL 分岐ルール（Advanced エッジ用）。"""
    return [{"type": "paragraph", "children": [
        {"text": "= ", "bold": False, "italic": False, "underlined": False, "sql": False},
        {"type": "variable", "children": [{"text": "", "bold": False, "italic": False, "underlined": False, "sql": False}],
         "dataType": "text", "id": VAR_REPORT_TYPE, "name": "report_type", "isList": False},
        {"text": f' = "{value}"', "bold": False, "italic": False, "underlined": False, "sql": False},
    ]}]


def prompt_value() -> List[Dict[str, Any]]:
    """AI_AGENT の prompt.value（CollectionId と AiPromptText を注入）。既存 WF-02 の形を踏襲。"""
    def para(text: str) -> Dict[str, Any]:
        return {"type": "paragraph", "children": [{"text": text, "bold": False, "italic": False, "underlined": False, "sql": False}]}

    def var_ref(var_id: str, name: str) -> Dict[str, Any]:
        return {"type": "variable", "children": [{"text": "", "bold": False, "italic": False, "underlined": False, "sql": False}],
                "dataType": "text", "id": var_id, "name": name, "isList": False}

    blank = {"text": "", "bold": False, "italic": False, "underlined": False, "sql": False}
    return [
        para("入力変数："),
        {"type": "paragraph", "children": [blank | {"text": "collection_id: "}, var_ref(VAR_COLLECTION, "CollectionId"), dict(blank)]},
        para("これはAppDBコレクションID（文字列）です。保存は pl_report_api(operation=\"save\", request={collection_id, document}) で行う。"),
        para(""),
        para("以下のデータに基づいて分析を行ってください。"),
        para("<data>"),
        {"type": "paragraph", "children": [dict(blank), var_ref(VAR_PROMPT, "AiPromptText"), dict(blank)]},
        para("</data>"),
    ]


def pl_report_api_tool(package_id: str, package_version: str) -> Dict[str, Any]:
    """公開1関数 pl_report_api を呼ぶ保存ツール。AI が operation=\"save\" で保存する。"""
    def field(param_name: str, data_type: str) -> Dict[str, Any]:
        return {"id": gen_id(), "paramName": param_name, "dataType": data_type, "mappedTo": None, "value": None,
                "required": True, "isList": False, "children": [], "displayName": param_name, "visible": True,
                "flag": "input", "customMappingType": None, "configType": None, "entitySubType": None, "aiDescription": None}

    operation = field("operation", "text")
    req = field("request", "object")
    output = {"id": gen_id(), "paramName": "result", "dataType": "object", "mappedTo": None, "value": None,
              "required": False, "isList": False, "children": [], "displayName": "result", "visible": True,
              "flag": "output", "customMappingType": None, "configType": None, "entitySubType": None, "aiDescription": None}
    return {
        "functionName": FUNCTION_NAME,
        "functionDescription": "店舗別損益AIレポートの保存（AppDB保存＋同一doc_keyの旧版削除）",
        "inputs": [operation, req],
        "inputDescriptions": {
            operation["id"]: '操作名。"save"（レポート保存＋同一doc_keyの旧版削除）を入れる。',
            req["id"]: 'JSONオブジェクト {collection_id: AppDBコレクションのUUID（入力変数 collection_id をそのまま）, document: 作成した最終レポートJSON（フラット・content キー禁止）}',
        },
        "id": gen_id(), "name": "pl_report_api",
        "description": "店舗別損益AIレポートの検証(validate)・保存(save)を operation で切り替える単一ツール",
        "packageId": package_id, "packageVersion": package_version, "output": output, "type": "FUNCTION",
    }


def send_email_tool() -> Dict[str, Any]:
    """全社ブランチ用 Send Email 組込みツール。配布安全化のため実シェイプを2点だけ動的化する。

    設計思想「インスタンスに合わせて解決し、成功を偽装しない」:
    - packageVersion: 配備先の Send Email パッケージの最新版を解決（固定版の取り違え＝バインド失敗を防ぐ）。
      宛先は personRecipients（person 型・**全版で list のまま＝シェイプ無変化**）を使うため、2.1.17+ で
      recipientEmails が list 化しても影響を受けない（inventory の recipientEmails 経路とは別物。隔離テストで
      2.1.18＋personRecipients の AI エージェント送信が COMPLETED を実測）。
    - personRecipients: env `PL_EMAIL_PERSON_RECIPIENTS`（カンマ区切り person ID）があれば注入する。
      配布物（send_email_tool.json）には実在の個人IDを焼き込まない。**未設定なら宛先ゼロで配備し、その旨を
      配備時に大きく警告する**（プロンプトは宛先を創作せずスキップ＝WF は COMPLETED でもメールは出さない）。
    """
    tool = json.loads(SEND_EMAIL_TOOL_PATH.read_text(encoding="utf-8"))
    pkg_id = str(tool.get("packageId") or "")
    try:
        latest = request("GET", f"api/codeengine/v2/packages/{pkg_id}/versions/latest") or {}
        if isinstance(latest, dict) and latest.get("version"):
            tool["packageVersion"] = str(latest["version"])
    except Exception:
        pass  # 解決失敗（dry-run/権限）時はファイルの版を使う
    if EMAIL_PERSON_RECIPIENTS:
        recipients = [r.strip() for r in EMAIL_PERSON_RECIPIENTS.split(",") if r.strip()]
        for field in tool.get("inputs") or []:
            if field.get("paramName") == "personRecipients":
                field["value"] = recipients
        print(f"  Send Email 宛先: personRecipients に {len(recipients)} 件を束縛", flush=True)
    else:
        # 設計思想「成功を偽装しない — 宛先が無いことは配備時に大きく知らせる」。
        # 未設定だと全社ブランチの Send Email は宛先ゼロで、プロンプトに従い AI は送信をスキップする
        # （宛先の創作はしない）。WF は COMPLETED になるがメールは届かない。これを“静かに”で終わらせない。
        print("  ⚠ PL_EMAIL_PERSON_RECIPIENTS 未設定 — 全社レポートのメール通知は送信されません"
              "（宛先なし。AI は宛先を創作せずスキップ）。メールを送るには person ID をカンマ区切りで "
              "`export PL_EMAIL_PERSON_RECIPIENTS=<id1,id2>` を設定して再配備してください"
              "（person ID の調べ方は docs/setup-guide.md STEP 6）。", flush=True)
    return tool


def ai_agent_node(node_id: str, title: str, description: str, instructions: str, result_var: str,
                  x: int, y: int, index: int, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
    datasets = [{"id": v} for alias, v in dataset_ids().items() if alias in CONTEXT_DATASET_ALIASES and v]
    result = {"id": gen_id(), "paramName": "result", "dataType": "object", "mappedTo": result_var, "value": None,
              "required": True, "isList": False, "children": [], "displayName": "Result", "visible": True,
              "flag": "output", "customMappingType": None, "configType": None, "entitySubType": None, "aiDescription": None}
    return {"id": node_id, "position": {"x": x, "y": y}, "data": {
        "dimensions": {"width": 200, "height": 60}, "title": title, "description": description,
        "prompt": {"id": gen_id(), "paramName": "prompt", "dataType": "text", "mappedTo": None, "value": prompt_value(),
                   "required": True, "isList": False, "children": [], "displayName": "Prompt", "visible": True,
                   "flag": "input", "customMappingType": None, "configType": None, "entitySubType": None, "aiDescription": None},
        "result": result,
        "agent": {"instructions": instructions, "tools": tools,
                  "context": {"datasets": datasets, "directories": [], "files": [], "isEmpty": not datasets},
                  "outputDescriptions": {result["id"]: "AppDBへ保存した構造化レポート"}},
        "_designNode": "AI_AGENT",
    }, "style": {"zIndex": 4, "outline": "none"}, "index": index, "type": "AI_AGENT"}


def subflow_definition(package_id: str, package_version: str) -> Dict[str, Any]:
    """統合サブ Workflow: 開始 → 待機 → レポート種別？ → 店舗AI(既定)/全社AI → 終了。"""
    store_tool = pl_report_api_tool(package_id, package_version)
    company_tools = [pl_report_api_tool(package_id, package_version), send_email_tool()]

    root = root_node("開始（AIレポート生成）")
    settle = timer_node("child_settle_timer", CHILD_SETTLE_SECONDS, 360, 140, 1,
                        f"{CHILD_SETTLE_SECONDS}秒待機｜AI負荷平準化")
    gateway = gateway_node("report_type_gateway", "レポート種別？", 360, 240, 2)
    store_ai = ai_agent_node("ai_store", "AIエージェント｜店舗レポート生成", "単一店舗の損益レポートを生成しAppDBへ保存",
                             build_instructions(STORE_PROMPT_PATH), VAR_STORE_RESULT, 360, 440, 4, [store_tool])
    company_ai = ai_agent_node("ai_company", "AIエージェント｜全社サマリー生成", "全社損益サマリーを生成しAppDBへ保存・通知",
                               build_instructions(COMPANY_PROMPT_PATH), VAR_COMPANY_RESULT, 580, 440, 3, company_tools)
    end = end_node(360, 5, y=640)

    e_root_timer = edge(root["id"], settle["id"], 6)
    e_root_timer["data"].update({"sourcePosition": "bottom", "targetPosition": "top", "path": [[460, 100], [460, 140]]})
    e_timer_gw = edge(settle["id"], gateway["id"], 7)
    e_timer_gw["data"].update({"sourcePosition": "bottom", "targetPosition": "top", "path": [[460, 200], [460, 240]]})
    # 全社（Advanced・report_type="company"）: ゲート右 → 右コリドー x=680 を下り全社AIの上辺へ。
    e_gw_company = condition_edge(gateway["id"], company_ai["id"], 8, title="全社サマリー", node_id=gen_id(),
                                  position={"x": 580, "y": 310},
                                  path=[[560, 270], [680, 270], [680, 310], [680, 350], [680, 440]],
                                  advanced=True, source_position="right", target_position="top",
                                  entry_position="top", exit_position="bottom", split_index=3)
    e_gw_company["data"]["advancedRule"] = report_type_rule("company")
    # 店舗（既定・Default）: ゲート上辺から本線 x=460 を真下へ。
    e_gw_store = condition_edge(gateway["id"], store_ai["id"], 9, title="店舗レポート", node_id=gen_id(),
                                position={"x": 360, "y": 350},
                                path=[[460, 240], [460, 350], [460, 350], [460, 440]],
                                source_position="top", target_position="top",
                                entry_position="top", exit_position="top", split_index=2)
    e_company_end = edge(company_ai["id"], end["id"], 10)
    e_company_end["data"].update({"sourcePosition": "bottom", "targetPosition": "right", "path": [[680, 500], [680, 670], [560, 670]]})
    e_store_end = edge(store_ai["id"], end["id"], 11)
    e_store_end["data"].update({"sourcePosition": "bottom", "targetPosition": "top", "path": [[460, 500], [460, 640]]})

    elements = [root, settle, gateway, company_ai, store_ai, end,
                e_root_timer, e_timer_gw, e_gw_company, e_gw_store, e_company_end, e_store_end]
    schema_inputs = {
        INPUT_COLLECTION_ID: {"name": "CollectionId", "type": "text", "subType": None, "isList": False,
                              "isNullable": False, "id": INPUT_COLLECTION_ID, "isChild": False, "parent": None},
        INPUT_PROMPT_ID: {"name": "AiPromptText", "type": "text", "subType": None, "isList": False,
                          "isNullable": False, "id": INPUT_PROMPT_ID, "isChild": False, "parent": None},
        INPUT_REPORT_TYPE_ID: {"name": "report_type", "type": "text", "subType": None, "isList": False,
                               "isNullable": False, "id": INPUT_REPORT_TYPE_ID, "isChild": False, "parent": None},
    }
    data_list = [
        wf_var(VAR_COLLECTION, "CollectionId", "text"),
        wf_var(VAR_PROMPT, "AiPromptText", "text"),
        wf_var(VAR_REPORT_TYPE, "report_type", "text"),
        wf_var(VAR_STORE_RESULT, "StoreResult", "object"),
        wf_var(VAR_COMPANY_RESULT, "CompanyResult", "object"),
    ]
    return {"designElements": elements, "dataList": data_list, "version": 2,
            "schema": {"inputs": schema_inputs, "outputs": {}}}


# --------------------------------------------------------------------------- #
# Round-trip verification（reference-app と同じ）
# --------------------------------------------------------------------------- #
def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def verify_roundtrip(model_id: str, version: str, definition: Dict[str, Any], label: str) -> None:
    saved = request("GET", f"api/workflow/v2/models/{model_id}/versions/{version}/definition") or {}
    if isinstance(saved, dict) and isinstance(saved.get("savedJson"), str):
        saved = json.loads(saved["savedJson"])
    expected = definition.get("designElements") or []
    actual = saved.get("designElements") or []
    if len(actual) != len(expected):
        raise RuntimeError(f"{label}: round-trip 要素数不一致（期待 {len(expected)} / 実 {len(actual)}）。release 中止。")
    if {str(e.get("id") or "") for e in actual} != {str(e.get("id") or "") for e in expected}:
        raise RuntimeError(f"{label}: round-trip 要素id不一致。release 中止。")
    if sorted(str(e.get("type") or "") for e in actual) != sorted(str(e.get("type") or "") for e in expected):
        raise RuntimeError(f"{label}: round-trip 要素type不一致。release 中止。")
    def _norm(data: Any) -> Any:
        # AI_AGENT の tools / context.datasets はセット的意味（順序非依存）。Domo が保存時に並べ替えても
        # 偽陰性で release をブロックしないよう、比較前に安定キーでソートする（他のリストは順序を保つ）。
        if not isinstance(data, dict):
            return data
        data = copy.deepcopy(data)
        agent = data.get("agent")
        if isinstance(agent, dict):
            if isinstance(agent.get("tools"), list):
                agent["tools"] = sorted(agent["tools"], key=lambda t: str((t or {}).get("functionName") or (t or {}).get("name") or ""))
            ctx = agent.get("context")
            if isinstance(ctx, dict) and isinstance(ctx.get("datasets"), list):
                ctx["datasets"] = sorted(ctx["datasets"], key=lambda x: str((x or {}).get("id") or ""))
        return data

    by_id = {e["id"]: e for e in actual}
    for e in expected:
        if _canonical(_norm(e.get("data"))) != _canonical(_norm(by_id[e["id"]].get("data"))):
            raise RuntimeError(f"{label}: round-trip data不一致（{e['id']}）。release 中止。")
    if _canonical(saved.get("dataList")) != _canonical(definition.get("dataList")):
        raise RuntimeError(f"{label}: round-trip dataList不一致。release 中止。")
    print(f"  round-trip OK: {label}（{len(actual)} 要素）", flush=True)


def put_new_version(model_id: str, definition: Dict[str, Any], label: str, apply: bool, release: bool) -> str:
    target = next_patch(highest_version(model_id))
    if not apply:
        print(f"  [dry-run] {label}: 次版 v{target} を PUT せず（--apply で実行）", flush=True)
        return target
    request("POST", f"api/workflow/v2/models/{model_id}/versions", {"version": target})
    request("PUT", f"api/workflow/v2/models/{model_id}/versions/{target}/definition", definition)
    verify_roundtrip(model_id, target, definition, f"{label} v{target}")
    if release:
        request("POST", f"api/workflow/v2/models/{model_id}/versions/{target}/release", {})
        print(f"  released {label} v{target}", flush=True)
    else:
        print(f"  draft {label} v{target}（未 release・--release で昇格）", flush=True)
    return target


# --------------------------------------------------------------------------- #
# WF-01 transform
# --------------------------------------------------------------------------- #
# =========================================================================== #
# 数学的レイアウトエンジン（グリッド座標系）
# reference-app のユーザー実証「美配置」を一般化。レイアウトを毎回手直し
# しなくて済むよう、ノードは「レーン(列)×行」のグリッドに置き、エッジはノード中心を通る
# 直交折れ線で結ぶ。座標はすべて下記の定数から算出する（X軸=レーン、Y軸=行×ピッチ）。
# 詳細な数学モデルは本スクリプトの set_grid/route_* と README「レイアウトエンジン」節を参照。
# =========================================================================== #
NODE_W, NODE_H = 200, 60
GRID_Y0, GRID_PITCH = 40, 100          # 行 r の上辺 y = Y0 + r*PITCH
# 列（レーン）の左辺 x（ユーザー実証 v1.0.21 の美配置を正とする）。
#   main=本線 / counter=戻りカウンタ(中心690) / branch=全社サイドブランチ。
#   ⭐counter はその中心(690)が「次店舗へ」ラベル(590+100=690)と一致するよう置く＝チップ→カウンタが
#     真っ直ぐ縦に抜け、線の横ジョグ(段差)が出ない。branch は本線クエリと同じ行に置き、分岐を
#     「真っ直ぐ水平」にする（§2.6）。
LANE_X = {"main": 360, "counter": 590, "branch": 840}
CORRIDOR_LOOP_X = LANE_X["counter"] + NODE_W // 2  # 戻りループの縦コリドー（=カウンタ中心=690）


def _cx(lane: str) -> int:              # ノードの水平中心
    return LANE_X[lane] + NODE_W // 2


def _row_y(row: int) -> int:            # 行→上辺 y
    return GRID_Y0 + row * GRID_PITCH


def _cy(row: int) -> int:               # 行の垂直中心
    return _row_y(row) + NODE_H // 2


def set_grid(node: Dict[str, Any], lane: str, row: int) -> None:
    node["position"] = {"x": LANE_X[lane], "y": _row_y(row)}
    node.setdefault("data", {})["dimensions"] = {"width": NODE_W, "height": NODE_H}


def route_v(lane: str, src_row: int, tgt_row: int) -> Dict[str, Any]:
    """同一レーンの縦エッジ（上→下）。中心 x を通る bottom→top。"""
    cx = _cx(lane)
    return {"sourcePosition": "bottom", "targetPosition": "top",
            "path": [[cx, _row_y(src_row) + NODE_H], [cx, _row_y(tgt_row)]]}


def route_h(src_lane: str, tgt_lane: str, row: int) -> Dict[str, Any]:
    """同一行の水平エッジ（本線→サイドブランチの並列フォーク等）。src 右辺 → tgt 左辺を真っ直ぐ。
    サイドブランチの先頭をフォーク元と**同じ行**に置くことで、分岐が折れ曲がらない直線になる（v1.0.21）。"""
    return {"sourcePosition": "right", "targetPosition": "left",
            "path": [[LANE_X[src_lane] + NODE_W, _cy(row)], [LANE_X[tgt_lane], _cy(row)]]}


def route_gw_end(gw_row: int, end_row: int) -> Dict[str, Any]:
    """分岐ゲートウェイ下 → 終了（本線直下）。中心 x=460 の縦直線（間隔ぶんの中継点を2つ入れて安定）。"""
    cx = _cx("main")
    gy, ey = _row_y(gw_row) + NODE_H, _row_y(end_row)
    return {"sourcePosition": "bottom", "targetPosition": "top", "entryPosition": "top",
            "exitPosition": "bottom", "path": [[cx, gy], [cx, gy + 50], [cx, ey - 50], [cx, ey]]}


def route_gw_counter(gw_row: int, counter_row: int) -> Dict[str, Any]:
    """分岐ゲートウェイ右 → カウンタ左辺 → 小さな対角で戻りコリドー(=カウンタ中心) → カウンタ下辺。

    カウンタ中心(CORRIDOR_LOOP_X=690)まで入ってから真上にカウンタ下辺へ抜ける。対角(短い斜め)で
    折れ点を1つに抑え、ラベルチップ中心(690)と縦線が一致＝線の横ジョグ(段差)が出ない（v1.0.21）。"""
    g_r = LANE_X["main"] + NODE_W
    cy = _cy(gw_row)
    return {"sourcePosition": "right", "targetPosition": "bottom", "entryPosition": "left",
            "exitPosition": "top", "path": [[g_r, cy], [LANE_X["counter"], cy],
                                            [CORRIDOR_LOOP_X, cy - 20], [CORRIDOR_LOOP_X, _row_y(counter_row) + NODE_H]]}


def route_loop_back(counter_row: int, tgt_row: int) -> Dict[str, Any]:
    """カウンタ上辺 → 戻りコリドー上がり → 本線ノード右辺（ループバック）。"""
    t_r = LANE_X["main"] + NODE_W
    return {"sourcePosition": "top", "targetPosition": "right",
            "path": [[CORRIDOR_LOOP_X, _row_y(counter_row)], [CORRIDOR_LOOP_X, _cy(tgt_row)], [t_r, _cy(tgt_row)]]}


CHIP_W, CHIP_H = 200, 40   # 条件エッジのラベルチップ寸法（Domo 既定）


def validate_layout(definition: Dict[str, Any]) -> List[str]:
    """オフライン検証（ラベルチップも対象）: ①ノード同士の重なり ②ラベルチップがノード/他チップに
    重なる ③エッジ経路が無関係ノード／自分以外のラベルチップを貫く、を総当たりで機械確認する。
    「次店舗へ」チップが縦コリドーに食い込む／宙に浮く類の崩れを検出する（従来はノードのみ検査で見逃した）。
    """
    els = definition.get("designElements") or []
    nodes = [e for e in els if e.get("type") not in ("defaultEdge", "conditionEdge")]
    edges = [e for e in els if e.get("type") in ("defaultEdge", "conditionEdge")]
    node_rects = {}
    for n in nodes:
        p = n.get("position") or {}
        dim = (n.get("data") or {}).get("dimensions") or {"width": NODE_W, "height": NODE_H}
        node_rects[n["id"]] = (p.get("x", 0), p.get("y", 0), dim["width"], dim["height"])
    chips = []  # (ラベル表示名, rect, 所有エッジの id())
    for e in edges:
        pos = (e.get("data") or {}).get("position")
        if pos:
            chips.append((f"label<{(e.get('data') or {}).get('title', '')}>",
                          (pos.get("x", 0), pos.get("y", 0), CHIP_W, CHIP_H), id(e)))
    problems: List[str] = []

    def overlap(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah

    def inside(px, py, r):
        x, y, w, h = r
        return x < px < x + w and y < py < y + h

    nids = list(node_rects)
    for i in range(len(nids)):
        for j in range(i + 1, len(nids)):
            if overlap(node_rects[nids[i]], node_rects[nids[j]]):
                problems.append(f"node overlap: {nids[i]} & {nids[j]}")
    for cid, crect, _ in chips:
        for nid, nrect in node_rects.items():
            if overlap(crect, nrect):
                problems.append(f"{cid} overlaps node {nid}")
    for i in range(len(chips)):
        for j in range(i + 1, len(chips)):
            if overlap(chips[i][1], chips[j][1]):
                problems.append(f"{chips[i][0]} overlaps {chips[j][0]}")
    for e in edges:
        path = (e.get("data") or {}).get("path") or []
        skip = {e.get("source"), e.get("target")}
        own = id(e)
        for k in range(len(path) - 1):
            (x1, y1), (x2, y2) = path[k], path[k + 1]
            for s in range(1, 20):
                px, py = x1 + (x2 - x1) * s / 20.0, y1 + (y2 - y1) * s / 20.0
                for nid, r in node_rects.items():
                    if nid not in skip and inside(px, py, r):
                        problems.append(f"edge {e.get('source')}->{e.get('target')} crosses node {nid}")
                for cid, crect, owner in chips:
                    if owner != own and inside(px, py, crect):
                        problems.append(f"edge {e.get('source')}->{e.get('target')} crosses {cid}")
    return sorted(set(problems))


# =========================================================================== #
# WF-01 を reference-app 流（並列サイドブランチ＋2終了）へ再構成する
# =========================================================================== #
def _ensure_subflow_input(subflow: Dict[str, Any], sub_version: str, report_type: str) -> None:
    """SUB_FLOW ノードを統合モデルへ張替（report_type 付与・prompt 入力名を AiPromptText に統一）。"""
    data = subflow["data"]
    data["modelId"] = SUBFLOW_MODEL_ID
    data["modelVersion"] = sub_version
    prompt_mapped = next((i.get("mappedTo") for i in data.get("input") or []
                          if i.get("paramName") not in ("CollectionId", "report_type")), None)

    def field(name: str, mapped: Optional[str], value: Optional[str]) -> Dict[str, Any]:
        return {"id": gen_id(), "paramName": name, "dataType": "text", "mappedTo": mapped, "value": value,
                "required": True, "isList": False, "children": [], "displayName": name, "visible": True,
                "flag": "input", "customMappingType": None, "configType": None, "entitySubType": None, "aiDescription": None}

    data["input"] = [field("CollectionId", VAR_COLLECTION, None),
                     field("AiPromptText", prompt_mapped, None),
                     field("report_type", None, report_type)]


def ci_style_mainflow_definition(definition: Dict[str, Any], sub_version: str) -> Dict[str, Any]:
    """ライブ WF-01 を reference-app の親Workflow流の「美配置」へ再構成する。

    - **本線＝店舗ループ**: 開始→店舗別SQL→単一店舗取得→各店舗整形→15秒待機→店舗子WF→
      次店舗あり?→終了#1。戻りはカウンタ(次店舗ID)経由。
    - **並列サイドブランチ＝全社**: 店舗別SQL から分岐 → 全店舗SQL→全店舗整形→全社子WF→**終了#2**。
    - **終了ノードは2つ**（本線・全社ブランチが各々独立に終端）。
    ノードは役割（type/functionName/配線）で同定し、data（SQL/指示/配線）は保持。position・
    SUB_FLOW入力・タイトル・終了#2 のみ変更し、座標/経路は数学的レイアウトエンジンで算出する。
    """
    d = copy.deepcopy(definition)
    els = d.get("designElements") or []
    nodes = [e for e in els if e.get("type") not in ("defaultEdge", "conditionEdge")]
    cond_edges = [e for e in els if e.get("type") == "conditionEdge"]

    def svc_fn(e):
        return (e.get("data", {}).get("metadata") or {}).get("functionName")

    # --- 役割同定（ID/タイトルに依存せず type・functionName・変数配線で判定） ---
    root = next(e for e in nodes if e.get("type") == "rootNode")
    gateway = next(e for e in nodes if e.get("type") == "conditionalGatewayNode")
    timer = next(e for e in nodes if e.get("type") == "intermediateCatchEventNode")
    getone = next(e for e in nodes if svc_fn(e) == "getObjectFromList")   # 単一店舗取得
    counter = next(e for e in nodes if svc_fn(e) == "addNumbers")          # 次店舗ID
    texts = [e for e in nodes if svc_fn(e) == "objectToText"]
    queries = [e for e in nodes if e.get("type") == "DATASET_QUERY_TASK"]
    subflows = [e for e in nodes if e.get("type") == "SUB_FLOW"]
    ends = [e for e in nodes if e.get("type") == "endNode"]
    if not (len(texts) >= 2 and len(queries) >= 2 and len(subflows) >= 2 and ends):
        raise RuntimeError("WF-01 の構成ノード（整形2/クエリ2/子WF2/終了）を同定できません。")

    def rt(e):
        return next((i.get("value") for i in e["data"].get("input", []) or [] if i.get("paramName") == "report_type"), None)
    store_sub = next((e for e in subflows if rt(e) == "store"), subflows[0])
    company_sub = next((e for e in subflows if rt(e) == "company"), next(e for e in subflows if e is not store_sub))

    getone_out = (getone["data"].get("output") or [{}])[0].get("mappedTo")
    def text_in(e):
        return next((i.get("mappedTo") for i in e["data"].get("input", []) or [] if i.get("paramName") == "objectValue"), None)
    store_text = next((e for e in texts if text_in(e) == getone_out), texts[0])   # 各店舗整形
    company_text = next(e for e in texts if e is not store_text)                   # 全店舗整形

    getone_list = next((i.get("mappedTo") for i in getone["data"].get("input", []) or [] if i.get("paramName") == "list"), None)
    def qresult(e):
        r = e["data"].get("result")
        return r.get("mappedTo") if isinstance(r, dict) else None
    store_query = next((e for e in queries if qresult(e) == getone_list), queries[0])   # 店舗別SQL（本線）
    company_query = next(e for e in queries if e is not store_query)                      # 全店舗SQL（全社）
    end1 = ends[0]

    # --- 子WF張替＋タイトル整合（配布向け：WF-02/WF-03 名残を解消） ---
    _ensure_subflow_input(store_sub, sub_version, "store")
    _ensure_subflow_input(company_sub, sub_version, "company")
    store_sub["data"]["title"] = "子WF｜店舗レポート生成（report_type=store）"
    company_sub["data"]["title"] = "子WF｜全社サマリー生成（report_type=company）"
    end1["data"]["title"] = "終了（店舗ループ）"
    end2 = end_node(LANE_X["branch"], 0, node_id="branchEndNode")
    end2["data"]["title"] = "終了（全社）"

    # --- グリッド配置（本線=main / カウンタ=counter / 全社=branch） ---
    set_grid(root, "main", 0)
    set_grid(store_query, "main", 1)
    set_grid(getone, "main", 2)
    set_grid(store_text, "main", 3)
    set_grid(timer, "main", 4)
    set_grid(store_sub, "main", 5)
    set_grid(gateway, "main", 6)
    set_grid(end1, "main", 8)
    set_grid(counter, "counter", 4)
    # 全社ブランチは**本線クエリ(店舗別SQL=row1)と同じ row1 から**始める＝分岐が真っ直ぐ水平になる（v1.0.21）。
    set_grid(company_query, "branch", 1)
    set_grid(company_text, "branch", 2)
    set_grid(company_sub, "branch", 3)
    set_grid(end2, "branch", 4)

    # --- ゲートウェイの条件エッジ（ループ判定ロジックを保持し経路だけ再計算） ---
    gw_to_end = next((e for e in cond_edges if e.get("source") == gateway["id"] and e["data"].get("type") == "Default"), None)
    gw_to_counter = next((e for e in cond_edges if e.get("source") == gateway["id"] and e["data"].get("type") == "Advanced"), None)
    if not (gw_to_end and gw_to_counter):
        raise RuntimeError("WF-01 のゲートウェイ条件エッジ（Default/Advanced）を同定できません。")
    gw_to_end["target"] = end1["id"]
    gw_to_end["data"].update(route_gw_end(6, 8))
    # ラベルチップ(200x40)は線の「中心」に来るよう左上を (中心x-100, 中心y-20) に置く。
    # 次店舗なし: ゲート→終了 の縦線(x=460)上・ゲート下辺(700)と終了上辺(840)の中点(770)に中央寄せ。
    gw_to_end["data"]["position"] = {"x": _cx("main") - 100, "y": (_row_y(6) + NODE_H + _row_y(8)) // 2 - 20}
    gw_to_counter["target"] = counter["id"]
    gw_to_counter["data"].update(route_gw_counter(6, 4))
    # 次店舗へ: チップ中心x = CORRIDOR_LOOP_X(=カウンタ中心690) に合わせ、ゲート折れ点の高さ(cy6=670)へ
    # 中央寄せ（左上=中心-100,-20 → (590,650)）。チップ中心xをカウンタ中心に一致させることで「チップ→
    # カウンタ」が真っ直ぐ縦に抜け、横ジョグ（線の段差）が出ない（v1.0.21 ユーザー実証）。
    gw_to_counter["data"]["position"] = {"x": CORRIDOR_LOOP_X - 100, "y": _cy(6) - 20}

    # --- 残りはすべて defaultEdge として本線＋全社ブランチを再構築 ---
    def ve(src, tgt, lane, r0, r1, idx):
        return {**edge(src["id"], tgt["id"], idx), "data": {**edge(src["id"], tgt["id"], idx)["data"], **route_v(lane, r0, r1)}}

    spine = [
        ve(root, store_query, "main", 0, 1, 0),
        ve(store_query, getone, "main", 1, 2, 1),
        ve(getone, store_text, "main", 2, 3, 2),
        ve(store_text, timer, "main", 3, 4, 3),
        ve(timer, store_sub, "main", 4, 5, 4),
        ve(store_sub, gateway, "main", 5, 6, 5),
    ]
    loop_back = {**edge(counter["id"], getone["id"], 6),
                 "data": {**edge(counter["id"], getone["id"], 6)["data"], **route_loop_back(4, 2)}}
    # フォークは本線クエリ(row1)→全社クエリ(row1) の**真っ直ぐ水平**（同一行）。
    fork = {**edge(store_query["id"], company_query["id"], 7),
            "data": {**edge(store_query["id"], company_query["id"], 7)["data"], **route_h("main", "branch", 1)}}
    branch = [
        {**edge(company_query["id"], company_text["id"], 8),
         "data": {**edge(company_query["id"], company_text["id"], 8)["data"], **route_v("branch", 1, 2)}},
        {**edge(company_text["id"], company_sub["id"], 9),
         "data": {**edge(company_text["id"], company_sub["id"], 9)["data"], **route_v("branch", 2, 3)}},
        {**edge(company_sub["id"], end2["id"], 10),
         "data": {**edge(company_sub["id"], end2["id"], 10)["data"], **route_v("branch", 3, 4)}},
    ]

    new_nodes = [root, store_query, getone, store_text, timer, store_sub, gateway, end1,
                 counter, company_query, company_text, company_sub, end2]
    new_edges = spine + [loop_back, fork] + branch + [gw_to_end, gw_to_counter]
    for i, e in enumerate(new_nodes):
        e["index"] = i
    for j, e in enumerate(new_edges):
        e["index"] = len(new_nodes) + j
    d["designElements"] = new_nodes + new_edges
    return d


def build_wf01_definition(sub_model_id: str, sub_version: str, collection_id: str,
                          summary_ds_id: str, wf01_created_new: bool) -> Dict[str, Any]:
    """WF-01 の定義を組む（既存は live を変換、新規は snapshot を seed に）＋インスタンス非依存へ再束縛。

    - 子WF参照（SUB_FLOW）を `sub_model_id` / `sub_version` へ張替。`_ensure_subflow_input` が
      グローバル `SUBFLOW_MODEL_ID` を読むため、変換前にここで確定させる。
    - dataList の CollectionId 変数値と全 DATASET_QUERY_TASK の `dataset.value` を、対象インスタンスの
      実 ID（名称で発見した collection・manifest の summary DS）へ**再束縛**＝保守用インスタンスの GUID を
      顧客環境に焼き込まない。レイアウトは `ci_style_mainflow_definition` が数学エンジンで再算出する。
    """
    global SUBFLOW_MODEL_ID
    if sub_model_id:
        SUBFLOW_MODEL_ID = sub_model_id   # _ensure_subflow_input がこれを読む（変換前に確定）

    if wf01_created_new:
        base = json.loads(SNAPSHOT_WF01_PATH.read_text(encoding="utf-8"))
        if isinstance(base.get("savedJson"), str):
            base = json.loads(base["savedJson"])
        print(f"  seeded WF-01 from snapshot {SNAPSHOT_WF01_PATH.name}", flush=True)
    else:
        cur = highest_version(WF01_MODEL_ID)
        base = get_definition(WF01_MODEL_ID, cur)
        print(f"  transformed WF-01 from live v{cur}", flush=True)

    definition = ci_style_mainflow_definition(base, sub_version)

    # --- インスタンス非依存の再束縛（空の解決値では上書きしない＝snapshot 値を温存） ---
    n_col = n_ds = 0
    for v in definition.get("dataList") or []:
        if v.get("id") == VAR_COLLECTION and collection_id:
            v["value"] = collection_id
            n_col += 1
    for e in definition.get("designElements") or []:
        if e.get("type") == "DATASET_QUERY_TASK" and summary_ds_id:
            ds = (e.get("data") or {}).get("dataset")
            if isinstance(ds, dict):
                ds["value"] = summary_ds_id
                n_ds += 1
    if collection_id:
        bound = [v for v in definition.get("dataList") or [] if v.get("id") == VAR_COLLECTION]
        if any(v.get("value") != collection_id for v in bound):
            raise RuntimeError("CollectionId の再束縛に失敗（dataList に反映されていません）。")
    if summary_ds_id:
        for e in definition.get("designElements") or []:
            if e.get("type") == "DATASET_QUERY_TASK" and (e.get("data") or {}).get("dataset", {}).get("value") != summary_ds_id:
                raise RuntimeError("DATASET_QUERY_TASK の dataset.value 再束縛に失敗。")
    print(f"  rebound CollectionId×{n_col} / query dataset.value×{n_ds} "
          f"(collection={collection_id or '—'}, summary={summary_ds_id or '—'})", flush=True)
    return definition


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_ce(apply: bool, dry_dir: Optional[pathlib.Path]) -> Tuple[str, str]:
    if apply:
        _guard_maintenance_write("ce")
    pkg_id, pkg_ver = ensure_report_api_package(apply)
    print(json.dumps({"codeEngine": {"packageId": pkg_id, "version": pkg_ver, "function": FUNCTION_NAME}}, ensure_ascii=False))
    return pkg_id, pkg_ver


def cmd_subflow(apply: bool, release: bool, dry_dir: Optional[pathlib.Path],
                pkg_id: str = "", pkg_ver: str = "", rename: bool = True) -> str:
    if apply:
        _guard_maintenance_write("subflow")
    if not pkg_id:
        pkg_id, pkg_ver = ensure_report_api_package(apply)
    if not pkg_id and apply:
        raise RuntimeError("Code Engine パッケージIDが解決できません（先に ce を実行）。")
    pkg_id = pkg_id or "__PACKAGE_ID__"
    pkg_ver = pkg_ver or "__PACKAGE_VERSION__"
    definition = subflow_definition(pkg_id, pkg_ver)
    if dry_dir:
        (dry_dir / "subflow_built.json").write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  wrote {dry_dir/'subflow_built.json'}", flush=True)
    if rename and apply:
        request("PUT", f"api/workflow/v1/models/{SUBFLOW_MODEL_ID}", {"name": SUBFLOW_NAME})
        print(f"  renamed sub-workflow model -> {SUBFLOW_NAME}", flush=True)
    version = put_new_version(SUBFLOW_MODEL_ID, definition, "統合サブWF", apply, release)
    return version


def cmd_mainflow(apply: bool, release: bool, dry_dir: Optional[pathlib.Path], sub_version: str) -> str:
    if apply:
        _guard_maintenance_write("mainflow")
    cur_version = highest_version(WF01_MODEL_ID)
    live = get_definition(WF01_MODEL_ID, cur_version)
    definition = ci_style_mainflow_definition(live, sub_version)
    problems = validate_layout(definition)   # オフライン検証（重なり/経路貫通）
    if problems:
        raise RuntimeError("WF-01 レイアウト検証に失敗（PUT しません）:\n  - " + "\n  - ".join(problems))
    print(f"  layout OK: 重なり0・経路貫通0（{len(definition['designElements'])} 要素）", flush=True)
    if dry_dir:
        (dry_dir / "mainflow_built.json").write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  wrote {dry_dir/'mainflow_built.json'} (from live v{cur_version})", flush=True)
    return put_new_version(WF01_MODEL_ID, definition, "WF-01", apply, release)


def cmd_provision(apply: bool, release: bool, dry_dir: Optional[pathlib.Path]) -> Dict[str, Any]:
    """ゼロからの（空の）インスタンスへワークフロー層を配備する: 名前で発見→無ければ作成→
    インスタンス非依存へ再束縛→draft→round-trip検証→(任意)release。

    CI の provision_platform.py 相当の「from-scratch」経路。既存 maintenance-instance では各モデルを**発見して
    再利用**するため、ce/subflow/mainflow を順に流すのと等価に動く（＝移植にも保守にも使える単一経路）。
    前提: 先に `scripts/provision_domo.py` でデータ層（コレクション・データセット・manifest 同期）を作る。
    """
    global SUBFLOW_MODEL_ID, WF01_MODEL_ID

    if apply:
        _guard_provision_write()

    # 1) Code Engine パッケージ（名前で発見/作成は ensure_report_api_package が担う）
    pkg_id, pkg_ver = ensure_report_api_package(apply)
    pkg_id = pkg_id or "__PACKAGE_ID__"
    pkg_ver = pkg_ver or "__PACKAGE_VERSION__"

    # 2) インスタンス固有の束縛を解決（apply 時は欠落を loud に失敗＝保守用GUIDを焼き込まない）
    collection_id = resolve_collection_id()
    summary_ds_id = dataset_ids().get("summary", "")
    if apply and not collection_id:
        raise RuntimeError(
            f"AppDB コレクション '{BUSINESS_COLLECTION_NAME}' が見つかりません。"
            " 先に scripts/provision_domo.py でデータ層を作成してください。")
    if apply and not summary_ds_id:
        raise RuntimeError(
            "manifest.json に summary データセットIDがありません。"
            " 先に scripts/provision_domo.py sync-manifest を実行してください。")

    # 3) 統合サブWF モデル（発見/作成）→ 定義 PUT（新規は版 1.0.0・既存は次 patch）
    sub_id, sub_found = ensure_model(
        SUBFLOW_NAME, "店舗/全社の損益AIレポートを生成（report_type 分岐・保存は pl_report_api）", apply)
    if sub_id:
        SUBFLOW_MODEL_ID = sub_id
    sub_def = subflow_definition(pkg_id, pkg_ver)
    if dry_dir:
        (dry_dir / "provision_subflow.json").write_text(json.dumps(sub_def, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  wrote {dry_dir/'provision_subflow.json'}", flush=True)
    if apply:
        if not sub_found:
            request("PUT", f"api/workflow/v1/models/{SUBFLOW_MODEL_ID}", {"name": SUBFLOW_NAME})
        sub_version = put_version_create_aware(SUBFLOW_MODEL_ID, sub_def, "統合サブWF", apply, release, not sub_found)
    else:
        sub_version = (active_version(SUBFLOW_MODEL_ID)[0] if sub_found else "1.0.0")
        print(f"  [dry-run] 統合サブWF 定義を組立（PUT せず・pin 想定版 v{sub_version}）", flush=True)

    # 4) WF-01 モデル（発見/作成）→ 子WF/束縛を再構築 → レイアウト検証 → PUT
    wf01_id, wf01_found = ensure_model(
        WF01_MODEL_NAME, "店舗損益AIメイン（店舗ループ→統合サブWFを report_type で呼び分け）", apply)
    if wf01_id:
        WF01_MODEL_ID = wf01_id
    definition = build_wf01_definition(SUBFLOW_MODEL_ID, sub_version, collection_id, summary_ds_id, not wf01_found)
    problems = validate_layout(definition)
    if problems:
        raise RuntimeError("WF-01 レイアウト検証に失敗（PUT しません）:\n  - " + "\n  - ".join(problems))
    print(f"  layout OK: 重なり0・経路貫通0（{len(definition['designElements'])} 要素）", flush=True)
    if dry_dir:
        (dry_dir / "provision_wf01.json").write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  wrote {dry_dir/'provision_wf01.json'}", flush=True)
    if apply:
        wf01_version = put_version_create_aware(WF01_MODEL_ID, definition, "WF-01", apply, release, not wf01_found)
    else:
        wf01_version = "1.0.0" if not wf01_found else next_patch(highest_version(WF01_MODEL_ID))
        print("  [dry-run] WF-01 定義を組立（PUT せず）", flush=True)

    out = {"provision": {
        "codeEngine": {"packageId": pkg_id, "version": pkg_ver, "function": FUNCTION_NAME},
        "subflow": {"modelId": SUBFLOW_MODEL_ID, "version": sub_version, "created": not sub_found},
        "wf01": {"modelId": WF01_MODEL_ID, "version": wf01_version, "created": not wf01_found},
        "bindings": {"collectionId": collection_id, "summaryDataset": summary_ds_id},
        "applied": apply, "released": apply and release,
    }}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def cmd_delete_wf03(apply: bool) -> None:
    if apply:
        _guard_maintenance_write("delete-wf03")
    # WF-01 が統合モデルを指していることを確認してから削除する。
    cur = highest_version(WF01_MODEL_ID)
    live = get_definition(WF01_MODEL_ID, cur)
    sub_models = {(e.get("data") or {}).get("modelId") for e in live.get("designElements") or [] if e.get("type") == "SUB_FLOW"}
    if WF03_MODEL_ID in sub_models:
        raise RuntimeError("WF-01 がまだ旧 WF-03 を参照しています。先に mainflow を release してください。")
    if sub_models and sub_models != {SUBFLOW_MODEL_ID}:
        raise RuntimeError(f"WF-01 の SUB_FLOW 参照が想定外です: {sub_models}")
    if not apply:
        print(f"  [dry-run] WF-03 ({WF03_MODEL_ID}) を削除予定", flush=True)
        return
    request("DELETE", f"api/workflow/v2/models/{WF03_MODEL_ID}")
    try:
        gone = request("GET", f"api/workflow/v1/models/{WF03_MODEL_ID}") or {}
        status = f"still present? name={gone.get('name')!r} deletedAt={gone.get('deletedAt')}"
    except RuntimeError as error:
        status = "confirmed removed (404)" if "404" in str(error) else f"post-check error: {error}"
    print(f"  deleted WF-03 model {WF03_MODEL_ID} — {status}", flush=True)


def cmd_verify() -> Dict[str, Any]:
    out: Dict[str, Any] = {"instance": INSTANCE}
    sub_v, _ = active_version(SUBFLOW_MODEL_ID)
    sub_def = get_definition(SUBFLOW_MODEL_ID, sub_v)
    types = [e.get("type") for e in sub_def.get("designElements") or []]
    out["subflow"] = {"modelId": SUBFLOW_MODEL_ID, "version": sub_v, "name": model_meta(SUBFLOW_MODEL_ID).get("name"),
                      "aiAgents": types.count("AI_AGENT"), "timers": sum(1 for e in sub_def.get("designElements") or [] if e.get("type") == "intermediateCatchEventNode"),
                      "gateways": types.count("conditionalGatewayNode")}
    main_v, _ = active_version(WF01_MODEL_ID)
    main_def = get_definition(WF01_MODEL_ID, main_v)
    mels = main_def.get("designElements") or []
    has_dedupe = any((e.get("data") or {}).get("metadata", {}).get("packageId") == DEDUPE_CE_PACKAGE_ID for e in mels)
    sub_refs = [{"modelId": (e.get("data") or {}).get("modelId"), "version": (e.get("data") or {}).get("modelVersion"),
                 "report_type": next((i.get("value") for i in (e.get("data") or {}).get("input") or [] if i.get("paramName") == "report_type"), None)}
                for e in mels if e.get("type") == "SUB_FLOW"]
    out["mainflow"] = {"modelId": WF01_MODEL_ID, "version": main_v,
                       "hasDedupeNode": has_dedupe,
                       "endNodes": sum(1 for e in mels if e.get("type") == "endNode"),
                       "timers": sum(1 for e in mels if e.get("type") == "intermediateCatchEventNode"),
                       "subflowRefs": sub_refs,
                       "layoutProblems": validate_layout(main_def)}
    try:
        wf03 = request("GET", f"api/workflow/v1/models/{WF03_MODEL_ID}") or {}
        out["wf03"] = {"name": wf03.get("name"), "deletedAt": wf03.get("deletedAt"), "versions": len(wf03.get("versions") or [])}
    except RuntimeError as error:
        out["wf03"] = {"status": "deleted (404)"} if "404" in str(error) else {"status": f"error: {error}"}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ce", "subflow", "mainflow", "delete-wf03", "verify", "all", "provision"))
    parser.add_argument("--apply", action="store_true", help="実際に作成/PUT する（無指定は dry-run）")
    parser.add_argument("--release", action="store_true", help="PUT 後に release まで行う")
    parser.add_argument("--dry-dir", default="/tmp/plwf", help="dry-run で組み立てた定義の出力先")
    parser.add_argument("--sub-version", default="", help="mainflow: 統合サブWFの版（省略時は active を解決）")
    args = parser.parse_args()
    dry_dir = pathlib.Path(args.dry_dir)
    dry_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "ce":
        cmd_ce(args.apply, dry_dir)
    elif args.command == "subflow":
        cmd_subflow(args.apply, args.release, dry_dir)
    elif args.command == "mainflow":
        sub_version = args.sub_version or active_version(SUBFLOW_MODEL_ID)[0]
        cmd_mainflow(args.apply, args.release, dry_dir, sub_version)
    elif args.command == "delete-wf03":
        cmd_delete_wf03(args.apply)
    elif args.command == "verify":
        cmd_verify()
    elif args.command == "all":
        pkg_id, pkg_ver = cmd_ce(args.apply, dry_dir)
        sub_version = cmd_subflow(args.apply, args.release, dry_dir, pkg_id, pkg_ver)
        cmd_mainflow(args.apply, args.release, dry_dir, sub_version)
        if args.apply and args.release:
            cmd_delete_wf03(args.apply)
        cmd_verify()
    elif args.command == "provision":
        cmd_provision(args.apply, args.release, dry_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
