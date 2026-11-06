# -*- coding: utf-8 -*-
"""统一消息中心测试：聚合、去重、分来源、动作、旧接口兼容与用户隔离。"""
import json
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./notifications_test.db"
for f in Path(".").glob("notifications_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import (  # noqa: E402
    AgentNotification, BillCategory, BudgetAlert,
)

config.AI_BASE_URL = ""
config.AI_API_KEY = ""
config.AI_MODEL = ""
Base.metadata.create_all(bind=engine)
seed_default_categories()
client = TestClient(app)
PASSED = 0
MONTH = date.today().strftime("%Y-%m")


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASSED += 1
    else:
        raise SystemExit(f"测试失败：{name} {detail}")


def register(username: str) -> tuple[dict, int]:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


H_A, UID_A = register("notif_a")
H_B, UID_B = register("notif_b")

with SessionLocal() as db:
    food = db.scalar(select(BillCategory.id).where(
        BillCategory.name == "餐饮", BillCategory.type == "expense",
        BillCategory.user_id.is_(None)))
    budget_alert = BudgetAlert(
        user_id=UID_A, alert_type="budget_100", level="warn", category_id=food,
        month=MONTH, title="「餐饮」预算已超支", message="已超出预算 ¥120",
        suggestion="控制餐饮支出", payload=json.dumps({
            "category": "餐饮", "category_id": food, "over": 120,
        }, ensure_ascii=False), status="unread")
    anomaly_alert = BudgetAlert(
        user_id=UID_A, alert_type="anomaly", level="warn", category_id=None,
        month=MONTH, title="餐饮异常大额", message="单笔金额明显高于历史",
        suggestion="确认是否一次性支出", related_bill_id=999,
        payload=json.dumps({"category": "餐饮"}, ensure_ascii=False),
        status="unread")
    agent_budget = AgentNotification(
        user_id=UID_A, alert_type="budget", level="warn",
        title="「餐饮」预算已超支", message="已花 ¥1200 / 预算 ¥1000",
        suggestion="可以让 Agent 调配", category="餐饮", amount=Decimal("200"),
        payload_json=json.dumps({
            "dedupe": f"budget:{food}:{MONTH}", "month": MONTH,
            "impact_amount": "200", "trigger": "分类支出超过预算",
        }, ensure_ascii=False), status="unread",
        dedupe_key=f"budget:{food}:{MONTH}")
    agent_sub = AgentNotification(
        user_id=UID_A, alert_type="subscription", level="info",
        title="订阅「视频会员」涨价", message="从 ¥25 涨到 ¥30",
        suggestion="可以暂停或复核", category="订阅", amount=Decimal("360"),
        payload_json=json.dumps({
            "dedupe": f"subscription:1:price_up:{MONTH}", "month": MONTH,
            "impact_amount": "360",
        }, ensure_ascii=False), status="unread",
        dedupe_key=f"subscription:1:price_up:{MONTH}")
    db.add_all([budget_alert, anomaly_alert, agent_budget, agent_sub])
    db.commit()
    ids = {
        "budget": budget_alert.id, "anomaly": anomaly_alert.id,
        "agent_budget": agent_budget.id, "agent_sub": agent_sub.id,
    }

r = client.get("/api/notifications/summary", headers=H_A)
check("summary 200", r.status_code == 200, r.text)
s = r.json()
check("原始未读 4", s["total_unread"] == 4, str(s))
check("去重未读 3", s["unique_unread"] == 3, str(s))
check("预算未读 2", s["budget_unread"] == 2, str(s))
check("Agent 未读 2", s["agent_unread"] == 2, str(s))
check("等级统计", s["by_level"].get("warn") == 2 and s["by_level"].get("info") == 1,
      str(s))

