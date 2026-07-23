-- Database initialization
-- The database and user are auto-created by PostgreSQL container via POSTGRES_* env vars.
-- This script ensures the extensions and settings are correct.

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Grant full privileges
GRANT ALL PRIVILEGES ON DATABASE app_yobgvieg TO appyobgvieg;
ALTER DATABASE app_yobgvieg SET timezone TO 'UTC';
