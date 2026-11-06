# -*- coding: utf-8 -*-
"""Agent 历史会话测试：标题/预览、继续会话、软删除与跨用户隔离。"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./agent_session_test.db"
for f in Path(".").glob("agent_session_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.models import AgentRun  # noqa: E402

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


A = register("session_a")
B = register("session_b")

r = client.post("/api/agent/run", headers=A, json={
    "message": "查看我的个人资产", "mode": "auto"})
check("第一轮完成", r.status_code == 200 and r.json()["status"] == "completed", r.text)
first = r.json()
session_id = first["session_id"]
check("返回会话 id", bool(session_id), first)

r = client.post("/api/agent/run", headers=A, json={
    "message": "为什么这个月净资产减少了", "mode": "auto",
    "session_id": session_id, "parent_run_id": first["run_id"]})
check("第二轮继续会话", r.status_code == 200 and r.json()["session_id"] == session_id, r.text)

r = client.get("/api/agent/sessions", headers=A, params={"limit": 10})
sessions = r.json()
check("历史会话列表有记录", len(sessions) == 1, sessions)
check("历史轮数正确", sessions[0]["turn_count"] == 2, sessions)
check("历史标题取首轮", sessions[0]["title"] == "查看我的个人资产", sessions)
check("历史预览非空", bool(sessions[0]["preview"]), sessions)

r = client.get(f"/api/agent/sessions/{session_id}", headers=A)
check("可读取历史消息", r.status_code == 200 and len(r.json()) == 2, r.text)

r = client.delete(f"/api/agent/sessions/{session_id}", headers=A)
check("删除会话成功", r.status_code == 200 and r.json()["ok"] is True, r.text)
r = client.get("/api/agent/sessions", headers=A)
check("删除后不出现在历史", r.json() == [], r.text)
r = client.get(f"/api/agent/sessions/{session_id}", headers=A)
check("删除后不可读取", r.status_code == 404, r.text)
r = client.delete(f"/api/agent/sessions/{session_id}", headers=A)
check("重复删除幂等", r.status_code == 200, r.text)

with SessionLocal() as db:
    count = db.scalar(select(func.count()).where(AgentRun.user_id == 1))
check("软删除保留审计记录", count == 2, str(count))

r = client.delete(f"/api/agent/sessions/{session_id}", headers=B)
check("B 不能删除 A 的会话", r.status_code == 404, r.text)

print(f"\n全部通过：{PASSED} 项断言")
