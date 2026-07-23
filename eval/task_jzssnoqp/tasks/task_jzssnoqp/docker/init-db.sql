-- Database initialization for Omnichannel Customer Communication Platform
-- The database and user are created by PostgreSQL container via environment variables.
-- This script enables required extensions.

-- Connect to the application database
\c app_jzssnoqp;

-- Enable required PostgreSQL extensions
CREATE EXTENSION IF NOT EXISTS plpgsql;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS vector;

-- Grant full privileges to application user
GRANT ALL PRIVILEGES ON DATABASE app_jzssnoqp TO appjzssnoqp;
GRANT ALL PRIVILEGES ON SCHEMA public TO appjzssnoqp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appjzssnoqp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appjzssnoqp;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO appjzssnoqp;
