"""Aggregate queries that summarise a month.

Split out of the original single operations module; the SQL and the
function bodies are unchanged. Import these through the package, which
re-exports every name.

Every query here carries `transfer_group_id IS NULL`. A transfer is written
as two ordinary rows -- an Expense leaving one account and an Income
arriving in another -- and both are real from their account's point of view,
which is why balances count them. No report should. Moving 10,000 from
savings to current is not 10,000 earned and 10,000 spent: the net is zero,
so cashflow would survive, but the trend would grow two bars out of money
that never entered or left, and the payee list would rank your own savings
account among the places your money goes.
"""

from decimal import Decimal

from .. import db


# Nothing here catches psycopg2.Error. A report that cannot run has no
# answer, and an empty list is not "no answer" -- it is the specific claim
# that the account spent nothing, which is a lie the reader has no way to
# see through. The blueprint turns a database error into 503, so letting it
# out is what produces an honest one.


def category_wise_spend(user_id, month_year):
    """Report: total Expense amount per category for the given 'YYYY-MM' month.

    Returns a list of (category_name, total_spent) tuples, highest spend first.
    The GROUP BY collapses every transaction row in a category into one row
    so SUM(amount) can add up all of them together.
    """
    # A half-open range on txn_date, not EXTRACT on it.
    #
    # This used to split 'YYYY-MM' and match the year and month separately,
    # to avoid a date-format string containing '%' clashing with the %s the
    # driver substitutes. That worry was real but the remedy overshot:
    # Postgres spells its format 'YYYY-MM', which has no '%' in it at all.
    #
    # What it cost was the index. Wrapping a column in a function makes it
    # unreachable, so EXTRACT(YEAR FROM txn_date) could not use
    # idx_txn_user_type (user_id, txn_type, txn_date) -- the index migration
    # 008 added for exactly this shape. EXPLAIN showed only user_id reaching
    # the index and every one of that account's rows fetched from the heap
    # to be filtered in memory; with the range it is an Index Only Scan that
    # never touches the heap.
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT c.category_name, SUM(t.amount) AS total_spent
            FROM transactions t
            JOIN categories c ON t.category_id = c.category_id
            WHERE t.user_id = %s AND t.txn_type = 'Expense'
              AND t.transfer_group_id IS NULL
              AND t.txn_date >= to_date(%s, 'YYYY-MM')
              AND t.txn_date <  to_date(%s, 'YYYY-MM') + INTERVAL '1 month'
            GROUP BY c.category_name
            ORDER BY total_spent DESC
        """
        cursor.execute(query, (user_id, month_year, month_year))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def budget_vs_actual(user_id, month_year):
    """Report: for each budgeted category in the given month, compare the
    budget limit against the actual amount spent.

    Returns a list of (category_name, budget_limit, actual_spent, difference)
    tuples, where difference = budget_limit - actual_spent (positive means
    under budget, negative means over budget).
    """
    # The WHERE clause already pins every budget row to the requested month,
    # so matching transactions on that same month lines the two tables up.
    # Matched as a range rather than with EXTRACT, for the reason given in
    # category_wise_spend above.
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT
                c.category_name,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS actual_spent,
                -- The allowance is the limit plus whatever the previous
                -- month carried in, so an underspent June genuinely widens
                -- July rather than merely being reported next to it.
                b.budget_limit + b.rollover_in - COALESCE(SUM(t.amount), 0)
                    AS difference,
                b.rollover_in,
                b.rollover
            FROM budgets b
            JOIN categories c ON b.category_id = c.category_id
            LEFT JOIN transactions t
                -- user_id first, and not for safety: a category belongs to
                -- exactly one account, so matching on category_id alone was
                -- already correct. It is here because every useful index on
                -- this table starts with user_id, and without it none of
                -- them could be used at all.
                ON t.user_id = b.user_id
                AND t.category_id = b.category_id
                AND t.txn_type = 'Expense'
                AND t.transfer_group_id IS NULL
                -- A range, not EXTRACT. See category_wise_spend above.
                AND t.txn_date >= to_date(%s, 'YYYY-MM')
                AND t.txn_date <  to_date(%s, 'YYYY-MM') + INTERVAL '1 month'
            WHERE b.user_id = %s AND b.month_year = %s
            GROUP BY c.category_name, b.budget_limit, b.rollover_in, b.rollover
            ORDER BY difference ASC
        """
        cursor.execute(query, (month_year, month_year, user_id, month_year))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


