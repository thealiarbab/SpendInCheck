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

from psycopg2 import Error
from .. import db

def category_wise_spend(user_id, month_year):
    """Report: total Expense amount per category for the given 'YYYY-MM' month.

    Returns a list of (category_name, total_spent) tuples, highest spend first.
    The GROUP BY collapses every transaction row in a category into one row
    so SUM(amount) can add up all of them together.
    """
    # Split 'YYYY-MM' and match the year and month separately with EXTRACT,
    # avoiding any date-format string containing '%' that would clash with
    # the %s placeholders the driver substitutes.
    year_part, month_part = month_year.split("-")
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
              AND EXTRACT(YEAR FROM t.txn_date) = %s
              AND EXTRACT(MONTH FROM t.txn_date) = %s
            GROUP BY c.category_name
            ORDER BY total_spent DESC
        """
        cursor.execute(query, (user_id, year_part, month_part))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating category-wise spend report: {e}")
        return []
    finally:
        db.close_connection(connection)


def budget_vs_actual(user_id, month_year):
    """Report: for each budgeted category in the given month, compare the
    budget limit against the actual amount spent.

    Returns a list of (category_name, budget_limit, actual_spent, difference)
    tuples, where difference = budget_limit - actual_spent (positive means
    under budget, negative means over budget).
    """
    # Same reasoning as category_wise_spend: EXTRACT keeps '%' out of the SQL.
    # The WHERE clause already pins every budget row to the requested month, so
    # matching transactions on that same year/month lines the two tables up.
    year_part, month_part = month_year.split("-")
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        query = """
            SELECT
                c.category_name,
                b.budget_limit,
                COALESCE(SUM(t.amount), 0) AS actual_spent,
                b.budget_limit - COALESCE(SUM(t.amount), 0) AS difference
            FROM budgets b
            JOIN categories c ON b.category_id = c.category_id
            LEFT JOIN transactions t
                ON t.category_id = b.category_id
                AND t.txn_type = 'Expense'
                AND t.transfer_group_id IS NULL
                AND EXTRACT(YEAR FROM t.txn_date) = %s
                AND EXTRACT(MONTH FROM t.txn_date) = %s
            WHERE b.user_id = %s AND b.month_year = %s
            GROUP BY c.category_name, b.budget_limit
            ORDER BY difference ASC
        """
        cursor.execute(query, (year_part, month_part, user_id, month_year))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating budget-vs-actual report: {e}")
        return []
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
    except Error as e:
        print(f"Error generating the monthly trend: {e}")
        return []
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
    except Error as e:
        print(f"Error generating the cashflow series: {e}")
        return []
    finally:
        db.close_connection(connection)


def top_merchants(user_id, months=3, limit=8):
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
    except Error as e:
        print(f"Error generating the top merchants report: {e}")
        return []
    finally:
        db.close_connection(connection)


def net_worth_series(user_id, months=SERIES_MONTHS):
    """Net worth at the end of each month: holdings plus cash accumulated.

    Returns (month, holdings_value, cash, net_worth).

    Holdings are valued at their current price for every month, not at what
    they were worth at the time. This project stores one price per holding
    and no history, so anything else would be invented. Phase 9 replaces
    this with real historical closes from quote_history, and the shape of
    the answer is the same so the chart will not have to change.
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
                       COALESCE((
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
                SELECT m.month_start,
                       COALESCE((
                           SELECT SUM(i.current_price * i.quantity)
                           FROM investments i
                           WHERE i.user_id = %s
                             AND i.buy_date < m.month_start + interval '1 month'
                       ), 0) AS value
                FROM months m
            )
            SELECT to_char(cash.month_start, 'YYYY-MM'),
                   held.value, cash.running, held.value + cash.running
            FROM cash JOIN held ON held.month_start = cash.month_start
            ORDER BY cash.month_start
        """, (months - 1, user_id, user_id))
        return cursor.fetchall()
    except Error as e:
        print(f"Error generating the net worth series: {e}")
        return []
    finally:
        db.close_connection(connection)


def dashboard_summary(user_id, months=SERIES_MONTHS):
    """Everything the opening screen and the reporting screen need, at once.

    Returns a dictionary of the five series and figures below.

    The point is the connection, not the SQL. Each query here is quick --
    single-digit milliseconds against tables this size -- while reaching
    Supabase at all costs roughly two hundred. Asked separately these are
    seven round trips and most of a second and a half; sharing one
    connection they are one trip and the queries are almost free.

    db.get_connection() returns the request's own connection, so the
    functions called below reuse it rather than opening their own.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()

        # This month's income and expense, for the headline figures.
        cursor.execute("""
            SELECT COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Income'), 0),
                   COALESCE(SUM(amount) FILTER (WHERE txn_type = 'Expense'), 0),
                   COUNT(*)
            FROM transactions
            WHERE user_id = %s AND transfer_group_id IS NULL
              AND txn_date >= date_trunc('month', CURRENT_DATE)
        """, (user_id,))
        income, expense, count = cursor.fetchone()

        return {
            "this_month": {"income": income, "expense": expense,
                           "net": income - expense, "transactions": count},
            "trend": monthly_trend(user_id, months),
            "cashflow": cashflow_series(user_id, months),
            "net_worth": net_worth_series(user_id, months),
            "merchants": top_merchants(user_id),
            "spend_by_category": category_wise_spend(
                user_id, _current_month(cursor)),
        }
    except Error as e:
        print(f"Error generating the dashboard summary: {e}")
        return {}
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
