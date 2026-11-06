# -*- coding: utf-8 -*-
"""个人资产账本测试：账户/负债/流水/转账/账单联动/用户隔离/Decimal 精度。"""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./assets_test.db"
for f in Path(".").glob("assets_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

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


def dec(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def register(username: str) -> dict:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def cat_id(name: str, type_: str = "expense") -> int:
    with SessionLocal() as db:
        return db.query(BillCategory).filter_by(
            name=name, type=type_, user_id=None).first().id


H_A = register("asset_a")
H_B = register("asset_b")

# ---------- 账户与总览 ----------
r = client.post("/api/assets/accounts", headers=H_A, json={
    "name": "现金钱包", "type": "cash", "balance": "1000.00", "note": "日常现金"})
check("新增现金账户", r.status_code == 200 and dec(r.json()["balance"]) == dec("1000.00"), r.text)
cash_id = r.json()["id"]

r = client.post("/api/assets/accounts", headers=H_A, json={
    "name": "微信零钱", "type": "wechat", "institution": "微信",
    "account_hint": "123456789", "balance": "500.00"})
check("新增微信账户且只保留尾号", r.status_code == 200
      and r.json()["account_hint"] == "6789", r.text)
wechat_id = r.json()["id"]

r = client.get("/api/assets/overview", headers=H_A)
body = r.json()
check("总资产正确", dec(body["total_assets"]) == dec("1500.00"), r.text)
check("净资产正确", dec(body["net_worth"]) == dec("1500.00"), r.text)
check("账户数量正确", body["account_count"] == 2, r.text)
check("已维护资产标记", body["has_data"] is True, r.text)

r = client.get("/api/assets/transactions", headers=H_A)
check("初始余额流水 2 条", r.json()["total"] == 2, r.text)
check("初始流水类型 opening",
      all(i["type"] == "opening" for i in r.json()["items"]), r.text)

# ---------- 转账不生成消费 ----------
r = client.post("/api/assets/transfers", headers=H_A, json={
    "from_account_id": cash_id, "to_account_id": wechat_id,
    "amount": "200.00", "note": "转到微信"})
check("账户转账成功", r.status_code == 200, r.text)
check("转出流水", dec(r.json()["from_account"]["balance"]) == dec("800.00"), r.text)
check("转入流水", dec(r.json()["to_account"]["balance"]) == dec("700.00"), r.text)
check("转账两条流水同一组", len(r.json()["transactions"]) == 2
      and r.json()["transactions"][0]["transfer_group_id"]
      == r.json()["transactions"][1]["transfer_group_id"], r.text)

r = client.get("/api/bills", headers=H_A)
check("转账不生成账单", r.json()["total"] == 0, r.text)
month = date.today().strftime("%Y-%m")
r = client.get("/api/statistics/monthly", headers=H_A, params={"month": month})
check("转账不进入月度支出", dec(r.json()["expense"]) == dec("0.00"), r.text)

r = client.post("/api/assets/transfers", headers=H_A, json={
    "from_account_id": cash_id, "to_account_id": cash_id, "amount": "10.00"})
check("同账户转账被拒绝", r.status_code == 400, r.text)
r = client.post("/api/assets/transfers", headers=H_A, json={
    "from_account_id": cash_id, "to_account_id": wechat_id, "amount": "99999.00"})
check("转账超过余额被拒绝", r.status_code == 409, r.text)

# ---------- 余额调整 ----------
r = client.post(f"/api/assets/accounts/{cash_id}/adjust", headers=H_A, json={
    "kind": "increase", "amount": "100.00", "note": "报销"})
check("手动增加余额", dec(r.json()["balance"]) == dec("900.00"), r.text)
r = client.post(f"/api/assets/accounts/{cash_id}/adjust", headers=H_A, json={
    "kind": "decrease", "amount": "50.00"})
check("手动减少余额", dec(r.json()["balance"]) == dec("850.00"), r.text)
r = client.post(f"/api/assets/accounts/{cash_id}/adjust", headers=H_A, json={
    "kind": "adjust", "target_balance": "900.00", "note": "对账"})
check("余额调整到目标值", dec(r.json()["balance"]) == dec("900.00"), r.text)
check("余额调整前后流水", client.get("/api/assets/transactions", headers=H_A)
      .json()["items"][0]["type"] == "adjustment", "missing adjustment")

# ---------- 负债与还款 ----------
r = client.post("/api/assets/liabilities", headers=H_A, json={
    "name": "招行信用卡", "type": "credit_card", "outstanding": "300.00",
    "due_date": (date.today().replace(day=28)).isoformat(), "remark": "本月账单"})
check("新增负债", r.status_code == 200 and dec(r.json()["outstanding"]) == dec("300.00"), r.text)
liability_id = r.json()["id"]

r = client.get("/api/assets/overview", headers=H_A)
body = r.json()
check("总负债正确", dec(body["total_liabilities"]) == dec("300.00"), r.text)
check("净资产=资产-负债", dec(body["net_worth"]) == dec("1300.00"), r.text)

r = client.post(f"/api/assets/liabilities/{liability_id}/repay", headers=H_A, json={
    "amount": "100.00", "account_id": cash_id, "note": "还款"})
check("负债还款成功", dec(r.json()["outstanding"]) == dec("200.00"), r.text)
r = client.get("/api/assets/overview", headers=H_A)
body = r.json()
check("还款后资产减少", dec(body["total_assets"]) == dec("1500.00"), r.text)
check("还款后净资产不变", dec(body["net_worth"]) == dec("1300.00"), r.text)

# ---------- 用户隔离 ----------
r = client.get("/api/assets/overview", headers=H_B)
check("B 的资产为空", r.status_code == 200 and r.json()["has_data"] is False, r.text)
r = client.put(f"/api/assets/accounts/{cash_id}", headers=H_B, json={
    "name": "篡改", "type": "cash"})
check("B 不能编辑 A 的账户", r.status_code == 404, r.text)
r = client.post(f"/api/assets/accounts/{cash_id}/adjust", headers=H_B, json={
    "kind": "increase", "amount": "1.00"})
check("B 不能调整 A 的余额", r.status_code == 404, r.text)
r = client.delete(f"/api/assets/liabilities/{liability_id}", headers=H_B)
check("B 不能删除 A 的负债", r.status_code == 404, r.text)
r = client.post("/api/bills", headers=H_B, json={
    "type": "expense", "amount": "1.00", "category": "餐饮",
    "bill_date": date.today().isoformat(), "account_id": cash_id})
check("B 不能关联 A 的账户", r.status_code == 400, r.text)

# Decimal 精度：0.01 元级别不丢失
r = client.post("/api/assets/accounts", headers=H_B, json={
    "name": "零钱", "type": "cash", "balance": "0.01"})
check("B 创建 0.01 账户", r.status_code == 200 and dec(r.json()["balance"]) == dec("0.01"), r.text)
b_account = r.json()["id"]
r = client.post(f"/api/assets/accounts/{b_account}/adjust", headers=H_B, json={
    "kind": "increase", "amount": "0.02"})
check("0.01 精度累加", dec(r.json()["balance"]) == dec("0.03"), r.text)

# ---------- 账单联动 ----------
food = cat_id("餐饮")
r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "50.00", "category": "餐饮",
    "bill_date": date.today().isoformat(), "remark": "午饭",
    "account_id": cash_id})
