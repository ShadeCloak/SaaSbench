-- Stage 3 — Postgres initialization script
-- task.md §8.1 mandate: database app_iyjruvfz is auto-created by the POSTGRES_DB env
-- Here we enable 4 extensions (Postgres enables plpgsql by default, 5 in total)

\connect app_iyjruvfz;

-- pgcrypto: used for gen_random_uuid() (some fields in schema.prisma use @default(uuid()))
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- uuid-ossp: fallback uuid generation (provides only v1/v3/v4/v5; v7 is built into Postgres 17+ or a separate extension, not relied on by this project)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- pg_trgm: GIN index for LIKE / ILIKE fuzzy search (Insights / RoutingFormResponseField.valueString etc.)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- citext: used for case-insensitive text (e.g. email uniqueness)
CREATE EXTENSION IF NOT EXISTS "citext";

-- Note: Postgres has 5 extensions in total (4 explicit CREATE EXTENSION + 1 default plpgsql)
-- The data model (119 models + 54 enums + 3 views + 591 migrations) is applied by the agent via `yarn prisma migrate deploy` after the container starts
