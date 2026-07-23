CREATE DATABASE IF NOT EXISTS `timetracker_db`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

GRANT ALL PRIVILEGES ON `timetracker_db`.* TO 'tt_user'@'%';
FLUSH PRIVILEGES;
