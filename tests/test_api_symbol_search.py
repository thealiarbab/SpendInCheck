"""Symbol autocomplete, served from our own instrument master.

The universe is seeded from NSE's published equity list rather than read
from StockSaathi's dhan_instruments, which is behind row level security
with no anon policy. So these tests seed a handful of rows directly and
assert on the ordering, which is the whole value of the feature: any query
can return RELIANCE, only a good one returns it first.
"""

import pytest

from server import db, operations


SEEDED = [
    # ticker, name, priced
    ("RELIANCE", "Reliance Industries Limited", True),
    ("RELIANCEPOWER", "Reliance Power Limited", False),
    ("RELINFRA", "Reliance Infrastructure Limited", False),
    ("TATAMOTORS", "Tata Motors Limited", False),
    ("TATASTEEL", "Tata Steel Limited", True),
    ("HEROMOTOCO", "Hero MotoCorp Limited", False),
]


@pytest.fixture
def seeded_instruments():
    """Put a few known rows in the shared instrument master, then remove them.

    instruments is deliberately not user-scoped -- the name of a company is
    a fact about the company -- so this cleans up after itself by ticker
    rather than relying on a user cascade.
    """
    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        for ticker, name, priced in SEEDED:
            cursor.execute(
                "INSERT INTO instruments (ticker, name, exchange, priced) "
                "VALUES (%s, %s, 'NSE', %s) "
                "ON CONFLICT (ticker) DO UPDATE "
                "   SET name = EXCLUDED.name, priced = EXCLUDED.priced",
                (ticker, name, priced))
        connection.commit()
    finally:
        db.close_connection(connection)

    yield [ticker for ticker, _, _ in SEEDED]

    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM instruments WHERE ticker = ANY(%s::varchar[])",
                       ([ticker for ticker, _, _ in SEEDED],))
        connection.commit()
    finally:
        db.close_connection(connection)


def search(client, term):
    response = client.get("/api/v1/symbols/search?q=" + term)
    assert response.status_code == 200, response.get_data(as_text=True)[:200]
    return [row["symbol"] for row in response.get_json()["items"]]


def test_a_ticker_prefix_suggests_the_symbol(api_account, seeded_instruments):
    """The fix this whole feature exists for: you should not have to already
    know the symbol in order to type it."""
    found = search(api_account["client"], "relianc")
    assert "RELIANCE" in found


def test_an_exact_ticker_comes_first(api_account, seeded_instruments):
    """Somebody who typed RELIANCE meant RELIANCE, and it must not sit under
    RELIANCEPOWER for being the shorter row."""
    assert search(api_account["client"], "RELIANCE")[0] == "RELIANCE"


def test_a_ticker_prefix_outranks_a_name_match(api_account, seeded_instruments):
    """A typed fragment is far more often the start of a ticker than the
    middle of a company name."""
    found = search(api_account["client"], "reli")
    assert found[0] == "RELIANCE"
    # RELINFRA matches on ticker too; the parent still leads on length.
    assert found.index("RELIANCE") < found.index("RELIANCEPOWER")


def test_a_company_name_is_searchable_too(api_account, seeded_instruments):
    """Nobody starts at the first word of a company name, so "motors" has to
    find TATAMOTORS even though the ticker does not begin with it."""
    assert "TATAMOTORS" in search(api_account["client"], "motors")


def test_the_search_is_case_insensitive(api_account, seeded_instruments):
    assert search(api_account["client"], "ReLiAnCe")[0] == "RELIANCE"


@pytest.mark.parametrize("term", ["", "r", " ", "  "])
def test_a_fragment_too_short_is_an_empty_list_not_an_error(api_account, term):
    """This runs on a keystroke. The first letter of every search is not a
    client error, and answering 422 would put a red message under a field
    somebody is still typing into."""
    response = api_account["client"].get("/api/v1/symbols/search?q=" + term)
    assert response.status_code == 200
    assert response.get_json()["items"] == []


def test_a_wildcard_is_matched_literally(api_account, seeded_instruments):
    """% and _ are wildcards to LIKE. Unescaped, "%" alone would return the
    whole instrument master two characters at a time."""
    assert search(api_account["client"], "%%") == []
    assert search(api_account["client"], "__") == []


def test_the_search_needs_an_account(client, seeded_instruments):
    """2,292 rows of instrument master is worth scraping, which is exactly
    why StockSaathi keeps theirs behind RLS. Ours is behind a session."""
    assert client.get("/api/v1/symbols/search?q=reliance").status_code == 401


def test_results_are_capped(api_account, seeded_instruments):
    """A list under a text box is a suggestion, not a directory."""
    found = search(api_account["client"], "li")
    assert len(found) <= 8


def test_a_symbol_with_a_price_outranks_one_merely_listed(api_account,
                                                          seeded_instruments):
    """Both match "ta"; TATASTEEL has been priced and TATAMOTORS has not."""
    found = [s for s in search(api_account["client"], "tata")]
    assert found.index("TATASTEEL") < found.index("TATAMOTORS")


def test_searching_directly_returns_the_columns_the_client_needs(
        seeded_instruments):
    """The hook's Suggestion type reads all five."""
    rows = operations.search_instruments("reliance", limit=1)
    assert len(rows) == 1
    ticker, name, exchange, sector, isin = rows[0]
    assert ticker == "RELIANCE"
    assert name == "Reliance Industries Limited"
    assert exchange == "NSE"
