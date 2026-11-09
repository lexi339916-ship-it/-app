# -*- coding: utf-8 -*-
"""便签分类测试：待办 / 想法 / 心情的创建、筛选、排序、兼容与用户隔离。"""
import io
import os
import sys
from pathlib import Path

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./notes_entries_test.db"
for f in Path(".").glob("notes_entries_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402

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


H_A = register("notes_a")
H_B = register("notes_b")

# ---------- 创建三类记录 ----------
r = client.post("/api/notes", headers=H_A, json={
    "title": "咖啡店的灵感", "content": "靠窗的位置适合写周报。",
    "note_type": "note", "entry_type": "idea", "color": "lilac"})
check("创建想法", r.status_code == 200 and r.json()["entry_type"] == "idea", r.text)
idea_id = r.json()["id"]

r = client.post("/api/notes", headers=H_A, json={
    "title": "今天心情不错", "content": "下班路上看到了晚霞。",
    "note_type": "note", "entry_type": "mood", "color": "rose"})
check("创建心情", r.status_code == 200 and r.json()["entry_type"] == "mood", r.text)
mood_id = r.json()["id"]

r = client.post("/api/notes", headers=H_A, json={
    "title": "周五交房租", "note_type": "todo", "entry_type": "mood",
    "due_at": "2026-11-20 18:00:00", "location": "手机银行"})
check("待办自动归为 note 细分",
      r.status_code == 200 and r.json()["note_type"] == "todo"
      and r.json()["entry_type"] == "note", r.text)
check("待办地点保存成功", r.json()["location"] == "手机银行", r.text)

r = client.post("/api/notes", headers=H_A, json={
    "title": "旧版普通便签", "content": "升级前创建的便签"})
check("旧版便签默认 entry_type=note",
      r.status_code == 200 and r.json()["entry_type"] == "note", r.text)
legacy_id = r.json()["id"]

# ---------- 照片上传 ----------
buf = io.BytesIO()
Image.new("RGB", (64, 48), (246, 198, 213)).save(buf, format="PNG")
r = client.post("/api/notes/photo", headers=H_A,
                files={"file": ("moment.png", buf.getvalue(), "image/png")})
check("上传记录照片", r.status_code == 200
      and r.json()["image"].startswith("data:image/jpeg;base64,"), r.text)
note_image = r.json()["image"]
check("照片压缩为 JPEG data URL", len(note_image) > 100, r.text)

r = client.post("/api/notes", headers=H_A, json={
    "title": "带照片的想法", "content": "把今天的桌面拍下来。",
    "note_type": "note", "entry_type": "idea", "image": note_image})
check("记录保存单张照片",
      r.status_code == 200 and r.json()["image"] == note_image
      and r.json()["images"] == [note_image], r.text)
photo_note_id = r.json()["id"]

r = client.get(f"/api/notes/{photo_note_id}", headers=H_A)
check("记录详情返回照片", r.json()["images"] == [note_image], r.text)

r = client.put(f"/api/notes/{photo_note_id}", headers=H_A, json={
    "title": "带照片的想法（已编辑）", "content": "保留照片",
    "note_type": "note", "entry_type": "idea",
    "images": [note_image, note_image]})
check("编辑记录保留多张照片", r.status_code == 200
      and r.json()["images"] == [note_image, note_image]
      and "已编辑" in r.json()["title"], r.text)

r = client.post("/api/notes", headers=H_A, json={
    "title": "多图想法", "entry_type": "idea",
    "images": [note_image, note_image, note_image]})
check("记录支持多张照片",
      r.status_code == 200 and len(r.json()["images"]) == 3, r.text)
multi_photo_id = r.json()["id"]

r = client.post("/api/notes", headers=H_A, json={
    "title": "太多照片", "entry_type": "idea",
    "images": [note_image] * 7})
check("最多 6 张照片(422)", r.status_code == 422, r.text)

r = client.post("/api/notes/photo", headers=H_A,
                files={"file": ("not-image.txt", b"hello", "text/plain")})
check("非图片文件被拒绝(400)", r.status_code == 400, r.text)

r = client.post("/api/notes/photo",
                files={"file": ("moment.png", buf.getvalue(), "image/png")})
check("未登录不能上传照片(401)", r.status_code == 401, r.text)

# ---------- 筛选与兼容 ----------
r = client.get("/api/notes", headers=H_A, params={"entry_type": "idea"})
body = r.json()
check("想法列表包含想法与旧便签",
      body["total"] == 4 and {i["id"] for i in body["items"]}
      == {idea_id, legacy_id, photo_note_id, multi_photo_id}, r.text)
check("想法列表全部是普通便签",
      all(i["note_type"] == "note" and i["entry_type"] in ("idea", "note")
          for i in body["items"]), r.text)
check("想法列表不含心情/待办",
      all(i["id"] not in (mood_id,) for i in body["items"]), r.text)

r = client.get("/api/notes", headers=H_A, params={"entry_type": "mood"})
body = r.json()
check("心情列表仅含心情", body["total"] == 1 and body["items"][0]["id"] == mood_id, r.text)

r = client.get("/api/notes", headers=H_A, params={"note_type": "todo"})
check("待办列表仍可用", any(i["title"] == "周五交房租" for i in r.json()["items"]), r.text)

# ---------- 更新与用户隔离 ----------
r = client.put(f"/api/notes/{mood_id}", headers=H_A, json={
    "title": "今天心情很好", "content": "晚霞像橘子汽水。",
    "note_type": "note", "entry_type": "mood", "status": "open",
    "priority": "medium", "pinned": False, "color": "rose"})
check("编辑心情保留分类",
      r.status_code == 200 and r.json()["entry_type"] == "mood"
      and r.json()["title"] == "今天心情很好", r.text)

r = client.get(f"/api/notes/{mood_id}", headers=H_B)
check("跨用户读取想法/心情(404)", r.status_code == 404, r.text)

r = client.get("/api/notes", headers=H_B, params={"entry_type": "mood"})
check("用户B看不到A的心情", r.json()["total"] == 0, r.text)

r = client.post("/api/notes", headers=H_A, json={
    "title": "非法分类", "entry_type": "diary"})
check("非法分类被拒绝(422)", r.status_code == 422, r.text)

print(f"\n通过 {PASSED} 项便签分类测试")
