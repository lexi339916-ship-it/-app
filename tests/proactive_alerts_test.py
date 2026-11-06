# -*- coding: utf-8 -*-
"""主动风险预警测试：覆盖 7 类风险、去重、忽略冷却与用户隔离。

运行：python tests/proactive_alerts_test.py
"""
import json
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./proactive_alerts.db"
for f in Path(".").glob("proactive_alerts.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import (  # noqa: E402
    AgentNotification, Bill, BillCategory, CategoryBudget, Note, SavingsGoal,
    Subscription,
)

config.AI_BASE_URL = ""
config.AI_API_KEY = ""
config.AI_MODEL = ""
Base.metadata.create_all(bind=engine)
seed_default_categories()
client = TestClient(app)
PASSED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASSED += 1
    else:
        raise SystemExit(f"测试失败：{name} {detail}")


def shift_month(d: date, delta: int) -> date:
    index = d.year * 12 + (d.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def register(username: str) -> dict:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def cat_id(db, name: str, type_: str = "expense") -> int:
    return db.scalar(select(BillCategory.id).where(
        BillCategory.name == name, BillCategory.type == type_,
        BillCategory.user_id.is_(None)))


def add_bill(db, uid: int, cid: int, type_: str, amount: str, day: date,
             source: str = "manual", remark: str = "") -> None:
    db.add(Bill(user_id=uid, category_id=cid, type=type_, amount=Decimal(amount),
                bill_date=day, source=source, remark=remark or f"{type_} {amount}"))


today = date.today()
current = today.strftime("%Y-%m")
cur_day = date(today.year, today.month, min(today.day, 28))
prev1, prev2, prev3 = shift_month(today, -1), shift_month(today, -2), shift_month(today, -3)

H_A = register("alert_a")
H_B = register("alert_b")
uid_a = client.get("/api/auth/me", headers=H_A).json()["id"]
uid_b = client.get("/api/auth/me", headers=H_B).json()["id"]

db = SessionLocal()
try:
    ids = {name: cat_id(db, name) for name in ("餐饮", "交通", "购物", "娱乐", "医疗")}
    ids["工资"] = cat_id(db, "工资", "income")

    add_bill(db, uid_a, ids["工资"], "income", "8000", cur_day, remark="工资")
    add_bill(db, uid_a, ids["餐饮"], "expense", "1200", cur_day)
    add_bill(db, uid_a, ids["娱乐"], "expense", "400", cur_day)
    add_bill(db, uid_a, ids["购物"], "expense", "300", cur_day)
    add_bill(db, uid_a, ids["交通"], "expense", "200", cur_day)
    add_bill(db, uid_a, ids["医疗"], "expense", "500", cur_day)

    for index, day in enumerate((prev1, prev2, prev3)):
        add_bill(db, uid_a, ids["工资"], "income", "8000",
                 date(day.year, day.month, 15), remark="工资")
        add_bill(db, uid_a, ids["餐饮"], "expense", "750",
                 date(day.year, day.month, 15))
        add_bill(db, uid_a, ids["娱乐"], "expense", "300",
                 date(day.year, day.month, 15))
        add_bill(db, uid_a, ids["购物"], "expense", "200",
                 date(day.year, day.month, 15))
        add_bill(db, uid_a, ids["交通"], "expense", "200",
                 date(day.year, day.month, 15))
        for offset in range(3 - index):
            add_bill(db, uid_a, ids["医疗"], "expense", "50",
                     date(day.year, day.month, 10 + offset))

    for name, amount in (("餐饮", "1000"), ("娱乐", "500"),
                         ("购物", "200"), ("交通", "200")):
        db.add(CategoryBudget(user_id=uid_a, category_id=ids[name],
                              month=current, amount=Decimal(amount), source="manual"))

    db.add(SavingsGoal(user_id=uid_a, name="旅行基金",
                       target_amount=Decimal("60000"), saved_amount=Decimal("1000"),
                       target_months=3, created_at=datetime.now() - timedelta(days=60)))
    db.add(Subscription(user_id=uid_a, name="视频会员", day_of_month=10,
                        amount=Decimal("25"), previous_amount=Decimal("20"),
                        usage_90d=1, status="active", last_billed_month=current))
    add_bill(db, uid_a, ids["娱乐"], "expense", "25", cur_day,
             source="subscription", remark="视频会员 · 自动订阅扣费")
    db.add(Note(user_id=uid_a, title="买电脑 5000 元", content="下个月换电脑",
                note_type="todo", status="open",
                due_at=datetime.now() + timedelta(days=20)))
    db.commit()
finally:
    db.close()

# ---------------- 首次扫描 ----------------
r = client.post("/api/agent/proactive/scan", headers=H_A)
check("扫描返回 200", r.status_code == 200, r.text)
j = r.json()
items = j["items"]
types = {item["alert_type"] for item in items}
check("包含预算风险", "budget" in types, str(types))
check("包含订阅风险", "subscription" in types, str(types))
check("包含目标风险", "goal" in types, str(types))
check("包含消费变化", "spending_change" in types, str(types))
check("包含异常大额", "anomaly" in types, str(types))
check("包含计划采购", "planned_purchase" in types, str(types))
check("扫描项不超过 12 条", len(items) <= 12, str(len(items)))
check("未读数大于 0", j["unread_count"] > 0, str(j["unread_count"]))

budget_items = [i for i in items if i["alert_type"] == "budget"]
check("有超支和接近上限两类", any(i["level"] == "critical" for i in budget_items)
      and any(i["level"] == "warn" for i in budget_items), str(budget_items))
check("包含预算刚好用完", any("预算已用完" in i["title"] for i in budget_items), str(budget_items))
check("超支项金额为超出额", any(
    i["category"] == "餐饮" and Decimal(i["amount"]) == Decimal("200.00")
    for i in budget_items), str(budget_items))

sub_items = [i for i in items if i["alert_type"] == "subscription"]
check("订阅标题包含名称", any("视频会员" in i["title"] for i in sub_items), str(sub_items))
check("订阅含年化影响", all(i["amount"] is not None for i in sub_items), str(sub_items))
check("通知带触发原因", all(i["payload"].get("trigger") for i in items), str(items[:2]))
check("通知带金额影响", all("impact_amount" in i["payload"] for i in items))

goal_items = [i for i in items if i["alert_type"] == "goal"]
check("目标延期通知", any("延期" in i["title"] for i in goal_items), str(goal_items))

change_items = [i for i in items if i["alert_type"] == "spending_change"]
check("消费变化含餐饮", any(i["category"] == "餐饮" for i in change_items), str(change_items))

# ---------------- 去重 ----------------
with SessionLocal() as db:
    count_before = db.scalar(select(func.count()).select_from(AgentNotification))
r2 = client.post("/api/agent/proactive/scan", headers=H_A)
with SessionLocal() as db:
    count_after = db.scalar(select(func.count()).select_from(AgentNotification))
check("重复扫描不新增通知", count_after == count_before, f"{count_before} -> {count_after}")
check("重复扫描返回相同 id", {i["id"] for i in r2.json()["items"]}
      == {i["id"] for i in items})

# ---------------- 忽略冷却 ----------------
target = next(i for i in items if i["alert_type"] == "budget")
r = client.post(f"/api/agent/notifications/{target['id']}/action",
                headers=H_A, json={"action": "dismissed"})
check("忽略成功", r.status_code == 200 and r.json()["status"] == "dismissed", r.text)

r = client.post("/api/agent/proactive/scan", headers=H_A)
check("冷却期内不再提醒", all(i["id"] != target["id"] for i in r.json()["items"]),
      str([i["id"] for i in r.json()["items"]]))

with SessionLocal() as db:
    row = db.get(AgentNotification, target["id"])
    row.read_at = datetime.now() - timedelta(days=8)
    db.commit()

r = client.post("/api/agent/proactive/scan", headers=H_A)
again = [i for i in r.json()["items"] if i["id"] == target["id"]]
check("冷却 7 天后再次提醒", bool(again), str(r.json()["items"]))
check("再提醒次数 1", again and again[0]["status"] == "unread", str(again))
with SessionLocal() as db:
    row = db.get(AgentNotification, target["id"])
    payload = json.loads(row.payload_json)
    check("payload 记录再提醒次数", payload.get("remind_count") == 1, str(payload))

# 第二次再提醒
client.post(f"/api/agent/notifications/{target['id']}/action",
            headers=H_A, json={"action": "dismissed"})
with SessionLocal() as db:
    row = db.get(AgentNotification, target["id"])
    row.read_at = datetime.now() - timedelta(days=8)
    db.commit()
r = client.post("/api/agent/proactive/scan", headers=H_A)
check("第二次冷却后再提醒", any(i["id"] == target["id"] for i in r.json()["items"]))
with SessionLocal() as db:
    row = db.get(AgentNotification, target["id"])
    payload = json.loads(row.payload_json)
    check("再提醒次数 2", payload.get("remind_count") == 2, str(payload))

# 第三次后达到上限，不再提醒
client.post(f"/api/agent/notifications/{target['id']}/action",
            headers=H_A, json={"action": "dismissed"})
with SessionLocal() as db:
    row = db.get(AgentNotification, target["id"])
    row.read_at = datetime.now() - timedelta(days=8)
    db.commit()
r = client.post("/api/agent/proactive/scan", headers=H_A)
check("达到上限后不再提醒", all(i["id"] != target["id"] for i in r.json()["items"]))

# ---------------- 用户隔离 ----------------
r = client.post("/api/agent/proactive/scan", headers=H_B)
check("用户 B 扫描返回 200", r.status_code == 200, r.text)
check("用户 B 没有他人风险", r.json()["items"] == [], str(r.json()["items"]))

print(f"\n全部通过：{PASSED} 项断言")


def func_count(db):
    from sqlalchemy import func
    return select(func.count()).select_from(AgentNotification)
