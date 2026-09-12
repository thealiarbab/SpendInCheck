"""What things used to be worth.

quote_history is the one table here that is not user-scoped. A closing
price is a fact about the market, not about a person: twenty accounts
holding RELIANCE share one set of closes, and a copy each would be twenty
rows saying the same thing and twenty chances to disagree. Every function
below is therefore missing the user_id filter that every other operation
has, deliberately.

Nothing here is reachable without an account -- the endpoints that call it
still require one -- but what comes back is public information either way.
"""


from .. import db, vocabulary


def record_closes(ticker, closes):
    """Write daily closes for one symbol. Returns how many rows landed.

    `closes` is [(date, Decimal)]. Existing rows are left alone rather than
    overwritten: a close is final once the day is over, and a feed that
    revises one later is likelier to be having a bad day than to be right.
    The exception would be today's row, which is not a close until the
    market shuts -- see the DO UPDATE below.
    """
    rows = [(ticker, on_date, close) for on_date, close in (closes or [])
            if on_date is not None and close is not None]
    if not ticker or not rows:
        return 0

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        # unnest of three arrays rather than a row per statement: a year of
        # history is 250 rows, and 250 round trips to Mumbai is seven
        # seconds to write something nobody is waiting for.
        cursor.execute("""
            INSERT INTO quote_history (ticker, on_date, close)
            SELECT * FROM unnest(%s::varchar[], %s::date[], %s::numeric[])
            ON CONFLICT (ticker, on_date) DO UPDATE
                -- Only today's row is allowed to move. Yesterday's close
                -- is settled, and a feed revising it is more likely to be
                -- wrong than the record is.
                SET close = EXCLUDED.close
                WHERE quote_history.on_date >= CURRENT_DATE
        """, ([ticker] * len(rows),
              [on_date for _, on_date, _ in rows],
              [close for _, _, close in rows]))
        connection.commit()
        return cursor.rowcount
    finally:
        db.close_connection(connection)


def symbols_with_history():
    """Every symbol that already has at least one close recorded.

    The snapshot job asks this to decide what it is doing per symbol: a
    symbol it has never seen needs a year fetched, one it knows needs only
    the last few days. Without the distinction, either every run pulls a
    year for everything or a newly tracked holding charts as a flat line
    until a year has passed.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT DISTINCT ticker FROM quote_history")
        return {row[0] for row in cursor.fetchall()}
    finally:
        db.close_connection(connection)


def close_on(ticker, on_date):
    """The last close at or before this date, or None.

    Used by tests and by hand. The reports do this as a lateral join rather
    than by calling here per holding per month, which would be a round trip
    each.
    """
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT close FROM quote_history
             WHERE ticker = %s AND on_date <= %s
             ORDER BY on_date DESC LIMIT 1
        """, (ticker, on_date))
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        db.close_connection(connection)


def recent_closes(tickers, days=30):
    """Recent closes for several symbols at once, as {ticker: [(date, close)]}.

    One statement for the whole screen rather than one per holding: six
    holdings would otherwise be six round trips to Mumbai for a chart the
    width of a thumbnail.

    Oldest first per symbol, so a caller can draw it without sorting.
    """
    wanted = sorted({t for t in (tickers or []) if t})
    if not wanted:
        return {}

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT ticker, on_date, close
              FROM quote_history
             WHERE ticker = ANY(%s::varchar[])
               AND on_date > CURRENT_DATE - make_interval(days => %s)
             ORDER BY ticker, on_date
        """, (wanted, days))
        series = {}
        for ticker, on_date, close in cursor.fetchall():
            series.setdefault(ticker, []).append((on_date, close))
        return series
    finally:
        db.close_connection(connection)


def record_instrument(found):
    """Write down what a symbol is. Returns True when a row landed.

    `found` is what services.stocksaathi.instrument returns. Overwrites on
    conflict, unlike a close: a company's sector can be reclassified and
    its 52-week range moves every day, so the newest answer is the right
    one. That is the opposite rule from quote_history, and the difference
    is that one records what happened on a day and this records what is
    true now.
    """
    if not found or not found.get("symbol"):
        return False

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO instruments (ticker, name, sector, exchange,
                                     low_52w, high_52w, fund_house, priced)
            VALUES (%s, %s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (ticker) DO UPDATE
               SET name = COALESCE(EXCLUDED.name, instruments.name),
                   sector = COALESCE(EXCLUDED.sector, instruments.sector),
                   exchange = COALESCE(EXCLUDED.exchange, instruments.exchange),
                   -- COALESCE throughout so a partial answer tops up what
                   -- is known rather than blanking it. A feed that has
                   -- momentarily lost the sector should not erase it.
                   low_52w = COALESCE(EXCLUDED.low_52w, instruments.low_52w),
                   high_52w = COALESCE(EXCLUDED.high_52w, instruments.high_52w),
                   -- A fund has a house where a share has an exchange.
                   fund_house = COALESCE(EXCLUDED.fund_house, instruments.fund_house),
                   -- Never back to false. Reaching here means the feed
                   -- answered for this symbol, and a seeded row arriving
                   -- later must not un-confirm it. The search ranks on this.
                   priced = true,
                   updated_at = now()
        """, (found["symbol"], found.get("name"), found.get("sector"),
              found.get("exchange"), found.get("low_52w"),
              found.get("high_52w"), found.get("fund_house")))
        connection.commit()
        return True
    finally:
        db.close_connection(connection)


