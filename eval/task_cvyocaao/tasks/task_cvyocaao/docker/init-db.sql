-- Database is auto-created by POSTGRES_DB env var.
-- This script ensures correct encoding and grants.

ALTER DATABASE app_cvyocaao SET timezone TO 'UTC';

GRANT ALL PRIVILEGES ON DATABASE app_cvyocaao TO appcvyocaao;
GRANT ALL PRIVILEGES ON SCHEMA public TO appcvyocaao;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO appcvyocaao;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO appcvyocaao;
