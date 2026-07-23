
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 9012
HISTORY = []
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "TaskMockReceiver/1.0"

    def log_message(self, format, *args):
        return

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n > 0 else b""

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _record(self, body):
        with LOCK:
            HISTORY.append({
                "method": self.command,
                "path": self.path,
                "headers": {k: v for k, v in self.headers.items()},
                "body": body.decode("utf-8", errors="replace"),
                "ts": time.time(),
            })

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/health"):
            self._send_json(200, {"status": "ok", "history_count": len(HISTORY)})
            return
        if u.path == "/history":
            qs = parse_qs(u.query)
            since = float(qs.get("since", ["0"])[0])
            with LOCK:
                items = [h for h in HISTORY if h["ts"] >= since]
            self._send_json(200, items)
            return
        self._record(b"")
        self._send_json(200, {"received": True})

    def do_POST(self):
        body = self._read_body()
        self._record(body)
        if "/always-500" in self.path:
            self._send_json(500, {"intentional": "500 for retry test"})
            return
        self._send_json(200, {"received": True})

    do_PUT = do_POST
    do_PATCH = do_POST

    def do_DELETE(self):
        if urlparse(self.path).path == "/history":
            with LOCK:
                count = len(HISTORY)
                HISTORY.clear()
            self._send_json(200, {"cleared": count})
            return
        body = self._read_body()
        self._record(body)
        self._send_json(200, {"received": True})


def main():
    print("[mock-receiver] starting on 0.0.0.0:{}".format(PORT), flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
