# -*- coding: utf-8 -*-
"""账单分类筛选测试：分类、类型组合、分页与用户隔离。"""
import os
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./bills_filter_test.db"
for f in Path(".").glob("bills_filter_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import BillCategory  # noqa: E402

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


def cat_id(name: str, type_: str = "expense") -> int:
    with SessionLocal() as db:
        return db.scalar(select(BillCategory.id).where(
            BillCategory.name == name, BillCategory.type == type_,
            BillCategory.user_id.is_(None)))


H_A = register("filter_a")
H_B = register("filter_b")
food = cat_id("餐饮")
traffic = cat_id("交通")
parttime = cat_id("兼职", "income")

for header, rows in (
    (H_A, [("餐饮", "32.50", "expense"), ("交通", "21.00", "expense"),
           ("兼职", "800.00", "income")]),
    (H_B, [("餐饮", "50.00", "expense")]),
):
    for name, amount, type_ in rows:
        r = client.post("/api/bills", headers=header, json={
            "type": type_, "amount": amount, "category": name,
            "bill_date": date.today().isoformat(), "remark": f"{name} 测试"})
        check(f"创建 {name} 账单", r.status_code == 200, r.text)

r = client.get("/api/bills", headers=H_A, params={"category_id": food})
check("按餐饮分类筛选 200", r.status_code == 200, r.text)
check("餐饮只返回 1 笔", r.json()["total"] == 1, r.text)
check("餐饮金额正确", r.json()["items"][0]["amount"] == "32.50", r.text)

r = client.get("/api/bills", headers=H_A, params={"category_id": traffic})
check("按交通分类筛选", r.json()["total"] == 1
      and r.json()["items"][0]["category"] == "交通", r.text)

r = client.get("/api/bills", headers=H_A, params={
    "category_id": food, "type": "income"})
check("分类+类型组合无结果", r.json()["total"] == 0, r.text)

r = client.get("/api/bills", headers=H_A, params={"category_id": parttime})
check("收入分类筛选", r.json()["total"] == 1
      and r.json()["items"][0]["type"] == "income", r.text)

r = client.get("/api/bills", headers=H_B, params={"category_id": food})
check("用户隔离：B 只看到自己的餐饮", r.json()["total"] == 1
      and r.json()["items"][0]["amount"] == "50.00", r.text)

r = client.get("/api/bills", headers=H_A, params={"category_id": 999999})
check("不存在的分类返回空列表", r.json()["total"] == 0, r.text)

month = date.today().strftime("%Y-%m")
r = client.get("/api/statistics/monthly", headers=H_A,
               params={"month": month, "category_id": food})
check("月度统计按餐饮筛选", r.status_code == 200 and r.json()["count"] == 1
      and r.json()["expense"] == "32.50", r.text)
r = client.get("/api/statistics/monthly", headers=H_A, params={"month": month})
check("月度统计未筛选包含全部", r.json()["count"] == 3
      and r.json()["income"] == "800.00" and r.json()["expense"] == "53.50", r.text)
r = client.get("/api/statistics/monthly", headers=H_B,
               params={"month": month, "category_id": food})
check("月度统计用户隔离", r.json()["count"] == 1
      and r.json()["expense"] == "50.00", r.text)

print(f"\n全部通过：{PASSED} 项断言")
