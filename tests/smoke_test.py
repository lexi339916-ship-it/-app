# -*- coding: utf-8 -*-
"""后端接口冒烟测试：不依赖 MySQL 与真实模型密钥。

- 数据库：SQLite（通过环境变量注入）
- AI：monkeypatch 模型调用，验证草稿校验/脱敏/限流/降级全链路
运行：python tests/smoke_test.py
"""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = "sqlite:///./smoke_test.db"
os.environ["AI_DAILY_LIMIT"] = "4"  # 前面 4 次 mock 调用成功后，第 5 次触发限流

for f in Path(".").glob("smoke_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.services import ai_service  # noqa: E402

# TestClient 不触发 lifespan，手动执行启动初始化（建表 + 种子分类）
Base.metadata.create_all(bind=engine)
seed_default_categories()

client = TestClient(app)
PASSED = 0
FUTURE_DUE = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d 09:00:00")


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASSED += 1
    else:
        raise SystemExit(f"测试失败：{name} {detail}")


# ---------- 1. 健康检查 ----------
r = client.get("/api/health")
check("健康检查", r.status_code == 200 and r.json()["ok"])

# ---------- 2. 认证 ----------
r = client.post("/api/auth/register", json={
    "username": "student_a", "password": "abc123", "nickname": "同学A"})
check("注册", r.status_code == 200, r.text)
token_a = r.json()["access_token"]
H_A = {"Authorization": f"Bearer {token_a}"}

r = client.post("/api/auth/register", json={
    "username": "student_a", "password": "abc123"})
check("重复注册被拒绝(400)", r.status_code == 400, r.text)

r = client.post("/api/auth/register", json={
    "username": "student_b", "password": "abc123"})
check("注册用户B", r.status_code == 200, r.text)
token_b = r.json()["access_token"]
H_B = {"Authorization": f"Bearer {token_b}"}

r = client.post("/api/auth/login", json={"username": "student_a", "password": "wrong!"})
check("错误密码登录被拒绝(400)", r.status_code == 400, r.text)

# 登录失败限流：同一用户名+IP 连续失败达到阈值后返回 429
for _ in range(config.LOGIN_MAX_ATTEMPTS):
    r = client.post("/api/auth/login", json={
        "username": "rate_limit_probe", "password": "wrong!"})
check("阈值内仍返回 400", r.status_code == 400, r.text)
r = client.post("/api/auth/login", json={
    "username": "rate_limit_probe", "password": "wrong!"})
check("超过阈值返回 429", r.status_code == 429, r.text)
check("限流提示可读", "登录失败次数过多" in r.json().get("message", ""), r.text)

r = client.get("/api/bills")
check("未登录访问账单(401)", r.status_code == 401, r.text)

r = client.get("/api/auth/me", headers=H_A)
check("获取当前用户", r.status_code == 200 and r.json()["username"] == "student_a")

# ---------- 3. 分类 ----------
r = client.get("/api/categories", headers=H_A)
cats = r.json()["items"]
check("系统预置分类(15条)", r.status_code == 200 and len(cats) == 15, r.text)

r = client.post("/api/categories", headers=H_A, json={"name": "宠物", "type": "expense"})
check("创建自定义分类", r.status_code == 200, r.text)

r = client.post("/api/categories", headers=H_A, json={"name": "宠物", "type": "expense"})
check("重复分类被拒绝(400)", r.status_code == 400)

# ---------- 4. 账单 CRUD 与筛选 ----------
bill = {"type": "expense", "amount": "32.50", "category": "餐饮",
        "bill_date": "2026-10-18", "remark": "午饭", "source": "manual"}
r = client.post("/api/bills", headers=H_A, json=bill)
check("创建支出账单", r.status_code == 200 and r.json()["amount"] == "32.50", r.text)
bill_id = r.json()["id"]

r = client.post("/api/bills", headers=H_A, json={
    "type": "income", "amount": "800", "category": "兼职",
    "bill_date": "2026-10-10", "remark": "家教", "source": "manual"})
check("创建收入账单", r.status_code == 200, r.text)

r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "10", "category": "不存在的分类",
    "bill_date": "2026-10-18", "remark": ""})
