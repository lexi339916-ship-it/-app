"""个人资产账本服务。

设计边界：
- 资产账户/负债由用户手动维护，不接真实银行、支付宝或微信账户；
- 余额变化必须写 asset_transactions，不允许只改余额不留痕；
- 账户间转账只写两条流水，不生成 Bill，因此不进入消费统计；
- 账单只有显式关联 account_id 且为新建/已关联编辑时才影响资产，旧账单补关联不追溯；
- 所有金额使用 Decimal / DECIMAL(14,2)，所有查询按 user_id 隔离。
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models import (
    AssetAccount, AssetLiability, AssetTransaction, Bill, User,
)
from app.schemas import (
    AssetAccountChangeIn, AssetAccountIn, AssetAccountOut, AssetAccountUpdateIn,
    AssetChangeAnalysisOut, AssetDeleteOut, AssetLiabilityAdjustIn,
    AssetLiabilityIn, AssetLiabilityOut, AssetLiabilityRepayIn,
    AssetLiabilityUpdateIn, AssetOverviewOut, AssetTransactionOut,
    AssetTransactionPageOut, AssetTransferIn, AssetTransferOut,
)

ASSET_TYPES = {"cash", "bank", "wechat", "alipay", "savings", "other"}
LIABILITY_TYPES = {"credit_card", "installment", "personal_loan", "other"}


def q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _parse_month(month: str) -> tuple[str, int, int]:
    month = (month or date.today().strftime("%Y-%m")).strip()
    try:
        year, mon = int(month[:4]), int(month[5:7])
        assert month[4] == "-" and 1 <= mon <= 12
    except (ValueError, AssertionError, IndexError):
        raise HTTPException(400, "月份格式应为 YYYY-MM")
    return f"{year:04d}-{mon:02d}", year, mon


def _get_account(db: Session, user: User, account_id: int,
                 active_only: bool = True, for_update: bool = False) -> AssetAccount:
    query = select(AssetAccount).where(
        AssetAccount.id == int(account_id), AssetAccount.user_id == user.id)
    if active_only:
        query = query.where(AssetAccount.is_active == 1)
    if for_update:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "资产账户不存在或不属于当前用户")
    return row


def _get_liability(db: Session, user: User, liability_id: int,
                   active_only: bool = True, for_update: bool = False) -> AssetLiability:
    query = select(AssetLiability).where(
        AssetLiability.id == int(liability_id),
        AssetLiability.user_id == user.id)
    if active_only:
        query = query.where(AssetLiability.is_active == 1)
    if for_update:
        query = query.with_for_update()
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "负债记录不存在或不属于当前用户")
    return row


def _account_out(row: AssetAccount) -> AssetAccountOut:
    return AssetAccountOut(
        id=row.id, name=row.name, type=row.type,
        institution=row.institution or "", account_hint=row.account_hint or "",
        balance=q2(row.balance), note=row.note or "",
        is_active=bool(row.is_active),
        created_at=row.created_at, updated_at=row.updated_at)


def _liability_out(row: AssetLiability) -> AssetLiabilityOut:
    days_left = (row.due_date - date.today()).days if row.due_date else None
    return AssetLiabilityOut(
        id=row.id, name=row.name, type=row.type,
        outstanding=q2(row.outstanding), due_date=row.due_date,
        remark=row.remark or "", status=row.status or "active",
        is_active=bool(row.is_active), days_left=days_left,
        is_overdue=bool(days_left is not None and days_left < 0
                        and q2(row.outstanding) > 0),
        created_at=row.created_at, updated_at=row.updated_at)


def _post_account_tx(db: Session, account: AssetAccount, type_: str,
                     direction: str, amount: Decimal, note: str,
                     source: str = "manual", related_bill_id: int | None = None,
                     transfer_group_id: str = "") -> AssetTransaction:
    amount = q2(amount)
    if amount <= 0:
        raise HTTPException(400, "变动金额必须大于 0")
    before = q2(account.balance)
    after = q2(before + amount) if direction == "in" else q2(before - amount)
    if after < 0:
        raise HTTPException(409, "账户余额不足，无法完成本次变动")
    account.balance = after
    tx = AssetTransaction(
        user_id=account.user_id, account_id=account.id, type=type_,
        direction=direction, amount=amount, before_amount=before,
        after_amount=after, note=(note or "")[:200], source=source,
        related_bill_id=related_bill_id,
        transfer_group_id=(transfer_group_id or "")[:40],
        status="posted")
    db.add(tx)
    db.flush()
    return tx


def _post_liability_tx(db: Session, liability: AssetLiability, type_: str,
                       direction: str, amount: Decimal, note: str,
                       source: str = "manual", transfer_group_id: str = "") -> AssetTransaction:
    amount = q2(amount)
    if amount <= 0:
        raise HTTPException(400, "变动金额必须大于 0")
    before = q2(liability.outstanding)
    after = q2(before + amount) if direction == "in" else q2(before - amount)
    if after < 0:
        raise HTTPException(409, "还款金额不能超过当前欠款")
    liability.outstanding = after
    liability.status = "repaid" if after == 0 else "active"
    tx = AssetTransaction(
        user_id=liability.user_id, liability_id=liability.id, type=type_,
        direction=direction, amount=amount, before_amount=before,
        after_amount=after, note=(note or "")[:200], source=source,
        transfer_group_id=(transfer_group_id or "")[:40], status="posted")
    db.add(tx)
    db.flush()
    return tx


# ---------------- 账户 ----------------

def create_account(db: Session, user: User, data: AssetAccountIn) -> AssetAccountOut:
    if data.type not in ASSET_TYPES:
        raise HTTPException(400, "资产类型不正确")
    row = AssetAccount(
        user_id=user.id, name=data.name.strip(), type=data.type,
        institution=(data.institution or "").strip(),
        account_hint=(data.account_hint or "").strip()[-4:],
        balance=Decimal("0"), note=(data.note or "").strip(), is_active=1)
    db.add(row)
    db.flush()
    if q2(data.balance) > 0:
        _post_account_tx(
            db, row, "opening", "in", q2(data.balance),
            "初始余额", source="manual")
    db.commit()
    db.refresh(row)
    return _account_out(row)


def update_account(db: Session, user: User, account_id: int,
                   data: AssetAccountUpdateIn) -> AssetAccountOut:
    row = _get_account(db, user, account_id)
    row.name = data.name.strip()
    row.type = data.type
    row.institution = (data.institution or "").strip()
    row.account_hint = (data.account_hint or "").strip()[-4:]
    row.note = (data.note or "").strip()
    db.commit()
    db.refresh(row)
    return _account_out(row)


def adjust_account(db: Session, user: User, account_id: int,
                   data: AssetAccountChangeIn) -> AssetAccountOut:
    row = _get_account(db, user, account_id, for_update=True)
    before = q2(row.balance)
    if data.kind in ("increase", "decrease"):
        amount = q2(data.amount or 0)
        if amount <= 0:
            raise HTTPException(400, "请填写大于 0 的变动金额")
        direction = "in" if data.kind == "increase" else "out"
        type_ = "manual_in" if direction == "in" else "manual_out"
    else:
        if data.target_balance is None:
            raise HTTPException(400, "请填写调整后的余额")
        target = q2(data.target_balance)
        if target < 0:
            raise HTTPException(400, "余额不能小于 0")
        delta = q2(target - before)
        if delta == 0:
            return _account_out(row)
        amount = abs(delta)
        direction = "in" if delta > 0 else "out"
        type_ = "adjustment"
    _post_account_tx(db, row, type_, direction, amount,
                     data.note or ("余额调整" if type_ == "adjustment" else "手动变动"),
                     source="manual")
    db.commit()
    db.refresh(row)
    return _account_out(row)


def archive_account(db: Session, user: User, account_id: int) -> AssetDeleteOut:
    row = _get_account(db, user, account_id)
    tx_count = int(db.scalar(select(func.count()).where(
        AssetTransaction.user_id == user.id,
        AssetTransaction.account_id == row.id)) or 0)
    opening_count = int(db.scalar(select(func.count()).where(
        AssetTransaction.user_id == user.id,
        AssetTransaction.account_id == row.id,
        AssetTransaction.type == "opening")) or 0)
    bill_refs = int(db.scalar(select(func.count()).where(
        Bill.user_id == user.id, Bill.account_id == row.id)) or 0)
    # 只有初始余额、没有其他流水/账单引用时可以直接删除；否则归档，保留历史
    has_activity = tx_count > opening_count or bill_refs > 0
    if has_activity:
        row.is_active = 0
        db.commit()
        return AssetDeleteOut(ok=True, archived=True,
                              message="账户已停用，历史流水保留")
    db.query(AssetTransaction).filter(
        AssetTransaction.user_id == user.id,
        AssetTransaction.account_id == row.id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return AssetDeleteOut(ok=True, archived=False, message="账户已删除")


def transfer(db: Session, user: User, data: AssetTransferIn) -> AssetTransferOut:
    if int(data.from_account_id) == int(data.to_account_id):
        raise HTTPException(400, "转出账户和转入账户不能相同")
    amount = q2(data.amount)
    if amount <= 0:
        raise HTTPException(400, "转账金额必须大于 0")
    ids = sorted({int(data.from_account_id), int(data.to_account_id)})
    rows = db.scalars(select(AssetAccount).where(
        AssetAccount.user_id == user.id,
        AssetAccount.id.in_(ids),
        AssetAccount.is_active == 1,
    ).order_by(AssetAccount.id).with_for_update()).all()
    by_id = {r.id: r for r in rows}
    src = by_id.get(int(data.from_account_id))
    dst = by_id.get(int(data.to_account_id))
    if src is None or dst is None:
        raise HTTPException(404, "转出或转入账户不存在")
    group = uuid.uuid4().hex
    out_tx = _post_account_tx(
        db, src, "transfer_out", "out", amount,
        data.note or f"转账至「{dst.name}」", source="manual",
        transfer_group_id=group)
    in_tx = _post_account_tx(
        db, dst, "transfer_in", "in", amount,
        data.note or f"来自「{src.name}」", source="manual",
        transfer_group_id=group)
    db.commit()
    db.refresh(src)
    db.refresh(dst)
    db.refresh(out_tx)
    db.refresh(in_tx)
    return AssetTransferOut(
        ok=True, transfer_group_id=group,
        from_account=_account_out(src), to_account=_account_out(dst),
        transactions=[_tx_out(out_tx), _tx_out(in_tx)])


# ---------------- 负债 ----------------

def create_liability(db: Session, user: User, data: AssetLiabilityIn) -> AssetLiabilityOut:
    if data.type not in LIABILITY_TYPES:
        raise HTTPException(400, "负债类型不正确")
    row = AssetLiability(
        user_id=user.id, name=data.name.strip(), type=data.type,
        outstanding=Decimal("0"), due_date=data.due_date,
        remark=(data.remark or "").strip(), status="active", is_active=1)
    db.add(row)
    db.flush()
    _post_liability_tx(db, row, "liability_increase", "in",
                       q2(data.outstanding), "初始欠款", source="manual")
    db.commit()
    db.refresh(row)
    return _liability_out(row)


def update_liability(db: Session, user: User, liability_id: int,
                     data: AssetLiabilityUpdateIn) -> AssetLiabilityOut:
    row = _get_liability(db, user, liability_id)
    row.name = data.name.strip()
    row.type = data.type
    row.due_date = data.due_date
    row.remark = (data.remark or "").strip()
    db.commit()
    db.refresh(row)
    return _liability_out(row)


def adjust_liability(db: Session, user: User, liability_id: int,
                     data: AssetLiabilityAdjustIn) -> AssetLiabilityOut:
    row = _get_liability(db, user, liability_id, for_update=True)
    target = q2(data.target_outstanding)
    before = q2(row.outstanding)
    delta = q2(target - before)
    if delta == 0:
        return _liability_out(row)
    _post_liability_tx(
        db, row, "liability_adjustment", "in" if delta > 0 else "out",
        abs(delta), data.note or "欠款调整", source="manual")
    db.commit()
    db.refresh(row)
    return _liability_out(row)


def repay_liability(db: Session, user: User, liability_id: int,
                    data: AssetLiabilityRepayIn) -> AssetLiabilityOut:
    liability = _get_liability(db, user, liability_id, for_update=True)
    account = _get_account(db, user, data.account_id, for_update=True)
    amount = q2(data.amount)
    if amount <= 0:
        raise HTTPException(400, "还款金额必须大于 0")
    if amount > q2(liability.outstanding):
        raise HTTPException(409, "还款金额不能超过当前欠款")
    group = uuid.uuid4().hex
    _post_account_tx(
        db, account, "liability_repay", "out", amount,
        data.note or f"偿还「{liability.name}」", source="manual",
        transfer_group_id=group)
    _post_liability_tx(
        db, liability, "liability_repay", "out", amount,
        data.note or f"从「{account.name}」还款", source="manual",
        transfer_group_id=group)
    db.commit()
    db.refresh(liability)
    return _liability_out(liability)


def archive_liability(db: Session, user: User, liability_id: int) -> AssetDeleteOut:
    row = _get_liability(db, user, liability_id)
    tx_count = int(db.scalar(select(func.count()).where(
        AssetTransaction.user_id == user.id,
        AssetTransaction.liability_id == row.id)) or 0)
    has_activity = tx_count > 1
    if has_activity:
        row.is_active = 0
        db.commit()
        return AssetDeleteOut(ok=True, archived=True,
                              message="负债已停用，历史流水保留")
    db.query(AssetTransaction).filter(
        AssetTransaction.user_id == user.id,
        AssetTransaction.liability_id == row.id).delete(synchronize_session=False)
    db.delete(row)
    db.commit()
    return AssetDeleteOut(ok=True, archived=False, message="负债已删除")


# ---------------- 总览与流水 ----------------

def overview(db: Session, user: User) -> AssetOverviewOut:
    accounts = db.scalars(select(AssetAccount).where(
        AssetAccount.user_id == user.id, AssetAccount.is_active == 1)
        .order_by(AssetAccount.type, AssetAccount.id)).all()
    liabilities = db.scalars(select(AssetLiability).where(
        AssetLiability.user_id == user.id, AssetLiability.is_active == 1)
        .order_by(AssetLiability.status, AssetLiability.due_date,
                  AssetLiability.id)).all()
    total_assets = q2(sum((q2(r.balance) for r in accounts), Decimal("0")))
    total_liabilities = q2(sum((q2(r.outstanding) for r in liabilities
                                if r.status == "active"), Decimal("0")))
    latest_tx = db.scalar(select(func.max(AssetTransaction.created_at)).where(
        AssetTransaction.user_id == user.id))
    timestamps = [r.updated_at for r in accounts] + [r.updated_at for r in liabilities]
    if latest_tx:
        timestamps.append(latest_tx)
    return AssetOverviewOut(
        total_assets=total_assets, total_liabilities=total_liabilities,
        net_worth=q2(total_assets - total_liabilities),
        account_count=len(accounts), liability_count=len(liabilities),
        accounts=[_account_out(r) for r in accounts],
        liabilities=[_liability_out(r) for r in liabilities],
        last_updated_at=max(timestamps) if timestamps else None,
        as_of=datetime.now(), has_data=bool(accounts or liabilities))


def _tx_maps(db: Session, user: User, rows: list[AssetTransaction]):
    account_ids = {r.account_id for r in rows if r.account_id}
    liability_ids = {r.liability_id for r in rows if r.liability_id}
    accounts = {}
    if account_ids:
        accounts = {r.id: r.name for r in db.scalars(select(AssetAccount).where(
            AssetAccount.user_id == user.id, AssetAccount.id.in_(account_ids))).all()}
    liabilities = {}
    if liability_ids:
        liabilities = {r.id: r.name for r in db.scalars(select(AssetLiability).where(
            AssetLiability.user_id == user.id,
            AssetLiability.id.in_(liability_ids))).all()}
    return accounts, liabilities


def _tx_out(row: AssetTransaction, account_names: dict | None = None,
            liability_names: dict | None = None) -> AssetTransactionOut:
    account_names = account_names or {}
    liability_names = liability_names or {}
    return AssetTransactionOut(
        id=row.id, account_id=row.account_id, liability_id=row.liability_id,
        account_name=account_names.get(row.account_id, ""),
        liability_name=liability_names.get(row.liability_id, ""),
        type=row.type, direction=row.direction, amount=q2(row.amount),
        before_amount=q2(row.before_amount), after_amount=q2(row.after_amount),
        note=row.note or "", source=row.source,
        related_bill_id=row.related_bill_id,
        transfer_group_id=row.transfer_group_id or "", status=row.status,
        created_at=row.created_at)


def list_transactions(db: Session, user: User, account_id: int | None = None,
                      liability_id: int | None = None, type_: str = "",
                      month: str = "", page: int = 1,
                      page_size: int = 20) -> AssetTransactionPageOut:
    conditions = [AssetTransaction.user_id == user.id]
    if account_id is not None:
        conditions.append(AssetTransaction.account_id == int(account_id))
    if liability_id is not None:
        conditions.append(AssetTransaction.liability_id == int(liability_id))
    if type_:
        conditions.append(AssetTransaction.type == type_)
    if month:
        _, year, mon = _parse_month(month)
        conditions.append(extract("year", AssetTransaction.created_at) == year)
        conditions.append(extract("month", AssetTransaction.created_at) == mon)
    total = int(db.scalar(select(func.count()).where(*conditions)) or 0)
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), 100))
    rows = db.scalars(
        select(AssetTransaction).where(*conditions)
        .order_by(AssetTransaction.created_at.desc(), AssetTransaction.id.desc())
        .offset((page - 1) * page_size).limit(page_size)).all()
    accounts, liabilities = _tx_maps(db, user, rows)
    return AssetTransactionPageOut(
        items=[_tx_out(r, accounts, liabilities) for r in rows],
        total=total, page=page, page_size=page_size)


def change_analysis(db: Session, user: User, month: str = "") -> AssetChangeAnalysisOut:
    month, year, mon = _parse_month(month)
    accounts_count = int(db.scalar(select(func.count()).where(
        AssetAccount.user_id == user.id, AssetAccount.is_active == 1)) or 0)
    liabilities_count = int(db.scalar(select(func.count()).where(
        AssetLiability.user_id == user.id, AssetLiability.is_active == 1)) or 0)
    rows = db.scalars(select(AssetTransaction).where(
        AssetTransaction.user_id == user.id,
        extract("year", AssetTransaction.created_at) == year,
        extract("month", AssetTransaction.created_at) == mon,
    )).all()

    components = {
        "consumption": Decimal("0"), "income": Decimal("0"),
        "transfer": Decimal("0"), "liability": Decimal("0"),
        "manual": Decimal("0"),
    }
    transfer_gross = Decimal("0")
    transfer_ids: set[str] = set()
    for row in rows:
        signed = q2(row.after_amount) - q2(row.before_amount)
        if row.account_id:
            if row.type == "bill_expense":
                components["consumption"] += signed
            elif row.type == "bill_reversal":
                # 支出冲正方向为 in，收入冲正方向为 out
                if row.direction == "in":
                    components["consumption"] += signed
                else:
                    components["income"] += signed
            elif row.type == "bill_income":
                components["income"] += signed
            elif row.type in ("transfer_in", "transfer_out"):
                components["transfer"] += signed
                transfer_gross += q2(row.amount)
                if row.transfer_group_id:
                    transfer_ids.add(row.transfer_group_id)
            elif row.type == "liability_repay":
                components["liability"] += signed
            else:
                components["manual"] += signed
        if row.liability_id:
            if row.type in ("liability_increase", "liability_repay",
                            "liability_adjustment"):
                components["liability"] -= signed
            elif row.type == "bill_expense":
                components["consumption"] -= signed

    total_expense = q2(db.scalar(select(func.coalesce(func.sum(Bill.amount), 0)).where(
        Bill.user_id == user.id, Bill.type == "expense",
        extract("year", Bill.bill_date) == year,
        extract("month", Bill.bill_date) == mon)) or 0)
    linked_expense = q2(db.scalar(select(func.coalesce(func.sum(Bill.amount), 0)).where(
        Bill.user_id == user.id, Bill.type == "expense",
        Bill.account_id.is_not(None),
        extract("year", Bill.bill_date) == year,
        extract("month", Bill.bill_date) == mon)) or 0)
    unlinked_expense = q2(total_expense - linked_expense)
    coverage = round(float(linked_expense / total_expense), 4) if total_expense > 0 else 0.0
    net_change = q2(sum(components.values(), Decimal("0")))
    has_data = bool(accounts_count or liabilities_count)
    if not has_data:
        message = "还没有维护资产账户，先到资产管理页添加账户和负债。"
    else:
        message = (f"{month} 净资产变动 ¥{net_change}；消费影响 ¥{components['consumption']}，"
                   f"收入影响 ¥{components['income']}，负债影响 ¥{components['liability']}，"
                   f"手动调整 ¥{components['manual']}；转账净影响 ¥{components['transfer']}。")
        if unlinked_expense > 0:
            message += f" 另有 ¥{unlinked_expense} 支出未关联账户，未计入资产变动。"
    return AssetChangeAnalysisOut(
        month=month, net_worth_change=net_change, components=components,
        linked_expense=linked_expense, total_expense=total_expense,
        unlinked_expense=unlinked_expense, coverage_ratio=coverage,
        has_data=has_data, transfer_count=len(transfer_ids),
        transfer_gross=q2(transfer_gross), message=message,
        as_of=datetime.now())


# ---------------- 账单联动 ----------------

def post_bill_movement(db: Session, user: User, bill: Bill) -> None:
    """新建账单关联账户时记账；由账单路由在同一事务内调用。"""
    if not bill.account_id:
        return
    account = _get_account(db, user, bill.account_id, for_update=True)
    direction = "out" if bill.type == "expense" else "in"
    type_ = "bill_expense" if bill.type == "expense" else "bill_income"
    _post_account_tx(
        db, account, type_, direction, q2(bill.amount),
        bill.remark or "账单", source="bill", related_bill_id=bill.id)


def reverse_bill_movements(db: Session, user: User, bill: Bill) -> int:
    """冲正某笔账单产生且仍有效的账户流水；返回冲正条数。

    保留原流水并追加 bill_reversal，便于审计；由账单路由在同一事务内调用。
    """
    rows = db.scalars(select(AssetTransaction).where(
        AssetTransaction.user_id == user.id,
        AssetTransaction.related_bill_id == bill.id,
        AssetTransaction.account_id.is_not(None),
        AssetTransaction.status == "posted",
        AssetTransaction.type.in_(("bill_expense", "bill_income")),
    ).order_by(AssetTransaction.id)).all()
    for row in rows:
        account = _get_account(db, user, row.account_id, active_only=False,
                               for_update=True)
        row.status = "reversed"
        _post_account_tx(
            db, account, "bill_reversal",
            "in" if row.direction == "out" else "out",
            q2(row.amount), f"冲正：{row.note or '账单'}",
            source="bill", related_bill_id=bill.id)
    return len(rows)
