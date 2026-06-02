from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt as pyjwt
import os
from datetime import date
from typing import Optional
from dotenv import load_dotenv

from db import supabase
from models import (
    LoginRequest, RegisterRequest,
    CategoryCreate, CategoryUpdate,
    SubcategoryCreate, SubcategoryUpdate,
    TransactionUpdate, TransactionCreate,
    SettingUpdate,
)
from parser import parse_excel, _keyword_subcategory

load_dotenv()

app = FastAPI(title="Family Finance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")


# ── Auth helpers ───────────────────────────────────────────────────────────────

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    try:
        payload = pyjwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Auth routes ────────────────────────────────────────────────────────────────

@app.post("/auth/login")
def login(body: LoginRequest):
    try:
        res = supabase.auth.sign_in_with_password({"email": body.email, "password": body.password})
        session = res.session
        user    = res.user
        return {
            "access_token": session.access_token,
            "user_id": user.id,
            "email": user.email,
            "display_name": (user.user_metadata or {}).get("display_name", user.email),
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/auth/register", status_code=201)
def register(body: RegisterRequest):
    try:
        res = supabase.auth.sign_up({
            "email": body.email,
            "password": body.password,
            "options": {"data": {"display_name": body.display_name}},
        })
        user = res.user
        # Mirror into users table
        supabase.table("users").upsert({
            "id": user.id,
            "email": body.email,
            "display_name": body.display_name,
        }).execute()
        return {"message": "Registration successful. Check your email to confirm."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Categories ─────────────────────────────────────────────────────────────────

@app.get("/categories")
def list_categories(user_id: str = Depends(get_current_user)):
    cats = supabase.table("categories").select("*").order("name").execute().data
    subs = supabase.table("subcategories").select("*").order("name").execute().data
    # Attach subcategories to each category
    subs_by_cat = {}
    for s in subs:
        subs_by_cat.setdefault(s["category_id"], []).append(s)
    for c in cats:
        c["subcategories"] = subs_by_cat.get(c["id"], [])
    return cats


@app.post("/categories", status_code=201)
def create_category(body: CategoryCreate, user_id: str = Depends(get_current_user)):
    res = supabase.table("categories").insert(body.model_dump()).execute()
    return res.data[0]


@app.put("/categories/{cat_id}")
def update_category(cat_id: int, body: CategoryUpdate, user_id: str = Depends(get_current_user)):
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "Nothing to update")
    res = supabase.table("categories").update(update_data).eq("id", cat_id).execute()
    if not res.data:
        raise HTTPException(404, "Category not found")
    return res.data[0]


@app.delete("/categories/{cat_id}", status_code=204)
def delete_category(cat_id: int, user_id: str = Depends(get_current_user)):
    # Check for transactions using any subcategory in this category
    subs = supabase.table("subcategories").select("id").eq("category_id", cat_id).execute().data
    sub_ids = [s["id"] for s in subs]
    if sub_ids:
        txns = supabase.table("transactions").select("id").in_("subcategory_id", sub_ids).is_("deleted_at", "null").limit(1).execute().data
        if txns:
            raise HTTPException(400, "Cannot delete: transactions reference this category")
    supabase.table("categories").delete().eq("id", cat_id).execute()


# ── Subcategories ──────────────────────────────────────────────────────────────

@app.post("/subcategories", status_code=201)
def create_subcategory(body: SubcategoryCreate, user_id: str = Depends(get_current_user)):
    res = supabase.table("subcategories").insert(body.model_dump()).execute()
    return res.data[0]


@app.put("/subcategories/{sub_id}")
def update_subcategory(sub_id: int, body: SubcategoryUpdate, user_id: str = Depends(get_current_user)):
    res = supabase.table("subcategories").update({"name": body.name}).eq("id", sub_id).execute()
    if not res.data:
        raise HTTPException(404, "Subcategory not found")
    return res.data[0]


@app.delete("/subcategories/{sub_id}", status_code=204)
def delete_subcategory(sub_id: int, user_id: str = Depends(get_current_user)):
    txns = supabase.table("transactions").select("id").eq("subcategory_id", sub_id).is_("deleted_at", "null").limit(1).execute().data
    if txns:
        raise HTTPException(400, "Cannot delete: transactions reference this subcategory")
    supabase.table("subcategories").delete().eq("id", sub_id).execute()


# ── Uploads ────────────────────────────────────────────────────────────────────

@app.get("/uploads")
def list_uploads(user_id: str = Depends(get_current_user)):
    uploads = supabase.table("uploads").select("*").is_("deleted_at", "null").order("created_at", desc=True).execute().data
    # Enrich with display_name from public users table
    user_ids = list({u["uploaded_by"] for u in uploads if u.get("uploaded_by")})
    if user_ids:
        users = supabase.table("users").select("id,display_name,email").in_("id", user_ids).execute().data
        user_map = {u["id"]: u for u in users}
        for u in uploads:
            u["uploader"] = user_map.get(u.get("uploaded_by"), {})
    return uploads


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    bank_source: str = Form(...),
    user_id: str = Depends(get_current_user),
):
    content = await file.read()

    # Build subcategory lookup: name → id
    subs = supabase.table("subcategories").select("id,name").execute().data
    subcategory_lookup = {s["name"]: s["id"] for s in subs}

    # Build merchant_map lookup: terminal_id → subcategory_id
    merchant_data = supabase.table("merchant_map").select("terminal_id,subcategory_id").execute().data
    merchant_map = {m["terminal_id"]: m["subcategory_id"] for m in merchant_data}

    try:
        rows = parse_excel(content, bank_source, subcategory_lookup, filename=file.filename or "")
    except Exception as e:
        raise HTTPException(400, f"Parse error: {str(e)}")

    if not rows:
        raise HTTPException(400, "No valid transactions found in file")

    # Apply merchant_map overrides
    for row in rows:
        if row.get("terminal_id") and row["terminal_id"] in merchant_map:
            row["subcategory_id"] = merchant_map[row["terminal_id"]]
            row["auto_categorized"] = True
            row["needs_review"] = False

    # Detect cross-bank duplicates: (txn_date, amount) appearing in another bank_source
    existing = supabase.table("transactions").select("txn_date,amount,bank_source").is_("deleted_at", "null").execute().data
    existing_pairs = {(r["txn_date"], str(r["amount"]), r["bank_source"]) for r in existing}

    for row in rows:
        key = (row["txn_date"], str(row["amount"]))
        for ex in existing_pairs:
            if ex[0] == key[0] and ex[1] == key[1] and ex[2] != bank_source:
                row["is_duplicate"] = True
                break

    # Create upload record
    dates = [r["txn_date"] for r in rows]
    upload = supabase.table("uploads").insert({
        "uploaded_by": user_id,
        "bank_source": bank_source,
        "filename": file.filename,
        "row_count": len(rows),
        "date_range_start": min(dates),
        "date_range_end": max(dates),
    }).execute().data[0]

    upload_id = upload["id"]

    # Insert transactions (handle dedup key)
    imported = 0
    skipped = 0
    last_error = None
    for row in rows:
        row["upload_id"] = upload_id
        try:
            supabase.table("transactions").insert(row).execute()
            imported += 1
        except Exception as e:
            skipped += 1
            last_error = str(e)

    needs_review_count = sum(1 for r in rows if r.get("needs_review"))

    return {
        "imported": imported,
        "skipped": skipped,
        "needs_review": needs_review_count,
        "last_error": last_error,
        "upload_id": upload_id,
    }


