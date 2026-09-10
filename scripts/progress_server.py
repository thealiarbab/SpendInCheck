"""A live progress page for the SpendInCheck rewrite.

Run it and leave it open:

    python scripts/progress_server.py

Then watch http://localhost:5099. It reads the git history on every request,
so it cannot drift from what has actually been committed -- there is no
progress file anyone has to remember to update.

Standard library only, deliberately: this is a window onto the work, and it
should never be a reason for the project to gain a dependency.
"""

import json
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 5099
REPO = Path(__file__).resolve().parent.parent

# The commit the rewrite starts from. Everything after this belongs to a phase.
BASELINE = "b2c9a7c"

# Which phase each commit belongs to. Phases interleave -- the design system
# was largely built before the backend restructure -- so this is an explicit
# mapping rather than a range. Any commit not listed is treated as part of
# CURRENT_PHASE, which is what keeps this accurate as new work lands without
# anyone editing the file.
CURRENT_PHASE = 2

COMMIT_PHASE = {
    0: ["5e3ab5e", "6308244", "931dabe", "490f434", "c030a97", "e166bb4", "efb70ab"],
    1: ["d293e7d", "47c1f9d", "e2b87cf", "955e5a6", "0ea83e3", "0197007",
        "125130e", "81d0152", "d3363a5", "ae136db", "80e1337", "9db89f0"],
    2: ["ddaf76c", "ac9de82", "e001a5c", "944c83d", "93c81f1", "fc9dd98",
        "8b7896b", "aaca719", "89c58b0", "9324f7e", "2a00990", "ad743d9",
        "2fddf8d", "44e2272", "f2b37c8", "269ea6a", "a56f0fd", "f7c0cf4",
        "5f13215"],
    3: ["e3edb16", "5167880", "0078b12", "d5faeb9", "d722367", "58fbd03",
        "8f2bae6", "514eb37", "8e97c8f", "c32e02b", "357a022", "d027ab7",
        "4685dcd", "21a21de"],
}

PHASES = [
    {"n": 0, "name": "Hygiene", "state": "done",
     "blurb": "Clear out the CBSE submission, repoint config at Postgres, scaffold the "
              "React workspace.",
     "open": []},
    {"n": 1, "name": "Backend restructure", "state": "done",
     "blurb": "create_app() factory, operations split into seven domain modules, "
              "money/validators/errors, migration 001. Zero behaviour change by design.",
     "open": []},
    {"n": 2, "name": "JSON API alongside Jinja", "state": "now",
     "blurb": "A /api/v1 blueprint reusing the existing operations, mounted beside the "
              "pages so both read the same session and screens can move one at a time.",
     "open": ["Endpoint tests for the five resource groups",
              "Scheduled cleanup for abandoned demo accounts"]},
    {"n": 3, "name": "Design system and shell", "state": "started",
     "blurb": "Tokens, both themes, the UI primitives and the side-by-side ThemeLab. "
              "Built early, so the code exists and the decision does not.",
     "open": ["YOUR CALL: brass, paper, or ship both — before Phase 4 builds on it"]},
    {"n": 4, "name": "Port the six existing screens", "state": "next",
     "blurb": "Parity with the Jinja pages, plus rupee formatting and field-level "
              "errors. Adds the missing CRUD.",
     "open": []},
    {"n": 5, "name": "Search, filter, pagination, export", "state": "next",
     "blurb": "search_transactions replaces get_all_transactions. Column names come "
              "from a whitelist; only values go through %s.",
     "open": []},
    {"n": 6, "name": "Reporting depth and charts", "state": "next",
     "blurb": "dashboard_summary in one round trip, plus trend, cashflow and net worth.",
     "open": []},
    {"n": 7, "name": "Accounts through CSV import", "state": "next",
     "blurb": "Migrations 002-006 in order. Import lands last, because it is the "
              "feature that can create hundreds of wrong rows at once.",
     "open": []},
    {"n": 8, "name": "Kill Jinja", "state": "next",
     "blurb": "Flip the rewrite so React owns /*. One revertable commit.",
     "open": []},
    {"n": 9, "name": "StockSaathi prices", "state": "next",
     "blurb": "Symbol autocomplete first, because it populates the ticker every later "
              "price feature depends on.",
     "open": []},
    {"n": 10, "name": "Opt-in account linking", "state": "next",
     "blurb": "Last, because it is the only feature that can damage a different "
              "product's data.",
     "open": []},
]


