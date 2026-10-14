#!/usr/bin/env python3
"""Local server for Laura's page. Standard library only.

    python3 backend/server.py [--port 8787] [--provider claude|deepseek]

Serves frontend/ at http://localhost:8787/ and a small API:
  GET  /api/months                       month folders in data/, newest first, plus whether the API key is set
  POST /api/upload?month=YYYY-MM         multipart field "file" -> data/<month>/happier-hour.csv, then run_month.py
  POST /api/run?month=YYYY-MM[&no_api=1] run_month.py on the folder as it is
  GET  /api/tracker?month=YYYY-MM        data/<month>/tracker-page.json, or {}
  PUT  /api/tracker?month=YYYY-MM        write the JSON body to data/<month>/tracker-page.json

Listens on 127.0.0.1 only. API keys stay in the environment; run_month.py inherits it."""
import argparse
import json
import os
import re
import subprocess
import sys
import webbrowser
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vpm_core as core  # noqa: E402

core.load_dotenv()  # fills ANTHROPIC_API_KEY / DEEPSEEK_API_KEY / VPM_* from .env if not already set

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FRONTEND = ROOT / "frontend"
DATA = ROOT / "data"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".csv": "text/csv; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}
PROVIDER = "claude"
API_KEY_ENV = {"claude": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
API_KEY_SET = False


def count_matches(folder):
    try:
        return len(json.loads((folder / "validated.json").read_text(encoding="utf-8")).get("matches", []))
    except (OSError, ValueError):
        return 0


def run_month(folder, no_api=False):
    cmd = [sys.executable, str(HERE / "run_month.py"), "--folder", str(folder), "--provider", PROVIDER]
    if no_api:
        cmd.append("--no-api")
    env = dict(os.environ, PYTHONUNBUFFERED="1")  # keeps step output in order with the child scripts
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode == 0:
        return 200, {"ok": True, "log": r.stdout, "matches": count_matches(folder)}
    return 500, {"ok": False, "log": r.stdout}


def parse_upload(content_type, body):
    """Return the bytes of the multipart field named "file", or None."""
    msg = BytesParser(policy=email_policy).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    if not msg.is_multipart():
        return None
    for part in msg.iter_parts():
        if part.get_param("name", header="content-disposition") == "file":
            return part.get_payload(decode=True) or b""
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "VoltaPeerMatch"

    def send_json(self, code, obj):
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n > 0 else b""

    def route(self):
        u = urlparse(self.path)
        return u.path, parse_qs(u.query)

    def month_folder(self, q):
        """data/<month> for a valid ?month=, else sends 400 and returns None."""
        m = (q.get("month") or [""])[0]
        if not MONTH_RE.match(m):
            self.send_json(400, {"ok": False, "log": "month must be YYYY-MM"})
            return None
        return DATA / m

    # ---- GET
    def do_GET(self):
        path, q = self.route()
        if path.startswith("/api/"):
            if path == "/api/months":
                if q:
                    return self.send_json(400, {"ok": False, "log": "no parameters expected"})
                months = sorted((d for d in DATA.iterdir() if d.is_dir() and MONTH_RE.match(d.name)),
                                key=lambda d: d.name, reverse=True) if DATA.is_dir() else []
                return self.send_json(200, {"months": [{"month": d.name, "processed": (d / "validated.json").exists()}
                                                        for d in months],
                                            "api_key_set": API_KEY_SET})
            if path == "/api/tracker":
                folder = self.month_folder(q)
                if folder is None:
                    return
                f = folder / "tracker-page.json"
                try:
                    return self.send_json(200, json.loads(f.read_text(encoding="utf-8")) if f.exists() else {})
                except ValueError:
                    return self.send_json(200, {})
            return self.send_json(404, {"ok": False, "log": "unknown endpoint"})
        self.serve_static(path)

    def serve_static(self, path):
        rel = unquote(path).lstrip("/") or "index.html"
        if "\x00" in rel or ".." in Path(rel).parts:
            return self.send_json(400, {"ok": False, "log": "bad path"})
        target = (FRONTEND / rel).resolve()
        if target != FRONTEND and FRONTEND not in target.parents:
            return self.send_json(403, {"ok": False, "log": "forbidden"})
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self.send_json(404, {"ok": False, "log": "not found"})
        raw = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(target.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    # ---- POST
    def do_POST(self):
        path, q = self.route()
        if path not in ("/api/upload", "/api/run"):
            return self.send_json(404, {"ok": False, "log": "unknown endpoint"})
        folder = self.month_folder(q)
        if folder is None:
            return
        if path == "/api/upload":
            ctype = self.headers.get("Content-Type", "")
            if not ctype.startswith("multipart/form-data"):
                return self.send_json(400, {"ok": False, "log": "expected multipart/form-data"})
            data = parse_upload(ctype, self.read_body())
            if not data:
                return self.send_json(400, {"ok": False, "log": "no file in field 'file'"})
            folder.mkdir(parents=True, exist_ok=True)
            csv_path = folder / "happier-hour.csv"
            if csv_path.exists():
                csv_path.unlink()  # the old export may be read-only
            csv_path.write_bytes(data)
        elif not folder.is_dir():
            return self.send_json(400, {"ok": False, "log": f"no folder data/{folder.name}"})
        code, obj = run_month(folder, no_api=(q.get("no_api") or [""])[0] == "1")
        self.send_json(code, obj)

    # ---- PUT
    def do_PUT(self):
        path, q = self.route()
        if path != "/api/tracker":
            return self.send_json(404, {"ok": False, "log": "unknown endpoint"})
        folder = self.month_folder(q)
        if folder is None:
            return
        try:
            obj = json.loads(self.read_body().decode("utf-8") or "{}")
        except (UnicodeDecodeError, ValueError):
            return self.send_json(400, {"ok": False, "log": "body is not JSON"})
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / "tracker-page.json.tmp"
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(folder / "tracker-page.json")
        self.send_json(200, {"ok": True})

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    global PROVIDER, API_KEY_SET
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--provider", choices=["claude", "deepseek"], default=os.environ.get("VPM_PROVIDER") or "claude")
    p.add_argument("--no-browser", action="store_true", help="do not open the page automatically")
    a = p.parse_args()
    PROVIDER = a.provider
    key_env = API_KEY_ENV[PROVIDER]
    API_KEY_SET = bool(os.environ.get(key_env))
    if not API_KEY_SET:
        print(f"\nWARNING: {key_env} is not set. Uploads will stop at match.py.\n"
              f"Set it in this terminal first:  export {key_env}=...\n", flush=True)
    httpd = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://localhost:{a.port}/"
    print(f"Volta Peer Match on {url}  (provider: {PROVIDER}). Ctrl+C to stop.", flush=True)
    if not a.no_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
