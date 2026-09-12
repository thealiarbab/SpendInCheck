-- 014: enough of an instrument master to autocomplete against.
--
-- instruments (013) already holds what a symbol is, but only for symbols
-- somebody here already tracks -- the nightly job writes a row the first
-- time a holding points at one. That is exactly backwards for a search
-- box: the table is empty at the moment somebody needs to be told that
-- RELIANCE exists, and full only of the symbols they could already name.
--
-- So the table is seeded with the NSE equity list, from NSE's own public
-- archive, by scripts/sync_instruments.py. The alternative was reading
-- StockSaathi's dhan_instruments, which is behind row level security with
-- no anon policy -- correct of them, and not ours to open. Taking the list
-- from the exchange itself means this app owns its own universe and does
-- not wait on another product's deploy.
--
-- A seeded row carries a ticker, a name, an exchange and an ISIN, and
-- nothing else. Sector and the 52-week range stay null until the nightly
-- job fetches the real ones, which is why record_instrument COALESCEs
-- every column rather than overwriting: a seed must never be able to blank
-- a figure the feed has already answered.

ALTER TABLE instruments ADD COLUMN IF NOT EXISTS isin VARCHAR(12);

-- Where the row came from. A seeded row is a name and a ticker; a priced
-- row has been confirmed against a live quote. The search prefers the
-- second, because a symbol somebody here already holds is a better guess
-- than one merely listed.
ALTER TABLE instruments ADD COLUMN IF NOT EXISTS priced BOOLEAN NOT NULL DEFAULT false;

-- Matching a ticker is a prefix question: "reli" should find RELIANCE, and
-- nobody types the middle of a ticker. text_pattern_ops is what lets
-- LIKE 'RELI%' use an index at all -- the default opclass cannot serve it.
CREATE INDEX IF NOT EXISTS instruments_ticker_prefix
    ON instruments (ticker text_pattern_ops);

-- Matching a name is a substring question: "motors" should find TATAMOTORS
-- and somebody typing a company name rarely starts at its first word. That
-- needs trigrams, and pg_trgm may not be grantable on a pooled connection
-- -- 001 already handles that case, so this follows the same shape: index
-- it if the extension is there, carry on without it if not. Without the
-- index the search still answers, it just scans 2,500 rows to do it, which
-- is a table small enough to survive that.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS instruments_name_trgm
            ON instruments USING gin (name gin_trgm_ops);
    ELSE
        RAISE NOTICE 'pg_trgm not enabled; instrument name search will scan';
    END IF;
END $$;
