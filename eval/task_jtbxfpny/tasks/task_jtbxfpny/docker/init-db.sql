-- Database and user are created by POSTGRES_USER/POSTGRES_DB env vars.
-- This script runs additional initialization if needed.

-- Ensure the database has proper encoding and collation
ALTER DATABASE app_jtbxfpny SET timezone TO 'UTC';

-- Grant full privileges (already granted by default, but explicit for clarity)
GRANT ALL PRIVILEGES ON DATABASE app_jtbxfpny TO appjtbxfpny;
