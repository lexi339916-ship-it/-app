"""储蓄目标接口：进度与预计完成时间均由后端计算（模型不参与算术）。"""
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select, update
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Bill, GoalDeposit, SavingsGoal, User
from app.schemas import GoalDepositIn, GoalDepositOut, GoalIn, GoalOut

router = APIRouter()


def _avg_monthly_net(db: Session, user_id: int, months: int = 3) -> Decimal:
    """近 N 个自然月（含本月）的平均月结余，用于估算目标完成时间。"""
    today = date.today()
    total_net = Decimal("0")
    for i in range(months):
        year, month = today.year, today.month - i
        while month < 1:
            year, month = year - 1, month + 12
        cond = [Bill.user_id == user_id,
                extract("year", Bill.bill_date) == year,
                extract("month", Bill.bill_date) == month]
        income = Decimal(str(db.scalar(
            select(func.coalesce(func.sum(Bill.amount), 0))
            .where(*cond, Bill.type == "income")) or 0))
        expense = Decimal(str(db.scalar(
            select(func.coalesce(func.sum(Bill.amount), 0))
            .where(*cond, Bill.type == "expense")) or 0))
        total_net += income - expense
    return (total_net / months).quantize(Decimal("0.01"))


def _to_out(db: Session, user_id: int, row: SavingsGoal) -> GoalOut:
    avg_net = _avg_monthly_net(db, user_id)
    saved = Decimal(str(row.saved_amount))
    target = Decimal(str(row.target_amount))
    remaining = max(Decimal("0"), target - saved)
    ratio = float(saved / target) if target > 0 else 0.0
    estimated = None
    if remaining <= 0:
        estimated = "已达成"
    elif avg_net > 0:
        days_needed = int(remaining / avg_net * 30)
        estimated = (date.today() + timedelta(days=max(1, days_needed))).isoformat()
    return GoalOut(
        id=row.id, name=row.name, target_amount=target, saved_amount=saved,
        remaining=remaining, progress_ratio=round(ratio, 4),
        estimated_finish=estimated, avg_monthly_net=avg_net,
        target_months=row.target_months, target_date=row.target_date)


def _get_owned(db: Session, user: User, goal_id: int) -> SavingsGoal:
    row = db.get(SavingsGoal, goal_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "目标不存在")
    return row


@router.get("", response_model=list[GoalOut])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(SavingsGoal).where(SavingsGoal.user_id == user.id)
                      .order_by(SavingsGoal.created_at.desc())).all()
    return [_to_out(db, user.id, r) for r in rows]


@router.post("", response_model=GoalOut)
def create_goal(data: GoalIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = SavingsGoal(user_id=user.id, name=data.name,
                      target_amount=data.target_amount, saved_amount=Decimal("0"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(db, user.id, row)


@router.post("/{goal_id}/deposit", response_model=GoalOut)
def deposit(goal_id: int, data: GoalDepositIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """存入一笔：累加已存金额，同时写入单笔记录（便于事后修改/删除）。"""
    row = _get_owned(db, user, goal_id)
    # 原子自增，避免并发存入时读改写丢失更新
    db.execute(update(SavingsGoal).where(
        SavingsGoal.id == row.id, SavingsGoal.user_id == user.id
    ).values(saved_amount=SavingsGoal.saved_amount + data.amount))
    db.add(GoalDeposit(goal_id=row.id, user_id=user.id, amount=data.amount))
    db.commit()
    db.refresh(row)
    return _to_out(db, user.id, row)


# ---------------- 存入记录（改/删某一笔） ----------------

@router.get("/{goal_id}/deposits", response_model=list[GoalDepositOut])
def list_deposits(goal_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """某目标的全部存入记录，新的在前。"""
    _get_owned(db, user, goal_id)
    return db.scalars(select(GoalDeposit)
                      .where(GoalDeposit.goal_id == goal_id,
                             GoalDeposit.user_id == user.id)
                      .order_by(GoalDeposit.created_at.desc())).all()


def _get_owned_deposit(db: Session, user: User, deposit_id: int) -> GoalDeposit:
    row = db.get(GoalDeposit, deposit_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "存入记录不存在")
    return row


@router.put("/deposits/{deposit_id}", response_model=GoalDepositOut)
def update_deposit(deposit_id: int, data: GoalDepositIn,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """修改某一笔存入金额：目标的已存金额按差额同步调整。"""
    dep = _get_owned_deposit(db, user, deposit_id)
    goal = _get_owned(db, user, dep.goal_id)
    old = Decimal(str(dep.amount))
    goal.saved_amount = Decimal(str(goal.saved_amount)) - old + data.amount
    if goal.saved_amount < 0:
        raise HTTPException(400, "金额不能小于 0")
    dep.amount = data.amount
    db.commit()
    db.refresh(dep)
    return dep


@router.delete("/deposits/{deposit_id}")
def delete_deposit(deposit_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """删除某一笔存入：目标的已存金额同步扣减。"""
    dep = _get_owned_deposit(db, user, deposit_id)
    goal = _get_owned(db, user, dep.goal_id)
    goal.saved_amount = max(Decimal("0"),
                            Decimal(str(goal.saved_amount)) - Decimal(str(dep.amount)))
    db.delete(dep)
    db.commit()
    return {"ok": True}


@router.delete("/{goal_id}")
def delete_goal(goal_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = _get_owned(db, user, goal_id)
    # 级联删掉该目标的所有存入记录
    db.query(GoalDeposit).filter(GoalDeposit.goal_id == row.id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}
