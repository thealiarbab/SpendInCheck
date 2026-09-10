"""The whole site on one port, the way production will look after Phase 8.

    python scripts/mirror.py        ->  http://localhost:8000

Until Phase 8 the site is split across two servers: Flask serves the pages at
"/" and Vite serves the React client at "/app". Reading it that way means
juggling two ports, and worse, two origins -- so a session started on one is
invisible to the other, and nothing can be compared side by side.

This puts both behind a single origin. "/app" goes to the client, everything
else to Flask, exactly as vercel.json will be arranged when the client
finally takes over. One cookie jar, one URL to open.

It proxies rather than serving files, so whatever the two servers are doing
right now is what appears -- including Vite's hot reload. If Vite is not
running it falls back to the built bundle in web/dist, so the mirror is
still useful with only Flask up.

Standard library only: a development convenience must never become a reason
for the project to gain a dependency.
"""

import http.client
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = 8000
FLASK = ("127.0.0.1", 5000)
VITE = ("127.0.0.1", 5173)

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "web" / "dist"

# Headers that describe one hop of a connection rather than the message, so
# they must not be copied through a proxy.
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript",
    ".css": "text/css", ".svg": "image/svg+xml", ".json": "application/json",
    ".png": "image/png", ".ico": "image/x-icon", ".map": "application/json",
    ".woff2": "font/woff2",
}


def reachable(target):
    """True when something is listening, so the fallback can be chosen."""
    try:
        connection = http.client.HTTPConnection(*target, timeout=0.4)
        connection.connect()
        connection.close()
        return True
    except OSError:
        return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # --- routing ------------------------------------------------------------

    def target_for(self, path):
        """Which server owns this path.

        The split matches what vercel.json will say after Phase 8, so the
        mirror is a rehearsal of the real arrangement rather than a
        development-only shape that has to be reasoned about separately.
        """
        if path == "/app" or path.startswith("/app/"):
            return VITE
        return FLASK

    def handle_request(self):
        path = self.path
        target = self.target_for(path)

        if target is VITE and not reachable(VITE):
            return self.serve_built(path)
        return self.proxy(target, path)

    # --- proxying -----------------------------------------------------------

    def proxy(self, target, path):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        headers = {}
        for name, value in self.headers.items():
            if name.lower() in HOP_BY_HOP or name.lower() == "host":
                continue
            # Asking upstream not to compress keeps this from having to
            # decode anything just to pass it along.
            if name.lower() == "accept-encoding":
                continue
            headers[name] = value
        headers["Host"] = f"{target[0]}:{target[1]}"
        headers["Accept-Encoding"] = "identity"

        try:
            connection = http.client.HTTPConnection(*target, timeout=90)
            connection.request(self.command, path, body=body, headers=headers)
            upstream = connection.getresponse()
            payload = upstream.read()
        except OSError as error:
            return self.explain_unreachable(target, error)

        self.send_response(upstream.status)
        for name, value in upstream.getheaders():
            if name.lower() in HOP_BY_HOP or name.lower() == "content-length":
                continue
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        connection.close()

    # --- fallback when Vite is not running ----------------------------------

    def serve_built(self, path):
        """Serve web/dist, so the client is still visible without Vite.

        Any path that is not a file is answered with index.html, because the
        client owns its own routing and a deep link must reach it rather than
        404 here.
        """
        if not DIST.exists():
            return self.explain_no_build()

        relative = path[len("/app"):].lstrip("/").split("?")[0]
        candidate = (DIST / relative) if relative else (DIST / "index.html")
        if not candidate.is_file():
            candidate = DIST / "index.html"

        payload = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
                         CONTENT_TYPES.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        # The bundle is rebuilt by hand in this mode, so it must not be cached.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    # --- failures, explained rather than crashed ----------------------------

    def reply_html(self, status, title, message):
        page = f"""<!doctype html><meta charset="utf-8">
<title>{title}</title>
<style>body{{background:#14110e;color:#ede6dc;font:15px/1.6 system-ui;
margin:0;display:grid;place-items:center;height:100vh}}
div{{max-width:52ch;padding:0 24px}}
h1{{font:400 30px/1.1 Georgia,serif;color:#e0a836;margin:0 0 12px}}
code{{font-family:ui-monospace,Consolas,monospace;color:#e0a836;
background:#1b1713;padding:2px 6px}}</style>
<div><h1>{title}</h1><p>{message}</p></div>"""
        payload = page.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def explain_unreachable(self, target, error):
        which = "Flask" if target == FLASK else "Vite"
        command = ("python app.py" if target == FLASK
                   else "npm run dev --prefix web")
        self.reply_html(502, f"{which} is not running",
                        f"Nothing answered on port {target[1]} ({error}). "
                        f"Start it with <code>{command}</code> and reload.")

    def explain_no_build(self):
        self.reply_html(502, "No client to show",
                        "Vite is not running and <code>web/dist</code> does not "
                        "exist. Start the dev server, or build once with "
                        "<code>npm run build --prefix web</code>.")

    # --- verbs --------------------------------------------------------------

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = handle_request

    def log_message(self, fmt, *args):
        """One quiet line per request, so the split is visible while working."""
        sys.stdout.write(f"  {self.command:6} {self.path}\n")


if __name__ == "__main__":
    flask_up = reachable(FLASK)
    vite_up = reachable(VITE)
    print(f"SpendInCheck mirror -> http://localhost:{PORT}")
    print(f"  /       -> Flask on {FLASK[1]}   {'up' if flask_up else 'DOWN'}")
    print(f"  /app    -> Vite on {VITE[1]}    "
          f"{'up' if vite_up else 'down, will serve web/dist'}")
    print("  ctrl-c to stop\n")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
