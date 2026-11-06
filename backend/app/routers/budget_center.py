"""AI 消费预警 & 预算中心接口。

包含：分类月度预算设置、记账后预警检查（80%/100%/异常大额）、
AI 预算推荐与自然语言目标分配、弹性调度建议、待办计划采购联动、预警消息中心。

设计约束：
- 不改动账单录入与 OCR 代码，预警由前端在记账保存成功后调用 /check 触发；
- 所有 AI 能力都有规则/模板降级，AI 未配置或超限时功能仍可用；
- 所有操作校验数据归属（用户隔离）。
"""
import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import extract, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import (
    Bill, BillCategory, Budget, BudgetAlert, BudgetPlan, CategoryBudget, Note, User,
)
from app.schemas import (
    AlertActionIn, AlertOut, AlertPageOut, BillCheckIn, BillCheckOut,
    BudgetOverviewOut, BudgetPlanItem, BudgetPlanOut, CategoryBudgetBatchIn,
    CategoryBudgetIn, CategoryBudgetItem, GoalAllocateIn, PlannedPurchaseOut,
    RebalanceSuggestion,
)
from app.services import ai_service, budget_ai
from app.services.ai_service import AIServiceError

router = APIRouter()

# 异常大额判定参数：近 180 天历史、至少 5 笔样本、金额下限 50 元
ANOMALY_DAYS = 180
ANOMALY_MIN_SAMPLES = 5
ANOMALY_MIN_AMOUNT = Decimal("50")
# 弹性调度：使用率 >= 80% 视为紧缺，<= 50% 且剩余 >= 100 视为可调配
REBALANCE_TIGHT = 0.8
REBALANCE_SURPLUS = 0.5
REBALANCE_MIN_REMAINING = Decimal("100")


# ---------------- 公共工具 ----------------

def _check_month(month: str) -> tuple[int, int]:
    """校验并拆解 YYYY-MM 月份。"""
    try:
        year, mon = int(month[:4]), int(month[5:7])
        assert 1 <= mon <= 12
        return year, mon
    except (ValueError, AssertionError):
        raise HTTPException(400, "月份格式应为 YYYY-MM")


def _spent_map(db: Session, user_id: int, month: str) -> dict[int, Decimal]:
    """某月各分类已花金额：{category_id: 支出合计}。"""
    year, mon = _check_month(month)
    rows = db.execute(
        select(Bill.category_id, func.coalesce(func.sum(Bill.amount), 0))
        .where(Bill.user_id == user_id, Bill.type == "expense",
               extract("year", Bill.bill_date) == year,
               extract("month", Bill.bill_date) == mon)
        .group_by(Bill.category_id)
    ).all()
    return {cid: Decimal(str(total)) for cid, total in rows if cid is not None}


def _visible_categories(db: Session, user: User, type_: str = "expense") -> list[BillCategory]:
    """用户可见的分类（系统预置 + 自己创建）。"""
    return db.scalars(select(BillCategory).where(
        BillCategory.type == type_,
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    )).all()


def _get_owned_alert(db: Session, user: User, alert_id: int) -> BudgetAlert:
    row = db.get(BudgetAlert, alert_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "消息不存在")
    return row


def _to_alert_out(db: Session, row: BudgetAlert) -> AlertOut:
    """ORM → 输出契约；category 优先查表，anomaly 的分类名放在 payload 里。"""
    try:
        payload = json.loads(row.payload) if row.payload else {}
    except json.JSONDecodeError:
        payload = {}
    category = payload.get("category", "")
    if row.category_id:
        cat = db.get(BillCategory, row.category_id)
        if cat:
            category = cat.name
    return AlertOut(
        id=row.id, alert_type=row.alert_type, level=row.level, category=category,
        month=row.month, title=row.title, message=row.message,
        suggestion=row.suggestion, payload=payload,
        related_bill_id=row.related_bill_id, status=row.status,
        created_at=row.created_at)


def _save_alert(db: Session, **kwargs) -> BudgetAlert | None:
    """写入预警；命中唯一约束（同类同月已推送）时静默返回 None。"""
    row = BudgetAlert(**kwargs)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(row)
    return row


def _history_per_bill(db: Session, user_id: int, category_id: int,
                      exclude_bill_id: int) -> tuple[Decimal, Decimal, int]:
    """该分类近 180 天单笔历史：返回 (均值, 标准差, 样本数)，排除当前账单。"""
    since = date.today() - timedelta(days=ANOMALY_DAYS)
    rows = db.scalars(
        select(Bill.amount).where(
            Bill.user_id == user_id, Bill.category_id == category_id,
            Bill.type == "expense", Bill.bill_date >= since,
            Bill.id != exclude_bill_id)
    ).all()
    amounts = [Decimal(str(a)) for a in rows]
    n = len(amounts)
    if n == 0:
        return Decimal("0"), Decimal("0"), 0
    avg = sum(amounts) / n
    # 总体标准差，衡量该类开销的波动范围
    var = sum((a - avg) ** 2 for a in amounts) / n
    return avg, var.sqrt(), n


