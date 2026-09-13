# Picking this up again

## Start a new session. Do not reopen an old one.

Paste this into a **fresh** session:

```
SpendInCheck. Read docs/RESUMING.md and check memory first.
Phase 9 is done. Phase 10's spec is rewritten and ready; it needs asking
before it is built.
```

That is the whole handoff, and it is deliberate. Every message in a resumed
session re-reads the entire transcript above it, and after a few hours idle
it re-reads it *uncached* -- so the first message back to a long
conversation can cost more than a day of actual work. A new session with
three lines costs three lines.

Nothing is lost by starting fresh, because nothing important lives in the
transcript. It lives in git, in this file, in `scripts/progress_server.py`,
and in memory. That is what they are for.


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

**Judge speed there, never on 5173.** Vite serves every source file as its
own request, so a cold dev page makes hundreds of them and an API call
queues behind the lot. Same click, same server, same database: opening the
demo measured 2,588ms cold on 5173, 803ms warm, and **267ms on the built
bundle** — the POST alone went 1,311ms to 170ms purely from warming up.
5173 is for building; 4173 is for believing.

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
trip to roll back.

**The pool holds five connections, which is what the reports screen
opens.** Below that they queued: `_checkout` waits for a connection rather
than failing, so the screen worked, but it was as slow as its slowest
serialised pair. psycopg2's own pool raises "connection pool exhausted" the
instant it is empty, which is how that screen once served a 400 to
whichever request lost the race.

Five is a division, not a preference. **The ceiling is sixteen, not the
sixty that `show max_connections` reports** -- that number describes the
Postgres instance, and every client here arrives through Supabase's pooler,
which hands out sixteen. Measured by opening connections until one broke.
It breaks *lazily*: the seventeenth connects fine and then dies on first
use with "SSL connection has been closed unexpectedly".

That sixteen is shared across every process, and serverless means many
containers each holding a whole pool, so the constraint is
`DB_MAX_CONNECTIONS x concurrent containers <= 16`. Raising it is not free
either: `minconn = maxconn`, so the pool opens every connection at
construction, at ~195ms each and linear -- 600ms for three, 955ms for five,
1,570ms for eight. That is paid once per container, not per request. Anything needing several statements to succeed or fail
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

**Phase 9 is done.** What works, verified against the live database and
the real API:

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

### The two things I called blocked, and what became of them

Both are cleared. Neither was as blocked as it looked.

**Portfolio against the market: done.** Only the NIFTY 50 *index* is
unreachable -- `NIFTY` and `^NSEI` return null, and `NIFTY50` returns some
unrelated instrument near 8,095 that would have drawn a confident wrong
line. `NIFTYBEES`, the Nippon India ETF tracking the same index, quotes
and has a full year of closes. The chart names it rather than calling it
"the NIFTY", the snapshot always fetches it whether or not anybody holds
it, and both sides are rebased to 100.

The part worth not breaking: the basket is valued at **today's quantities
in every month**. Charting the portfolio's real value against an index
compares two different things -- buying more raises the value without the
market moving, so a month of heavy saving reads as spectacular returns.

**Symbol autocomplete: live, and the list is genuinely StockSaathi's.**

Three sessions called this blocked on a deploy in their repository. It
never was. The reasoning was that their instrument master is
`dhan_instruments`, behind RLS with no anon policy, so reading it needed a
new endpoint over there. True, and beside the point:

- `dhan_instruments` is **empty**. Their own nightly sync has never
  filled it.
- `app/api/search.py`, the endpoint everyone waited on, selects a column
  called `exchange` when the column is `exchange_segment`. It would have
  answered 503 to everything.
- Their product never reads that table. It loads a **published static
  universe** from its own edge, and so do we now:

      https://stocksaathi.co.in/js/data/universeFull.<sha8>.json   4,367
      https://stocksaathi.co.in/js/data/mfFull.<sha8>.json        13,969

  Public, CORS-open, no key. The hash is discovered from an unhashed
  `<name>.meta.json` sidecar; `services/stocksaathi.py` owns that protocol
  and `scripts/sync_instruments.py` seeds from it.

So the suggestion box now says "instruments by StockSaathi" and means it,
and the data is better than what NSE and AMFI gave directly: sectors on
every share, fund houses on every scheme, ETFs included, and 13,969 funds
that can actually be bought rather than 37,882 mostly dormant ones.

Re-seed with `python scripts/sync_instruments.py`. Add `--prune` to drop
schemes they no longer carry; it cannot delete anything anybody holds,
because that is a condition inside the DELETE rather than a check before
it.

**The lesson worth keeping** is not about instruments. Every session that
called this blocked reasoned from a true premise to a false conclusion
without looking. One `ls js/data/` would have ended it -- the same way one
`ls app/api/` ended the "they have no mutual fund endpoint" claim.

