"""账单接口：CRUD、筛选与分页。所有操作校验数据归属（用户隔离）。"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import AssetAccount, AssetLiability, Bill, BillCategory, User
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


def _resolve_liability(db: Session, user: User,
                       liability_id: int | None) -> AssetLiability | None:
    if liability_id is None:
        return None
    row = db.get(AssetLiability, int(liability_id))
    if row is None or row.user_id != user.id or not row.is_active:
        raise HTTPException(400, "所选负债不存在或已停用")
    return row


def _validate_asset_source(account: AssetAccount | None,
                           liability: AssetLiability | None, type_: str) -> None:
    if account is not None and liability is not None:
        raise HTTPException(400, "资产账户和负债不能同时关联，请选择其中一个")
    if liability is not None and type_ != "expense":
        raise HTTPException(400, "只有支出账单可以计入负债")


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
    liability_name = ""
    if row.liability_id:
        liability = db.get(AssetLiability, row.liability_id)
        if liability:
            liability_name = liability.name
    return BillOut(
        id=row.id, type=row.type, amount=row.amount, category=category_name,
        category_id=row.category_id, account_id=row.account_id,
        account_name=account_name, liability_id=row.liability_id,
        liability_name=liability_name, bill_date=row.bill_date, remark=row.remark,
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
    liability = _resolve_liability(db, user, data.liability_id)
    _validate_asset_source(account, liability, data.type)
    row = Bill(
        user_id=user.id, category_id=cat.id,
        account_id=account.id if account else None,
        liability_id=liability.id if liability else None,
        type=data.type, amount=data.amount, bill_date=data.bill_date,
        remark=data.remark, source=data.source,
        pay_channel=data.pay_channel,
        funding_account=(data.funding_account
                         or (account.name if account else "")
                         or (liability.name if liability else ""))[:40])
    db.add(row)
    try:
        db.flush()
        if account:
            # 新建账单显式关联账户时才影响资产余额
            asset_service.post_bill_movement(db, user, row)
        elif liability:
            # 信用卡/分期消费：增加负债，不扣资产账户
            asset_service.post_bill_liability(db, user, row)
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
    liability = _resolve_liability(db, user, data.liability_id)
    _validate_asset_source(account, liability, data.type)
    old_account_id = row.account_id
    old_liability_id = row.liability_id
    old_type, old_amount = row.type, row.amount
    new_account_id = account.id if account else None
    new_liability_id = liability.id if liability else None

    # 账户：仅在原账单已关联账户、且金额/类型/账户变化时冲正并重记
    asset_changed = bool(old_account_id) and (
        old_type != data.type or old_amount != data.amount
        or old_account_id != new_account_id)
    asset_switch_from_liability = bool(old_liability_id) and bool(new_account_id)
    asset_post = bool(new_account_id) and (asset_changed or asset_switch_from_liability)

    # 负债：原关联变化、从账户切换、或旧账单第一次关联负债时记账
    liability_changed = bool(old_liability_id) and (
        old_type != data.type or old_amount != data.amount
        or old_liability_id != new_liability_id)
    liability_switch_from_account = bool(old_account_id) and bool(new_liability_id)
    liability_new = (new_liability_id is not None
                     and old_liability_id is None and old_account_id is None)
    liability_post = bool(new_liability_id) and (
        liability_changed or liability_switch_from_account or liability_new)

    try:
        if asset_changed:
            asset_service.reverse_bill_movements(db, user, row)
        if liability_changed:
            asset_service.reverse_bill_liability(db, user, row)
        row.type = data.type
        row.amount = data.amount
        row.bill_date = data.bill_date
        row.remark = data.remark
        row.category_id = cat.id
        row.source = data.source
        row.pay_channel = data.pay_channel
        row.funding_account = (data.funding_account
                               or (account.name if account else "")
                               or (liability.name if liability else ""))[:40]
        row.account_id = new_account_id
        row.liability_id = new_liability_id
        if asset_post:
            asset_service.post_bill_movement(db, user, row)
        if liability_post:
            asset_service.post_bill_liability(db, user, row)
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
        if row.liability_id:
            asset_service.reverse_bill_liability(db, user, row)
        db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"ok": True}
