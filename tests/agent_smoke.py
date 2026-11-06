# -*- coding: utf-8 -*-
"""Agent 专项冒烟测试：不依赖真实模型与 MySQL。

覆盖：
- 记账 → 预算冲击 → 审批 → 执行 → 幂等 → 撤销
- 订阅体检 → 拒绝 → 替代方案 → 批准
- 目标规划 → 创建目标 → 撤销
- 查询场景、主动扫描、跨用户隔离

运行：python tests/agent_smoke.py
"""
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = "sqlite:///./agent_smoke.db"
for f in Path(".").glob("agent_smoke.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import (  # noqa: E402
    AgentApproval, AgentMemory, Bill, BillCategory, BudgetAlert, CategoryBudget,
    SavingsGoal, Subscription,
)
from app.services import ai_service  # noqa: E402

# 强制走规则解析，避免测试依赖真实模型
config.AI_BASE_URL = ""
config.AI_API_KEY = ""
config.AI_MODEL = ""
config.AI_DAILY_LIMIT = 999

Base.metadata.create_all(bind=engine)
seed_default_categories()
client = TestClient(app)
PASSED = 0
MONTH = date.today().strftime("%Y-%m")


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        raise SystemExit(f"测试失败：{name} {detail}")
    PASSED += 1


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(username: str) -> tuple[str, int]:
    res = client.post("/api/auth/register", json={
        "username": username, "password": "agent123456", "nickname": username})
    check(f"注册 {username}", res.status_code == 200, res.text)
    body = res.json()
    return body["access_token"], body["user"]["id"]


def seed_user_data(user_id: int) -> None:
    db = SessionLocal()
    try:
        cats = {c.name: c.id for c in db.scalars(
            select(BillCategory).where(BillCategory.user_id.is_(None))).all()}
        # 餐饮预算 100，已花 90；交通预算 100，可调配
        db.add(CategoryBudget(user_id=user_id, category_id=cats["餐饮"],
                              month=MONTH, amount=Decimal("100.00")))
        db.add(CategoryBudget(user_id=user_id, category_id=cats["交通"],
                              month=MONTH, amount=Decimal("100.00")))
        db.add(Bill(user_id=user_id, category_id=cats["餐饮"], type="expense",
                    amount=Decimal("90.00"), bill_date=date.today(),
                    remark="测试餐饮", source="manual"))
        # 订阅：涨价 + 低频
        db.add(Subscription(
            user_id=user_id, name="测试视频会员", day_of_month=15,
            amount=Decimal("30.00"), category_id=cats["娱乐"],
            previous_amount=Decimal("25.00"), usage_90d=1,
            remark="涨价测试", remind_enabled=0, status="active",
            last_billed_month="", remind_month=""))
        db.commit()
    finally:
        db.close()


def count_bills(user_id: int) -> int:
    db = SessionLocal()
    try:
        return db.query(Bill).filter(Bill.user_id == user_id).count()
    finally:
        db.close()


