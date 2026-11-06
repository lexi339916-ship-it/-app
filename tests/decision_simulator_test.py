# -*- coding: utf-8 -*-
"""消费决策模拟器测试：预算冲击、目标差额/延期、方案、缺数据与越权。

运行：python tests/decision_simulator_test.py
"""
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./decision_sim.db"
for f in Path(".").glob("decision_sim.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import Bill, BillCategory, CategoryBudget, SavingsGoal  # noqa: E402

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


def register(username: str) -> tuple[dict, int]:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]["id"]


def cat_id(db, name: str, type_: str = "expense") -> int:
    return db.scalar(select(BillCategory.id).where(
        BillCategory.name == name, BillCategory.type == type_,
        BillCategory.user_id.is_(None)))


def shift_day(month_offset: int, day: int = 15) -> date:
    index = date.today().year * 12 + date.today().month - 1 - month_offset
    year, mon = index // 12, index % 12 + 1
    return date(year, mon, day)


def seed_history(db, uid: int, cats: dict, with_goal: bool = True) -> None:
    for offset in (1, 2, 3):
        d = shift_day(offset)
        db.add(Bill(user_id=uid, category_id=cats["工资"], type="income",
                    amount=Decimal("9000"), bill_date=d, remark="工资"))
        for name, amount in (("住房", "2500"), ("餐饮", "1000"),
                             ("购物", "1000"), ("娱乐", "500")):
            db.add(Bill(user_id=uid, category_id=cats[name], type="expense",
                        amount=Decimal(amount), bill_date=d, remark=name))
    today = date.today()
    db.add(Bill(user_id=uid, category_id=cats["工资"], type="income",
                amount=Decimal("9000"), bill_date=today, remark="工资"))
    for name, amount in (("住房", "2500"), ("餐饮", "500"),
                         ("购物", "1000"), ("娱乐", "500")):
        db.add(Bill(user_id=uid, category_id=cats[name], type="expense",
                    amount=Decimal(amount), bill_date=today, remark=name))
    if with_goal:
        db.add(SavingsGoal(user_id=uid, name="旅行基金",
                           target_amount=Decimal("50000"),
                           saved_amount=Decimal("5000"), target_months=12,
                           created_at=datetime.now()))


def seed_budgets(db, uid: int, cats: dict, empty: bool = False) -> None:
    if empty:
        return
    month = date.today().strftime("%Y-%m")
    for name, amount in (("购物", "3000"), ("餐饮", "3000"),
                         ("娱乐", "3000"), ("住房", "2500")):
        db.add(CategoryBudget(user_id=uid, category_id=cats[name], month=month,
                              amount=Decimal(amount), source="manual"))


H_A, UID_A = register("sim_a")
H_B, UID_B = register("sim_b")
H_C, UID_C = register("sim_no_goal")
H_D, UID_D = register("sim_no_cash")
H_E, UID_E = register("sim_no_budget")
H_F, UID_F = register("sim_no_deadline")

with SessionLocal() as db:
    cats = {name: cat_id(db, name) for name in
            ("工资", "住房", "餐饮", "购物", "娱乐")}
    seed_history(db, UID_A, cats, with_goal=True)
    seed_budgets(db, UID_A, cats)
    seed_history(db, UID_B, cats, with_goal=True)
    seed_budgets(db, UID_B, cats)
    seed_history(db, UID_C, cats, with_goal=False)
    seed_budgets(db, UID_C, cats)
    # D 没有账单，但有一个目标
    db.add(SavingsGoal(user_id=UID_D, name="应急金",
                       target_amount=Decimal("10000"), saved_amount=Decimal("0"),
                       target_months=6, created_at=datetime.now()))
    # E 有账单和目标，但没有预算
    seed_history(db, UID_E, cats, with_goal=True)
    # F 有账单、目标和预算，但目标没有周期
    seed_history(db, UID_F, cats, with_goal=False)
    seed_budgets(db, UID_F, cats)
    db.add(SavingsGoal(user_id=UID_F, name="相机基金",
                       target_amount=Decimal("5000"), saved_amount=Decimal("1000"),
                       target_months=None, created_at=datetime.now()))
    db.commit()

