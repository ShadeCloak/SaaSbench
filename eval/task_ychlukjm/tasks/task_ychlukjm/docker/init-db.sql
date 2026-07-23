CREATE DATABASE IF NOT EXISTS `app_ychlukjm`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_bin;

CREATE USER IF NOT EXISTS 'appychlukjm'@'%' IDENTIFIED BY 'app123ychlukjm';
GRANT ALL PRIVILEGES ON `app_ychlukjm`.* TO 'appychlukjm'@'%';
FLUSH PRIVILEGES;

USE `app_ychlukjm`;
