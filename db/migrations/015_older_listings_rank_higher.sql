-- 015: how long a company has been listed, so the search can rank on it.
--
-- 014 gave the search a universe. Using it immediately showed the ranking
-- was not good enough: typing "reli" suggested RELIABLE before RELIANCE.
--
-- Both tickers are eight characters, so the "shortest wins" tiebreak had
-- nothing to separate them and alphabetical order decided it -- putting
-- Reliable Data Services Limited, listed in 2024, above Reliance
-- Industries, listed in 1995. Correct by the rules as written, and wrong
-- by any reading of what somebody typing "reli" wants.
--
-- What was missing is any notion of which company is the bigger one. This
-- app has no market capitalisation and should not acquire one for a search
-- box. But NSE's list carries the date of listing, and it is already being
-- downloaded: a company still trading thirty years after it listed is
-- established, and one that listed last year is not. It is a proxy rather
-- than a measure, and it is honest about being one.
--
-- Ranked below `priced`, deliberately. A symbol somebody here actually
-- holds beats any guess about prominence, so a recently listed company
-- that this app tracks still rises above an old one it has never priced --
-- which is the case the proxy would otherwise get wrong.
ALTER TABLE instruments ADD COLUMN IF NOT EXISTS listed_on DATE;

-- The ordering reads (prefix match, priced, listed_on, length), and the
-- first two are already served. This covers the tail so a two-letter
-- fragment matching several hundred rows does not sort them all.
CREATE INDEX IF NOT EXISTS instruments_rank
    ON instruments (priced DESC, listed_on, ticker);
