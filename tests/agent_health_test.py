# -*- coding: utf-8 -*-
"""Agent 消费健康诊断测试：只读意图、真实报告卡、无审批。"""
import os
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./agent_health_test.db"
for f in Path(".").glob("agent_health_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402

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


def register(username: str) -> dict:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


A = register("health_agent_a")
B = register("health_agent_b")
today = date.today().isoformat()

for headers, amount, category, type_ in (
    (A, "9000.00", "工资", "income"),
    (A, "2500.00", "住房", "expense"),
    (A, "1180.00", "餐饮", "expense"),
):
    r = client.post("/api/bills", headers=headers, json={
        "type": type_, "amount": amount, "category": category,
        "bill_date": today, "remark": f"健康测试 {category}"})
    check(f"准备账单 {category}", r.status_code == 200, r.text)

r = client.get("/api/categories", headers=A, params={"type": "expense"})
check("读取支出分类", r.status_code == 200, r.text)
food_id = next(c["id"] for c in r.json()["items"] if c["name"] == "餐饮")
r = client.put("/api/budget-center/category", headers=A, json={
    "category_id": food_id, "month": today[:7], "amount": "1200.00"})
check("准备预算", r.status_code == 200, r.text)
r = client.post("/api/goals", headers=A, json={
    "name": "健康测试目标", "target_amount": "3000.00"})
check("准备目标", r.status_code == 200, r.text)

r = client.post("/api/agent/run", headers=A, json={
    "message": "帮我做一次消费健康诊断", "mode": "auto"})
check("健康诊断 200", r.status_code == 200, r.text)
body = r.json()
check("健康诊断完成", body["status"] == "completed", body["status"])
check("命中健康工具",
      any(s["tool_name"] == "get_health_report" for s in body["steps"]), body["steps"])
check("健康诊断不误走记账",
      not any(s["tool_name"] == "parse_bill" for s in body["steps"]), body["steps"])
check("健康诊断无审批", body.get("approvals") == [], str(body.get("approvals")))
check("健康诊断有结构化卡",
      (body["evidence"].get("cards") or [{}])[0].get("type") == "health_report",
      body["evidence"])
check("健康回答非空", bool(body["answer"]), body["answer"])

# 无数据用户也可以得到“数据不足”的真实报告，不编造分数
r = client.post("/api/agent/run", headers=B, json={
    "message": "查看我的消费健康诊断", "mode": "auto"})
check("无数据健康诊断完成", r.status_code == 200 and r.json()["status"] == "completed",
      r.text)
check("无数据有覆盖率提示", bool(r.json()["answer"]), r.json()["answer"])

print(f"\n全部通过：{PASSED} 项断言")
