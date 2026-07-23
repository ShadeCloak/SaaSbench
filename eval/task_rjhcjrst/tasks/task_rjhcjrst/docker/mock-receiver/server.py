#!/usr/bin/env python3
import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()
HISTORY: list[dict] = []
PORT = 9001


def record(handler: BaseHTTPRequestHandler) -> None:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    body = handler.rfile.read(length).decode("utf-8", errors="replace") if length else ""
    entry = {
        "received_at": time.time(),
        "method": handler.command,
        "path": handler.path,
        "headers": {k.lower(): v for k, v in handler.headers.items()},
        "body": body,
        "remote_addr": f"{handler.client_address[0]}:{handler.client_address[1]}",
    }
    with LOCK:
        HISTORY.append(entry)
    return entry


def reply(handler: BaseHTTPRequestHandler, status: int, body: str = "", ctype: str = "application/json") -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body.encode("utf-8"))))
    handler.send_header("Connection", "close")
    handler.end_headers()
    if body:
        handler.wfile.write(body.encode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def do_POST(self) -> None:
        record(self)
        if self.path == "/always-500" or self.path.startswith("/always-500?"):
            reply(self, 500, json.dumps({"status": "always-500"}))
            return
        if self.path == "/hook" or self.path.startswith("/hook?"):
            reply(self, 200, json.dumps({"status": "ok"}))
            return
        reply(self, 200, json.dumps({"status": "ok", "default_handler": True}))

    def do_PUT(self) -> None:
        record(self)
        reply(self, 200, json.dumps({"status": "ok"}))

    def do_DELETE(self) -> None:
        if self.path == "/history" or self.path.startswith("/history?"):
            with LOCK:
                HISTORY.clear()
            reply(self, 204, "")
            return
        record(self)
        reply(self, 200, json.dumps({"status": "ok"}))

    def do_GET(self) -> None:
        if self.path == "/health" or self.path.startswith("/health?"):
            reply(self, 200, "ok", ctype="text/plain")
            return
        if self.path == "/history" or self.path.startswith("/history?"):
            since = 0.0
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            for pair in qs.split("&"):
                if pair.startswith("since="):
                    try:
                        since = float(pair.split("=", 1)[1])
                    except ValueError:
                        since = 0.0
            with LOCK:
                items = [e for e in HISTORY if e["received_at"] >= since]
            reply(self, 200, json.dumps({"count": len(items), "items": items}))
            return
        record(self)
        reply(self, 404, json.dumps({"status": "not-found", "path": self.path}))


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[mock-receiver] listening on 0.0.0.0:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[mock-receiver] shutting down", flush=True)


if __name__ == "__main__":
    main()
