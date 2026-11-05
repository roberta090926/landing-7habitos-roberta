import io
import json
import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app

EID = "rbvc-" + "a" * 32
ORIGIN = "https://7habitos.robertabitencourt.com.br"


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "META_CAPI_ACCESS_TOKEN": "fake-test-token-not-real",
            "META_GRAPH_VERSION": "v99.0",
            "RB_CAPI_SIGNING_SECRET": "test-signing-secret-" + "x" * 48,
            "RB_CAPI_ALLOWED_ORIGIN": ORIGIN,
        })
        self.env.start()
        app._requests.clear()
        app._sent.clear()

    def tearDown(self):
        self.env.stop()

    def call(self, path, method="GET", data=None, origin=ORIGIN, query="", ip="198.51.100.10"):
        raw = b"" if data is None else json.dumps(data).encode("utf-8")
        e = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "HTTP_ORIGIN": origin,
            "REMOTE_ADDR": ip,
            "HTTP_USER_AGENT": "Test Browser 1",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(raw)),
            "wsgi.input": io.BytesIO(raw),
        }
        result = {}
        def start(status, headers):
            result["status"] = status
            result["headers"] = dict(headers)
        body = b"".join(app.application(e, start))
        return result["status"], json.loads(body) if body else {}, result["headers"]

    def token(self):
        status, data, _ = self.call("/v1/view-token", query="event_id=" + EID)
        self.assertTrue(status.startswith("200"))
        return data

    def post(self, token, extra=None):
        data = {"event_id": EID, "expires": token["expires"],
                "signature": token["signature"], "consent": True}
        data.update(extra or {})
        return self.call("/v1/view-content", "POST", data)

    def test_health_has_no_secrets(self):
        status, body, headers = self.call("/health", origin=None)
        self.assertEqual(status, "200 OK")
        self.assertEqual(body, {"status": "ok"})
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_mismatched_origin_is_rejected(self):
        status, body, _ = self.call("/v1/view-token", origin="https://other.example",
                                    query="event_id=" + EID)
        self.assertEqual(status, "403 Forbidden")

    def test_token_is_valid_hmac(self):
        token = self.token()
        self.assertEqual(token["event_id"], EID)
        self.assertEqual(token["signature"], app._signature(EID, token["expires"],
                          os.environ["RB_CAPI_SIGNING_SECRET"]))

    @patch.object(app, "_send_meta", return_value=True)
    def test_success_and_repeat_are_deduplicated(self, send):
        token = self.token()
        a, resp, _ = self.post(token, {"fbp": "fb.1.1795555555555.1234567890"})
        b, repeated, _ = self.post(token)
        self.assertEqual(a, "200 OK")
        self.assertTrue(resp["ok"])
        self.assertEqual(b, "200 OK")
        self.assertTrue(repeated["duplicate"])
        send.assert_called_once()
        event = send.call_args.args[0]
        self.assertEqual(event["event_name"], "ViewContent")
        self.assertEqual(event["event_id"], EID)
        self.assertEqual(event["action_source"], "website")
        self.assertEqual(event["user_data"]["client_user_agent"], "Test Browser 1")
        self.assertIn("fbp", event["user_data"])
        self.assertNotIn("custom_data", event)
        self.assertNotIn("email", json.dumps(event).lower())

    @patch.object(app, "_send_meta", return_value=True)
    def test_invalid_signature_never_reaches_meta(self, send):
        token = self.token()
        status, _, _ = self.post(token, {"signature": "0" * 64})
        self.assertEqual(status, "400 Bad Request")
        send.assert_not_called()

    @patch.object(app, "_send_meta", return_value=True)
    def test_expired_token_rejected(self, send):
        token = self.token()
        token["expires"] = int(time.time()) - 50
        token["signature"] = app._signature(EID, token["expires"],
                                           os.environ["RB_CAPI_SIGNING_SECRET"])
        status, _, _ = self.post(token)
        self.assertEqual(status, "400 Bad Request")
        send.assert_not_called()

    @patch.object(app, "_send_meta", return_value=True)
    def test_consent_is_required(self, send):
        token = self.token()
        status, _, _ = self.post(token, {"consent": False})
        self.assertEqual(status, "400 Bad Request")
        send.assert_not_called()

    @patch.object(app, "_send_meta", return_value=True)
    def test_bad_fbp_rejected(self, send):
        token = self.token()
        status, _, _ = self.post(token, {"fbp": "email@example.com"})
        self.assertEqual(status, "400 Bad Request")
        send.assert_not_called()

    @patch.object(app, "_send_meta", return_value=False)
    def test_meta_failure_not_acknowledged(self, send):
        token = self.token()
        status, res, _ = self.post(token)
        self.assertEqual(status, "502 Bad Gateway")
        self.assertFalse(res["ok"])
        self.assertNotIn(EID, app._sent)

    def test_rate_limit(self):
        for i in range(24):
            st, _, _ = self.call("/v1/view-token", query="event_id=" + EID)
            self.assertEqual(st, "200 OK")
        st, _, _ = self.call("/v1/view-token", query="event_id=" + EID)
        self.assertEqual(st, "429 Too Many Requests")

    def test_no_config_rejected(self):
        with patch.dict(os.environ, {"META_CAPI_ACCESS_TOKEN": ""}):
            st, _, _ = self.call("/v1/view-token", query="event_id=" + EID)
            self.assertEqual(st, "503 Service Unavailable")


if __name__ == "__main__":
    unittest.main()
