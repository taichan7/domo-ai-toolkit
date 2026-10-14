#!/usr/bin/env python3
"""サンドボックス隔離（バックエンド完全隔離）の命名契約＋本番保護ガードを固定するテスト（ネットワーク不要）。

PL_SANDBOX_SUFFIX の有無で、provision_domo.py（データ層＝seed/AppDB/dedupe CE/DataFlow/4出力/App Studio）と
provision_workflows.py（WF 層＝保存CE/統合サブWF/WF-01/業務コレクション）の「名前」定数が:
  - 未設定（既定）: 本番と完全に同じ（＝従来挙動・本番メンテ/顧客配備に無影響）
  - 設定時: 全オブジェクト名に名札サフィックス（検証・氏名）が付き一意化（本番/他参加者と衝突しない）
alias（summary/detail/trend/dept）・公開関数名（pl_report_api / dedupe_appdb_documents）は不変であること、
両スクリプトが同じ名札で業務コレクション名を揃えること、state 保存先が参加者ごとに分かれること、
本番保護ガードが maintenance-instance の本番オブジェクトだけを守り顧客自身のインスタンスは素通しすることを確認する。

実行: python3 tests/test_sandbox_isolation.py
"""
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SFX = "検証・テスト太郎"
WRAP = f"（{SFX}）"


def _probe(env_overrides, snippet):
    """子プロセスで（任意の env を設定して）両モジュールを import し、式を印字して返す。"""
    env = dict(os.environ)
    for key in ("PL_SANDBOX_SUFFIX", "PL_ALLOW_PRODUCTION", "DOMO_INSTANCE", "INSTANCE"):
        env.pop(key, None)
    env.update(env_overrides)
    code = (
        "import sys;"
        f"sys.path[:0]=[{str(ROOT / 'scripts')!r}];"
        "import provision_workflows as w, provision_domo as d;"
        f"print({snippet})"
    )
    return subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip()


def _guard(env_overrides, call):
    """ガード関数を子プロセスで呼び、SystemExit なら REFUSED、通れば PASS を返す。"""
    env = dict(os.environ)
    for key in ("PL_SANDBOX_SUFFIX", "PL_ALLOW_PRODUCTION", "DOMO_INSTANCE", "INSTANCE"):
        env.pop(key, None)
    env.update(env_overrides)
    code = (
        "import sys;"
        f"sys.path[:0]=[{str(ROOT / 'scripts')!r}];"
        "import provision_workflows as w, provision_domo as d\n"
        "try:\n"
        f"    {call}\n"
        "    print('PASS')\n"
        "except SystemExit:\n"
        "    print('REFUSED')\n"
    )
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True).stdout.strip()


class DefaultNamesUnchanged(unittest.TestCase):
    """名札なし＝本番名そのまま（スナップショット・本番メンテ・顧客配備に無影響）。"""

    def test_wf_defaults(self):
        self.assertEqual(_probe({}, "w.SUBFLOW_NAME"), "WF-02｜店舗損益AIレポート生成（店舗/全社）")
        self.assertEqual(_probe({}, "w.WF01_MODEL_NAME"), "WF-01｜店舗損益AIメイン (Loop→Sub)")
        self.assertEqual(_probe({}, "w.REPORT_API_PACKAGE_NAME"), "店舗別損益AI要約｜レポートAPI")

    def test_domo_defaults(self):
        self.assertEqual(_probe({}, "d.DATAFLOW_NAME"), "DF｜店舗別損益データフロー")
        self.assertEqual(_probe({}, "d.SUMMARY_OUTPUT_NAME"), "OUT｜P/L要約（店舗×月）")
        self.assertEqual(_probe({}, "d.APP_STUDIO_NAME"), "店舗別損益AIインサイト")

    def test_sandbox_flag_false_by_default(self):
        self.assertEqual(_probe({}, "(w.SANDBOX, d.SANDBOX)"), "(False, False)")


class SuffixIsolatesAllBackendNames(unittest.TestCase):
    """名札あり＝WF層・データ層の全オブジェクト名にサフィックスが付く（バックエンド完全隔離）。"""

    def test_wf_layer_all_suffixed(self):
        for const in ("SUBFLOW_NAME", "WF01_MODEL_NAME", "BUSINESS_COLLECTION_NAME", "REPORT_API_PACKAGE_NAME"):
            self.assertTrue(_probe({"PL_SANDBOX_SUFFIX": SFX}, f"w.{const}").endswith(WRAP), const)

    def test_data_layer_all_suffixed(self):
        for const in ("SEED_DATASTORE_NAME", "SEED_COLLECTION_NAME", "BUSINESS_COLLECTION_NAME",
                      "PACKAGE_NAME", "DATAFLOW_NAME", "DETAIL_OUTPUT_NAME", "SUMMARY_OUTPUT_NAME",
                      "TREND_OUTPUT_NAME", "DEPT_OUTPUT_NAME", "APP_STUDIO_NAME",
                      "APP_STUDIO_CARD_TITLE", "GUIDE_CARD_TITLE"):
            self.assertTrue(_probe({"PL_SANDBOX_SUFFIX": SFX}, f"d.{const}").endswith(WRAP), const)

    def test_sandbox_flag_true_when_set(self):
        self.assertEqual(_probe({"PL_SANDBOX_SUFFIX": SFX}, "(w.SANDBOX, d.SANDBOX)"), "(True, True)")