def search_instruments(term, limit=8, kind=None):
    """Symbols matching what somebody typed, best guess first.

    **People type phrases, not fragments, and they use the old names.** This
    matched the whole input as one substring, so "reliance shares" found
    nothing at all -- no company is called that -- while "reliance" found
    three. And "sbi bluechip" found the wrong SBI funds, because SEBI's 2018
    recategorisation renamed that scheme to SBI Large Cap and the words
    somebody types are not in the data any more.

    So the input becomes a list of *concepts* (server/vocabulary.py), each
    carrying every spelling worth matching -- "bluechip" brings "blue chip"
    and "large cap" with it -- and a row matching more concepts ranks
    higher. Matching any spelling counts the concept once, which is what
    keeps that honest: offering three spellings of one word must not
    outrank a row that genuinely matched three different words.

    Trigram similarity is the backstop for what neither splitting nor the
    dictionary catches, which is mostly typos.

    The ordering, in order:

      an exact ticker  somebody who typed RELIANCE meant RELIANCE, and it
                       must not sit under RELIANCEPOWER for being shorter
      a ticker prefix  before any name match, because a typed fragment is
                       far more often the start of a ticker than the middle
                       of a company name
      concepts matched two ideas of two beats one of two
      a name prefix    "sbi large" means the SBI Large Cap Fund, not some
                       other house's fund with those words in the middle.
                       This matters far more for funds than for shares:
                       13,969 schemes share most of their words
      priced           a symbol this app has actually fetched a price for
                       is a better suggestion than one merely listed
      similarity       banded, not ordered -- see the comment below
      growth, direct   every scheme exists as four near-identical rows, and
                       a list that leads with the payout variant answers a
                       question nobody asked
      listed longest   RELIANCE (1995) above RELIABLE (2024), both eight
                       characters. NULLS LAST, so an undated row does not
                       outrank the exchange
      the shortest     RELIANCE above RELIANCEPOWER

    LIKE, not ILIKE, on the ticker: tickers are stored upper case and the
    term is folded before it gets here, so this stays on the prefix index
    that migration 014 adds. ILIKE would not use it.
    """
    raw = (term or "").strip()
    if len(raw) < 2:
        return []

    def escape(value):
        # %% and _ are wildcards to LIKE, so a term containing one would
        # quietly match far more than it looks like it should. Escaped
        # rather than stripped, because a name legitimately contains "&"
        # and friends and this should not start editing what somebody typed.
        return (value.replace(chr(92), chr(92) * 2)
                     .replace("%", chr(92) + "%").replace("_", chr(92) + "_"))

    fragment = raw.upper()
    safe = escape(fragment)

    params = {"kind": kind, "prefix": safe + "%", "upper": fragment,
              "raw": raw, "limit": limit}

    # One bracketed OR per concept, spelled out rather than looped over
    # inside SQL: an OR of plain ILIKEs uses the GIN trigram index on name,
    # where a lateral over unnest() does not. Measured at 172ms against
    # 24ms on 18,489 rows.
    groups = []
    for n, spellings in enumerate(vocabulary.concepts(raw)):
        parts = []
        for m, spelling in enumerate(spellings):
            key = "c%d_%d" % (n, m)
            params[key] = escape(spelling)
            parts.append("name ILIKE '%%' || %(" + key + ")s || '%%' ESCAPE '\\'")
        groups.append("(" + " OR ".join(parts) + ")")

    matches = " OR ".join(groups) or "false"
    # Counted per concept, not per spelling.
    # "0::int" rather than "0": a bare integer constant in ORDER BY is read
    # as a column position, so the empty case asked to sort by column zero.
    matched = " + ".join("(" + g + ")::int" for g in groups) or "0::int"

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT ticker, name, exchange, sector, isin, kind
              FROM instruments
             WHERE (%(kind)s::varchar IS NULL OR kind = %(kind)s)
               AND (ticker LIKE %(prefix)s ESCAPE '\\'
                    OR """ + matches + """
                    OR name %% %(raw)s)
             ORDER BY (ticker = %(upper)s) DESC,
                      (ticker LIKE %(prefix)s ESCAPE '\\') DESC,
                      (""" + matched + """) DESC,
                      (name ILIKE %(prefix)s ESCAPE '\\') DESC,
                      priced DESC,
                      -- Rounded, so it bands rather than orders. The four
                      -- variants of one scheme differ by hundredths --
                      -- 0.3250 against 0.3333 for the same query -- and at
                      -- full precision that noise decided the winner,
                      -- putting the payout variant above the growth one.
                      -- Banded, they tie and the two rules below decide.
                      round(similarity(name, %(raw)s)::numeric, 1) DESC,
                      (name ILIKE '%%IDCW%%' OR name ILIKE '%%DIVIDEND%%'),
                      (name NOT ILIKE '%%DIRECT%%'),
                      listed_on ASC NULLS LAST,
                      length(ticker),
                      ticker
             LIMIT %(limit)s
        """, params)
        return cursor.fetchall()
    finally:
        db.close_connection(connection)


def instruments_for(tickers):
    """What these symbols are, as {ticker: row}. One statement, not one each."""
    wanted = sorted({t for t in (tickers or []) if t})
    if not wanted:
        return {}

    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT ticker, name, sector, exchange, low_52w, high_52w,
                   kind, fund_house
              FROM instruments
             WHERE ticker = ANY(%s::varchar[])
        """, (wanted,))
        return {row[0]: {"symbol": row[0], "name": row[1], "sector": row[2],
                         "exchange": row[3], "low_52w": row[4],
                         "high_52w": row[5], "kind": row[6],
                         "fund_house": row[7]}
                for row in cursor.fetchall()}
    finally:
        db.close_connection(connection)


