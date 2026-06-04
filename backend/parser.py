"""
Excel parser for Bankinter PT (debit + credit) and Bank Hapoalim IL.
Returns a list of dicts ready to insert into the transactions table.
"""
import re
import pandas as pd
from typing import Optional

# ── column name aliases ────────────────────────────────────────────────────────
DATE_ALIASES   = ["date", "fecha", "data"]
DESC_ALIASES   = ["description", "concepto", "descripcion", "details", "descricao", "descrição"]
AMOUNT_ALIASES = ["amount", "importe", "montante", "valor"]
DEBIT_ALIASES  = ["debit", "débito", "debito", "saida", "saída"]
CREDIT_ALIASES = ["credit", "crédito", "credito", "entrada"]

# ── keyword → subcategory name mapping ────────────────────────────────────────
# NOTE: order matters — more-specific entries must come before shorter ones
# (e.g. "Eating out" with "bolt food" before "Uber" with bare "bolt")
KEYWORD_MAP = {
    "Mortgage":          ["hipoteca", "mortgage", "crédito habitação", "habitacao", "emprestimo"],
    "Electricity":       ["edp", "endesa", "iberdrola", "eletricidade", "electricity"],
    "Water":             ["smas", "epal", "águas", "aguas", "water"],
    "Internet":          ["nos", "meo", "vodafone", "internet", "fibra", "fiber"],
    "Condominium":       ["condominio", "condomínio", "condominium"],
    "House Ins":         ["pagamento de seguros"],
    "Maintenance":       ["patricia rodrigues", "leroy merlin"],
    "Education":         ["ptb"],
    "Padel":             ["padel", "pádel", "blue padel kourts"],
    "Ella gym":          ["g dram s cascais", "g dram", "dram s cascais"],
    "General_Girls":     ["school", "escola", "colégio", "colegio", "pediatr", "kids", "children"],
    "Gas":               ["galp", "bp", "repsol", "gasolina", "combustivel", "petrol", "fuel"],
    "Supermarket":       ["continente", "pingo doce", "lidl", "aldi", "minipreco", "minipreço",
                          "intermarché", "intermache", "mercadona", "froiz", "supermercado", "grocery",
                          "talho lugar carne", "auchan", "el corte inglés", "mercado"],
    # Eating out BEFORE Uber so "bolt food" matches here before bare "bolt"
    "Eating out":        ["uber eats", "bolt food", "mcdonalds", "mcdonald's", "burger king",
                          "restaurant", "café", "cafe", "tasca", "starbucks",
                          "pastelaria", "delivery", "glovo", "zomato", "just eat", "polo 1921"],
    "Uber":              ["uber", "bolt", "cabify"],
    "Shopping":          ["amazon", "fnac"],
    "Subscriptions":     ["claude.ai"],
    "General_Insurance": ["seguro", "insurance", "fidelidade", "allianz", "generali", "tranquilidade"],
    "Salary":            ["bloqstrxn"],
    "Via Verde":         ["03-TRANSACCOES BXV"],
}


