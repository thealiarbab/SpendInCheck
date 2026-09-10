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
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

PORT = 8000
# Named rather than pinned to an address, because the two servers do not
# agree on a family: Flask listens on 127.0.0.1 and Vite on ::1, so either
# literal misses one of them. What the name must not do is cost anything --
# see address_for() below.
FLASK = ("localhost", 5000)
VITE = ("localhost", 5173)

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


# Which concrete address each named target actually answers on, remembered
# after the first successful connection.
_resolved = {}

# How long to wait when trying a candidate address. Refusal is not instant on
# Windows -- a closed port takes about 2.3 seconds to say so -- and without a
# short bound here the wrong family is paid for at full price.
PROBE_TIMEOUT = 0.4


def _answers(address):
    """True when something accepts a connection at this exact address."""
    try:
        socket.create_connection(address, timeout=PROBE_TIMEOUT).close()
        return True
    except OSError:
        return False


def address_for(target, refresh=False):
    """The address a named target actually answers on, or None.

    getaddrinfo("localhost") returns the IPv6 form first on this machine, and
    a refused connection takes about 2.3 seconds to fail. Flask listens only
    on 127.0.0.1, so simply handing the name to http.client paid that 2.3
    seconds on every single request through the mirror -- which is what made
    opening the demo take nine seconds rather than the six hundred
    milliseconds the API actually spends.

    So the families are tried once, with a short timeout, and the one that
    answers is remembered. A server restarting on the other family is handled
    by refresh=True, which the proxy passes after a failed attempt.
    """
    if not refresh and target in _resolved:
        return _resolved[target]

    _resolved.pop(target, None)
    host, port = target
    try:
        candidates = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return None

    for _, _, _, _, address in candidates:
        # getaddrinfo hands back four-tuples for IPv6; create_connection and
        # http.client both want just the host and the port.
        address = (address[0], address[1])
        if _answers(address):
            _resolved[target] = address
            return address
    return None


def reachable(target):
    """True when something is listening, so the fallback can be chosen."""
    return address_for(target) is not None


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

        # The root goes to the client being built, not the pages being
        # replaced. Opening the mirror should show the work in progress --
        # landing on the old site instead made the mirror look frozen.
        # Every Jinja page is still there at its own address, which is what
        # makes the two comparable: /transactions beside /app/transactions.
        if path in ("", "/"):
            return self.redirect("/app/")

        target = self.target_for(path)

        if target is VITE and not reachable(VITE):
            return self.serve_built(path)
        return self.proxy(target, path)

    def redirect(self, where):
        """Send the reader somewhere else on this same origin."""
        self.send_response(302)
        self.send_header("Location", where)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # --- proxying -----------------------------------------------------------

    def forward(self, target, path, body, headers, refresh=False):
        """Send one request upstream and read the whole reply back."""
        address = address_for(target, refresh=refresh)
        if address is None:
            raise OSError(f"nothing listening for {target[0]}:{target[1]}")

        connection = http.client.HTTPConnection(*address, timeout=90)
        try:
            connection.request(self.command, path, body=body, headers=headers)
            upstream = connection.getresponse()
            return upstream.read(), upstream
        finally:
            connection.close()

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

        # Connect to the address this target is known to answer on, rather
        # than to its name: the name costs a refused IPv6 attempt first.
        try:
            payload, upstream = self.forward(target, path, body, headers)
        except OSError:
            # The server may have restarted on the other family. Resolve
            # again and give it one more chance before reporting it down.
            try:
                payload, upstream = self.forward(target, path, body, headers,
                                                 refresh=True)
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
    print(f"  /        -> the React client being built")
    print(f"  /app/*   -> Vite on {VITE[1]}    "
          f"{'up' if vite_up else 'down, will serve web/dist'}")
    print(f"  anything else -> Flask on {FLASK[1]}   "
          f"{'up' if flask_up else 'DOWN'}")
    print(f"  compare: /transactions is the old page, /app/transactions the new")
    print("  ctrl-c to stop\n")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
