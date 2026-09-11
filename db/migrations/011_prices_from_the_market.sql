-- 011: give a holding a ticker, so its price can come from the market.
--
-- Today every holding's current_price is typed in by hand and then rots:
-- the portfolio is worth whatever somebody last remembered to update. This
-- is the column that lets a price arrive on its own.
--
-- The shape of this is deliberately small. current_price stays exactly what
-- it was -- the one number every report and every P&L reads -- and nothing
-- about how it is *used* changes. What changes is that it can now be
-- *written* by the price path instead of only by a person. A second column
-- holding "the live price" beside it would mean every report choosing
-- between two numbers, and reports that chose differently.

-- The symbol as StockSaathi's API wants it: bare uppercase for NSE
-- (RELIANCE), .BO-suffixed for BSE-only. Nullable, and that is the whole
-- design of the opt-in: a fixed deposit has no ticker and never will, and
-- somebody tracking an unlisted holding by hand is not doing it wrong.
ALTER TABLE investments ADD COLUMN IF NOT EXISTS ticker VARCHAR(32);

-- Which exchange the symbol belongs to. Stored rather than inferred from
-- the suffix, because "no suffix" means NSE by convention and a convention
-- is a bad place to keep a fact.
ALTER TABLE investments ADD COLUMN IF NOT EXISTS exchange VARCHAR(8);

-- The instrument's ISIN, when the symbol was chosen from a real instrument
-- rather than typed. Not used for pricing -- it is here because it is the
-- only identifier that survives a ticker being reassigned, which is how a
-- holding silently starts tracking a different company.
ALTER TABLE investments ADD COLUMN IF NOT EXISTS isin CHAR(12);

-- Per-holding consent to overwrite current_price. Off by default, so this
-- migration cannot change a single number anybody is looking at: every
-- existing holding keeps the price its owner typed until they ask for
-- something else.
ALTER TABLE investments ADD COLUMN IF NOT EXISTS auto_price BOOLEAN NOT NULL
    DEFAULT false;

-- Where current_price last came from, and when. Without these a stale
-- automatic price is indistinguishable from a fresh one, and a price the
-- owner typed is indistinguishable from one the market sent -- which
-- matters the first time a number looks wrong and somebody has to work out
-- whether to blame the feed or their own typing.
ALTER TABLE investments ADD COLUMN IF NOT EXISTS price_source VARCHAR(16)
    NOT NULL DEFAULT 'manual';
ALTER TABLE investments ADD COLUMN IF NOT EXISTS price_updated_at TIMESTAMPTZ;

-- --- the two rules that keep the column honest -------------------------------

DO $$
BEGIN
    -- Automatic pricing without a symbol is a holding that has asked to be
    -- updated from nothing. Better to refuse it here than to have the
    -- refresh skip it every night in silence.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'auto_price_needs_a_ticker') THEN
        ALTER TABLE investments ADD CONSTRAINT auto_price_needs_a_ticker
            CHECK (NOT auto_price OR ticker IS NOT NULL);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'price_source_is_known') THEN
        ALTER TABLE investments ADD CONSTRAINT price_source_is_known
            CHECK (price_source IN ('manual', 'stocksaathi'));
    END IF;
END $$;

-- --- what the refresh will read ----------------------------------------------
--
-- The nightly snapshot asks one question: which symbols does anybody hold
-- automatically? That is a question about the whole table, not about one
-- user, so it is the one index here that is deliberately not user-scoped.
-- Partial, because the answer is a small subset of a table that is mostly
-- deposits and hand-priced holdings.
CREATE INDEX IF NOT EXISTS idx_investments_auto_priced
    ON investments (ticker) WHERE auto_price;
