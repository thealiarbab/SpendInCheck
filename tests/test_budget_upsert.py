"""Regression tests for setting a budget.

The conflict target in set_budget has to name exactly the columns of the
unique constraint. When the constraint gained user_id and the query did not,
Postgres rejected every statement and budgets silently stopped saving -- the
page still answered 200 and the row was simply never written.

These run against the real database because the bug lived in the agreement
between the SQL and the schema. A mock cursor accepts any conflict target
and would have reported success throughout.
"""

from server import db, operations


def _constraint_columns():
    """The columns of the unique constraint on budgets, in order."""
    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conrelid = 'budgets'::regclass AND contype = 'u'
        """)
        definition = cursor.fetchone()[0]
        inside = definition[definition.index("(") + 1:definition.rindex(")")]
        return [column.strip() for column in inside.split(",")]
    finally:
        db.close_connection(connection)


def test_setting_a_budget_stores_it(make_user):
    user_id = make_user()
    category_id = operations.get_all_categories(user_id)[0][0]

    assert operations.set_budget(user_id, category_id, "2026-08", 5000) is True
    stored = operations.get_all_budgets(user_id)
    assert len(stored) == 1


def test_setting_the_same_month_twice_overwrites(make_user):
    """The second call must replace the limit, not add a row or fail."""
    user_id = make_user()
    category_id = operations.get_all_categories(user_id)[0][0]

    operations.set_budget(user_id, category_id, "2026-08", 5000)
    operations.set_budget(user_id, category_id, "2026-08", 6000)

    stored = operations.get_all_budgets(user_id)
    assert len(stored) == 1
    assert str(stored[0][3]) == "6000.00"


def test_two_accounts_can_budget_the_same_month(make_user):
    """The constraint is per user, so one account must not block another."""
    first, second = make_user(), make_user()
    assert operations.set_budget(first, operations.get_all_categories(first)[0][0],
                                 "2026-08", 1000) is True
    assert operations.set_budget(second, operations.get_all_categories(second)[0][0],
                                 "2026-08", 2000) is True


def test_the_query_targets_the_constraint_that_exists(make_user):
    """Guards the mismatch directly, so a schema change fails loudly here.

    A future migration that alters this constraint will break set_budget in
    exactly the way it broke last time, and the other tests only catch it if
    they happen to run against a migrated database.
    """
    import inspect
    source = inspect.getsource(operations.set_budget)
    columns = _constraint_columns()
    target = "ON CONFLICT (" + ", ".join(columns) + ")"
    assert target in source, f"set_budget must conflict on {columns}"