def git(*args):
    """Run a git command in the repo and return its output, or '' on failure."""
    try:
        return subprocess.run(("git",) + args, cwd=REPO, capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def collect():
    """Build the whole progress payload from the repository as it stands now."""
    phase_of = {sha: n for n, shas in COMMIT_PHASE.items() for sha in shas}

    log = git("log", "--format=%h\x1f%s\x1f%ar\x1f%b\x1e", "--reverse",
              f"{BASELINE}..HEAD")
    commits = []
    for entry in log.split("\x1e"):
        entry = entry.strip("\n")
        if not entry:
            continue
        parts = entry.split("\x1f")
        if len(parts) < 3:
            continue
        sha, subject, when = parts[0], parts[1], parts[2]
        body = parts[3].strip() if len(parts) > 3 else ""
        commits.append({
            "sha": sha,
            "subject": subject,
            "when": when,
            # The first paragraph of the body is the reason for the change,
            # which is the part worth reading at a glance.
            "why": body.split("\n\n")[0].replace("\n", " ") if body else "",
            "phase": phase_of.get(sha, CURRENT_PHASE),
            "kind": subject.split(":")[0].split("(")[0] if ":" in subject else "other",
        })

    by_phase = {}
    for commit in commits:
        by_phase.setdefault(commit["phase"], []).append(commit)

    dirty = [line[3:] for line in git("status", "--porcelain").splitlines() if line]
    unpushed = git("rev-list", "--count", "origin/main..HEAD") or "?"

    # Counting test functions by reading the files is instant; running pytest
    # here would make every page refresh wait on the database.
    tests = 0
    for path in (REPO / "tests").glob("test_*.py"):
        tests += len(re.findall(r"^def test_", path.read_text(encoding="utf-8"), re.M))

    phases = []
    for phase in PHASES:
        rows = by_phase.get(phase["n"], [])
        phases.append(dict(phase, commits=rows, count=len(rows)))

    return {
        "phases": phases,
        "total_commits": len(commits),
        "tests": tests,
        "unpushed": unpushed,
        "dirty": dirty,
        "latest": commits[-1] if commits else None,
        "done": sum(1 for p in PHASES if p["state"] == "done"),
    }


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpendInCheck Progress</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
:root{
  --ink:#14110e; --ink-2:#1b1713; --panel:#1e1a16; --rule:#322a22; --rule-soft:#241f19;
  --paper:#ede6dc; --paper-dim:#b3a695; --paper-mute:#877a6a;
  --brass:#e0a836; --brass-dim:#a67c22; --credit:#7da96a; --debit:#c4553d;
  --level:#c9922f; --invest:#00B386;
  --serif:"Instrument Serif",Georgia,serif;
  --sans:"Inter",-apple-system,"Segoe UI",system-ui,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);font-family:var(--sans);
     font-size:15px;line-height:1.62;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding:0 30px 90px}
.masthead{border-bottom:1px solid var(--rule);padding:48px 0 26px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:2.4px;text-transform:uppercase;
         color:var(--brass-dim);margin:0 0 14px}
h1{font-family:var(--serif);font-weight:400;font-size:50px;line-height:1.04;margin:0;
   letter-spacing:-.4px}
.live{display:inline-flex;align-items:center;gap:8px;font-family:var(--mono);font-size:11px;
      letter-spacing:1.4px;text-transform:uppercase;color:var(--paper-mute);margin-left:14px;
      vertical-align:middle}
.dot{width:7px;height:7px;background:var(--credit);border-radius:50%;
     animation:pulse 2s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}

.stat-row{display:flex;gap:0;flex-wrap:wrap;border-top:1px solid var(--rule);margin-top:30px}
.stat{padding:18px 30px 16px 0;min-width:140px}
.stat .n{display:block;font-family:var(--serif);font-size:38px;line-height:1;color:var(--brass);
         font-variant-numeric:tabular-nums}
