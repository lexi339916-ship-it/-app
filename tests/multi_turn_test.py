# -*- coding: utf-8 -*-
"""多轮对话测试：会话隔离、追问重规划、替代方案、审批替代与撤销。

运行：python tests/multi_turn_test.py
"""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./multi_turn.db"
for f in Path(".").glob("multi_turn.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import (  # noqa: E402
    AgentApproval, AgentRun, Bill, BillCategory, CategoryBudget, Note,
    Subscription,
)

config.AI_BASE_URL = ""
config.AI_API_KEY = ""
config.AI_MODEL = ""
config.AI_DAILY_LIMIT = 999
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


def register(username: str) -> tuple[dict, int]:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


def cat_id(db, name: str, type_: str = "expense") -> int:
    return db.scalar(select(BillCategory.id).where(
        BillCategory.name == name, BillCategory.type == type_,
        BillCategory.user_id.is_(None)))


def run(headers: dict, message: str, session_id: str | None = None,
        parent_run_id: int | None = None, mode: str = "auto") -> dict:
    data = {"message": message, "mode": mode}
    if session_id:
        data["session_id"] = session_id
    if parent_run_id:
        data["parent_run_id"] = parent_run_id
    r = client.post("/api/agent/run", json=data, headers=headers)
    check(f"运行「{message}」返回 200", r.status_code == 200, r.text[:300])
    return r.json()


def budget(uid: int, cid: int, month: str) -> Decimal | None:
    with SessionLocal() as db:
        row = db.scalar(select(CategoryBudget).where(
            CategoryBudget.user_id == uid, CategoryBudget.category_id == cid,
            CategoryBudget.month == month))
        return Decimal(str(row.amount)) if row else None


H_A, UID_A = register("multi_a")
H_B, UID_B = register("multi_b")
MONTH = date.today().strftime("%Y-%m")
TODAY = date.today()

with SessionLocal() as db:
    income = cat_id(db, "工资", "income")
    food = cat_id(db, "餐饮")
    fun = cat_id(db, "娱乐")
    traffic = cat_id(db, "交通")
    db.add(Bill(user_id=UID_A, category_id=income, type="income",
                amount=Decimal("1000"), bill_date=TODAY, remark="工资"))
    for cid, amount in ((food, "90"), (fun, "100"), (traffic, "100")):
        db.add(Bill(user_id=UID_A, category_id=cid, type="expense",
                    amount=Decimal(amount), bill_date=TODAY, remark="基础支出"))
    for cid, amount in ((food, "100"), (fun, "500"), (traffic, "200")):
        db.add(CategoryBudget(user_id=UID_A, category_id=cid, month=MONTH,
                              amount=Decimal(amount), source="manual"))
    db.add(Subscription(user_id=UID_A, name="视频会员", day_of_month=10,
                        amount=Decimal("30"), previous_amount=Decimal("20"),
                        usage_90d=1, status="active"))
    db.commit()

# ---------------- 1. 第一轮：记账 → 预算调配审批 ----------------
r1 = run(H_A, "午饭花了20元")
check("第一轮生成会话 id", bool(r1.get("session_id")), str(r1))
check("第一轮 turn_index=0", r1.get("turn_index") == 0, str(r1))
check("第一轮等待审批", r1["status"] == "awaiting_approval", r1["status"])
S1 = r1["session_id"]
approval1 = r1["approvals"][0]
rebalance1 = approval1["diff"]["impact"].get("rebalance") or {}
check("第一轮从娱乐调配", rebalance1.get("from") == "娱乐", str(rebalance1))
check("第一轮调配 50", Decimal(str(rebalance1.get("amount"))) == Decimal("50"), str(rebalance1))

