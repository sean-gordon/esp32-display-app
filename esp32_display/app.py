"""Home Assistant ingress app; no external Python dependencies."""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from display_logic import GLYPHS, source_value, validate_value

LOG = logging.getLogger("esp32_display")
ENTITY = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
DEFAULTS = {"target": "", "source": "", "mode": "manual", "format": "text", "value": "", "refresh_seconds": 60}


class HAError(Exception):
    pass


class HAClient:
    def __init__(self, token, base="http://supervisor/core/api"):
        self.token = token
        self.base = base.rstrip("/")

    def request(self, path, data=None):
        if not self.token:
            raise HAError("Supervisor API token is missing. Start this app through Home Assistant Apps.")
        req = Request(self.base + path, data=None if data is None else json.dumps(data).encode(),
                      headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=8) as response:
                return json.load(response)
        except HTTPError as exc:
            raise HAError(f"Home Assistant returned HTTP {exc.code}. Check the ESPHome entity and connection.") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise HAError("Cannot reach Home Assistant. The app will retry automatically.") from None

    def states(self):
        return self.request("/states")

    def state(self, entity_id):
        if not ENTITY.fullmatch(entity_id): raise ValueError("Invalid entity ID.")
        return self.request("/states/" + entity_id)

    def send(self, entity_id, value):
        self.request("/services/text/set_value", {"entity_id": entity_id, "value": value})


class Controller:
    def __init__(self, client, data_dir, clock=time.monotonic):
        self.client = client
        self.clock = clock
        self.lock = threading.RLock()
        self.file = Path(data_dir) / "display_settings.json"
        self.settings = DEFAULTS.copy()
        self.last_value = None
        self.last_sent = None
        self.last_error = ""
        self.source_warning = ""
        self.last_send_at = -float("inf")
        if self.file.exists():
            try:
                saved = json.loads(self.file.read_text())
                self.settings = self.valid_settings(saved)
            except (OSError, ValueError, TypeError):
                LOG.warning("Saved settings invalid; using defaults")

    @staticmethod
    def valid_settings(data):
        if not isinstance(data, dict): raise ValueError("Settings must be an object.")
        s = {k: data.get(k, v) for k,v in DEFAULTS.items()}
        if s["mode"] not in {"manual", "follow"}: raise ValueError("Choose manual or follow mode.")
        if s["format"] not in {"text", "integer"}: raise ValueError("Choose text or integer formatting.")
        for key in ("target", "source"):
            if not isinstance(s[key], str) or (s[key] and not ENTITY.fullmatch(s[key])):
                raise ValueError("Select a valid Home Assistant entity.")
        if s["target"] and not s["target"].startswith("text."):
            raise ValueError("Destination must be the ESP32 Display value text entity.")
        if s["source"] and s["source"] == s["target"]:
            raise ValueError("Source and destination must be different entities.")
        if type(s["refresh_seconds"]) is not int or not 10 <= s["refresh_seconds"] <= 120:
            raise ValueError("Refresh interval must be between 10 and 120 seconds.")
        validate_value(s["value"])
        return s

    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        temp.replace(self.file)

    def configure(self, data):
        s = self.valid_settings(data)
        if not s["target"]: raise ValueError("Select the ESP32 destination first.")
        if s["mode"] == "follow" and not s["source"]: raise ValueError("Select a source entity to follow.")
        with self.lock:
            target = self.client.state(s["target"])
            if target.get("state") in {"unknown", "unavailable"}:
                raise HAError("ESP32 destination is unavailable. Check its Wi-Fi and ESPHome connection.")
            if target.get("attributes", {}).get("max", 3) != 3:
                raise ValueError("Select the ESP32 three-character Display value entity.")
            previous = self.settings
            self.settings = s
            try:
                self.save()
            except OSError:
                self.settings = previous
                raise
            self.last_value = None
            self.source_warning = ""
            self.last_error = ""
            self.tick(force=True)
            return self.status()

    def tick(self, force=False):
        with self.lock:
            s = self.settings
            if not s["target"]: return
            try:
                value = s["value"]
                self.source_warning = ""
                if s["mode"] == "follow":
                    # Source errors should produce Err, not keep renewing a healthy value.
                    try:
                        source = self.client.state(s["source"])
                    except HAError:
                        value, self.source_warning = "Err", "Source cannot be read."
                    else:
                        value, self.source_warning = source_value(source.get("state"), s["format"])
                if force or value != self.last_value or self.clock() - self.last_send_at >= s["refresh_seconds"]:
                    target = self.client.state(s["target"])
                    if target.get("state") in {"unknown", "unavailable"}:
                        raise HAError("ESP32 destination is unavailable; waiting for it to reconnect.")
                    self.client.send(s["target"], value)
                    self.last_value = value
                    self.last_send_at = self.clock()
                    self.last_sent = datetime.now(timezone.utc).isoformat()
                self.last_error = ""
            except HAError as exc:
                self.last_error = str(exc)

    def status(self):
        with self.lock:
            return {"settings": self.settings.copy(), "last_sent_value": self.last_value,
                    "last_sent_at": self.last_sent, "error": self.last_error, "warning": self.source_warning}

    def entities(self):
        result = []
        for s in self.client.states():
            entity = s.get("entity_id", "")
            if entity.split(".", 1)[0] in {"text", "sensor", "input_text", "input_number", "number", "select", "input_select"}:
                result.append({"entity_id": entity, "name": s.get("attributes", {}).get("friendly_name", entity),
                               "state": s.get("state"), "max": s.get("attributes", {}).get("max")})
        return sorted(result, key=lambda e: (e["name"].casefold(), e["entity_id"]))


