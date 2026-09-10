-- 003: accounts, and transfers between them.
--
-- Numbering note: the plan calls this migration 002. 002 was spent widening
-- the money columns, so everything from here sits one number later than the
-- plan's table. The order is unchanged.
--
-- Until now a transaction belonged to a user and nothing else, so "how much
-- is in the current account" was a question the schema could not be asked.
-- This adds the missing noun.
--
-- Balances are never stored. An account's balance is its opening balance
-- plus every income row minus every expense row against it, computed on
-- read. A stored balance is a second copy of a fact that already exists,
-- and the two disagree the first time anything is edited or deleted --
-- which is exactly the failure that is invisible until someone reconciles
-- against a real bank statement months later.

-- --- The accounts themselves -----------------------------------------------

CREATE TABLE IF NOT EXISTS accounts (
    account_id      SERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    account_name    VARCHAR(60) NOT NULL,
    account_kind    VARCHAR(16) NOT NULL DEFAULT 'Bank',
    -- What was in it before the ledger starts. Without this, an account
    -- opened with money already in it reads as empty until its whole
    -- history is typed in.
    opening_balance NUMERIC(14,3) NOT NULL DEFAULT 0,
    -- Archived rather than deleted: an account with history cannot be
    -- removed without removing the history, so it is hidden instead.
    is_archived     BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_account_kind_check;
ALTER TABLE accounts ADD CONSTRAINT accounts_account_kind_check
    CHECK (account_kind IN ('Bank', 'Cash', 'Card', 'Wallet', 'Other'));

ALTER TABLE accounts DROP CONSTRAINT IF EXISTS uniq_user_account;
ALTER TABLE accounts ADD CONSTRAINT uniq_user_account
    UNIQUE (user_id, account_name);

CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts (user_id);

-- --- Hanging transactions off them -----------------------------------------
--
-- Nullable on purpose, and it stays nullable at the end of this file. The
-- column cannot be NOT NULL until every code path that writes a transaction
-- supplies one, and that code does not exist yet. Flipping it here would
-- mean a migration that passes on the current data and rejects the next row
-- the running application tries to insert. A later migration sets NOT NULL,
-- once the writes are in place and the check below is trivially true.

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS account_id INT;

-- RESTRICT, for the same reason the category key is RESTRICT: a transaction
-- is a historical fact and must not vanish because an account was tidied
-- away. The API offers to move the rows first.
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS transactions_account_id_fkey;
ALTER TABLE transactions ADD CONSTRAINT transactions_account_id_fkey
    FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE RESTRICT;

-- A transfer is two ordinary rows that share this: an Expense leaving one
-- account and an Income arriving in another. Modelling it as one row with
-- two account columns would mean every balance query has to handle a row
-- that is simultaneously in two accounts with opposite signs. Two rows are
-- what the accounts each actually see.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS transfer_group_id UUID;

CREATE INDEX IF NOT EXISTS idx_txn_user_account
    ON transactions (user_id, account_id, txn_date DESC);

-- Partial: only a small minority of rows are transfer legs, and the index
-- exists solely to find the other leg of one.
CREATE INDEX IF NOT EXISTS idx_txn_transfer_group
    ON transactions (transfer_group_id) WHERE transfer_group_id IS NOT NULL;

-- --- The system category that transfers use --------------------------------
--
-- Both legs of a transfer are filed under a per-user 'Transfer' category,
-- which every report excludes. Without that exclusion, moving 10,000 from
-- savings to current would appear as 10,000 of income and 10,000 of
-- expense: the net is right, so cashflow survives, but the trend chart
-- grows two bars out of money that never entered or left.
--
-- The category is created on demand by the first transfer rather than
-- seeded for every user here, because most users never make one and a row
-- per account that nothing references is just clutter.

ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL
    DEFAULT false;

-- 'Transfer' joins the two real types. A category's type is what decides a
-- transaction's type on entry, and a transfer's legs take their type from
-- their direction instead, which is the one case where the two differ.
ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_category_type_check;
ALTER TABLE categories ADD CONSTRAINT categories_category_type_check
    CHECK (category_type IN ('Income', 'Expense', 'Transfer'));

-- --- Backfill --------------------------------------------------------------
--
-- Every user gets a 'Main' account, including users with no transactions
-- yet, so that the application always has somewhere to put the next row and
-- never has to invent an account mid-write.

INSERT INTO accounts (user_id, account_name, account_kind)
SELECT user_id, 'Main', 'Bank' FROM users
ON CONFLICT (user_id, account_name) DO NOTHING;

UPDATE transactions t
   SET account_id = a.account_id
  FROM accounts a
 WHERE a.user_id = t.user_id
   AND a.account_name = 'Main'
   AND t.account_id IS NULL;

-- --- Prove the backfill did what it claims ---------------------------------
--
-- A backfill that half-worked leaves plausible-looking data, which is the
-- worst kind. These raise rather than warn: a migration that reports a
-- problem in output nobody reads has not reported it.

DO $$
DECLARE
    homeless   INT;
    misfiled   INT;
BEGIN
    SELECT count(*) INTO homeless FROM transactions WHERE account_id IS NULL;
    IF homeless > 0 THEN
        RAISE EXCEPTION 'backfill left % transaction(s) with no account', homeless;
    END IF;

    -- The account a row landed on must belong to the same user as the row.
    -- Nothing in the schema enforces this -- the foreign key only checks
    -- that the account exists -- so it is checked here and again in every
    -- query, which always scopes by user_id.
    SELECT count(*) INTO misfiled
      FROM transactions t JOIN accounts a ON a.account_id = t.account_id
     WHERE a.user_id <> t.user_id;
    IF misfiled > 0 THEN
        RAISE EXCEPTION 'backfill put % transaction(s) on another user''s account',
                        misfiled;
    END IF;
END $$;
