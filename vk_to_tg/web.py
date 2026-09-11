from http.server import BaseHTTPRequestHandler, HTTPServer
import hmac
import json
import logging


log = logging.getLogger("vk_to_tg.web")


class Callback:
    def __init__(self, state, group_id: int, secret: str, confirmation: str):
        self.state = state
        self.group_id = group_id
        self.secret = secret
        self.confirmation = confirmation

    def handle(self, event: dict) -> tuple[int, str]:
        try:
            group_id = int(event.get("group_id", 0))
        except (TypeError, ValueError):
            return 400, "bad request"
        if group_id != self.group_id:
            return 403, "forbidden"
        if event.get("type") == "confirmation":
            return 200, self.confirmation
        if not hmac.compare_digest(str(event.get("secret", "")), self.secret):
            return 403, "forbidden"
        if event.get("type") != "wall_post_new":
            return 200, "ok"
        post = event.get("object", {})
        if isinstance(post, dict) and isinstance(post.get("post"), dict):
            post = post["post"]
        if not isinstance(post, dict) or "id" not in post or "owner_id" not in post:
            return 400, "bad request"
        if int(post["owner_id"]) != -self.group_id:
            return 403, "forbidden"
        self.state.enqueue(f"vk:{post['owner_id']}:{post['id']}", post)
        return 200, "ok"


def make_handler(callback: Callback, path: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "VKCallback/1"

        def do_POST(self):
            if self.path != path:
                self._reply(404, "not found")
                return
            if self.headers.get_content_type() != "application/json":
                self._reply(415, "unsupported media type")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2 * 1024 * 1024:
                    raise ValueError
                event = json.loads(self.rfile.read(length))
                if not isinstance(event, dict):
                    raise ValueError
            except (ValueError, json.JSONDecodeError):
                self._reply(400, "bad request")
                return
            status, body = callback.handle(event)
            self._reply(status, body)

        def do_GET(self):
            if self.path == "/health":
                self._reply(200, "ok")
            else:
                self._reply(404, "not found")

        def _reply(self, status: int, body: str):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format, *args):
            log.info("callback HTTP %s", args[1] if len(args) > 1 else "unknown")

    return Handler


def serve(callback: Callback, path: str, host: str, port: int, stop):
    server = HTTPServer((host, port), make_handler(callback, path))
    server.timeout = 1
    while not stop.is_set():
        server.handle_request()
    server.server_close()
