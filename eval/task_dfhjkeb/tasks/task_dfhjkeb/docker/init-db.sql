-- Database initialization script
-- The database 'app_db' is created automatically by the POSTGRES_DB environment variable.
-- This script ensures proper extensions and encoding.

-- Enable commonly used extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Ensure the app user has full privileges on the database
GRANT ALL PRIVILEGES ON DATABASE app_db TO app;
ALTER DATABASE app_db SET timezone TO 'UTC';
