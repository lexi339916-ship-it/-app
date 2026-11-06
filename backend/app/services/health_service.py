"""消费健康诊断：所有指标、分数和金额均由后端确定性计算，模型不参与算术。

设计约束：
- 每个指标都返回 formula / inputs / source / period / as_of，便于评委现场核对；
- 数据不足时返回 available=False，而不是给 0 分惩罚用户；
- 健康分只用于个人消费管理参考，不是信用评分、金融风险评级或投资建议；
- 金额一律使用 Decimal，比例使用 float 仅用于展示。
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models import (
    Bill, BillCategory, CategoryBudget, Note, SavingsGoal, Subscription, User,
)

DISCLAIMER = ("消费健康分仅用于个人消费管理参考，不是信用评分、金融风险评级，"
              "也不构成投资建议。")

# 总分权重：预算执行 30%、储蓄目标 25%、订阅健康 15%、结构稳定 15%、计划执行 15%
INDICATOR_WEIGHTS = {
    "budget_execution": 0.30,
    "savings_goal": 0.25,
    "subscription_health": 0.15,
    "structure_stability": 0.15,
    "plan_execution": 0.15,
}

INDICATOR_NAMES = {
    "budget_execution": "预算执行",
    "savings_goal": "储蓄目标",
    "subscription_health": "订阅健康",
    "structure_stability": "消费结构稳定性",
    "plan_execution": "计划执行",
}

LEVEL_THRESHOLDS = ((85, "优秀"), (70, "良好"), (55, "需关注"), (0, "需改善"))


# ---------------- 通用工具 ----------------

def q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _ratio(numerator, denominator) -> float | None:
    if denominator is None or Decimal(str(denominator)) <= 0:
        return None
    return round(float(Decimal(str(numerator)) / Decimal(str(denominator))), 4)


def _level(score: float | None) -> str:
    if score is None:
        return "数据不足"
    for threshold, label in LEVEL_THRESHOLDS:
        if score >= threshold:
            return label
    return "需改善"


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 1)


def parse_month(month: str) -> tuple[int, int]:
    try:
        year, mon = int(month[:4]), int(month[5:7])
        assert 1 <= mon <= 12
        return year, mon
    except (ValueError, AssertionError):
        raise ValueError("月份格式应为 YYYY-MM")


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = parse_month(month)
    last_day = calendar.monthrange(year, mon)[1]
    return date(year, mon, 1), date(year, mon, last_day)


def shift_month(month: str, delta: int) -> str:
    year, mon = parse_month(month)
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _month_of(value: date | datetime) -> str:
    return value.strftime("%Y-%m")


# ---------------- 数据读取 ----------------

def _load_bills(db: Session, user_id: int, month: str, history: int = 3) -> dict[str, list[Bill]]:
    """一次读取报告月 + 之前 N 个月的账单，按月份分组。"""
    start, _ = month_bounds(shift_month(month, -history))
    _, end = month_bounds(month)
    rows = db.scalars(select(Bill).where(
        Bill.user_id == user_id,
        Bill.bill_date >= start,
        Bill.bill_date <= end,
    )).all()
    result: dict[str, list[Bill]] = {}
    for row in rows:
        result.setdefault(_month_of(row.bill_date), []).append(row)
    return result


def _sum_type(rows: list[Bill], type_: str) -> Decimal:
    return q2(sum((Decimal(str(r.amount)) for r in rows if r.type == type_), Decimal("0")))


def _expense_by_category(rows: list[Bill]) -> dict[int | None, Decimal]:
    result: dict[int | None, Decimal] = {}
    for row in rows:
        if row.type != "expense":
            continue
        result[row.category_id] = result.get(row.category_id, Decimal("0")) + Decimal(str(row.amount))
    return {key: q2(value) for key, value in result.items()}


def _category_names(db: Session, user: User) -> dict[int, str]:
    rows = db.scalars(select(BillCategory).where(
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id))).all()
    return {row.id: row.name for row in rows}


def _expense_categories(db: Session, user: User) -> list[BillCategory]:
    return db.scalars(select(BillCategory).where(
        BillCategory.type == "expense",
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    ).order_by(BillCategory.id)).all()


def _history_months(month: str, count: int = 3) -> list[str]:
    return [shift_month(month, -i) for i in range(1, count + 1)]


def _months_with_data(by_month: dict[str, list[Bill]], months: list[str]) -> list[str]:
    return [m for m in months if by_month.get(m)]


def _avg_monthly_net(by_month: dict[str, list[Bill]], months: list[str]) -> Decimal:
    used = _months_with_data(by_month, months)
    if not used:
        return Decimal("0")
    total = sum((_sum_type(by_month[m], "income") - _sum_type(by_month[m], "expense")
                 for m in used), Decimal("0"))
    return q2(total / len(used))


def _avg_monthly_expense(by_month: dict[str, list[Bill]], months: list[str]) -> Decimal | None:
    used = _months_with_data(by_month, months)
    if not used:
        return None
    total = sum((_sum_type(by_month[m], "expense") for m in used), Decimal("0"))
    return q2(total / len(used))


# ---------------- 分类结构 ----------------

def _category_structure(db: Session, user: User, month: str,
                        by_month: dict[str, list[Bill]]) -> tuple[list[dict], dict]:
    names = _category_names(db, user)
    current_rows = by_month.get(month, [])
    current_expense = _sum_type(current_rows, "expense")
    current_map = _expense_by_category(current_rows)
    prev_month = shift_month(month, -1)
    prev_map = _expense_by_category(by_month.get(prev_month, []))
    history = _history_months(month)
    budgets = {b.category_id: b for b in db.scalars(
        select(CategoryBudget).where(CategoryBudget.user_id == user.id,
                                     CategoryBudget.month == month)).all()}

    items: list[dict] = []
    for cat in _expense_categories(db, user):
        amount = current_map.get(cat.id, Decimal("0"))
        prev = prev_map.get(cat.id, Decimal("0"))
        budget = budgets.get(cat.id)
        budget_amount = q2(budget.amount) if budget else Decimal("0")
        remaining = q2(budget_amount - amount)
        usage = _ratio(amount, budget_amount) if budget_amount > 0 else None
        if budget is None:
            status = "none"
        elif usage is not None and usage > 1:
            status = "over100"
        elif usage is not None and usage >= 1:
            status = "used_up"
        elif usage is not None and usage >= 0.8:
            status = "near80"
        else:
            status = "ok"
        items.append({
            "category_id": cat.id,
            "category": cat.name,
            "amount": amount,
            "ratio": _ratio(amount, current_expense) or 0.0,
            "prev_amount": prev,
            "change_amount": q2(amount - prev),
            "change_ratio": _ratio(amount - prev, prev),
            "budget": budget_amount,
            "budget_source": budget.source if budget else "none",
            "usage_ratio": usage,
            "budget_status": status,
            "remaining": remaining,
        })

    # 未挂分类的账单单独展示，避免总额与分类合计对不上
    unclassified = current_map.get(None, Decimal("0"))
    if unclassified > 0:
        items.append({
            "category_id": None, "category": "未分类", "amount": unclassified,
            "ratio": _ratio(unclassified, current_expense) or 0.0,
            "prev_amount": Decimal("0"), "change_amount": unclassified,
            "change_ratio": None, "budget": Decimal("0"), "budget_source": "none",
            "usage_ratio": None, "budget_status": "none", "remaining": Decimal("0"),
        })
    items.sort(key=lambda i: (-float(i["amount"]), i["category"]))

    budget_summary = {
        "available": any(i["budget"] > 0 for i in items),
        "total_budget": q2(sum((i["budget"] for i in items), Decimal("0"))),
        "total_spent": q2(sum((i["amount"] for i in items if i["budget"] > 0), Decimal("0"))),
        "over_count": sum(1 for i in items if i["budget_status"] == "over100"),
        "used_up_count": sum(1 for i in items if i["budget_status"] == "used_up"),
        "near_count": sum(1 for i in items if i["budget_status"] == "near80"),
        "budgeted_category_count": sum(1 for i in items if i["budget"] > 0),
        "unbudgeted_amount": q2(sum((i["amount"] for i in items if i["budget"] <= 0), Decimal("0"))),
    }
    budget_summary["remaining"] = q2(budget_summary["total_budget"] - budget_summary["total_spent"])
    budget_summary["usage_ratio"] = _ratio(budget_summary["total_spent"],
                                           budget_summary["total_budget"])
    budget_summary["overrun_amount"] = q2(sum(
        (max(Decimal("0"), i["amount"] - i["budget"])
         for i in items if i["budget"] > 0), Decimal("0")))
    return items, budget_summary


# ---------------- 储蓄目标 ----------------

def _months_between(start: date, end: date) -> float:
    return max(0.0, (end - start).days / 30.44)


def _goal_analysis(db: Session, user: User, month: str,
                   by_month: dict[str, list[Bill]], period_end: date) -> list[dict]:
    history = _history_months(month)
    avg_net = _avg_monthly_net(by_month, history)
    today = date.today()
    # 历史月份只纳入当时已创建的目标，避免用今天的目标解释过去的月份
    cutoff = datetime.combine(period_end, time.max)
    goals = db.scalars(select(SavingsGoal).where(
        SavingsGoal.user_id == user.id,
        SavingsGoal.created_at <= cutoff,
    ).order_by(SavingsGoal.created_at.desc())).all()
    result: list[dict] = []
    for goal in goals:
        target = q2(goal.target_amount)
        saved = q2(goal.saved_amount)
        remaining = q2(max(Decimal("0"), target - saved))
        progress = _ratio(saved, target) or 0.0

        target_date: date | None = None
        if goal.target_date:
            target_date = goal.target_date
        elif goal.target_months:
            base = goal.created_at.date() if goal.created_at else today
            target_date = _add_months(base, int(goal.target_months))

        months_left = _months_between(today, target_date) if target_date else None
        required_monthly = None
        if remaining > 0:
            if months_left is not None and months_left > 0:
                required_monthly = q2(remaining / Decimal(str(months_left)))
            elif months_left is not None:
                # 目标日期已到或已过：剩余金额需要在当期补齐
                required_monthly = remaining

        projected_months = None
        projected_finish = None
        if remaining <= 0:
            projected_months = 0.0
            projected_finish = today
        elif avg_net > 0:
            projected_months = float(remaining / avg_net)
            projected_finish = today + timedelta(days=int(projected_months * 30.44))

        delay_days = None
        if remaining > 0 and target_date:
            if projected_finish is not None:
                delay_days = max(0, (projected_finish - target_date).days)
            elif avg_net <= 0:
                delay_days = None

        expected_progress = None
        if target_date and goal.created_at:
            total_months = _months_between(goal.created_at.date(), target_date)
            elapsed = _months_between(goal.created_at.date(), min(today, target_date))
            if total_months > 0:
                expected_progress = min(1.0, elapsed / total_months)

        score = None
        if remaining <= 0:
            score = 100.0
        elif expected_progress and expected_progress > 0:
            score = _clamp(progress / expected_progress * 100)

        if remaining <= 0:
            status = "achieved"
        elif avg_net <= 0:
            status = "stalled"
        elif delay_days is not None and delay_days > 0:
            status = "delayed"
        elif target_date and projected_finish and projected_finish > target_date:
            status = "delayed"
        elif not target_date:
            status = "no_deadline"
        else:
            status = "on_track"

        result.append({
            "id": goal.id, "name": goal.name, "target_amount": target,
            "saved_amount": saved, "remaining": remaining,
            "progress_ratio": progress, "target_date": target_date,
            "required_monthly": required_monthly,
            "projected_finish": projected_finish, "delay_days": delay_days,
            "status": status, "score": score, "avg_monthly_net": avg_net,
            "expected_progress": round(expected_progress, 4) if expected_progress is not None else None,
        })
    return result


def _add_months(day: date, months: int) -> date:
    year = day.year + (day.month - 1 + months) // 12
    mon = (day.month - 1 + months) % 12 + 1
    return date(year, mon, min(day.day, calendar.monthrange(year, mon)[1]))


# ---------------- 订阅 ----------------

def _subscription_analysis(db: Session, user: User, month: str,
                           by_month: dict[str, list[Bill]], total_expense: Decimal,
                           period_end: date) -> dict:
    cutoff = datetime.combine(period_end, time.max)
    subs = db.scalars(select(Subscription).where(
        Subscription.user_id == user.id,
        Subscription.created_at <= cutoff,
    )).all()
    active = [s for s in subs if s.status == "active"]
    month_rows = [r for r in by_month.get(month, []) if r.source == "subscription"]
    prev_rows = [r for r in by_month.get(shift_month(month, -1), []) if r.source == "subscription"]
    month_spent = _sum_type(month_rows, "expense")
    prev_spent = _sum_type(prev_rows, "expense")
    monthly_amount = q2(sum((Decimal(str(s.amount)) for s in active), Decimal("0")))

    issues: list[dict] = []
    for sub in active:
        current = q2(sub.amount)
        previous = q2(sub.previous_amount) if sub.previous_amount is not None else None
        price_up = bool(previous and current > previous)
        low_usage = int(sub.usage_90d or 0) <= 1
        if not price_up and not low_usage:
            continue
        if price_up and low_usage:
            kind = "price_up_low_usage"
            annual = q2(current * 12)
            message = f"{sub.name} 从 ¥{previous} 涨到 ¥{current}，近 90 天仅使用 {int(sub.usage_90d or 0)} 次"
        elif price_up:
            kind = "price_up"
            annual = q2((current - previous) * 12)
            message = f"{sub.name} 从 ¥{previous} 涨到 ¥{current}"
        else:
            kind = "low_usage"
            annual = q2(current * 12)
            message = f"{sub.name} 近 90 天仅使用 {int(sub.usage_90d or 0)} 次，仍每月扣 ¥{current}"
        issues.append({
            "kind": kind, "subscription_id": sub.id, "name": sub.name,
            "message": message, "previous_amount": previous,
            "current_amount": current, "annual_impact": annual,
            "usage_90d": int(sub.usage_90d or 0), "count": None,
        })

    # 同月同备注同金额的订阅账单出现多次 → 可能重复扣款
    grouped: dict[tuple[str, Decimal], list[Bill]] = {}
    for row in month_rows:
        grouped.setdefault((row.remark or "订阅扣费", q2(row.amount)), []).append(row)
    for (remark, amount), rows in grouped.items():
        if len(rows) <= 1:
            continue
        issues.append({
            "kind": "duplicate", "subscription_id": None, "name": remark,
            "message": f"{remark} 本月出现 {len(rows)} 次，可能重复扣款",
            "previous_amount": None, "current_amount": amount,
            "annual_impact": q2(amount * (len(rows) - 1)),
            "usage_90d": None, "count": len(rows),
           })

    share = _ratio(month_spent, total_expense)
    monthly_income = None
    income_months = _months_with_data(by_month, _history_months(month))
    if income_months:
        total_income = sum((_sum_type(by_month[m], "income") for m in income_months), Decimal("0"))
        monthly_income = q2(total_income / len(income_months))
    burden = _ratio(monthly_amount, monthly_income) if monthly_income and monthly_income > 0 else None

    available = bool(active or month_spent > 0)
    score = None
    if available:
        score = 100.0
        score -= 15 * sum(1 for i in issues if i["kind"] in ("price_up", "price_up_low_usage"))
        score -= 10 * sum(1 for i in issues if i["kind"] in ("low_usage", "price_up_low_usage"))
        score -= 10 * sum(1 for i in issues if i["kind"] == "duplicate")
        if share is not None:
            if share > 0.15:
                score -= 20
            elif share > 0.10:
                score -= 10
        if burden is not None and burden > 0.10:
            score -= 10
        score = _clamp(score)

    return {
        "available": available,
        "active_count": len(active),
        "monthly_amount": monthly_amount,
        "month_spent": month_spent,
        "prev_month_spent": prev_spent,
        "change_amount": q2(month_spent - prev_spent),
        "change_ratio": _ratio(month_spent - prev_spent, prev_spent),
        "share_of_expense": share,
        "monthly_income": monthly_income,
        "income_burden": burden,
        "issues": issues,
        "score": score,
    }


# ---------------- 消费变化与异常 ----------------

def _behavior_changes(db: Session, user: User, month: str,
                      by_month: dict[str, list[Bill]], categories: list[dict]) -> tuple[list, list]:
    changes: list[dict] = []
    for item in categories:
        if item["category"] == "未分类":
            continue
        change = item["change_amount"]
        ratio = item["change_ratio"]
        if abs(change) < 100:
            continue
        if item["prev_amount"] <= 0 and item["amount"] < 200:
            continue
        if item["prev_amount"] > 0 and ratio is not None and abs(ratio) < 0.5:
            continue
        direction = "增加" if change > 0 else "减少"
        changes.append({
            "kind": "category_up" if change > 0 else "category_down",
            "title": f"「{item['category']}」支出{direction} ¥{abs(change)}",
            "detail": (f"本月 ¥{item['amount']}，上月 ¥{item['prev_amount']}"
                       + (f"，变化 {round(abs(ratio) * 100)}%" if ratio is not None else "（上月无支出）")),
            "category": item["category"],
            "amount": item["amount"],
            "change_amount": change,
            "change_ratio": ratio,
            "bill_date": "",
            "source_ids": [],
        })

    # 单笔异常：与该分类报告月之前 3 个月的单笔历史比较
    history_rows: dict[int, list[Decimal]] = {}
    for key in _history_months(month):
        for row in by_month.get(key, []):
            if row.type == "expense" and row.category_id is not None:
                history_rows.setdefault(row.category_id, []).append(Decimal(str(row.amount)))
    names = _category_names(db, user)
    anomalies: list[dict] = []
    for row in by_month.get(month, []):
        if row.type != "expense" or row.category_id is None:
            continue
        amounts = history_rows.get(row.category_id) or []
        if len(amounts) < 5:
            continue
        avg = sum(amounts) / len(amounts)
        variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
        std = variance.sqrt()
        threshold = max(avg * 2, avg + std * 2)
        amount = Decimal(str(row.amount))
        if amount < 50 or amount <= threshold:
            continue
        anomalies.append({
            "kind": "anomaly",
            "title": f"「{names.get(row.category_id, '未分类')}」出现异常大额",
            "detail": (f"单笔 ¥{q2(amount)}，该分类历史均值 ¥{q2(avg)}，"
                       f"异常阈值 ¥{q2(threshold)}"),
            "category": names.get(row.category_id, "未分类"),
            "amount": q2(amount),
            "change_amount": q2(amount - avg),
            "change_ratio": _ratio(amount - avg, avg),
            "bill_date": row.bill_date.isoformat(),
            "source_ids": [row.id],
        })
    anomalies.sort(key=lambda i: -float(i["amount"]))
    return changes[:6], anomalies[:3]


# ---------------- 计划执行 ----------------

def _plan_execution(db: Session, user: User, month: str,
                    period_start: date, period_end: date) -> dict:
    today = date.today()
    cutoff = min(period_end, today) if month == today.strftime("%Y-%m") else period_end
    rows = db.scalars(select(Note).where(
        Note.user_id == user.id,
        Note.note_type == "todo",
        Note.due_at.isnot(None),
        Note.due_at >= datetime.combine(period_start, datetime.min.time()),
        Note.due_at <= datetime.combine(cutoff, datetime.max.time()),
    )).all()
    done = sum(1 for r in rows if r.status == "done")
    open_count = sum(1 for r in rows if r.status != "done")
    total = done + open_count
    score = _clamp(done / total * 100) if total else None
    return {
        "available": total > 0,
        "total": total,
        "done": done,
        "open": open_count,
        "score": score,
        "formula": "已完成任务数 ÷ 截止本月且已到期的任务总数 × 100",
    }


# ---------------- 指标与建议 ----------------

def _indicator(key: str, score: float | None, formula: str, explanation: str,
               inputs: dict, source: str, period: str) -> dict:
    return {
        "key": key, "name": INDICATOR_NAMES[key],
        "score": round(score, 1) if score is not None else None,
        "level": _level(score), "available": score is not None,
        "formula": formula, "explanation": explanation, "inputs": inputs,
        "source": source, "period": period,
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }


def _budget_indicator(budget: dict, period: str) -> dict:
    if not budget["available"]:
        return _indicator(
            "budget_execution", None,
            "已设预算分类的支出合计 ÷ 预算合计；超支/接近上限分类额外扣分",
            "本月还没有设置分类预算，暂不计算该指标。",
            budget, "category_budgets + bills", period)
    score = 100.0
    usage = budget["usage_ratio"] or 0
    if usage > 1:
        score -= min(50.0, (usage - 1) * 100)
    elif usage >= 0.8:
        score -= 10
    score -= 8 * budget["over_count"]
    score -= 4 * budget.get("used_up_count", 0)
    score -= 3 * budget["near_count"]
    score = _clamp(score)
    explanation = (f"预算合计 ¥{budget['total_budget']}，已花 ¥{budget['total_spent']}，"
                   f"使用率 {round(usage * 100)}%；超支 {budget['over_count']} 个分类，"
                   f"刚好用完 {budget.get('used_up_count', 0)} 个，"
                   f"接近上限 {budget['near_count']} 个分类。")
    return _indicator(
        "budget_execution", score,
        "基础 100 分；整体使用率 80%–100% 扣 10 分，超 100% 按超出比例最多扣 50 分；"
        "每个超支分类扣 8 分，每个刚好用完分类扣 4 分，每个 80%–100% 分类扣 3 分",
        explanation, budget, "category_budgets + bills", period)


def _goal_indicator(goals: list[dict], period: str) -> dict:
    scored = [g["score"] for g in goals if g["score"] is not None]
    inputs = {"goals": goals}
    if not scored:
        return _indicator(
            "savings_goal", None,
            "实际进度 ÷ 按目标周期应达到的进度 × 100；已达成记 100 分",
            ("还没有设置带周期的储蓄目标，暂不计算该指标。"
             if not goals else "储蓄目标缺少目标日期/周期，暂不计算进度分。"),
            inputs, "savings_goals + bills", period)
    score = _clamp(sum(scored) / len(scored))
    explanation = "；".join(
        f"「{g['name']}」进度 {round(g['progress_ratio'] * 100)}%"
        + (f"，预计 {g['projected_finish']} 完成" if g.get("projected_finish") else "")
        for g in goals[:3])
    return _indicator(
        "savings_goal", score,
        "每个目标：实际进度 ÷ 按创建时间到目标日期应完成的进度 × 100，上限 100；多目标取平均",
        explanation, inputs, "savings_goals + bills", period)


def _subscription_indicator(subs: dict, period: str) -> dict:
    if not subs["available"]:
        return _indicator(
            "subscription_health", None,
            "基础 100 分；涨价每个 -15、低频每个 -10、重复扣款每个 -10；"
            "订阅支出占比 >15% 再 -20，>10% -10；月订阅额占收入 >10% -10",
            "没有进行中的订阅，暂不计算该指标。",
            subs, "subscriptions + bills", period)
    explanation = (f"{subs['active_count']} 个进行中订阅，每月固定 ¥{subs['monthly_amount']}；"
                   f"本月订阅支出 ¥{subs['month_spent']}，占总支出的 "
                   f"{round((subs['share_of_expense'] or 0) * 100)}%；"
                   f"发现 {len(subs['issues'])} 个异常。")
    return _indicator(
        "subscription_health", subs["score"],
        "基础 100 分；涨价每个 -15、低频每个 -10、重复扣款每个 -10；"
        "订阅支出占比 >15% 再 -20，>10% -10；月订阅额占收入 >10% -10",
        explanation, subs, "subscriptions + bills", period)


def _structure_indicator(month: str, by_month: dict[str, list[Bill]],
                         categories: list[dict], period: str) -> dict:
    history = _months_with_data(by_month, _history_months(month))
    current_total = sum((i["amount"] for i in categories if i["category"] != "未分类"), Decimal("0"))
    if len(history) < 2 or current_total <= 0:
        return _indicator(
            "structure_stability", None,
            "本月各分类占比与近 3 个月平均占比的总变差距离（TVD）；得分 = (1 - TVD) × 100",
            "历史月份不足 2 个或本月没有支出，暂不计算结构稳定性。",
            {"history_months": history}, "bills", period)

    current_share = {i["category"]: i["ratio"] for i in categories}
    name_by_id = {i["category_id"]: i["category"] for i in categories}
    history_share: dict[str, list[float]] = {}
    for key in history:
        rows = by_month.get(key, [])
        total = _sum_type(rows, "expense")
        if total <= 0:
            continue
        for row in rows:
            if row.type != "expense":
                continue
            name = name_by_id.get(row.category_id, "未分类")
            history_share.setdefault(name, []).append(float(Decimal(str(row.amount)) / total))
    avg_share = {name: sum(values) / len(values) for name, values in history_share.items()}
    names = set(current_share) | set(avg_share)
    tvd = 0.5 * sum(abs(current_share.get(n, 0.0) - avg_share.get(n, 0.0)) for n in names)
    score = _clamp((1 - tvd) * 100)
    return _indicator(
        "structure_stability", score,
        "本月各分类占比与近 3 个月平均占比的总变差距离（TVD）；得分 = (1 - TVD) × 100",
        f"与近 {len(history)} 个月平均结构相比，总变差距离 {round(tvd, 3)}；"
        f"得分越高说明消费结构越稳定。",
        {"tvd": round(tvd, 4), "history_months": history,
         "current_share": {k: round(v, 4) for k, v in current_share.items()},
         "avg_share": {k: round(v, 4) for k, v in avg_share.items()}},
        "bills", period)


def _plan_indicator(plan: dict, period: str) -> dict:
    if not plan["available"]:
        return _indicator(
            "plan_execution", None,
            "已完成任务数 ÷ 截止本月且已到期的任务总数 × 100",
            "本月没有到期任务，暂不计算计划执行。",
            plan, "notes", period)
    return _indicator(
        "plan_execution", plan["score"],
        "已完成任务数 ÷ 截止本月且已到期的任务总数 × 100",
        f"本月到期任务 {plan['total']} 个，已完成 {plan['done']} 个，未完成 {plan['open']} 个。",
        plan, "notes", period)


def _recommendations(overview: dict, categories: list[dict], budget: dict,
                     goals: list[dict], subs: dict, changes: list[dict],
                     plan: dict) -> list[dict]:
    result: list[dict] = []

    for item in categories:
        if item["budget_status"] == "over100":
            result.append({
                "title": f"「{item['category']}」已超预算",
                "detail": (f"已花 ¥{item['amount']}，预算 ¥{item['budget']}，"
                           f"超出 ¥{abs(item['remaining'])}。"),
                "impact_amount": abs(item["remaining"]),
                "priority": "high",
                "action_hint": "可以让 Agent 生成调配方案，或本周控制该分类支出。",
                "source": "category_budgets + bills",
            })
        elif item["budget_status"] == "used_up":
            result.append({
                "title": f"「{item['category']}」预算已用完",
                "detail": (f"已花 ¥{item['amount']}，预算 ¥{item['budget']}，"
                           "剩余 ¥0；后续支出会直接超支。"),
                "impact_amount": None,
                "priority": "medium",
                "action_hint": "如果本月还有必要支出，可以提前从结余分类调配额度。",
                "source": "category_budgets + bills",
            })
        elif item["budget_status"] == "near80":
            result.append({
                "title": f"「{item['category']}」接近预算上限",
                "detail": (f"已用 {round((item['usage_ratio'] or 0) * 100)}%，"
                           f"剩余 ¥{item['remaining']}。"),
                "impact_amount": item["remaining"],
                "priority": "medium",
                "action_hint": "提前规划剩余额度，避免月底超支。",
                "source": "category_budgets + bills",
            })

    for goal in goals:
        if goal["status"] == "delayed":
            result.append({
                "title": f"「{goal['name']}」预计延期",
                "detail": (f"按近 3 个月平均结余 ¥{goal['avg_monthly_net']} 估算，"
                           f"预计 {goal['projected_finish']} 完成，目标日期 {goal['target_date']}。"),
                "impact_amount": goal["remaining"],
                "priority": "high",
                "action_hint": (f"每月需存 ¥{goal['required_monthly']}；"
                                "可以压缩可自由支配预算或调整目标周期。"),
                "source": "savings_goals + bills",
            })
        elif goal["status"] == "stalled":
            result.append({
                "title": f"「{goal['name']}」进度停滞",
                "detail": f"近 3 个月平均结余为 ¥{goal['avg_monthly_net']}，目标还差 ¥{goal['remaining']}。",
                "impact_amount": goal["remaining"],
                "priority": "high",
                "action_hint": "先恢复正向结余，再拆解每月储蓄额。",
                "source": "savings_goals + bills",
            })

    for issue in subs.get("issues", [])[:3]:
        result.append({
            "title": f"订阅「{issue['name']}」需要复核",
            "detail": issue["message"],
            "impact_amount": issue["annual_impact"],
            "priority": "medium",
            "action_hint": "可以让 Agent 暂停或创建月底复盘任务。",
            "source": "subscriptions + bills",
        })

    for change in changes:
        if change["kind"] == "category_up":
            result.append({
                "title": change["title"],
                "detail": change["detail"],
                "impact_amount": abs(change["change_amount"]),
                "priority": "medium",
                "action_hint": "可以给该分类设置预算上限，或检查是否有一次性大额支出。",
                "source": "bills",
            })

    if not budget["available"]:
        result.append({
            "title": "还没有设置分类预算",
            "detail": "没有预算就无法判断哪些分类正在失控。",
            "impact_amount": None, "priority": "medium",
            "action_hint": "在预算中心按历史月均生成一套预算，或让 Agent 帮你规划。",
            "source": "category_budgets",
        })

    if plan["available"] and plan["open"] > 0:
        result.append({
            "title": "有到期任务未完成",
            "detail": f"本月 {plan['total']} 个到期任务中还有 {plan['open']} 个未完成。",
            "impact_amount": None, "priority": "low",
            "action_hint": "到便签页处理，或让 Agent 重新安排本周计划。",
            "source": "notes",
        })

    if (overview["savings_rate"] or 0) >= 0.2:
        result.append({
            "title": "本月结余率不错",
            "detail": f"结余 ¥{overview['net']}，结余率 {round((overview['savings_rate'] or 0) * 100)}%。",
            "impact_amount": overview["net"], "priority": "info",
            "action_hint": "可以考虑把结余的一部分存入储蓄目标。",
            "source": "bills",
        })

    priority_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    result.sort(key=lambda r: priority_order.get(r["priority"], 9))
    return result[:6]


# ---------------- 对外入口 ----------------

def build_report(db: Session, user: User, month: str | None = None) -> dict:
    """生成某月的消费健康报告；month 为空时使用当前月。"""
    month = month or date.today().strftime("%Y-%m")
    period_start, period_end = month_bounds(month)
    by_month = _load_bills(db, user.id, month)
    current_rows = by_month.get(month, [])

    income = _sum_type(current_rows, "income")
    expense = _sum_type(current_rows, "expense")
    net = q2(income - expense)
    bill_count = len(current_rows)
    today = date.today()
    days_in_month = (period_end - period_start).days + 1
    is_current = month == today.strftime("%Y-%m")
    days_elapsed = min(today.day, days_in_month) if is_current else days_in_month
    avg_daily = q2(expense / days_elapsed) if days_elapsed else Decimal("0")
    # 月初样本太少时不做线性外推，避免“5 天花 5000 就预测月支出 3 万”的误导
    projected = (q2(avg_daily * days_in_month)
                 if is_current and days_elapsed >= 7 else None)

    prev_month = shift_month(month, -1)
    prev_expense = _sum_type(by_month.get(prev_month, []), "expense")
    history_avg = _avg_monthly_expense(by_month, _history_months(month))
    overview = {
        "income": income, "expense": expense, "net": net,
        "savings_rate": _ratio(net, income),
        "bill_count": bill_count,
        "days_elapsed": days_elapsed, "days_in_month": days_in_month,
        "avg_daily_expense": avg_daily, "projected_expense": projected,
        "prev_expense": prev_expense,
        "expense_change_amount": q2(expense - prev_expense),
        "expense_change_ratio": _ratio(expense - prev_expense, prev_expense),
        "history_avg_expense": history_avg,
    }

    categories, budget = _category_structure(db, user, month, by_month)
    goals = _goal_analysis(db, user, month, by_month, period_end)
    subs = _subscription_analysis(db, user, month, by_month, expense, period_end)
    changes, anomalies = _behavior_changes(db, user, month, by_month, categories)
    plan = _plan_execution(db, user, month, period_start, period_end)

    period_label = f"{month}（{period_start} ~ {period_end}）"
    indicators = [
        _budget_indicator(budget, period_label),
        _goal_indicator(goals, period_label),
        _subscription_indicator(subs, period_label),
        _structure_indicator(month, by_month, categories, period_label),
        _plan_indicator(plan, period_label),
    ]
    available = [i for i in indicators if i["available"]]
    total_weight = sum(INDICATOR_WEIGHTS[i["key"]] for i in available)
    coverage = total_weight / sum(INDICATOR_WEIGHTS.values())
    overall_score = None
    # 覆盖不足 50% 时不给总分，避免用两三个指标得出“优秀”的误导性结论
    if total_weight > 0 and coverage >= 0.5:
        overall_score = round(sum(i["score"] * INDICATOR_WEIGHTS[i["key"]] for i in available)
                              / total_weight, 1)
    weights_used = {i["key"]: INDICATOR_WEIGHTS[i["key"]] for i in available}
    overall_level = _level(overall_score)

    if bill_count == 0 and not goals and not subs["available"]:
        summary = ("本月还没有账单，也没有储蓄目标或订阅。先记几笔账，"
                   "或让 Agent 帮你建立第一个预算目标。")
    else:
        parts = [f"本月收入 ¥{income}，支出 ¥{expense}，结余 ¥{net}"]
        if budget["available"]:
            parts.append(f"分类预算使用率 {round((budget['usage_ratio'] or 0) * 100)}%")
        parts.append(f"消费健康分 {overall_score if overall_score is not None else '数据不足'}"
                     f"（{overall_level}）")
        top_issue = next((r for r in _recommendations(
            overview, categories, budget, goals, subs, changes, plan)
            if r["priority"] in ("high", "medium")), None)
        if top_issue:
            parts.append(f"最需要关注：{top_issue['title']}")
        summary = "；".join(parts) + "。"

    recommendations = _recommendations(overview, categories, budget, goals, subs, changes, plan)
    data_sources = ["bills", "bill_categories", "category_budgets", "savings_goals",
                    "subscriptions", "notes"]

    return {
        "month": month,
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overview": overview,
        "categories": categories,
        "budget": budget,
        "goals": goals,
        "subscriptions": subs,
        "changes": changes,
        "anomalies": anomalies,
        "plan": plan,
        "indicators": indicators,
        "overall_score": overall_score,
        "overall_level": overall_level,
        "weights": INDICATOR_WEIGHTS,
        "weights_used": weights_used,
        "coverage": round(coverage, 4),
        "summary": summary,
        "recommendations": recommendations,
        "data_sources": data_sources,
        "disclaimer": DISCLAIMER,
    }
