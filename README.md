# Family Finance Tracker

A personal finance web app for tracking family expenses across multiple bank accounts. Upload Excel exports from Bankinter PT or Bank Hapoalim IL, auto-categorize transactions by keyword, review uncategorized ones, and visualize spending by category.

---

## Project Overview

- **Backend**: FastAPI (Python) with Supabase as the database and auth provider
- **Frontend**: Single-page app (plain HTML + Tailwind CSS via CDN) — no build step required
- **Database**: PostgreSQL hosted on Supabase
- **Deployment**: Render (backend), Supabase (database + auth), local file serving (frontend)

**Features:**
- Multi-bank import (Bankinter Debit, Bankinter Credit, Bank Hapoalim)
- Keyword-based auto-categorization of transactions
- Terminal ID merchant memory (re-categorizes future transactions from the same terminal automatically)
- Duplicate detection across bank sources
- Dashboard with income/expense summary and category breakdown
- Transaction review queue for uncategorized items
- Full CRUD for categories and subcategories
- Dark mode support

---

## Setup

### 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a new project.
2. Choose the **eu-west-1** (Ireland) region for best latency from Portugal.
3. Note your project URL and keys from **Settings → API**.

### 2. Run the Database Schema

1. In your Supabase project, go to **SQL Editor**.
2. Paste the contents of `supabase/schema.sql` and run it.
3. This creates all tables and seeds the default categories and subcategories.

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in:

| Variable | Where to find it |
|---|---|
| `SUPABASE_URL` | Settings → API → Project URL |
| `SUPABASE_SERVICE_KEY` | Settings → API → service_role key |
| `SUPABASE_ANON_KEY` | Settings → API → anon key |
| `SUPABASE_JWT_SECRET` | Settings → API → JWT Settings → JWT Secret |

### 4. Install Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

Requires Python 3.11+. Using a virtual environment is recommended:

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Start the Backend

```bash
uvicorn backend.main:app --reload
```

The API will be available at `http://localhost:8000`.
Interactive API docs: `http://localhost:8000/docs`

### 6. Open the Frontend

Open `frontend/index.html` directly in your browser — no web server needed.

If you want to serve it (optional):
```bash
python -m http.server 3000 --directory frontend
```
Then open `http://localhost:3000`.

---

## Deploy to Render

1. Push this repository to GitHub.
2. Go to [render.com](https://render.com) and create a new **Web Service**.
3. Connect your GitHub repo. Render will detect `render.yaml` automatically.
4. In the Render dashboard, set the three environment variables under **Environment**:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_KEY`
   - `SUPABASE_JWT_SECRET`
5. Deploy. Your API will be available at `https://family-finance-api.onrender.com`.
6. Update the `API_BASE` constant in `frontend/index.html` to point to your Render URL:
   ```js
   const CONFIG = { API_BASE: 'https://family-finance-api.onrender.com' };
   ```

For the frontend, you can host `frontend/index.html` on any static hosting (Netlify, Vercel, GitHub Pages, or Render static site).

---

## How to Use

### Register & Login

1. Open `frontend/index.html`.
2. Click **Register** and create your account (requires email confirmation via Supabase).
3. After confirming your email, log in.

### Upload Bank Files

1. Go to the **Uploads** tab.
2. Drag and drop your Excel file onto the appropriate bank zone (Bankinter Debit, Bankinter Credit, or Bank Hapoalim), or click the zone to browse.
3. The app will parse the file, auto-categorize transactions it recognizes, and show a summary (imported / skipped / needs review).

### Review Transactions

1. After uploading, a yellow **"X to review"** badge appears in the top navbar.
2. Click it or go to **Dashboard** to see the review panel.
3. For each uncategorized transaction, select a category and subcategory, optionally add a note, and click **Save**.
4. Once you categorize a transaction that came from a known terminal ID (physical card purchase), the app saves that mapping in `merchant_map`. Future uploads with the same terminal will be auto-categorized.

### Manage Categories

1. Go to **Categories**.
2. Click a category on the left to see its subcategories on the right.
3. Use the **+ Add** buttons to create new categories or subcategories.
4. Hover over an item to reveal **edit** and **delete** icons.

### Browse Transactions

1. Go to **Transactions**.
2. Filter by month, bank, subcategory, "unreviewed only", or "duplicates only".
3. Click the **edit** icon on any row to inline-edit the category, subcategory, merchant, and notes.
4. Click the **+** button to manually add a transaction.

---

## Bank File Format Notes

### Bankinter PT (Debit and Credit)

Export from Bankinter's online banking as **Excel (.xlsx)**. The parser looks for these column names (case-insensitive):

| Purpose | Expected columns |
|---|---|
| Date | `Date`, `Fecha`, `Data` |
| Description | `Description`, `Concepto`, `Descricao`, `Descrição` |
| Amount | `Amount`, `Importe`, `Montante`, `Valor` |
| Debit (alt) | `Debit`, `Débito`, `Saída` |
| Credit (alt) | `Credit`, `Crédito`, `Entrada` |

Transaction descriptions follow the Bankinter PT format:
- `COMPRA 1234567890 STORE NAME` — card purchase at a physical terminal
- `COMPRA ONLINE 1234567890 MERCHANT` — online purchase
- `DÉBITO DIRETO …` — direct debit
- `MB WAY …` — peer-to-peer transfer
- `MULTIBANCO …` — ATM withdrawal
- `CARTOES BKCF …` — internal credit card settlement (automatically skipped)

### Bank Hapoalim IL

Export from Hapoalim's online banking (Poalim) as Excel. The parser looks for the same column name aliases. Amounts in the file should be in EUR (or you can convert separately). The `currency` field defaults to `EUR`; if your Hapoalim account is in ILS, you may want to adjust this post-import via the notes field until multi-currency support is added.

---

## Architecture Notes

- All API endpoints require a valid Supabase JWT (Bearer token). The token is obtained by calling `/auth/login` and stored in `localStorage`.
- Soft deletes: transactions are not removed from the database; a `deleted_at` timestamp is set instead.
- Duplicate detection: if the same `(txn_date, amount)` pair exists in a different `bank_source`, the new transaction is flagged `is_duplicate = true`.
- The `merchant_map` table is populated automatically when you manually categorize a transaction that has a `terminal_id`. This provides progressive learning — the more you categorize, the less you need to review.