def _category_monthly_history(db: Session, user_id: int, months: int = 6) -> list[dict]:
    """近 N 个月各分类月均支出（只统计有账单的月份）。"""
    since = date.today().replace(day=1) - timedelta(days=months * 31)
    rows = db.execute(
        select(Bill.category_id, Bill.bill_date, Bill.amount)
        .where(Bill.user_id == user_id, Bill.type == "expense",
               Bill.bill_date >= since, Bill.category_id.isnot(None))
    ).all()
    # 按 分类 → 月份集合 聚合，得到月均
    by_cat: dict[int, dict[str, Decimal]] = {}
    for cid, bdate, amount in rows:
        key = f"{bdate.year:04d}-{bdate.month:02d}"
        by_cat.setdefault(cid, {})[key] = by_cat.setdefault(cid, {}).get(key, Decimal("0")) + Decimal(str(amount))
    cats = {c.id: c.name for c in _visible_categories(db, db.get(User, user_id))}
    history = []
    for cid, per_month in by_cat.items():
        total = sum(by_cat[cid].values())
        n = len(by_cat[cid])
        history.append({
            "category_id": cid,
            "category": cats.get(cid, "其他"),
            "avg_monthly": float((total / n).quantize(Decimal("0.01"))),
            "months": n,
        })
    history.sort(key=lambda h: h["avg_monthly"], reverse=True)
    return history


def _avg_monthly_income(db: Session, user_id: int, months: int = 3) -> Decimal:
    """近 N 个月平均月收入（无收入记录返回 0）。"""
    since = date.today().replace(day=1) - timedelta(days=months * 31)
    rows = db.execute(
        select(Bill.bill_date, func.coalesce(func.sum(Bill.amount), 0))
        .where(Bill.user_id == user_id, Bill.type == "income",
               Bill.bill_date >= since)
        .group_by(extract("year", Bill.bill_date), extract("month", Bill.bill_date))
    ).all()
    if not rows:
        return Decimal("0")
    total = sum(Decimal(str(t)) for _, t in rows)
    return (total / len(rows)).quantize(Decimal("0.01"))


def _round10(value: Decimal) -> Decimal:
    """金额取整到十位数，最低 10 元。"""
    return max(Decimal("10"), (value / 10).quantize(Decimal("1")) * 10)


# ---------------- 分类预算设置 ----------------

