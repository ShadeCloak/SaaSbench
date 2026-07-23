-- task_gavmyneb — PostgreSQL initialization
--
-- Dual-DB architecture:
--   1. canvas_development / canvas_test  — for Canvas internal use (following Canvas's own design)
--   2. app_gavmyneb                       — the compliant facade required by the task.md §8 spec
--
-- This script runs only on the first startup of the PG container (when pgdata is empty).
-- Dual superuser: postgres (retained from Canvas) + appgavmyneb (task.md spec)

-- =============================================================================
-- Create the task.md-specified app user + DB
-- =============================================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_user WHERE usename='appgavmyneb') THEN
    CREATE USER appgavmyneb WITH PASSWORD 'app123gavmyneb' SUPERUSER;
  END IF;
END $$;

SELECT 'CREATE DATABASE app_gavmyneb OWNER appgavmyneb'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='app_gavmyneb')\gexec

-- =============================================================================
-- Create the DBs retained from Canvas
-- =============================================================================
SELECT 'CREATE DATABASE canvas_development'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='canvas_development')\gexec

SELECT 'CREATE DATABASE canvas_test'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='canvas_test')\gexec

-- =============================================================================
-- Enable the 4 extensions required by task.md §2.2 in both DB sets
-- =============================================================================
\c canvas_development
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\c canvas_test
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\c app_gavmyneb
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

GRANT ALL PRIVILEGES ON DATABASE app_gavmyneb TO appgavmyneb;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appgavmyneb;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appgavmyneb;
