"""自动订阅扣费接口。

业务约束：
- 订阅由用户手动录入，后端不联网查询 QQ 音乐 / 网易云等平台的真实续费状态；
- 每次进入账单页（或打开小程序）调用 /sync，后端按**服务器日期**判断：
  1）已到本月扣费日且本月未生成过账单 → 自动生成一笔支出账单（计入收支统计）；
  2）明天是扣费日 → 返回提醒项，由前端弹窗提示（每月只提醒一次）；
- 暂停（paused）的订阅不参与自动记账与提醒。
"""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Bill, BillCategory, Subscription, SubscriptionBilling, User
from app.schemas import (
    SubscriptionIn, SubscriptionOut, SubscriptionReminder, SubscriptionSyncOut,
)

router = APIRouter()


# ---------------- 日期工具 ----------------

def _last_day(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _charge_date(year: int, month: int, day_of_month: int) -> date:
    """每月扣费日：小月自动收敛到当月最后一天（如 2 月 31 日 → 2 月 28/29 日）。"""
    return date(year, month, min(day_of_month, _last_day(year, month)))


def _next_charge(today: date, day_of_month: int) -> date:
    """下一个扣费日：本月未到则取本月，已过（不含今天）则取下个月。"""
    cur = _charge_date(today.year, today.month, day_of_month)
    if cur >= today:
        return cur
    year, month = today.year, today.month + 1
    if month > 12:
        year, month = year + 1, 1
    return _charge_date(year, month, day_of_month)


# ---------------- 通用 ----------------

def _resolve_expense_category(db: Session, user: User) -> int | None:
    """未指定分类时的兜底：计入「其他」支出分类；若被删则退化为任一支出分类。"""
    row = db.scalar(select(BillCategory).where(
        BillCategory.name == "其他",
        BillCategory.type == "expense",
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    ).limit(1))
    if row is None:
        row = db.scalar(select(BillCategory).where(
            BillCategory.type == "expense",
            (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
        ).limit(1))
    return row.id if row else None


def _valid_expense_category_ids(db: Session, user: User) -> set[int]:
    """当前用户可用的全部支出分类 id（系统预置 + 自定义），用于校验订阅分类是否仍有效。"""
    return set(db.scalars(select(BillCategory.id).where(
        BillCategory.type == "expense",
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    )).all())


def _check_category_id(db: Session, user: User, category_id: int | None) -> int | None:
    """保存订阅时校验分类：必须存在、为支出类型且当前用户可见；为空表示归入「其他」。"""
    if category_id is None:
        return None
    if category_id not in _valid_expense_category_ids(db, user):
        raise HTTPException(400, "所选支出分类不存在或不可用")
    return category_id


def _get_owned(db: Session, user: User, sub_id: int) -> Subscription:
    row = db.get(Subscription, sub_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "订阅不存在")
    return row


def _to_out(row: Subscription, today: date) -> SubscriptionOut:
    nxt = _next_charge(today, row.day_of_month)
    return SubscriptionOut(
        id=row.id, name=row.name, day_of_month=row.day_of_month,
        amount=Decimal(str(row.amount)), category_id=row.category_id,
        previous_amount=(Decimal(str(row.previous_amount))
                         if row.previous_amount is not None else None),
        usage_90d=int(row.usage_90d or 0),
        remark=row.remark or "",
        remind_enabled=bool(row.remind_enabled), status=row.status,
        next_charge_date=nxt, days_left=(nxt - today).days,
        last_billed_month=row.last_billed_month or "",
        created_at=row.created_at)


# ---------------- 进页面同步（自动记账 + 提醒） ----------------

def _next_month(month_key: str) -> str:
    year, month = int(month_key[:4]), int(month_key[5:7]) + 1
    if month > 12:
        year, month = year + 1, 1
    return f"{year:04d}-{month:02d}"


def _iter_months(start: str, end: str):
    year, month = int(start[:4]), int(start[5:7])
    end_year, end_month = int(end[:4]), int(end[5:7])
    while (year, month) <= (end_year, end_month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month > 12:
            year, month = year + 1, 1


@router.post("/sync", response_model=SubscriptionSyncOut)
def sync(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    month_key = today.strftime("%Y-%m")
    rows = db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()

    created_count = 0
    created_amount = Decimal("0")
    reminders: list[SubscriptionReminder] = []
    default_category_id = _resolve_expense_category(db, user)
    valid_category_ids = _valid_expense_category_ids(db, user)
    active_count = 0

    for sub in rows:
        if sub.status != "active":
            continue
        active_count += 1

        # 从上次已记账月份的下一个月开始补；首次使用只处理当前月，避免回溯太久
        start = _next_month(sub.last_billed_month) if sub.last_billed_month else month_key
        if start > month_key:
            start = month_key
        for month in _iter_months(start, month_key):
            charge = _charge_date(int(month[:4]), int(month[5:7]), sub.day_of_month)
            # 当前月还没到扣费日：先不生成，等到了再补
            if month == month_key and today < charge:
                continue

            billing = db.scalar(select(SubscriptionBilling.id).where(
                SubscriptionBilling.subscription_id == sub.id,
                SubscriptionBilling.month == month).limit(1))
            if billing:
                sub.last_billed_month = month
                continue

            # 兼容旧版本已生成、但没有计费记录的账单，避免重复
            existing_bill = db.scalar(select(Bill).where(
                Bill.user_id == user.id, Bill.source == "subscription",
                Bill.remark.like(f"{sub.name} · 自动订阅扣费%"),
                extract("year", Bill.bill_date) == int(month[:4]),
                extract("month", Bill.bill_date) == int(month[5:7]),
            ).order_by(Bill.id.desc()).limit(1))
            if existing_bill:
                try:
                    with db.begin_nested():
                        db.add(SubscriptionBilling(
                            user_id=user.id, subscription_id=sub.id, month=month,
                            bill_id=existing_bill.id, amount=existing_bill.amount))
                        db.flush()
                except IntegrityError:
                    pass
                sub.last_billed_month = month
                continue

            category_id = (sub.category_id if sub.category_id in valid_category_ids
                           else None) or default_category_id
            remark = f"{sub.name} · 自动订阅扣费"
            if sub.remark:
                remark += f"（{sub.remark}）"
            try:
                with db.begin_nested():
                    bill = Bill(
                        user_id=user.id, category_id=category_id, type="expense",
                        amount=Decimal(str(sub.amount)), bill_date=charge,
                        remark=remark[:200], source="subscription")
                    db.add(bill)
                    db.flush()
                    db.add(SubscriptionBilling(
                        user_id=user.id, subscription_id=sub.id, month=month,
                        bill_id=bill.id, amount=Decimal(str(sub.amount))))
                    db.flush()
            except IntegrityError:
                # 并发 sync 已由另一个请求写入，跳过
                continue
            sub.last_billed_month = month
            created_count += 1
            created_amount += Decimal(str(sub.amount))

        # 扣费前 1 天提醒：同一扣费月只提醒一次
        if sub.remind_enabled:
            nxt = _next_charge(today, sub.day_of_month)
            if (nxt - today).days == 1:
                remind_key = nxt.strftime("%Y-%m")
                if sub.remind_month != remind_key:
                    sub.remind_month = remind_key
                    reminders.append(SubscriptionReminder(
                        id=sub.id, name=sub.name, amount=Decimal(str(sub.amount)),
                        charge_date=nxt, days_left=1, remark=sub.remark or ""))

    db.commit()
    return SubscriptionSyncOut(
        created_count=created_count,
        created_amount=created_amount.quantize(Decimal("0.01")),
        active_count=active_count, reminders=reminders)


# ---------------- CRUD ----------------

@router.get("", response_model=list[SubscriptionOut])
def list_subscriptions(user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    today = date.today()
    rows = db.scalars(select(Subscription).where(Subscription.user_id == user.id)
                      .order_by(Subscription.status, Subscription.day_of_month)).all()
    return [_to_out(r, today) for r in rows]


@router.post("", response_model=SubscriptionOut)
def create_subscription(data: SubscriptionIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    row = Subscription(
        user_id=user.id, name=data.name.strip(), day_of_month=data.day_of_month,
        amount=data.amount, category_id=_check_category_id(db, user, data.category_id),
        previous_amount=None,
        usage_90d=int(data.usage_90d if data.usage_90d is not None else 5),
        remark=data.remark, remind_enabled=1 if data.remind_enabled else 0,
        status="active", last_billed_month="", remind_month="")
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row, date.today())


@router.put("/{sub_id}", response_model=SubscriptionOut)
def update_subscription(sub_id: int, data: SubscriptionIn,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    row = _get_owned(db, user, sub_id)
    row.name = data.name.strip()
    row.day_of_month = data.day_of_month
    # 改价时保留旧价格，订阅体检才能发现“涨价”
    if Decimal(str(data.amount)) != Decimal(str(row.amount)):
        row.previous_amount = row.amount
    row.amount = data.amount
    row.category_id = _check_category_id(db, user, data.category_id)
    if data.usage_90d is not None:
        row.usage_90d = int(data.usage_90d)
    row.remark = data.remark
    row.remind_enabled = 1 if data.remind_enabled else 0
    db.commit()
    db.refresh(row)
    return _to_out(row, date.today())


@router.post("/{sub_id}/toggle", response_model=SubscriptionOut)
def toggle_subscription(sub_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """暂停 / 恢复：暂停后不再自动生成月度账单，也不弹扣费提醒。"""
    row = _get_owned(db, user, sub_id)
    row.status = "paused" if row.status == "active" else "active"
    db.commit()
    db.refresh(row)
    return _to_out(row, date.today())


@router.delete("/{sub_id}")
def delete_subscription(sub_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """删除订阅项：已自动生成的历史账单保留（属于真实支出记录）。"""
    row = _get_owned(db, user, sub_id)
    db.delete(row)
    db.commit()
    return {"ok": True}