# How many months of history the trend and cashflow series cover. A year
# reads as a year -- twelve points is enough to see a season in, and few
# enough to draw legibly on a phone.
SERIES_MONTHS = 12


def monthly_trend(user_id, months=SERIES_MONTHS):
    """Income and expense per month, oldest first.

    Returns (month, income, expense) with month as 'YYYY-MM'.

    Both figures come from one pass with FILTER rather than two queries or a
    self-join: the rows are already being read, and asking twice means a
    second trip to the database to say something about the same rows.

    Months with no transactions are absent rather than zero. Filling the gaps
    is the caller's job, because only the caller knows which months it means
    to show -- a chart wants a continuous axis, a table does not.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT to_char(date_trunc('month', txn_date), 'YYYY-MM') AS month,
                   COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Income'), 0),
                   COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Expense'), 0)
            FROM transactions
            WHERE user_id = %s AND transfer_group_id IS NULL
              AND txn_date >= date_trunc('month', CURRENT_DATE)
                              - make_interval(months => %s)
            GROUP BY date_trunc('month', txn_date)
            ORDER BY date_trunc('month', txn_date)
        """, (user_id, months - 1))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def cashflow_series(user_id, months=SERIES_MONTHS):
    """What was left over each month, and the running total of it.

    Returns (month, net, cumulative). Net is income minus expense for that
    month; cumulative is every net up to and including it.

    The running total is a window function rather than a loop in Python
    because the database is already ordered by month here -- doing it after
    the fact means the caller has to know the rows arrived in the right
    order, which is exactly the assumption that breaks when someone later
    adds a sort.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            WITH monthly AS (
                SELECT date_trunc('month', txn_date) AS month_start,
                       COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Income'), 0)
                     - COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Expense'), 0)
                       AS net
                FROM transactions
                WHERE user_id = %s AND transfer_group_id IS NULL
                  AND txn_date >= date_trunc('month', CURRENT_DATE)
                                  - make_interval(months => %s)
                GROUP BY date_trunc('month', txn_date)
            )
            SELECT to_char(month_start, 'YYYY-MM'), net,
                   SUM(net) OVER (ORDER BY month_start)
            FROM monthly
            ORDER BY month_start
        """, (user_id, months - 1))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


# How far back the payee list looks, and how many payees it shows. Named
# because the combined summary statement uses the same two numbers, and two
# copies of a window is two answers to "last three months".
MERCHANT_MONTHS = 3
MERCHANT_LIMIT = 8


def top_merchants(user_id, months=MERCHANT_MONTHS, limit=MERCHANT_LIMIT):
    """What the money actually went to, by description.

    Returns (description, times, total), biggest total first.

    Grouped on the description because that is the nearest thing this schema
    has to a payee -- there is no merchant column, and inventing one from
    free text is guesswork. Blank descriptions are excluded rather than
    collected into an "unnamed" row, which would usually be the largest bar
    on the chart and say nothing.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT lower(trim(description)) AS payee,
                   COUNT(*) AS times,
                   SUM(amount) AS total
            FROM transactions
            WHERE user_id = %s AND txn_type = 'Expense'
              AND transfer_group_id IS NULL
              AND description IS NOT NULL AND trim(description) <> ''
              AND txn_date >= date_trunc('month', CURRENT_DATE)
                              - make_interval(months => %s)
            GROUP BY lower(trim(description))
            ORDER BY total DESC
            LIMIT %s
        """, (user_id, months - 1, limit))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


# What the holdings were worth at the end of one month.
#
# Written once and used twice -- by net_worth_series below and by the
# combined _SUMMARY statement -- because the two had the same subquery
# copied out, and a valuation rule that exists in two places is one that
# will be corrected in one of them.
#
# The lateral join is the whole point. For each holding it takes the last
# close recorded on or before that month end, so March is valued at March's
# price rather than at today's. A holding with no ticker -- a deposit, an
# unlisted holding -- has no history to find, and one whose symbol was only
# tracked recently has none that far back; both fall through to
# current_price, which is the best figure available and is what this used to
# do for everything.
#
# Interpolated rather than parameterised because both arguments are SQL
# fragments named in this file, never anything from a request. Same rule as
# the sort whitelist in search_transactions: identifiers and expressions are
# chosen in code, values go through %s.
def _holdings_at_month_end(month_end, user_param):
    """The SQL for one month's holdings valuation."""
    return f"""
        COALESCE((
            SELECT SUM(COALESCE(past.close, i.current_price) * i.quantity)
              FROM investments i
              LEFT JOIN LATERAL (
                  SELECT q.close
                    FROM quote_history q
                   WHERE q.ticker = i.ticker
                     AND q.on_date < {month_end}
                   ORDER BY q.on_date DESC
                   LIMIT 1
              ) past ON TRUE
             WHERE i.user_id = {user_param}
               AND i.buy_date < {month_end}
        ), 0)"""