def make_handler(controller):
    class Handler(BaseHTTPRequestHandler):
        def send_body(self, code, body, content_type="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, code, obj):
            self.send_body(code, json.dumps(obj).encode())

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            try:
                if path in {"/", "/index.html"}:
                    self.send_body(200, Path(__file__).with_name("index.html").read_bytes(), "text/html; charset=utf-8")
                elif path == "/api/status": self.send_json(200, controller.status())
                elif path == "/api/entities": self.send_json(200, {"entities": controller.entities(), "glyphs": GLYPHS})
                else: self.send_json(404, {"error": "Not found"})
            except HAError as exc: self.send_json(503, {"error": str(exc)})
            except OSError:
                LOG.exception("App file read failed")
                self.send_json(500, {"error": "App file could not be read."})

        def do_POST(self):
            if self.path != "/api/settings":
                self.send_json(404, {"error": "Not found"}); return
            if self.headers.get("X-Display-App") != "1" or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self.send_json(403, {"error": "Use the app interface to change the display."}); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096: raise ValueError("Invalid request size.")
                data = json.loads(self.rfile.read(length))
                self.send_json(200, controller.configure(data))
            except (ValueError, TypeError) as exc: self.send_json(400, {"error": str(exc)})
            except HAError as exc: self.send_json(503, {"error": str(exc)})
            except OSError:
                LOG.exception("Settings could not be saved")
                self.send_json(500, {"error": "Settings could not be saved."})

        def log_message(self, format, *args):
            # No API token, payload, or source value is logged.
            LOG.debug("HTTP request completed")
    return Handler


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    client = HAClient(os.environ.get("SUPERVISOR_TOKEN", ""))
    controller = Controller(client, os.environ.get("DISPLAY_DATA_DIR", "/data"))
    stop = threading.Event()
    def refresh():
        while not stop.is_set():
            try: controller.tick()
            except Exception:
                LOG.exception("Display refresh failed; retrying")
            stop.wait(5)
    worker = threading.Thread(target=refresh, daemon=True)
    worker.start()
    server = ThreadingHTTPServer(("0.0.0.0", 8099), make_handler(controller))
    LOG.info("ESP32 Display app ready on ingress port 8099")
    try: server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        worker.join(timeout=10)


if __name__ == "__main__":
    run()
