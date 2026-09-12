-- 016: mutual funds alongside equities, in the table that already holds one.
--
-- instruments was built for NSE symbols and the search seeded it with the
-- 2,292 ordinary equities. That leaves every mutual fund priced by hand --
-- which is most of what a personal portfolio in India actually holds, and
-- exactly the two holdings in the demo still carrying a typed-in number.
--
-- AMFI publishes a daily NAV for every scheme, and api.mfapi.in serves it
-- free, without a key and CORS-open, the same way NSE publishes the equity
-- list. So this needs no new dependency on anybody's deploy: 37,882 schemes
-- with a code, a name and an ISIN, and a NAV history per code.
--
-- One table, not two. A fund and an equity answer the same questions -- what
-- is this called, what is it worth, what did it close at -- and splitting
-- them would mean every search, every price write and every sparkline query
-- doing its work twice and then merging. The identifier column stays named
-- `ticker` and holds an NSE symbol for an equity and an AMFI scheme code for
-- a fund.
--
-- Checked before relying on it: no NSE equity ticker is purely numeric, no
-- AMFI code repeats, and the two sets do not intersect. So the values could
-- not collide even without a discriminator -- but `kind` is here anyway,
-- because "they happen not to collide today" is not a property NSE has
-- promised to preserve, and code that has to infer a namespace from the
-- shape of a string is code that will one day infer it wrongly.
ALTER TABLE instruments ADD COLUMN IF NOT EXISTS kind VARCHAR(8) NOT NULL DEFAULT 'equity';

ALTER TABLE instruments DROP CONSTRAINT IF EXISTS instruments_kind_known;
ALTER TABLE instruments ADD CONSTRAINT instruments_kind_known
    CHECK (kind IN ('equity', 'fund'));

-- The holding carries it too. The pricing job splits what it has to fetch
-- into the two feeds before it calls either, and reading the kind back out
-- of instruments per holding to do that would be a round trip for a fact
-- the row could simply have stated.
ALTER TABLE investments ADD COLUMN IF NOT EXISTS kind VARCHAR(8) NOT NULL DEFAULT 'equity';

ALTER TABLE investments DROP CONSTRAINT IF EXISTS investments_kind_known;
ALTER TABLE investments ADD CONSTRAINT investments_kind_known
    CHECK (kind IN ('equity', 'fund'));

-- A fund has a house and a category where an equity has a sector and an
-- exchange. Kept rather than derived: mfapi returns them beside the NAV, and
-- asking again per holding per page load is the same mistake 013 avoided.
ALTER TABLE instruments ADD COLUMN IF NOT EXISTS fund_house VARCHAR(120);

-- Searching 40,000 rows by name needs the trigram index 014 added to cover
-- it, and the ranking needs kind beside the rest so a search can prefer one
-- namespace without sorting the other.
CREATE INDEX IF NOT EXISTS instruments_kind_rank
    ON instruments (kind, priced DESC, listed_on, ticker);