with SessionLocal() as db:
    goal_id_a = db.scalar(select(SavingsGoal.id).where(SavingsGoal.user_id == UID_A))

# ---------------- 1. 正常测算：5000 元购物 ----------------
r = client.post("/api/decision-simulator/simulate", headers=H_A, json={
    "amount": "5000", "category": "购物", "horizon_months": 3})
check("模拟返回 200", r.status_code == 200, r.text)
j = r.json()
check("模拟可用", j.get("available") is True, str(j.get("missing")))
check("无缺失项", j.get("missing") == [], str(j.get("missing")))
check("月均收入 9000", j["cashflow"]["monthly_income"] == "9000.00", str(j["cashflow"]))
check("月均支出 5000", j["cashflow"]["monthly_expense"] == "5000.00", str(j["cashflow"]))
check("月均结余 4000", j["cashflow"]["monthly_net"] == "4000.00", str(j["cashflow"]))
check("账单样本 15 笔", j["cashflow"]["bill_count"] == 15, str(j["cashflow"]))
check("购买后本月结余 -1000",
      j["purchase"]["monthly_net_after"] == "-1000.00", str(j["purchase"]))

check("预算来源分类", j["purchase"]["source"] == "category", str(j["purchase"]))
check("购物预算 3000", j["purchase"]["category_budget"] == "3000.00", str(j["purchase"]))
check("购物已花 1000", j["purchase"]["category_spent"] == "1000.00", str(j["purchase"]))
check("购买前剩余 2000", j["purchase"]["budget_remaining_before"] == "2000.00", str(j["purchase"]))
check("购买后剩余 -3000", j["purchase"]["budget_remaining_after"] == "-3000.00", str(j["purchase"]))
check("预算超支 3000", j["purchase"]["over_budget"] is True
      and j["purchase"]["over_amount"] == "3000.00", str(j["purchase"]))

goal = j["goal"]
check("目标存在", goal is not None)
check("目标还差 45000", goal["remaining"] == "45000.00", str(goal))
check("购买前目标差额 0", goal["gap_before"] == "0.00", str(goal))
check("购买后目标差额 >0", Decimal(goal["gap_after"]) > 0, str(goal))
check("目标预计延期 10~20 天", 10 <= (goal["delay_days"] or 0) <= 20, str(goal))
check("目标额外耗时 30~45 天", 30 <= (goal["extra_days"] or 0) <= 45, str(goal))
check("目标状态 delayed", goal["status"] == "delayed", str(goal))

scenarios = {s["key"]: s for s in j["scenarios"]}
check("三种方案", set(scenarios) == {"buy_now", "next_month", "offset_by_cutting"},
      str(scenarios))
check("现在购买预算冲击 -3000",
      scenarios["buy_now"]["budget_impact"] == "-3000.00", str(scenarios["buy_now"]))
check("下月购买本月预算 0",
      scenarios["next_month"]["budget_impact"] == "0.00", str(scenarios["next_month"]))
check("压缩支出可行", scenarios["offset_by_cutting"]["feasible"] is True,
      str(scenarios["offset_by_cutting"]))
check("压缩后目标不延期",
      scenarios["offset_by_cutting"]["goal_delay_days"] == 0,
      str(scenarios["offset_by_cutting"]))
check("每月压缩约 1666.67",
      scenarios["offset_by_cutting"]["monthly_cut"] == "1666.67",
      str(scenarios["offset_by_cutting"]))
check("建议包含预算超支", any("预算" in x["title"] for x in j["recommendations"]),
      str(j["recommendations"]))
check("建议包含目标延期", any("延期" in x["title"] for x in j["recommendations"]),
      str(j["recommendations"]))
check("摘要包含金额", "5000" in j["message"], j["message"])
check("免责声明", "不代表账户真实余额" in j["disclaimer"])
check("假设说明非空", len(j["assumptions"]) >= 2, str(j["assumptions"]))

# ---------------- 2. 小额购买：不影响预算/目标 ----------------
r = client.post("/api/decision-simulator/simulate", headers=H_A, json={
    "amount": "1000", "category": "购物", "horizon_months": 3})
