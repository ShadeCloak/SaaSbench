-- task_lgzivily — initial database bootstrap.
--
-- The MariaDB image runs every *.sql file in /docker-entrypoint-initdb.d/
-- exactly once during the very first container start (when the data volume
-- is empty). After that, schema migrations are the application's job.
--
-- This script ONLY:
--   1. (re-)creates the application database with utf8mb4
--   2. (re-)grants the application user full privileges on it
--
-- It deliberately creates NO TABLES — building the 282-table schema is the
-- agent's responsibility (see task.md §3 Data Model and §9.1 build steps).

CREATE DATABASE IF NOT EXISTS `app_lgzivily`
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

-- The MariaDB entrypoint already creates the user from MARIADB_USER, but we
-- (idempotently) re-grant just to be explicit; this also lets people change the
-- credentials in .env and re-`docker compose down -v && up` cleanly.
CREATE USER IF NOT EXISTS 'applgzivily'@'%' IDENTIFIED BY 'app123lgzivily';
GRANT ALL PRIVILEGES ON `app_lgzivily`.* TO 'applgzivily'@'%';

-- The application also needs the GLOBAL privileges that audit-log + GACL
-- triggers expect on a fresh install:
GRANT PROCESS, REFERENCES ON *.* TO 'applgzivily'@'%';

FLUSH PRIVILEGES;

-- Optional — make `applgzivily` able to connect from inside the container too
-- (useful for `docker exec ... mysql -u applgzivily ...`)
CREATE USER IF NOT EXISTS 'applgzivily'@'localhost' IDENTIFIED BY 'app123lgzivily';
GRANT ALL PRIVILEGES ON `app_lgzivily`.* TO 'applgzivily'@'localhost';
FLUSH PRIVILEGES;
