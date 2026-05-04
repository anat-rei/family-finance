from pydantic import BaseModel
from typing import Optional
from datetime import date


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str


class CategoryCreate(BaseModel):
    name: str
    color: str = "#6366f1"
    is_income: bool = False


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    is_income: Optional[bool] = None


class SubcategoryCreate(BaseModel):
    category_id: int
    name: str


class SubcategoryUpdate(BaseModel):
    name: str


class TransactionUpdate(BaseModel):
    subcategory_id: Optional[int] = None
    notes: Optional[str] = None
    merchant_name: Optional[str] = None
    needs_review: Optional[bool] = None


class TransactionCreate(BaseModel):
    txn_date: date
    bank_source: str
    description: str
    merchant_name: Optional[str] = None
    amount: float
    currency: str = "EUR"
    subcategory_id: Optional[int] = None
    notes: Optional[str] = None


class SettingUpdate(BaseModel):
    value: str


class TransactionFilter(BaseModel):
    month: Optional[str] = None          # YYYY-MM
    bank_source: Optional[str] = None
    subcategory_id: Optional[int] = None
    needs_review: Optional[bool] = None
    show_duplicates: bool = False
    page: int = 1
    page_size: int = 50
