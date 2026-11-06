# -*- coding: utf-8 -*-
"""消费健康诊断测试：公式、数据隔离、空数据、月份校验。

运行：python tests/health_report_test.py
"""
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./health_report.db"
for f in Path(".").glob("health_report.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import (  # noqa: E402
    Bill, BillCategory, CategoryBudget, Note, SavingsGoal, Subscription,
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


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def shift_month(d: date, delta: int) -> date:
    index = d.year * 12 + (d.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def register(username: str) -> dict:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def category_id(db, name: str, type_: str = "expense") -> int:
    row = db.scalar(select(BillCategory).where(
        BillCategory.name == name, BillCategory.type == type_,
        BillCategory.user_id.is_(None)))
    return row.id


def add_bill(db, user_id: int, cid: int | None, type_: str, amount: str,
             day: date, source: str = "manual", remark: str = "") -> None:
    db.add(Bill(user_id=user_id, category_id=cid, type=type_,
                amount=Decimal(amount), bill_date=day, source=source,
                remark=remark or f"{type_} {amount}"))


today = date.today()
current = month_key(today)
cur_day = date(today.year, today.month, min(today.day, 28))
prev1 = shift_month(today, -1)
prev2 = shift_month(today, -2)
prev3 = shift_month(today, -3)

H_A = register("health_a")
H_B = register("health_b")
uid_a = client.get("/api/auth/me", headers=H_A).json()["id"]
uid_b = client.get("/api/auth/me", headers=H_B).json()["id"]

db = SessionLocal()
try:
    ids = {name: category_id(db, name) for name in
           ("餐饮", "交通", "购物", "娱乐", "医疗")}
    ids["工资"] = category_id(db, "工资", "income")

    # 本月：收入 8000；支出 餐饮 1200 / 娱乐 400 / 购物 300 / 交通 200 / 医疗 500
    add_bill(db, uid_a, ids["工资"], "income", "8000", cur_day, remark="工资")
    add_bill(db, uid_a, ids["餐饮"], "expense", "1200", cur_day)
    add_bill(db, uid_a, ids["娱乐"], "expense", "400", cur_day)
    add_bill(db, uid_a, ids["购物"], "expense", "300", cur_day)
    add_bill(db, uid_a, ids["交通"], "expense", "200", cur_day)
    add_bill(db, uid_a, ids["医疗"], "expense", "500", cur_day)

    # 前 3 个月：餐饮/娱乐/购物/交通；医疗每月几笔小额，用于异常检测
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

    # 本月分类预算：餐饮 1000（超支）、娱乐 500（80%）、购物 200（超支）、交通 300（正常）
    for name, amount in (("餐饮", "1000"), ("娱乐", "500"),
                         ("购物", "200"), ("交通", "300"), ("医疗", "500")):
        db.add(CategoryBudget(user_id=uid_a, category_id=ids[name],
                              month=current, amount=Decimal(amount), source="manual"))

    # 储蓄目标：6 万 / 3 个月，已存 1000；按当前结余会延期
    db.add(SavingsGoal(
        user_id=uid_a, name="旅行基金", target_amount=Decimal("60000"),
        saved_amount=Decimal("1000"), target_months=3,
        created_at=datetime.now() - timedelta(days=60)))

    # 订阅：视频会员涨价 + 低频；音乐会员正常
    db.add(Subscription(
        user_id=uid_a, name="视频会员", day_of_month=10, amount=Decimal("25"),
        previous_amount=Decimal("20"), usage_90d=1, status="active",
        last_billed_month=current))
    db.add(Subscription(
        user_id=uid_a, name="音乐会员", day_of_month=12, amount=Decimal("15"),
        usage_90d=20, status="active", last_billed_month=current))
    add_bill(db, uid_a, ids["娱乐"], "expense", "25", cur_day,
             source="subscription", remark="视频会员 · 自动订阅扣费")

    # 计划执行：本月到期 3 个任务，2 个完成
    for title, status in (("复盘餐饮", "done"), ("控制娱乐", "done"), ("检查订阅", "open")):
        db.add(Note(user_id=uid_a, title=title, content="", note_type="todo",
                    status=status, due_at=datetime.combine(cur_day, datetime.min.time())))
    db.commit()
finally:
    db.close()

# ---------------- 正常报告 ----------------
r = client.get("/api/consumption-health/report", headers=H_A,
               params={"month": current})
check("健康报告返回 200", r.status_code == 200, r.text)
j = r.json()
check("报告月份正确", j["month"] == current)
check("本月收入 8000", j["overview"]["income"] == "8000.00", str(j["overview"]))
check("本月支出 2625", j["overview"]["expense"] == "2625.00", str(j["overview"]))
check("本月结余 5375", j["overview"]["net"] == "5375.00", str(j["overview"]))
check("账单数 7", j["overview"]["bill_count"] == 7, str(j["overview"]))
check("结余率 0.6719", j["overview"]["savings_rate"] == 0.6719, str(j["overview"]))
check("上月支出 1600", j["overview"]["prev_expense"] == "1600.00", str(j["overview"]))

check("分类含餐饮", any(c["category"] == "餐饮" for c in j["categories"]))
catering = next(c for c in j["categories"] if c["category"] == "餐饮")
check("餐饮超预算", catering["budget_status"] == "over100", str(catering))
check("餐饮剩余 -200", catering["remaining"] == "-200.00", str(catering))
check("预算超支分类 2 个", j["budget"]["over_count"] == 2, str(j["budget"]))
check("预算接近上限 1 个", j["budget"]["near_count"] == 1, str(j["budget"]))
check("预算刚好用完 1 个", j["budget"]["used_up_count"] == 1, str(j["budget"]))
check("预算超支金额 300", j["budget"]["overrun_amount"] == "300.00", str(j["budget"]))
check("未设预算支出 0", j["budget"]["unbudgeted_amount"] == "0.00", str(j["budget"]))

check("储蓄目标存在", len(j["goals"]) == 1)
goal = j["goals"][0]
check("目标预计延期", goal["status"] == "delayed", str(goal))
check("目标延期天数 > 0", (goal["delay_days"] or 0) > 0, str(goal))
check("目标每月需存金额 > 0", Decimal(goal["required_monthly"]) > 0, str(goal))

check("订阅健康有数据", j["subscriptions"]["available"] is True)
check("订阅异常非空", len(j["subscriptions"]["issues"]) >= 1,
      str(j["subscriptions"]))
check("发现涨价+低频", any(i["kind"] == "price_up_low_usage"
                           for i in j["subscriptions"]["issues"]),
      str(j["subscriptions"]))
check("订阅健康分被扣分",
      j["subscriptions"]["score"] is not None and j["subscriptions"]["score"] < 100,
      str(j["subscriptions"]))

check("异常大额检测到医疗", any(a["category"] == "医疗" for a in j["anomalies"]),
      str(j["anomalies"]))

check("五个健康指标", len(j["indicators"]) == 5, str(j["indicators"]))
keys = {i["key"] for i in j["indicators"]}
check("指标键完整", keys == {"budget_execution", "savings_goal",
                              "subscription_health", "structure_stability",
                              "plan_execution"}, str(keys))
budget_ind = next(i for i in j["indicators"] if i["key"] == "budget_execution")
check("预算指标有公式", "扣" in budget_ind["formula"] and budget_ind["available"])
check("预算指标分数 72.0", budget_ind["score"] == 72.0, str(budget_ind))
plan_ind = next(i for i in j["indicators"] if i["key"] == "plan_execution")
check("计划执行分 66.7", plan_ind["score"] == 66.7, str(plan_ind))
check("总分在 0~100", 0 <= j["overall_score"] <= 100, str(j["overall_score"]))
check("总分等级非空", j["overall_level"] in ("优秀", "良好", "需关注", "需改善"),
      j["overall_level"])
check("覆盖率 1.0", j["coverage"] == 1.0, str(j["coverage"]))
check("摘要包含健康分", "消费健康分" in j["summary"], j["summary"])
check("建议非空", len(j["recommendations"]) >= 1, str(j["recommendations"]))
check("免责声明正确", "不是信用评分" in j["disclaimer"])
check("数据来源完整", "bills" in j["data_sources"]
      and "category_budgets" in j["data_sources"])

# ---------------- 用户隔离 ----------------
r = client.get("/api/consumption-health/report", headers=H_B, params={"month": current})
check("用户 B 报告返回 200", r.status_code == 200, r.text)
jb = r.json()
check("用户 B 收入为 0", jb["overview"]["income"] == "0.00", str(jb["overview"]))
check("用户 B 支出为 0", jb["overview"]["expense"] == "0.00", str(jb["overview"]))
check("用户 B 指标数据不足", all(i["available"] is False for i in jb["indicators"]),
      str(jb["indicators"]))
check("用户 B 总分 None", jb["overall_score"] is None)
check("用户 B 等级数据不足", jb["overall_level"] == "数据不足", jb["overall_level"])
check("用户 B 无目标", jb["goals"] == [])

# ---------------- 空月份 / 非法月份 ----------------
r = client.get("/api/consumption-health/report", headers=H_A,
               params={"month": "2020-01"})
check("空月份返回 200", r.status_code == 200, r.text)
jempty = r.json()
check("空月份支出 0", jempty["overview"]["expense"] == "0.00")
check("空月份总分 None", jempty["overall_score"] is None)
check("空月份摘要说明无账单", "还没有账单" in jempty["summary"], jempty["summary"])

r = client.get("/api/consumption-health/report", headers=H_A,
               params={"month": "2026-13"})
check("非法月份返回 400", r.status_code == 400, r.text)

r = client.get("/api/consumption-health/report")
check("未登录返回 401", r.status_code == 401, r.text)

print(f"\n全部通过：{PASSED} 项断言")
