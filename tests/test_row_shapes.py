"""A query's column count must match the field names the API zips onto it.

This file used to be test_pages_render.py, and existed because three Jinja
templates in a row broke the same way: an operation grew a column, the
template kept unpacking the old count, and the page raised on every render.
The templates are gone as of Phase 8. The hazard is not.

money.row() builds each JSON object with

    zip(field_names, values)

and zip stops at the shorter of the two. So a query that gains a tenth
column while its FIELDS list still names nine does not raise, does not warn,
and does not appear in the response -- the new column is silently dropped on
the way out. That is strictly worse than the template breakage this replaced,
which at least announced itself with a 500.

So rather than counting columns against a number typed here, each row shape
is checked against the list the route actually serialises it with. Nothing
in this file needs updating when a column is added: add it to the FIELDS
list where it belongs, and this passes again.
"""

import pytest

from server import operations
from server.routes.api import accounts, budgets, categories, investments
from server.routes.api import recurring, reports, transactions

# operation -> the field names the route zips onto its rows.
#
# Only operations the demo seed fills. An empty result would make every
# assertion below vacuously true, which is a worse outcome than not
# checking at all, because it looks like coverage.
SERIALISED = {
    "get_all_transactions": transactions.LIST_FIELDS,
    "get_all_budgets": budgets.FIELDS,
    "portfolio_pnl": reports.PNL_FIELDS,
    "get_all_categories": categories.FIELDS,
    "get_all_investments": investments.FIELDS,
    "list_accounts": accounts.FIELDS,
    "list_rules": recurring.FIELDS,
}


@pytest.fixture
def seeded_client(client):
    """A client signed into a throwaway demo account, with data in it.

    The demo seed is what makes this worth running: empty tables would
    return zero rows and prove nothing about their shape.
    """
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    body = client.post("/api/v1/auth/demo",
                       headers={"X-CSRF-Token": token}).get_json()
    yield client
    operations.delete_demo_user(body["user"]["id"])


@pytest.mark.parametrize("name", sorted(SERIALISED))
def test_the_row_shape_matches_the_field_names(seeded_client, name):
    """Fails when a query gains or loses a column its route does not name."""
    user_id = seeded_client.get("/api/v1/auth/session").get_json()["user"]["id"]
    rows = getattr(operations, name)(user_id)
    assert rows, f"{name} returned nothing; the demo seed should have rows"

    fields = SERIALISED[name]
    assert len(rows[0]) == len(fields), (
        f"{name} returns {len(rows[0])} columns and the route names "
        f"{len(fields)}: {fields}. zip() drops the difference silently, so "
        "the extra column would never reach the client. Name it in the "
        "FIELDS list for that route.")
