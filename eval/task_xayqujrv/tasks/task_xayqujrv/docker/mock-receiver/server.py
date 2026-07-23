#!/usr/bin/env python3
"""Mock HTTP receiver for Stage 5 P27 (webhook delivery) evaluator nodes.

A self-contained, dependency-free HTTP server that records every inbound webhook
and exposes a query interface. Replaces `mendhak/http-https-echo` which lacks a
history/query endpoint.

Endpoints:
    POST /hook                     accepts a webhook, returns 200
    POST /always-500               accepts a webhook, returns 500 (for retry tests)
    POST /delay/<seconds>          accepts a webhook after the specified delay, returns 200
    GET  /history?since=<ts>       lists the recorded events (optionally filtered by epoch ts)
    DELETE /history                clears the in-memory history
    GET  /health                   liveness probe

Example:
    curl -X POST http://localhost:9001/hook \\
         -H 'Content-Type: application/json' \\
         -H 'X-Webhook-Signature: sha256=abc...' \\
         -d '{"event":"FLAG_UPDATED"}'

    curl http://localhost:9001/history | jq

The server stores up to 1000 recent events in memory. Restart clears state.
"""
import json
import re
import sys
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = 9001
MAX_HISTORY = 1000

_history: deque = deque(maxlen=MAX_HISTORY)
_lock = Lock()


def _record(method: str, path: str, headers: dict, body: bytes, status: int) -> None:
    try:
        body_text = body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = repr(body)
    try:
        body_json = json.loads(body_text) if body_text else None
    except (json.JSONDecodeError, ValueError):
        body_json = None
    event = {
        "received_at": time.time(),
        "received_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "method": method,
        "path": path,
        "headers": {k: v for k, v in headers.items()},
        "body_text": body_text,
        "body_json": body_json,
        "status": status,
    }
    with _lock:
        _history.append(event)


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    return handler.rfile.read(length) if length > 0 else b""


def _send(handler: BaseHTTPRequestHandler, status: int, body: dict) -> None:
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class MockReceiver(BaseHTTPRequestHandler):
    server_version = "MockWebhookReceiver/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[mock-receiver] %s - %s\n" % (self.address_string(), fmt % args))

    # ---------------- GET ----------------
    def do_GET(self):
        if self.path == "/health":
            _send(self, 200, {"status": "ok", "history_len": len(_history)})
            return
        if self.path.startswith("/history"):
            try:
                since = float(re.search(r"since=([0-9.]+)", self.path).group(1))
            except (AttributeError, ValueError):
                since = 0.0
            with _lock:
                events = [e for e in _history if e["received_at"] >= since]
            _send(self, 200, {"count": len(events), "events": events})
            return
        _send(self, 404, {"error": "not_found", "path": self.path})

    # ---------------- DELETE ----------------
    def do_DELETE(self):
        if self.path == "/history":
            with _lock:
                _history.clear()
            _send(self, 200, {"status": "cleared"})
            return
        _send(self, 404, {"error": "not_found"})

    # ---------------- POST ----------------
    def do_POST(self):
        body = _read_body(self)
        if self.path == "/hook":
            _record("POST", self.path, self.headers, body, 200)
            _send(self, 200, {"status": "received", "byte_count": len(body)})
            return
        if self.path == "/always-500":
            _record("POST", self.path, self.headers, body, 500)
            _send(self, 500, {"status": "intentional_failure"})
            return
        m = re.match(r"^/delay/([0-9]+)$", self.path)
        if m:
            delay = min(int(m.group(1)), 30)
            time.sleep(delay)
            _record("POST", self.path, self.headers, body, 200)
            _send(self, 200, {"status": "delayed_received", "delay_s": delay})
            return
        _record("POST", self.path, self.headers, body, 200)
        _send(self, 200, {"status": "received_catchall", "path": self.path})


def main() -> None:
    sys.stderr.write(f"[mock-receiver] starting on 0.0.0.0:{PORT}\n")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), MockReceiver)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("[mock-receiver] shutting down\n")
        server.server_close()


if __name__ == "__main__":
    main()
