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
