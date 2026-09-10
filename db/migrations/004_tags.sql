-- 004: tags.
--
-- A category answers "what kind of spending is this", and a transaction has
-- exactly one. Tags answer everything else -- which holiday, which client,
-- which flat share, whether it was reimbursed -- and a transaction has any
-- number of them, including none.
--
-- That is why this is a second mechanism rather than more categories.
-- Letting a row carry several categories would break every report that
-- assumes spending sums to a total: a 3,000 dinner filed under both Food
-- and Holiday would count twice.

CREATE TABLE IF NOT EXISTS tags (
    tag_id     SERIAL PRIMARY KEY,
    user_id    INT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    tag_name   VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique on the lowercased name, not the name. Nobody means "Holiday" and
-- "holiday" to be two different tags, and a list containing both is the
-- kind of mess that only ever grows. An expression index rather than a
-- constraint because a UNIQUE constraint cannot be written over an
-- expression.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_user_tag ON tags (user_id, lower(tag_name));

-- The join table has no user_id, deliberately.
--
-- It would be denormalisation: the transaction already knows whose it is,
-- and a second copy is a second thing that can disagree with the first. The
-- cost is that every query here has to reach user scope through
-- transactions rather than filtering this table directly -- which is a
-- constraint worth having, because it means no query can accidentally be
-- written against tag links alone and quietly cross accounts.
CREATE TABLE IF NOT EXISTS transaction_tags (
    -- CASCADE on both sides, but for different reasons. A tag link is not
    -- history: when the transaction goes the link is meaningless, and when
    -- the tag goes the transaction is untouched and simply loses a label.
    transaction_id INT NOT NULL REFERENCES transactions(transaction_id)
                       ON DELETE CASCADE,
    tag_id         INT NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (transaction_id, tag_id)
);

-- The primary key already serves "which tags does this transaction have".
-- This serves the other direction -- "which transactions carry this tag" --
-- which is what the filter on the ledger asks.
CREATE INDEX IF NOT EXISTS idx_transaction_tags_tag ON transaction_tags (tag_id);