# ---------------- 2. 追问：不想动娱乐 → 换来源 ----------------
r2 = run(H_A, "我不想动娱乐预算，还有其他方案吗？", S1, r1["run_id"])
check("追问生成新一轮", r2.get("run_id") != r1["run_id"], str(r2))
check("追问 turn_index=1", r2.get("turn_index") == 1, str(r2))
check("追问 parent_run_id 正确", r2.get("parent_run_id") == r1["run_id"], str(r2))
check("追问等待审批", r2["status"] == "awaiting_approval", r2["status"])
new_actions = r2["approvals"][0]["diff"]["actions"]
budget_actions = [a for a in new_actions if a["action"] == "set_category_budgets"]
check("追问方案仍含预算调配", len(budget_actions) == 1, str(new_actions))
items = budget_actions[0]["items"] if budget_actions else []
check("追问不再动娱乐", all(i.get("category_name") != "娱乐" for i in items), str(items))
check("追问改从交通调配", any(i.get("category_name") == "交通" for i in items), str(items))
check("追问方案保留账单",
      any(a["action"] == "create_bill" for a in new_actions), str(new_actions))
with SessionLocal() as db:
    old = db.get(AgentApproval, approval1["id"])
    old_run = db.get(AgentRun, r1["run_id"])
    check("旧审批标记 superseded", old.status == "superseded", old.status)
    check("旧任务标记 superseded", old_run.status == "superseded", old_run.status)

# ---------------- 3. 追问：只调整 100 元 ----------------
r3 = run(H_A, "只调整100元", S1, r1["run_id"])
check("改金额进入第二轮追问", r3.get("turn_index") == 2, str(r3))
check("改金额等待审批", r3["status"] == "awaiting_approval", r3["status"])
budget3 = [a for a in r3["approvals"][0]["diff"]["actions"]
           if a["action"] == "set_category_budgets"][0]
items3 = {i["category_name"]: Decimal(str(i["amount"])) for i in budget3["items"]}
check("娱乐预算调为 400", items3.get("娱乐") == Decimal("400.00"), str(items3))
check("餐饮预算调为 200", items3.get("餐饮") == Decimal("200.00"), str(items3))
check("改金额后的 rebalance=100",
      Decimal(str(r3["approvals"][0]["diff"]["impact"]["rebalance"]["amount"]))
      == Decimal("100"), str(r3["approvals"][0]["diff"]["impact"]))

# ---------------- 4. 批准追问方案 → 数据库校验 → 撤销 ----------------
status = client.post(f"/api/agent/approvals/{r2['approvals'][0]['id']}",
                     json={"decision": "approved"}, headers=H_A)
check("批准追问方案返回 200", status.status_code == 200, status.text)
check("追问方案执行完成", status.json().get("status") == "completed", status.text)
with SessionLocal() as db:
    food = cat_id(db, "餐饮")
    fun = cat_id(db, "娱乐")
    traffic = cat_id(db, "交通")
check("交通预算 150", budget(UID_A, traffic, MONTH) == Decimal("150.00"),
      str(budget(UID_A, traffic, MONTH)))
check("餐饮预算 150", budget(UID_A, food, MONTH) == Decimal("150.00"),
      str(budget(UID_A, food, MONTH)))
check("娱乐预算保持 500", budget(UID_A, fun, MONTH) == Decimal("500.00"),
      str(budget(UID_A, fun, MONTH)))
r = client.post(f"/api/agent/runs/{r2['run_id']}/undo", json={}, headers=H_A)
check("追问方案可撤销", r.status_code == 200, r.text)
check("撤销后交通恢复 200", budget(UID_A, traffic, MONTH) == Decimal("200.00"),
      str(budget(UID_A, traffic, MONTH)))
check("撤销后餐饮恢复 100", budget(UID_A, food, MONTH) == Decimal("100.00"),
      str(budget(UID_A, food, MONTH)))

# 清理第三轮待审批，避免遗留
client.post(f"/api/agent/approvals/{r3['approvals'][0]['id']}",
            json={"decision": "rejected"}, headers=H_A)

