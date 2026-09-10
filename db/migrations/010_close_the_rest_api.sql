-- 010: stop the public REST API serving this database to anybody who asks.
--
-- This one is not a performance change. Supabase exposes every table in the
-- `public` schema through PostgREST, and grants the `anon` and
-- `authenticated` roles full DELETE, INSERT, SELECT, TRUNCATE and UPDATE on
-- each of them by default. Those roles are reached with the project's
-- publishable key, which is designed to be public -- it is meant to be
-- shipped in client-side code.
--
-- With row level security disabled, that combination means the publishable
-- key alone is enough to read every row in this database and to delete
-- them. Verified before writing this, against the live project:
--
--     GET /rest/v1/users?select=user_id,username,email,password_hash
--       -> 200, with real rows
--     GET /rest/v1/transactions   -> 206, Content-Range: 0-0/619
--
-- Nothing in this application uses PostgREST. It connects with psycopg2 as
-- `postgres`, which has rolbypassrls, so every query in server/operations
-- is unaffected by anything below. The API surface that is being closed is
-- one this project never opened and never wanted.
--
-- Two locks rather than one, because either alone would do and neither is
-- expensive:
--
--   Enabling RLS with no policies denies every row to every role that does
--   not bypass it. This is what the Supabase linter asks for, and it is the
--   part that keeps working if a future migration hands out a grant by
--   accident.
--
--   Revoking the grants means the roles have no privilege to exercise in
--   the first place, so a policy added later cannot quietly open a door.

-- --- Deny by default --------------------------------------------------------
--
-- Every table, including schema_migrations: the list of applied migrations
-- is a description of the schema, which is not something to hand out.

ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories         ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions       ENABLE ROW LEVEL SECURITY;
ALTER TABLE budgets            ENABLE ROW LEVEL SECURITY;
ALTER TABLE investments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags               ENABLE ROW LEVEL SECURITY;
ALTER TABLE transaction_tags   ENABLE ROW LEVEL SECURITY;
ALTER TABLE goals              ENABLE ROW LEVEL SECURITY;
ALTER TABLE goal_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_rules    ENABLE ROW LEVEL SECURITY;
ALTER TABLE schema_migrations  ENABLE ROW LEVEL SECURITY;

-- No policies are created. A table with RLS enabled and no policy permits
-- nothing, which is exactly the intent: these tables are reached by this
-- application's own connection and by nothing else.

-- --- And take the privileges away -------------------------------------------

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON SCHEMA public FROM anon, authenticated;

-- Supabase's default privileges hand the same grants to every table created
-- afterwards, so without this the next migration would reopen everything it
-- creates.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM anon, authenticated;
