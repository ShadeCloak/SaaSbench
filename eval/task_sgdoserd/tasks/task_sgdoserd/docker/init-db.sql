-- task_sgdoserd database initialization
--
-- This script runs once when the postgres container is bootstrapped (the
-- official postgres image runs every *.sql in /docker-entrypoint-initdb.d/
-- against the default database the FIRST time the data volume is created).
--
-- The default database (app_sgdoserd) and role (appsgdoserd) are already
-- created by the postgres entrypoint from POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD,
-- so the only work we need to do here is enable a few PostgreSQL extensions
-- the platform relies on at runtime (full-text search via pg_trgm, deterministic
-- random for some test fixtures via uuid-ossp).
--
-- Schema migrations are NOT run here — the agent's compiled server is
-- responsible for running its own migration set against this database on
-- first boot.
--
-- NOTE: The postgres docker-entrypoint runs every *.sql in this dir against
-- the database named by POSTGRES_DB (here: app_sgdoserd). Do NOT use
-- `\connect <db>` — under scram-sha-256 auth-local that re-connect will
-- be challenged for a password and fail.

-- pg_trgm: GIN trigram indexes used by the default full-text search backend
-- for posts.message / channels.display_name / users.username searches.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- citext: case-insensitive text type. Some columns in later migrations use it
-- (e.g., user emails). The platform copes if it's missing, but having it ready
-- avoids a permission-required CREATE EXTENSION at runtime.
CREATE EXTENSION IF NOT EXISTS citext;

-- uuid-ossp: kept for compatibility with older installations / utility scripts
-- that may want UUID generators. The platform's own IDs are 26-char ULID-style
-- strings, not UUIDs.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- (Sanity-grant block removed.) The postgres entrypoint already grants the
-- DB owner role to POSTGRES_USER (here: appsgdoserd), so explicit
-- `GRANT ALL PRIVILEGES ON DATABASE app_sgdoserd TO appsgdoserd` is a no-op.
-- On PG 14+ the user automatically owns objects they create in `public`, so
-- legacy `GRANT ALL ON SCHEMA public TO appsgdoserd` is also unnecessary.
-- If the agent later introduces additional roles (e.g., a read-only audit
-- role), it should issue scoped GRANTs from its own migration set, not here.

-- Final verification (this only logs; the script never errors out)
DO $$
DECLARE
    ext_count int;
BEGIN
    SELECT count(*) INTO ext_count
      FROM pg_extension
     WHERE extname IN ('pg_trgm', 'citext', 'uuid-ossp');
    RAISE NOTICE 'task_sgdoserd init-db.sql: % extensions enabled', ext_count;
END $$;