j2 = r.json()
check("小额购买不超预算", j2["purchase"]["over_budget"] is False, str(j2["purchase"]))
check("小额购买目标差额 0", j2["goal"]["gap_after"] == "0.00", str(j2["goal"]))
check("小额购买不延期", j2["goal"]["delay_days"] == 0, str(j2["goal"]))

# ---------------- 3. 缺目标 / 缺账单 / 缺预算 ----------------
r = client.post("/api/decision-simulator/simulate", headers=H_C, json={
    "amount": "5000", "category": "购物"})
j3 = r.json()
check("缺目标不可用", j3["available"] is False, str(j3))
check("缺目标 missing=goal", "goal" in j3["missing"], str(j3["missing"]))
check("缺目标提示创建", "创建" in j3["message"], j3["message"])
check("缺目标不返回 goal", j3["goal"] is None)

r = client.post("/api/decision-simulator/simulate", headers=H_D, json={
    "amount": "5000", "category": "购物"})
j4 = r.json()
check("缺账单不可用", j4["available"] is False, str(j4))
check("缺账单 missing=cashflow", "cashflow" in j4["missing"], str(j4["missing"]))
check("缺账单提示先记账", "账单" in j4["message"], j4["message"])

r = client.post("/api/decision-simulator/simulate", headers=H_E, json={
    "amount": "5000", "category": "购物"})
j5 = r.json()
check("缺预算仍可算目标", j5["available"] is True, str(j5["missing"]))
check("缺预算 missing=budget", "budget" in j5["missing"], str(j5["missing"]))
check("缺预算 purchase.available=False", j5["purchase"]["available"] is False,
      str(j5["purchase"]))

# ---------------- 4. 校验与越权 ----------------
r = client.post("/api/decision-simulator/simulate", headers=H_B, json={
    "amount": "5000", "category": "购物", "goal_id": goal_id_a})
check("跨用户目标 404", r.status_code == 404, r.text)
r = client.post("/api/decision-simulator/simulate", headers=H_A, json={
    "amount": "5000", "category": "不存在的分类"})
check("非法分类 400", r.status_code == 400, r.text)
r = client.post("/api/decision-simulator/simulate", headers=H_A, json={
    "amount": "0", "category": "购物"})
check("金额 0 返回 422", r.status_code == 422, r.text)
r = client.post("/api/decision-simulator/simulate", json={
    "amount": "5000", "category": "购物"})
check("未登录 401", r.status_code == 401, r.text)

# ---------------- 5. 无周期目标：完成时间晚但在观察期内 ----------------
r = client.post("/api/decision-simulator/simulate", headers=H_F, json={
    "amount": "5000", "category": "购物", "horizon_months": 3})
jf = r.json()
check("无周期目标可用", jf["available"] is True, str(jf.get("missing")))
check("无周期目标状态", jf["goal"]["status"] == "no_deadline", str(jf["goal"]))
check("无周期目标不延期", jf["goal"]["delay_days"] == 0, str(jf["goal"]))
check("无周期目标完成时间变晚", (jf["goal"]["extra_days"] or 0) > 0, str(jf["goal"]))
check("无周期目标提示完成变晚", "晚约" in jf["message"], jf["message"])

# ---------------- 6. 用户隔离 ----------------
r = client.post("/api/decision-simulator/simulate", headers=H_B, json={
    "amount": "5000", "category": "购物"})
jb = r.json()
check("用户 B 独立测算", jb["goal"]["name"] == "旅行基金", str(jb.get("goal")))
check("用户 B 不读取 A 的目标 id", jb["goal"]["id"] != goal_id_a, str(jb["goal"]))


from datetime import datetime as _dt  # noqa: E402

_report = Path(__file__).resolve().parent / "agent_eval" / "decision_simulator_report.md"
_report.parent.mkdir(parents=True, exist_ok=True)
_lines = [
    "# 消费决策模拟器测试报告（团队自测）",
    "",
    f"- 生成时间：{_dt.now().isoformat(timespec='seconds')}",
    f"- 断言：{PASSED}，通过：{PASSED}，失败：0",
    "- 覆盖：预算冲击、目标差额/延期、三种方案、缺目标/缺账单/缺预算、越权与用户隔离。",
    "",
]
_report.write_text(chr(10).join(_lines), encoding="utf-8")

print(f"\n全部通过：{PASSED} 项断言")
