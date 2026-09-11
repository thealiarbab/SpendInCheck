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

## 9. Where things stand

**Phase 8 is done and not deployed.** The Jinja app is deleted, the client
owns every URL, the tests pass -- and nothing has been pushed, so
spendincheck.com is still serving `templates/` from an older commit.

> Pushing to `main` deploys. This is the first phase a visitor sees, so it
> needs asking first.

**Phase 9 is most of the way there.** What works, verified against the
live database and the real API:

- Migration 011 puts `ticker`, `exchange`, `isin`, `auto_price`,
  `price_source` and `price_updated_at` on `investments`. `auto_price`
  defaults false, so no existing figure moved.
- `server/services/stocksaathi.py` is the only place that knows their API.
- Pointing a holding at a symbol prices it in the same request; a symbol
  that returns no price is refused with the field named.
- The holdings screen shows a live price and the day's move beside the
  stored one, polling only while the market is open.
- Migration 012 adds `quote_history`, and net worth is valued month by
  month from real closes with `current_price` as the fallback.
- The nightly snapshot backfills a year for a symbol it has never seen and
  tops up five days for one it has.

### Two things Phase 9 cannot finish from this repository

**Symbol autocomplete is blocked, and the plan wanted it first.** It was
meant to complete against StockSaathi's instrument master. There is no
public endpoint for it: their API serves `live-quote`, `quote`, `history`,
`mf-history`, `screener` and `universe-quotes`, and none of them search.
The master lives in their Supabase as `dhan_instruments`, and their anon
key returns `[]` for it -- RLS is on with no policy, which is correct of
them and closes the door to us.

So it needs **a new endpoint on StockSaathi**, something like
`GET /api/search?q=reli` returning symbol, name, exchange and ISIN. That
is a change to the other repository and a deploy of a second production
site, which is not mine to make. Until then a symbol is typed rather than
chosen -- and it is still checked: a symbol that does not quote cannot be
switched on.

**Portfolio vs NIFTY is blocked for the same kind of reason.** The index
does not quote: `NIFTY` and `^NSEI` both come back null, and `NIFTY50`
returns about 8,095, which is some other instrument and not the index --
using it would draw a confident wrong line. `NIFTYBEES`, the ETF that
tracks the index, does quote and is the honest substitute if labelled as
one.

### What is left that is not blocked

- The 52-week range. It already comes back from the instrument lookup and
  is carried to the client; it is not drawn anywhere, because showing it
  per row would mean a lookup per holding at up to three seconds each.
  Storing it is the obvious answer and the wrong one -- it changes daily,
  so a stored copy is wrong by definition. If it is wanted per row, it
  belongs in the nightly snapshot beside the closes.
- The savings-goal-reached card, which is the third and last placement.
  The investments empty state and the surplus prompt are done. Three is
  the cap -- more reads as advertising.
- Phase 10, opt-in account linking, which is untouched and is the only
  feature that can damage a different product's data.

Sparklines are done, and not the way the plan described. It said to draw
them from `/api/history`, which would be one request to StockSaathi per
holding every time the screen opened. They read `quote_history` instead --
the snapshot has already written those closes down -- so six holdings are
one statement against this app's own database and the chart does not
depend on anybody else's server being up.

### Deployment notes worth having before the push

`vercel.json` declares two builds: `@vercel/python` for `app.py`, and
`@vercel/static-build` on the **root** `package.json`, whose only job is
`npm --prefix web ci && npm --prefix web run build`. The entrypoint is at
the root deliberately -- a legacy build mounts its output under its
entrypoint's directory, so pointing it at `web/package.json` would address
every file as `/web/...`, a prefix that cannot be checked without
deploying. From the root there is no prefix to get wrong. `npm run build`
at the repo root is exactly what Vercel runs, and it works.

**This account is on Vercel's Hobby plan, which allows two cron jobs.**
That is a choice, not a list. The two scheduled are the snapshot (11:30
UTC, 90 minutes after the NSE close, and the only job whose data cannot be
recovered later -- a close nobody wrote down is gone) and the demo sweep.
`/api/v1/cron/recurring` is deliberately **not** scheduled: rules can be
materialised from the app through `POST /recurring/run`, which is how it
has always worked, and a third entry would exceed the plan.

**An unknown URL answers 200, not 404.** The catch-all serves
`index.html` and React renders "Not found" inside it -- how any SPA works,
since the edge cannot tell `/reports` from `/nonsense`. The old URLs are
all accounted for: `/dashboard`, `/transactions`, `/categories`,
`/budgets`, `/investments`, `/reports`, `/sign-in` and `/register` are
real routes; `/app/*` redirects; `/demo` and `/sign-out` were POST-only
actions and are now `/api/v1/auth/demo` and `/api/v1/auth/sign-out`.

Everything else in this file still applies: one round trip per screen, the
REST API deliberately closed, and the tests running against the real
database.
