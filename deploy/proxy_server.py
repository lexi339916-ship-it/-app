# -*- coding: utf-8 -*-
"""本地/隧道部署用的单端口服务：静态 H5 + /api 反向代理。

用途：
- 没有 Nginx 时，一条命令让前端和 API 同源，避免 CORS；
- 配合 cloudflared/ngrok/服务器反代即可暴露公网。

运行：
    python deploy/proxy_server.py --port 8080 --backend http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "h5"
BACKEND = "http://127.0.0.1:8000"
FORWARD_HEADERS = ("Authorization", "Content-Type", "Accept", "Cookie",
                   "Origin", "Referer", "User-Agent")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print(f"[web] {self.address_string()} {fmt % args}")

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None
        url = BACKEND + self.path
        request = urllib.request.Request(url, data=body, method=self.command)
        for name in FORWARD_HEADERS:
            value = self.headers.get(name)
            if value:
                request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() in ("transfer-encoding", "connection", "content-length"):
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as exc:
            data = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            data = json.dumps(
                {"code": 502, "message": f"后端不可达：{exc}"},
                ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def _is_api(self) -> bool:
        return self.path.split("?")[0].startswith("/api/")

    def do_GET(self):
        if self._is_api():
            return self._proxy()
        return super().do_GET()

    def do_POST(self):
        if self._is_api():
            return self._proxy()
        self.send_error(404)

    def do_PUT(self):
        if self._is_api():
            return self._proxy()
        self.send_error(404)

    def do_DELETE(self):
        if self._is_api():
            return self._proxy()
        self.send_error(404)

    def do_PATCH(self):
        if self._is_api():
            return self._proxy()
        self.send_error(404)

    def send_head(self):
        path = self.path.split("?")[0]
        # SPA 路由（没有文件后缀）回退到 index.html
        if path != "/" and "." not in path.rsplit("/", 1)[-1]:
            self.path = "/index.html"
        return super().send_head()


def main() -> None:
    global BACKEND, ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--root", default="")
    args = parser.parse_args()
    BACKEND = args.backend.rstrip("/")
    if args.root:
        ROOT = Path(args.root)
    if not (ROOT / "index.html").exists():
        raise SystemExit(f"找不到前端构建产物：{ROOT / 'index.html'}")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"知账同源服务：http://{args.host}:{args.port}  ->  API {BACKEND}")
    print("可用 cloudflared/ngrok 或 Nginx 将本端口暴露到公网。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