.stat .l{font-family:var(--mono);font-size:10px;letter-spacing:1.3px;text-transform:uppercase;
         color:var(--paper-mute);display:block;margin-top:7px}

.now-strip{border:1px solid var(--rule);border-left:3px solid var(--level);background:var(--ink-2);
           padding:16px 20px;margin:28px 0 0}
.now-strip .k{font-family:var(--mono);font-size:10px;letter-spacing:1.3px;text-transform:uppercase;
              color:var(--brass-dim);display:block;margin-bottom:6px}
.now-strip .v{color:var(--paper);font-size:14.5px}
.now-strip .why{color:var(--paper-mute);font-size:13px;margin-top:5px;max-width:74ch}
.dirty{margin-top:10px;font-family:var(--mono);font-size:12px;color:var(--level)}

.ticks{display:flex;gap:4px;margin:26px 0 0}
.tick{flex:1;height:6px;background:var(--rule)}
.tick.done{background:var(--credit)} .tick.now{background:var(--level)}
.tick.started{background:var(--brass-dim)}

.phase{display:grid;grid-template-columns:64px 1fr;gap:22px;padding:26px 0;
       border-top:1px solid var(--rule)}
.pnum{font-family:var(--mono);font-size:26px;font-weight:700;color:var(--rule);line-height:1;
      padding-top:4px;font-variant-numeric:tabular-nums}
.phase.done .pnum{color:var(--credit)} .phase.now .pnum{color:var(--level)}
.phase.started .pnum{color:var(--brass-dim)}
.phead{display:flex;align-items:baseline;gap:13px;flex-wrap:wrap;margin-bottom:8px}
.pname{font-family:var(--serif);font-size:23px;font-weight:400;margin:0}
.tag{display:inline-block;padding:2px 0 3px;font-size:10px;font-weight:700;text-transform:uppercase;
     letter-spacing:1.1px;border-bottom:2px solid}
.tag.done{color:var(--credit);border-color:var(--credit)}
.tag.now{color:var(--level);border-color:var(--level)}
.tag.started{color:var(--brass);border-color:var(--brass)}
.tag.next{color:var(--paper-mute);border-color:var(--paper-mute)}
.count{font-family:var(--mono);font-size:11.5px;color:var(--paper-mute);margin-left:auto}
.blurb{color:var(--paper-dim);margin:0 0 12px;max-width:70ch;font-size:14px}
.open{margin:0 0 12px;padding:0;list-style:none}
.open li{font-size:13px;color:var(--level);padding-left:18px;position:relative}
.open li::before{content:"·";position:absolute;left:4px;font-size:19px;top:-4px}

.commits{margin:0;padding:0;list-style:none;border-left:1px solid var(--rule)}
.commits li{padding:5px 0 5px 15px;position:relative}
.commits li::before{content:"";position:absolute;left:-3.5px;top:13px;width:6px;height:6px;
                    background:var(--rule);border:1px solid var(--ink)}
.commits li.fresh::before{background:var(--brass)}
.c-sha{font-family:var(--mono);font-size:11.5px;color:var(--brass-dim);margin-right:9px}
.c-sub{font-size:13.5px;color:var(--paper-dim)}
.c-when{font-family:var(--mono);font-size:11px;color:var(--paper-mute);margin-left:8px}
.c-why{display:block;color:var(--paper-mute);font-size:12.5px;margin-top:2px;max-width:76ch}
.kind{display:inline-block;font-family:var(--mono);font-size:9.5px;letter-spacing:.8px;
      text-transform:uppercase;padding:1px 5px;margin-right:8px;border:1px solid var(--rule-soft);
      color:var(--paper-mute)}
