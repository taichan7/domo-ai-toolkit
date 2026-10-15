import importlib.util
import json
import pathlib
import sys
import types
import unittest
from urllib.parse import parse_qs, urlsplit


class FakeCodeEngine(types.ModuleType):
    def __init__(self):
        super().__init__("codeengine")
        self.stores = {}
        self.counter = 0
        self.user_id = "admin-1"
        self.email = "operator@example.invalid"
        self.user_name = "テスト利用者"
        # 標準同期の即時エクスポート起動(datastoreId キー)を記録する。CRUD 用の collections
        # パスとは別系統なので、呼び出し回数と任意の失敗注入をここで観測できるようにする。
        self.export_calls = []
        self.fail_export = False
        # 通知Workflowの起動経路（CE がモデルの最新有効版を解決して instances/message を叩く）。
        # workflow_start_calls は instances/message への POST 本文を記録し、テストが起動ペイロード
        # （event_type/headline/shortage_lines/recipient_email/version 等）を直接検査できる。
        self.workflow_model = {
            "id": "wf-model-1",
            "versions": [{"version": "1.0.0", "active": True}, {"version": "1.0.2", "active": True}],
        }
        self.workflow_start_calls = []
        self.workflow_model_calls = []
        self.fail_workflow = False
        # AppDB の結果整合性（作成→query インデックス反映の遅延）を再現するための仮想クロックと
        # 反映遅延。create_visibility_lag>0 のとき、作成した文書は「clock が visible_at を越える」
        # まで query に現れない。clock は SERVICE.time を差し替えた仮スリーパが進める。既定は
        # lag=0＝作成即可視（既存テストの挙動を変えない）。
        self.clock = 0.0
        self.create_visibility_lag = 0.0
        # 反映遅延を課さない派生レコード種別。BALANCE / ALERT_STATE は1つの操作フローの中で
        # 「書いて直後に読む」read-your-own-writes で、本番でも書込み経路が整合を保つ（Inc3 が
        # 狙う「一括作成→別処理で一括 query」の失敗モードとは別系統）。バリアが待つのは
        # ITEM/LOCATION/RULE/TRANSACTION なので、遅延はそれらにだけ効かせて検証を対象へ絞る。
        self.lag_exempt_record_types = {"BALANCE", "ALERT_STATE", "ALERT_HISTORY"}

    def get_execution_information(self):
        info = {"userId": self.user_id, "userEmail": self.email}
        # 一部インスタンスは氏名を返さない。テストで欠落を再現できるよう任意項目にする。
        if self.user_name is not None:
            info["userName"] = self.user_name
        return info

    def send_request(self, method, url, body=None):
        method = method.lower()
        path = urlsplit(url).path.strip("/")
        parts = path.split("/")
        # 標準同期の即時エクスポート起動は datastoreId をキーにする別系統のパスで、
        # collections を含まない。CRUD 解析(下の parts.index)より前に横取りする。
        if "/export/" in path and method == "post":
            self.export_calls.append(path)
            if self.fail_export:
                raise RuntimeError("export failed")
            return None
        # 通知Workflowの起動は collections を含まない別系統のパスなので、CRUD 解析より前に
        # 横取りする。モデルGETは版一覧（active フラグで最新有効版を選ばせる）、instances/message
        # へのPOSTは起動本文（messageName/modelId/version/data）を記録して実行IDを返す。
        if path.startswith("api/workflow/v1/models/") and method == "get":
            self.workflow_model_calls.append(path)
            if self.fail_workflow:
                raise RuntimeError("workflow model unavailable")
            return dict(self.workflow_model)
        if path == "api/workflow/v1/instances/message" and method == "post":
            if self.fail_workflow:
                raise RuntimeError("workflow start failed")
            self.workflow_start_calls.append({"url": url, "body": body or {}})
            return {"id": f"wf-instance-{len(self.workflow_start_calls)}"}
        collection_id = parts[parts.index("collections") + 1]
        store = self.stores.setdefault(collection_id, [])
        if path.endswith("/documents/query") and method == "post":
            # 本物の AppDB は documents/query を1応答最大1万件で打ち切り、limit/offset は
            # クエリ文字列で受ける。ここでも同じ契約を再現し、_records のページング反復
            # (QUERY_PAGE_SIZE ごとに offset を進める)を検証できるようにする。
            # さらに結果整合性を再現: 仮想クロックが visible_at を越えた文書だけを返す
            # （create_visibility_lag=0 の既定では全件が即可視なので既存テストは不変）。
            matched = [
                self._wrapped(row)
                for row in store
                if self._matches(row, body or {}) and row.get("_visible_at", 0.0) <= self.clock
            ]
            params = parse_qs(urlsplit(url).query)
            offset = int(params.get("offset", ["0"])[0])
            limit = int(params.get("limit", ["10000"])[0])
            return matched[offset:offset + limit]
        if path.endswith("/documents") and method == "post":
            self.counter += 1
            content = dict((body or {}).get("content") or {})
            # 反映遅延を文書へ焼き付ける。clock が visible_at 以上になるまで query に現れない。
            # ただし派生レコード（BALANCE/ALERT_STATE 等）は1操作フロー内で「書いて直後に読む」
            # read-your-own-writes で本番も整合を保つため遅延を課さない（lag_exempt_record_types）。
            # バリアが待つ ITEM/LOCATION/RULE/TRANSACTION にだけ遅延を効かせ、検証を対象へ絞る。
            lag = 0.0 if content.get("record_type") in self.lag_exempt_record_types else self.create_visibility_lag
            row = {"id": f"doc-{self.counter}", "content": content,
                   "_visible_at": self.clock + lag}
            store.append(row)
            return self._wrapped(row)
        if "/documents/" in path and method == "put":
            document_id = parts[-1]
            row = next(item for item in store if item["id"] == document_id)
            row["content"] = dict((body or {}).get("content") or {})
            return self._wrapped(row)
        if "/documents/" in path and method == "delete":
            document_id = parts[-1]
            before = len(store)
            store[:] = [item for item in store if item["id"] != document_id]
            return {"deleted": before - len(store)}
        raise AssertionError(f"Unhandled request: {method} {url}")

    @staticmethod
    def _wrapped(row):
        return {"id": row["id"], "content": dict(row["content"])}

    @staticmethod
    def _matches(row, criteria):
        for field, expected in criteria.items():
            if row["content"].get(field.removeprefix("content.")) != expected:
                return False
        return True


FAKE = FakeCodeEngine()
sys.modules["codeengine"] = FAKE
MODULE_PATH = pathlib.Path(__file__).parents[1] / "code-engine" / "inventory_service.py"
SPEC = importlib.util.spec_from_file_location("inventory_service_under_test", MODULE_PATH)
SERVICE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVICE)
# 非公開ヘルパーを _service() から受けてモジュール属性へ貼り直し、テストが SERVICE._records
# 等を直接叩けるようにする。クロージャは呼び出し時にモジュール定数を読むため、setUp の差し替え
# （COLLECTION_ID="records" 等）は各テストで尊重される。
_TOOLKIT = SERVICE._service()
SERVICE._records = _TOOLKIT["records"]
SERVICE._is_true = _TOOLKIT["is_true"]
SERVICE._register = _TOOLKIT["register"]
SERVICE._notify_now = _TOOLKIT["notify_now"]
SERVICE._admin = _TOOLKIT["admin"]
SERVICE._resolve_recipient_email = _TOOLKIT["resolve_recipient_email"]


