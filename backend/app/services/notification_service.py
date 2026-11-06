"""统一通知读模型：聚合 BudgetAlert 与 AgentNotification，不改变两张源表。

设计目的：
- 用户只看到一个消息中心和一套未读角标；
- 旧接口（预算预警/Agent 通知）保持不变，避免破坏现有测试和审计；
- 列表按业务键折叠重复风险，优先展示可操作的 Agent 通知。
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import AgentNotification, BillCategory, BudgetAlert, User
from app.services.agent import orchestrator

STATUS_RANK = {"unread": 0, "read": 1, "accepted": 2, "dismissed": 3}
SOURCE_RANK = {"agent": 0, "budget": 1}
LEVEL_ORDER = {"critical": 0, "warn": 1, "info": 2}


def _json(value: str) -> dict:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _amount(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None


def _target_route(source: str, alert_type: str) -> str:
    if source == "budget":
        if alert_type in ("budget_80", "budget_100", "rebalance"):
            return "/pages/budget/center"
        if alert_type == "planned_purchase":
            return "/pages/notes/list"
        return "/pages/health/report"
    return {
        "budget": "/pages/budget/center",
        "subscription": "/pages/subscriptions/list",
        "goal": "/pages/goals/goals",
        "planned_purchase": "/pages/notes/list",
        "spending_change": "/pages/health/report",
        "anomaly": "/pages/health/report",
    }.get(alert_type, "/pages/agent/agent")


def _budget_dedupe(row: BudgetAlert) -> str:
    payload = _json(row.payload)
    if row.alert_type in ("budget_80", "budget_100"):
        category = payload.get("category_id") or row.category_id
        return f"budget:{category}:{row.month}"
    if row.alert_type == "anomaly":
        return f"anomaly:{row.related_bill_id or row.id}"
    if row.alert_type == "planned_purchase":
        return f"planned:{row.related_bill_id or row.id}"
    if row.alert_type == "rebalance":
        category = row.category_id or payload.get("to_category_id")
        return f"rebalance:{category}:{row.month}"
    return f"budget:{row.alert_type}:{row.id}"


def _agent_dedupe(row: AgentNotification) -> str:
    payload = _json(row.payload_json)
    key = str(payload.get("dedupe") or "")
    if key.startswith("planned:") and key.count(":") >= 2:
        parts = key.split(":")
        return f"planned:{parts[1]}"
    return key or f"agent:{row.alert_type}:{row.id}"


def _normalize_budget(db: Session, row: BudgetAlert) -> dict:
    payload = _json(row.payload)
    category = payload.get("category", "")
    if row.category_id:
        cat = db.get(BillCategory, row.category_id)
        if cat:
            category = cat.name
    amount = (_amount(payload.get("over")) or _amount(payload.get("remaining"))
              or _amount(payload.get("amount")) or _amount(payload.get("estimated_amount"))
              or _amount(payload.get("annual_impact")))
    return {
        "source": "budget", "id": row.id, "alert_type": row.alert_type,
        "level": row.level, "title": row.title, "message": row.message,
        "suggestion": row.suggestion or "", "category": category,
        "amount": amount, "status": row.status, "month": row.month,
        "created_at": row.created_at, "read_at": row.read_at,
        "dedupe_key": _budget_dedupe(row), "remind_count": 0,
        "target_route": _target_route("budget", row.alert_type),
        "payload": payload, "related_count": 1,
    }


def _normalize_agent(row: AgentNotification) -> dict:
    payload = _json(row.payload_json)
    month = str(payload.get("month") or row.created_at.strftime("%Y-%m"))
    return {
        "source": "agent", "id": row.id, "alert_type": row.alert_type,
        "level": row.level, "title": row.title, "message": row.message,
        "suggestion": row.suggestion or "", "category": row.category or "",
        "amount": _amount(row.amount), "status": row.status, "month": month,
        "created_at": row.created_at, "read_at": row.read_at,
        "dedupe_key": _agent_dedupe(row),
        "remind_count": int(payload.get("remind_count") or 0),
        "target_route": _target_route("agent", row.alert_type),
        "payload": payload, "related_count": 1,
    }


def _select_representative(items: list[dict]) -> list[dict]:
    """同一业务键只展示一条：未读优先，其次 Agent（更可操作），再按时间。"""
    groups: dict[str, list[dict]] = {}
    for item in items:
        groups.setdefault(item["dedupe_key"], []).append(item)
    result = []
    for group in groups.values():
        group.sort(key=lambda x: (
            STATUS_RANK.get(x["status"], 9),
            SOURCE_RANK.get(x["source"], 9),
            -x["created_at"].timestamp(),
        ))
        chosen = dict(group[0])
        chosen["related_count"] = len(group)
        result.append(chosen)
    return result


def _query(db: Session, user: User, source: str = "", status: str = "",
           limit: int = 50) -> list[dict]:
    items: list[dict] = []
    if source in ("", "budget"):
        conditions = [BudgetAlert.user_id == user.id]
        if status in ("unread", "read", "accepted", "dismissed"):
            conditions.append(BudgetAlert.status == status)
        rows = db.scalars(select(BudgetAlert).where(*conditions)
                          .order_by(BudgetAlert.created_at.desc())
                          .limit(max(1, min(limit, 100)))).all()
        items.extend(_normalize_budget(db, row) for row in rows)
    if source in ("", "agent"):
        conditions = [AgentNotification.user_id == user.id]
        if status in ("unread", "read", "dismissed"):
            conditions.append(AgentNotification.status == status)
        rows = db.scalars(select(AgentNotification).where(*conditions)
                          .order_by(AgentNotification.created_at.desc())
                          .limit(max(1, min(limit, 100)))).all()
        items.extend(_normalize_agent(row) for row in rows)
    return items


def list_notifications(db: Session, user: User, status: str = "",
                       source: str = "", limit: int = 50) -> list[dict]:
    items = _query(db, user, source, status, limit)
    if source:
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items[:max(1, min(limit, 100))]
    items = _select_representative(items)
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return items[:max(1, min(limit, 100))]


def summary(db: Session, user: User) -> dict:
    budget_unread = int(db.scalar(select(func.count()).where(
        BudgetAlert.user_id == user.id, BudgetAlert.status == "unread")) or 0)
    agent_unread = int(db.scalar(select(func.count()).where(
        AgentNotification.user_id == user.id,
        AgentNotification.status == "unread")) or 0)
    unread_items = _query(db, user, "", "unread", 200)
    unique = _select_representative(unread_items)
    by_level = {"critical": 0, "warn": 0, "info": 0}
    for item in unique:
        by_level[item["level"]] = by_level.get(item["level"], 0) + 1
    return {
        "total_unread": budget_unread + agent_unread,
        "unique_unread": len(unique),
        "budget_unread": budget_unread,
        "agent_unread": agent_unread,
        "by_level": by_level,
        "as_of": datetime.now(),
    }


def mark_all_read(db: Session, user: User) -> dict:
    """进入消息中心时把两张源表的未读全部标记为已读，红点立即消失。"""
    now = datetime.now()
    budget = db.execute(update(BudgetAlert).where(
        BudgetAlert.user_id == user.id,
        BudgetAlert.status == "unread",
    ).values(status="read", read_at=now))
    agent = db.execute(update(AgentNotification).where(
        AgentNotification.user_id == user.id,
        AgentNotification.status == "unread",
    ).values(status="read", read_at=now))
    db.commit()
    return {"marked": int(budget.rowcount or 0) + int(agent.rowcount or 0),
            "as_of": now}


def action(db: Session, user: User, source: str, notification_id: int,
           action_name: str) -> dict:
    if source == "budget":
        from app.routers.budget_center import AlertActionIn, alert_action
        if action_name not in ("read", "dismissed", "accepted"):
            raise ValueError("不支持的操作")
        alert_action(notification_id, AlertActionIn(action=action_name), user, db)
        row = db.get(BudgetAlert, notification_id)
        return _normalize_budget(db, row)
    if source == "agent":
        if action_name not in ("read", "dismissed"):
            raise ValueError("Agent 通知不支持采纳操作")
        orchestrator.notification_action(db, user, notification_id, action_name)
        row = db.get(AgentNotification, notification_id)
        return _normalize_agent(row)
    raise ValueError("通知来源不正确")
