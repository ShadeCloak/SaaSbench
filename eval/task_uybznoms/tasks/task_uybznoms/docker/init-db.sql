-- Database initialization for CMS Framework benchmark task
-- Only creates the database and grants permissions.
-- Table creation is the agent's responsibility (via migrations).

-- Database and user are already created by PostgreSQL container via
-- POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD environment variables.
-- This file handles any additional setup if needed.

-- Ensure UUID extension is available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Ensure PostGIS extension is available (for Point/GeoJSON field types)
CREATE EXTENSION IF NOT EXISTS postgis;

-- Grant full privileges to application user
GRANT ALL PRIVILEGES ON DATABASE app_uybznoms TO appuybznoms;
ALTER DATABASE app_uybznoms OWNER TO appuybznoms;