# ---------------- 5. 订阅替代方案：选择第二种 ----------------
r4 = run(H_A, "帮我检查订阅")
check("订阅第一轮等待审批", r4["status"] == "awaiting_approval", r4["status"])
check("订阅方案有替代项", bool(r4["approvals"][0]["diff"].get("alternatives")),
      str(r4["approvals"][0]["diff"]))
S2 = r4["session_id"]
r5 = run(H_A, "选择第二种方案", S2, r4["run_id"])
check("选择替代方案等待审批", r5["status"] == "awaiting_approval", r5["status"])
actions5 = r5["approvals"][0]["diff"]["actions"]
check("替代方案只创建任务", [a["action"] for a in actions5] == ["create_task"],
      str(actions5))
with SessionLocal() as db:
    old4 = db.get(AgentApproval, r4["approvals"][0]["id"])
    check("订阅旧审批被替代", old4.status == "superseded", old4.status)
status = client.post(f"/api/agent/approvals/{r5['approvals'][0]['id']}",
                     json={"decision": "approved"}, headers=H_A)
check("替代方案可执行", status.status_code == 200
      and status.json().get("status") == "completed", status.text)
client.post(f"/api/agent/runs/{r5['run_id']}/undo", json={}, headers=H_A)

# ---------------- 6. 会话历史与摘要 ----------------
r = client.get(f"/api/agent/sessions/{S1}", headers=H_A)
check("会话历史返回 200", r.status_code == 200, r.text)
history = r.json()
check("会话历史 3 轮", len(history) == 3, str(len(history)))
check("会话历史按轮次排序",
      [x["turn_index"] for x in history] == [0, 1, 2],
      str([x["turn_index"] for x in history]))
r = client.get("/api/agent/sessions", headers=H_A)
check("会话摘要返回 200", r.status_code == 200, r.text)
summary = r.json()
check("摘要包含 S1", any(x["session_id"] == S1 for x in summary), str(summary))
check("摘要轮次数正确",
      next(x["turn_count"] for x in summary if x["session_id"] == S1) == 3,
      str(summary))

# ---------------- 7. 跨用户隔离 ----------------
r = client.get(f"/api/agent/sessions/{S1}", headers=H_B)
check("跨用户读会话 404", r.status_code == 404, r.text)
r = client.post("/api/agent/run", json={
    "message": "只调整100元", "session_id": S1, "parent_run_id": r1["run_id"]},
    headers=H_B)
check("跨用户追问 404", r.status_code == 404, r.text)

# ---------------- 8. 无上下文追问不崩溃 ----------------
r = run(H_A, "不想动娱乐预算")
check("无上下文追问不报错", r["status"] in ("completed", "needs_input"),
      str(r["status"]))

# ---------------- 9. 审批隔离：旧审批不能再执行 ----------------
r = client.post(f"/api/agent/approvals/{approval1['id']}",
                json={"decision": "approved"}, headers=H_A)
check("被替代审批不可执行", r.status_code == 200, r.text)
with SessionLocal() as db:
    old = db.get(AgentApproval, approval1["id"])
    check("旧审批仍是 superseded", old.status == "superseded", old.status)


from datetime import datetime as _dt  # noqa: E402

_report = Path(__file__).resolve().parent / "agent_eval" / "multi_turn_report.md"
_report.parent.mkdir(parents=True, exist_ok=True)
_lines = [
    "# 多轮对话测试报告（团队自测）",
    "",
    f"- 生成时间：{_dt.now().isoformat(timespec='seconds')}",
    f"- 断言：{PASSED}，通过：{PASSED}，失败：0",
    "- 覆盖：会话链路、换预算来源、改调配金额、选替代方案、"
    "旧审批 superseded、执行回查、撤销、跨用户隔离。",
    "",
]
_report.write_text(chr(10).join(_lines), encoding="utf-8")

print(f"\n全部通过：{PASSED} 项断言")
