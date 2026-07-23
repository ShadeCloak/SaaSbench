-- Stage 3 — Postgres initialisation script.
-- task.md §8.7 mandate: the database `app_xayqujrv` is auto-created by POSTGRES_DB.
-- This file enables a few extensions; Django migrations create the actual schema.

\connect app_xayqujrv;

-- Set timezone to UTC (matches Django's USE_TZ=True convention).
ALTER DATABASE app_xayqujrv SET timezone TO 'UTC';

-- pgcrypto: provides gen_random_uuid() — used by some UUIDField defaults and HMAC operations.
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- uuid-ossp: backup uuid generation (v1/v3/v4/v5).
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- pg_trgm: trigram index for ILIKE / search-style queries (Identity.identifier search, audit log search, etc.).
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- citext: case-insensitive text — used for email uniqueness on FFAdminUser / Invite.
CREATE EXTENSION IF NOT EXISTS "citext";

-- Note: the data model (87 Django models + 458 migrations) is created by the agent via
-- `python manage.py migrate` after the container is running.
