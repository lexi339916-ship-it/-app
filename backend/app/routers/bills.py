"""账单接口：CRUD、筛选与分页。所有操作校验数据归属（用户隔离）。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import AssetAccount, Bill, BillCategory, User
from app.schemas import BillIn, BillOut, BillPageOut
from app.services import asset_service

router = APIRouter()


def _resolve_category(db: Session, user: User, name: str, type_: str) -> BillCategory:
    row = db.scalar(select(BillCategory).where(
        BillCategory.name == name,
        BillCategory.type == type_,
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    ).limit(1))
    if row is None:
        raise HTTPException(400, f"分类“{name}”不存在，请先创建或选择已有分类")
    return row


def _resolve_account(db: Session, user: User, account_id: int | None) -> AssetAccount | None:
    if account_id is None:
        return None
    row = db.get(AssetAccount, int(account_id))
    if row is None or row.user_id != user.id or not row.is_active:
        raise HTTPException(400, "所选资产账户不存在或已停用")
    return row


def _to_out(db: Session, row: Bill) -> BillOut:
    category_name = "未分类"
    if row.category_id:
        cat = db.get(BillCategory, row.category_id)
        if cat:
            category_name = cat.name
    account_name = ""
    if row.account_id:
        account = db.get(AssetAccount, row.account_id)
        if account:
            account_name = account.name
    return BillOut(
        id=row.id, type=row.type, amount=row.amount, category=category_name,
        category_id=row.category_id, account_id=row.account_id,
        account_name=account_name, bill_date=row.bill_date, remark=row.remark,
        source=row.source, pay_channel=row.pay_channel or "",
        funding_account=row.funding_account or "", created_at=row.created_at)


def _get_owned(db: Session, user: User, bill_id: int) -> Bill:
    row = db.get(Bill, bill_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "账单不存在")
    return row


@router.get("", response_model=BillPageOut)
def list_bills(
    type: str = "",
    month: str = "",          # 2026-10
    start_date: date | None = None,
    end_date: date | None = None,
    q: str = "",
    category_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conditions = [Bill.user_id == user.id]
    if type in ("income", "expense"):
        conditions.append(Bill.type == type)
    if month:
        # 兼容 MySQL 与 SQLite 的按月过滤
        try:
            year_s, month_s = month.split("-")
            year_i, month_i = int(year_s), int(month_s)
            assert 1 <= month_i <= 12
        except (ValueError, AssertionError):
            raise HTTPException(400, "月份格式应为 YYYY-MM")
        conditions.append(extract("year", Bill.bill_date) == year_i)
        conditions.append(extract("month", Bill.bill_date) == month_i)
    if start_date:
        conditions.append(Bill.bill_date >= start_date)
    if end_date:
        conditions.append(Bill.bill_date <= end_date)
    if q:
        conditions.append(Bill.remark.like(f"%{q}%"))
    if category_id is not None:
        conditions.append(Bill.category_id == category_id)

    total = db.scalar(select(func.count()).where(*conditions)) or 0
    rows = db.scalars(
        select(Bill).where(*conditions)
        .order_by(Bill.bill_date.desc(), Bill.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return BillPageOut(
        items=[_to_out(db, r) for r in rows], total=total,
        page=page, page_size=page_size)


@router.post("", response_model=BillOut)
def create_bill(data: BillIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    if data.amount <= 0 or data.amount > Decimal("9999999999.99"):
        raise HTTPException(400, "金额必须在 0.01 ~ 9999999999.99 之间")
    cat = _resolve_category(db, user, data.category, data.type)
    account = _resolve_account(db, user, data.account_id)
    row = Bill(
        user_id=user.id, category_id=cat.id, account_id=account.id if account else None,
        type=data.type, amount=data.amount, bill_date=data.bill_date,
        remark=data.remark, source=data.source,
        pay_channel=data.pay_channel,
        funding_account=(data.funding_account or (account.name if account else ""))[:40])
    db.add(row)
    try:
        db.flush()
        if account:
            # 新建账单显式关联账户时才影响资产余额
            asset_service.post_bill_movement(db, user, row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _to_out(db, row)


@router.get("/{bill_id}", response_model=BillOut)
def get_bill(bill_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return _to_out(db, _get_owned(db, user, bill_id))


@router.put("/{bill_id}", response_model=BillOut)
def update_bill(bill_id: int, data: BillIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = _get_owned(db, user, bill_id)
    cat = _resolve_category(db, user, data.category, data.type)
    account = _resolve_account(db, user, data.account_id)
    old_account_id = row.account_id
    old_type, old_amount = row.type, row.amount
    new_account_id = account.id if account else None
    ledger_changed = bool(old_account_id) and (
        old_type != data.type or old_amount != data.amount
        or old_account_id != new_account_id)
    reversed_count = 0
    try:
        # 旧关联账单的金额/类型/账户发生变化时才冲正；只改备注不动余额
        if ledger_changed:
            reversed_count = asset_service.reverse_bill_movements(db, user, row)
        row.type = data.type
        row.amount = data.amount
        row.bill_date = data.bill_date
        row.remark = data.remark
        row.category_id = cat.id
        row.source = data.source
        row.pay_channel = data.pay_channel
        row.funding_account = (data.funding_account or (account.name if account else ""))[:40]
        row.account_id = new_account_id
        if account and reversed_count > 0:
            asset_service.post_bill_movement(db, user, row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _to_out(db, row)


@router.delete("/{bill_id}")
def delete_bill(bill_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = _get_owned(db, user, bill_id)
    try:
        if row.account_id:
            asset_service.reverse_bill_movements(db, user, row)
        db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"ok": True}
