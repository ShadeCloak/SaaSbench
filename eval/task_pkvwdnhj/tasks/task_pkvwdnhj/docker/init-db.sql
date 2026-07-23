-- Database and user are auto-created by POSTGRES_USER/POSTGRES_DB env vars.
-- This script runs additional setup inside the already-created database.

\connect app_pkvwdnhj;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
