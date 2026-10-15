"""Offline checks at the deployment authentication boundary."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("deployment_client", Path(__file__).resolve().parents[1] / "scripts/provision_domo.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DeploymentSafety(unittest.TestCase):
    def client(self):
        with patch.dict(os.environ, {"DOMO_DEVELOPER_TOKEN": "test-token"}):
            return MODULE.DomoClient("tenant.domo.com")

    def test_missing_or_malformed_instance_is_rejected_before_auth(self):
        for instance in ("", "https://tenant.domo.com", "tenant.domo.com/path", "tenant.domo.com@evil.invalid", "localhost", "tenant.domo.com:443"):
            with self.subTest(instance=instance), patch.object(MODULE.DomoClient, "refresh_sid") as auth:
                with self.assertRaises(ValueError):
                    MODULE.DomoClient(instance)
                auth.assert_not_called()

    def test_credentials_cannot_leave_the_selected_https_origin(self):
        client = self.client()
        for path in ("https://other.domo.com/api/data", "https://evil.invalid/", "http://tenant.domo.com/api/data", "https://tenant.domo.com@evil.invalid/api/data", "https://tenant.domo.com/api/data#fragment"):
            with self.subTest(path=path), patch.object(client, "_open") as send:
                with self.assertRaises(ValueError):
                    client.request("GET", path)
                send.assert_not_called()

    def test_redirect_handler_never_forwards_custom_authentication_headers(self):
        client = self.client()
        handlers = client._open.__self__.handlers
        blocker = next(h for h in handlers if type(h).__name__ == "NoRedirect")
        self.assertIsNone(blocker.redirect_request(None, None, 302, "", {}, "https://evil.invalid/"))

    def test_error_message_omits_raw_customer_body(self):
        error = MODULE.DomoApiError("GET", "/api/data", 403, "private-response-value")
        self.assertNotIn("private-response-value", str(error))


if __name__ == "__main__":
    unittest.main()