# ── Transactions ───────────────────────────────────────────────────────────────

@app.get("/transactions")
def list_transactions(
    month: Optional[str] = Query(None),
    bank_source: Optional[str] = Query(None),
    subcategory_id: Optional[int] = Query(None),
    needs_review: Optional[bool] = Query(None),
    show_duplicates: bool = Query(False),
    expenses_only: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user),
):
    q = supabase.table("transactions").select(
        "*, subcategories(id, name, category_id, categories(id, name, color, is_income))"
    ).is_("deleted_at", "null").order("txn_date", desc=True)

    if expenses_only:
        q = q.lt("amount", 0)

    if month:
        try:
            year, mo = month.split("-")
            import calendar
            last_day = calendar.monthrange(int(year), int(mo))[1]
            q = q.gte("txn_date", f"{month}-01").lte("txn_date", f"{month}-{last_day:02d}")
        except Exception:
            pass

    if bank_source:
        q = q.eq("bank_source", bank_source)
    if subcategory_id is not None:
        q = q.eq("subcategory_id", subcategory_id)
    if needs_review is not None:
        q = q.eq("needs_review", needs_review)
    if show_duplicates:
        q = q.eq("is_duplicate", True)

    offset = (page - 1) * page_size
    res = q.range(offset, offset + page_size - 1).execute()
    return {"transactions": res.data, "page": page, "page_size": page_size}


