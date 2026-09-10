# SpendInCheck

**Know whether you're on budget — not just what you spent.**

SpendInCheck is a personal finance tracker that ties three things most trackers keep
apart: where your money goes, what you planned to spend, and what your investments are
actually worth. It answers the question a list of transactions can't — *am I over or
under, and by how much?*

Runs on **PostgreSQL (Supabase)**, with every query written as raw parameterised SQL
rather than through an ORM.

---

## What it does

**Tracks the ledger.** Every rupee in and out, filed under a category, with full
create / read / update / delete from either interface.

**Holds you to a budget.** Set a monthly limit per category. The budget report puts
planned against actual side by side and labels each category *Over budget*, *On budget*
or *Under budget* — the report the whole app is named for.

**Watches the portfolio.** Stocks, mutual funds and fixed deposits with buy price
against current price, giving per-holding profit and loss plus a portfolio total.

## Screens

| Dashboard | Reports |
|---|---|
| ![Dashboard](docs/dashboard.png) | ![Reports](docs/reports.png) |

| Transactions |
|---|
| ![Transactions](docs/transactions.png) |

## Reports

| Report | Question it answers |
|---|---|
| Category-wise spend | Where did the money actually go this month? |
| Budget vs actual | Which categories blew past their limit, and by how much? |
| Portfolio P&L | Which holdings are up, which are down, what's the net? |

## How it's built

The design rule is that **all SQL lives in one place**. `server/operations/` holds every
query as a single function that returns plain Python data and never prints anything.

That constraint is what keeps the interfaces interchangeable: a route calls a function
and presents whatever comes back, so a new frontend needs no new SQL. The package is
split by domain, but it re-exports every name, so callers still write
`operations.add_transaction(...)`.

```
server/
  config.py       →  settings, read from the environment
  db.py           →  opens/closes the database connection
  operations/     →  every SQL query, one function each   ← all database logic
  app.py          →  the application factory
  routes/web.py   →  Flask routes + templates
app.py            →  local entrypoint; calls the factory
```

Queries are parameterised throughout (`%s` placeholders, never string interpolation),
so user input can never be executed as SQL. Writes commit on success and roll back on
failure. Every query is scoped by `user_id`, and the test suite asserts that a signed-in
account cannot reach another account's rows.

**Stack:** Python 3.11 · PostgreSQL (Supabase) · Flask · plain CSS

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

Put your connection settings in a `.env` file (see `.env.example`) and start the server:

```bash
python app.py
```

Run the tests with:

```bash
python -m pytest
```

`SECRET_KEY` signs the session cookie, which is what identifies a signed-in account.
It has a development default, and the app **refuses to start in production without a
real one** rather than serving sessions anyone could forge.

The schema ships with seed data — categories, three months of transactions, budgets and
a mixed portfolio — so every report returns real output immediately.

## About

Built by [Ali Arbab](https://github.com/thealiarbab).
