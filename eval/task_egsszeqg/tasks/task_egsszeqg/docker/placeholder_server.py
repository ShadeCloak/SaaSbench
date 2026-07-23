import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


APP_PORT = int(os.environ.get("APP_PORT", "8014"))
PUBLIC_APP_PORT = int(os.environ.get("PUBLIC_APP_PORT", str(APP_PORT)))


class PlaceholderHandler(BaseHTTPRequestHandler):
    server_version = "TaskBootstrap/1.0"

    def _write(self, status_code: int, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path in {"/healthz", "/"}:
            self._write(
                200,
                {
                    "status": "ok",
                    "message": "workspace is empty; bootstrap environment is ready behind nginx",
                    "public_port": PUBLIC_APP_PORT,
                    "upstream_port": APP_PORT,
                },
            )
            return
        self._write(
            404,
            {
                "status": "not_ready",
                "message": "application code has not been added to /app yet",
                "path": self.path,
            },
        )

    def do_HEAD(self) -> None:
        self.do_GET()

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", APP_PORT), PlaceholderHandler)
    server.serve_forever()