For the record, in case it comes up again: the site is
`G:\StockSaathi\app`, which is **its own git repository** on `main`,
tracking github.com/thealiarbab/StockSaathi, deploying to Vercel on push.
The outer `G:\StockSaathi` has no remote and deploys nothing; `app/` shows
as untracked there only because every nested repo does. Ali has since
allowed changes and deploys there -- but **never the `kotlin` branch**.

One thing the browser caught that is worth remembering: **a missing
cross-origin endpoint does not present as a readable 404.** The host
answers its own 404 page, that page carries no
`Access-Control-Allow-Origin`, and the browser will not let script see the
status -- `fetch` simply rejects. The hook counts consecutive failures and
gives up after three rather than trusting a status it can never read.

### Phase 10 has been rewritten, and is ready to build

The spec is the last section of the plan,
`C:\Users\Alig\.claude\plans\hello-bubbly-lecun.md` -> **"Phase 10,
rewritten"**. It replaces the phase-table row, the `009 stocksaathi_link`
schema row and risk 4, all three of which now point at it. What follows is
the short version.

**The original was "opt-in account linking", importing StockSaathi holdings
into this ledger. That is cancelled, not deferred.** StockSaathi is a paper
trading simulator: teens 13-18, virtual money, SEBI-disclaimed, every
account opening with a lakh of play cash. Importing its positions would
file imaginary shares as net worth, and the figure would look entirely
plausible -- a wrong net worth looks exactly like a right one. SpendInCheck
exists to answer "am I over or under, and by how much", so that is not a
smaller version of the promise, it is the opposite of it.

**What gets built instead is a watchlist of this app's own**, on
Investments beneath the holdings: the things being considered rather than
the things owned. Search the universe already seeded from StockSaathi's
published file, add a symbol, remove it, price it with the same
`useLiveQuotes` hook the holdings use. Migration 018 gives it a table with
**no quantity column and no value column**, and that is the whole safety
property -- a row that cannot enter a total because it holds nothing to add
up.

**The import is a shortcut into that watchlist, not the reason for it.**
Symbols only. Build and commit the watchlist first; the phase is worth
having even if the import is never approved.

### The blocker three sessions reported does not exist

Every previous session called this blocked on StockSaathi shipping OAuth.
The premise was true and checkable -- their `app/api/` has no OAuth, no
token issuance, and no endpoint that reads one user's portfolio. The
conclusion did not follow. **Their Supabase is itself the authorisation
server**, it is public, and `watchlist` already carries a policy scoped to
`auth.uid()`.

Probed live on 2026-09-13, not inferred:

- `/api/config` publishes their Supabase URL and anon key -- meant to ship
  in client code.
- `/auth/v1/settings` reports `email: true` and **every** OAuth provider
  `false`, so a one-time email code is the flow, and `disable_signup` is
  `false`, which is exactly why `shouldCreateUser: false` is mandatory.
- `POST /auth/v1/otp` with `create_user: false` for an unknown address
  answers `422 otp_disabled` and sends no mail.
- The anon key reads `[]` from both `watchlist` and `holdings`. Their row
  level security is what scopes the import -- their enforcement, not our
  promise.

So: the user types their StockSaathi **email** (never their password) into
Settings, gets a six-digit code, and the browser holds a StockSaathi
session in a variable for one `SELECT` and then throws it away. It is never
written to `localStorage`, never sent to Flask, never stored anywhere.
**There is no link row, no stored token and no unlink** -- migration 009
and its Fernet-encrypted columns are cancelled outright, which deletes the
old risk 4 rather than mitigating it.

Nothing in StockSaathi's repository has to change. No deploy, no endpoint,
no migration. That is what makes this buildable now.

**The lesson, for the third time.** This is the same failure as the
instrument list and the "they have no mutual fund endpoint" claim: a true
premise, a conclusion that did not follow, and nobody looked. One
`curl /auth/v1/settings` ended it. When a StockSaathi feature looks
blocked, probe their live surface before concluding anything.

### The verify that decides the phase

Not that the import works. **That every total in the app is unchanged to
the paisa afterwards** -- net worth, net worth over time, the portfolio
total, the dashboard summary, every report. Record the numbers before,
diff them after. A watchlist that can move a number has failed the phase
however well the rest of it works.

### The one risk worth stating rather than hiding

A GoTrue session is a *whole* session, not a watchlist-scoped grant: RLS
stops it reaching anybody else's rows, not other tables of the user's own.
For the few seconds it is live it could in principle write to that
StockSaathi account. Held in memory only, never persisted, one `SELECT`,
then `signOut()`. The narrower fix is a scoped `GET /api/my-watchlist` in
their repository, and this deliberately does not wait for it.

> Still needs asking before it is built, like every phase a visitor sees.
> The product decision above is made; the go-ahead is not.

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
