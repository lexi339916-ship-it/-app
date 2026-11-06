# -*- coding: utf-8 -*-
"""预算一致性与账单来源测试：分类预算投影、旧预算兼容、同步清理、source 白名单。"""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./budget_consistency_test.db"
for f in Path(".").glob("budget_consistency_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import Bill, BillCategory, Budget, CategoryBudget, User  # noqa: E402
from app.routers.budget_center import _sync_month_budget  # noqa: E402

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


H_A, UID_A = register("budget_a")
with SessionLocal() as db:
    food = db.scalar(select(BillCategory.id).where(
        BillCategory.name == "餐饮", BillCategory.type == "expense",
        BillCategory.user_id.is_(None)))
    transit = db.scalar(select(BillCategory.id).where(
        BillCategory.name == "交通", BillCategory.type == "expense",
        BillCategory.user_id.is_(None)))
    db.add(Bill(user_id=UID_A, category_id=food, type="expense",
                amount=Decimal("80"), bill_date=date.today(), remark="午饭"))
    db.add(Bill(user_id=UID_A, category_id=transit, type="expense",
                amount=Decimal("20"), bill_date=date.today(), remark="地铁"))
    db.commit()

# 没有分类预算时，旧整月预算接口保持兼容
r = client.put("/api/budgets", headers=H_A, json={"month": MONTH, "amount": "2000"})
check("旧预算可以单独设置", r.status_code == 200 and r.json()["amount"] == "2000.00",
      r.text)
r = client.get("/api/budgets", headers=H_A, params={"month": MONTH})
check("旧预算已花=全部支出", r.json()["spent"] == "100.00", r.text)

# 新增分类预算后，整月预算变成只读投影
r = client.put("/api/budget-center/category", headers=H_A, json={
    "category_id": food, "month": MONTH, "amount": "500"})
check("设置分类预算", r.status_code == 200, r.text)
r = client.get("/api/budgets", headers=H_A, params={"month": MONTH})
j = r.json()
check("整月预算投影为分类合计", j["amount"] == "500.00", str(j))
check("整月已花只算预算内分类", j["spent"] == "80.00", str(j))
r = client.put("/api/budgets", headers=H_A, json={"month": MONTH, "amount": "3000"})
check("已有分类预算时旧接口 409", r.status_code == 409, r.text)

# 分类预算全部删除后，旧 Budget 缓存应被清理
with SessionLocal() as db:
    rows = db.scalars(select(CategoryBudget).where(
        CategoryBudget.user_id == UID_A, CategoryBudget.month == MONTH)).all()
    for row in rows:
        db.delete(row)
    db.commit()
    _sync_month_budget(db, db.get(User, UID_A), MONTH)
    old = db.scalar(select(Budget).where(
        Budget.user_id == UID_A, Budget.month == MONTH))
    check("分类预算清空后旧总预算删除", old is None, str(old))

# 账单来源白名单扩展，编辑不再丢来源
for source in ("agent", "csv", "subscription"):
    r = client.post("/api/bills", headers=H_A, json={
        "type": "expense", "amount": "10", "category": "餐饮",
        "bill_date": date.today().isoformat(), "remark": f"来源 {source}",
        "source": source})
    check(f"创建 source={source} 账单", r.status_code == 200
          and r.json()["source"] == source, r.text)
    bill_id = r.json()["id"]
    r = client.put(f"/api/bills/{bill_id}", headers=H_A, json={
        "type": "expense", "amount": "11", "category": "餐饮",
        "bill_date": date.today().isoformat(), "remark": f"来源 {source}",
        "source": source})
    check(f"编辑保留 source={source}", r.status_code == 200
          and r.json()["source"] == source, r.text)

print(f"\n全部通过：{PASSED} 项断言")