def net_worth_series(user_id, months=SERIES_MONTHS):
    """Net worth at the end of each month: holdings plus cash accumulated.

    Returns (month, holdings_value, cash, net_worth).

    Each month values the holdings at what they actually closed at then,
    from quote_history, rather than at today's price. The difference is not
    cosmetic: valuing everything at today's price made a holding that has
    doubled look as though it had always been worth double, so the line
    described the portfolio's composition changing and nothing about the
    market.

    Anything with no recorded close for that month -- a deposit, an
    unlisted holding, a symbol only tracked since last week -- still falls
    back to current_price. That is the old behaviour, kept as the fallback
    rather than as the rule.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            WITH months AS (
                SELECT generate_series(
                    date_trunc('month', CURRENT_DATE) - make_interval(months => %s),
                    date_trunc('month', CURRENT_DATE),
                    interval '1 month') AS month_start
            ),
            cash AS (
                SELECT m.month_start,
                       -- What the accounts opened with, before a single row
                       -- was written. Without it this line is the ledger's
                       -- movement rather than the money, and disagrees with
                       -- the total the Accounts screen shows -- which counts
                       -- opening balances, because that is where the money
                       -- actually starts.
                       (SELECT COALESCE(SUM(a.opening_balance), 0)
                          FROM accounts a WHERE a.user_id = %s)
                       + COALESCE((
                           SELECT SUM(CASE WHEN t.txn_type = 'Income'
                                           THEN t.amount ELSE -t.amount END)
                           FROM transactions t
                           WHERE t.user_id = %s
                             AND t.transfer_group_id IS NULL
                             AND t.txn_date < m.month_start + interval '1 month'
                       ), 0) AS running
                FROM months m
            ),
            held AS (
                SELECT m.month_start, """ + _holdings_at_month_end(
                    "m.month_start + interval '1 month'", "%s") + """ AS value
                FROM months m
            )
            SELECT to_char(cash.month_start, 'YYYY-MM'),
                   held.value, cash.running, held.value + cash.running
            FROM cash JOIN held ON held.month_start = cash.month_start
            ORDER BY cash.month_start
        """, (months - 1, user_id, user_id, user_id))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


