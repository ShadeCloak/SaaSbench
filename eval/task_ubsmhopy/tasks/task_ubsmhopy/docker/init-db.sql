-- Database initialization for password manager server
-- Only creates the database and grants privileges.
-- Table creation is the agent's responsibility (via Diesel migrations).

-- Database and user are created by PostgreSQL container via environment variables:
--   POSTGRES_DB=app_ubsmhopy
--   POSTGRES_USER=appubsmhopy
--   POSTGRES_PASSWORD=app123ubsmhopy

-- Ensure UTF-8 encoding
ALTER DATABASE app_ubsmhopy SET client_encoding TO 'UTF8';
ALTER DATABASE app_ubsmhopy SET timezone TO 'UTC';

-- Grant full privileges
GRANT ALL PRIVILEGES ON DATABASE app_ubsmhopy TO appubsmhopy;