def main() -> None:
    token, user_id = register("agent_tester")
    seed_user_data(user_id)
    h = auth(token)

    # 场景 1：记账 → 审批 → 执行 → 幂等 → 撤销
    res = client.post("/api/agent/run", json={"message": "午饭花了32元，微信付的"}, headers=h)
    check("记账任务返回 200", res.status_code == 200, res.text)
    run = res.json()
    check("记账任务等待审批", run["status"] == "awaiting_approval", str(run))
    check("记账生成审批", len(run["approvals"]) == 1, str(run["approvals"]))
    approval = run["approvals"][0]
    actions = [a["action"] for a in approval["diff"]["actions"]]
    check("包含写入账单", "create_bill" in actions, str(actions))
    check("包含预算调配", "set_category_budgets" in actions, str(actions))

    before = count_bills(user_id)
    res = client.post(f"/api/agent/approvals/{approval['id']}",
                      json={"decision": "approved"}, headers=h)
    check("批准执行返回 200", res.status_code == 200, res.text)
    done = res.json()
    check("批准后完成", done["status"] == "completed", str(done))
    check("账单已写入", count_bills(user_id) == before + 1, str(count_bills(user_id)))
    db = SessionLocal()
    try:
        alert_count = db.query(BudgetAlert).filter(BudgetAlert.user_id == user_id).count()
        check("Agent 执行触发预算预警", alert_count >= 1, str(alert_count))
    finally:
        db.close()
    verify_steps = [s for s in done["steps"] if s["tool_name"] == "verify_result"]
    check("执行后有真实校验", bool(verify_steps)
          and verify_steps[-1]["result"].get("all_ok") is True, str(verify_steps))

    # 重复批准幂等：不应再写一笔
    res = client.post(f"/api/agent/approvals/{approval['id']}",
                      json={"decision": "approved"}, headers=h)
    check("重复批准仍返回 200", res.status_code == 200, res.text)
    check("重复批准不重复写账单", count_bills(user_id) == before + 1,
          str(count_bills(user_id)))

    res = client.post(f"/api/agent/runs/{run['run_id']}/undo", json={}, headers=h)
    check("撤销返回 200", res.status_code == 200, res.text)
    check("撤销后状态为 undone", res.json()["status"] == "undone", res.text)
    check("撤销后账单删除", count_bills(user_id) == before, str(count_bills(user_id)))

    # 审批编辑：改成 50 元后，写入和文案都要用 50
    res = client.post("/api/agent/run", json={"message": "买咖啡18元"}, headers=h)
    edit_run = res.json()
    edit_approval = edit_run["approvals"][0]
    res = client.post(f"/api/agent/approvals/{edit_approval['id']}",
                      json={"decision": "approved", "edits": {"bill_amount": "50"}},
                      headers=h)
    edited = res.json()
    check("编辑金额后执行成功", res.status_code == 200 and edited["status"] == "completed",
          res.text)
    check("编辑金额写入 50", "50" in edited["answer"], edited["answer"])
    db = SessionLocal()
    try:
        latest = db.scalar(select(Bill).where(Bill.user_id == user_id)
                           .order_by(Bill.id.desc()))
        check("编辑后账单金额为 50", latest is not None and str(latest.amount) == "50.00",
              str(latest.amount if latest else None))
    finally:
        db.close()
    client.post(f"/api/agent/runs/{edit_run['run_id']}/undo", json={}, headers=h)

    # 记忆：星巴克→餐饮，规则解析不认识时用记忆纠正
    db = SessionLocal()
    try:
        db.add(AgentMemory(user_id=user_id, kind="merchant_category",
                           mem_key="星巴克", value_json='{"category": "餐饮"}'))
        db.commit()
    finally:
        db.close()
    res = client.post("/api/agent/run", json={"message": "星巴克 32 元"}, headers=h)
    mem_run = res.json()
    mem_bills = [a for a in mem_run["approvals"][0]["diff"]["actions"]
                 if a["action"] == "create_bill"]
    check("记忆纠正分类", mem_bills and mem_bills[0]["bill"]["category"] == "餐饮",
          str(mem_bills))
    check("回答提到记忆", "习惯" in mem_run["answer"], mem_run["answer"])

    # 场景 2：订阅体检 → 拒绝 → 替代方案 → 批准
    res = client.post("/api/agent/run", json={"message": "帮我检查订阅"}, headers=h)
    check("订阅任务返回 200", res.status_code == 200, res.text)
    sub_run = res.json()
    check("订阅任务等待审批", sub_run["status"] == "awaiting_approval", str(sub_run))
    sub_approval = sub_run["approvals"][0]
    check("订阅有替代方案", bool(sub_approval["diff"].get("alternatives")), str(sub_approval))

    res = client.post(f"/api/agent/approvals/{sub_approval['id']}",
                      json={"decision": "rejected"}, headers=h)
    check("拒绝返回 200", res.status_code == 200, res.text)
    replanned = res.json()
    pending = [a for a in replanned["approvals"] if a["status"] == "pending"]
    check("拒绝后生成替代审批", len(pending) == 1, str(replanned["approvals"]))
    res = client.post(f"/api/agent/approvals/{pending[0]['id']}",
                      json={"decision": "approved"}, headers=h)
    check("替代方案批准完成", res.status_code == 200 and res.json()["status"] == "completed",
          res.text)

    # 再次体检，批准暂停动作，验证订阅状态与撤销恢复
    res = client.post("/api/agent/run", json={"message": "检查订阅"}, headers=h)
    pause_run = res.json()
    pause_approval = pause_run["approvals"][0]
    res = client.post(f"/api/agent/approvals/{pause_approval['id']}",
                      json={"decision": "approved"}, headers=h)
    check("订阅暂停执行成功", res.status_code == 200 and res.json()["status"] == "completed",
          res.text)
    db = SessionLocal()
    try:
        sub = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
        check("订阅状态为 paused", sub is not None and sub.status == "paused",
              str(sub.status if sub else None))
    finally:
        db.close()
    res = client.post(f"/api/agent/runs/{pause_run['run_id']}/undo", json={}, headers=h)
    check("订阅撤销成功", res.status_code == 200 and res.json()["status"] == "undone",
          res.text)
    db = SessionLocal()
    try:
        sub = db.scalar(select(Subscription).where(Subscription.user_id == user_id))
        check("撤销后订阅恢复 active", sub is not None and sub.status == "active",
              str(sub.status if sub else None))
    finally:
        db.close()

    # 场景 3：目标规划 → 审批 → 创建目标 → 撤销
    res = client.post("/api/agent/run", json={"message": "3个月存3000元去旅行"}, headers=h)
    check("目标任务返回 200", res.status_code == 200, res.text)
    goal_run = res.json()
    check("目标任务等待审批", goal_run["status"] == "awaiting_approval", str(goal_run))
    goal_approval = goal_run["approvals"][0]
    goal_actions = [a["action"] for a in goal_approval["diff"]["actions"]]
    check("目标方案包含创建目标", "create_goal" in goal_actions, str(goal_actions))
    check("目标名称解析正确", goal_approval["diff"]["actions"][0]["goal"]["name"] == "旅行基金",
          str(goal_approval["diff"]["actions"][0]))
    res = client.post(f"/api/agent/approvals/{goal_approval['id']}",
                      json={"decision": "approved"}, headers=h)
    check("目标批准完成", res.status_code == 200 and res.json()["status"] == "completed",
          res.text)
    db = SessionLocal()
    try:
        goal = db.scalar(select(SavingsGoal).where(SavingsGoal.user_id == user_id,
                                                   SavingsGoal.name == "旅行基金"))
        check("目标已创建", goal is not None)
        check("目标周期已保存", goal is not None and goal.target_months == 3,
              str(goal.target_months if goal else None))
    finally:
        db.close()
    res = client.post(f"/api/agent/runs/{goal_run['run_id']}/undo", json={}, headers=h)
    check("目标撤销成功", res.status_code == 200 and res.json()["status"] == "undone",
          res.text)
    db = SessionLocal()
    try:
        goal = db.scalar(select(SavingsGoal).where(SavingsGoal.user_id == user_id,
                                                   SavingsGoal.name == "旅行基金"))
        check("撤销后目标删除", goal is None)
    finally:
        db.close()

    # 查询场景
    res = client.post("/api/agent/run", json={"message": "这个月花了多少"}, headers=h)
    check("查询任务完成", res.status_code == 200 and res.json()["status"] == "completed",
          res.text)
    check("查询有回答", bool(res.json()["answer"]), res.text)

    # 查询月份：支持“上个月”，金额来自真实账单
    prev_day = date.today().replace(day=1) - timedelta(days=1)
    client.post("/api/bills", headers=h, json={
        "type": "expense", "amount": "123.45", "category": "餐饮",
        "bill_date": prev_day.isoformat(), "remark": "上月测试账单"})
    res = client.post("/api/agent/run", json={"message": "上个月花了多少"}, headers=h)
    prev_run = res.json()
    check("上月查询完成", prev_run["status"] == "completed", res.text)
    check("上月查询月份正确", prev_day.strftime("%Y-%m") in prev_run["answer"],
          prev_run["answer"])
    check("上月查询金额正确", "123.45" in prev_run["answer"], prev_run["answer"])

    # 主动扫描 + 通知持久化/去重/已读/忽略
    res = client.post("/api/agent/proactive/scan", json={}, headers=h)
    check("主动扫描返回 200", res.status_code == 200, res.text)
    scan = res.json()
    check("主动扫描返回列表", isinstance(scan.get("items"), list), res.text)
    check("主动扫描有未读数", scan.get("unread_count", 0) >= 1, str(scan))
    check("扫描项带通知 id", all(item.get("id") for item in scan["items"]), str(scan))
    first_id = scan["items"][0]["id"]

    res = client.post("/api/agent/proactive/scan", json={}, headers=h)
    check("重复扫描不新增通知", res.json().get("unread_count") == scan.get("unread_count"),
          res.text)

    res = client.get("/api/agent/notifications", headers=h)
    check("通知列表返回", res.status_code == 200 and isinstance(res.json(), list), res.text)
    res = client.post(f"/api/agent/notifications/{first_id}/action",
                      json={"action": "read"}, headers=h)
    check("通知标记已读", res.status_code == 200 and res.json()["status"] == "read", res.text)
    res = client.get("/api/agent/notifications/unread-count", headers=h)
    check("已读后未读数下降", res.json()["count"] == scan["unread_count"] - 1, res.text)

    # 过期审批：把 expires_at 改到过去，批准应失败
    res = client.post("/api/agent/run", json={"message": "午饭花了12元"}, headers=h)
    exp_run = res.json()
    exp_approval = exp_run["approvals"][0]
    db = SessionLocal()
    try:
        row = db.get(AgentApproval, exp_approval["id"])
        row.expires_at = datetime.now() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    res = client.post(f"/api/agent/approvals/{exp_approval['id']}",
                      json={"decision": "approved"}, headers=h)
    check("过期审批不能执行", res.status_code == 200 and res.json()["status"] == "failed",
          res.text)

    # 多笔账单：模型返回两个 bills，应生成两个 create_bill 动作
    async def fake_chat_json(*args, **kwargs):
        return {"bills": [
            {"type": "expense", "amount": 32, "category": "餐饮",
             "bill_date": date.today().isoformat(), "remark": "午饭"},
            {"type": "expense", "amount": 21, "category": "交通",
             "bill_date": date.today().isoformat(), "remark": "打车"},
        ], "notice": ""}

    old_config = (config.AI_BASE_URL, config.AI_API_KEY, config.AI_MODEL)
    original_chat_json = ai_service.chat_json
    config.AI_BASE_URL, config.AI_API_KEY, config.AI_MODEL = "http://fake", "fake", "fake"
    ai_service.chat_json = fake_chat_json
    try:
        res = client.post("/api/agent/run", json={"message": "午饭32，打车21"}, headers=h)
        multi = res.json()
        multi_bills = [a for a in multi["approvals"][0]["diff"]["actions"]
                       if a["action"] == "create_bill"]
        check("多笔账单生成两个动作", len(multi_bills) == 2, str(multi_bills))
    finally:
        ai_service.chat_json = original_chat_json
        config.AI_BASE_URL, config.AI_API_KEY, config.AI_MODEL = old_config

    # 敏感信息：先脱敏再解析，不能把密码带进回答或审批 diff
    res = client.post("/api/agent/run",
                      json={"message": "用我的银行卡密码 123456 记账"}, headers=h)
    check("纯密码输入不生成账单", res.json()["status"] == "needs_input", res.text)
    check("密码数字未进入响应", "123456" not in res.text, res.text[:200])

    res = client.post("/api/agent/run",
                      json={"message": "我的密码是 abc123，记一笔午饭32"}, headers=h)
    secure_run = res.json()
    check("含密码但仍能识别真实消费",
          secure_run["status"] == "awaiting_approval", res.text)
    check("非数字密码未进入响应", "abc123" not in res.text, res.text[:300])
    secure_bills = [a for a in secure_run["approvals"][0]["diff"]["actions"]
                    if a["action"] == "create_bill"]
    check("真实消费金额仍为 32", secure_bills
          and secure_bills[0]["bill"]["amount"] == "32.00", str(secure_bills))

    # 跨用户隔离
    other_token, _ = register("agent_other")
    res = client.get(f"/api/agent/runs/{run['run_id']}", headers=auth(other_token))
    check("跨用户读取轨迹返回 404", res.status_code == 404, res.text)
    res = client.post(f"/api/agent/approvals/{approval['id']}",
                      json={"decision": "approved"}, headers=auth(other_token))
    check("跨用户审批返回 404", res.status_code == 404, res.text)

    # 健康检查
    res = client.get("/api/agent/health")
    check("Agent 健康检查", res.status_code == 200 and res.json()["ok"], res.text)

    print(f"\n全部通过：{PASSED} 项断言")


if __name__ == "__main__":
    main()
