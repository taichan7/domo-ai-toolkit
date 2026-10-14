"""AppDB メンテナンス関数（Domo Code Engine）。【レガシー／フロー非配線】

⚠ 2026-10 の統合改修以降、重複除去は保存処理に内包された（`report_api.py` の
`pl_report_api(operation="save")` が保存時に同一 doc_key の旧版を削除する）。本モジュールの
`dedupe_appdb_documents` は **WF-01 のノードから撤去済み**で、現行フローからは呼ばれない。
手動・バッチでのコレクション一括重複除去ユーティリティとして残置しているだけなので、
統合フローの保存系を再デプロイする際は `report_api.py` を使うこと（本ファイルを再配線しない）。

Domo Workflows / Code Engine ランタイムが提供する `codeengine` モジュールで
Domo 内部 API を呼び出す。認証トークンは不要（ランタイムが認証を注入する）ので
シークレット（旧 DOMO_TOKEN）は設定しなくてよい。

保守しやすさのため、公開関数は `dedupe_appdb_documents` の1本のみ。取得・
グループ化・削除の全ロジックをこの関数内にインライン展開している。
"""

import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List

# Domo Code Engine ランタイム提供モジュール（ローカルには存在しない）
import codeengine

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GUID_REGEX = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-(8|9|a|b)[0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)

_PAGE_SIZE = 5000
# bulk 削除は URL 長を抑えるため 100 件ずつに分割する（GUID×100 ≒ 3700 文字）
_DELETE_CHUNK = 100


def dedupe_appdb_documents(collection_id: str) -> Dict[str, Any]:
    """
    AppDB コレクションの重複ドキュメントを除去する。
    content.doc_key ごとに content.generated_at が最新の1件のみを残し、
    それ以外を削除する（全削除ではなく最新1件保持なので途中失敗しても安全）。

    取得（ページング）・グループ化・削除（bulk 分割）を1関数に集約している。

    collection_id は必須引数（ワークフローの CollectionId 変数から渡す）。
    インスタンス非依存にするため既定値は持たない（移植先ごとに正しい ID を渡す）。

    @domoWorkflows {output: "object"}
    """
    if not collection_id or not GUID_REGEX.match(collection_id):
        raise ValueError("collection_id の形式が正しくありません")

    # --- 1. コレクション内の全ドキュメントをページングで取得 ---
    docs: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = (
            f"api/datastores/v1/collections/{collection_id}/documents"
            f"?limit={_PAGE_SIZE}&offset={offset}"
        )
        page = codeengine.send_request("get", url) or []
        docs.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    total = len(docs)

    # --- 2. content.doc_key でグループ化（doc_key を持たない不正データは単独保持） ---
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for d in docs:
        content = d.get("content", {}) or {}
        key = content.get("doc_key")
        if key is None:
            key = f"__nokey__{d.get('id')}"
        groups[key].append(d)

    # --- 3. doc_key ごとに generated_at 最新1件を残し、残りを削除候補にする ---
    to_delete: List[str] = []
    for items in groups.values():
        if len(items) <= 1:
            continue
        items.sort(
            key=lambda x: (x.get("content", {}) or {}).get("generated_at", ""),
            reverse=True,
        )
        for stale in items[1:]:
            doc_id = stale.get("id")
            if doc_id:
                to_delete.append(doc_id)

    # --- 4. bulk エンドポイントで分割削除（途中失敗は継続＝最新1件は保持済み） ---
    deleted = 0
    for i in range(0, len(to_delete), _DELETE_CHUNK):
        chunk = to_delete[i : i + _DELETE_CHUNK]
        id_list = ",".join(chunk)
        url = (
            f"api/datastores/v2/collections/{collection_id}/documents/bulk"
            f"?ids={id_list}"
        )
        try:
            codeengine.send_request("delete", url)
            deleted += len(chunk)
        except Exception as err:  # noqa: BLE001 - 途中失敗は継続（最新1件は保持済み）
            logger.warning("bulk delete failed chunk=%d..%d: %s", i, i + len(chunk), err)

    # --- 5. 結果を集計してログ出力し返す ---
    result = {
        "success": True,
        "collection_id": collection_id,
        "total_before": total,
        "unique_keys": len(groups),
        "delete_candidates": len(to_delete),
        "deleted": deleted,
        "remaining": total - deleted,
    }
    logger.info("dedupe result: %s", json.dumps(result, ensure_ascii=False))
    return result
