"""Offline authentication checks; no real credentials or network requests."""
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parent


class AuthHelpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="domo-auth-'")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        curl = self.bin / "curl"
        curl.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "if os.environ.get('FAKE_CURL_FAIL'):\n"
            "    print('mock HTTP failure', file=sys.stderr)\n"
            "    sys.exit(22)\n"
            "if any('/api/oauth2/token' in arg for arg in sys.argv):\n"
            "    print(json.dumps({'access_token': None if os.environ.get('FAKE_EMPTY_ACCESS') else 'test-access'}))\n"
            "else:\n"
            "    print(json.dumps({'sid': os.environ.get('FAKE_SID', 'test-sid')}))\n"
        )
        curl.chmod(0o700)
        config = self.root / ".config/configstore/ryuu"
        config.mkdir(parents=True)
        (config / "tenant.domo.com.json").write_text('{"refreshToken":"test-refresh"}')
        self.session = self.root / "session.sid"
        self.env = dict(os.environ, HOME=str(self.root),
                        PATH=f"{self.bin}:{os.environ['PATH']}",
                        DOMO_SESSION_FILE=str(self.session))
        for key in ("INSTANCE", "SID", "DOMO_TOKEN", "DOMO_DEVELOPER_TOKEN"):
            self.env.pop(key, None)

    def authenticate(self, **extra):
        return subprocess.run(["bash", str(SCRIPTS / "authenticate.sh"), "tenant.domo.com"],
                              env=dict(self.env, **extra), capture_output=True, text=True)

    def load_auth(self, **extra):
        return subprocess.run(
            ["bash", "-c", 'source "$1"; domo_load_auth || exit; printf "%s|%s" "$INSTANCE" "$SID"',
             "auth-test", str(SCRIPTS / "lib/common.sh")],
            env=dict(self.env, **extra), capture_output=True, text=True,
        )

    def test_authentication_does_not_print_credentials(self):
        result = self.authenticate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Authenticated to tenant.domo.com", result.stdout)
        for value in ("test-refresh", "test-access", "test-sid"):
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_session_is_private_even_when_replacing_an_existing_file(self):
        self.session.write_text("old")
        self.session.chmod(0o644)
        result = self.authenticate()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(self.session.stat().st_mode), 0o600)

    def test_session_values_round_trip_without_shell_expansion(self):
        value = "test-session with $variables; and 'quotes'"
        result = self.authenticate(FAKE_SID=value)
        self.assertEqual(result.returncode, 0, result.stderr)
        loaded = self.load_auth()
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        self.assertEqual(loaded.stdout, "tenant.domo.com|" + value)

    def test_failed_exchange_does_not_write_a_session(self):
        result = self.authenticate(FAKE_CURL_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.session.exists())

    def test_missing_access_token_does_not_become_a_session(self):
        result = self.authenticate(FAKE_EMPTY_ACCESS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no access token", result.stderr)
        self.assertFalse(self.session.exists())

    def test_invalid_authentication_host_is_rejected(self):
        for host in ("https://tenant.domo.com", "tenant.domo.com/path", "tenant.domo.com@evil.invalid"):
            with self.subTest(host=host):
                result = subprocess.run(["bash", str(SCRIPTS / "authenticate.sh"), host],
                                        env=self.env, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("hostname", result.stderr)
                self.assertFalse(self.session.exists())

    def test_mcp_reuses_cli_exchange_without_printing_credentials(self):
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; PYTHON_BIN="$(domo_find_python)"; '
             'domo_load_mcp_auth || exit; printf "%s" "$AUTH_METHOD"',
             "mcp-test", str(SCRIPTS / "lib/common.sh")],
            env=dict(self.env, INSTANCE="tenant.domo.com"), capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("temporary SID", result.stdout)
        self.assertNotIn("test-sid", result.stdout + result.stderr)

    def test_mcp_rejects_a_different_customers_cached_session(self):
        self.session.write_text("INSTANCE=other.domo.com\nSID=other-session\n")
        result = subprocess.run(
            ["bash", "-c", 'source "$1"; PYTHON_BIN="$(domo_find_python)"; domo_load_mcp_auth',
             "mcp-test", str(SCRIPTS / "lib/common.sh")],
            env=dict(self.env, INSTANCE="tenant.domo.com",
                     DOMO_RYUU_CONFIG=str(self.root / "no-login.json")),
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different instance", result.stderr)
        self.assertNotIn("other-session", result.stdout + result.stderr)

    def test_environment_session_takes_precedence_over_cached_customer(self):
        self.session.write_text("INSTANCE=other.domo.com\nSID=other-session\n")
        result = self.load_auth(INSTANCE="tenant.domo.com", SID="environment-session")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "tenant.domo.com|environment-session")

    def test_cached_session_cannot_silently_change_selected_instance(self):
        self.session.write_text("INSTANCE=other.domo.com\nSID=other-session\n")
        result = self.load_auth(INSTANCE="tenant.domo.com")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different instance", result.stderr)
        self.assertNotIn("other-session", result.stdout + result.stderr)

    def test_cached_session_is_loaded_when_no_target_is_selected(self):
        self.session.write_text("INSTANCE=tenant.domo.com\nSID=cached-session\n")
        result = self.load_auth()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "tenant.domo.com|cached-session")


if __name__ == "__main__":
    unittest.main()