check("非法分类被拒绝(400)", r.status_code == 400)

r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "-5", "category": "餐饮",
    "bill_date": "2026-10-18", "remark": ""})
check("负数金额被拒绝(422)", r.status_code == 422)

r = client.get("/api/bills", headers=H_A, params={"month": "2026-10"})
j = r.json()
check("按月查询账单(2条)", r.status_code == 200 and j["total"] == 2, r.text)

r = client.get("/api/bills", headers=H_A, params={"type": "income"})
check("按类型筛选(1条)", r.json()["total"] == 1)

r = client.get("/api/bills", headers=H_B)
check("用户B看不到A的账单(0条)", r.json()["total"] == 0)

r = client.get(f"/api/bills/{bill_id}", headers=H_B)
check("跨用户访问账单(404)", r.status_code == 404)

r = client.put(f"/api/bills/{bill_id}", headers=H_A, json={
    "type": "expense", "amount": "35", "category": "餐饮",
    "bill_date": "2026-10-18", "remark": "午饭加饮料"})
check("修改账单", r.status_code == 200 and r.json()["amount"] == "35.00", r.text)

# ---------- 5. 便签与待办 ----------
r = client.post("/api/notes", headers=H_A, json={
    "title": "周五交房租", "content": "记得转账2500", "note_type": "todo",
    "status": "open", "due_at": "2026-10-23 18:00:00"})
check("创建待办", r.status_code == 200, r.text)
note_id = r.json()["id"]

r = client.post("/api/notes", headers=H_A, json={
    "title": "购物清单", "content": "牛奶 鸡蛋 纸巾", "note_type": "note"})
check("创建普通便签", r.status_code == 200)

r = client.get("/api/notes", headers=H_A, params={"q": "房租"})
check("便签搜索", r.json()["total"] == 1)

r = client.get("/api/notes", headers=H_A)
check("待办统计 pending_count=1", r.json()["pending_count"] == 1, r.text)

r = client.put(f"/api/notes/{note_id}", headers=H_A, json={
    "title": "周五交房租", "content": "记得转账2500", "note_type": "todo",
    "status": "done", "due_at": "2026-10-23 18:00:00"})
check("待办标记完成", r.status_code == 200 and r.json()["status"] == "done")

r = client.delete(f"/api/notes/{note_id}", headers=H_B)
check("跨用户删除便签(404)", r.status_code == 404)

# ---------- 5b. 任务管理扩展：优先级 / 置顶 / 逾期 / 视图 ----------
r = client.post("/api/notes", headers=H_A, json={
    "title": "交课程设计报告", "content": "", "note_type": "todo",
    "status": "open", "due_at": "2026-10-01 09:00:00",
    "priority": "high", "pinned": True})
check("创建高优先级置顶任务",
      r.status_code == 200 and r.json()["priority"] == "high" and r.json()["pinned"] is True,
      r.text)
task_id = r.json()["id"]
check("逾期任务 is_overdue=True", r.json()["is_overdue"] is True, r.text)

r = client.get("/api/notes", headers=H_A)
check("置顶任务排在首位", r.json()["items"][0]["id"] == task_id, r.text[:200])

r = client.get("/api/notes", headers=H_A, params={"view": "today"})
check("今天视图包含逾期任务", any(x["id"] == task_id for x in r.json()["items"]), r.text)

r = client.post("/api/notes", headers=H_A, json={
    "title": "下周计划", "content": "", "note_type": "todo",
    "status": "open", "due_at": FUTURE_DUE, "priority": "low"})
future_id = r.json()["id"]
r = client.get("/api/notes", headers=H_A, params={"view": "upcoming"})
check("近期视图包含未来任务", any(x["id"] == future_id for x in r.json()["items"]))
check("近期视图不含今天/逾期任务", all(x["id"] != task_id for x in r.json()["items"]))

r = client.put(f"/api/notes/{future_id}", headers=H_A, json={
    "title": "下周计划", "content": "", "note_type": "todo",
    "status": "done", "due_at": FUTURE_DUE, "priority": "low"})
