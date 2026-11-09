# -*- coding: utf-8 -*-
"""Agent 简单对话测试：问候/身份/感谢不误走业务工具。"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./agent_chat_test.db"
for f in Path(".").glob("agent_chat_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402

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


r = client.post("/api/auth/register", json={
    "username": "chat_user", "password": "abc123", "nickname": "chat"})
check("注册", r.status_code == 200, r.text)
H = {"Authorization": f"Bearer {r.json()['access_token']}"}


def run(message: str) -> dict:
    response = client.post("/api/agent/run", headers=H, json={
        "message": message, "mode": "auto"})
    check(f"发送「{message}」", response.status_code == 200, response.text)
    return response.json()


body = run("你好")
check("你好完成", body["status"] == "completed", body["status"])
check("你好回答包含知账", "知账" in body["answer"], body["answer"])
check("你好不误走记账",
      not any(s["tool_name"] == "parse_bill" for s in body["steps"]), body["steps"])
check("你好不返回月度统计", "收入" not in body["answer"], body["answer"])

body = run("你是谁")
check("身份回答", "个人消费管理助手" in body["answer"], body["answer"])
check("身份不审批", body["approvals"] == [], str(body["approvals"]))

body = run("谢谢")
check("感谢回答", "不客气" in body["answer"], body["answer"])

body = run("你好，帮我查一下本月预算")
check("带业务的问候不误判寒暄",
      any(s["tool_name"] == "get_budget_status" for s in body["steps"]), body["steps"])
check("带业务问候回答预算", "预算" in body["answer"], body["answer"])

body = run("你好，午饭32元微信付的")
check("代记账问候仍走记账",
      any(s["tool_name"] == "parse_bill" for s in body["steps"]), body["steps"])

print(f"\n全部通过：{PASSED} 项断言")
