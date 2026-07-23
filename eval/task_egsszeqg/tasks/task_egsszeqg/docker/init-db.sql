DO
$$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'appegsszeqg') THEN
        CREATE ROLE appegsszeqg LOGIN PASSWORD 'app123egsszeqg';
    END IF;
END
$$;

SELECT 'CREATE DATABASE app_egsszeqg OWNER appegsszeqg ENCODING ''UTF8'' TEMPLATE template0'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'app_egsszeqg')\gexec

GRANT ALL PRIVILEGES ON DATABASE app_egsszeqg TO appegsszeqg;
