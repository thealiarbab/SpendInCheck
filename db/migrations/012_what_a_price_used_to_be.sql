-- 012: remember what things used to be worth.
--
-- Net worth over time is currently a lie of omission. The chart values
-- every holding at today's price in every month it existed, because that is
-- the only price this database has -- so a stock bought at 1,200 and now
-- worth 2,400 makes the whole of last year look like it was worth 2,400.
-- The line describes the portfolio's *composition* changing, and nothing
-- about the market.
--
-- One table fixes that, and it is the one piece of this that cannot be
-- bought later: a close that was not recorded on the day is gone. The
-- upstream serves a year of history, so the first months come free, but
-- everything after today only exists if something writes it down tonight.

-- A price is a fact about the market, not about a person. This table is
-- therefore NOT user-scoped, and that is deliberate rather than an
-- oversight -- it will read as a missing user_id to the next person who
-- sees it. Twenty accounts holding RELIANCE share one set of closes, and
-- storing a copy each would be twenty rows saying the same thing and
-- twenty chances for them to disagree.
CREATE TABLE IF NOT EXISTS quote_history (
    ticker   VARCHAR(32)    NOT NULL,
    on_date  DATE           NOT NULL,
    close    NUMERIC(14,3)  NOT NULL,
    -- Which feed said so. Kept because a price nobody can attribute is a
    -- price nobody can check, and this table is the input to a chart people
    -- will make decisions from.
    source   VARCHAR(16)    NOT NULL DEFAULT 'stocksaathi',
    PRIMARY KEY (ticker, on_date)
);

-- The primary key is already (ticker, on_date), which serves the only
-- question this table is ever asked: "what did X close at, on or before
-- date D". DESC is not needed -- Postgres reads a btree backwards just as
-- cheaply -- so there is deliberately no second index here.

-- Nothing reaches this table except through the application, which connects
-- as postgres. Migration 010 revoked every grant from anon and
-- authenticated and set default privileges so new tables do not reopen the
-- door; RLS here is the second lock, matching every other table.
ALTER TABLE quote_history ENABLE ROW LEVEL SECURITY;

-- --- why there is no quote_cache ---------------------------------------------
--
-- The plan called for a quote_cache table beside this one. It is not here,
-- on purpose. A current price already has two homes: StockSaathi caches
-- each symbol upstream and serves one copy to everybody, and this
-- application stores the figure it last accepted on investments.current_price.
-- A third copy would be a cache of a cache, with its own staleness rules,
-- sitting in the path of a request that a person is waiting on.
--
-- quote_history earns its place because it answers a question nothing else
-- can: what was this worth in March. A cache only answers what it is worth
-- now, which two other things already know.
