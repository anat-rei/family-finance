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
  created_at TIMESTAMPTZ DEFAULT now()
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
  UNIQUE(txn_date, amount, description, bank_source)
);

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
  (2, 'General'),
  (3, 'Gas'), (3, 'Uber'),
  (4, 'Padel'), (4, 'Yoga'),
  (5, 'Supermarket'), (5, 'Eating out'),
  (6, 'General'),
  (7, 'General'),
  (8, 'Salary'), (8, 'Rental'),
  (9, 'Uncategorized');
