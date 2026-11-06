"""统计接口：月度汇总与分类占比。金额计算全部在后端 SQL 完成。"""
import calendar
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Bill, BillCategory, Note, User
from app.schemas import (
    CategoryStatItem, CategoryStatsOut, ChannelStatItem, ChannelStatsOut,
    DayPoint, MonthlyStatsOut, ProfileStatsOut,
)

router = APIRouter()


def _parse_month(month: str) -> tuple[int, int]:
    try:
        year, mon = int(month[:4]), int(month[5:7])
        assert 1 <= mon <= 12
        return year, mon
    except (ValueError, AssertionError):
        raise HTTPException(400, "月份格式应为 YYYY-MM")


def _month_days(year: int, mon: int) -> list[date]:
    return [date(year, mon, d) for d in range(1, calendar.monthrange(year, mon)[1] + 1)]


@router.get("/monthly", response_model=MonthlyStatsOut)
def monthly(month: str = "", category_id: int | None = None,
            user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    today = date.today()
    month = month or today.strftime("%Y-%m")
    year, mon = _parse_month(month)

    conditions = [
        Bill.user_id == user.id,
        extract("year", Bill.bill_date) == year,
        extract("month", Bill.bill_date) == mon,
    ]
    if category_id is not None:
        conditions.append(Bill.category_id == category_id)
    rows = db.scalars(select(Bill).where(*conditions)).all()

    income = sum((r.amount for r in rows if r.type == "income"), Decimal("0"))
    expense = sum((r.amount for r in rows if r.type == "expense"), Decimal("0"))
    by_day: dict[date, dict] = {
        d: {"expense": Decimal("0"), "income": Decimal("0")} for d in _month_days(year, mon)}
    for r in rows:
        by_day[r.bill_date][r.type] += r.amount

    return MonthlyStatsOut(
        month=month, income=income, expense=expense, net=income - expense,
        count=len(rows),
        days=[DayPoint(date=d, expense=v["expense"], income=v["income"])
              for d, v in by_day.items()])


@router.get("/categories", response_model=CategoryStatsOut)
def categories(month: str = "", type: str = "expense",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    month = month or today.strftime("%Y-%m")
    if type not in ("income", "expense"):
        raise HTTPException(400, "type 只能为 income 或 expense")
    year, mon = _parse_month(month)

    rows = db.execute(
        select(BillCategory.name, func.sum(Bill.amount))
        .join(Bill, Bill.category_id == BillCategory.id)
        .where(
            Bill.user_id == user.id,
            Bill.type == type,
            extract("year", Bill.bill_date) == year,
            extract("month", Bill.bill_date) == mon,
        )
        .group_by(BillCategory.name)
        .order_by(func.sum(Bill.amount).desc())
    ).all()

    total = sum((amount for _, amount in rows), Decimal("0"))
    items = [
        CategoryStatItem(
            category=name,
            amount=Decimal(str(amount)),
            ratio=round(float(Decimal(str(amount)) / total), 4) if total > 0 else 0.0)
        for name, amount in rows
    ]
    return CategoryStatsOut(month=month, type=type, total=total, items=items)


@router.get("/profile", response_model=ProfileStatsOut)
def profile_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """个人中心统计：账单条数、记账天数、便签数、未完成待办数。"""
    total_bills = db.scalar(select(func.count()).where(Bill.user_id == user.id)) or 0
    total_days = db.scalar(
        select(func.count(func.distinct(Bill.bill_date))).where(Bill.user_id == user.id)) or 0
    total_notes = db.scalar(select(func.count()).where(Note.user_id == user.id)) or 0
    pending_todos = db.scalar(select(func.count()).where(
        Note.user_id == user.id, Note.note_type == "todo", Note.status == "open")) or 0
    return ProfileStatsOut(total_bills=total_bills, total_days=total_days,
                           total_notes=total_notes, pending_todos=pending_todos)


@router.get("/channels", response_model=ChannelStatsOut)
def channels(month: str = "", type: str = "expense",
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """按支付渠道统计：金额、笔数、占比。month 为空表示全部时间。"""
    if type not in ("income", "expense"):
        raise HTTPException(400, "type 只能为 income 或 expense")
    conditions = [Bill.user_id == user.id, Bill.type == type]
    label = ""
    if month:
        year, mon = _parse_month(month)
        conditions += [extract("year", Bill.bill_date) == year,
                       extract("month", Bill.bill_date) == mon]
        label = month

    rows = db.execute(
        select(Bill.pay_channel, func.sum(Bill.amount), func.count())
        .where(*conditions)
        .group_by(Bill.pay_channel)).all()
    total = sum((Decimal(str(amount)) for _, amount, _ in rows), Decimal("0"))
    items = [
        ChannelStatItem(
            channel=(name or "未记录"),
            amount=Decimal(str(amount)),
            count=count,
            ratio=round(float(Decimal(str(amount)) / total), 4) if total > 0 else 0.0)
        for name, amount, count in rows
    ]
    items.sort(key=lambda i: i.amount, reverse=True)
    return ChannelStatsOut(month=label, type=type, total=total, items=items)
