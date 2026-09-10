-- 009: cover the foreign keys that point at things people delete.
--
-- Reported by Supabase's own linter, and worth acting on because of what a
-- foreign key does on the *parent* side. Deleting a category has to prove
-- no transaction still references it -- that is what the RESTRICT means --
-- and without an index on transactions.category_id, proving it means
-- scanning every transaction in the table. The table is shared by every
-- account, so one person tidying up a category reads everybody's rows.
--
-- The existing composite indexes do not help. idx_txn_user_cat is
-- (user_id, category_id): right for "this user's rows in this category",
-- useless for "any row in this category", because the leading column is not
-- the one being asked about.
--
-- Nothing measurable changes today -- the tables are small enough that a
-- scan is fast, and the benchmark is unmoved. The cost of adding these
-- later is that they are added while somebody waits.

-- The two that matter most: both parents are deletable from the UI, and
-- transactions is the table that grows without bound.
CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions (category_id);
CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions (account_id);

-- Deleting a category also checks budgets and recurring rules.
CREATE INDEX IF NOT EXISTS idx_budgets_category ON budgets (category_id);
CREATE INDEX IF NOT EXISTS idx_recurring_category
    ON recurring_rules (category_id);

-- Deleting an account checks rules and goals, which hold it ON DELETE SET
-- NULL -- still a scan to find the rows to null out.
CREATE INDEX IF NOT EXISTS idx_recurring_account ON recurring_rules (account_id);
CREATE INDEX IF NOT EXISTS idx_goals_account ON goals (account_id);
