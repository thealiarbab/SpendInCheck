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

-- Seed data: transactions spread across three months (2026-06, 2026-07, 2026-08)
INSERT INTO transactions (txn_date, category_id, amount, txn_type, description) VALUES
('2026-06-01', 1, 55000.00, 'Income',  'June salary'),
('2026-06-02', 4, 15000.00, 'Expense', 'June rent'),
('2026-06-05', 3,  3200.50, 'Expense', 'Weekly groceries'),
('2026-06-10', 5,  1200.00, 'Expense', 'Fuel and cab rides'),
('2026-06-15', 6,   800.00, 'Expense', 'Movie night'),
('2026-06-20', 7,  2100.00, 'Expense', 'Electricity bill'),
('2026-06-25', 2,  8000.00, 'Income',  'Freelance web project'),
('2026-07-01', 1, 55000.00, 'Income',  'July salary'),
('2026-07-02', 4, 15000.00, 'Expense', 'July rent'),
('2026-07-06', 3,  2900.00, 'Expense', 'Weekly groceries'),
('2026-07-11', 5,  1500.00, 'Expense', 'Metro pass'),
('2026-07-14', 8,  1100.00, 'Expense', 'Dinner with friends'),
('2026-07-18', 6,  600.00,  'Expense', 'Streaming subscription'),
('2026-07-22', 7,  2300.00, 'Expense', 'Electricity bill'),
('2026-08-01', 1, 56000.00, 'Income',  'August salary'),
('2026-08-02', 4, 15000.00, 'Expense', 'August rent'),
('2026-08-05', 3,  3400.00, 'Expense', 'Weekly groceries'),
('2026-08-09', 5,  1300.00, 'Expense', 'Fuel'),
('2026-08-12', 6,  950.00,  'Expense', 'Concert ticket'),
('2026-08-19', 8,  1400.00, 'Expense', 'Weekend brunch');