@app.post("/transactions", status_code=201)
def create_transaction(body: TransactionCreate, user_id: str = Depends(get_current_user)):
    data = body.model_dump()
    data["txn_date"] = str(data["txn_date"])
    res = supabase.table("transactions").insert(data).execute()
    return res.data[0]


@app.put("/transactions/{txn_id}")
def update_transaction(txn_id: int, body: TransactionUpdate, user_id: str = Depends(get_current_user)):
    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "Nothing to update")

    # If subcategory changed and terminal_id exists, update merchant_map
    if "subcategory_id" in update_data:
        txn = supabase.table("transactions").select("terminal_id,description").eq("id", txn_id).single().execute().data
        if txn and txn.get("terminal_id"):
            supabase.table("merchant_map").upsert({
                "terminal_id": txn["terminal_id"],
                "raw_description": txn.get("description"),
                "subcategory_id": update_data["subcategory_id"],
                "created_by": user_id,
            }, on_conflict="terminal_id").execute()

    res = supabase.table("transactions").update(update_data).eq("id", txn_id).execute()
    if not res.data:
        raise HTTPException(404, "Transaction not found")
    return res.data[0]


@app.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, user_id: str = Depends(get_current_user)):
    from datetime import datetime
    supabase.table("transactions").update({"deleted_at": datetime.utcnow().isoformat()}).eq("id", txn_id).execute()


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/dashboard")
def get_dashboard(
    month: Optional[str] = Query(None),
    user_id: str = Depends(get_current_user),
):
    q = supabase.table("transactions").select(
        "amount, needs_review, subcategory_id, subcategories(name, category_id, categories(name, color, is_income))"
    ).is_("deleted_at", "null")

    if month:
        try:
            year, mo = month.split("-")
            import calendar
            last_day = calendar.monthrange(int(year), int(mo))[1]
            q = q.gte("txn_date", f"{month}-01").lte("txn_date", f"{month}-{last_day:02d}")
        except Exception:
            pass

    txns = q.execute().data

    total_income   = sum(float(t["amount"]) for t in txns if float(t["amount"]) > 0)
    total_expenses = sum(float(t["amount"]) for t in txns if float(t["amount"]) < 0)
    net            = total_income + total_expenses
    needs_review_count = sum(1 for t in txns if t.get("needs_review"))

    # Group by category / subcategory
    from collections import defaultdict
    cat_totals = defaultdict(lambda: {"amount": 0.0, "color": "#6b7280", "is_income": False, "subcats": defaultdict(float)})

    for t in txns:
        amt = float(t["amount"])
        if amt >= 0:
            continue  # skip income for expense breakdown
        s = t.get("subcategories")
        if s:
            c = s.get("categories") or {}
            cat_name  = c.get("name", "Other")
            sub_name  = s.get("name", "Uncategorized")
            cat_totals[cat_name]["amount"]    += amt
            cat_totals[cat_name]["color"]     = c.get("color", "#6b7280")
            cat_totals[cat_name]["is_income"] = c.get("is_income", False)
            cat_totals[cat_name]["subcats"][sub_name] += amt
        else:
            cat_totals["Other"]["amount"] += amt
            cat_totals["Other"]["subcats"]["Uncategorized"] += amt

    total_exp_abs = abs(total_expenses) or 1
    by_category = []
    for cat_name, data in sorted(cat_totals.items(), key=lambda x: x[1]["amount"]):
        rows = []
        for sub_name, sub_amt in sorted(data["subcats"].items(), key=lambda x: x[1]):
            rows.append({
                "subcategory": sub_name,
                "amount": sub_amt,
                "pct": round(abs(sub_amt) / total_exp_abs * 100, 1),
            })
        by_category.append({
            "category": cat_name,
            "color":    data["color"],
            "amount":   data["amount"],
            "pct":      round(abs(data["amount"]) / total_exp_abs * 100, 1),
            "subcategories": rows,
        })

    top = by_category[0]["category"] if by_category else None

    return {
        "total_income":         total_income,
        "total_expenses":       total_expenses,
        "net":                  net,
        "needs_review_count":   needs_review_count,
        "by_category":          by_category,
        "top_expense_category": top,
    }