check("完成未来任务", r.status_code == 200 and r.json()["status"] == "done", r.text)
r = client.get("/api/notes", headers=H_A, params={"view": "done"})
check("已完成视图包含该任务", any(x["id"] == future_id for x in r.json()["items"]))

# ---------- 6. 预算 ----------
r = client.put("/api/budgets", headers=H_A, json={"month": "2026-10", "amount": "2000"})
j = r.json()
check("设置月度预算", r.status_code == 200 and j["amount"] == "2000.00", r.text)
check("预算已用=当月支出35", j["spent"] == "35.00", r.text)

# ---------- 7. 统计 ----------
r = client.get("/api/statistics/monthly", headers=H_A, params={"month": "2026-10"})
j = r.json()
check("月度统计 收入800 支出35",
      j["income"] == "800.00" and j["expense"] == "35.00" and j["count"] == 2, r.text)
check("月度按日明细31天", len(j["days"]) == 31)

r = client.get("/api/statistics/categories", headers=H_A,
               params={"month": "2026-10", "type": "expense"})
j = r.json()
check("分类统计 餐饮35占100%", j["total"] == "35.00" and j["items"][0]["ratio"] == 1.0, r.text)

# ---------- 7b. 支付渠道 ----------
r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "15", "category": "购物",
    "bill_date": "2026-10-19", "remark": "渠道测试",
    "pay_channel": "微信支付", "funding_account": "零钱", "source": "receipt"})
check("创建带渠道账单",
      r.status_code == 200 and r.json()["pay_channel"] == "微信支付"
      and r.json()["funding_account"] == "零钱", r.text)
channel_bill_id = r.json()["id"]
r = client.get(f"/api/bills/{channel_bill_id}", headers=H_A)
check("账单详情返回渠道", r.json()["pay_channel"] == "微信支付", r.text)
r = client.put(f"/api/bills/{channel_bill_id}", headers=H_A, json={
    "type": "expense", "amount": "15", "category": "购物",
    "bill_date": "2026-10-19", "remark": "渠道测试",
    "pay_channel": "支付宝", "funding_account": "", "source": "receipt"})
check("修改账单渠道", r.json()["pay_channel"] == "支付宝", r.text)
r = client.get("/api/statistics/channels", headers=H_A, params={"month": "2026-10"})
j = r.json()
check("渠道统计包含支付宝", any(i["channel"] == "支付宝" for i in j["items"]), r.text)
check("渠道统计占比合计约为1",
      abs(sum(i["ratio"] for i in j["items"]) - 1.0) < 0.01, r.text)
r = client.get("/api/statistics/channels", headers=H_A)
j = r.json()
check("渠道统计全部时间包含未记录", any(i["channel"] == "未记录" for i in j["items"]), r.text)

# ---------- 8. AI：未配置密钥 → 503 降级 ----------
# 显式清空 AI 配置（.env 中可能已有真实密钥，不影响本断言）
config.AI_BASE_URL = config.AI_API_KEY = config.AI_MODEL = ""
r = client.post("/api/ai/parse-bill", headers=H_A, json={"text": "午饭花了32元"})
check("AI未配置返回503", r.status_code == 503, r.text)

# ---------- 9. AI：mock 模型输出，验证草稿管线 ----------
config.AI_BASE_URL = "https://mock.local/v1"
config.AI_API_KEY = "mock-key"
config.AI_MODEL = "mock-model"

async def fake_chat(messages, temperature=0.0, model=None):
    user_text = messages[-1]["content"]
    if "多笔" in user_text or "，" in user_text and "块" in user_text:
        return ('```json\n{"bills": ['
                '{"type":"expense","amount":32,"category":"餐饮","bill_date":"2026-10-19","remark":"午饭","missing_fields":[]},'
                '{"type":"expense","amount":12,"category":"交通","bill_date":"2026-10-19","remark":"打车","missing_fields":[]}'
                '], "notice":""}\n```')
    if "三十多元" in user_text:
        return '{"bills":[{"type":"expense","amount":null,"category":"餐饮","bill_date":"2026-10-19","remark":"午饭","missing_fields":["amount"]}],"notice":"金额不明确"}'
    if "银行卡密码" in user_text:
        return '{"bills":[{"type":"expense","amount":12,"category":"购物","bill_date":"2026-10-19","remark":"买水，银行卡密码是123456","missing_fields":[]}],"notice":""}'
    return '{"bills":[{"type":"expense","amount":32,"category":"餐饮","bill_date":"2026-10-19","remark":"午饭","missing_fields":[]}],"notice":""}'