# The instrument the portfolio is measured against.
#
# Not the NIFTY 50 index, because the upstream cannot quote it: NIFTY and
# ^NSEI both return null, and NIFTY50 returns some unrelated instrument at
# around 8,095 that would draw a confident wrong line. This is the Nippon
# India ETF that tracks the same index, it quotes, it has a full year of
# daily closes, and every screen showing it says so rather than calling it
# "the NIFTY".
BENCHMARK = "NIFTYBEES"


def basket_against_benchmark(user_id, months=12, benchmark=None):
    """What this account's holdings did, beside what the market did.

    Returns (month, basket_value, benchmark_close) oldest first, with
    months left out unless BOTH sides can be valued in full: the benchmark
    needs a close, and so does every one of the holdings. A month in which
    only part of the basket had a price is not a cheaper answer, it is a
    different basket -- see the HAVING below.

    The basket is valued at **today's quantities** throughout, which is the
    whole point and the thing that is easy to get wrong. Charting the
    portfolio's actual value against an index compares two different
    things: buying more of something raises the value without the market
    having moved at all, so a month of heavy saving looks like a month of
    spectacular returns. Holding the quantities constant isolates what the
    prices did, which is the only part a benchmark can fairly answer.

    Only holdings with a ticker take part. A deposit has no market return
    to compare, and including it at a flat price would quietly drag the
    line toward zero movement.

    `benchmark` resolves at call time rather than defaulting in the
    signature, so a test can substitute a synthetic symbol. That is not
    tidiness: NIFTYBEES is a real symbol whose history every account's
    chart reads, and a test that cleaned up after itself by deleting it
    wiped the chart for everybody until the next nightly run. It did
    exactly that once.
    """
    benchmark = benchmark or BENCHMARK
    connection = None
    try:
        connection = db.get_connection()
        cursor = connection.cursor()
        cursor.execute("""
            WITH calendar AS (
                SELECT generate_series(
                    date_trunc('month', CURRENT_DATE)
                        - make_interval(months => %s),
                    date_trunc('month', CURRENT_DATE),
                    interval '1 month') AS month_start
            ),
            -- The closing price for one symbol at one month end, used for
            -- both sides so they cannot be measured differently.
            basket AS (
                SELECT c.month_start,
                       SUM(past.close * i.quantity) AS value
                  FROM calendar c
                  JOIN investments i
                    ON i.user_id = %s AND i.ticker IS NOT NULL
                  JOIN LATERAL (
                      SELECT q.close FROM quote_history q
                       WHERE q.ticker = i.ticker
                         AND q.on_date < c.month_start + interval '1 month'
                       ORDER BY q.on_date DESC LIMIT 1
                  ) past ON TRUE
                 GROUP BY c.month_start
                -- Every holding, or the month does not count.
                --
                -- The lateral above is an inner join, so a holding with no
                -- close before this month drops out of it -- while the
                -- month itself survives on the strength of the others. The
                -- basket then changes membership partway along the chart,
                -- and the month a late-listed holding gains a history, its
                -- whole value arrives at once and reads as a market gain.
                -- Measured on a flat pair: 1000, 1000, 2000, with neither
                -- price having moved at all.
                --
                -- So a month is charted only when the entire basket can be
                -- valued in it. The series starts later for an account
                -- holding something recently listed, which is the honest
                -- answer: there is no comparison to draw for a month in
                -- which half the basket did not yet exist.
                HAVING COUNT(*) = (
                    SELECT COUNT(*) FROM investments
                     WHERE user_id = %s AND ticker IS NOT NULL)
            ),
            market AS (
                SELECT c.month_start, past.close
                  FROM calendar c
                  JOIN LATERAL (
                      SELECT q.close FROM quote_history q
                       WHERE q.ticker = %s
                         AND q.on_date < c.month_start + interval '1 month'
                       ORDER BY q.on_date DESC LIMIT 1
                  ) past ON TRUE
            )
            SELECT to_char(basket.month_start, 'YYYY-MM'),
                   basket.value, market.close
              FROM basket JOIN market ON market.month_start = basket.month_start
             ORDER BY basket.month_start
        """, (months - 1, user_id, user_id, benchmark))
        return cursor.fetchall()
    finally:
        db.close_connection(connection)
