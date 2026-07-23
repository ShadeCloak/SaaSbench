-- Database initialization for app_ghmkznee
-- Only creates the database and grants permissions.
-- Table creation is the agent's responsibility (via migrations).

-- The database is already created by POSTGRES_DB env var in docker-compose.
-- This script ensures proper encoding and grants.

ALTER DATABASE app_ghmkznee SET timezone TO 'UTC';

GRANT ALL PRIVILEGES ON DATABASE app_ghmkznee TO appghmkznee;
GRANT ALL PRIVILEGES ON SCHEMA public TO appghmkznee;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appghmkznee;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appghmkznee;
