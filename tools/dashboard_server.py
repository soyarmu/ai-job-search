#!/usr/bin/env python3
"""Serve the application dashboard plus CV/summary generation APIs.

GET  /             -> latest dashboard HTML (reports/application-dashboard.html)
POST /api/cv       -> generate a tailored CV (tools/gen_cv.py --json)
POST /api/summary  -> generate a neutral one-line summary (tools/gen_cv.py --summarize-only --json)

Body is JSON: {"url": ...} and/or {"text": ...}, optional {"company":..., "role":...}.
Local only (127.0.0.1), one job at a time, 100KB body cap, 5 min subprocess timeout.
"""
import json
import os
import subprocess
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DASHBOARD = os.path.join(ROOT, "reports", "application-dashboard.html")
GEN_CV = os.path.join(ROOT, "tools", "gen_cv.py")
HOST, PORT = "127.0.0.1", 8765
MAX_BODY = 100 * 1024
TIMEOUT = 300

lock = threading.Lock()


def read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    if length > MAX_BODY:
        return None
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def local_only(handler):
    host = (handler.headers.get("Host") or "").split(":")[0]
    origin = (handler.headers.get("Origin") or "").split("://")[-1].split("/")[0].split(":")[0]
    return (host in ("127.0.0.1", "localhost") and origin in ("127.0.0.1", "localhost", ""))


def build_args(body, summarize):
    args = ["python3", GEN_CV]
    if summarize:
        args.append("--summarize-only")
    args.append("--json")
    if body.get("url"):
        args.append(body["url"])
    company = body.get("company")
    role = body.get("role")
    if company:
        args += ["--company", company]
    if role:
        args += ["--role", role]
    if body.get("force"):
        args.append("--force")
    text = body.get("text")
    if text:
        # pasted text goes to a temp file
        fd, path = tempfile.mkstemp(suffix=".txt", prefix="posting_", dir=os.path.join(ROOT, "job_scraper"))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        args += ["--file", path]
        if body.get("url"):
            args += ["--source", body["url"]]
    return args


def run_gen(args):
    try:
        r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 504, {"error": "timed out after %ss" % TIMEOUT}
    out = r.stdout.strip()
    if r.returncode != 0:
        msg = out or r.stderr.strip() or "gen_cv.py failed"
        return 500, {"error": msg}
    try:
        return 200, json.loads(out.splitlines()[-1])
    except (ValueError, IndexError):
        return 200, {"error": "empty result", "raw": out[:500]}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            if not os.path.exists(DASHBOARD):
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"dashboard not generated; run /html-report first")
                return
            with open(DASHBOARD, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not local_only(self):
            self._send(403, {"error": "forbidden"})
            return
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/cv", "/api/summary"):
            self._send(404, {"error": "not found"})
            return
        body = read_body(self)
        if body is None:
            self._send(413, {"error": "body too large or not JSON"})
            return
        if not body.get("url") and not body.get("text"):
            self._send(400, {"error": "provide url or text"})
            return
        if not lock.acquire(blocking=False):
            self._send(429, {"error": "busy: another job is running"})
            return
        try:
            args = build_args(body, path == "/api/summary")
            code, result = run_gen(args)
        except Exception as e:  # never leak internals/keys
            code, result = 500, {"error": "internal error"}
        finally:
            lock.release()
        self._send(code, result)

    def log_message(self, fmt, *args):
        pass  # silence per-request logging (which would echo request lines)


if __name__ == "__main__":
    srv = HTTPServer((HOST, PORT), Handler)
    print(f"Serving {DASHBOARD} at http://{HOST}:{PORT}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
