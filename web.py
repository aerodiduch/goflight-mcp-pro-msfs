"""Local live view on http://localhost:<port>, served from inside the bridge."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_HOSTS = ("localhost", "127.0.0.1")
ACTIONS = {"press", "knob", "switch", "event", "watch", "unwatch"}


class WebUI:
    def __init__(self, bridge, log_lines, port, log):
        self.bridge = bridge
        self.log_lines = log_lines
        self.port = port
        self.log = log
        self.server = None

    def start(self):
        ui = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _host_ok(self):
                # blocks DNS rebinding tricks from random web pages
                host = (self.headers.get("Host") or "").split(":")[0]
                return host in ALLOWED_HOSTS

            def _send(self, code, body=b"", ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not self._host_ok():
                    return self._send(403)
                if self.path == "/":
                    with open(os.path.join(HERE, "ui.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html; charset=utf-8")
                if self.path == "/state":
                    return self._send(200, json.dumps(ui.bridge.snapshot).encode())
                if self.path == "/stream":
                    return self._stream()
                self._send(404)

            def do_POST(self):
                if not self._host_ok():
                    return self._send(403)
                # requiring JSON forces a CORS preflight, so other sites can't post here
                if self.path != "/action" or "application/json" not in (self.headers.get("Content-Type") or ""):
                    return self._send(400)
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    action = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400)
                if action.get("type") not in ACTIONS:
                    return self._send(400)
                ui.bridge.actions.put(action)
                self._send(204)

            def _stream(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seq = ui.log_lines[0][0] - 1 if ui.log_lines else 0
                last_t = None
                try:
                    while True:
                        lines = [l for l in list(ui.log_lines) if l[0] > seq]
                        if lines:
                            seq = lines[-1][0]
                        snap = ui.bridge.snapshot
                        if lines or snap.get("t") != last_t:
                            last_t = snap.get("t")
                            msg = json.dumps({"state": snap, "log": [l[1] for l in lines]})
                            self.wfile.write(f"data: {msg}\n\n".encode())
                            self.wfile.flush()
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        except OSError as e:
            self.log(f"Live view disabled, port {self.port} is busy ({e}).")
            return
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.log(f"Live view: http://localhost:{self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
