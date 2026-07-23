-- init-db.sql
--
-- Runs once on first PostgreSQL container startup (mounted at
-- /docker-entrypoint-initdb.d/init-db.sql by docker-compose).
--
-- Note: the official postgres image already creates POSTGRES_USER /
-- POSTGRES_DB / POSTGRES_PASSWORD from environment vars before running this
-- script, so the owner role + database are already present. This file only
-- provides:
--   1. The `citext` extension required by users.email / invitations.email /
--      etc. (per task.md §3.1.1, §3.1.10)
--   2. Defensive grants in case schema_search_path or roles are restricted

\connect app_orghjavi;

CREATE EXTENSION IF NOT EXISTS citext;

GRANT ALL PRIVILEGES ON DATABASE app_orghjavi TO apporghjavi;
GRANT ALL ON SCHEMA public TO apporghjavi;

-- Verify extension is loaded
SELECT extname, extversion FROM pg_extension WHERE extname = 'citext';