.kind.feat{color:var(--credit);border-color:#33452c}
.kind.fix{color:var(--debit);border-color:#4a2b23}
.kind.test{color:var(--brass-dim);border-color:#3d3018}
.empty{color:var(--paper-mute);font-size:13px;font-style:italic}
footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--rule);
       color:var(--paper-mute);font-size:12.5px;display:flex;justify-content:space-between;
       gap:14px;flex-wrap:wrap}
@media(max-width:700px){h1{font-size:34px}.wrap{padding:0 18px 60px}
  .phase{grid-template-columns:40px 1fr;gap:14px}}
@media(prefers-reduced-motion:reduce){.dot{animation:none}}
</style></head>
<body>
<div class="wrap">
  <header class="masthead">
    <p class="eyebrow">Live from the git history</p>
    <h1>SpendInCheck Progress<span class="live"><span class="dot"></span><span id="beat">connecting</span></span></h1>
    <div class="stat-row" id="stats"></div>
    <div class="now-strip" id="now"></div>
    <div class="ticks" id="ticks"></div>
  </header>
  <main id="phases"></main>
  <footer>
    <span>Reads <code>git log</code> on every refresh &mdash; it cannot drift from what was committed.</span>
    <span id="stamp"></span>
  </footer>
</div>
<script>
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function render(d) {
  document.getElementById("stats").innerHTML = [
    [d.done + " / 11", "phases complete"],
    [d.total_commits, "commits"],
    [d.tests, "tests"],
    [d.unpushed, "unpushed"],
  ].map(([n, l]) => `<div class="stat"><span class="n">${esc(n)}</span><span class="l">${esc(l)}</span></div>`).join("");

  const latest = d.latest;
  document.getElementById("now").innerHTML = latest ? `
    <span class="k">Most recent commit &mdash; ${esc(latest.when)}</span>
    <div class="v"><span class="c-sha">${esc(latest.sha)}</span>${esc(latest.subject)}</div>
    ${latest.why ? `<div class="why">${esc(latest.why)}</div>` : ""}
    ${d.dirty.length ? `<div class="dirty">${d.dirty.length} file${d.dirty.length > 1 ? "s" : ""} changed but not committed &mdash; ${d.dirty.slice(0, 4).map(esc).join(", ")}${d.dirty.length > 4 ? " …" : ""}</div>` : ""}
  ` : `<span class="k">Waiting for the first commit</span>`;

  document.getElementById("ticks").innerHTML =
    d.phases.map(p => `<div class="tick ${esc(p.state)}" title="Phase ${p.n} — ${esc(p.name)}"></div>`).join("");

  document.getElementById("phases").innerHTML = d.phases.map(p => `
    <section class="phase ${esc(p.state)}">
      <div class="pnum">${String(p.n).padStart(2, "0")}</div>
      <div>
        <div class="phead">
          <h2 class="pname">${esc(p.name)}</h2>
          <span class="tag ${esc(p.state)}">${esc({done:"Done",now:"In progress",started:"Started",next:"Pending"}[p.state])}</span>
          <span class="count">${p.count} commit${p.count === 1 ? "" : "s"}</span>
        </div>
        <p class="blurb">${esc(p.blurb)}</p>
        ${p.open.length ? `<ul class="open">${p.open.map(o => `<li>${esc(o)}</li>`).join("")}</ul>` : ""}
        ${p.commits.length ? `<ul class="commits">${p.commits.slice().reverse().map((c, i) => `
          <li class="${i === 0 && p.state === "now" ? "fresh" : ""}">
            <span class="kind ${esc(c.kind)}">${esc(c.kind)}</span><span class="c-sha">${esc(c.sha)}</span><span class="c-sub">${esc(c.subject.replace(/^[a-z]+(\([^)]*\))?:\s*/, ""))}</span><span class="c-when">${esc(c.when)}</span>
            ${c.why ? `<span class="c-why">${esc(c.why)}</span>` : ""}
          </li>`).join("")}</ul>` : `<p class="empty">Not started.</p>`}
      </div>
    </section>`).join("");

  document.getElementById("stamp").textContent =
    "updated " + new Date().toLocaleTimeString();
}

async function tick() {
  const beat = document.getElementById("beat");
  try {
    const r = await fetch("/progress.json", { cache: "no-store" });
    render(await r.json());
    beat.textContent = "live";
  } catch (e) {
    beat.textContent = "server stopped";
  }
}
tick();
setInterval(tick, 4000);
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/progress.json"):
            payload = json.dumps(collect()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
        else:
            payload = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        """Stay quiet. The point of this server is the page, not its access log."""


if __name__ == "__main__":
    print(f"SpendInCheck progress -> http://localhost:{PORT}   (ctrl-c to stop)")
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