r = client.get("/api/notifications", headers=H_A)
check("统一列表 200", r.status_code == 200, r.text)
items = r.json()
check("默认折叠为 3 条", len(items) == 3, str(len(items)))
budget_item = next(i for i in items if i["dedupe_key"] == f"budget:{food}:{MONTH}")
check("重复预算折叠 2 条", budget_item["related_count"] == 2, str(budget_item))
check("优先展示 Agent 来源", budget_item["source"] == "agent", str(budget_item))
check("预算消息跳预算中心", budget_item["target_route"] == "/pages/budget/center")
sub_item = next(i for i in items if i["alert_type"] == "subscription")
check("订阅消息跳订阅页", sub_item["target_route"] == "/pages/subscriptions/list")
check("统一列表带金额", Decimal(budget_item["amount"]) == Decimal("200.00"),
      str(budget_item))

r = client.get("/api/notifications", headers=H_A, params={"source": "budget"})
check("按预算来源筛选 2 条", len(r.json()) == 2, r.text)
r = client.get("/api/notifications", headers=H_A, params={"source": "agent"})
check("按 Agent 来源筛选 2 条", len(r.json()) == 2, r.text)

# 旧接口仍然只统计自己的表
r = client.get("/api/agent/notifications/unread-count", headers=H_A)
check("旧 Agent 未读数 2", r.json()["count"] == 2, r.text)
r = client.get("/api/budget-center/alerts/unread-count", headers=H_A)
check("旧预算未读数 2", r.json()["count"] == 2, r.text)

# 标记 Agent 订阅消息已读
r = client.post(f"/api/notifications/agent/{ids['agent_sub']}/action",
                headers=H_A, json={"action": "read"})
check("统一动作标记已读", r.status_code == 200 and r.json()["status"] == "read", r.text)
r = client.get("/api/notifications/summary", headers=H_A)
check("已读后总数下降", r.json()["total_unread"] == 3, r.text)
check("已读后去重数下降", r.json()["unique_unread"] == 2, r.text)

# 标记预算异常已读
r = client.post(f"/api/notifications/budget/{ids['anomaly']}/action",
                headers=H_A, json={"action": "read"})
check("预算消息标记已读", r.status_code == 200 and r.json()["status"] == "read", r.text)

# 越权与非法动作
r = client.post(f"/api/notifications/agent/{ids['agent_budget']}/action",
                headers=H_B, json={"action": "read"})
check("跨用户操作 404", r.status_code == 404, r.text)
r = client.post(f"/api/notifications/agent/{ids['agent_budget']}/action",
                headers=H_A, json={"action": "accepted"})
check("Agent 不支持采纳 400", r.status_code == 400, r.text)
r = client.get("/api/notifications", headers=H_A, params={"source": "other"})
check("非法来源 400", r.status_code == 400, r.text)
r = client.get("/api/notifications", headers=H_A, params={"group": "budget_over"})
check("预算超支分组", r.status_code == 200
      and any(item["alert_type"] == "budget_100" for item in r.json())
      and all(item["alert_type"] in ("budget_100", "budget") for item in r.json()), r.text)
r = client.get("/api/notifications", headers=H_A, params={"group": "budget_near"})
check("预算不足分组", r.status_code == 200
      and all(item["alert_type"] in ("budget_80", "budget") for item in r.json()), r.text)
r = client.get("/api/notifications", headers=H_A, params={"group": "other"})
check("异常/其他分组", r.status_code == 200
      and any(item["alert_type"] == "anomaly" for item in r.json()), r.text)
r = client.get("/api/notifications", headers=H_A, params={"group": "bad"})
check("非法分组 400", r.status_code == 400, r.text)
r = client.get("/api/notifications/summary")
check("未登录 401", r.status_code == 401, r.text)


# 进入消息中心：全部标记已读，未读红点消失
r = client.post("/api/notifications/read-all", headers=H_A)
check("全部已读返回 200", r.status_code == 200, r.text)
check("至少标记一条", r.json().get("marked", 0) >= 1, r.text)
s = client.get("/api/notifications/summary", headers=H_A).json()
check("全部已读后总未读 0", s["total_unread"] == 0, str(s))
check("全部已读后去重未读 0", s["unique_unread"] == 0, str(s))
check("旧 Agent 未读归零",
      client.get("/api/agent/notifications/unread-count", headers=H_A).json()["count"] == 0)
check("旧预算未读归零",
      client.get("/api/budget-center/alerts/unread-count", headers=H_A).json()["count"] == 0)

print(f"\n全部通过：{PASSED} 项断言")