check("新增关联账单", r.status_code == 200 and r.json()["account_id"] == cash_id, r.text)
bill_id = r.json()["id"]
r = client.get("/api/assets/overview", headers=H_A)
check("支出扣减资产", dec(r.json()["total_assets"]) == dec("1450.00"), r.text)

r = client.put(f"/api/bills/{bill_id}", headers=H_A, json={
    "type": "expense", "amount": "70.00", "category": "餐饮",
    "bill_date": date.today().isoformat(), "remark": "午饭改金额",
    "account_id": cash_id})
check("编辑账单金额", r.status_code == 200 and dec(r.json()["amount"]) == dec("70.00"), r.text)
r = client.get("/api/assets/overview", headers=H_A)
check("编辑后按差额扣减", dec(r.json()["total_assets"]) == dec("1430.00"), r.text)

r = client.delete(f"/api/bills/{bill_id}", headers=H_A)
check("删除账单成功", r.status_code == 200, r.text)
r = client.get("/api/assets/overview", headers=H_A)
check("删除账单冲正余额", dec(r.json()["total_assets"]) == dec("1500.00"), r.text)

# 旧账单补关联：只建立关系，不追溯调整余额
r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "30.00", "category": "餐饮",
    "bill_date": date.today().isoformat(), "remark": "旧账单"})
old_bill_id = r.json()["id"]
before_assets = dec(client.get("/api/assets/overview", headers=H_A).json()["total_assets"])
r = client.put(f"/api/bills/{old_bill_id}", headers=H_A, json={
    "type": "expense", "amount": "30.00", "category": "餐饮",
    "bill_date": date.today().isoformat(), "remark": "旧账单",
    "account_id": wechat_id})
check("旧账单补关联保存成功", r.status_code == 200 and r.json()["account_id"] == wechat_id, r.text)
after_assets = dec(client.get("/api/assets/overview", headers=H_A).json()["total_assets"])
check("旧账单补关联不追溯扣款", after_assets == before_assets,
      f"{before_assets} -> {after_assets}")
client.delete(f"/api/bills/{old_bill_id}", headers=H_A)

# ---------- 净资产变化拆解 ----------
r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "25.00", "category": "餐饮",
    "bill_date": date.today().isoformat(), "remark": "关联消费",
    "account_id": cash_id})
check("创建分析用账单", r.status_code == 200, r.text)
r = client.get("/api/assets/change-analysis", headers=H_A, params={"month": month})
body = r.json()
check("净资产变化分析可用", r.status_code == 200 and body["has_data"] is True, r.text)
check("消费影响为负", dec(body["components"]["consumption"]) <= dec("-25.00"), r.text)
check("关联支出覆盖", dec(body["linked_expense"]) >= dec("25.00"), r.text)
check("转账净影响为 0", dec(body["components"]["transfer"]) == dec("0.00"), r.text)

# ---------- 删除/归档 ----------
r = client.delete(f"/api/assets/accounts/{cash_id}", headers=H_A)
check("有流水账户归档", r.status_code == 200 and r.json()["archived"] is True, r.text)
r = client.get("/api/assets/overview", headers=H_A)
check("归档账户不出现在总览", all(a["id"] != cash_id for a in r.json()["accounts"]), r.text)
r = client.get("/api/assets/transactions", headers=H_A)
check("归档后流水仍保留", any(t["account_id"] == cash_id for t in r.json()["items"]), r.text)

r = client.delete(f"/api/assets/liabilities/{liability_id}", headers=H_A)
check("有还款负债归档", r.status_code == 200 and r.json()["archived"] is True, r.text)

print(f"\n全部通过：{PASSED} 项断言")