def _find_col(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    """Return the first column name (case-insensitive) matching any alias."""
    lower_cols = {c.lower(): c for c in df.columns}
    for alias in aliases:
        if alias in lower_cols:
            return lower_cols[alias]
    return None


def _parse_description(description: str) -> dict:
    """
    Parse a Bankinter-style description string.
    Returns dict with keys: type, terminal_id, merchant_name, skip
    """
    desc = str(description).strip()
    desc_upper = desc.upper()
    result = {"type": "other", "terminal_id": None, "merchant_name": None, "skip": False}

    if "CARTOES BKCF" in desc_upper:
        result["skip"] = True
        return result

    if desc_upper.startswith("COMPRA ONLINE"):
        result["type"] = "online_purchase"
        # Extract merchant after numeric code: "COMPRA ONLINE 3912047.28 AMAZON" → "Amazon"
        m = re.search(r"COMPRA ONLINE\s+[\d.]+\s+(.*)", desc, re.IGNORECASE)
        if m:
            result["merchant_name"] = m.group(1).strip().title()
        return result

    if desc_upper.startswith("COMPRA"):
        result["type"] = "card_purchase"
        # Extract terminal_id: first numeric token after COMPRA
        m = re.search(r"COMPRA\s+([\d.]+)", desc, re.IGNORECASE)
        if m:
            result["terminal_id"] = m.group(1)
        # Try to extract a brand name after the code
        m2 = re.search(r"COMPRA\s+[\d.]+\s+[\w-]+\s+(.*)", desc, re.IGNORECASE)
        if m2:
            result["merchant_name"] = m2.group(1).strip().title()
        return result

    if re.match(r"^DD\b|^DÉBITO DIRETO|^DEBITO DIRETO", desc, re.IGNORECASE):
        result["type"] = "direct_debit"
        return result

    if desc_upper.startswith("MB WAY"):
        result["type"] = "peer_transfer"
        return result

    if desc_upper.startswith("MULTIBANCO"):
        result["type"] = "atm_withdrawal"
        return result

    return result


def _keyword_subcategory(description: str) -> Optional[str]:
    """Return subcategory name if a keyword matches, else None."""
    desc_lower = description.lower()
    for subcat_key, keywords in KEYWORD_MAP.items():
        for kw in keywords:
            if kw in desc_lower:
                # Map _Girls and _Insurance internal keys back to "General"
                if subcat_key in ("General_Girls", "General_Insurance"):
                    return "General"
                return subcat_key
    return None


def parse_excel(file_bytes: bytes, bank_source: str, subcategory_lookup: dict, filename: str = "") -> list[dict]:
    """
    Parse an Excel or CSV file and return a list of transaction dicts.

    subcategory_lookup: dict mapping subcategory name → subcategory_id
    """
    import io
    fname = (filename or "").lower()
    if fname.endswith(".csv"):
        raw = file_bytes.decode("utf-8-sig", errors="replace")  # strip BOM if present
        # Auto-detect separator: semicolon (common in EU bank exports) or comma
        sep = ";" if raw.count(";") > raw.count(",") else ","
        df = pd.read_csv(io.StringIO(raw), sep=sep, skip_blank_lines=True)
    else:
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    # Normalize column names (strip whitespace)
    df.columns = [str(c).strip() for c in df.columns]

    # ── Hardcoded column mappings per bank source ──────────────────────────────
    if bank_source == "bankinter_debit":
        # Columns: Movement Date | Value Date | Description | Transaction | Amount | Currency | Balance
        date_col   = "Movement Date"
        desc_col   = "Description"
        amt_col    = "Amount"
        debit_col  = None
        credit_col = None
    elif bank_source == "bankinter_credit":
        # Columns: Transaction Date | Processing Date | Invoice | Description | Amount
        date_col   = "Transaction Date"
        desc_col   = "Description"
        amt_col    = "Amount"
        debit_col  = None
        credit_col = None
    else:
        # Hapoalim: flexible column detection
        date_col   = _find_col(df, DATE_ALIASES)
        desc_col   = _find_col(df, DESC_ALIASES)
        amt_col    = _find_col(df, AMOUNT_ALIASES)
        debit_col  = _find_col(df, DEBIT_ALIASES)
        credit_col = _find_col(df, CREDIT_ALIASES)

    missing = [name for name, col in [("date", date_col), ("description", desc_col)] if not col or col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns {missing}. Found columns: {list(df.columns)}")

    rows = []
    for _, row in df.iterrows():
        description = str(row[desc_col]).strip()
        if not description or description.lower() == "nan":
            continue

        parsed = _parse_description(description)
        if parsed["skip"]:
            continue

        # Resolve amount — format is period-decimal (e.g. 12.34 or -1234.56)
        amount = None
        if amt_col and amt_col in df.columns and pd.notna(row.get(amt_col)):
            try:
                # Strip spaces and any accidental thousands commas
                amount = float(str(row[amt_col]).strip().replace(" ", "").replace(",", ""))
            except (ValueError, TypeError):
                pass

        if amount is None and debit_col and credit_col:
            debit  = float(str(row[debit_col]).strip().replace(",", "") or 0) if pd.notna(row.get(debit_col)) else 0.0
            credit = float(str(row[credit_col]).strip().replace(",", "") or 0) if pd.notna(row.get(credit_col)) else 0.0
            amount = credit - debit

        if amount is None:
            continue  # skip unparseable rows

        # Bankinter credit exports charges as positive; negate so they're expenses (negative)
        if bank_source == "bankinter_credit" and amount > 0:
            amount = -amount

        # Parse date — dd-mm-yyyy
        try:
            txn_date = pd.to_datetime(row[date_col], dayfirst=True).date()
        except Exception:
            continue

        # Keyword-based auto-categorization
        subcat_name = _keyword_subcategory(description)
        if parsed["merchant_name"]:
            subcat_name = subcat_name or _keyword_subcategory(parsed["merchant_name"])

        subcategory_id = None
        auto_categorized = False
        needs_review = True

        if subcat_name and subcat_name in subcategory_lookup:
            subcategory_id = subcategory_lookup[subcat_name]
            auto_categorized = True
            needs_review = False

        rows.append({
            "bank_source":      bank_source,
            "txn_date":         txn_date.isoformat(),
            "description":      description,
            "merchant_name":    parsed["merchant_name"],
            "terminal_id":      parsed["terminal_id"],
            "amount":           amount,
            "currency":         "EUR",
            "subcategory_id":   subcategory_id,
            "needs_review":     needs_review,
            "auto_categorized": auto_categorized,
            "is_duplicate":     False,
        })

    return rows
