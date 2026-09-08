-- FinTrack database schema and seed data
-- Run with: mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS fintrack;
USE fintrack;

DROP TABLE IF EXISTS budgets;
DROP TABLE IF EXISTS transactions;
DROP TABLE IF EXISTS investments;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
    category_id   INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL UNIQUE,
    category_type ENUM('Income','Expense') NOT NULL
);
