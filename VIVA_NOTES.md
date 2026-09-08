# SpendInCheck — Viva Notes

Read this before your viva. It explains *why* the database looks the way it
does and *what* each report query is doing, in plain English, with no code.

## The four tables and how they relate

**categories** is the master list of "buckets" money can belong to — things
like Salary, Rent, Groceries. Each category is tagged Income or Expense.

**transactions** is the actual ledger: every rupee that came in or went out,
on a date, tied to exactly one category through `category_id`. This is a
foreign key — it means a transaction can never point to a category that
doesn't exist, because MySQL checks it for you.

**budgets** is a monthly spending limit set per category — "I want to spend
at most ₹4000 on Groceries in July 2026." It also has a foreign key back to
`categories`, and a UNIQUE constraint on (category_id, month_year) so you
can't accidentally create two different budgets for the same category in
the same month — setting a budget again just overwrites the old value.

**investments** is separate from the other three — it doesn't track day-to-day
cash flow, it tracks holdings (stocks, mutual funds, FDs) with a buy price,
a quantity, and a current price, so we can compute profit or loss.

The chain **categories → transactions → budgets** is the heart of the app:
categories are the shared vocabulary that both what-you-spent (transactions)
and what-you-planned-to-spend (budgets) refer back to. That's what makes the
"budget vs actual" report possible — it lines up rows from two different
tables because they share the same category_id.

## What each report query does, conceptually

### Category-wise spend (`operations.category_wise_spend`)

We JOIN transactions to categories to get readable category names, filter
down to just Expense rows in the chosen month, then GROUP BY category name.
GROUP BY collapses every transaction row belonging to the same category into
a single row, so SUM(amount) can add up all of them together into one total
per category. We sort by that total, highest first, so the biggest expense
category is immediately visible.

The month filter uses `YEAR(txn_date) = %s AND MONTH(txn_date) = %s` rather
than `DATE_FORMAT(txn_date, '%Y-%m')`. Both would work in plain SQL, but the
`%` characters inside a DATE_FORMAT pattern collide with the `%s`
placeholders that mysql.connector substitutes, which silently made this
report return nothing. Splitting 'YYYY-MM' in Python and comparing the year
and month separately keeps the SQL free of `%` signs entirely.

### Budget vs actual (`operations.budget_vs_actual`)

We start from budgets (so every budgeted category shows up even if it had
zero spending that month), and LEFT JOIN in the matching transactions for
that same category and month. LEFT JOIN is important here: if a category
was budgeted but nothing was actually spent, a plain JOIN would drop that
row entirely, but LEFT JOIN keeps it and just treats the missing spend as
NULL. We wrap the summed spend in COALESCE(..., 0) to turn that NULL into a
plain 0, then GROUP BY category so SUM(amount) again collapses multiple
transactions into one actual-spend figure. difference = budget - actual, so
a negative difference means the category went over budget. The month is
matched with YEAR()/MONTH() for the same reason as the report above.

Worked example from the seed data (July 2026): Utilities has a budget of
2000 but an actual electricity bill of 2300, so difference is -300 and the
report flags it "Over budget". Groceries has a budget of 4000 against 2900
spent, so difference is +1100, "Under budget".

### Portfolio P&L (`operations.portfolio_pnl`)

No JOIN or GROUP BY needed here — every investment is already one row. For
each row we compute `(current_price - buy_price) * quantity`, which is just
"how much has each unit gained or lost, times how many units you hold."
We sort by that P&L figure, highest first, so the best-performing asset is
at the top. main.py then adds up the P&L and current value across all rows
to show the whole portfolio's total gain/loss.

## Design choices worth being able to defend

- **Parameterized queries (`%s` placeholders) everywhere.** User input is
  never pasted directly into an SQL string. This prevents SQL injection —
  if someone typed `'; DROP TABLE transactions; --` into a text field, it
  would be treated as a literal string value, not as SQL to execute.
- **operations.py never prints anything — it only returns data.** main.py
  is the only file that formats and prints. This means the exact same
  functions could be called from a different frontend (e.g. a Flask web
  page) without changing any SQL at all.
- **Every write function commits on success and rolls back on failure**,
  wrapped in try/except catching `mysql.connector.Error` specifically
  (never a bare `except:`), so a failed insert can't leave the database in
  a half-changed state.
- **ON DUPLICATE KEY UPDATE for budgets** relies on the UNIQUE constraint
  on (category_id, month_year): instead of manually checking "does a
  budget already exist?" and then choosing INSERT or UPDATE, MySQL does
  that check atomically in one statement.

## Five questions an examiner might ask

**Q1. Why use `%s` placeholders instead of just building the SQL string with
Python f-strings?**
A: f-strings would let raw user input become part of the SQL command
itself, which is how SQL injection attacks work. `%s` placeholders send the
value separately from the query structure, so it's always treated as data,
never as SQL code.

**Q2. Why does `transactions` store `category_id` instead of the category
name directly?**
A: This is normalization — the category name only needs to be stored once,
in the `categories` table. If we stored "Groceries" as text in every
transaction row and later wanted to rename it, we'd have to update every
single row. With a foreign key, we change it once in `categories` and every
transaction automatically reflects it.

**Q3. What does `cursor.rowcount` tell you, and why is checking
`rowcount > 0` on its own not enough after an UPDATE?**
A: `rowcount` is how many rows the last statement actually *changed* — not
how many it matched. Running a DELETE with `WHERE transaction_id = 999`
that matches nothing doesn't raise an error; the query "succeeds" but
removes zero rows, so for DELETE, `rowcount > 0` correctly means "something
was really removed."

For UPDATE it's trickier: if you re-save a row with exactly the same values
it already had, MySQL reports rowcount 0 because nothing physically
changed, even though the update worked perfectly. So in
`update_transaction` a rowcount of 0 is followed by a quick SELECT to check
whether the row exists — that separates "nothing to change" (success) from
"no such transaction" (genuine failure). This is a real bug that was caught
by testing the app against the live database.

**Q4. Why is the connection opened and closed inside every single function
in operations.py, instead of once at the start of the program?**
A: It keeps each function self-contained and simple to reason about for a
viva — you can read any one function in isolation and know exactly when the
connection opens and closes. It also means a failed or slow connection in
one function can't leave a connection hanging open for the rest of the
session.

**Q5. In the portfolio P&L report, what would a negative value in the `pnl`
column mean?**
A: That the current price has dropped below the buy price for that asset,
so `(current_price - buy_price)` is negative — the investment is currently
at a loss. Multiplying by quantity scales that per-unit loss to the total
loss on the whole holding.
