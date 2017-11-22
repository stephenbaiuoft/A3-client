CREATE DATABASE IF NOT EXISTS photo_browser;
USE photo_browser;
CREATE TABLE users
(
user_id int NOT NULL AUTO_INCREMENT,
username char(20) NOT NULL,
hashed_pwd char(64) NOT NULL,
salt char(8) NOT NULL,
PRIMARY KEY (user_id)
) ENGINE=InnoDB;

CREATE TABLE images
(
img_id int NOT NULL AUTO_INCREMENT,
img_name char(20) NOT NULL,
location char(50) NULL,
description char(150) NULL,
owned_by int NOT NULL,
filename char(32) NOT NULL,
PRIMARY KEY (img_id)
) ENGINE=InnoDB;