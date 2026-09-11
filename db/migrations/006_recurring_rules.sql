-- 006: recurring transactions.
--
-- Rent, salary, the streaming subscription: rows that arrive on a schedule
-- and that nobody wants to type twelve times a year.
--
-- A rule does not *contain* its transactions. It writes ordinary rows into
-- `transactions`, marked with rule_id so they can be traced back. That
-- matters because a materialised row is editable, deletable and reportable
-- like any other -- the rent that went up in August is a fact about August,
-- not a reason to rewrite the rule's history.

CREATE TABLE IF NOT EXISTS recurring_rules (
    rule_id      SERIAL PRIMARY KEY,
    user_id      INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    description  VARCHAR(255) NOT NULL,
    category_id  INT NOT NULL REFERENCES categories(category_id) ON DELETE RESTRICT,
    -- SET NULL, as for goals: closing the account the rent went out of does
    -- not mean the rent stopped.
    account_id   INT REFERENCES accounts(account_id) ON DELETE SET NULL,
    amount       NUMERIC(14,3) NOT NULL,
    txn_type     VARCHAR(10) NOT NULL,
    cadence      VARCHAR(10) NOT NULL,
    -- Which day monthly and yearly rules land on. 31 is allowed and means
    -- "the last day", clamped per month in Python -- February has no 31st
    -- and a rule that silently skipped February would be worse than one
    -- that lands on the 28th.
    day_of_month SMALLINT,
    -- The date the next row is due. This is the whole schedule: there is no
    -- separate calendar, and advancing it is what marks a run as done.
    next_run_on  DATE NOT NULL,
    -- When it should stop. NULL means never.
    ends_on      DATE,
    is_paused    BOOLEAN NOT NULL DEFAULT false,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE recurring_rules DROP CONSTRAINT IF EXISTS recurring_rules_type_check;
ALTER TABLE recurring_rules ADD CONSTRAINT recurring_rules_type_check
    CHECK (txn_type IN ('Income', 'Expense'));

ALTER TABLE recurring_rules DROP CONSTRAINT IF EXISTS recurring_rules_cadence_check;
ALTER TABLE recurring_rules ADD CONSTRAINT recurring_rules_cadence_check
    CHECK (cadence IN ('weekly', 'monthly', 'yearly'));

ALTER TABLE recurring_rules DROP CONSTRAINT IF EXISTS recurring_rules_day_check;
ALTER TABLE recurring_rules ADD CONSTRAINT recurring_rules_day_check
    CHECK (day_of_month IS NULL OR day_of_month BETWEEN 1 AND 31);

ALTER TABLE recurring_rules DROP CONSTRAINT IF EXISTS recurring_rules_amount_check;
ALTER TABLE recurring_rules ADD CONSTRAINT recurring_rules_amount_check
    CHECK (amount > 0);

-- The sweep asks one question: which rules are due? This is the index for
-- exactly that question, and it excludes paused rules from the index
-- entirely rather than making the planner filter them out.
CREATE INDEX IF NOT EXISTS idx_recurring_due
    ON recurring_rules (next_run_on) WHERE NOT is_paused;

-- --- Marking the rows a rule produced ---------------------------------------

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS rule_id INT;

-- SET NULL, not CASCADE. Deleting the rule must not delete the rent you
-- actually paid; the rows simply stop knowing where they came from.
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_rule_id_fkey;
ALTER TABLE transactions ADD CONSTRAINT transactions_rule_id_fkey
    FOREIGN KEY (rule_id) REFERENCES recurring_rules(rule_id) ON DELETE SET NULL;

-- The guard against double-posting, and the reason the sweep is safe to run
-- twice.
--
-- Vercel's cron is at-least-once: a run that times out after writing may be
-- retried, and two instances can overlap. Without this, a retried sweep
-- posts January's rent twice and the only evidence is a duplicate row that
-- looks exactly like a real one. With it, the second insert conflicts and
-- does nothing, so the sweep is idempotent by construction rather than by
-- being careful.
--
-- Partial, because rows written by hand have no rule and there are many of
-- them sharing dates.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_rule_run
    ON transactions (rule_id, txn_date) WHERE rule_id IS NOT NULL;
