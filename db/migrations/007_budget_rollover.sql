-- 007: budget rollover.
--
-- Without rollover, a budget is a monthly amnesty: underspend 3,000 in June
-- and it evaporates; overspend 3,000 and July starts clean as though it
-- never happened. Neither matches how anybody actually thinks about a
-- limit they set themselves.
--
-- With rollover on, what was left over (or overspent) at the end of a month
-- is carried into the next one's allowance.

ALTER TABLE budgets ADD COLUMN IF NOT EXISTS rollover BOOLEAN NOT NULL
    DEFAULT false;

-- What was carried in from the previous month, materialised on write.
--
-- This is the important decision in this migration. Rollover is recursive
-- by nature -- June's carry-in depends on May's, which depends on April's
-- -- so deriving it at read time means walking back through every month a
-- category has ever had a budget for, on every report. That is O(months)
-- per category per page, and it grows forever.
--
-- Storing it makes a read O(1). The cost is that it has to be recomputed
-- whenever anything upstream changes: a budget edited, or a transaction
-- added, moved or deleted in a category that has one. The application owns
-- that, and the recompute rebuilds the whole of one category's history in a
-- single recursive statement -- still O(months), but paid once per write
-- rather than on every read, and by one round trip rather than a loop.
--
-- The usual objection to a stored derived value -- that it can disagree
-- with what it was derived from -- is real here and answered by never
-- letting it be the only copy: it is always recomputable from budgets and
-- transactions, and there is a test that recomputes it from scratch and
-- compares.
ALTER TABLE budgets ADD COLUMN IF NOT EXISTS rollover_in NUMERIC(14,3) NOT NULL
    DEFAULT 0;

-- Walking forward from a changed month means "every budget for this
-- category in this month or later", which is exactly this index.
CREATE INDEX IF NOT EXISTS idx_budgets_category_month
    ON budgets (user_id, category_id, month_year);