@router.get("/overview", response_model=BudgetOverviewOut)
def overview(month: str, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """预算中心总览：所有支出分类的预算 + 已花 + 占比 + 状态。"""
    _check_month(month)
    spent = _spent_map(db, user.id, month)
    budgets = {b.category_id: b for b in db.scalars(
        select(CategoryBudget).where(CategoryBudget.user_id == user.id,
                                     CategoryBudget.month == month)).all()}
    items: list[CategoryBudgetItem] = []
    for cat in _visible_categories(db, user, "expense"):
        budget = budgets.get(cat.id)
        used = spent.get(cat.id, Decimal("0"))
        if budget is None:
            status = "none"
            ratio = 0.0
            amount = Decimal("0")
            source = "manual"
        else:
            amount = budget.amount
            source = budget.source
            ratio = float(used / amount) if amount > 0 else 0.0
            status = ("over100" if ratio > 1 else
                      ("used_up" if ratio >= 1 else
                       ("near80" if ratio >= 0.8 else "ok")))
        items.append(CategoryBudgetItem(
            category_id=cat.id, category=cat.name, amount=amount, spent=used,
            remaining=amount - used, usage_ratio=round(ratio, 4),
            status=status, source=source))
    # 已设预算的排前面，按使用率降序
    items.sort(key=lambda i: (i.status == "none", -i.usage_ratio))
    total_budget = sum(i.amount for i in items)
    total_spent = sum(i.spent for i in items if i.status != "none")
    return BudgetOverviewOut(month=month, total_budget=total_budget,
                             total_spent=total_spent, items=items)


def _sync_month_budget(db: Session, user: User, month: str) -> None:
    """分类预算变更后同步整月总预算，避免首页和预算中心出现两个数字。"""
    total = Decimal(str(db.scalar(select(func.coalesce(func.sum(CategoryBudget.amount), 0))
                                    .where(CategoryBudget.user_id == user.id,
                                           CategoryBudget.month == month)) or 0))
    row = db.scalar(select(Budget).where(Budget.user_id == user.id,
                                         Budget.month == month))
    if total <= 0:
        # 分类预算全部删除后，旧总预算不能残留
        if row is not None:
            db.delete(row)
            db.commit()
        return
    if row is None:
        db.add(Budget(user_id=user.id, month=month, amount=total))
    else:
        row.amount = total
    db.commit()


def _alert_if_already_over(db: Session, user: User, category_id: int, month: str,
                           budget_amount: Decimal) -> None:
    """设置/修改预算时按当前占比立即评估：已越过 80%/100% 就推送提醒。

    覆盖"先有账单后设预算、把预算调低到已花之下"等场景；
    与记账检查一致允许重复提醒（category_id 置 NULL 绕过唯一约束）。
    """
    cat = db.get(BillCategory, category_id)
    if cat is None or budget_amount <= 0:
        return
    spent = _spent_map(db, user.id, month).get(category_id, Decimal("0"))
    ratio = float(spent / budget_amount)
    if ratio > 1.0:  # 真正超出预算：强提醒
        title, message, suggestion = budget_ai.tpl_budget_100(cat.name, spent, spent - budget_amount)
        _save_alert(db, user_id=user.id, alert_type="budget_100", level="critical",
                    category_id=None, month=month, title=title, message=message,
                    suggestion=suggestion,
                    payload=json.dumps({"category": cat.name, "category_id": cat.id,
                                        "spent": float(spent), "budget": float(budget_amount),
                                        "over": float(spent - budget_amount),
                                        "ratio": round(ratio, 4)}, ensure_ascii=False))
    elif ratio >= 0.8:  # 已达八成：普通提醒
        title, message, suggestion = budget_ai.tpl_budget_80(cat.name, spent, budget_amount - spent)
        _save_alert(db, user_id=user.id, alert_type="budget_80", level="warn",
                    category_id=None, month=month, title=title, message=message,
                    suggestion=suggestion,
                    payload=json.dumps({"category": cat.name, "category_id": cat.id,
                                        "spent": float(spent), "budget": float(budget_amount),
                                        "remaining": float(budget_amount - spent),
                                        "ratio": round(ratio, 4)}, ensure_ascii=False))


@router.put("/category", response_model=CategoryBudgetItem)
def set_category_budget(data: CategoryBudgetIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """手动设置单个分类的月度预算（upsert）。"""
    _check_month(data.month)
    cat = db.get(BillCategory, data.category_id)
    if cat is None or (cat.user_id is not None and cat.user_id != user.id):
        raise HTTPException(404, "分类不存在")
    row = db.scalar(select(CategoryBudget).where(
        CategoryBudget.user_id == user.id,
        CategoryBudget.category_id == data.category_id,
        CategoryBudget.month == data.month))
    if row is None:
        row = CategoryBudget(user_id=user.id, category_id=data.category_id,
                             month=data.month, amount=data.amount, source="manual")
        db.add(row)
    else:
        row.amount = data.amount
        row.source = "manual"
    db.commit()
    _sync_month_budget(db, user, data.month)
    _alert_if_already_over(db, user, cat.id, data.month, data.amount)
    spent = _spent_map(db, user.id, data.month).get(data.category_id, Decimal("0"))
    ratio = float(spent / data.amount) if data.amount > 0 else 0.0
    status = ("over100" if ratio > 1 else
              ("used_up" if ratio >= 1 else
               ("near80" if ratio >= 0.8 else "ok")))
    return CategoryBudgetItem(category_id=cat.id, category=cat.name, amount=data.amount,
                              spent=spent, remaining=data.amount - spent,
                              usage_ratio=round(ratio, 4), status=status, source="manual")


@router.put("/batch", response_model=BudgetOverviewOut)
def set_category_budgets_batch(data: CategoryBudgetBatchIn,
                               user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    """批量写入分类预算（AI 方案一键采纳；仅支出分类）。"""
    _check_month(data.month)
    for item in data.items:
        if item.month != data.month:
            raise HTTPException(400, "批量设置时各项月份需与 month 一致")
        cat = db.get(BillCategory, item.category_id)
        if cat is None or (cat.user_id is not None and cat.user_id != user.id):
            raise HTTPException(404, f"分类 {item.category_id} 不存在")
        row = db.scalar(select(CategoryBudget).where(
            CategoryBudget.user_id == user.id,
            CategoryBudget.category_id == item.category_id,
            CategoryBudget.month == data.month))
        if row is None:
            db.add(CategoryBudget(user_id=user.id, category_id=item.category_id,
                                  month=data.month, amount=item.amount, source=data.source))
        else:
            row.amount = item.amount
            row.source = data.source
    db.commit()
    _sync_month_budget(db, user, data.month)
    # AI 方案采纳后同样补发：已越线分类立即收到预警
    for item in data.items:
        _alert_if_already_over(db, user, item.category_id, data.month, item.amount)
    return overview(data.month, user=user, db=db)


# ---------------- 记账后预警检查（需求 2、3） ----------------

async def _check_budget_threshold(db: Session, user: User, bill: Bill,
                                  cat: BillCategory) -> list[BudgetAlert]:
    """需求 2：分类花费达预算 80% / 100% 时生成两层提醒（动态状态检查 + 允许重复）。

    不看"跨阈值瞬间"，每次保存账单都直接评估当前占比：
    - ratio >= 1.0 → 发超支强提醒；
    - 0.8 <= ratio < 1.0 → 发八成提醒；
    同一级别允许反复提醒（用户明确要求"重复打扰"，随时知道有没有超），
    做法是把 category_id 置 NULL 绕过唯一约束，分类名写进 payload。
    """
    month = f"{bill.bill_date.year:04d}-{bill.bill_date.month:02d}"
    budget = db.scalar(select(CategoryBudget).where(
        CategoryBudget.user_id == user.id,
        CategoryBudget.category_id == bill.category_id,
        CategoryBudget.month == month))
    if budget is None or budget.amount <= 0:
        return []
    spent = _spent_map(db, user.id, month).get(bill.category_id, Decimal("0"))
    ratio = float(spent / budget.amount)
    alerts: list[BudgetAlert] = []

    if ratio > 1.0:
        # 超支强提醒（每次保存处于超支状态都提醒）
        title, message, suggestion = budget_ai.tpl_budget_100(
            cat.name, spent, spent - budget.amount)
        row = _save_alert(
            db, user_id=user.id, alert_type="budget_100", level="critical",
            category_id=None, month=month, title=title, message=message,
            suggestion=suggestion, related_bill_id=bill.id,
            payload=json.dumps({"category": cat.name, "category_id": cat.id,
                                "spent": float(spent), "budget": float(budget.amount),
                                "over": float(spent - budget.amount),
                                "ratio": round(ratio, 4)}, ensure_ascii=False))
        if row:
            alerts.append(row)
    elif ratio >= 0.8:
        # 八成提醒（每次保存处于 80%~100% 状态都提醒）
        title, message, suggestion = budget_ai.tpl_budget_80(
            cat.name, spent, budget.amount - spent)
        row = _save_alert(
            db, user_id=user.id, alert_type="budget_80", level="warn",
            category_id=None, month=month, title=title, message=message,
            suggestion=suggestion, related_bill_id=bill.id,
            payload=json.dumps({"category": cat.name, "category_id": cat.id,
                                "spent": float(spent), "budget": float(budget.amount),
                                "remaining": float(budget.amount - spent),
                                "ratio": round(ratio, 4)}, ensure_ascii=False))
        if row:
            alerts.append(row)
    return alerts


async def _check_anomaly(db: Session, user: User, bill: Bill,
                         cat: BillCategory) -> BudgetAlert | None:
    """需求 3：AI 个性化大额异常预警。

    与该用户此分类近 180 天的单笔历史对比：样本 >= 5 且
    新金额 > max(2×均值, 均值+2σ) 且 >= 50 元时触发；文案由 AI 生成，失败用模板。
    """
    if bill.amount < ANOMALY_MIN_AMOUNT:
        return None
    avg, stddev, n = _history_per_bill(db, user.id, bill.category_id, bill.id)
    if n < ANOMALY_MIN_SAMPLES:
        return None
    threshold = max(avg * 2, avg + stddev * 2)
    if bill.amount <= threshold:
        return None
    # 同一账单只预警一次
    exists = db.scalar(select(BudgetAlert.id).where(
        BudgetAlert.user_id == user.id, BudgetAlert.alert_type == "anomaly",
        BudgetAlert.related_bill_id == bill.id).limit(1))
    if exists:
        return None

    month = f"{bill.bill_date.year:04d}-{bill.bill_date.month:02d}"
    context = {"type": "anomaly", "category": cat.name, "amount": float(bill.amount),
               "avg": float(avg.quantize(Decimal("0.01"))), "samples": n,
               "remark": bill.remark}
    # 优先 AI 生成柔和文案；未配置/超限/失败时降级为模板（功能不中断）
    try:
        ai_service.ensure_configured()
        ai_service.check_rate_limit(db, user.id)
        copy = await budget_ai.gen_alert_copy(db, user_id=user.id,
                                              feature="alert_anomaly", context=context)
        title, message, suggestion = copy["title"], copy["message"], copy["suggestion"]
    except AIServiceError:
        title, message, suggestion = budget_ai.tpl_anomaly(cat.name, bill.amount, avg)

    # category_id 置 NULL：唯一约束对 NULL 不去重，多笔异常都能提醒；
    # 分类信息放进 payload 供展示
    return _save_alert(
        db, user_id=user.id, alert_type="anomaly", level="warn",
        category_id=None, month=month, title=title, message=message,
        suggestion=suggestion, related_bill_id=bill.id,
        payload=json.dumps({"category": cat.name, "category_id": cat.id,
                            "amount": float(bill.amount),
                            "avg": float(avg.quantize(Decimal("0.01"))),
                            "sample_count": n,
                            "threshold": float(threshold.quantize(Decimal("0.01")))},
                           ensure_ascii=False))


@router.post("/check", response_model=BillCheckOut)
async def check_after_bill(data: BillCheckIn, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """记账保存成功后由前端追加调用：检查该账单触发的预警并返回（用于弹窗）。"""
    bill = db.get(Bill, data.bill_id)
    if bill is None or bill.user_id != user.id:
        raise HTTPException(404, "账单不存在")
    if bill.type != "expense" or not bill.category_id:
        return BillCheckOut(alerts=[])
    cat = db.get(BillCategory, bill.category_id)
    if cat is None:
        return BillCheckOut(alerts=[])

    alerts = await _check_budget_threshold(db, user, bill, cat)
    anomaly = await _check_anomaly(db, user, bill, cat)
    if anomaly:
        alerts.append(anomaly)
    return BillCheckOut(alerts=[_to_alert_out(db, a) for a in alerts])


# ---------------- AI 预算推荐 & 目标分配（需求 4） ----------------

def _fallback_recommend(history: list[dict], avg_income: Decimal) -> dict:
    """规则降级推荐：历史月均上浮 15%，取整到十位数。"""
    items = [{"category": h["category"], "amount": float(_round10(Decimal(str(h["avg_monthly"])) * Decimal("1.15"))),
              "reason": "参考你的历史月均开销"} for h in history[:8]]
    return {"items": items,
            "comment": "已按你近几个月的实际开销上浮一点生成，够花又不超支。"}


def _fallback_allocate(goal_text: str, history: list[dict], avg_income: Decimal) -> dict:
    """规则降级目标分配：从原话提取存款数字，剩余按历史占比分摊。"""
    income = avg_income if avg_income > 0 else Decimal("5000")
    match = re.search(r"(\d+(?:\.\d+)?)", goal_text)
    save = Decimal(match.group(1)) if match else income * Decimal("0.2")
    save = min(save, income * Decimal("0.8"))  # 保底：至少留 80% 以内的存钱目标
    pool = income - save
    hist_total = sum(Decimal(str(h["avg_monthly"])) for h in history)
    items = []
    if hist_total > 0:
        for h in history[:8]:
            share = Decimal(str(h["avg_monthly"])) / hist_total
            items.append({"category": h["category"], "amount": float(_round10(pool * share)),
                          "reason": "按历史开销占比分配"})
    return {"income_estimate": float(income), "save_target": float(save),
            "items": items, "comment": "按你的存钱目标和历史开销比例分配完成。"}


def _normalize_plan_items(db: Session, user: User, raw_items: list) -> list[BudgetPlanItem]:
    """把 AI 输出的分类名映射回分类 ID；非法项丢弃。"""
    cats = {c.name: c for c in _visible_categories(db, user, "expense")}
    items: list[BudgetPlanItem] = []
    for raw in raw_items:
        name = str(raw.get("category", ""))
        cat = cats.get(name)
        try:
            amount = Decimal(str(raw.get("amount", 0)))
        except Exception:
            continue
        if cat is None or amount <= 0:
            continue
        items.append(BudgetPlanItem(category_id=cat.id, category=name,
                                    amount=_round10(amount),
                                    reason=str(raw.get("reason", ""))[:60]))
    return items


def _save_plan(db: Session, user: User, month: str, goal_text: str,
               income_estimate: Decimal, items: list[BudgetPlanItem],
               comment: str) -> BudgetPlan:
    plan = BudgetPlan(
        user_id=user.id, month=month, goal_text=goal_text,
        income_estimate=income_estimate,
        total_budget=sum(i.amount for i in items),
        plan_json=json.dumps({"comment": comment,
                              "items": [i.model_dump(mode="json") for i in items]},
                             ensure_ascii=False, default=str))
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/recommend", response_model=BudgetPlanOut)
async def recommend(month: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """AI 读取历史账单，推荐一套适配消费习惯的初始预算方案（需求 4 上半）。"""
    _check_month(month)
    history = _category_monthly_history(db, user.id)
    if not history:
        raise HTTPException(400, "还没有足够的历史账单，先记几天账再来试试～")
    avg_income = _avg_monthly_income(db, user.id)
    cats = [{"name": c.name} for c in _visible_categories(db, user, "expense")]

    comment = ""
    try:
        ai_service.ensure_configured()
        ai_service.check_rate_limit(db, user.id)
        result = await budget_ai.recommend_budget(
            db, user_id=user.id, month=month, history=history,
            avg_income=avg_income, categories=cats)
        raw_items, comment = result.get("items", []), str(result.get("comment", ""))
    except AIServiceError:
        fb = _fallback_recommend(history, avg_income)
        raw_items, comment = fb["items"], fb["comment"]

    items = _normalize_plan_items(db, user, raw_items)
    if not items:
        raise HTTPException(502, "预算方案生成失败，请稍后重试")
    plan = _save_plan(db, user, month, "", avg_income, items, comment)
    return BudgetPlanOut(id=plan.id, month=month, goal_text="",
                         income_estimate=plan.income_estimate,
                         total_budget=plan.total_budget, items=items,
                         comment=comment, applied=False,
                         prompt_version=budget_ai.PROMPT_VERSION,
                         model=ai_service.config.AI_MODEL or "")


@router.post("/allocate-goal", response_model=BudgetPlanOut)
async def allocate_goal(data: GoalAllocateIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """自然语言存钱目标 → AI 自动分配各分类预算（需求 4 下半）。"""
    _check_month(data.month)
    history = _category_monthly_history(db, user.id)
    avg_income = _avg_monthly_income(db, user.id)
    cats = [{"name": c.name} for c in _visible_categories(db, user, "expense")]

    income_est = avg_income
    comment = ""
    try:
        ai_service.ensure_configured()
        ai_service.check_rate_limit(db, user.id)
        result = await budget_ai.allocate_by_goal(
            db, user_id=user.id, month=data.month, goal_text=data.goal_text,
            history=history, avg_income=avg_income, categories=cats)
        raw_items = result.get("items", [])
        comment = str(result.get("comment", ""))
        income_est = Decimal(str(result.get("income_estimate") or avg_income or 0))
    except AIServiceError:
        fb = _fallback_allocate(data.goal_text, history, avg_income)
        raw_items, comment = fb["items"], fb["comment"]
        income_est = Decimal(str(fb["income_estimate"]))

    items = _normalize_plan_items(db, user, raw_items)
    if not items:
        raise HTTPException(502, "预算分配失败，请换个说法再试试")
    plan = _save_plan(db, user, data.month, data.goal_text, income_est, items, comment)
    return BudgetPlanOut(id=plan.id, month=data.month, goal_text=data.goal_text,
                         income_estimate=plan.income_estimate,
                         total_budget=plan.total_budget, items=items,
                         comment=comment, applied=False,
                         prompt_version=budget_ai.PROMPT_VERSION,
                         model=ai_service.config.AI_MODEL or "")


@router.post("/plans/{plan_id}/apply", response_model=BudgetOverviewOut)
def apply_plan(plan_id: int, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """一键采纳 AI 预算方案：批量写入分类预算并标记已采纳。"""
    plan = db.get(BudgetPlan, plan_id)
    if plan is None or plan.user_id != user.id:
        raise HTTPException(404, "方案不存在")
    raw = json.loads(plan.plan_json)
    items = [CategoryBudgetIn(category_id=i["category_id"], month=plan.month,
                              amount=Decimal(str(i["amount"])))
             for i in raw.get("items", [])]
    if not items:
        raise HTTPException(400, "方案内容为空")
    result = set_category_budgets_batch(
        CategoryBudgetBatchIn(month=plan.month, source="ai", items=items),
        user=user, db=db)
    plan.applied = 1
    db.commit()
    return result


# ---------------- 弹性调度建议（需求 5） ----------------

@router.get("/rebalance", response_model=list[RebalanceSuggestion])
async def rebalance(month: str, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """找出"有结余"与"快超支"的分类，生成调配建议（区分刚性/冲动消费文案）。"""
    _check_month(month)
    ov = overview(month, user=user, db=db)
    tight = [i for i in ov.items if i.status in ("near80", "used_up", "over100")]
    surplus = [i for i in ov.items
               if i.status == "ok" and i.usage_ratio <= REBALANCE_SURPLUS
               and i.remaining >= REBALANCE_MIN_REMAINING]
    if not tight or not surplus:
        return []

    suggestions: list[RebalanceSuggestion] = []
    for t in tight[:3]:  # 最多给 3 条，避免打扰
        s = max(surplus, key=lambda i: i.remaining)
        # 建议调配金额：紧缺分类补齐到 90% 的缺口 与 结余一半 取小
        need = (t.amount * Decimal("0.9") - t.spent) if t.usage_ratio < 1 else t.spent - t.amount
        amount = _round10(min(max(need, Decimal("50")), s.remaining / 2))
        if amount <= 0:
            continue

        # 同月同分类已生成过建议则直接复用（唯一约束兜底，防重复推送）
        existing = db.scalar(select(BudgetAlert).where(
            BudgetAlert.user_id == user.id, BudgetAlert.alert_type == "rebalance",
            BudgetAlert.category_id == t.category_id, BudgetAlert.month == month).limit(1))
        if existing:
            p = json.loads(existing.payload or "{}")
            suggestions.append(RebalanceSuggestion(
                alert_id=existing.id, from_category_id=p.get("from_category_id", s.category_id),
                from_category=p.get("from_category", s.category),
                to_category_id=t.category_id, to_category=t.category,
                amount=Decimal(str(p.get("amount", float(amount)))),
                message=existing.message, from_remaining=s.remaining,
                to_usage_ratio=t.usage_ratio))
            continue

        context = {"from_category": s.category, "to_category": t.category,
                   "amount": float(amount), "from_remaining": float(s.remaining),
                   "to_usage_pct": round(t.usage_ratio * 100),
                   "to_is_rigid": budget_ai.is_rigid(t.category)}
        try:
            ai_service.ensure_configured()
            ai_service.check_rate_limit(db, user.id)
            message = await budget_ai.gen_rebalance_copy(db, user_id=user.id, context=context)
        except AIServiceError:
            if budget_ai.is_rigid(t.category):
                message = (f"「{t.category}」是必要开销，快超支也正常～要不要从还有结余的"
                           f"「{s.category}」调 ¥{amount:.0f} 过来？")
            else:
                message = (f"「{t.category}」快超支啦，「{s.category}」还比较宽裕，"
                           f"要不要调 ¥{amount:.0f} 过去？这类开销也可以稍微留意下～")
        row = _save_alert(
            db, user_id=user.id, alert_type="rebalance", level="info",
            category_id=t.category_id, month=month,
            title="预算小调度建议", message=message,
            suggestion="点「采纳」自动完成调配，也可以忽略。",
            payload=json.dumps({"from_category_id": s.category_id, "from_category": s.category,
                                "to_category_id": t.category_id, "to_category": t.category,
                                "amount": float(amount)}, ensure_ascii=False))
        suggestions.append(RebalanceSuggestion(
            alert_id=row.id if row else None,
            from_category_id=s.category_id, from_category=s.category,
            to_category_id=t.category_id, to_category=t.category,
            amount=amount, message=message, from_remaining=s.remaining,
            to_usage_ratio=t.usage_ratio))
    return suggestions


# ---------------- 待办计划采购联动（需求 6） ----------------

@router.get("/planned-purchase", response_model=list[PlannedPurchaseOut])
async def planned_purchase(month: str, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    """扫描未完成待办中的计划大额采购，纳入预算预判并提示资金压力。"""
    _check_month(month)
    todos = db.scalars(select(Note).where(
        Note.user_id == user.id, Note.note_type == "todo", Note.status == "open")
        .limit(50)).all()
    if not todos:
        return []
    ai_service.ensure_configured()
    ai_service.check_rate_limit(db, user.id)
    cat_names = [c.name for c in _visible_categories(db, user, "expense")]
    todo_dicts = [{"id": t.id, "title": t.title, "content": t.content or "",
                   "due_at": t.due_at.isoformat() if t.due_at else None} for t in todos]
    purchases = await budget_ai.parse_planned_purchases(
        db, user_id=user.id, todos=todo_dicts, categories=cat_names)
    if not purchases:
        return []

    todo_map = {t.id: t for t in todos}
    spent = _spent_map(db, user.id, month)
    budgets = {b.category_id: b for b in db.scalars(
        select(CategoryBudget).where(CategoryBudget.user_id == user.id,
                                     CategoryBudget.month == month)).all()}
    cats_by_name = {c.name: c for c in _visible_categories(db, user, "expense")}

    results: list[PlannedPurchaseOut] = []
    for p in purchases[:10]:
        note = todo_map.get(p.get("note_id"))
        if note is None:
            continue
        est = p.get("estimated_amount")
        est_dec = Decimal(str(est)).quantize(Decimal("0.01")) if est else None
        cat_name = str(p.get("category", "购物"))
        cat = cats_by_name.get(cat_name)

        # 资金压力预判：与对应分类（或全部预算）的剩余额度比较
        remaining = Decimal("0")
        if cat and cat.id in budgets:
            remaining = budgets[cat.id].amount - spent.get(cat.id, Decimal("0"))
        else:
            remaining = sum(b.amount for b in budgets.values()) - sum(spent.values())
        context = {"title": note.title, "estimated_amount": float(est_dec) if est_dec else None,
                   "category": cat_name, "budget_remaining": float(remaining)}
        try:
            message = await budget_ai.gen_pressure_copy(db, user_id=user.id, context=context)
        except AIServiceError:
            if est_dec and remaining > 0:
                pct = float(est_dec / remaining * 100)
                message = (f"待办里的「{note.title}」预计 ¥{est_dec:.0f}，"
                           f"约占本月剩余预算的 {pct:.0f}%，提前规划一下会更从容～")
            else:
                message = f"待办里的「{note.title}」是一笔计划开销，记得提前留出预算哦～"
        results.append(PlannedPurchaseOut(
            note_id=note.id, title=note.title, due_at=note.due_at,
            estimated_amount=est_dec, category=cat_name, pressure_message=message))

        # 同一待办同月只入一次消息中心（related_bill_id 此处存放 note_id）
        dup = db.scalar(select(BudgetAlert.id).where(
            BudgetAlert.user_id == user.id, BudgetAlert.alert_type == "planned_purchase",
            BudgetAlert.month == month, BudgetAlert.related_bill_id == note.id).limit(1))
        if not dup and est_dec:
            _save_alert(db, user_id=user.id, alert_type="planned_purchase", level="info",
                        category_id=None, month=month, title="计划采购提醒",
                        message=message, suggestion="提前纳入本月预算，花钱时心里更有底。",
                        related_bill_id=note.id,
                        payload=json.dumps({"note_id": note.id, "category": cat_name,
                                            "estimated_amount": float(est_dec)},
                                           ensure_ascii=False))
    return results


# ---------------- 预警消息中心（需求 7） ----------------

@router.get("/alerts", response_model=AlertPageOut)
def list_alerts(month: str = "", status: str = "", page: int = 1, page_size: int = 20,
                user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """预警消息列表 + 未读数。"""
    conditions = [BudgetAlert.user_id == user.id]
    if month:
        _check_month(month)
        conditions.append(BudgetAlert.month == month)
    if status in ("unread", "read", "accepted", "dismissed"):
        conditions.append(BudgetAlert.status == status)
    total = db.scalar(select(func.count()).where(*conditions)) or 0
    unread = db.scalar(select(func.count()).where(
        BudgetAlert.user_id == user.id, BudgetAlert.status == "unread")) or 0
    rows = db.scalars(select(BudgetAlert).where(*conditions)
                      .order_by(BudgetAlert.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    return AlertPageOut(items=[_to_alert_out(db, r) for r in rows],
                        total=total, unread_count=unread)


@router.get("/alerts/unread-count")
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """首页/我的页红点用：未读预警数。"""
    count = db.scalar(select(func.count()).where(
        BudgetAlert.user_id == user.id, BudgetAlert.status == "unread")) or 0
    return {"count": count}


@router.post("/alerts/{alert_id}/action", response_model=AlertOut)
def alert_action(alert_id: int, data: AlertActionIn,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """消息操作：已读 / 忽略 / 采纳（rebalance 采纳后自动完成预算调配）。"""
    row = _get_owned_alert(db, user, alert_id)
    # 幂等：已采纳的建议不再重复搬移预算；已忽略的建议不允许直接采纳
    if row.status == "accepted":
        return _to_alert_out(db, row)
    if row.status == "dismissed" and data.action == "accepted":
        raise HTTPException(400, "该建议已被忽略，请刷新后重试")
    if data.action == "accepted" and row.alert_type == "rebalance":
        payload = json.loads(row.payload or "{}")
        from_id = payload.get("from_category_id")
        amount = Decimal(str(payload.get("amount", 0)))
        if from_id and amount > 0:
            # 从结余分类扣减额度、加到紧缺分类（不允许扣成负数）
            from_budget = db.scalar(select(CategoryBudget).where(
                CategoryBudget.user_id == user.id,
                CategoryBudget.category_id == from_id,
                CategoryBudget.month == row.month))
            to_budget = db.scalar(select(CategoryBudget).where(
                CategoryBudget.user_id == user.id,
                CategoryBudget.category_id == row.category_id,
                CategoryBudget.month == row.month))
            if from_budget and to_budget and from_budget.amount - amount > 0:
                from_budget.amount -= amount
                to_budget.amount += amount
            else:
                raise HTTPException(400, "预算余额不足或分类预算已被删除，无法调配")
    row.status = data.action
    row.read_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _to_alert_out(db, row)
