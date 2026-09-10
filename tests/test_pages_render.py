"""Every Jinja page still renders.

These exist because one of them stopped. When portfolio_pnl gained two
columns in Phase 6 the dashboard template kept unpacking the old seven and
raised on every render, and nothing noticed -- the API tests covered the
query, and no test had ever asked for the page.

They are deliberately shallow. The pages are being replaced in Phase 8, so
the only thing worth asserting is that they answer at all: a template that
unpacks the wrong number of columns fails at render, which is exactly what a
200 rules out.
"""

import pytest

from server import operations

# The pages that render rows, which is where a wrong column count shows up.
# POST-only routes are left out: they are actions, not pages.
DATA_PAGES = ["/dashboard", "/transactions", "/categories", "/budgets",
              "/investments", "/reports"]

# The landing page has neither a table nor a form -- it is two links -- so it
# is rendered but not asked to prove it drew anything.
PAGES = ["/"] + DATA_PAGES


@pytest.fixture
def demo_page_client(client):
    """A client signed into a throwaway demo account, with data in it.

    The demo seed is what makes this worth running: empty tables would
    render every loop zero times and prove nothing about the row shapes.
    """
    token = client.get("/api/v1/auth/session").get_json()["csrf_token"]
    body = client.post("/api/v1/auth/demo",
                       headers={"X-CSRF-Token": token}).get_json()
    yield client
    operations.delete_demo_user(body["user"]["id"])


@pytest.mark.parametrize("path", PAGES)
def test_the_page_renders(demo_page_client, path):
    response = demo_page_client.get(path)
    assert response.status_code == 200, path
    # The closing tag, so a template that stopped part way through is not
    # mistaken for one that finished.
    assert b"</html>" in response.data, path


@pytest.mark.parametrize("path", DATA_PAGES)
def test_the_page_actually_drew_something(demo_page_client, path):
    """A loop unpacking the wrong number of columns raises rather than
    drawing nothing, but an empty page would hide a query that quietly
    stopped returning rows."""
    response = demo_page_client.get(path)
    assert b"<table" in response.data or b"<form" in response.data, \
        f"{path} rendered but looks empty"


def test_the_ledger_page_shows_which_account_a_row_is_on(demo_page_client):
    """The column the accounts work added. Checked here rather than left to
    the eye, since this template is the one that has already drifted."""
    body = demo_page_client.get("/transactions").get_data(as_text=True)
    assert "<th>Account</th>" in body
    assert "Current" in body and "Cash" in body


def test_a_signed_out_visitor_is_sent_to_the_front(client):
    for path in ("/dashboard", "/transactions", "/reports"):
        response = client.get(path)
        assert response.status_code in (302, 303), path


# --- the shape the templates unpack ------------------------------------------
#
# Three templates have now broken the same way: an operation grew a column,
# the template kept unpacking the old count, and the page raised on every
# render. The parametrised tests above catch it, but only after somebody
# runs them and only by rendering a whole page. These say the same thing
# directly, so a change to a query fails against the number it changed.

EXPECTED_COLUMNS = {
    # operation                     columns  what the last change added
    "get_all_transactions": (9, "tags, carried with the row"),
    "get_all_budgets": (7, "rollover, rollover_in and category_id"),
    "portfolio_pnl": (9, "investment_id and buy_date"),
    "get_all_categories": (3, ""),
    "list_accounts": (7, ""),
    "list_rules": (14, ""),
}


@pytest.mark.parametrize("name", sorted(EXPECTED_COLUMNS))
def test_the_row_shape_is_what_the_templates_unpack(demo_page_client, name):
    """Fails when a query gains or loses a column.

    Deliberately brittle: that is the point. A template unpacking a tuple
    has no way to notice a column arriving, so this is where the noticing
    happens. When it fails, update the count here and the templates that
    unpack it -- the failure is the reminder that they exist.
    """
    user_id = demo_page_client.get("/api/v1/auth/session").get_json()["user"]["id"]
    rows = getattr(operations, name)(user_id)
    assert rows, f"{name} returned nothing; the demo seed should have rows"

    expected, added = EXPECTED_COLUMNS[name]
    assert len(rows[0]) == expected, (
        f"{name} now returns {len(rows[0])} columns, not {expected}"
        + (f" (last change added {added})" if added else "")
        + ". Update the Jinja templates that unpack it, then this count.")
