# -*- coding: utf-8 -*-
"""订阅自动记账与预算联动测试。运行：python tests/subscription_sync_test.py"""
import os
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./subscription_sync.db"
for f in Path(".").glob("subscription_sync.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import Bill, Subscription, SubscriptionBilling  # noqa: E402

Base.metadata.create_all(bind=engine)
seed_default_categories()
client = TestClient(app)
PASSED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if not cond:
        raise SystemExit(f"测试失败：{name} {detail}")
    PASSED += 1


def shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7]) + delta
    while mon < 1:
        year, mon = year - 1, mon + 12
    while mon > 12:
        year, mon = year + 1, mon - 12
    return f"{year:04d}-{mon:02d}"


def main() -> None:
    res = client.post("/api/auth/register", json={
        "username": "sub_tester", "password": "sub123456", "nickname": "订阅测试"})
    check("注册", res.status_code == 200, res.text)
    token = res.json()["access_token"]
    user_id = res.json()["user"]["id"]
    h = {"Authorization": f"Bearer {token}"}
    today = date.today()
    current = today.strftime("%Y-%m")

    cats = client.get("/api/categories?type=expense", headers=h).json()["items"]
    cat_id = cats[0]["id"]

    res = client.post("/api/subscriptions", json={
        "name": "测试订阅", "day_of_month": 1, "amount": "30.00",
        "category_id": cat_id, "usage_90d": 5,
        "remark": "", "remind_enabled": False}, headers=h)
    check("创建订阅", res.status_code == 200, res.text)
    sub_id = res.json()["id"]

    # 模拟“两个月没打开 App”：上次记账是两个月前
    db = SessionLocal()
    try:
        sub = db.get(Subscription, sub_id)
        sub.last_billed_month = shift_month(current, -2)
        db.commit()
    finally:
        db.close()

    res = client.post("/api/subscriptions/sync", headers=h)
    check("跨月 sync 返回 200", res.status_code == 200, res.text)
    body = res.json()
    check("跨月补单生成 2 笔", body["created_count"] == 2, str(body))
    check("补单金额正确", str(body["created_amount"]) == "60.00", str(body))

    res = client.post("/api/subscriptions/sync", headers=h)
    check("重复 sync 不重复记账", res.json()["created_count"] == 0, res.text)

    db = SessionLocal()
    try:
        bills = db.query(Bill).filter(Bill.user_id == user_id,
                                      Bill.source == "subscription").count()
        billings = db.query(SubscriptionBilling).filter(
            SubscriptionBilling.user_id == user_id).count()
        sub = db.get(Subscription, sub_id)
        check("订阅账单 2 笔", bills == 2, str(bills))
        check("计费记录 2 条", billings == 2, str(billings))
        check("last_billed_month 到当前月", sub.last_billed_month == current,
              str(sub.last_billed_month))
    finally:
        db.close()

    # 改价时保留旧价格
    res = client.put(f"/api/subscriptions/{sub_id}", json={
        "name": "测试订阅", "day_of_month": 1, "amount": "35.00",
        "category_id": cat_id, "usage_90d": 5,
        "remark": "", "remind_enabled": False}, headers=h)
    check("修改订阅价格", res.status_code == 200, res.text)
    check("旧价格已保留", str(res.json()["previous_amount"]) == "30.00", res.text)

    # 分类预算变更后整月预算同步
    res = client.put("/api/budget-center/category", json={
        "category_id": cat_id, "month": current, "amount": "500.00"}, headers=h)
    check("设置分类预算", res.status_code == 200, res.text)
    res = client.get(f"/api/budgets?month={current}", headers=h)
    check("整月预算同步为 500", str(res.json()["amount"]) == "500.00", res.text)

    print(f"\n全部通过：{PASSED} 项断言")


if __name__ == "__main__":
    main()
