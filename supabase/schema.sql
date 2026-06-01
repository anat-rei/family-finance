CREATE TABLE users (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  email TEXT NOT NULL,
  display_name TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE categories (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  color TEXT DEFAULT '#6366f1',
  is_income BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE subcategories (
  id SERIAL PRIMARY KEY,
  category_id INTEGER REFERENCES categories(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE merchant_map (
  id SERIAL PRIMARY KEY,
  terminal_id TEXT UNIQUE NOT NULL,
  raw_description TEXT,
  subcategory_id INTEGER REFERENCES subcategories(id),
  created_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE uploads (
  id SERIAL PRIMARY KEY,
  uploaded_by UUID REFERENCES auth.users(id),
  bank_source TEXT NOT NULL,
  filename TEXT,
  row_count INTEGER,
  date_range_start DATE,
  date_range_end DATE,
  created_at TIMESTAMPTZ DEFAULT now(),
  deleted_at TIMESTAMPTZ DEFAULT NULL
);

CREATE TABLE transactions (
  id SERIAL PRIMARY KEY,
  upload_id INTEGER REFERENCES uploads(id),
  bank_source TEXT NOT NULL,
  txn_date DATE NOT NULL,
  description TEXT NOT NULL,
  merchant_name TEXT,
  terminal_id TEXT,
  amount NUMERIC(12,2) NOT NULL,
  currency TEXT DEFAULT 'EUR',
  subcategory_id INTEGER REFERENCES subcategories(id),
  needs_review BOOLEAN DEFAULT false,
  is_duplicate BOOLEAN DEFAULT false,
  auto_categorized BOOLEAN DEFAULT false,
  notes TEXT,
  deleted_at TIMESTAMPTZ DEFAULT NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  -- partial unique index defined below (allows re-import after soft-delete)
);

CREATE UNIQUE INDEX transactions_unique_active
  ON transactions(txn_date, amount, description, bank_source)
  WHERE deleted_at IS NULL;

INSERT INTO categories (name, color, is_income) VALUES
  ('House',      '#3b82f6', false),
  ('Girls',      '#ec4899', false),
  ('Car',        '#f97316', false),
  ('Sport',      '#22c55e', false),
  ('Food',       '#eab308', false),
  ('Insurance',  '#8b5cf6', false),
  ('Transfer',   '#94a3b8', false),
  ('Income',     '#10b981', true),
  ('Other',      '#6b7280', false);

INSERT INTO subcategories (category_id, name) VALUES
  (1, 'Mortgage'), (1, 'Electricity'), (1, 'Water'), (1, 'Internet'),
  (1, 'Condominium'), (1, 'House Ins'),
  (2, 'General'), (2, 'Education'),
  (3, 'Gas'), (3, 'Uber'),
  (4, 'Padel'), (4, 'Yoga'), (4, 'Ella gym'),
  (5, 'Supermarket'), (5, 'Eating out'),
  (6, 'General'),
  (7, 'General'),
  (8, 'Salary'), (8, 'Rental'),
  (9, 'Uncategorized'), (9, 'Shopping');
