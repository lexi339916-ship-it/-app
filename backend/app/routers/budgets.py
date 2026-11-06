"""预算接口：按月设置预算并计算使用情况。"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Bill, Budget, CategoryBudget, User
from app.schemas import BudgetIn, BudgetOut

router = APIRouter()


def _month_condition(user_id: int, month: str):
    year, mon = int(month[:4]), int(month[5:7])
    return [
        Bill.user_id == user_id,
        Bill.type == "expense",
        extract("year", Bill.bill_date) == year,
        extract("month", Bill.bill_date) == mon,
    ]


def _category_budget_summary(db: Session, user: User, month: str):
    """分类预算存在时，整月预算只作为它的只读投影。"""
    rows = db.scalars(select(CategoryBudget).where(
        CategoryBudget.user_id == user.id, CategoryBudget.month == month)).all()
    if not rows:
        return None
    amount = sum((Decimal(str(row.amount)) for row in rows), Decimal("0"))
    category_ids = [row.category_id for row in rows]
    spent = db.scalar(select(func.coalesce(func.sum(Bill.amount), 0))
                      .where(*_month_condition(user.id, month),
                             Bill.category_id.in_(category_ids))) if category_ids else 0
    return Decimal(str(amount)), Decimal(str(spent))


@router.get("", response_model=BudgetOut)
def get_budget(month: str, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    try:
        year_i, month_i = int(month[:4]), int(month[5:7])
        assert 1 <= month_i <= 12
    except (ValueError, AssertionError):
        raise HTTPException(400, "月份格式应为 YYYY-MM")
    projected = _category_budget_summary(db, user, month)
    if projected is not None:
        amount, spent = projected
    else:
        row = db.scalar(select(Budget).where(
            Budget.user_id == user.id, Budget.month == month))
        amount = Decimal(str(row.amount)) if row else Decimal("0")
        spent = db.scalar(select(func.coalesce(func.sum(Bill.amount), 0))
                          .where(*_month_condition(user.id, month)))
        spent = Decimal(str(spent))
    ratio = float(spent / amount) if amount > 0 else 0.0
    return BudgetOut(month=month, amount=amount, spent=spent,
                     remaining=amount - spent, usage_ratio=round(ratio, 4))


@router.put("", response_model=BudgetOut)
def set_budget(data: BudgetIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    if data.amount <= 0:
        raise HTTPException(400, "预算金额必须大于 0")
    if _category_budget_summary(db, user, data.month) is not None:
        raise HTTPException(
            409, "该月已使用分类预算，请在预算中心按分类调整，避免两套预算互相覆盖。")
    row = db.scalar(select(Budget).where(
        Budget.user_id == user.id, Budget.month == data.month))
    if row is None:
        row = Budget(user_id=user.id, month=data.month, amount=data.amount)
        db.add(row)
    else:
        row.amount = data.amount
    db.commit()
    return get_budget(data.month, user=user, db=db)
