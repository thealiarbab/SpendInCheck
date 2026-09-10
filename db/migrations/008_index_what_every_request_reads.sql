-- 008: the two user_id indexes that were never added.
--
-- Found by reading pg_stat_user_tables rather than by guessing: investments
-- had 18,903 sequential scans against 108 index scans, and recurring_rules
-- 34,296 against 67. Both are read by ordinary screens -- the dashboard and
-- the holdings page for one, the ledger's rules panel for the other -- and
-- both were scanning the whole table to find one account's rows.
--
-- Honest about the payoff: these tables hold a few hundred rows today, and
-- at that size Postgres is right to prefer a sequential scan, so nothing
-- measurable changes now. The point is that they are shared across every
-- account and only grow. An index that arrives after the table is large is
-- an index added during an incident.
--
-- Every other table already had one. transactions, budgets, accounts, goals
-- and tags were all indexed on user_id as they were built; these two were
-- simply missed.

CREATE INDEX IF NOT EXISTS idx_investments_user ON investments (user_id);

-- The rules list is read per user and ordered by when each next fires, so
-- the sort comes free with the lookup. idx_recurring_due already covers the
-- other question -- "which rules are due anywhere" -- which is the sweep's,
-- not a user's.
CREATE INDEX IF NOT EXISTS idx_recurring_user
    ON recurring_rules (user_id, next_run_on);
