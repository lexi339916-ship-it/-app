# -*- coding: utf-8 -*-
"""头像上传测试：校验、压缩、持久化、删除与用户隔离。"""
import io
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./avatar_test.db"
for f in Path(".").glob("avatar_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

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


def register(username: str) -> dict:
    r = client.post("/api/auth/register", json={
        "username": username, "password": "abc123", "nickname": username})
    check(f"注册 {username}", r.status_code == 200, r.text)
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def png_bytes(size: tuple[int, int] = (320, 200), color=(90, 84, 184)) -> bytes:
    image = Image.new("RGB", size, color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


H_A = register("avatar_a")
H_B = register("avatar_b")
me = client.get("/api/auth/me", headers=H_A).json()
check("默认头像为空", me.get("avatar") == "", str(me))

r = client.post("/api/auth/avatar", files={
    "file": ("a.png", png_bytes(), "image/png")})
check("未登录上传 401", r.status_code == 401, r.text)

r = client.post("/api/auth/avatar", headers=H_A,
                files={"file": ("a.txt", b"not an image", "text/plain")})
check("非图片 400", r.status_code == 400, r.text)

r = client.post("/api/auth/avatar", headers=H_A,
                files={"file": ("big.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")})
check("超限 413", r.status_code == 413, r.text)

r = client.post("/api/auth/avatar", headers=H_A,
                files={"file": ("a.png", png_bytes(), "image/png")})
check("合法图片上传 200", r.status_code == 200, r.text[:200])
avatar = r.json().get("avatar", "")
check("返回 data URL", avatar.startswith("data:image/jpeg;base64,"), avatar[:40])
check("头像长度可控", 500 < len(avatar) < 200000, str(len(avatar)))

me = client.get("/api/auth/me", headers=H_A).json()
check("/me 返回头像", me.get("avatar") == avatar, str(me)[:100])
login = client.post("/api/auth/login", json={
    "username": "avatar_a", "password": "abc123"}).json()
check("登录返回头像", login["user"].get("avatar") == avatar)

other = client.get("/api/auth/me", headers=H_B).json()
check("其他用户头像为空", other.get("avatar") == "", str(other))

r = client.delete("/api/auth/avatar", headers=H_A)
check("删除头像 200", r.status_code == 200 and r.json().get("avatar") == "", r.text[:100])
me = client.get("/api/auth/me", headers=H_A).json()
check("删除后 /me 为空", me.get("avatar") == "")

print(f"\n全部通过：{PASSED} 项断言")
