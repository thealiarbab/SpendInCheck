-- 013: what a symbol is, kept rather than asked for every time.
--
-- The pricing work can already answer "whose symbol is this" -- the
-- instrument lookup returns the company's name, its sector, its exchange
-- and its 52-week range. It is only ever asked at the moment somebody
-- saves a symbol, and the answer is thrown away immediately afterwards,
-- because the endpoint takes up to three seconds cold and asking it once
-- per holding per page load is not a thing a screen can do.
--
-- So the nightly job, which already visits every tracked symbol, writes
-- the answer down here instead.
--
-- Like quote_history, this is NOT user-scoped, and for the same reason:
-- the name of a company is a fact about the company. Twenty accounts
-- holding RELIANCE share one row.
CREATE TABLE IF NOT EXISTS instruments (
    ticker      VARCHAR(32)  PRIMARY KEY,
    name        VARCHAR(200),
    sector      VARCHAR(100),
    exchange    VARCHAR(8),
    -- The 52-week range, as the upstream reports it. Nullable throughout:
    -- a symbol can be quotable while the richer endpoint knows nothing
    -- about it, and half an answer beats refusing to record any of it.
    low_52w     NUMERIC(14,3),
    high_52w    NUMERIC(14,3),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Not derived from quote_history, though it could be. A 52-week range
-- taken from daily *closes* is narrower than the real one, which is drawn
-- from intraday highs and lows -- so deriving it would produce a figure
-- that looks authoritative, is always slightly wrong, and disagrees with
-- every other site showing the same stock. The upstream already computes
-- the real one; this stores that.

ALTER TABLE instruments ENABLE ROW LEVEL SECURITY;