class ContractNamesInvariant(unittest.TestCase):
    """公開関数名・alias は名札でも不変＝下流（FE/CE/WF/テスト）の契約を壊さない。"""

    def test_function_names_invariant(self):
        self.assertEqual(_probe({"PL_SANDBOX_SUFFIX": SFX}, "w.FUNCTION_NAME"), "pl_report_api")
        self.assertEqual(_probe({"PL_SANDBOX_SUFFIX": SFX}, "d.DEDUPE_FUNCTION_NAME"), "dedupe_appdb_documents")

    def test_manifest_aliases_untouched_by_nameplate(self):
        # 名札はオブジェクト名だけを一意化し、manifest の alias（summary/detail/trend/dept）は変えない。
        aliases = _probe({"PL_SANDBOX_SUFFIX": SFX},
                         "sorted(r['alias'] for r in __import__('json').load(open("
                         f"{str(ROOT / 'pro-code' / 'manifest.json')!r}))['datasetsMapping'])")
        self.assertEqual(aliases, "['dept', 'detail', 'summary', 'trend']")


class CrossScriptConsistency(unittest.TestCase):
    """2スクリプトが同じ名札で業務コレクション名を揃える（resolve_collection_id が解決できる）。"""

    def test_business_collection_name_matches_across_scripts(self):
        self.assertEqual(
            _probe({"PL_SANDBOX_SUFFIX": SFX}, "w.BUSINESS_COLLECTION_NAME == d.BUSINESS_COLLECTION_NAME"),
            "True")


class StatePathIsolated(unittest.TestCase):
    """名札ありは registry（domo-assets.json）保存先も参加者ごとに分離（互いに/本番ピンを上書きしない）。"""

    def test_registry_path_isolated(self):
        path = _probe({"PL_SANDBOX_SUFFIX": SFX}, "str(d._registry_path())")
        self.assertIn("/sandbox-", path)
        self.assertTrue(path.endswith("domo-assets.json"))

    def test_registry_path_base_when_unset(self):
        path = _probe({}, "str(d._registry_path())")
        self.assertNotIn("/sandbox-", path)
        self.assertTrue(path.endswith("domo-assets.json"))


class ProductionWriteGuard(unittest.TestCase):
    """本番保護ガードは maintenance-instance の本番オブジェクトだけを守り、顧客自身のインスタンスは素通しする。"""

    CUSTOM = {"DOMO_INSTANCE": "maintenance-instance.domo.com"}

    def test_provision_refused_on_custom_apj_without_suffix_or_allow(self):
        self.assertEqual(_guard(self.CUSTOM, "w._guard_provision_write()"), "REFUSED")

    def test_provision_passes_on_custom_apj_with_suffix(self):
        self.assertEqual(_guard({**self.CUSTOM, "PL_SANDBOX_SUFFIX": SFX}, "w._guard_provision_write()"), "PASS")

    def test_provision_passes_on_custom_apj_with_allow_production(self):
        self.assertEqual(_guard({**self.CUSTOM, "PL_ALLOW_PRODUCTION": "1"}, "w._guard_provision_write()"), "PASS")

    def test_provision_passes_on_customer_instance_without_suffix(self):
        # 顧客が自分のインスタンスへ配備する既定フローは名札なしでも通る（instance != maintenance-instance）。
        self.assertEqual(_guard({"DOMO_INSTANCE": "acme.domo.com"}, "w._guard_provision_write()"), "PASS")

    def test_default_instance_is_guarded(self):
        # DOMO_INSTANCE 未設定の既定先は maintenance-instance なのでガード対象（名札なし→拒否）。
        self.assertEqual(_guard({}, "w._guard_provision_write()"), "REFUSED")

    def test_maintenance_commands_refused_in_sandbox(self):
        # ce/subflow/mainflow/delete-wf03 は固定の本番モデルID対象ゆえサンドボックスでは拒否（provision へ誘導）。
        for cmd in ("ce", "subflow", "mainflow", "delete-wf03"):
            self.assertEqual(_guard({**self.CUSTOM, "PL_SANDBOX_SUFFIX": SFX},
                                    f"w._guard_maintenance_write({cmd!r})"), "REFUSED", cmd)

    def test_maintenance_commands_require_allow_on_custom_apj(self):
        self.assertEqual(_guard(self.CUSTOM, "w._guard_maintenance_write('mainflow')"), "REFUSED")
        self.assertEqual(_guard({**self.CUSTOM, "PL_ALLOW_PRODUCTION": "1"},
                                "w._guard_maintenance_write('mainflow')"), "PASS")

    def test_domo_apply_and_embed_guide_guarded_on_custom_apj(self):
        for action in ("apply", "app-studio", "embed-guide"):
            self.assertEqual(_guard(self.CUSTOM, f"d._guard_production_write({action!r})"), "REFUSED", action)
            self.assertEqual(_guard({**self.CUSTOM, "PL_SANDBOX_SUFFIX": SFX},
                                    f"d._guard_production_write({action!r})"), "PASS", action)


if __name__ == "__main__":
    unittest.main(verbosity=2)
