-- Database initialization for benchmark environment
-- Only creates database, extensions, and grants privileges.
-- Schema creation (tables, indexes) is the agent's responsibility.
-- This script runs inside the default database created by POSTGRES_DB env var.

-- Extensions required by the application
CREATE EXTENSION IF NOT EXISTS plpgsql;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Ensure application user has full schema privileges
GRANT ALL PRIVILEGES ON SCHEMA public TO appcqfnbfay;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appcqfnbfay;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appcqfnbfay;
