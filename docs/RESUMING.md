# Picking this up again

Read this first after a `/compact`, a `/clear`, or a power cut. It says
where the truth lives, so nothing has to be remembered.

## 1. Where you are

    python scripts/progress_server.py      ->  http://localhost:5099

That page is generated from git, so it cannot be out of date. The phase
state itself is **code**, in `scripts/progress_server.py`:

- `PHASES` — every phase, its state, and what is still open in it
- `COMMIT_PHASE` — which commit belongs to which phase
- `CURRENT_PHASE` — anything not listed above is counted here

The plan those phases come from is
`C:\Users\Alig\.claude\plans\hello-bubbly-lecun.md`. Its phase table gives
each phase's **verify** step; do that step rather than deciding for
yourself that a phase is finished.

## 2. Restart the servers

None survive a power cut. Start them with `preview_start`, by name, from
`.claude/launch.json`:

| name | port | what |
|---|---|---|
| `spendincheck-spa` | 5173 | **the site** — Vite, proxying `/api` to Flask |
| `spendincheck-flask` | 5000 | the API, and nothing else |
| `spendincheck-built` | 4173 | the built bundle in `web/dist`, same proxy |
| `spendincheck-progress` | 5099 | the progress page |

Open `http://localhost:5173`. Since Phase 8 that is the whole site: there is
no second half to compare it against and no mirror to join them.

`spendincheck-built` is the rehearsal. It serves what Vercel will serve —
static files, and `index.html` for any path that is not one — so a deep
link, a hard refresh and the production bundle can all be checked before a
deploy. Run `npm --prefix web run build` first; it does not build for you.

## 3. After a power cut, check for corruption first

NTFS commits a file's size before its contents, so an interrupted write
leaves a file of NUL bytes that still looks the right length.

```bash
for f in $(git status --porcelain | awk '{print $2}'); do
  python -c "print('$f', open(r'$f','rb').read().count(b'\x00'))"
done
```

Non-zero means corrupt: `git checkout -- <file>` if it was committed,
otherwise rewrite it. Also clear a stale `.git/index.lock` if git complains
(check no git process is actually running first).

## 4. Run the tests before believing anything

```bash
python -m pytest -q
```

They run against the real Supabase database, because what is under test is
the SQL. Two consequences:

- They are slow (~5 minutes) and need the network.
- **A test that reaches beyond its own fixtures reaches real data.** One
  called the demo sweep with zero hours and deleted every demonstration
  account in the database, including a live one. Keep fixtures to
  themselves.

Client tests: `cd web && node --test --experimental-strip-types src/lib/money.test.ts`

## 5. What decides latency here

Two numbers, both measured against the Mumbai pooler: **182ms** to open a
connection, **28ms** for a round trip whatever it carries. Queries are
single figures. So an endpoint costs its statement count times 28ms, and
optimising means counting statements, not tuning SQL.

`server/db.py` pools connections and keeps them in autocommit, because a
plain SELECT otherwise leaves a transaction open that costs a full round
trip to roll back. Anything needing several statements to succeed or fail
together uses `db.transaction()`. Every read endpoint is one round trip;
opening the demo is three.

## 6. Measure, do not assert

`python scripts/benchmark.py` writes `docs/benchmarks.json`, which the
progress page renders. Run it after touching any request path, and quote
figures from it rather than reasoning about them.

## 7. The database is closed to everything but this app

Supabase serves every table in the `public` schema over PostgREST, and by
default grants `anon` and `authenticated` full read and write on all of
them. The publishable key is not a secret -- it is meant to ship in client
code -- so until migration 010 the whole database, `users.password_hash`
included, was readable and deletable by anyone holding it. That was
verified against the live project, not inferred.

Migration 010 enables RLS on every table with no policies and revokes the
grants, including default privileges so new tables do not reopen it. The
app is unaffected because it connects as `postgres`, which has
`rolbypassrls`.

**Anything that creates a table must not hand privileges back to `anon` or
`authenticated`.** Run `get_advisors` after schema changes; it is what
found this.

## 8. Decisions that are not visible in the code

- **Both themes ship, toggleable.** Every UI primitive reads semantic
  tokens, never a literal colour, so a screen is correct in brass and paper
  at once.
- **The demo is open to anyone, any time, with no sign-up.** One throwaway
  account per visitor.
- **The client is built but not deployed.** Phase 8 is finished locally and
  nothing has been pushed: spendincheck.com is still serving the Jinja
  pages from an older commit. Pushing to `main` deploys, so it needs
  asking first.
- **Money never converts between currencies.** There are no exchange rates;
  changing currency relabels and re-rounds, and the settings screen says so
  before the control.

## 9. What Phase 8 left, and where Phase 9 starts

Phase 8 is done in the repository and **not in production**. The Jinja app
is deleted, the client owns every URL, and the tests pass — but nothing was
pushed, so spendincheck.com is still serving `templates/` from an older
commit. That is the one open item, and it is not a code decision:

> Pushing to `main` deploys. This is the first phase a visitor sees, so it
> needs asking first.

Two things to know before that push.

**`vercel.json` changed shape and has never run.** It now declares two
builds instead of one: `@vercel/python` for `app.py` as before, and
`@vercel/static-build` for the client. Only `/api` reaches Python;
everything else is served from the edge, with `index.html` as the fallback
for any path that is not a file.

The static build's entrypoint is the **root** `package.json`, whose only
job is `npm --prefix web ci && npm --prefix web run build`. That is
deliberate: a legacy build mounts its output under the directory of its
entrypoint, so pointing it at `web/package.json` would have addressed
every file as `/web/...` — a prefix that cannot be checked without
deploying. From the root there is no prefix to get wrong, and `handle:
filesystem` then serves whatever the build produced without anything
having to name it. `npm run build` at the repo root is exactly what
Vercel runs, and it works.

**An unknown URL answers 200, not 404.** The catch-all serves
`index.html`, and React renders "Not found" inside it. That is how a
single-page app works and the alternative is worse — the edge cannot tell
`/reports` from `/nonsense` — but it does mean a crawler sees 200 for
anything. The old URLs are all accounted for: `/dashboard`,
`/transactions`, `/categories`, `/budgets`, `/investments`, `/reports`
and `/sign-in` and `/register` are real routes; `/app/*` redirects to the
same path without the prefix; `/demo` and `/sign-out` were POST-only
actions and are now `/api/v1/auth/demo` and `/api/v1/auth/sign-out`.

Phase 9 is **StockSaathi prices**. From the plan: symbol autocomplete
first, because it populates the ticker every later price feature depends
on. Nothing has been started, and it is the first phase that reaches
outside this repository — `G:\StockSaathi` is the other working
directory.

Everything else in this file still applies: one round trip per screen, the
REST API deliberately closed, and the tests running against the real
database.
