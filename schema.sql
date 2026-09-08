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

CREATE TABLE transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    txn_date        DATE NOT NULL,
    category_id     INT NOT NULL,
    amount          DECIMAL(10,2) NOT NULL,
    txn_type        ENUM('Income','Expense') NOT NULL,
    description     VARCHAR(255),
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

CREATE TABLE budgets (
    budget_id     INT AUTO_INCREMENT PRIMARY KEY,
    category_id   INT NOT NULL,
    month_year    VARCHAR(7) NOT NULL,   -- 'YYYY-MM'
    budget_limit  DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(category_id),
    UNIQUE KEY uniq_cat_month (category_id, month_year)
);

CREATE TABLE investments (
    investment_id INT AUTO_INCREMENT PRIMARY KEY,
    asset_name    VARCHAR(100) NOT NULL,
    asset_type    ENUM('Stock','Mutual Fund','FD') NOT NULL,
    buy_date      DATE NOT NULL,
    buy_price     DECIMAL(10,2) NOT NULL,
    quantity      DECIMAL(10,4) NOT NULL,
    current_price DECIMAL(10,2) NOT NULL
);

-- Seed data: categories
INSERT INTO categories (category_name, category_type) VALUES
('Salary',        'Income'),
('Freelance',      'Income'),
('Groceries',      'Expense'),
('Rent',           'Expense'),
('Transport',      'Expense'),
('Entertainment',  'Expense'),
('Utilities',      'Expense'),
('Dining Out',     'Expense');
