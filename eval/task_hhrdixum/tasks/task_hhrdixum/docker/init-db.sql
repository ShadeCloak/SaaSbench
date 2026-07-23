-- task_hhrdixum — initial database bootstrap
--
-- This file is mounted into /docker-entrypoint-initdb.d/ on the postgres
-- container.  It only ever runs ONCE — when the postgres data volume is
-- empty (i.e. first `docker compose up -d` after a `down -v`).
--
-- Per task.md § 8.7, this script MUST NOT create any application tables —
-- Django migrations are responsible for the schema.  Its sole job is to make
-- sure the database and the application user exist with the correct
-- ownership / grants.
--
-- The official postgres image already creates the user defined by
-- POSTGRES_USER and the database defined by POSTGRES_DB before running
-- this script, so the statements below use IF NOT EXISTS guards and
-- idempotent ALTER/GRANT.
--
-- Postgres extensions are deliberately NOT installed here — task.md § 8.7
-- does not list any extensions, so adding them in this file would violate
-- the docker ↔ task.md two-way consistency principle. If the agent needs a
-- particular extension, it must declare it explicitly in its own migrations.

DO
$$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'apphhrdixum') THEN
        CREATE USER apphhrdixum WITH ENCRYPTED PASSWORD 'app123hhrdixum';
    END IF;
END
$$;

-- Make sure the application database is owned by the app user.
ALTER DATABASE app_hhrdixum OWNER TO apphhrdixum;

-- Privileges (idempotent).
GRANT ALL PRIVILEGES ON DATABASE app_hhrdixum TO apphhrdixum;
GRANT ALL PRIVILEGES ON SCHEMA public TO apphhrdixum;
ALTER SCHEMA public OWNER TO apphhrdixum;