class InventoryServiceTest(unittest.TestCase):
    def setUp(self):
        # Other independently collected app suites may replace the runtime stub.
        # Bind a fresh fake to this imported service for every test.
        global FAKE
        FAKE = FakeCodeEngine()
        SERVICE.codeengine = FAKE
        FAKE.stores = {}
        FAKE.counter = 0
        FAKE.user_id = "admin-1"
        FAKE.email = "operator@example.invalid"
        FAKE.user_name = "テスト利用者"
        FAKE.export_calls = []
        FAKE.fail_export = False
        # 通知Workflowの起動先は既定で有効（テストごとに独立の dict へ戻し、個別テストが
        # 版構成や失敗を注入できるようにする）。
        FAKE.workflow_model = {"id": "wf-model-1", "versions": [{"version": "1.0.0", "active": True}, {"version": "1.0.2", "active": True}]}
        FAKE.workflow_start_calls = []
        FAKE.workflow_model_calls = []
        FAKE.fail_workflow = False
        # 既定は反映遅延ゼロ（作成即可視）。バリアのテストだけが lag を注入する。
        FAKE.clock = 0.0
        FAKE.create_visibility_lag = 0.0
        SERVICE.COLLECTION_ID = "records"
        SERVICE.ADMIN_USER_IDS = {"admin-1"}
        # 既定はプレースホルダのまま＝標準同期キックは無操作。個別テストで実IDを注入する。
        SERVICE.DATASTORE_ID = "__DATASTORE_ID__"
        # 通知WorkflowのモデルIDも実IDを注入する（プレースホルダの失敗系は専用テストで検証）。
        SERVICE.WORKFLOW_MODEL_ID = "wf-model-1"
        SERVICE._records("create", "ITEM", record_key="ITEM|ITEM-001", content={"item_code": "ITEM-001", "item_name": "安全手袋", "active": True})
        SERVICE._records("create", "LOCATION", record_key="LOCATION|LOC-01", content={"location_code": "LOC-01", "location_name": "中央倉庫", "active": True})
        SERVICE._records("create", "RULE", record_key="RULE|LOC-01|ITEM-001", content={"rule_key": "LOC-01|ITEM-001", "location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": 10, "active": True})

    def _api(self, operation, payload=None):
        return SERVICE.inventory_api(operation, json.dumps(payload or {}, ensure_ascii=False))

    def _register(self, request_id, transaction_type, quantity):
        return self._api("REGISTER", {"request_id": request_id, "transaction_type": transaction_type, "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": quantity, "reason": "テスト"})

    def test_get_state_returns_authenticated_user_and_balance(self):
        result = self._api("GET_STATE", {"location_code": "LOC-01", "item_code": "ITEM-001"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"]["id"], "admin-1")
        self.assertEqual(result["balance"]["quantity"], 0)

    def test_qr_parsing_is_not_a_backend_operation(self):
        result = self._api("PARSE_QR", {"qr_value": "LOC:LOC-01"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_OPERATION")

    def test_in_and_out_update_projection_in_one_collection(self):
        self.assertTrue(self._register("request-1", "IN", 20)["ok"])
        result = self._register("request-2", "OUT", 4)
        self.assertEqual(result["balance"]["quantity"], 16)
        types = [row["content"]["record_type"] for row in FAKE.stores["records"]]
        self.assertEqual(types.count("TRANSACTION"), 2)
        self.assertEqual(types.count("BALANCE"), 1)

    def test_duplicate_request_is_idempotent(self):
        self._register("same-request", "IN", 20)
        second = self._register("same-request", "IN", 20)
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 1)

    def test_get_state_and_replay_do_not_leak_internal_document_id(self):
        # AppDB の find 結果には内部の _document_id が付く。LIST_MASTERS と同じく、
        # GET_STATE の balance/rule と重複リプレイの transaction は公開契約から
        # 内部フィールドを取り除いて返すこと（他フィールドは維持）。
        no_internal = lambda row: not any(key.startswith("_") for key in row)
        first = self._register("dup-1", "IN", 20)
        self.assertTrue(no_internal(first["transaction"]))  # 新規登録の取引も内部IDを含まない
        state = self._api("GET_STATE", {"location_code": "LOC-01", "item_code": "ITEM-001"})
        self.assertEqual(state["balance"]["quantity"], 20)
        self.assertTrue(no_internal(state["balance"]))
        self.assertIsNotNone(state["rule"])  # setUp のルールが実在する
        self.assertTrue(no_internal(state["rule"]))
        replay = self._register("dup-1", "IN", 20)
        self.assertTrue(replay["duplicate"])
        self.assertTrue(no_internal(replay["transaction"]))

    def test_negative_inventory_is_rejected_without_write(self):
        result = self._register("request-out", "OUT", 1)
        self.assertEqual(result["error"]["code"], "NEGATIVE_INVENTORY")
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 0)

    def test_adjust_type_is_rejected(self):
        # 調整(ADJUST)は概念ごと廃止。管理者であっても未知の処理種別として弾き、台帳を書かない。
        result = self._register("adjust", "ADJUST", 1)
        self.assertEqual(result["error"]["code"], "INVALID_TRANSACTION_TYPE")
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 0)

    def test_threshold_history_is_deduplicated_and_starts_one_workflow(self):
        # 閾値遷移で通知対象が確定したら、CE が最新の有効版を解決して Workflow を起動し、
        # 結果（STARTED＋実行ID）を同じ監査行へ確定する。連続する同状態の取引では起動しない。
        self._register("initial", "IN", 20)
        first = self._register("shortage-1", "OUT", 12)
        second = self._register("shortage-2", "OUT", 1)
        self.assertTrue(first["notification"]["workflow_ready"])
        self.assertTrue(first["notification"]["workflow_started"])
        self.assertEqual(first["notification"]["workflow_instance_id"], "wf-instance-1")
        self.assertEqual(len(FAKE.workflow_start_calls), 1)
        started = FAKE.workflow_start_calls[0]["body"]
        self.assertEqual(started["messageName"], "不足通知を開始")
        self.assertEqual(started["modelId"], "wf-model-1")
        self.assertEqual(started["version"], "1.0.2")  # 有効（release済み）な最新版を実行時に解決する
        self.assertEqual(started["data"]["recipient_email"], "operator@example.invalid")
        self.assertEqual(started["data"]["event_type"], "SHORTAGE")
        self.assertFalse(second["notification"]["triggered"])
        alerts = SERVICE._records("query", "ALERT_HISTORY")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["notification_status"], "STARTED")
        self.assertEqual(alerts[0]["workflow_instance_id"], "wf-instance-1")

    def test_register_records_failed_when_workflow_start_fails(self):
        # Workflow起動の失敗は在庫登録の結果を覆さない。CE は ALERT_HISTORY に FAILED と理由を残し、
        # Pro Code は notification.workflow_started=False / workflow_error を見て利用者へ伝える。
        FAKE.fail_workflow = True
        self._register("in-20", "IN", 20)
        result = self._register("out-12", "OUT", 12)
        self.assertTrue(result["ok"])
        note = result["notification"]
        self.assertTrue(note["workflow_ready"])
        self.assertFalse(note["workflow_started"])
        self.assertTrue(note["workflow_error"])
        alert = SERVICE._records("find", "ALERT_HISTORY", field="alert_id", value=note["alert_id"])
        self.assertEqual(alert["notification_status"], "FAILED")
        self.assertIn("通知Workflow", alert["error_message"])

    def test_workflow_start_skips_with_unconfigured_model_id(self):
        # 配備不良（モデルIDがプレースホルダ）では Workflow API を呼ばず、監査へ理由を残して fail-soft。
        SERVICE.WORKFLOW_MODEL_ID = "__WORKFLOW_MODEL_ID__"
        self._register("in-20", "IN", 20)
        result = self._register("out-12", "OUT", 12)
        self.assertTrue(result["ok"])
        note = result["notification"]
        self.assertFalse(note["workflow_started"])
        self.assertEqual(FAKE.workflow_start_calls, [])
        self.assertEqual(FAKE.workflow_model_calls, [])
        alert = SERVICE._records("find", "ALERT_HISTORY", field="alert_id", value=note["alert_id"])
        self.assertEqual(alert["notification_status"], "FAILED")
        self.assertIn("接続先が未設定", alert["error_message"])

    def test_workflow_start_requires_an_active_version(self):
        # 有効（release済み）な版が無ければ起動しない。未releaseの新版は選ばない（FAILEDを記録）。
        FAKE.workflow_model = {"id": "wf-model-1", "versions": [{"version": "2.0.0", "active": False}]}
        self._register("in-20", "IN", 20)
        result = self._register("out-12", "OUT", 12)
        self.assertTrue(result["ok"])
        self.assertFalse(result["notification"]["workflow_started"])
        self.assertEqual(FAKE.workflow_start_calls, [])
        alert = SERVICE._records("find", "ALERT_HISTORY", field="alert_id", value=result["notification"]["alert_id"])
        self.assertEqual(alert["notification_status"], "FAILED")
        self.assertIn("公開版", alert["error_message"])

    def test_workflow_start_uses_latest_active_version_only(self):
        # 版一覧に未releaseの新版（1.0.3）が混ざっても、起動に使うのは有効な最新版（1.0.2）。
        FAKE.workflow_model = {"id": "wf-model-1", "versions": [
            {"version": "1.0.0", "active": True},
            {"version": "1.0.3", "active": False},
            {"version": "1.0.2", "active": True},
        ]}
        self._register("in-20", "IN", 20)
        self._register("out-12", "OUT", 12)
        started = FAKE.workflow_start_calls[0]["body"]
        self.assertEqual(started["version"], "1.0.2")
        self.assertEqual(started["messageName"], "不足通知を開始")
        self.assertEqual(started["modelId"], "wf-model-1")

    def test_shortage_quantity_is_rounded_without_float_residue(self):
        # minimum=10 に対し 6.6 を入庫すると 10-6.6 が浮動小数残差(3.4000000000000004)を生む。
        # BALANCE / ALERT_HISTORY / 通知本文 / Workflow起動ペイロード すべてで6桁丸め済みの
        # 同一値を共有し、監査記録と通知文面に不自然な桁が出ないことを固定する。
        result = self._register("frac-shortage", "IN", 6.6)
        self.assertTrue(result["ok"])
        balance = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertTrue(balance["is_shortage"])
        self.assertEqual(balance["shortage_quantity"], 3.4)
        # SHORTAGE 遷移で作られた監査行も丸め済み。本文にも残差桁(3.4000...)を出さない。
        alerts = SERVICE._records("query", "ALERT_HISTORY")
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["shortage_quantity"], 3.4)
        self.assertIn("不足数3.4です", alerts[0]["notification_body"])
        self.assertNotIn("3.4000", alerts[0]["notification_body"])
        # CE が Workflow へ渡した起動ペイロードは、見出し/一覧の整形済みテキストに同一の丸め値を含む。
        payload = FAKE.workflow_start_calls[0]["body"]["data"]
        self.assertIn("3.4", payload["headline"])
        self.assertNotIn("3.4000", payload["headline"])
        self.assertIn("3.4", payload["shortage_lines"])
        self.assertNotIn("shortage_quantity", payload)

    def test_recalculate_reprojects_identical_rounded_shortage(self):
        # register が保存する不足数と RECALCULATE の再投影が一致すること(register≡recalc 不変条件)。
        # 片方だけ丸めると RECALCULATE が保存値を書き換える divergence が生じるため両側を固定する。
        self._register("frac-recalc", "IN", 6.6)
        before = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(before["shortage_quantity"], 3.4)
        recalc = self._api("RECALCULATE")
        self.assertTrue(recalc["ok"])
        after = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(after["shortage_quantity"], 3.4)
        self.assertEqual(after["quantity"], before["quantity"])

    def test_notification_status_records_failed_reason_and_clears_it_on_started(self):
        # 通知ワークフローの失敗も同じ NOTIFICATION_STATUS で記録する。error_message は
        # FAILED のときだけ残し、STARTED では消す（古い失敗理由を復旧後まで引きずらないため）。
        self._register("initial", "IN", 20)
        alert_id = self._register("shortage-1", "OUT", 12)["notification"]["alert_id"]
        failed = self._api("NOTIFICATION_STATUS", {
            "alert_id": alert_id, "status": "FAILED",
            "workflow_instance_id": "wf-err-1", "error_message": "SMTP timeout",
        })
        self.assertTrue(failed["ok"])
        self.assertEqual(failed["notification_status"], "FAILED")
        row = SERVICE._records("find", "ALERT_HISTORY", field="alert_id", value=alert_id)
        self.assertEqual(row["notification_status"], "FAILED")
        self.assertEqual(row["error_message"], "SMTP timeout")
        # 復旧して STARTED へ更新すると失敗理由はクリアされる（成功状態に失敗痕を残さない）。
        started = self._api("NOTIFICATION_STATUS", {
            "alert_id": alert_id, "status": "STARTED", "error_message": "この文言は保存されない",
        })
        self.assertTrue(started["ok"])
        row = SERVICE._records("find", "ALERT_HISTORY", field="alert_id", value=alert_id)
        self.assertEqual(row["notification_status"], "STARTED")
        self.assertEqual(row["error_message"], "")

    def test_notification_status_rejects_invalid_status_and_missing_alert(self):
        # 状態は STARTED / FAILED のみ許可。alert_id 空・不正状態は INVALID、実在しない
        # alert_id は ALERT_NOT_FOUND として業務エラーで弾く（不正な監査更新を防ぐ）。
        self._register("initial", "IN", 20)
        alert_id = self._register("shortage-1", "OUT", 12)["notification"]["alert_id"]
        bad_status = self._api("NOTIFICATION_STATUS", {"alert_id": alert_id, "status": "DONE"})
        self.assertEqual(bad_status["error"]["code"], "INVALID_NOTIFICATION_STATUS")
        empty_id = self._api("NOTIFICATION_STATUS", {"alert_id": "", "status": "STARTED"})
        self.assertEqual(empty_id["error"]["code"], "INVALID_NOTIFICATION_STATUS")
        missing = self._api("NOTIFICATION_STATUS", {"alert_id": "ALERT-does-not-exist", "status": "STARTED"})
        self.assertEqual(missing["error"]["code"], "ALERT_NOT_FOUND")

    def test_notification_status_guards_against_updating_another_users_alert(self):
        # 通知履歴は作成者本人だけが状態更新できる。別ユーザーが他人のアラートを書き換えようと
        # すると FORBIDDEN で拒否し、元の状態（CE 起動済みの STARTED）は保つ。監査証跡の所有権を守る。
        self._register("initial", "IN", 20)
        alert_id = self._register("shortage-1", "OUT", 12)["notification"]["alert_id"]
        FAKE.user_id = "member-9"  # 作成者(admin-1)とは別のユーザーに切り替える
        blocked = self._api("NOTIFICATION_STATUS", {"alert_id": alert_id, "status": "FAILED"})
        self.assertEqual(blocked["error"]["code"], "FORBIDDEN")
        row = SERVICE._records("find", "ALERT_HISTORY", field="alert_id", value=alert_id)
        self.assertEqual(row["notification_status"], "STARTED")

    def test_recalculation_uses_transaction_source_of_truth(self):
        self._register("request-1", "IN", 20)
        self._register("request-2", "OUT", 4)
        balance = next(row for row in FAKE.stores["records"] if row["content"].get("record_type") == "BALANCE")
        balance["content"]["quantity"] = 999
        result = self._api("RECALCULATE")
        self.assertTrue(result["ok"])
        current = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(current["quantity"], 16)

    def test_register_rounds_off_float_residual_and_does_not_false_trip_negative_guard(self):
        # 0.01粒度の小数を足し引きすると浮動小数の残差(0.3-0.1-0.2 = -2.8e-17)が乗る。丸めが無いと
        # 実質ゼロの在庫で正当な出庫が NEGATIVE_INVENTORY と誤判定される。丸め後は素通りし残高は 0。
        self.assertTrue(self._register("frac-in", "IN", 0.3)["ok"])
        self.assertTrue(self._register("frac-out-1", "OUT", 0.1)["ok"])
        third = self._register("frac-out-2", "OUT", 0.2)
        self.assertTrue(third["ok"])  # 丸めが無いと NEGATIVE_INVENTORY で False になる回帰点
        self.assertEqual(third["balance"]["quantity"], 0)
        self.assertEqual(repr(third["balance"]["quantity"]), "0.0")  # -0.0 ではなく正のゼロに正規化

    def test_recalculation_rounds_off_accumulated_float_residual_to_positive_zero(self):
        # RECALCULATE は取引の signed_quantity を素の float で合計するため、小数取引の集計で
        # 残差(-2.8e-17)が出る。丸め+正規化が無いと BALANCE.quantity に負の残差や -0.0 が残る。
        self._register("frac-in", "IN", 0.3)
        self._register("frac-out-1", "OUT", 0.1)
        self._register("frac-out-2", "OUT", 0.2)
        result = self._api("RECALCULATE")
        self.assertTrue(result["ok"])
        current = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(current["quantity"], 0)
        self.assertEqual(repr(current["quantity"]), "0.0")  # 負の残差や -0.0 を残さない

    def test_recalculation_does_not_resurrect_physically_deleted_master(self):
        # 物理削除の恒久性を保証する回帰テスト。取引台帳は追記専用で残るため、
        # 再計算がその取引から残高を作り直すと、削除済みマスタが「復活」してしまう。
        # 対策として物理削除時に取引へ archived 印を付け、再計算は archived を集計から外す。
        self._register("request-1", "IN", 20)
        self._register("request-2", "OUT", 4)  # 残高16
        self.assertTrue(self._master("DELETE_ITEM", {"item_code": "ITEM-001"})["ok"])
        self.assertEqual(len(SERVICE._records("query", "BALANCE")), 0)
        # 台帳は監査証跡として残るが、削除済みマスタの取引はすべて archived 印が付く。
        transactions = SERVICE._records("query", "TRANSACTION")
        self.assertEqual(len(transactions), 2)
        self.assertTrue(all(SERVICE._is_true(row.get("archived")) for row in transactions))
        result = self._api("RECALCULATE")
        self.assertTrue(result["ok"])
        # archived 取引は集計対象から外れるため、残高は復活せず集計キーにも現れない。
        self.assertIsNone(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001"))
        self.assertEqual(result["balance_count"], 0)
        self.assertEqual(result["skipped_deleted_master_count"], 0)
        # 台帳自体は再計算後も監査証跡として保持されている（再計算は台帳を消さない）。
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 2)

    def test_recreated_master_code_starts_from_zero_after_delete(self):
        # 削除→同じ人手コードで作り直しの回帰テスト。作り直すとマスタ存在ガードは
        # くぐり抜けられるが、削除前の取引が archived 印付きで集計から外れるため、
        # 再計算は _register が削除後に BALANCE を失って before=0 から始めるのと同じ投影になる。
        self._register("old-1", "IN", 20)
        self._register("old-2", "OUT", 4)  # 残高16
        self.assertTrue(self._master("DELETE_ITEM", {"item_code": "ITEM-001"})["ok"])
        # 同じコードでマスタを作り直す（存在ガードは通るようになる）。
        self.assertTrue(self._master("UPSERT_ITEM", {"item_code": "ITEM-001", "item_name": "安全手袋(再登録)"})["ok"])
        result = self._api("RECALCULATE")
        self.assertTrue(result["ok"])
        # 旧取引は archived のため集計されず、作り直したコードの残高は復活しない。
        self.assertIsNone(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001"))
        # 作り直した後の新しい取引だけが積み上がる（before=0 から始まる）。
        self._register("new-1", "IN", 3)
        self._api("RECALCULATE")
        current = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(current["quantity"], 3)

    def test_seed_restores_physically_deleted_demo_item(self):
        # SEED は既知のデモ一式を冪等に再生成する操作。デモ品目を物理削除するとその取引は
        # archived 印付きで台帳に残る。archived は再計算の集計対象外で、かつ request_id の重複
        # ガードは archived 取引を「既存」として素通りさせるため、放置すると再 SEED しても
        # 消したデモ品目の残高が復活しない。SEED は先頭で archived な SEED 由来取引を物理削除
        # してから作り直すので、消したデモ品目も残高・ルールごとよみがえる。
        self._api("SEED")
        # デモ品目 ITEM-001 を物理削除（依存ルール・残高が消え、取引は archived として残る）。
        self.assertTrue(self._master("DELETE_ITEM", {"item_code": "ITEM-001"})["ok"])
        self.assertIsNone(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001"))
        # 再 SEED で archived な SEED 取引を掃除してから作り直すため、残高とルールが復活する。
        second = self._api("SEED")
        self.assertTrue(second["ok"])
        self.assertGreaterEqual(second["created"]["purged_archived_seed"], 1)
        balance = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertIsNotNone(balance)
        self.assertEqual(balance["quantity"], 38)  # SEED-001 IN50 → SEED-002 OUT12 = 38
        rule = SERVICE._records("find", "RULE", field="rule_key", value="LOC-01|ITEM-001")
        self.assertEqual(rule["minimum_quantity"], 20)  # SEED が最小在庫ルールも作り直す
        # 削除していないデモ品目は掃除の巻き添えにならない（purge は archived な SEED 取引限定）。
        other = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-002")
        self.assertEqual(other["quantity"], 7)  # SEED-003 IN15 → SEED-004 OUT8 = 7

    def test_seed_does_not_corrupt_real_activity_under_demo_codes(self):
        # 配布先が同じコード（デモと同名）を実運用で使い、そのキーに SEED 由来でない取引があるとき、
        # SEED を再実行してもデモ取引/ルールを注入して実在庫や基準を黙って書き換えてはならない。
        # setUp が用意する LOC-01|ITEM-001 へ実運用の入庫を1件入れる（source 既定=DOMO＝実運用扱い）。
        self.assertTrue(self._register("real-1", "IN", 7)["ok"])
        # ITEM-002 は実運用マスタとして用意し、ルール無しで実取引だけ持たせる（デモは min10 を敷こうとする）。
        self.assertTrue(self._master("UPSERT_ITEM", {"item_code": "ITEM-002", "item_name": "実運用の保護メガネ"})["ok"])
        self.assertTrue(self._api("REGISTER", {"request_id": "real-2", "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-002", "quantity": 3, "reason": "実運用"})["ok"])

        result = self._api("SEED")
        self.assertTrue(result["ok"])
        # 実取引のあるキー（LOC-01|ITEM-001, LOC-01|ITEM-002）の2件を保護対象として検出している。
        self.assertGreaterEqual(result["created"]["protected_real_keys"], 2)

        # 実取引のあるキーには SEED 由来取引（SEED-*/GEN-*）が1件も注入されない。
        seed_sources = {"DEMO_SEED", "DEMO_SEED_GENERATED"}
        for key in ("LOC-01|ITEM-001", "LOC-01|ITEM-002"):
            injected = [
                row for row in SERVICE._records("query", "TRANSACTION")
                if f"{row.get('location_code')}|{row.get('item_code')}" == key and str(row.get("source")) in seed_sources
            ]
            self.assertEqual(injected, [], f"{key} に SEED 由来取引が注入された")

        # 実在庫はデモで上書きされず、実取引ぶんだけ（IN7 / IN3）。
        self.assertEqual(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")["quantity"], 7)
        self.assertEqual(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-002")["quantity"], 3)
        # 実運用キー（ルール未設定）にデモの min-stock ルールを敷かない（幽霊しきい値＝誤不足を作らない）。
        self.assertIsNone(SERVICE._records("find", "RULE", field="rule_key", value="LOC-01|ITEM-002"))

        # デモ専用キー（実取引なし）は通常どおり生成され、SEED 自体は機能している。
        demo_only = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-02|ITEM-003")
        self.assertIsNotNone(demo_only)
        self.assertGreater(demo_only["quantity"], 0)
        self.assertGreaterEqual(len(SERVICE._records("query", "BALANCE")), 100)

    def test_records_query_paginates_beyond_one_page(self):
        # AppDB は documents/query を1応答最大1万件で打ち切り、limit/offset はクエリ文字列で
        # 受ける。_records の query はページ上限ごとに offset を進めて全ページを辿るため、
        # 1ページ上限を超えても全件そろう。ここではページ上限を 2 に縮めて複数ページの集約を検証する。
        original_page_size = SERVICE.QUERY_PAGE_SIZE
        SERVICE.QUERY_PAGE_SIZE = 2
        self.addCleanup(setattr, SERVICE, "QUERY_PAGE_SIZE", original_page_size)
        for index in range(5):
            self._register(f"page-{index}", "IN", 1)
        transactions = SERVICE._records("query", "TRANSACTION")
        self.assertEqual(len(transactions), 5)  # 3ページ(2+2+1)を辿って全件そろう
        # find はページ上限に依らず1件だけ返す（page_size=1 の早期 return）。
        one = SERVICE._records("find", "TRANSACTION", field="request_id", value="page-3")
        self.assertEqual(one["request_id"], "page-3")

    def test_recalculation_purges_stale_derived_records_for_deleted_master(self):
        # 万一削除済みマスタの派生レコードが残っていても、再計算が物理削除して整合を回復する。
        self._register("request-1", "IN", 20)
        self.assertTrue(self._master("DELETE_ITEM", {"item_code": "ITEM-001"})["ok"])
        # 削除後に残ってしまった派生レコードを模擬的に再注入する。
        SERVICE._records("create", "BALANCE", record_key="BALANCE|LOC-01|ITEM-001", content={"balance_key": "LOC-01|ITEM-001", "item_code": "ITEM-001", "location_code": "LOC-01", "quantity": 20})
        SERVICE._records("create", "ALERT_STATE", record_key="ALERT_STATE|LOC-01|ITEM-001", content={"balance_key": "LOC-01|ITEM-001"})
        self._api("RECALCULATE")
        self.assertIsNone(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001"))
        self.assertIsNone(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001"))

    def test_recalculation_ignores_inactive_rule_threshold(self):
        # 再計算は停止中(active=false)ルールのしきい値を沈黙させ、_register と同じ投影に揃える。
        # これがないと再計算だけが停止中ルールの基準を拾い、幽霊の不足を作り直してしまう。
        self._register("in-1", "IN", 3)  # 基準10・有効ルール → この時点では不足
        before = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertTrue(before["is_shortage"])  # 前提: 有効ルール下では不足
        # ルールを一時停止する。停止直後の残高フラグは次の取引/再計算まで据え置かれる。
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": 10, "active": False})
        result = self._api("RECALCULATE")
        self.assertTrue(result["ok"])
        current = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertFalse(current["is_shortage"])
        self.assertEqual(current["minimum_quantity"], 0)
        self.assertEqual(current["shortage_quantity"], 0)

    def test_recalculate_clears_stale_shortage_alert_but_does_not_force_shortage(self):
        # 不足が解消したのにアラート状態が SHORTAGE に取り残されると、次の回復方向の取引が
        # previous_status=SHORTAGE を読んで実体のない RECOVERY を誤発火する。RECALCULATE は
        # DELETE_RULE と同じく、不足解消時にだけ据え置きの SHORTAGE を NORMAL へ掃除する。
        # (A) 実在庫は健全だがアラート状態が SHORTAGE に取り残されたドリフトを掃除する。
        self._register("healthy", "IN", 20)  # 残高20・基準10 → 健全(_register が NORMAL を書く)
        SERVICE._records("upsert", "ALERT_STATE", record_key="ALERT_STATE|LOC-01|ITEM-001",
                         content={"balance_key": "LOC-01|ITEM-001", "status": "SHORTAGE"})
        self._api("RECALCULATE")
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "NORMAL")
        # (B) 逆向き(NORMAL→SHORTAGE)は強制しない。不足残高でアラートが NORMAL のときは据え置き、
        #     次の取引の通常遷移で SHORTAGE 通知を発火させる(再計算で通知を握り潰さない)。
        self._register("draw-down", "OUT", 17)  # 残高3・基準10 → 不足(_register が SHORTAGE を書く)
        SERVICE._records("upsert", "ALERT_STATE", record_key="ALERT_STATE|LOC-01|ITEM-001",
                         content={"balance_key": "LOC-01|ITEM-001", "status": "NORMAL"})
        self._api("RECALCULATE")
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "NORMAL")

    def test_register_backdated_transaction_does_not_rewind_last_transaction_at(self):
        # last_transaction_at は「最新取引の時刻」。過去日を遡って登録しても既存の最新時刻を
        # 後退させず、RECALCULATE の max 集約(occurred_at 昇順の末尾)と一致する。
        self._api("REGISTER", {"request_id": "recent", "transaction_type": "IN", "location_code": "LOC-01",
                               "item_code": "ITEM-001", "quantity": 10, "reason": "テスト", "occurred_at": "2026-08-01T00:00:00Z"})
        self._api("REGISTER", {"request_id": "backdated", "transaction_type": "IN", "location_code": "LOC-01",
                               "item_code": "ITEM-001", "quantity": 5, "reason": "テスト", "occurred_at": "2026-07-01T00:00:00Z"})
        balance = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(balance["last_transaction_at"], "2026-08-01T00:00:00Z")  # 遡及登録でも後退しない
        self.assertEqual(balance["quantity"], 15)  # 数量は両取引を反映する

    def test_seed_is_idempotent_and_contains_core_record_types(self):
        first = self._api("SEED")
        second = self._api("SEED")
        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        request_ids = [row["request_id"] for row in SERVICE._records("query", "TRANSACTION")]
        self.assertEqual(len(request_ids), len(set(request_ids)))
        types = {row["record_type"] for row in SERVICE._records("query")}
        self.assertTrue({"ITEM", "LOCATION", "RULE", "TRANSACTION", "BALANCE", "ALERT_STATE"}.issubset(types))

    def test_auth_uses_domo_execution_context(self):
        result = self._api("AUTH")
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"]["id"], "admin-1")
        self.assertTrue(result["user"]["isAdmin"])
        # 実行コンテキストが氏名を持つときはそれを表示名にする。
        self.assertEqual(result["user"]["name"], "テスト利用者")

    def test_auth_returns_empty_name_when_context_lacks_it(self):
        # get_execution_information() が氏名を返さないインスタンスでは、仮名を捏造せず
        # 空文字を返す。フロントは People API で解決済みの実名を保持しており、CE 側が
        # truthy な仮名（例: "Domo利用者"）を返すとその実名を上書きしてしまうため。
        FAKE.user_name = None
        result = self._api("AUTH")
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"]["name"], "")
        self.assertNotIn("Domo利用者", result["user"]["name"])

    def test_name_falls_back_to_frontend_display_hint_when_context_lacks_it(self):
        # 実行コンテキストが氏名を返さないインスタンスでは、フロントが People API で解決した表示名を
        # operator_display_name として送る。CE はそれを表示ラベルとして採用し AppDB に永続化する
        # （本人特定の id は実行コンテキスト由来のまま＝クライアントは渡していない）。
        FAKE.user_name = None
        result = self._api("AUTH", {"operator_display_name": "山田 太郎"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"]["name"], "山田 太郎")
        self.assertEqual(result["user"]["id"], "admin-1")

    def test_context_name_wins_over_frontend_display_hint(self):
        # 実行コンテキストが氏名を持つインスタンスでは、そちらを最優先（信頼度が高い）。
        # クライアント送信の operator_display_name は無視する。
        FAKE.user_name = "テスト利用者"
        result = self._api("AUTH", {"operator_display_name": "別人"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["user"]["name"], "テスト利用者")

    def test_register_persists_frontend_display_name_when_context_lacks_it(self):
        # 入出庫登録でも、氏名が空のインスタンスでは operator_display_name を取引レコードの
        # operator_name として永続化する（画面がユーザーIDだけになる問題の恒久修正）。
        # operator_user_id は実行コンテキスト由来のまま。
        FAKE.user_name = None
        result = self._api("REGISTER", {"request_id": "nm-hint-1", "transaction_type": "IN",
                                        "location_code": "LOC-01", "item_code": "ITEM-001",
                                        "quantity": 3, "reason": "テスト",
                                        "operator_display_name": "鈴木 花子"})
        self.assertTrue(result["ok"])
        txn = next(row for row in SERVICE._records("query", "TRANSACTION") if row.get("request_id") == "nm-hint-1")
        self.assertEqual(txn["operator_name"], "鈴木 花子")
        self.assertEqual(txn["operator_user_id"], "admin-1")

    # --- request_json 正規化契約（公開関数へ素の値を直接渡して固定する） -----------
    # _api ヘルパーは常に json.dumps した正しい JSON オブジェクトを渡すため、下記4分岐
    # （壊れた文字列 / 非オブジェクト / None・空 / dict 素通り）は _api 経由では踏めない。
    # Pro Code は dict も生文字列も渡し得るので、公開関数 inventory_api を直接呼んで固定する。
    def test_request_json_malformed_string_is_invalid_json(self):
        # 壊れた JSON 文字列は、実処理・利用者解決より前に INVALID_JSON で弾く（送出せず ok=False）。
        result = SERVICE.inventory_api("AUTH", "{壊れた: JSON")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "INVALID_JSON")

    def test_request_json_valid_but_non_object_is_invalid_request(self):
        # JSON として妥当でも「オブジェクト以外」（配列・数値・文字列・真偽・null）は
        # INVALID_REQUEST で弾く。request は後段でフィールドを get する dict 前提のため。
        for raw in ("[1, 2, 3]", "42", '"文字列"', "true", "null"):
            result = SERVICE.inventory_api("AUTH", raw)
            self.assertFalse(result["ok"], f"{raw!r} は object でないので弾かれるべき")
            self.assertEqual(result["error"]["code"], "INVALID_REQUEST", f"{raw!r}")

    def test_request_json_none_and_empty_are_treated_as_empty_request(self):
        # None・空文字は「空要求」= {} として扱い正常応答を返す（引数省略の既定 "{}" と同値）。
        for raw in (None, ""):
            result = SERVICE.inventory_api("AUTH", raw)
            self.assertTrue(result["ok"], f"{raw!r} は空要求として通るべき")
            self.assertEqual(result["user"]["id"], "admin-1")

    def test_request_json_dict_is_passed_through_and_its_fields_are_used(self):
        # request_json は dict でも受け付け、再パースせず素通りさせる（Pro Code が dict を直接渡す経路）。
        # 単に受理するだけでなく dict のフィールドが実際に読まれることを、GET_STATE が
        # location_code/item_code から在庫キーを組む挙動（大文字化＋"|"連結）で確かめる。
        result = SERVICE.inventory_api("GET_STATE", {"location_code": "z1", "item_code": "z9"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["balance"], {"balance_key": "Z1|Z9", "quantity": 0})

    def _make_shortage(self):
        # 在庫20→払出12で残8（基準10未満）＝不足を1件つくる。
        self._register("initial", "IN", 20)
        self._register("shortage-1", "OUT", 12)

    def test_notify_now_reports_no_shortage_when_stock_is_healthy(self):
        self._register("initial", "IN", 20)
        result = self._api("NOTIFY_NOW")
        self.assertTrue(result["ok"])
        self.assertFalse(result["notification"]["workflow_ready"])
        self.assertEqual(result["notification"]["reason"], "NO_SHORTAGE")
        self.assertEqual(result["notification"]["shortage_count"], 0)

    def test_notify_now_starts_manual_workflow_for_current_shortage(self):
        self._make_shortage()  # 自動SHORTAGE（起動#1）→ 手動（起動#2）の順で2件起動する
        result = self._api("NOTIFY_NOW")
        self.assertTrue(result["ok"])
        note = result["notification"]
        self.assertTrue(note["workflow_ready"])
        self.assertTrue(note["workflow_started"])
        self.assertEqual(note["workflow_instance_id"], "wf-instance-2")
        self.assertEqual(note["reason"], "MANUAL_TRIGGER")
        self.assertEqual(note["shortage_count"], 1)
        self.assertEqual(len(FAKE.workflow_start_calls), 2)
        started = FAKE.workflow_start_calls[-1]["body"]
        self.assertEqual(started["data"]["event_type"], "MANUAL")
        # 単一品目でも見出し/一覧は整形済みテキストで渡す（旧スカラー項目は持たない）。
        self.assertIn("ITEM-001", started["data"]["headline"])
        self.assertIn("ITEM-001", started["data"]["shortage_lines"])
        self.assertNotIn("item_code", started["data"])
        self.assertNotIn("shortage_quantity", started["data"])
        self.assertEqual(started["data"]["recipient_email"], "operator@example.invalid")
        # 手動起動は自動SHORTAGEとは別のMANUAL監査を1件だけ残し、起動結果（STARTED＋実行ID）を記録する。
        manual = [row for row in SERVICE._records("query", "ALERT_HISTORY") if row.get("event_type") == "MANUAL"]
        self.assertEqual(len(manual), 1)
        self.assertEqual(manual[0]["notification_status"], "STARTED")
        self.assertEqual(manual[0]["workflow_instance_id"], "wf-instance-2")

    def test_notify_now_requires_recipient_email(self):
        self._make_shortage()
        FAKE.email = "no-at-sign"
        result = self._api("NOTIFY_NOW")
        self.assertTrue(result["ok"])
        self.assertFalse(result["notification"]["workflow_ready"])
        self.assertEqual(result["notification"]["reason"], "RECIPIENT_EMAIL_MISSING")
        self.assertEqual(result["notification"]["shortage_count"], 1)

    def test_notify_now_falls_back_to_operator_email_from_request(self):
        # 実行コンテキストがメールを返さないインスタンスでも、Pro Code が渡す
        # operator_email（People API で解決した宛先）で通知先を確定できる。
        self._make_shortage()
        FAKE.email = ""
        result = self._api("NOTIFY_NOW", {"operator_email": "line-lead@example.invalid"})
        self.assertTrue(result["ok"])
        note = result["notification"]
        self.assertTrue(note["workflow_started"])
        self.assertEqual(FAKE.workflow_start_calls[-1]["body"]["data"]["recipient_email"], "line-lead@example.invalid")

    def test_notify_now_skips_shortage_whose_rule_has_notifications_disabled(self):
        # 通知を無効化したルールの不足は、手動通知(NOTIFY_NOW)でも起動しない（自動経路 _register と整合）。
        # 不足そのものは存在するので shortage_count は返しつつ、triggered=False / NOTIFICATION_DISABLED とする。
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": 10, "active": True, "notification_enabled": False})
        self._make_shortage()  # 残8 < 基準10 → 不足1件（ただし通知無効）
        result = self._api("NOTIFY_NOW")
        note = result["notification"]
        self.assertTrue(result["ok"])
        self.assertFalse(note["triggered"])
        self.assertFalse(note["workflow_ready"])
        self.assertEqual(note["reason"], "NOTIFICATION_DISABLED")
        self.assertEqual(note["shortage_count"], 1)  # 不足は存在するので件数は返す
        self.assertFalse(note["workflow_started"])   # 起動しない
        self.assertEqual(FAKE.workflow_start_calls, [])  # Workflow API も呼ばない
        # 起動しないので MANUAL 監査は残さない。
        manual = [row for row in SERVICE._records("query", "ALERT_HISTORY") if row.get("event_type") == "MANUAL"]
        self.assertEqual(manual, [])

    def test_notify_now_picks_worst_shortage_among_notification_enabled_rules(self):
        # 通知有効なルールの中から最も深刻な不足を選ぶ。より深刻でも通知無効なキーは対象にしない
        # （管理者が黙らせた品目を手動ボタンで蒸し返さない）。shortage_count は全不足件数を返す。
        self.assertTrue(self._master("UPSERT_ITEM", {"item_code": "ITEM-002", "item_name": "実運用の保護メガネ"})["ok"])
        # 通知無効・大不足（本来なら最優先だが対象外）。
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-002", "minimum_quantity": 100, "active": True, "notification_enabled": False})
        self.assertTrue(self._api("REGISTER", {"request_id": "muted-in", "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-002", "quantity": 5, "reason": "実運用"})["ok"])
        # 通知有効・小不足（setUp のルール min10 は notification_enabled 省略＝既定で通知有効）。
        self._make_shortage()  # LOC-01|ITEM-001 残8 → 不足2
        result = self._api("NOTIFY_NOW")
        note = result["notification"]
        self.assertTrue(note["triggered"])
        self.assertEqual(note["reason"], "MANUAL_TRIGGER")
        self.assertEqual(note["shortage_count"], 2)                          # 不足は2件（無効ぶんも数える）
        # 見出しは通知有効な ITEM-001 を選び、通知無効の ITEM-002 は見出しにも一覧にも出さない。
        started = FAKE.workflow_start_calls[-1]["body"]["data"]
        self.assertIn("ITEM-001", started["headline"])
        self.assertNotIn("ITEM-002", started["headline"])
        self.assertNotIn("ITEM-002", started["shortage_lines"])

    def test_notify_now_consolidates_multiple_shortages_into_one_shortage_lines(self):
        # 手動通知は現時点の通知有効な不足を「まとめて1通」に集約する。shortage_lines は
        # 1行1件で全不足を列挙し、見出し(headline)は最も深刻な1件を代表として選ぶ。
        # これがワークフロー入力を権威データ化した集約通知の中核。
        self.assertTrue(self._master("UPSERT_ITEM", {"item_code": "ITEM-002", "item_name": "保護メガネ"})["ok"])
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-002", "minimum_quantity": 10, "active": True})
        self.assertTrue(self._api("REGISTER", {"request_id": "i2-in", "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-002", "quantity": 20, "reason": "テスト"})["ok"])
        self.assertTrue(self._api("REGISTER", {"request_id": "i2-out", "transaction_type": "OUT", "location_code": "LOC-01", "item_code": "ITEM-002", "quantity": 15, "reason": "テスト"})["ok"])  # 残5 → 不足5
        self._make_shortage()  # LOC-01|ITEM-001 残8 → 不足2
        note = self._api("NOTIFY_NOW")["notification"]
        self.assertEqual(note["shortage_count"], 2)
        started = FAKE.workflow_start_calls[-1]["body"]["data"]
        lines = [line for line in started["shortage_lines"].split("\n") if line]
        self.assertEqual(len(lines), 2)                       # 2件を1通に集約
        self.assertIn("ITEM-001", started["shortage_lines"])
        self.assertIn("ITEM-002", started["shortage_lines"])
        self.assertIn("ITEM-002", started["headline"])  # 不足5 > 不足2 → 最深刻を見出しに

    def test_register_falls_back_to_operator_email_for_shortage_notification(self):
        # 自動SHORTAGEの宛先も、実行コンテキストにメールが無ければ operator_email で確定する。
        FAKE.email = ""
        self._register("initial", "IN", 20)
        first = self._api("REGISTER", {
            "request_id": "shortage-fallback", "transaction_type": "OUT",
            "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": 12,
            "reason": "テスト", "operator_email": "line-lead@example.invalid",
        })
        self.assertTrue(first["notification"]["workflow_started"])
        self.assertEqual(FAKE.workflow_start_calls[-1]["body"]["data"]["recipient_email"], "line-lead@example.invalid")

    def test_register_shortage_then_recovery_transitions_alert_state_and_fires_recovery_event(self):
        # 不足→補充の一巡で、自動通知の event_type が SHORTAGE→RECOVERY と遷移すること。
        # 閾値を跨いだ「遷移」だけを通知し、同じ状態の連続では重複通知を作らない設計の裏返し。
        self._register("in-20", "IN", 20)                 # 残高20・基準10 → 健全(event_type 無し)
        shortage = self._register("out-12", "OUT", 12)     # 残高8 → 不足へ遷移
        self.assertEqual(FAKE.workflow_start_calls[0]["body"]["data"]["event_type"], "SHORTAGE")
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "SHORTAGE")
        recovery = self._register("in-12", "IN", 12)       # 残高20 → 基準以上へ回復
        note = recovery["notification"]
        self.assertTrue(note["triggered"])
        self.assertEqual(FAKE.workflow_start_calls[1]["body"]["data"]["event_type"], "RECOVERY")
        # 監査(ALERT_HISTORY)にも RECOVERY 行が残り、件名は「在庫回復」テンプレートになる。
        recovered = [row for row in SERVICE._records("query", "ALERT_HISTORY") if row.get("event_type") == "RECOVERY"]
        self.assertEqual(len(recovered), 1)
        self.assertIn("在庫回復", recovered[0]["notification_subject"])
        # アラート状態は NORMAL へ戻り、回復時刻(last_recovered_at)が刻まれる。
        state = SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertEqual(state["status"], "NORMAL")
        self.assertTrue(state["last_recovered_at"])

    def test_register_shortage_with_notifications_disabled_skips_workflow_but_records_history(self):
        # 通知を無効化したルールでは、不足へ遷移しても Workflow を起動しない。ただし状態遷移と
        # 監査記録(SKIPPED)は残す＝「なぜ送らなかったか」を後から追跡できるようにする。
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": 10, "active": True, "notification_enabled": False})
        self._register("in-20", "IN", 20)                  # 残高20 → 健全
        shortage = self._register("out-12", "OUT", 12)      # 残高8 → 不足へ遷移
        note = shortage["notification"]
        self.assertFalse(note["triggered"])
        self.assertFalse(note["workflow_ready"])
        self.assertEqual(note["reason"], "NOTIFICATION_DISABLED")
        self.assertFalse(note["workflow_started"])          # 起動しない
        self.assertEqual(FAKE.workflow_start_calls, [])     # Workflow API も呼ばない
        # 状態遷移そのものは通知有無に依らず記録し、監査は SKIPPED + 理由を残す。
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "SHORTAGE")
        history = [row for row in SERVICE._records("query", "ALERT_HISTORY") if row.get("event_type") == "SHORTAGE"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["notification_status"], "SKIPPED")
        self.assertEqual(history[0]["error_message"], "NOTIFICATION_DISABLED")

    def test_seed_creates_at_least_100_balance_projections(self):
        # SEED は per-item AI コメントの土台として、残高(BALANCE)を100件以上そろえる。
        # DataFlow の TextGeneration タイルが BATCH で最低100行を要求する制約(DP-TGTFR)の担保。
        self._api("SEED")
        self.assertGreaterEqual(len(SERVICE._records("query", "BALANCE")), 100)

    def test_operations_require_authenticated_domo_user(self):
        # 実行コンテキストに userId が無ければ、どの操作も AUTHENTICATION_REQUIRED で弾き、
        # 台帳(TRANSACTION)や残高(BALANCE)を一切書かないこと(認証ゲートは全操作の手前)。
        FAKE.user_id = ""
        for operation, payload in (
            ("AUTH", {}),
            ("GET_STATE", {"location_code": "LOC-01", "item_code": "ITEM-001"}),
            ("REGISTER", {"request_id": "noauth", "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": 5}),
        ):
            result = self._api(operation, payload)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "AUTHENTICATION_REQUIRED")
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 0)
        self.assertEqual(len(SERVICE._records("query", "BALANCE")), 0)

    def test_register_rejects_out_of_bounds_and_non_numeric_quantity(self):
        # 数量は 0 より大きく・MAX(1,000,000)以下・有限数のみ。0/負値/境界外/非数値/inf/nan は
        # すべて INVALID_QUANTITY で弾き、台帳を書かないこと。
        for quantity in (1_000_001, 0, -5, "abc", float("inf"), float("nan")):
            result = self._api("REGISTER", {"request_id": f"bad-{quantity}", "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": quantity})
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "INVALID_QUANTITY")
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 0)

    def test_register_rejects_unknown_type_and_bad_request_id(self):
        # 種別は IN/OUT のみ、request_id は 1〜100 文字。範囲外は専用コードで弾き台帳を書かない。
        unknown = self._api("REGISTER", {"request_id": "bad-type", "transaction_type": "TRANSFER", "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": 5})
        self.assertEqual(unknown["error"]["code"], "INVALID_TRANSACTION_TYPE")
        empty_id = self._api("REGISTER", {"request_id": "  ", "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": 5})
        self.assertEqual(empty_id["error"]["code"], "INVALID_REQUEST_ID")
        long_id = self._api("REGISTER", {"request_id": "x" * 101, "transaction_type": "IN", "location_code": "LOC-01", "item_code": "ITEM-001", "quantity": 5})
        self.assertEqual(long_id["error"]["code"], "INVALID_REQUEST_ID")
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 0)

    def _master(self, action, payload=None):
        return self._api("MANAGE_MASTER", dict({"action": action}, **(payload or {})))

    def test_manage_master_creates_then_updates_one_item_document(self):
        created = self._master("UPSERT_ITEM", {"item_code": "item-009", "item_name": "軍手", "category": "安全用品", "unit": "双"})
        self.assertTrue(created["ok"])
        self.assertEqual(created["status"], "created")
        self.assertEqual(created["record"]["item_code"], "ITEM-009")
        self.assertEqual(created["record"]["qr_value"], "ITEM:ITEM-009")
        self.assertTrue(created["record"]["active"])
        updated = self._master("UPSERT_ITEM", {"item_code": "ITEM-009", "item_name": "作業用軍手", "category": "安全用品", "unit": "双"})
        self.assertEqual(updated["status"], "updated")
        self.assertEqual(updated["record"]["item_name"], "作業用軍手")
        items = [row for row in SERVICE._records("query", "ITEM") if row.get("item_code") == "ITEM-009"]
        self.assertEqual(len(items), 1)

    def test_manage_master_whitespace_qr_value_falls_back_to_default(self):
        # 空白のみの qr_value は真値扱いで既定を飛ばし、空の qr_value を保存してしまう罠。
        # strip 後にフォールバックし、ITEM/LOCATION とも既定コードを埋めること。
        item = self._master("UPSERT_ITEM", {"item_code": "item-050", "item_name": "台車", "qr_value": "   "})
        self.assertEqual(item["record"]["qr_value"], "ITEM:ITEM-050")
        location = self._master("UPSERT_LOCATION", {"location_code": "loc-05", "location_name": "資材置場", "qr_value": "\t \n"})
        self.assertEqual(location["record"]["qr_value"], "LOC:LOC-05")

    def test_manage_master_lists_all_master_types_without_internal_fields(self):
        result = self._master("LIST_MASTERS")
        self.assertTrue(result["ok"])
        self.assertEqual([row["item_code"] for row in result["items"]], ["ITEM-001"])
        self.assertEqual([row["location_code"] for row in result["locations"]], ["LOC-01"])
        self.assertEqual([row["rule_key"] for row in result["rules"]], ["LOC-01|ITEM-001"])
        self.assertFalse(any(key.startswith("_") for row in result["items"] for key in row))

    def test_manage_master_physical_delete_removes_master_and_derived_but_keeps_ledger(self):
        # 品目に在庫を積んで残高・取引・(閾値割れで)アラート履歴を作る。
        self.assertTrue(self._register("in-1", "IN", 20)["ok"])
        self.assertTrue(self._register("out-1", "OUT", 15)["ok"])  # 5 < 基準10 → SHORTAGE
        deleted = self._master("DELETE_ITEM", {"item_code": "ITEM-001"})
        self.assertTrue(deleted["ok"])
        self.assertEqual(deleted["status"], "deleted")
        # マスタ本体・依存ルール・派生の残高/アラート状態は物理削除される。
        self.assertEqual(deleted["deleted"]["ITEM"], 1)
        self.assertEqual(deleted["deleted"]["RULE"], 1)
        self.assertEqual(deleted["deleted"]["BALANCE"], 1)
        self.assertEqual(deleted["deleted"]["ALERT_STATE"], 1)
        self.assertIsNone(SERVICE._records("find", "ITEM", field="item_code", value="ITEM-001"))
        self.assertEqual(len(SERVICE._records("query", "RULE")), 0)
        self.assertEqual(len(SERVICE._records("query", "BALANCE")), 0)
        self.assertEqual(len(SERVICE._records("query", "ALERT_STATE")), 0)
        # 追記専用の台帳(取引履歴・通知履歴)は監査証跡として保持する。
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 2)
        self.assertGreaterEqual(len(SERVICE._records("query", "ALERT_HISTORY")), 1)
        # 物理削除後は同コードの入出庫が「有効な品目なし」で弾かれる。
        blocked = self._register("after-delete", "IN", 5)
        self.assertEqual(blocked["error"]["code"], "INVALID_ITEM")

    def test_manage_master_physical_delete_rule_keeps_balance(self):
        self.assertTrue(self._register("in-1", "IN", 3)["ok"])  # 残高3、基準10 → SHORTAGE
        deleted = self._master("DELETE_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001"})
        self.assertEqual(deleted["deleted"], {"RULE": 1, "ALERT_STATE": 1})
        # ルール削除でしきい値と派生アラート状態は消えるが、現在庫(残高)は残る。
        self.assertEqual(len(SERVICE._records("query", "RULE")), 0)
        self.assertEqual(len(SERVICE._records("query", "ALERT_STATE")), 0)
        self.assertIsNotNone(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001"))

    def test_manage_master_delete_rule_clears_ghost_shortage_on_retained_balance(self):
        # ルール削除後、残高は残すが「ルール由来の派生値」(基準在庫/不足数/不足フラグ)は
        # 掃除する。据え置くと実体のないルールで NOTIFY_NOW が幽霊通知を発火してしまう。
        self._register("in-1", "IN", 3)  # 残高3、基準10 → SHORTAGE
        self.assertTrue(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")["is_shortage"])
        deleted = self._master("DELETE_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001"})
        self.assertEqual(deleted["deleted"], {"RULE": 1, "ALERT_STATE": 1})
        balance = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertIsNotNone(balance)  # 現在庫(残高)は保持する
        self.assertEqual(balance["quantity"], 3)
        # ルール由来のしきい値派生値は 0/false へ掃除される。
        self.assertFalse(balance["is_shortage"])
        self.assertEqual(balance["minimum_quantity"], 0)
        self.assertEqual(balance["shortage_quantity"], 0)
        # 実体のないルールで手動通知(NOTIFY_NOW)が発火しないことを確認する。
        notified = self._api("NOTIFY_NOW")
        self.assertFalse(notified["notification"]["triggered"])
        self.assertEqual(notified["notification"]["reason"], "NO_SHORTAGE")

    def test_upsert_rule_reprojects_retained_balance_and_alert_state(self):
        # ルールの停止・再開は、次の取引や再計算を待たずに残高の派生値を即時投影し直す
        # (DELETE_RULE と同じ「据え置き幽霊」を UPSERT でも作らない)。アラート状態は
        # 不足解消時にだけ SHORTAGE を掃除し、逆向きの強制はしない(通知の握り潰し防止)。
        self._register("in-1", "IN", 3)  # 残高3・基準10 → 不足、ALERT_STATE=SHORTAGE
        self.assertTrue(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")["is_shortage"])
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "SHORTAGE")
        # 停止 → しきい値を沈黙(minimum=0)。残高フラグは不足解消、据え置きの SHORTAGE も NORMAL へ掃除。
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": 10, "active": False})
        balance = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertFalse(balance["is_shortage"])
        self.assertEqual(balance["minimum_quantity"], 0)
        self.assertEqual(balance["shortage_quantity"], 0)
        self.assertEqual(balance["quantity"], 3)  # 現在庫は取引由来なので保持する
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "NORMAL")
        # 再開かつ基準引き上げ → 残高フラグは即時に不足へ戻る。ただしアラートは NORMAL のままにし、
        # 設定変更では通知を発火しない(次の取引の通常遷移に委ねる)。
        self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": 20, "active": True})
        balance = SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-01|ITEM-001")
        self.assertTrue(balance["is_shortage"])
        self.assertEqual(balance["minimum_quantity"], 20)
        self.assertEqual(balance["shortage_quantity"], 17)
        self.assertEqual(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-01|ITEM-001")["status"], "NORMAL")
        # 握り潰さない証明: 再開後の次の取引が通常遷移で SHORTAGE 通知を発火する。
        followup = self._register("in-2", "IN", 1)  # 残高4・基準20 → まだ不足、previous=NORMAL → SHORTAGE 発火
        self.assertEqual(FAKE.workflow_start_calls[-1]["body"]["data"]["event_type"], "SHORTAGE")

    def test_upsert_rule_without_transactions_does_not_create_phantom_balance(self):
        # 取引ゼロ(BALANCE 未生成)のルール新設では投影対象が無いので、幽霊の残高・アラートを作らない。
        self._master("UPSERT_ITEM", {"item_code": "ITEM-009", "item_name": "予備品"})
        self._master("UPSERT_LOCATION", {"location_code": "LOC-09", "location_name": "臨時置場"})
        self._master("UPSERT_RULE", {"location_code": "LOC-09", "item_code": "ITEM-009", "minimum_quantity": 5, "active": True})
        self.assertIsNone(SERVICE._records("find", "BALANCE", field="balance_key", value="LOC-09|ITEM-009"))
        self.assertIsNone(SERVICE._records("find", "ALERT_STATE", field="balance_key", value="LOC-09|ITEM-009"))

    def test_manage_master_disable_via_update_blocks_movements_and_is_reversible(self):
        # 物理削除とは別に、active=false の更新は「一時停止」(可逆)として機能する。
        self._master("UPSERT_ITEM", {"item_code": "ITEM-001", "item_name": "安全手袋", "active": False})
        blocked = self._register("while-disabled", "IN", 5)
        self.assertEqual(blocked["error"]["code"], "INVALID_ITEM")
        self._master("UPSERT_ITEM", {"item_code": "ITEM-001", "item_name": "安全手袋", "active": True})
        self.assertTrue(self._register("after-enable", "IN", 5)["ok"])

    def test_manage_master_requires_admin(self):
        FAKE.user_id = "member-1"
        result = self._master("UPSERT_ITEM", {"item_code": "ITEM-050", "item_name": "無権限"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "FORBIDDEN")

    def test_manage_master_rule_requires_existing_item_and_location(self):
        missing_item = self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-404", "minimum_quantity": 5})
        self.assertEqual(missing_item["error"]["code"], "INVALID_ITEM")
        missing_location = self._master("UPSERT_RULE", {"location_code": "LOC-404", "item_code": "ITEM-001", "minimum_quantity": 5})
        self.assertEqual(missing_location["error"]["code"], "INVALID_LOCATION")

    def test_manage_master_rule_validates_minimum_quantity(self):
        negative = self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": -1})
        self.assertEqual(negative["error"]["code"], "INVALID_MINIMUM_QUANTITY")
        not_a_number = self._master("UPSERT_RULE", {"location_code": "LOC-01", "item_code": "ITEM-001", "minimum_quantity": "abc"})
        self.assertEqual(not_a_number["error"]["code"], "INVALID_MINIMUM_QUANTITY")

    def test_manage_master_rejects_invalid_code_and_empty_name(self):
        bad_code = self._master("UPSERT_ITEM", {"item_code": "bad code!", "item_name": "不正コード"})
        self.assertEqual(bad_code["error"]["code"], "INVALID_MASTER_CODE")
        empty_name = self._master("UPSERT_LOCATION", {"location_code": "LOC-09", "location_name": "   "})
        self.assertEqual(empty_name["error"]["code"], "INVALID_MASTER_NAME")

    def test_manage_master_delete_missing_master_is_reported(self):
        result = self._master("DELETE_LOCATION", {"location_code": "LOC-999"})
        self.assertEqual(result["error"]["code"], "MASTER_NOT_FOUND")

    def test_manage_master_rejects_unknown_action(self):
        result = self._master("PURGE_EVERYTHING")
        self.assertEqual(result["error"]["code"], "UNSUPPORTED_MASTER_ACTION")

    def test_register_rejects_negative_quantity_for_in_and_out(self):
        # 入出庫はいずれも正の数量のみ。負値は INVALID_QUANTITY で弾き、台帳を書かない
        # （旧・管理者調整の負値経路は概念ごと廃止済み）。
        for tx_type in ("IN", "OUT"):
            result = self._register(f"neg-{tx_type}", tx_type, -5)
            self.assertEqual(result["error"]["code"], "INVALID_QUANTITY")
        self.assertEqual(len(SERVICE._records("query", "TRANSACTION")), 0)


class AppDbSyncKickTests(InventoryServiceTest):
    """変更系の操作が標準同期 DataSet の即時エクスポートを1回だけ起動することを検証する。

    AppDB へ追加・更新・削除した直後にダッシュボード（DataFlow 入力）へ数秒で反映するため、
    dispatcher は結果確定後に ``_records("sync")`` を一度だけ呼ぶ。読み取り専用の操作では
    呼ばず、エクスポート失敗は業務結果に影響させない（前倒しにすぎないため）。
    """

    def setUp(self):
        super().setUp()
        # 実 datastoreId を注入して sync キックを有効化する（既定はプレースホルダで無操作）。
        SERVICE.DATASTORE_ID = "datastore-1"

    def test_register_kicks_standard_sync_export_once(self):
        self.assertTrue(self._register("in-1", "IN", 5)["ok"])
        # datastoreId をキーにした空ボディの export を、操作ごとにちょうど1回だけ起動する。
        self.assertEqual(FAKE.export_calls, ["api/datastores/v1/export/datastore-1"])

    def test_manage_master_kicks_standard_sync_export_once(self):
        self._master("UPSERT_ITEM", {"item_code": "ITEM-050", "item_name": "新規品目"})
        self.assertEqual(FAKE.export_calls, ["api/datastores/v1/export/datastore-1"])

    def test_recalculate_kicks_standard_sync_export_once(self):
        self.assertTrue(self._register("in-1", "IN", 5)["ok"])
        FAKE.export_calls = []  # REGISTER 分のキックを除いて RECALCULATE 単体を測る。
        result = self._api("RECALCULATE")
        self.assertTrue(result["ok"])
        self.assertEqual(FAKE.export_calls, ["api/datastores/v1/export/datastore-1"])

    def test_seed_kicks_export_once_not_per_document(self):
        # SEED は多数のドキュメントを投入するが、キックは操作単位で1回に集約する
        # （品目ごとに呼ぶと export が多重起動してしまうため）。
        result = self._api("SEED")
        self.assertTrue(result["ok"])
        self.assertEqual(len(FAKE.export_calls), 1)

    def test_read_only_operations_do_not_kick_export(self):
        # AUTH / GET_STATE は AppDB を変更しないので同期の前倒しも不要。
        self.assertTrue(self._api("AUTH")["ok"])
        self.assertTrue(self._api("GET_STATE", {"location_code": "LOC-01", "item_code": "ITEM-001"})["ok"])
        self.assertEqual(FAKE.export_calls, [])

    def test_export_failure_is_swallowed_and_mutation_still_succeeds(self):
        # エクスポート起動が失敗しても書込みは確定済み。スケジュール同期が後で回収するため、
        # 例外は握りつぶして業務結果（ok）をそのまま返す。
        FAKE.fail_export = True
        result = self._register("in-1", "IN", 5)
        self.assertTrue(result["ok"])
        self.assertEqual(result["balance"]["quantity"], 5)
        self.assertEqual(FAKE.export_calls, ["api/datastores/v1/export/datastore-1"])

    def test_sync_is_noop_when_datastore_id_unset(self):
        # datastoreId がプレースホルダのままなら前倒し先が無いので無操作。書込みは成功する。
        SERVICE.DATASTORE_ID = "__DATASTORE_ID__"
        result = self._register("in-1", "IN", 5)
        self.assertTrue(result["ok"])
        self.assertEqual(FAKE.export_calls, [])


class AppDbConsistencyBarrierTests(InventoryServiceTest):
    """SEED の結果整合性バリア（await_queryable）が create→query の反映遅延を吸収することを検証する。

    AppDB は作成(POST documents)を即受理するが、query インデックスへの反映に短い遅延がある。
    FakeCodeEngine に仮想クロックと create_visibility_lag を持たせ、SERVICE.time を仮スリーパへ
    差し替えて「反映前 query の空振り→バックオフ→反映後に収束」を実 sleep なしで決定的に再現する。
    対話経路の _register はバリアを通さない設計なので、ここでは SEED 経由でのみ検証する。
    """

    def _seed_with_lag(self, lag):
        """仮スリーパを差し込み、指定の反映遅延で SEED を1回実行して (結果, sleep秒のリスト) を返す。

        time.sleep のたびに FakeCodeEngine の仮想クロックを進めることで、遅延中に作成された文書が
        「クロックが visible_at を越えた時点」で query に現れる。実時間は消費しない。
        """
        sleeps = []

        class _Clock:
            def sleep(_self, seconds):
                sleeps.append(seconds)
                FAKE.clock += seconds

        original = SERVICE.time
        SERVICE.time = _Clock()
        self.addCleanup(lambda: setattr(SERVICE, "time", original))
        FAKE.create_visibility_lag = lag
        result = self._api("SEED")
        FAKE.create_visibility_lag = 0.0  # 以降の検証 query は即時可視へ戻す
        return result, sleeps

    def test_barrier_is_free_when_documents_are_immediately_visible(self):
        # 反映遅延ゼロ＝作成直後から query に見える。バリアは query 1回で即収束し sleep しない
        # （冪等な再 SEED に待機コストを一切課さないことの担保）。
        result, sleeps = self._seed_with_lag(0.0)
        self.assertTrue(result["ok"])
        self.assertEqual(sleeps, [])
        consistency = result["created"]["appdb_consistency"]
        self.assertTrue(consistency["masters"]["item"]["converged"])
        self.assertEqual(consistency["masters"]["item"]["attempts"], 1)
        self.assertTrue(consistency["ledger"]["transaction"]["converged"])

    def test_barrier_absorbs_visibility_lag_and_seeds_correctly(self):
        # 現実的な反映遅延を再現。バリアはバックオフして反映を待ち、最終的に全キーへ収束する。
        # 作成直後の品目検索が INVALID_ITEM に化けず、100件以上の残高を作り切る（失敗モード⑤の解消）。
        result, sleeps = self._seed_with_lag(1.5)
        self.assertTrue(result["ok"])
        self.assertGreater(len(sleeps), 0)  # 反映待ちで実際にバックオフした
        consistency = result["created"]["appdb_consistency"]
        for phase in ("masters", "ledger"):
            for wait in consistency[phase].values():
                self.assertTrue(wait["converged"])
                self.assertEqual(wait["missing"], [])
        balances = SERVICE._records("query", "BALANCE")
        self.assertGreaterEqual(len(balances), 100)

    def test_barrier_degrades_gracefully_when_lag_exceeds_budget(self):
        # 反映遅延が待機予算を超える病的ケース。バリアは無限ループにならず attempts 上限で打ち切り、
        # マスタ/取引が不可視のまま _register や RECALCULATE を走らせずに明示エラーで中断する。
        # 「一部だけ入った中途半端な状態」や分かりにくい INVALID_ITEM ではなく、リトライ可能な
        # APPDB_CONSISTENCY_TIMEOUT（ok=False）へ穏当に縮退する（失敗モード⑤の最悪形＝残高過少を
        # 黙って作ることを防ぐ）。
        original_attempts = SERVICE.APPDB_CONSISTENCY_ATTEMPTS
        SERVICE.APPDB_CONSISTENCY_ATTEMPTS = 2
        self.addCleanup(lambda: setattr(SERVICE, "APPDB_CONSISTENCY_ATTEMPTS", original_attempts))
        result, sleeps = self._seed_with_lag(1000.0)  # 予算(2回×0.75秒)を遥かに超える反映遅延
        # 待機は予算ぶんで頭打ち＝無限リトライしない。1回あたり最大 (attempts-1) 回 sleep。
        self.assertTrue(all(s == SERVICE.APPDB_CONSISTENCY_DELAY_SECONDS for s in sleeps))
        self.assertLessEqual(len(sleeps), 8)
        # マスタ不可視のまま先へ進まず、明示エラー（ok=False）へ穏当に縮退する。
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "APPDB_CONSISTENCY_TIMEOUT")
        # 何を待っていたか（どの段の未反映キーか）を診断として伝える。
        self.assertIn(result["error"]["details"]["phase"], ("masters", "ledger"))
        self.assertTrue(result["error"]["details"]["unqueryable"])


if __name__ == "__main__":
    unittest.main()
