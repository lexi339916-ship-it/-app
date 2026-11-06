"""消费决策模拟器：用真实账单/预算/目标做确定性测算。

边界：
- 不读取真实银行账户余额，不预测收益；“剩余资金”指按历史结余测算的可支配结余；
- 所有金额用 Decimal，模型不参与计算；
- 数据不足时返回 missing，让前端提示补充，而不是猜。
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Bill, SavingsGoal, User
from app.services.agent import tools

DISCLAIMER = ("本测算基于历史账单、当前预算和储蓄目标的确定性估算，"
              "不代表账户真实余额，不构成投资建议。")


def q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _add_months(day: date, months: int) -> date:
    year = day.year + (day.month - 1 + months) // 12
    mon = (day.month - 1 + months) % 12 + 1
    return date(year, mon, min(day.day, calendar.monthrange(year, mon)[1]))


def _cashflow(db: Session, user_id: int) -> dict:
    """近 3 个完整自然月的平均收支；不足 3 个月有账单时标记数据不足。"""
    today = date.today()
    months = [_shift_month(today.strftime("%Y-%m"), -i) for i in (1, 2, 3)]
    total_income = Decimal("0")
    total_expense = Decimal("0")
    bill_count = 0
    for month in months:
        total_income += tools.month_sum(db, user_id, month, "income")
        total_expense += tools.month_sum(db, user_id, month, "expense")
        bill_count += int(db.scalar(select(func.count()).where(
            *tools.month_condition(user_id, month))) or 0)
    avg_income = q2(total_income / 3)
    avg_expense = q2(total_expense / 3)
    return {
        "available": bill_count > 0,
        "months": months,
        "monthly_income": avg_income,
        "monthly_expense": avg_expense,
        "monthly_net": q2(avg_income - avg_expense),
        "bill_count": bill_count,
    }


def _budget_impact(db: Session, user: User, category: str,
                   amount: Decimal) -> dict:
    month = tools.current_month()
    overview = tools.budget_overview(db, user, month)
    item = next((i for i in overview["items"] if i["category"] == category), None)
    total_budget = overview["total_budget"]
    if item is not None and item["amount"] > 0:
        before = item["remaining"]
        source = "category"
        category_budget = item["amount"]
        category_spent = item["spent"]
    elif total_budget > 0:
        before = q2(total_budget - overview["total_spent"])
        source = "total"
        category_budget = Decimal("0")
        category_spent = item["spent"] if item else Decimal("0")
    else:
        return {
            "available": False, "source": "none", "category": category,
            "category_budget": Decimal("0"), "category_spent": Decimal("0"),
            "budget_remaining_before": Decimal("0"),
            "budget_remaining_after": Decimal("0"),
            "over_budget": False, "over_amount": Decimal("0"),
            "total_budget": total_budget, "total_spent": overview["total_spent"],
        }
    after = q2(before - amount)
    return {
        "available": True, "source": source, "category": category,
        "category_budget": q2(category_budget),
        "category_spent": q2(category_spent),
        "budget_remaining_before": q2(before),
        "budget_remaining_after": after,
        "over_budget": after < 0,
        "over_amount": q2(abs(after)) if after < 0 else Decimal("0"),
        "total_budget": total_budget, "total_spent": overview["total_spent"],
    }


def _goal_analysis(db: Session, user: User, goal_id: int | None,
                   amount: Decimal, monthly_net: Decimal,
                   horizon_months: int) -> tuple[dict | None, str]:
    goal = None
    if goal_id is not None:
        goal = db.get(SavingsGoal, goal_id)
        if goal is None or goal.user_id != user.id:
            return None, "not_found"
    else:
        goal = db.scalar(select(SavingsGoal).where(SavingsGoal.user_id == user.id)
                         .order_by(SavingsGoal.created_at.desc()).limit(1))
    if goal is None:
        return None, "missing"

    target = q2(goal.target_amount)
    saved = q2(goal.saved_amount)
    remaining = q2(max(Decimal("0"), target - saved))
    target_date = goal.target_date
    if target_date is None and goal.target_months:
        target_date = _add_months(goal.created_at.date(), int(goal.target_months))
    months_left = (max(0.0, (target_date - date.today()).days / 30.44)
                   if target_date else float(horizon_months))

    net = monthly_net
    if remaining <= 0:
        projected_before = saved
        projected_after = saved
    elif net > 0:
        projected_before = q2(min(target, saved + net * Decimal(str(months_left))))
        projected_after = q2(min(target, max(
            Decimal("0"), saved + net * Decimal(str(months_left)) - amount)))
    else:
        projected_before = saved
        projected_after = q2(max(Decimal("0"), saved - amount))

    gap_before = q2(max(Decimal("0"), target - projected_before))
    gap_after = q2(max(Decimal("0"), target - projected_after))

    def finish(extra: Decimal) -> date | None:
        if remaining <= 0:
            return date.today()
        if net <= 0:
            return None
        return date.today() + timedelta(days=int((remaining + extra) / net * Decimal("30.44")))

    finish_before = finish(Decimal("0"))
    finish_after = finish(amount)
    extra_days = (max(0, (finish_after - finish_before).days)
                  if finish_before and finish_after else None)
    horizon_end = date.today() + timedelta(days=int(horizon_months * 30.44))
    delay_days = None
    if target_date and finish_after:
        delay_days = max(0, (finish_after - target_date).days)
    elif finish_after and not target_date:
        # 没有明确目标日时，用“观察周期末”作为基准；完成时间晚了但仍在周期内不算延期
        delay_days = max(0, (finish_after - horizon_end).days)

    if remaining <= 0:
        status = "achieved"
    elif net <= 0:
        status = "stalled"
    elif target_date and delay_days and delay_days > 0:
        status = "delayed"
    elif target_date is None:
        status = "no_deadline"
    else:
        status = "on_track"

    return {
        "id": goal.id, "name": goal.name, "target_amount": target,
        "saved_amount": saved, "remaining": remaining,
        "progress_ratio": round(float(saved / target), 4) if target > 0 else 0.0,
        "target_date": target_date,
        "months_left": round(months_left, 2),
        "projected_saved_before": projected_before,
        "projected_saved_after": projected_after,
        "gap_before": gap_before, "gap_after": gap_after,
        "projected_finish_before": finish_before,
        "projected_finish_after": finish_after,
        "delay_days": delay_days, "extra_days": extra_days,
        "status": status,
    }, "ok"


def simulate(db: Session, user: User, amount: Decimal, category: str,
             goal_id: int | None = None, horizon_months: int = 3) -> dict:
    amount = q2(amount)
    cashflow = _cashflow(db, user.id)
    budget = _budget_impact(db, user, category, amount)
    goal, goal_state = _goal_analysis(
        db, user, goal_id, amount, cashflow["monthly_net"], horizon_months)

    missing: list[str] = []
    if not cashflow["available"]:
        missing.append("cashflow")
    if goal_state == "missing":
        missing.append("goal")
    if not budget["available"]:
        missing.append("budget")

    monthly_net = cashflow["monthly_net"]
    monthly_net_after = q2(monthly_net - amount)
    goal_delay = goal["delay_days"] if goal else None

    scenarios: list[dict] = []
    if cashflow["available"] and goal:
        scenarios = [
            {
                "key": "buy_now", "title": "现在购买",
                "description": "本月直接支出，预算和目标按当前数据测算。",
                "budget_impact": budget["budget_remaining_after"] if budget["available"] else None,
                "goal_delay_days": goal_delay,
                "goal_gap_after": goal["gap_after"],
                "feasible": True, "monthly_cut": q2(0),
                "impact_amount": amount,
            },
            {
                "key": "next_month", "title": "下个月购买",
                "description": "本月预算不受影响；下月扣款，目标总延期不变。",
                "budget_impact": q2(0) if budget["available"] else None,
                "goal_delay_days": goal_delay,
                "goal_gap_after": goal["gap_after"],
                "feasible": True, "monthly_cut": q2(0),
                "impact_amount": amount,
            },
        ]
        # 压缩其他支出：每月从其他有结余的分类里省出 amount / horizon
        monthly_cut = q2(amount / Decimal(str(max(1, horizon_months))))
        discretionary = q2(sum(
            (i["remaining"] for i in tools.budget_overview(db, user, tools.current_month())["items"]
             if i["category"] != category and i["status"] == "ok" and i["amount"] > 0),
            Decimal("0")))
        feasible = discretionary >= monthly_cut
        scenarios.append({
            "key": "offset_by_cutting", "title": f"分 {horizon_months} 个月压缩其他支出",
            "description": (f"每月少花约 ¥{monthly_cut}，用结余抵消这次购买；"
                            f"可压缩的其他分类剩余约 ¥{discretionary}。"
                            + ("" if feasible else " 当前可压缩额度不足，无法完全抵消。")),
            "budget_impact": None,
            "goal_delay_days": 0 if feasible else None,
            "goal_gap_after": goal["gap_before"] if feasible else goal["gap_after"],
            "feasible": feasible, "monthly_cut": monthly_cut,
            "impact_amount": amount,
        })

    recommendations: list[dict] = []
    if budget["available"] and budget["over_budget"]:
        recommendations.append({
            "title": f"「{category}」预算会被击穿",
            "detail": (f"购买后该分类将超出预算 ¥{budget['over_amount']}；"
                       f"当前剩余额度 ¥{budget['budget_remaining_before']}。"),
            "impact_amount": budget["over_amount"], "priority": "high",
            "action_hint": "减少购买金额、从其他结余分类调配，或分月购买。",
        })
    if goal and goal_delay and goal_delay > 0:
        required = q2(amount / Decimal(str(max(1, int(goal["months_left"])))))
        recommendations.append({
            "title": f"「{goal['name']}」可能延期 {goal_delay} 天",
            "detail": (f"按近 3 个月平均结余 ¥{monthly_net} 测算，"
                       f"购买后目标差额从 ¥{goal['gap_before']} 变为 ¥{goal['gap_after']}。"),
            "impact_amount": amount, "priority": "high",
            "action_hint": (f"如果不想延期，未来 {max(1, int(goal['months_left']))} 个月"
                            f"每月需多存约 ¥{required}。"),
        })
    elif goal and goal.get("extra_days"):
        recommendations.append({
            "title": f"目标完成时间会晚约 {goal['extra_days']} 天",
            "detail": (f"购买后仍在观察周期内完成，但比不买晚约 {goal['extra_days']} 天；"
                       f"目标差额 ¥{goal['gap_after']}。"),
            "impact_amount": amount, "priority": "info",
            "action_hint": "如果希望按时完成，可以减少购买金额或压缩其他支出。",
        })
    if monthly_net_after < 0:
        recommendations.append({
            "title": "这次购买会吃掉本月结余",
            "detail": (f"按近 3 个月平均结余 ¥{monthly_net} 测算，购买后本月结余约 "
                       f"¥{monthly_net_after}。"),
            "impact_amount": abs(monthly_net_after), "priority": "high",
            "action_hint": "建议分月购买，或先确认有足够的已有储蓄，不要只看预算额度。",
        })
    if not budget["available"]:
        recommendations.append({
            "title": "该分类还没有预算",
            "detail": "没有预算就无法判断这次购买对本月额度的冲击。",
            "impact_amount": None, "priority": "medium",
            "action_hint": "先在预算中心为该分类设置预算，再回来测算。",
        })
    if cashflow["available"] and goal and (goal_delay or 0) == 0 \
            and not (budget["available"] and budget["over_budget"]):
        recommendations.append({
            "title": "当前数据下可以承受",
            "detail": "按近 3 个月结余和当前预算，这次购买不会导致目标延期或预算超支。",
            "impact_amount": None, "priority": "info",
            "action_hint": "仍建议保留至少 1 个月应急结余。",
        })

    available = cashflow["available"] and goal is not None
    if not cashflow["available"]:
        message = "近 3 个月账单不足，先记几笔账再做测算；当前结果只能作为参考。"
    elif goal is None:
        message = "还没有储蓄目标。先创建一个目标，才能判断这次购买会不会影响它。"
    else:
        message = (f"购买 ¥{amount} 的{category}："
                   + (f"预算将超支 ¥{budget['over_amount']}；"
                      if budget["available"] and budget["over_budget"]
                      else (f"预算剩余约 ¥{budget['budget_remaining_after']}；"
                            if budget["available"] else "该分类未设预算；"))
                   + (f"目标「{goal['name']}」预计延期 {goal_delay} 天。"
                      if goal_delay and goal_delay > 0
                      else (f"目标完成时间会晚约 {goal['extra_days']} 天，"
                            "但仍在观察周期内。"
                            if goal.get("extra_days") else "目标进度基本不受影响。")))

    return {
        "available": available,
        "missing": missing,
        "message": message,
        "as_of": date.today().isoformat(),
        "amount": amount,
        "category": category,
        "horizon_months": int(horizon_months),
        "purchase": {
            **budget,
            "monthly_net_after": monthly_net_after,
            "over_budget": budget["over_budget"],
            "over_amount": budget["over_amount"],
        },
        "cashflow": {**cashflow, "monthly_net_after": monthly_net_after},
        "goal": goal,
        "scenarios": scenarios,
        "recommendations": recommendations[:5],
        "assumptions": [
            "按近 3 个完整自然月的平均收入/支出计算结余",
            "购买金额视为从可自由支配结余中支出，未计入账户真实余额",
            "目标延期按“购买金额 ÷ 月均结余”估算，实际受收入变化影响",
        ],
        "disclaimer": DISCLAIMER,
    }