# Every series the reporting screen needs, in one statement.
#
# Each of these exists on its own above, and asked separately they are seven
# round trips. Against Supabase in Mumbai a round trip is about 29ms whatever
# it carries, so seven of them is 200ms of waiting for queries that take
# single-digit milliseconds to run. As one statement it is 29ms.
#
# The money comes back as text, not as JSON numbers. json_build_array would
# render a numeric as a JSON float, and a float is exactly what money must
# never be -- 1200.50 is not representable and the error is silent. ::text
# keeps the digits, and _rows() below turns them back into Decimals so the
# result is shaped exactly as the seven separate queries were.
_SUMMARY = """
WITH span AS (
    SELECT date_trunc('month', CURRENT_DATE) AS this_month,
           date_trunc('month', CURRENT_DATE)
               - make_interval(months => %(months_back)s) AS series_from,
           date_trunc('month', CURRENT_DATE)
               - make_interval(months => %(merchant_months)s) AS merchants_from
),
-- The user's own rows, with transfers already excluded, written once
-- rather than repeated in five places.
ledger AS (
    SELECT t.* FROM transactions t
     WHERE t.user_id = %(user_id)s AND t.transfer_group_id IS NULL
),
this_month AS (
    SELECT COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Income'), 0) AS income,
           COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Expense'), 0) AS expense,
           COUNT(*) AS rows_this_month
      FROM ledger, span
     WHERE txn_date >= span.this_month
),
trend AS (
    SELECT to_char(date_trunc('month', txn_date), 'YYYY-MM') AS month,
           COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Income'), 0) AS income,
           COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Expense'), 0) AS expense,
           date_trunc('month', txn_date) AS sort_key
      FROM ledger, span
     WHERE txn_date >= span.series_from
     GROUP BY date_trunc('month', txn_date)
),
cashflow AS (
    SELECT month, income - expense AS net,
           SUM(income - expense) OVER (ORDER BY sort_key) AS cumulative,
           sort_key
      FROM trend
),
calendar AS (
    SELECT generate_series(span.series_from, span.this_month,
                           interval '1 month') AS month_start
      FROM span
),
net_worth AS (
    SELECT to_char(c.month_start, 'YYYY-MM') AS month,
           """ + _holdings_at_month_end(
               "c.month_start + interval '1 month'", "%(user_id)s") + """
               AS holdings,
           -- The opening balances, exactly as net_worth_series counts them
           -- and for the same reason. This query and that one answer the
           -- same question by different routes, and a test asserts they
           -- agree row for row -- which is how the first version of this
           -- fix, applied to only one of them, was caught.
           (SELECT COALESCE(SUM(a.opening_balance), 0)
              FROM accounts a WHERE a.user_id = %(user_id)s)
           + COALESCE((SELECT SUM(CASE WHEN l.txn_type = 'Income'
                                     THEN l.amount ELSE -l.amount END)
                       FROM ledger l
                      WHERE l.txn_date < c.month_start + interval '1 month'), 0)
               AS cash,
           c.month_start
      FROM calendar c
),
merchants AS (
    SELECT lower(trim(description)) AS payee, COUNT(*) AS times,
           SUM(amount) AS total
      FROM ledger, span
     WHERE txn_type = 'Expense' AND description IS NOT NULL
       AND trim(description) <> '' AND txn_date >= span.merchants_from
     GROUP BY lower(trim(description))
     ORDER BY total DESC
     LIMIT %(merchant_limit)s
),
spend AS (
    SELECT c.category_name, SUM(l.amount) AS total
      FROM ledger l JOIN categories c ON c.category_id = l.category_id, span
     WHERE l.txn_type = 'Expense' AND l.txn_date >= span.this_month
     GROUP BY c.category_name
     ORDER BY total DESC
)
SELECT
    (SELECT json_build_array(income::text, expense::text,
                             (income - expense)::text, rows_this_month)
       FROM this_month),
    (SELECT json_agg(json_build_array(month, income::text, expense::text)
                     ORDER BY sort_key) FROM trend),
    (SELECT json_agg(json_build_array(month, net::text, cumulative::text)
                     ORDER BY sort_key) FROM cashflow),
    (SELECT json_agg(json_build_array(month, holdings::text, cash::text,
                                      (holdings + cash)::text)
                     ORDER BY month_start) FROM net_worth),
    (SELECT json_agg(json_build_array(payee, times, total::text)) FROM merchants),
    (SELECT json_agg(json_build_array(category_name, total::text)) FROM spend)
"""


def _rows(carried, money_columns):
    """Turn one JSON array-of-arrays back into the tuples callers expect.

    The text columns that hold money become Decimals again, so a row from
    here is indistinguishable from a row the separate queries returned and
    nothing downstream has to know where it came from.
    """
    if not carried:
        return []
    return [tuple(Decimal(value) if index in money_columns and value is not None
                  else value
                  for index, value in enumerate(row))
            for row in carried]


def dashboard_summary(user_id, months=SERIES_MONTHS):
    """Everything the opening screen and the reporting screen need, at once.

    Returns a dictionary of the five series and figures below, in exactly
    the shape the individual functions above return -- they remain the
    readable definition of each one, and each has its own endpoint.

    One round trip rather than seven. Each query is single-digit
    milliseconds; reaching Mumbai is 29ms whatever it carries, so the trips
    were 85% of the wait.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute(_SUMMARY, {
            "user_id": user_id,
            "months_back": months - 1,
            "merchant_months": MERCHANT_MONTHS - 1,
            "merchant_limit": MERCHANT_LIMIT,
        })
        month, trend, cashflow, net_worth, merchants, spend = cursor.fetchone()

        income, expense, net, count = month
        return {
            "this_month": {"income": Decimal(income), "expense": Decimal(expense),
                           "net": Decimal(net), "transactions": count},
            "trend": _rows(trend, {1, 2}),
            "cashflow": _rows(cashflow, {1, 2}),
            "net_worth": _rows(net_worth, {1, 2, 3}),
            "merchants": _rows(merchants, {2}),
            "spend_by_category": _rows(spend, {1}),
        }
    finally:
        db.close_connection(connection)


def _current_month(cursor):
    """The current month as 'YYYY-MM', according to the database.

    Read from the database rather than from Python's clock so every figure
    on the screen agrees about which month it is. The server may be in a
    different timezone from the database, and near midnight on the first of
    the month the two disagree -- which would show one month's spending
    beside another month's budget.
    """
    cursor.execute("SELECT to_char(CURRENT_DATE, 'YYYY-MM')")
    return cursor.fetchone()[0]
