-- 002: make the money columns able to hold every currency.
--
-- Every amount column is DECIMAL(10,2), which encodes two assumptions that
-- are only true of the rupee and its neighbours.
--
-- Scale. Two decimal places fits 156 of the 162 currencies ISO 4217 lists,
-- but six are divided into thousandths -- the Gulf and North African dinars,
-- BHD JOD KWD LYD OMR TND, whose minor unit is the fils. A balance of
-- 1.234 KWD cannot be stored at all in DECIMAL(10,2); it silently becomes
-- 1.23, and a tenth of a dinar goes missing on every row.
--
-- Precision. Ten digits caps a single figure at 99,999,999.99. In rupees
-- that is a fair ceiling for a personal ledger. In rupiah or dong, where a
-- modest car is priced in the hundreds of millions, it is not.
--
-- NUMERIC(14,3) covers both: thousandths for the dinars, and figures up to
-- 99,999,999,999.999. Widening a NUMERIC is not destructive -- Postgres
-- rewrites the column, and increasing precision and scale cannot truncate
-- an existing value. Every current row keeps exactly the value it has, with
-- a third decimal place of zero.
--
-- quantity is deliberately untouched. It counts units, not money, and its
-- four places already exceed anything a currency needs.

ALTER TABLE transactions ALTER COLUMN amount        TYPE NUMERIC(14,3);
ALTER TABLE budgets      ALTER COLUMN budget_limit  TYPE NUMERIC(14,3);
ALTER TABLE investments  ALTER COLUMN buy_price     TYPE NUMERIC(14,3);
ALTER TABLE investments  ALTER COLUMN current_price TYPE NUMERIC(14,3);

-- users.currency arrived in 001 with a default of INR and has never been
-- read. Nothing to add here; it is only noted so the two migrations read
-- as one decision rather than a column that appeared for no reason.
