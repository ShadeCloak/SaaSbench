-- task_ididetxj — initial database bootstrap
--
-- The POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB env vars set in
-- docker-compose.yml already create the database `app_ididetxj` owned by
-- `appididetxj`. This script only adds the extensions the application
-- requires and grants the proper privileges.
--
-- All schema (tables, indexes, constraints) is the agent's responsibility
-- via the migration runner — this file does NOT create any tables.

-- Connect to the application database
\c app_ididetxj

-- ===========================================================================
-- Extensions
-- ===========================================================================

-- Required for UUID v4 primary keys (used by IdModel base class)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Required for the full-text search vectors on documents (pg_trgm allows
-- trigram indexes for fuzzy match; tsvector / tsquery are built-in)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Optional but useful for case-insensitive email indexing
CREATE EXTENSION IF NOT EXISTS "citext";

-- ===========================================================================
-- Privileges
-- ===========================================================================
GRANT ALL PRIVILEGES ON DATABASE app_ididetxj TO appididetxj;
GRANT ALL ON SCHEMA public TO appididetxj;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appididetxj;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appididetxj;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO appididetxj;
