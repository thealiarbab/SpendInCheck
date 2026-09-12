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
    # ticker, name, priced, listed_on
    ("RELIANCE", "Reliance Industries Limited", True, "1995-11-29"),
    ("RELIANCEPOWER", "Reliance Power Limited", False, "2008-02-11"),
    ("RELINFRA", "Reliance Infrastructure Limited", False, "1995-08-09"),
    # Same length as RELIANCE, alphabetically before it, and listed thirty
    # years later. This row is the whole reason listed_on is in the ORDER BY.
    ("RELIABLE", "Reliable Data Services Limited", False, "2024-07-10"),
    ("TATAMOTORS", "Tata Motors Limited", False, "1998-07-22"),
    ("TATASTEEL", "Tata Steel Limited", True, "1998-11-18"),
    ("HEROMOTOCO", "Hero MotoCorp Limited", False, "2003-01-01"),
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
        for ticker, name, priced, listed in SEEDED:
            cursor.execute(
                "INSERT INTO instruments (ticker, name, exchange, priced, listed_on) "
                "VALUES (%s, %s, 'NSE', %s, %s) "
                "ON CONFLICT (ticker) DO UPDATE "
                "   SET name = EXCLUDED.name, priced = EXCLUDED.priced, "
                "       listed_on = EXCLUDED.listed_on",
                (ticker, name, priced, listed))
        connection.commit()
    finally:
        db.close_connection(connection)

    yield [ticker for ticker, _, _, _ in SEEDED]

    connection = db.get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("DELETE FROM instruments WHERE ticker = ANY(%s::varchar[])",
                       ([ticker for ticker, _, _, _ in SEEDED],))
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


def test_the_longer_listed_company_wins_a_tie(api_account, seeded_instruments):
    """The bug the live data found the moment the seed landed.

    RELIANCE and RELIABLE are both eight characters, so "shortest wins"
    separates them not at all, and the alphabet put Reliable Data Services
    Limited -- listed 2024 -- above Reliance Industries. Correct by the
    rules as they were written, and wrong by any reading of what somebody
    typing "reli" wants.

    How long a company has been listed is the tiebreak: a proxy for size
    rather than a measure of it, but an honest one, and the only such
    signal already in the file this app downloads.
    """
    found = search(api_account["client"], "reli")
    assert found[0] == "RELIANCE"
    assert found.index("RELIANCE") < found.index("RELIABLE")


def test_a_price_still_beats_a_longer_listing(api_account, seeded_instruments):
    """The ordering that keeps the proxy honest.

    RELINFRA listed in August 1995, three months before RELIANCE, so on
    listing date alone it would lead. RELIANCE is priced and it does not --
    because a symbol this app actually tracks is a better suggestion than
    any guess about which company is bigger.
    """
    found = search(api_account["client"], "reli")
    assert found.index("RELIANCE") < found.index("RELINFRA")


def test_searching_directly_returns_the_columns_the_client_needs(
        seeded_instruments):
    """The hook's Suggestion type reads all five."""
    rows = operations.search_instruments("reliance", limit=1)
    assert len(rows) == 1
    ticker, name, exchange, sector, isin = rows[0]
    assert ticker == "RELIANCE"
    assert name == "Reliance Industries Limited"
    assert exchange == "NSE"
