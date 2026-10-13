import json
from pathlib import Path
import re
import sys
import threading
import unittest
import uuid
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "esp32_display"))
from app import Controller, HAClient, HAError, make_handler
from display_logic import GLYPHS, render_masks, source_value, validate_value


class FakeHA:
    def __init__(self):
        self.entities = {
            "text.esp32_display_value": {"state": "Err", "attributes": {"max": 3}},
            "sensor.result": {"state": "42", "attributes": {}},
        }
        self.calls = []
        self.fail_send = False

    def state(self, entity):
        if entity not in self.entities:
            raise HAError("Missing entity")
        return self.entities[entity]

    def send(self, entity, value):
        if self.fail_send:
            raise HAError("Offline")
        self.calls.append((entity, value))
        self.entities[entity]["state"] = value

    def states(self):
        return [dict(entity_id=k, **v) for k, v in self.entities.items()]


class ValueTests(unittest.TestCase):
    def test_supported_and_rejected_inputs(self):
        for value in ("", "123", "-99", "999", "GO", "LO", "SOS", "Err", " 1", "---", "___"):
            self.assertEqual(validate_value(value), value)
        for value in ("1000", "-100", "1.2", "ABCd", "M", "é", "1\n", 123, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_value(value)

    def test_alignment_and_blank(self):
        self.assertEqual(render_masks("1"), [0, 0, 0x06])
        self.assertEqual(render_masks(""), [0, 0, 0])
        self.assertEqual(render_masks("GO"), [0, 0x7D, 0x3F])
        self.assertEqual(render_masks("Err"), [0x79, 0x50, 0x50])

    def test_numeric_boundaries(self):
        for raw, expected in (("999", "999"), ("-99", "-99"), ("23.5", "24"),
                              ("-23.5", "-24"), ("-0.1", "0"), ("999.4", "999")):
            self.assertEqual(source_value(raw, "integer"), (expected, ""))
        for raw in ("1000", "999.5", "-99.5", "-100", "NaN", "Infinity", "1e999", "no"):
            self.assertEqual(source_value(raw, "integer")[0], "Err")

    def test_missing_or_unsupported_source(self):
        for raw in ("unknown", "unavailable", None, "LONG", "1.2", "M"):
            self.assertEqual(source_value(raw, "text")[0], "Err")
        self.assertEqual(source_value("GO", "text"), ("GO", ""))

    def test_firmware_and_app_glyphs_match(self):
        source = (ROOT / "esphome" / "esp32.yaml").read_text()
        cpp = source[source.index("auto glyph ="):source.index("std::array<uint32_t, 5> frame{0")]
        masks = {}
        for match in re.finditer(r"((?:case '[^']':\s*)+)return (0x[0-9A-Fa-f]+|0);", cpp):
            for char in re.findall(r"case '([^'])':", match[1]):
                masks[char] = int(match[2], 0)
        self.assertEqual(masks, GLYPHS)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        # Path.mkdir inherits the workspace ACL. Python 3.14's restrictive
        # TemporaryDirectory ACL excludes the Windows sandbox identity.
        self.temp = ROOT / "tests" / "runtime" / uuid.uuid4().hex
        self.temp.mkdir(parents=True)
        self.ha = FakeHA()
        self.now = 0
        self.c = Controller(self.ha, self.temp, clock=lambda: self.now)
        self.settings = {"target": "text.esp32_display_value", "source": "sensor.result",
                         "mode": "manual", "format": "text", "value": "123", "refresh_seconds": 60}

    def test_manual_send_refresh_clear_and_restart(self):
        self.c.configure(self.settings)
        self.assertEqual(self.ha.calls[-1][1], "123")
        self.now = 59
        self.c.tick()
        self.assertEqual(len(self.ha.calls), 1)
        self.now = 60
        self.c.tick()
        self.assertEqual(len(self.ha.calls), 2)
        restarted = Controller(self.ha, self.temp, clock=lambda: self.now)
        restarted.tick()
        self.assertEqual(len(self.ha.calls), 3)
        self.c.configure({**self.settings, "value": ""})
        self.assertEqual(self.ha.calls[-1][1], "")

    def test_follow_changes_and_manual_takeover(self):
        self.c.configure({**self.settings, "mode": "follow"})
        self.assertEqual(self.ha.calls[-1][1], "42")
        self.ha.entities["sensor.result"]["state"] = "GO"
        self.c.tick()
        self.assertEqual(self.ha.calls[-1][1], "GO")
        self.c.configure(self.settings)
        self.ha.entities["sensor.result"]["state"] = "LO"
        self.c.tick()
        self.assertEqual(self.ha.calls[-1][1], "123")

    def test_follow_unavailable_and_missing_source(self):
        self.c.configure({**self.settings, "mode": "follow"})
        self.ha.entities["sensor.result"]["state"] = "unavailable"
        self.c.tick()
        self.assertEqual(self.ha.calls[-1][1], "Err")
        self.assertTrue(self.c.status()["warning"])
        del self.ha.entities["sensor.result"]
        self.c.tick(force=True)
        self.assertEqual(self.ha.calls[-1][1], "Err")

    def test_offline_retry_does_not_record_failed_send(self):
        self.ha.fail_send = True
        self.c.configure(self.settings)
        self.assertIsNone(self.c.last_value)
        self.assertTrue(self.c.status()["error"])
        self.ha.fail_send = False
        self.c.tick()
        self.assertEqual(self.ha.calls[-1][1], "123")
        self.assertFalse(self.c.status()["error"])

    def test_unavailable_destination_and_feedback_rejected(self):
        self.ha.entities["text.esp32_display_value"]["state"] = "unavailable"
        with self.assertRaises(HAError): self.c.configure(self.settings)
        for change in ({"target": "sensor.result"}, {"source": "text.esp32_display_value"},
                       {"refresh_seconds": 180}, {"value": "1234"}, {"target": "../../bad"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.c.configure({**self.settings, **change})

    def test_persistence_failure_preserves_previous_mode(self):
        self.c.configure(self.settings)
        with patch.object(self.c, "save", side_effect=OSError("Disk full")):
            with self.assertRaises(OSError):
                self.c.configure({**self.settings, "mode": "follow"})
        self.assertEqual(self.c.settings["mode"], "manual")
        self.assertEqual(self.c.last_value, "123")

    def test_ingress_endpoints(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.c))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/") as response:
            self.assertIn(b"ESP32 Display", response.read())
        with urlopen(base + "/api/entities") as response:
            self.assertIn("glyphs", json.load(response))
        req = Request(base + "/api/settings", data=json.dumps(self.settings).encode(),
                      headers={"Content-Type": "application/json", "X-Display-App": "1"})
        with urlopen(req) as response:
            self.assertEqual(json.load(response)["last_sent_value"], "123")
        req = Request(base + "/api/settings", data=b"{}", headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error: urlopen(req)
        self.assertEqual(error.exception.code, 403)
        error.exception.close()


class RESTClientTests(unittest.TestCase):
    def test_real_http_transport_and_token(self):
        calls = []
        class HAHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                calls.append((self.path, self.headers.get("Authorization"), None))
                body = json.dumps({"state": "123"}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(body)
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, self.headers.get("Authorization"), body))
                self.send_response(200); self.end_headers(); self.wfile.write(b"[]")
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), HAHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        client = HAClient("test-token", f"http://127.0.0.1:{server.server_port}/api")
        client.state("text.esp32_display_value")
        client.send("text.esp32_display_value", "123")
        self.assertEqual(calls[0][0], "/api/states/text.esp32_display_value")
        self.assertEqual(calls[0][1], "Bearer test-token")
        self.assertEqual(calls[1][0], "/api/services/text/set_value")
        self.assertEqual(calls[1][2], {"entity_id": "text.esp32_display_value", "value": "123"})
        with self.assertRaises(HAError): HAClient("").states()


if __name__ == "__main__":
    unittest.main()
