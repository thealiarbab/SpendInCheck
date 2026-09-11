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

## 2. Restart the four servers

None survive a power cut. Start them with `preview_start`, by name, from
`.claude/launch.json`:

| name | port | what |
|---|---|---|
| `spendincheck-mirror` | 8000 | **the site** — `/` is the React client, Jinja pages at their own paths |
| `spendincheck-flask` | 5000 | the API and the old pages |
| `spendincheck-spa` | 5173 | Vite |
| `spendincheck-progress` | 5099 | the progress page |

Open `http://localhost:8000`. Compare old against new by dropping `/app`:
`/transactions` is the Jinja page, `/app/transactions` the React one, on
one session.

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

## 5. Measure, do not assert

`python scripts/benchmark.py` writes `docs/benchmarks.json`, which the
progress page renders. Run it after touching any request path, and quote
figures from it rather than reasoning about them.

## 6. Decisions that are not visible in the code

- **Both themes ship, toggleable.** Every UI primitive reads semantic
  tokens, never a literal colour, so a screen is correct in brass and paper
  at once.
- **The demo is open to anyone, any time, with no sign-up.** One throwaway
  account per visitor.
- **Nothing is deployed until Phase 8.** The React client is not on
  spendincheck.com; pushing to `main` deploys, so it needs asking first.
- **Money never converts between currencies.** There are no exchange rates;
  changing currency relabels and re-rounds, and the settings screen says so
  before the control.

## 7. Where Phase 8 starts

Phase 7 is closed. Accounts, tags, goals, recurring, rollover and CSV
import, on migrations 003-007 -- one number later than the plan's table,
because 002 went on widening the money columns.

The four decisions worth knowing before touching any of it:

- **Balances and goal totals are summed on read, never stored.** A stored
  total is a second copy of a fact that already exists, and the two
  disagree the first time something is edited.
- **`budgets.rollover_in` is the one exception**, because deriving it means
  walking back through every month a category was ever budgeted for. Every
  write path recomputes it, and one test rebuilds it from scratch and
  compares.
- **A transfer is two ordinary rows sharing a `transfer_group_id`.** Every
  report carries `transfer_group_id IS NULL`; without it, moving money
  between your own accounts reads as income and expenditure.
- **The recurring sweep is idempotent by construction**, via a unique index
  on `(rule_id, txn_date)`. Vercel cron is at-least-once, so a repeat run
  has to be a no-op rather than a duplicate rent.

Phase 8 is killing Jinja: flip the rewrite so React owns `/*`, in one
revertable commit. Three Jinja templates have already broken this phase by
unpacking a tuple that grew a column -- `tests/test_pages_render.py` now
guards the row shapes, and all of that goes away with the templates.
