-- 005: savings goals, and what has been put towards them.
--
-- A goal is a target with a name: 40,000 for a laptop, 200,000 for an
-- emergency fund. What makes it a goal rather than a note is the second
-- table -- the record of what has actually been set aside.
--
-- Contributions are explicit rows, not a sum derived from tagged
-- transactions. Deriving looks tempting and is wrong twice over. Money put
-- towards a goal usually is not a transaction at all: nothing leaves your
-- accounts when you decide that 5,000 of what is already in savings is
-- earmarked for the laptop, so there would be no row to tag. And where
-- there is a transaction, counting it as both spending and saving means
-- every report has to choose which one to believe.

CREATE TABLE IF NOT EXISTS goals (
    goal_id       SERIAL PRIMARY KEY,
    user_id       INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    goal_name     VARCHAR(60) NOT NULL,
    target_amount NUMERIC(14,3) NOT NULL,
    -- Optional. "Save 200,000 eventually" is a real goal, and demanding a
    -- date would make people invent one, which turns every progress figure
    -- into a judgement about a deadline nobody meant.
    target_date   DATE,
    -- Where the money is kept, if anywhere in particular. SET NULL rather
    -- than CASCADE: closing the account you were saving into does not
    -- abandon the goal, it just stops saying where the money sits.
    account_id    INT REFERENCES accounts(account_id) ON DELETE SET NULL,
    is_archived   BOOLEAN NOT NULL DEFAULT false,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE goals DROP CONSTRAINT IF EXISTS goals_target_amount_check;
ALTER TABLE goals ADD CONSTRAINT goals_target_amount_check
    CHECK (target_amount > 0);

ALTER TABLE goals DROP CONSTRAINT IF EXISTS uniq_user_goal;
ALTER TABLE goals ADD CONSTRAINT uniq_user_goal UNIQUE (user_id, goal_name);

CREATE INDEX IF NOT EXISTS idx_goals_user ON goals (user_id);

-- As with transaction_tags, no user_id here: the goal already knows whose
-- it is, and every query reaches scope through it.
CREATE TABLE IF NOT EXISTS goal_contributions (
    contribution_id SERIAL PRIMARY KEY,
    goal_id         INT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
    contributed_on  DATE NOT NULL,
    -- Signed on purpose. Taking money back out of a goal is an ordinary
    -- thing to do, and recording it as a negative contribution keeps the
    -- running total honest without a second table or a direction column.
    amount          NUMERIC(14,3) NOT NULL,
    note            VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE goal_contributions
    DROP CONSTRAINT IF EXISTS goal_contributions_amount_check;
ALTER TABLE goal_contributions ADD CONSTRAINT goal_contributions_amount_check
    CHECK (amount <> 0);

-- Every read of a goal asks for its contributions, in date order.
CREATE INDEX IF NOT EXISTS idx_goal_contributions_goal
    ON goal_contributions (goal_id, contributed_on);
