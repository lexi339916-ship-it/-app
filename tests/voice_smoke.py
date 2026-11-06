# -*- coding: utf-8 -*-
"""语音转写接口测试（不依赖真实 ASR）。运行：python tests/voice_smoke.py"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./voice_smoke.db"
for f in Path(".").glob("voice_smoke.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.routers import voice as voice_router  # noqa: E402

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


def main() -> None:
    res = client.post("/api/auth/register", json={
        "username": "voice_tester", "password": "voice123456", "nickname": "语音测试"})
    check("注册", res.status_code == 200, res.text)
    token = res.json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    # 未配置 ASR：明确 503，前端应改用文字
    old_url, old_key, old_model = config.ASR_BASE_URL, config.ASR_API_KEY, config.ASR_MODEL
    config.ASR_BASE_URL, config.ASR_API_KEY = "", ""
    res = client.post("/api/voice/transcribe",
                      files={"file": ("voice.mp3", b"fake", "audio/mpeg")}, headers=h)
    check("未配置 ASR 返回 503", res.status_code == 503, res.text)

    # mock ASR 成功
    async def fake_asr(filename, data, content_type):
        return {"text": "午饭三十二元，微信付的", "provider": "mock"}

    original = voice_router._call_asr
    voice_router._call_asr = fake_asr
    config.ASR_BASE_URL, config.ASR_API_KEY, config.ASR_MODEL = "http://mock", "mock", "mock"
    try:
        res = client.post("/api/voice/transcribe",
                          files={"file": ("voice.mp3", b"fake-audio", "audio/mpeg")},
                          headers=h)
        check("语音转写返回 200", res.status_code == 200, res.text)
        body = res.json()
        check("转写文本正确", body["text"] == "午饭三十二元，微信付的", str(body))
        check("返回模型信息", body.get("model") == "mock", str(body))

        res = client.post("/api/voice/transcribe",
                          files={"file": ("voice.mp3", b"", "audio/mpeg")}, headers=h)
        check("空音频返回 400", res.status_code == 400, res.text)

        big = b"x" * (5 * 1024 * 1024 + 1)
        res = client.post("/api/voice/transcribe",
                          files={"file": ("voice.mp3", big, "audio/mpeg")}, headers=h)
        check("超大音频返回 413", res.status_code == 413, res.text)
    finally:
        voice_router._call_asr = original
        config.ASR_BASE_URL, config.ASR_API_KEY, config.ASR_MODEL = old_url, old_key, old_model

    print(f"\n全部通过：{PASSED} 项断言")


if __name__ == "__main__":
    main()