ai_service.chat = fake_chat

r = client.post("/api/ai/parse-bill", headers=H_A, json={"text": "午饭花了32元"})
j = r.json()
check("AI解析单笔账单", r.status_code == 200 and j["drafts"][0]["amount"] == "32.00", r.text)

r = client.post("/api/ai/parse-bill", headers=H_A, json={"text": "超市买菜73元，打车回家21块"})
j = r.json()
check("AI拆分多笔账单(2条)", len(j["drafts"]) == 2, r.text)

r = client.post("/api/ai/parse-bill", headers=H_A, json={"text": "花了三十多元买午饭"})
j = r.json()
d = j["drafts"][0]
check("模糊金额不猜测(null+missing)", d["amount"] is None and "amount" in d["missing_fields"], r.text)

r = client.post("/api/ai/parse-bill", headers=H_A, json={"text": "买水，银行卡密码是123456"})
d = r.json()["drafts"][0]
check("备注敏感数字脱敏", "123456" not in d["remark"] and "****" in d["remark"], r.text)

# ---------- 10. AI 限流（AI_DAILY_LIMIT=4，前面已成功 4 次） ----------
r = client.post("/api/ai/parse-bill", headers=H_A, json={"text": "午饭花了32元"})
check("超过每日上限返回429", r.status_code == 429, r.text)

# 后续用例放开限额
config.AI_DAILY_LIMIT = 50

# ---------- 11. AI 便签解析（多任务提取） ----------
async def fake_note_chat(messages, temperature=0.0, model=None):
    return ('{"items":['
            '{"title":"交课程设计报告","content":"","note_type":"todo","due_at":"2026-10-23 18:00","priority":"high","missing_fields":[]},'
            '{"title":"去超市买生活用品","content":"","note_type":"todo","due_at":"2026-10-20 15:00","priority":"medium","missing_fields":[]}'
            '],"notice":""}')

ai_service.chat = fake_note_chat
r = client.post("/api/ai/parse-note", headers=H_B, json={"text": "周五之前交课程设计报告，明天下午去超市买生活用品"})
j = r.json()
check("AI拆分多条任务(2条)", r.status_code == 200 and len(j["drafts"]) == 2, r.text)
check("AI推断高优先级", j["drafts"][0]["priority"] == "high", r.text)

# ---------- 12. AI 月度总结（无数据用户B → 不调用模型） ----------
r = client.get("/api/ai/summary", headers=H_B, params={"month": "2026-10"})
j = r.json()
check("无数据月份不调用模型", r.status_code == 200 and "暂无账单数据" in j["summary"], r.text)

async def fake_summary_chat(messages, temperature=0.0, model=None):
    return '{"summary":"本月收入800元，支出35元，结余765元，整体控制良好。建议继续保持记账习惯。"}'

ai_service.chat = fake_summary_chat
r = client.get("/api/ai/summary", headers=H_A, params={"month": "2026-10"})
j = r.json()
check("月度总结基于真实统计", r.status_code == 200 and j["expense"] == "50.00", r.text)

# ---------- 13. AI 草稿确认后保存（source=ai 可追溯） ----------
r = client.post("/api/bills", headers=H_A, json={
    "type": "expense", "amount": "32", "category": "餐饮",
    "bill_date": "2026-10-19", "remark": "午饭", "source": "ai"})
check("AI草稿确认保存(source=ai)", r.status_code == 200 and r.json()["source"] == "ai", r.text)

# ---------- 14. AI 调用日志已落库 ----------
from app.database import SessionLocal
from app.models import AICallLog
db = SessionLocal()
logs = db.query(AICallLog).filter(AICallLog.user_id != None).count()  # noqa: E711
db.close()
check("AI调用日志已记录", logs >= 4, f"实际 {logs} 条")

print(f"\n全部通过：{PASSED} 项断言")
