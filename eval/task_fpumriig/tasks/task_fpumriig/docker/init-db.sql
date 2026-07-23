-- Database is created by POSTGRES_DB env var, this script creates additional schemas
-- The application is responsible for creating tables (via TypeORM migrations)

-- Create the core schema for user/workspace/auth data
CREATE SCHEMA IF NOT EXISTS core;

-- Create the metadata schema for object/field definitions
CREATE SCHEMA IF NOT EXISTS metadata;

-- Grant privileges
GRANT ALL PRIVILEGES ON SCHEMA core TO appfpumriig;
GRANT ALL PRIVILEGES ON SCHEMA metadata TO appfpumriig;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA core TO appfpumriig;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA metadata TO appfpumriig;

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
