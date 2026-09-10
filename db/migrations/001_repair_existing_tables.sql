-- 001: repair the five original tables before anything is built on them.
--
-- Everything here is either a correction or an addition that later migrations
-- assume, which is why it runs first. Re-runnable: every statement is either
-- IF NOT EXISTS or wrapped in a guard that checks the current state.

-- --- Deletion behaviour ----------------------------------------------------
-- Neither category foreign key declared an ON DELETE rule, so both defaulted
-- to NO ACTION and deleting a category raised a bare database error. That is
-- why there is no delete-category route today.
--
-- They want different answers. A transaction is a historical fact and must
-- not disappear because a category was tidied up, so RESTRICT: the delete
-- fails loudly and the API can offer to reassign first. A budget for a
-- category that no longer exists is meaningless, so CASCADE.

ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_category_id_fkey;
ALTER TABLE transactions
    ADD CONSTRAINT transactions_category_id_fkey
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE RESTRICT;

ALTER TABLE budgets DROP CONSTRAINT IF EXISTS budgets_category_id_fkey;
ALTER TABLE budgets
    ADD CONSTRAINT budgets_category_id_fkey
    FOREIGN KEY (category_id) REFERENCES categories(category_id) ON DELETE CASCADE;

-- --- Budget uniqueness -----------------------------------------------------
-- uniq_cat_month covers (category_id, month_year). That is not a bug today:
-- a category belongs to exactly one user, so the pair is already unique per
-- user. It is restated to include user_id so the intent is legible in the
-- constraint itself and does not depend on a fact about another table.

ALTER TABLE budgets DROP CONSTRAINT IF EXISTS uniq_cat_month;
ALTER TABLE budgets DROP CONSTRAINT IF EXISTS uniq_user_cat_month;
ALTER TABLE budgets
    ADD CONSTRAINT uniq_user_cat_month UNIQUE (user_id, category_id, month_year);

-- --- Audit columns ---------------------------------------------------------
-- Needed to order transactions logged on the same date, and to tell an
-- imported row from one entered by hand.

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- --- User preferences ------------------------------------------------------
-- is_demo replaces identifying the demo account by its username, so demo
-- users can be created per visitor and cleaned up on a schedule.

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_demo   BOOLEAN     NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS theme     VARCHAR(16) NOT NULL DEFAULT 'brass';
ALTER TABLE users ADD COLUMN IF NOT EXISTS currency  VARCHAR(3)  NOT NULL DEFAULT 'INR';

-- --- Indexes ---------------------------------------------------------------
-- idx_txn_user_date already exists. These cover the filters the reports and
-- the transaction search actually use.

CREATE INDEX IF NOT EXISTS idx_txn_user_cat  ON transactions (user_id, category_id);
CREATE INDEX IF NOT EXISTS idx_txn_user_type ON transactions (user_id, txn_type, txn_date);

-- Trigram index for description search. pg_trgm needs privileges the pooled
-- application role may not have, and this migration must not fail for a
-- feature that does not exist yet, so both steps are guarded and skipping
-- them only means description search falls back to a scan until it is
-- enabled from the Supabase dashboard.
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EXCEPTION WHEN insufficient_privilege OR feature_not_supported THEN
    RAISE NOTICE 'pg_trgm not enabled (insufficient privilege); skipping the description index';
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
        CREATE INDEX IF NOT EXISTS idx_txn_desc_trgm
            ON transactions USING gin (description gin_trgm_ops);
    END IF;
END $$;
