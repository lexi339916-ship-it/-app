# -*- coding: utf-8 -*-
"""CSV 账单导入测试：通用/微信表头、GBK、去重、错误行、越权与用户隔离。

运行：python tests/csv_import_test.py
"""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./csv_import.db"
for f in Path(".").glob("csv_import.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import Bill, BillCategory  # noqa: E402

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


H_A, UID_A = register("csv_a")
H_B, UID_B = register("csv_b")

with SessionLocal() as db:
    food = cat_id(db, "餐饮")
    db.add(Bill(user_id=UID_A, category_id=food, type="expense",
                amount=Decimal("32.50"), bill_date=date(2026, 11, 1),
                remark="午饭", source="manual"))
    db.commit()

GENERIC = """日期,金额,类型,分类,备注,支付渠道,扣款账户
2026-11-01,32.50,支出,餐饮,午饭,微信支付,零钱
2026-11-02,21.00,支出,交通,打车,支付宝,余额
2026-11-03,800.00,收入,兼职,家教,银行卡,储蓄卡
2026-11-04,abc,支出,餐饮,错误金额,微信,
"""

# ---------------- 1. 通用 CSV 预览 ----------------
r = client.post("/api/imports/preview", headers=H_A, json={
    "text": GENERIC, "filename": "generic.csv"})
check("预览返回 200", r.status_code == 200, r.text)
j = r.json()
check("总行数 4", j["total_rows"] == 4, str(j))
check("有效行 3", j["valid_rows"] == 3, str(j))
check("重复行 1", j["duplicate_rows"] == 1, str(j))
check("错误行 1", j["error_rows"] == 1, str(j))
check("收入合计 800", j["income_total"] == "800.00", str(j))
check("支出合计 21", j["expense_total"] == "21.00", str(j))
check("表头映射日期", j["columns"].get("date") == "日期", str(j["columns"]))
check("表头映射金额", j["columns"].get("amount") == "金额", str(j["columns"]))
rows = {x["row_no"]: x for x in j["rows"]}
check("已有账单标记重复", rows[1]["duplicate"] is True
      and "已有" in rows[1]["duplicate_reason"], str(rows[1]))
check("重复行默认不勾选", rows[1]["include"] is False, str(rows[1]))
check("错误金额不猜", rows[4]["amount"] is None and rows[4]["errors"], str(rows[4]))
check("交通行可选", rows[2]["include"] is True, str(rows[2]))
check("收入行可选", rows[3]["include"] is True and rows[3]["type"] == "income",
      str(rows[3]))

# ---------------- 2. 确认导入 + 重复跳过 ----------------
selected = [{
    "row_no": x["row_no"], "bill_date": x["bill_date"], "amount": str(x["amount"]),
    "type": x["type"], "category": x["category"], "remark": x["remark"],
    "pay_channel": x["pay_channel"], "funding_account": x["funding_account"],
} for x in j["rows"] if x["include"]]
r = client.post("/api/imports/confirm", headers=H_A, json={
    "rows": selected, "filename": "generic.csv"})
check("确认导入 200", r.status_code == 200, r.text)
c = r.json()
check("导入 2 笔", c["imported_count"] == 2, str(c))
check("无失败", c["failed_count"] == 0, str(c))
check("收入合计 800", c["income_total"] == "800.00", str(c))
check("支出合计 21", c["expense_total"] == "21.00", str(c))
with SessionLocal() as db:
    csv_bills = db.scalars(select(Bill).where(
        Bill.user_id == UID_A, Bill.source == "csv")).all()
    check("数据库 source=csv 2 笔", len(csv_bills) == 2, str(len(csv_bills)))
    check("CSV 账单金额正确",
          sorted(str(b.amount) for b in csv_bills) == ["21.00", "800.00"],
          str([str(b.amount) for b in csv_bills]))
    check("CSV 账单分类正确",
          {b.category_id for b in csv_bills} == {cat_id(db, "交通"), cat_id(db, "兼职", "income")},
          str([b.category_id for b in csv_bills]))

r = client.post("/api/imports/confirm", headers=H_A, json={
    "rows": selected, "filename": "generic.csv"})
check("重复导入全部跳过", r.json()["imported_count"] == 0
      and r.json()["skipped_duplicates"] == 2, r.text)

# ---------------- 3. 微信表头 + 关闭交易跳过 ----------------
WECHAT = """交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态
2026-11-05 12:30:00,商户消费,美团,外卖,支出,¥35.00,零钱,支付成功
2026-11-06 09:00:00,转账,张三,红包,收入,200.00,零钱,已存入零钱
2026-11-07 10:00:00,商户消费,某店,退款,收入,15.00,零钱,已全额退款
2026-11-08 10:00:00,商户消费,某店,关闭订单,支出,50.00,零钱,交易关闭
"""
r = client.post("/api/imports/preview", headers=H_A, json={
    "text": WECHAT, "filename": "微信账单.csv"})
check("微信预览 200", r.status_code == 200, r.text)
w = r.json()
check("微信总行数 4", w["total_rows"] == 4, str(w))
check("微信错误行 1", w["error_rows"] == 1, str(w))
check("微信收入 215", w["income_total"] == "215.00", str(w))
check("微信支出 35", w["expense_total"] == "35.00", str(w))
wrows = {x["row_no"]: x for x in w["rows"]}
check("微信渠道识别", wrows[1]["pay_channel"] == "微信", str(wrows[1]))
check("微信扣款账户识别", wrows[1]["funding_account"] == "零钱", str(wrows[1]))
check("微信外卖归餐饮", wrows[1]["category"] == "餐饮", str(wrows[1]))
check("红包归红包", wrows[2]["category"] == "红包", str(wrows[2]))
check("关闭交易被跳过", wrows[4]["include"] is False and wrows[4]["errors"],
      str(wrows[4]))

# ---------------- 4. GBK 文件预览 ----------------
gbk_text = "日期,金额,类型,分类,备注\n2026-11-09,12.00,支出,餐饮,早餐\n"
r = client.post("/api/imports/preview-file", headers=H_A,
                files={"file": ("gbk.csv", gbk_text.encode("gb18030"), "text/csv")})
check("GBK 文件预览 200", r.status_code == 200, r.text)
g = r.json()
check("GBK 编码识别", g["encoding"] in ("gb18030", "gbk"), str(g["encoding"]))
check("GBK 金额正确", g["rows"][0]["amount"] == "12.00", str(g["rows"][0]))
check("GBK 分类正确", g["rows"][0]["category"] == "餐饮", str(g["rows"][0]))

# ---------------- 5. 非法输入 ----------------
r = client.post("/api/imports/preview", headers=H_A, json={"text": "金额,备注\n1,2"})
check("缺日期列 400", r.status_code == 400, r.text)
r = client.post("/api/imports/preview", headers=H_A, json={"text": ""})
check("空文本 422", r.status_code == 422, r.text)
r = client.post("/api/imports/preview-file", headers=H_A,
                files={"file": ("bad.csv", b"\xff\xfe\x00\x00bad", "text/csv")})
check("非法编码 400", r.status_code == 400, r.text)
r = client.post("/api/imports/preview", headers=H_A, json={"text": ""})
check("未登录/空文本不崩", r.status_code in (401, 422), r.text)
r = client.post("/api/imports/preview", json={"text": GENERIC})
check("未登录 401", r.status_code == 401, r.text)

# ---------------- 6. 用户隔离 ----------------
r = client.post("/api/imports/confirm", headers=H_B, json={
    "rows": selected, "filename": "generic.csv"})
check("用户 B 导入成功", r.status_code == 200 and r.json()["imported_count"] == 2,
      r.text)
with SessionLocal() as db:
    check("用户 B 只有自己的 CSV 账单",
          len(db.scalars(select(Bill).where(
              Bill.user_id == UID_B, Bill.source == "csv")).all()) == 2)
    check("用户 A 的 CSV 账单未被重复写入",
          len(db.scalars(select(Bill).where(
              Bill.user_id == UID_A, Bill.source == "csv")).all()) == 2)


from datetime import datetime as _dt  # noqa: E402

_report = Path(__file__).resolve().parent / "agent_eval" / "csv_import_report.md"
_report.parent.mkdir(parents=True, exist_ok=True)
_lines = [
    "# CSV 账单导入测试报告（团队自测）",
    "",
    f"- 生成时间：{_dt.now().isoformat(timespec='seconds')}",
    f"- 断言：{PASSED}，通过：{PASSED}，失败：0",
    "- 覆盖：通用/微信表头、UTF-8/GBK、重复检测、错误行、确认导入、越权与用户隔离。",
    "",
]
_report.write_text(chr(10).join(_lines), encoding="utf-8")

print(f"\n全部通过：{PASSED} 项断言")
