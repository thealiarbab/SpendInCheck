# SpendInCheck

**Know whether you're on budget — not just what you spent.**

### [**spendincheck.com**](https://spendincheck.com) — try the demo, no signup

SpendInCheck is a personal finance tracker that ties three things most trackers keep
apart: where your money goes, what you planned to spend, and what your investments are
actually worth. It answers the question a list of transactions can't — *am I over or
under, and by how much?*

The demo is your own private copy, loaded with three months of figures. Edit or delete
anything in it; it is discarded when you leave.

Runs on **PostgreSQL (Supabase)**, with every query written as raw parameterised SQL
rather than through an ORM.

---

## What it does

**Tracks the ledger.** Every amount in and out, filed under a category and an
account, with search, filters, sorting and CSV both ways.

**Holds you to a budget.** Set a monthly limit per category. The budget report puts
planned against actual side by side and labels each category *Over budget*, *On budget*
or *Under budget* — the report the whole app is named for.

**Watches the portfolio.** Stocks, mutual funds and fixed deposits with buy price
against current price, giving per-holding profit and loss plus a portfolio total.

**Prices itself from the market.** Point a holding at an NSE symbol — start typing and
it suggests one from the 2,292-strong equity list — and its price is fetched instead of
typed. Off by default and per holding, so nothing starts moving without being asked.

**Remembers what things used to be worth.** A nightly job records the day's close for
every tracked symbol, so the net-worth chart values each month at what things were
actually worth *then*. Valuing the past at today's price is the difference between a
line about the market and a line about what you happened to buy.

**Keeps up on its own.** Recurring rules write the rent on the first and the salary on
the last, once each, however often the sweep runs. Budgets can roll their unspent
remainder into next month. Transfers between accounts count as neither income nor
spending, and every report knows it.

**Puts the rest in one place.** Savings goals with contributions towards them, tags
across transactions, multiple accounts, and CSV import that shows you every row — and
the reason for each one it will skip — before writing anything.

## Screens

**Dashboard** — what you hold and what you have been spending.

![Dashboard](docs/dashboard.jpg)

**Reports** — income against expense, the running total, net worth at each
month's close, and where the money actually goes.

![Reports](docs/reports.jpg)

**Holdings** — a symbol on a holding means its price is fetched rather than
typed, with the day's move, a month of shape and the 52-week range beside it.
Leave the symbol off and the holding keeps whatever price you last gave it.

![Holdings](docs/holdings.jpg)

**Transactions** — search, filter, sort, and CSV in both directions. A transfer
between accounts is two rows sharing a group, which is why no report counts it
as income or spending.

![Transactions](docs/transactions.jpg)

## Reports

| Report | Question it answers |
|---|---|
| Category-wise spend | Where did the money actually go this month? |
| Budget vs actual | Which categories blew past their limit, and by how much? |
| Portfolio P&L | Which holdings are up, which are down, what's the net? |
| Net worth over time | What am I worth, month by month, at the prices of the time? |
| Income and expense | What came in against what went out, over the last year? |
| Cashflow running total | Is the gap between them widening or closing? |
| Against the market | Did my holdings beat the index, with quantities held constant? |
| Where it goes | Which payees take the most, and how often? |

## How it's built

The design rule is that **all SQL lives in one place**. `server/operations/` holds every
query as a single function that returns plain Python data and never prints anything.

That constraint is what kept the interfaces interchangeable while the site was rewritten
underneath them: a route calls a function and presents whatever comes back, so replacing
the entire frontend needed no new SQL. The package is split by domain, but it re-exports
every name, so callers still write `operations.add_transaction(...)`.

```
server/
  config.py       →  settings, read from the environment
  db.py           →  the connection pool
  operations/     →  every SQL query, one function each   ← all database logic
  app.py          →  the application factory
  routes/api/     →  the JSON API, one module per resource
app.py            →  local entrypoint; calls the factory
web/              →  the React client: everything a visitor sees
```

The server answers `/api/v1` and nothing else. The site itself is a built bundle served
from the edge, so a page load never wakes Python — only the data it asks for does. The
screens are split per route, so a visitor to the front page downloads the front page
rather than the whole application.

Three jobs run on a schedule: the day's closing prices, the recurring sweep, and a
clear-out of abandoned demo accounts. Each is guarded by a shared secret and each is
safe to run twice — the recurring sweep advances a rule and writes its row in the same
transaction, with a unique index making a repeat a no-op rather than a double entry.

Queries are parameterised throughout (`%s` placeholders, never string interpolation),
so user input can never be executed as SQL. Writes commit on success and roll back on
failure. Every query is scoped by `user_id`, and the test suite asserts that a signed-in
account cannot reach another account's rows.

**Stack:** Python 3.11 · PostgreSQL (Supabase) · Flask · React · TypeScript · Vite

## Running it

```bash
pip install -r requirements.txt
```

Load the schema into a Postgres database:

```bash
psql "$DATABASE_URL" -f schema_postgres.sql
```

Then apply any migrations in order:

```bash
python scripts/migrate.py
```

Put your connection settings in a `.env` file (see `.env.example`) and start the API:

```bash
python app.py
```

Then the client, which proxies `/api` to it — this is the whole site, on one port:

```bash
npm --prefix web install && npm --prefix web run dev
```

Run the tests with:

```bash
python -m pytest
```

They run against a real Postgres database, because what is under test is the SQL. A
query that forgets its `user_id` filter looks perfectly correct in Python and only
misbehaves in the database, so a mocked cursor would report success on exactly the bug
worth catching.

Symbol autocomplete needs its universe, taken from NSE's own published equity list:

```bash
python scripts/sync_instruments.py
```

`SECRET_KEY` signs the session cookie, which is what identifies a signed-in account.
It has a development default, and the app **refuses to start in production without a
real one** rather than serving sessions anyone could forge.

The schema ships with seed data — categories, three months of transactions, budgets and
a mixed portfolio — so every report returns real output immediately.

## About

Built by [Ali Arbab](https://github.com/thealiarbab).
