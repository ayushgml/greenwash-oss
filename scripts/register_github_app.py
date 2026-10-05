"""Register a Greenwash GitHub App with the manifest flow and store its credentials on Railway.

    uv run python scripts/register_github_app.py --host https://<service>.up.railway.app \
        --name greenwash-jev-buildathon --service greenwash

Open the printed local URL, then click "Create GitHub App" on GitHub. The app's private key and
webhook secret go from GitHub's response straight into `railway variable set --stdin`; they are
never printed or written to disk. Only the app id, slug and install URL are shown.
"""

from __future__ import annotations

import argparse
import html
import json
import secrets
import ssl
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import certifi

# python.org builds of Python do not use the macOS keychain; verify TLS against certifi's CA bundle.
TLS = ssl.create_default_context(cafile=certifi.where())

PORT = 8799


def manifest(host: str, name: str) -> dict:
    return {
        "name": name,
        "url": host,
        "hook_attributes": {"url": f"{host}/api/github/webhook", "active": True},
        "redirect_url": f"http://127.0.0.1:{PORT}/callback",
        "public": False,
        "default_permissions": {"checks": "write", "contents": "read", "pull_requests": "write", "metadata": "read"},
        "default_events": ["pull_request"],
    }


def railway_set(service: str, name: str, value: str, *, deploy: bool) -> None:
    args = ["railway", "variable", "set", name, "--stdin", "--service", service]
    if not deploy:
        args.append("--skip-deploys")
    subprocess.run(args, input=value, text=True, check=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--service", default="greenwash")
    parser.add_argument("--resume", action="store_true",
                        help="accept one callback started by an earlier run of this script (its state value is gone); "
                             "use only to finish a registration whose code exchange failed")
    args = parser.parse_args()
    host = args.host.rstrip("/")
    state = secrets.token_urlsafe(16)
    done = threading.Event()
    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # keep codes and query strings out of the terminal
            pass

        def _send(self, body: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                data = html.escape(json.dumps(manifest(host, args.name)), quote=True)
                self._send(
                    "<!doctype html><title>Register Greenwash</title><body style='font:16px system-ui;margin:40px'>"
                    f"<h1>Register {html.escape(args.name)}</h1><p>Webhook: {html.escape(host)}/api/github/webhook</p>"
                    f"<form method=post action='https://github.com/settings/apps/new?state={state}'>"
                    f"<input type=hidden name=manifest value=\"{data}\">"
                    "<button style='font:inherit;padding:12px 20px'>Continue to GitHub</button></form>"
                )
                return
            if url.path != "/callback":
                self._send("Not found", 404)
                return
            query = parse_qs(url.query)
            if "code" not in query or (not args.resume and query.get("state", [""])[0] != state):
                self._send("State mismatch: this callback was not started by this script.", 400)
                return
            code = query["code"][0]
            try:
                request = urllib.request.Request(
                    f"https://api.github.com/app-manifests/{code}/conversions", method="POST",
                    headers={"Accept": "application/vnd.github+json"},
                )
                with urllib.request.urlopen(request, timeout=30, context=TLS) as response:
                    app = json.load(response)
                railway_set(args.service, "GITHUB_APP_ID", str(app["id"]), deploy=False)
                railway_set(args.service, "GITHUB_APP_SLUG", app["slug"], deploy=False)
                railway_set(args.service, "GITHUB_WEBHOOK_SECRET", app["webhook_secret"], deploy=False)
                railway_set(args.service, "GITHUB_PRIVATE_KEY", app["pem"], deploy=True)  # triggers redeploy
                result.update(id=app["id"], slug=app["slug"], html_url=app["html_url"])
                install = f"https://github.com/apps/{app['slug']}/installations/new"
                self._send(f"<p>Created <b>{html.escape(app['slug'])}</b>. Credentials stored on Railway.</p>"
                           f"<p><a href='{html.escape(install)}'>Install it on greenwash-live-sandbox</a></p>")
            except Exception as exc:  # show the failure type only; never echo secrets
                result["error"] = type(exc).__name__
                self._send(f"Registration failed ({html.escape(type(exc).__name__)}). See the terminal.", 500)
            finally:
                done.set()

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if args.resume:
        print("Waiting for one callback: reload the earlier http://127.0.0.1:8799/callback?... tab.", flush=True)
    else:
        print(f"Open http://127.0.0.1:{PORT}/ and click 'Continue to GitHub', then 'Create GitHub App'.", flush=True)
    done.wait()
    server.shutdown()
    if "error" in result:
        print(f"Registration failed: {result['error']}", file=sys.stderr)
        return 1
    print(json.dumps({**result, "install_url": f"https://github.com/apps/{result['slug']}/installations/new"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
