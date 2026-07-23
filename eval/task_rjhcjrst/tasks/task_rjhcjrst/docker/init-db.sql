-- Stage 3 — MySQL initialization for PFM (Personal Finance Manager).
-- The MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD env vars on the `db`
-- service already create the database and user, but we re-affirm them
-- here so the schema, charset, collation, and per-host privileges are
-- guaranteed to match task.md §9.1.
--
-- IMPORTANT: This script does NOT create application tables — agent's
-- `php artisan migrate` is responsible for the full schema. We only
-- prepare the empty database with the right defaults.

CREATE DATABASE IF NOT EXISTS `app_rjhcjrst`
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

-- Re-assert the application user (idempotent). MySQL 8 requires user@host;
-- '%' allows access from any container in the docker network.
CREATE USER IF NOT EXISTS 'apprjhcjrst'@'%'
    IDENTIFIED WITH caching_sha2_password BY 'app123rjhcjrst';

GRANT ALL PRIVILEGES ON `app_rjhcjrst`.* TO 'apprjhcjrst'@'%';

-- Some Laravel migrations create temporary tables — grant TEMPORARY too.
GRANT CREATE TEMPORARY TABLES ON `app_rjhcjrst`.* TO 'apprjhcjrst'@'%';

-- NOTE: information_schema is implicitly readable by every user (rows are
-- filtered by each user's privileges), and MySQL 8 forbids GRANT on it
-- (even root gets ERROR 1044). The app user already has ALL on app_rjhcjrst.*,
-- so it can read its own tables' metadata in information_schema.statistics
-- (used by eval primitives P10/P11). No explicit grant needed here — issuing
-- one aborts this init script and leaves the DB half-initialized.

-- Allow the application user to read performance_schema (cron debugging).
GRANT SELECT ON `performance_schema`.* TO 'apprjhcjrst'@'%';

FLUSH PRIVILEGES;

-- Sanity log line — appears in `db` container stdout on startup.
SELECT 'PFM init-db.sql complete: app_rjhcjrst database & apprjhcjrst user ready.' AS status;
