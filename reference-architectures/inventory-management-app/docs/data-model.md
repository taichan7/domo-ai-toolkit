# データモデル

## AppDBコレクション

| 論理名 | 物理名 | 主キー相当 | 用途 |
|---|---|---|---|
| 統合在庫レコード | `inventory_management_records` | `record_key` | マスタ、取引、残高、アラートを1コレクションに保存 |

`record_type` と `record_key` は全レコード必須である。フィールドの物理型は [appdb/schemas.json](../appdb/schemas.json) を正とする。

## 共通およびマスタ列

| 列 | 型 | 必須となる `record_type` | 説明 |
|---|---|---|---|
| `record_type` | STRING | 全て | 論理レコード種別 |
| `record_key` | STRING | 全て | `TYPE|business-key` 形式の一意キー |
| `item_code` | STRING | ITEM, TRANSACTION, BALANCE, ALERT_HISTORY | 品目識別子 |
| `item_name` | STRING | ITEM | 品目名。履歴には登録時点の監査表示値も保持 |
| `category` | STRING | ITEM | 品目分類 |
| `unit` | STRING | ITEM | 数量単位 |
| `location_code` | STRING | LOCATION, TRANSACTION, BALANCE, ALERT_HISTORY | ロケーション識別子 |
| `location_name` | STRING | LOCATION | ロケーション名 |
| `zone` | STRING | LOCATION | ゾーン |
| `qr_value` | STRING | ITEM, LOCATION | `ITEM:<code>` または `LOC:<code>` |
| `active` | STRING | ITEM, LOCATION, RULE | `true` / `false`。マスタの有効フラグ。`false`（停止）にすると新規取引を止めるが行自体は残り、`true` に戻せる可逆な状態。`MANAGE_MASTER` の削除はこのフラグ操作ではなくドキュメント自体をAppDBから消す物理削除で、依存データも連鎖削除する（不可逆） |
| `rule_key` | STRING | RULE | `<location_code>|<item_code>` |
| `notification_enabled` | STRING | RULE | 通知接続後の有効フラグ |

## 取引列

| 列 | 型 | 必須 | 説明 |
|---|---|---|---|
| `transaction_id` | STRING | ○ | `TRX-<UUID>` |
| `request_id` | STRING | ○ | クライアントが生成する冗等キー、100文字以内 |
| `transaction_type` | STRING | ○ | `IN`, `OUT` |
| `quantity` | DOUBLE | ○ | 表示用絶対数 |
| `signed_quantity` | DOUBLE | ○ | INは正、OUTは負 |
| `balance_before` | DOUBLE | ○ | 処理前在庫 |
| `balance_after` | DOUBLE | ○ | 処理後在庫 |
| `reason` | STRING |  | 登録理由、200文字以内 |
| `operator_user_id` | STRING | ○ | Code Engine実行情報から取得したDomoユーザーID |
| `operator_name` | STRING | ○ | Domo表示名 |
| `source` | STRING | ○ | `DOMO_WEB`, `DOMO_MOBILE`, `DEMO_SEED` など |
| `occurred_at` | DATETIME | ○ | 業務上の発生時刻、UTC ISO 8601 |
| `created_at` | DATETIME | ○ | AppDBへの登録時刻 |

`request_id` は `TRANSACTION` 内で検索し、同じ値がある場合は新規書込みを行わず先行結果を返す。

## 残高投影列

| 列 | 型 | 必須 | 説明 |
|---|---|---|---|
| `balance_key` | STRING | ○ | `<location_code>|<item_code>` |
| `quantity` | DOUBLE | ○ | 現在庫 |
| `minimum_quantity` | DOUBLE | ○ | RULEから得た基準在庫 |
| `shortage_quantity` | DOUBLE | ○ | `max(minimum_quantity - quantity, 0)` |
| `is_shortage` | STRING | ○ | `true` / `false` |
| `last_transaction_at` | DATETIME | ○ | 最終取引時刻 |
| `updated_at` | DATETIME | ○ | 投影更新時刻 |

## アラート列

| 列 | 型 | 使用種別 | 説明 |
|---|---|---|---|
| `status` | STRING | ALERT_STATE | `NORMAL` / `SHORTAGE` |
| `last_alerted_quantity` | DOUBLE | ALERT_STATE | 最終不足遷移時の数量 |
| `last_alerted_at` | DATETIME | ALERT_STATE | 最終不足遷移時刻 |
| `last_recovered_at` | DATETIME | ALERT_STATE | 最終回復遷移時刻 |
| `alert_id` | STRING | ALERT_HISTORY | `ALERT-<UUID>` |
| `event_type` | STRING | ALERT_HISTORY | `SHORTAGE` / `RECOVERY` / `MANUAL`（手動通知） |
| `current_quantity` | DOUBLE | ALERT_HISTORY | イベント時在庫 |
| `notification_status` | STRING | ALERT_HISTORY | `PENDING` / `STARTED` / `FAILED` / `SKIPPED` |
| `notification_subject` | STRING | ALERT_HISTORY | 固定テンプレート件名 |
| `notification_body` | STRING | ALERT_HISTORY | 固定テンプレート本文 |
| `error_message` | STRING | ALERT_HISTORY | 通知対象外またはWorkflow開始失敗の理由 |
| `workflow_instance_id` | STRING | ALERT_HISTORY | Workflow開始後の実行ID |

## 残高再計算

`TRANSACTION` を `occurred_at` 順に読み、`location_code + item_code` 単位で `signed_quantity` を合計する。最後の `occurred_at` を `last_transaction_at` とし、マスタとRULEから表示名と基準在庫を補う。取引履歴は変更しない。

## DataSet

### 標準同期DataSet

AppDBスキーマの44業務列に、Domoが管理する `__documentId__`, `__createdBy__`, `__created__`, `__modifiedBy__`, `__modified__` が加わる。AppDBコレクションの標準同期のみで生成され、コードから書き込まない。

### ダッシュボードDataSet

| 出力 `record_type` | 粒度 | 主な列 |
|---|---|---|
| `KPI` | 指標×1行 | `metric_key`, `label`, `metric_value` |
| `ITEM_STOCK` | 品目×1行 | `label`, `metric_value` |
| `LOCATION` | ロケーション×1行 | `label`, `metric_value` |
| `TREND` | 日付×1行（7日） | `date_key`, `inbound_quantity`, `outbound_quantity` |
| `SHORTAGE` | 不足残高×1行 | 品目、場所、残高、基準、不足数 |
| `DORMANT` | 30日超の残高×1行 | 品目、場所、残高、`age_days` |
| `ALERT` | 通知履歴×1行 | アラートID、イベント、通知状態、件名 |
| `AI_NOTE` | 品目×ロケーション×1行 | `item_code`, `location_code`, `ai_summary`（AI要約タイルが生成） |

KPIは `TOTAL_QUANTITY`, `ITEM_COUNT`, `SHORTAGE_COUNT`, `TODAY_IN_COUNT`, `TODAY_OUT_COUNT` の5種。出力物理列と型は [datasets/contracts.json](../datasets/contracts.json) と [dataflow/dashboard_transform.py](../dataflow/dashboard_transform.py) を参照する。
