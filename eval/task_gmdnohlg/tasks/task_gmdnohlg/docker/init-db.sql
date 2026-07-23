-- Database initialization script
-- The database and user are already created by PostgreSQL container env vars.
-- This script ensures proper settings and extensions.

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Ensure proper encoding and collation
ALTER DATABASE app_gmdnohlg SET timezone TO 'UTC';

-- Grant all privileges (redundant with POSTGRES_USER but explicit)
GRANT ALL PRIVILEGES ON DATABASE app_gmdnohlg TO appgmdnohlg;
GRANT ALL PRIVILEGES ON SCHEMA public TO appgmdnohlg;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appgmdnohlg;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appgmdnohlg;
