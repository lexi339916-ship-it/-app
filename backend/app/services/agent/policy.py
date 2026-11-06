"""Agent 策略层：写操作白名单、金额/归属校验、幂等键与安全边界。"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Subscription, User
from app.services.agent import tools

ALLOWED_ACTIONS = {
    "create_bill", "set_category_budgets", "create_goal",
    "create_task", "pause_subscription", "create_memory",
}
MAX_ACTIONS = 12
MAX_AMOUNT = Decimal("9999999999.99")


class PolicyError(ValueError):
    """策略拒绝：消息可直接展示给用户。"""


def _amount(value) -> Decimal:
    try:
        amount = Decimal(str(value))
    except Exception:
        raise PolicyError("金额格式不正确")
    if amount <= 0 or amount > MAX_AMOUNT:
        raise PolicyError("金额必须在 0.01 ~ 9999999999.99 之间")
    return amount.quantize(Decimal("0.01"))


def validate_actions(db: Session, user: User, actions: list[dict]) -> list[dict]:
    if not actions:
        raise PolicyError("没有可执行的写操作")
    if len(actions) > MAX_ACTIONS:
        raise PolicyError(f"一次最多执行 {MAX_ACTIONS} 个动作，请拆分任务")
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise PolicyError(f"第 {index + 1} 个动作格式不正确")
        kind = str(action.get("action") or "")
        if kind not in ALLOWED_ACTIONS:
            raise PolicyError(f"不支持的动作：{kind or '空'}")

        if kind == "create_bill":
            bill = action.get("bill") or {}
            type_ = bill.get("type")
            if type_ not in ("income", "expense"):
                raise PolicyError("账单类型必须是 income 或 expense")
            action["bill"]["amount"] = str(_amount(bill.get("amount")))
            category = tools.resolve_category(db, user, bill.get("category", ""), type_)
            if category is None:
                raise PolicyError(f"分类“{bill.get('category', '')}”不存在或不可用")
            action["bill"]["category_id"] = category.id
            action["bill"]["category"] = category.name
            action["bill"]["bill_date"] = str(bill.get("bill_date") or "")[:10]

        elif kind == "set_category_budgets":
            month = str(action.get("month") or "")
            try:
                year, mon = int(month[:4]), int(month[5:7])
                assert 1 <= mon <= 12
            except (ValueError, AssertionError):
                raise PolicyError("预算月份格式应为 YYYY-MM")
            items = action.get("items") or []
            if not isinstance(items, list) or not items or len(items) > 20:
                raise PolicyError("预算调整条目数量不正确")
            valid = {c.id for c in tools.visible_categories(db, user, "expense")}
            for item in items:
                cid = int(item.get("category_id") or 0)
                if cid not in valid:
                    raise PolicyError("预算分类不存在或不可用")
                amount = Decimal(str(item.get("amount", 0)))
                if amount < 0 or amount > MAX_AMOUNT:
                    raise PolicyError("预算金额必须在 0 ~ 9999999999.99 之间")
                item["amount"] = str(amount.quantize(Decimal("0.01")))

        elif kind == "create_goal":
            goal = action.get("goal") or {}
            if not str(goal.get("name") or "").strip():
                raise PolicyError("目标名称不能为空")
            action["goal"]["target_amount"] = str(_amount(goal.get("target_amount")))

        elif kind == "create_task":
            note = action.get("note") or {}
            if not str(note.get("title") or "").strip():
                raise PolicyError("任务标题不能为空")

        elif kind == "pause_subscription":
            sub_id = int(action.get("subscription_id") or 0)
            row = db.get(Subscription, sub_id)
            if row is None or row.user_id != user.id:
                raise PolicyError("订阅不存在或不属于当前用户")
            action["before_status"] = row.status

        elif kind == "create_memory":
            if not str(action.get("key") or "").strip():
                raise PolicyError("记忆键不能为空")

    return actions


def summarize_actions(actions: list[dict]) -> list[dict]:
    """给前端审批卡用的精简动作列表，隐藏内部 before 等字段。"""
    public = []
    for action in actions:
        kind = action.get("action")
        if kind == "create_bill":
            bill = action.get("bill", {})
            public.append({
                "action": kind, "label": "写入账单",
                "detail": f"{bill.get('type')} ¥{bill.get('amount')} · {bill.get('category')} · {bill.get('bill_date')}",
            })
        elif kind == "set_category_budgets":
            public.append({
                "action": kind, "label": "调整分类预算",
                "detail": "；".join(
                    f"{item.get('category_name') or item.get('category_id')} → ¥{item.get('amount')}"
                    for item in action.get("items", [])),
            })
        elif kind == "create_goal":
            goal = action.get("goal", {})
            public.append({
                "action": kind, "label": "创建储蓄目标",
                "detail": f"{goal.get('name')} · ¥{goal.get('target_amount')}",
            })
        elif kind == "create_task":
            public.append({
                "action": kind, "label": "创建任务",
                "detail": (action.get("note") or {}).get("title", ""),
            })
        elif kind == "pause_subscription":
            public.append({
                "action": kind, "label": "暂停订阅",
                "detail": action.get("subscription_name", ""),
            })
        elif kind == "create_memory":
            public.append({"action": kind, "label": "记住偏好", "detail": action.get("key", "")})
    return public