# ── Recategorize ───────────────────────────────────────────────────────────────

@app.post("/recategorize")
def recategorize(user_id: str = Depends(get_current_user)):
    """Re-run keyword matching on all uncategorized transactions."""
    subs = supabase.table("subcategories").select("id,name").execute().data
    subcategory_lookup = {s["name"]: s["id"] for s in subs}

    txns = (
        supabase.table("transactions")
        .select("id,description,merchant_name")
        .is_("subcategory_id", "null")
        .is_("deleted_at", "null")
        .execute().data
    )

    updated = 0
    for t in txns:
        subcat_name = _keyword_subcategory(t["description"])
        if not subcat_name and t.get("merchant_name"):
            subcat_name = _keyword_subcategory(t["merchant_name"])
        if subcat_name and subcat_name in subcategory_lookup:
            supabase.table("transactions").update({
                "subcategory_id":   subcategory_lookup[subcat_name],
                "auto_categorized": True,
                "needs_review":     False,
            }).eq("id", t["id"]).execute()
            updated += 1

    return {"updated": updated, "scanned": len(txns)}


# ── Merchant map ───────────────────────────────────────────────────────────────

@app.get("/merchant-map")
def list_merchant_map(user_id: str = Depends(get_current_user)):
    res = supabase.table("merchant_map").select("*, subcategories(name, categories(name))").order("created_at", desc=True).execute()
    return res.data


@app.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: int, user_id: str = Depends(get_current_user)):
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    supabase.table("transactions").update({"deleted_at": now}).eq("upload_id", upload_id).is_("deleted_at", "null").execute()
    supabase.table("uploads").update({"deleted_at": now}).eq("id", upload_id).execute()


@app.delete("/merchant-map/{map_id}", status_code=204)
def delete_merchant_map(map_id: int, user_id: str = Depends(get_current_user)):
    supabase.table("merchant_map").delete().eq("id", map_id).execute()


# ── Settings ───────────────────────────────────────────────────────────────────

@app.get("/settings")
def get_settings(user_id: str = Depends(get_current_user)):
    res = supabase.table("settings").select("*").execute()
    return {r["key"]: r["value"] for r in res.data}


@app.put("/settings/{key}")
def update_setting(key: str, body: SettingUpdate, user_id: str = Depends(get_current_user)):
    from datetime import datetime
    supabase.table("settings").upsert(
        {"key": key, "value": body.value, "updated_at": datetime.utcnow().isoformat()},
        on_conflict="key"
    ).execute()
    return {"key": key, "value": body.value}
