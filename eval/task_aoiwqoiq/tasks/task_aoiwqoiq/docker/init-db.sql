-- Database initialization for Community Forum Platform
-- This script runs automatically when the PostgreSQL container starts for the first time.
-- It creates the required database with extensions.
-- NOTE: The database itself (app_aoiwqoiq) is created by POSTGRES_DB env var.
--       This script adds required PostgreSQL extensions.

-- Connect to the application database
\c app_aoiwqoiq;

-- Extensions required by the application
CREATE EXTENSION IF NOT EXISTS pg_trgm;       -- Trigram similarity for fuzzy search
CREATE EXTENSION IF NOT EXISTS hstore;        -- Key-value store for settings
CREATE EXTENSION IF NOT EXISTS unaccent;      -- Accent-insensitive search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";   -- UUID generation
