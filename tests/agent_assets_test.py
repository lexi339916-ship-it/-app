# -*- coding: utf-8 -*-
"""Agent 资产联动测试：资产查询、净资产变化、购买模拟、储蓄计划与审批。"""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./agent_assets_test.db"
for f in Path(".").glob("agent_assets_test.db*"):
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


def month_shift(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + mon - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def add_bill(headers: dict, month: str, day: int, type_: str,
             category: str, amount: str, remark: str) -> None:
    r = client.post("/api/bills", headers=headers, json={
        "type": type_, "amount": amount, "category": category,
        "bill_date": f"{month}-{day:02d}", "remark": remark})
    check(f"准备账单 {remark}", r.status_code == 200, r.text)


def run(headers: dict, message: str) -> dict:
    r = client.post("/api/agent/run", headers=headers, json={
        "message": message, "mode": "auto"})
    check(f"Agent 运行：{message}", r.status_code == 200, r.text)
    return r.json()


A = register("agent_asset_a")
B = register("agent_asset_b")

# 资产：现金 + 房产 + 理财；负债：信用卡
r = client.post("/api/assets/accounts", headers=A, json={
    "name": "工资卡", "type": "bank", "balance": "10000.00"})
check("创建工资卡", r.status_code == 200, r.text)
r = client.post("/api/assets/accounts", headers=A, json={
    "name": "自住房产", "type": "property", "balance": "500000.00"})
check("创建房产", r.status_code == 200, r.text)
r = client.post("/api/assets/accounts", headers=A, json={
    "name": "稳健理财", "type": "investment", "balance": "30000.00"})
check("创建理财", r.status_code == 200, r.text)
r = client.post("/api/assets/liabilities", headers=A, json={
    "name": "信用卡", "type": "credit_card", "outstanding": "5000.00"})
check("创建信用卡负债", r.status_code == 200, r.text)

# 近 3 个完整月收支，供模拟器和目标规划使用
today = date.today()
current = today.strftime("%Y-%m")
for delta in (1, 2, 3):
    month = month_shift(current, -delta)
    add_bill(A, month, 10, "income", "工资", "8000.00", f"{month}工资")
    add_bill(A, month, 12, "expense", "餐饮", "3000.00", f"{month}餐饮")

r = client.post("/api/goals", headers=A, json={
    "name": "旅行基金", "target_amount": "10000.00"})
check("创建储蓄目标", r.status_code == 200, r.text)

# ---------- 查询资产 ----------
res = run(A, "查看我的个人资产")
check("资产查询完成", res["status"] == "completed", res["status"])
check("资产查询命中资产工具",
      any(s["tool_name"] == "get_asset_overview" for s in res["steps"]), res["steps"])
check("资产回答包含总资产", "总资产" in res["answer"], res["answer"])
check("资产回答区分可动用与固定资产",
      "可动用" in res["answer"] and "固定资产" in res["answer"], res["answer"])
check("资产结构化卡片", (res["evidence"].get("cards") or [{}])[0].get("type")
      == "asset_overview", res["evidence"])

# ---------- 净资产变化 ----------
res = run(A, "为什么这个月净资产减少了？")
check("净资产变化完成", res["status"] == "completed", res["status"])
check("命中净资产变化工具",
      any(s["tool_name"] == "get_net_worth_change" for s in res["steps"]), res["steps"])
check("变化回答包含消费/收入/转账",
      all(k in res["answer"] for k in ("消费", "收入", "转账")), res["answer"])

# ---------- 购买模拟 ----------
res = run(A, "如果花3000元买手机，会影响我的储蓄目标吗？")
check("购买模拟完成", res["status"] == "completed", res["status"])
check("购买模拟不误走记账",
      not any(s["tool_name"] == "parse_bill" for s in res["steps"]), res["steps"])
check("购买模拟命中模拟工具",
      any(s["tool_name"] == "simulate_purchase" for s in res["steps"]), res["steps"])
check("购买模拟包含资产影响", "可动用资产" in res["answer"], res["answer"])
check("购买模拟结构化卡片", (res["evidence"].get("cards") or [{}])[0].get("type")
      == "simulation", res["evidence"])

# ---------- 储蓄计划（带资产上下文 + 审批） ----------
res = run(A, "我想在半年内攒下10000元")
check("储蓄计划等待审批", res["status"] == "awaiting_approval", res["status"])
check("储蓄计划读取资产上下文",
      any(s["tool_name"] == "get_asset_overview" for s in res["steps"]), res["steps"])
check("储蓄计划回答提及资产", "可动用资产" in res["answer"], res["answer"])
approval = (res.get("approvals") or [None])[0]
check("储蓄计划有审批卡", approval is not None, res)
r = client.post(f"/api/agent/approvals/{approval['id']}", headers=A,
                json={"decision": "approved", "edits": {}})
check("批准储蓄计划", r.status_code == 200 and r.json()["status"] == "completed", r.text)
goals = client.get("/api/goals", headers=A).json()
check("储蓄目标已写入", any(g["name"] == "旅行基金" and
                            Decimal(str(g["target_amount"])) == Decimal("10000.00")
                            for g in goals), goals)

# ---------- 用户隔离 ----------
res = run(B, "查看我的个人资产")
check("B 看不到 A 的资产", "还没有维护资产账户" in res["answer"], res["answer"])

print(f"\n全部通过：{PASSED} 项断言")
