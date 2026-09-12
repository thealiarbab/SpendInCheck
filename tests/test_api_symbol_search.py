"""Symbol autocomplete, served from our own instrument master.

The universe is seeded from NSE's published equity list rather than read
from StockSaathi's dhan_instruments, which is behind row level security
with no anon policy. These tests seed a handful of rows directly and assert
on the ordering, which is where the whole value of the feature is: any
query can return the right symbol, only a good one returns it first.

**Every ticker here is synthetic, and that is not fastidiousness.**
`instruments` is shared -- the name of a company is a fact about the
company, not about a user -- so a test cannot clean up by deleting its own
account and has to delete rows by ticker instead. The first version of this
file used RELIANCE, RELIABLE and TATAMOTORS, and its teardown deleted them
from the real instrument master that scripts/sync_instruments.py had seeded
from NSE. Typing "reli" on the live site stopped offering Reliance
Industries, and stayed that way until somebody re-ran the seed.

test_quote_history.py carries the same warning for the same reason, and
f4898a3 fixed exactly this bug in the benchmark tests. It is an easy
mistake to make twice.

The synthetic shapes still encode the real cases. ZZTESTAB and ZZTESTCO are
the same length and the first sorts before the second, which is the
RELIABLE-versus-RELIANCE trap: nothing but the listing date separates them.
"""

import pytest

from server import db, operations


# Synthetic throughout. No exchange lists a ZZ ticker, so nothing outside
# these tests can be reading one.
SEEDED = [
    # ticker, name, priced, listed_on
    ("ZZTESTCO", "Zztest Industries Limited", True, "1995-11-29"),
    ("ZZTESTCOPOWER", "Zztest Power Limited", False, "2008-02-11"),
    # Listed three months before ZZTESTCO, and unpriced: the row that proves
    # `priced` outranks the listing date.
    ("ZZTESTIN", "Zztest Infrastructure Limited", False, "1995-08-09"),
    # Same length as ZZTESTCO, sorts before it, listed thirty years later.
    ("ZZTESTAB", "Zztestab Data Services Limited", False, "2024-07-10"),
    ("ZZMOTORCO", "Zzmotor Vehicles Limited", False, "1998-07-22"),
    ("ZZMOTORST", "Zzmotor Steel Limited", True, "1998-11-18"),
]


@pytest.fixture
def seeded_instruments():
    """Put the synthetic rows in the shared master, then remove them."""
    tickers = [ticker for ticker, _, _, _ in SEEDED]

    def wipe():
        connection = db.get_connection()
        try:
            cursor = connection.cursor()
            cursor.execute(
                "DELETE FROM instruments WHERE ticker = ANY(%s::varchar[])",
                (tickers,))
            connection.commit()
        finally:
            db.close_connection(connection)

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

    yield tickers
    wipe()


def search(client, term):
    response = client.get("/api/v1/symbols/search?q=" + term)
    assert response.status_code == 200, response.get_data(as_text=True)[:200]
    return [row["symbol"] for row in response.get_json()["items"]]


def test_a_ticker_prefix_suggests_the_symbol(api_account, seeded_instruments):
    """The fix this whole feature exists for: you should not have to already
    know the symbol in order to type it."""
    assert "ZZTESTCO" in search(api_account["client"], "zztestc")


def test_an_exact_ticker_comes_first(api_account, seeded_instruments):
    """Somebody who typed the whole ticker meant that ticker, and it must not
    sit under a longer one that merely starts the same way."""
    assert search(api_account["client"], "ZZTESTCO")[0] == "ZZTESTCO"


def test_a_ticker_prefix_outranks_a_longer_one(api_account, seeded_instruments):
    """The parent, not the subsidiary: shorter wins once everything else ties."""
    found = search(api_account["client"], "zztest")
    assert found[0] == "ZZTESTCO"
    assert found.index("ZZTESTCO") < found.index("ZZTESTCOPOWER")


def test_a_company_name_is_searchable_too(api_account, seeded_instruments):
    """Nobody starts at the first word of a company name, so a word from the
    middle of it has to find the ticker that does not begin with it."""
    assert "ZZMOTORCO" in search(api_account["client"], "vehicles")


def test_the_search_is_case_insensitive(api_account, seeded_instruments):
    assert search(api_account["client"], "ZzTeStCo")[0] == "ZZTESTCO"


@pytest.mark.parametrize("term", ["", "r", " ", "  "])
def test_a_fragment_too_short_is_an_empty_list_not_an_error(api_account, term):
    """This runs on a keystroke. The first letter of every search is not a
    client error, and answering 422 would put a red message under a field
    somebody is still typing into."""
    response = api_account["client"].get("/api/v1/symbols/search?q=" + term)
    assert response.status_code == 200
    assert response.get_json()["items"] == []


def test_a_wildcard_is_matched_literally(api_account, seeded_instruments):
    """% and _ are wildcards to LIKE. Unescaped, "%%" alone would hand back
    the whole instrument master two characters at a time."""
    assert search(api_account["client"], "%%") == []
    assert search(api_account["client"], "__") == []


def test_the_search_needs_an_account(client, seeded_instruments):
    """Two thousand rows of instrument master is worth scraping, which is
    exactly why StockSaathi keeps theirs behind RLS. Ours is behind a
    session."""
    assert client.get("/api/v1/symbols/search?q=zztestco").status_code == 401


def test_results_are_capped(api_account, seeded_instruments):
    """A list under a text box is a suggestion, not a directory."""
    assert len(search(api_account["client"], "zz")) <= 8


def test_a_symbol_with_a_price_outranks_one_merely_listed(api_account,
                                                          seeded_instruments):
    """Both match; one has been priced by this app and the other has not."""
    found = search(api_account["client"], "zzmotor")
    assert found.index("ZZMOTORST") < found.index("ZZMOTORCO")


def test_the_longer_listed_company_wins_a_tie(api_account, seeded_instruments):
    """The bug the live data found the moment the seed landed.

    ZZTESTCO and ZZTESTAB stand in for RELIANCE and RELIABLE: both eight
    characters, so "shortest wins" separates them not at all, and the
    alphabet put the 2024 listing above the 1995 one. Correct by the rules
    as they were written, and wrong by any reading of what was wanted.
    """
    found = search(api_account["client"], "zztest")
    assert found[0] == "ZZTESTCO"
    assert found.index("ZZTESTCO") < found.index("ZZTESTAB")


def test_a_price_still_beats_a_longer_listing(api_account, seeded_instruments):
    """What keeps the proxy honest.

    ZZTESTIN listed three months before ZZTESTCO, so on listing date alone
    it would lead. ZZTESTCO is priced and it does not -- a symbol this app
    actually tracks beats any guess about which company is bigger.
    """
    found = search(api_account["client"], "zztest")
    assert found.index("ZZTESTCO") < found.index("ZZTESTIN")


def test_searching_directly_returns_the_columns_the_client_needs(
        seeded_instruments):
    """The hook's Suggestion type reads all five."""
    rows = operations.search_instruments("zztestco", limit=1)
    assert len(rows) == 1
    ticker, name, exchange, sector, isin = rows[0]
    assert ticker == "ZZTESTCO"
    assert name == "Zztest Industries Limited"
    assert exchange == "NSE"
