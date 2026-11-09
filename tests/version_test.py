# -*- coding: utf-8 -*-
"""版本一致性测试：后端健康检查、Agent health、前端 manifest/pages。"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["DATABASE_URL"] = "sqlite:///./version_test.db"
for f in Path(".").glob("version_test.db*"):
    f.unlink()

from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app, seed_default_categories  # noqa: E402
from app.version import APP_NAME, APP_VERSION  # noqa: E402

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


r = client.get("/api/health")
check("健康检查 200", r.status_code == 200, r.text)
h = r.json()
check("服务名统一", h.get("service") == "zhizhang-api", str(h))
check("应用名包含知账", "知账" in h.get("name", ""), str(h))
check("版本为 2.1.0", h.get("version") == APP_VERSION == "2.1.0", str(h))

r = client.get("/api/agent/health")
check("Agent health 200", r.status_code == 200, r.text)
a = r.json()
check("Agent 服务名统一", a.get("service") == "zhizhang-agent", str(a))
check("Agent 版本一致", a.get("version") == APP_VERSION, str(a))

check("版本符合 semver", bool(re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)), APP_VERSION)
check("应用名常量正确", APP_NAME == "知账 · 家庭消费健康 Agent", APP_NAME)

manifest = json.loads((ROOT / "frontend" / "manifest.json").read_text(encoding="utf-8"))
check("manifest 应用名", manifest.get("name") == "知账", str(manifest.get("name")))
check("manifest 版本", manifest.get("versionName") == APP_VERSION,
      str(manifest.get("versionName")))
check("manifest versionCode", str(manifest.get("versionCode")) == "210",
      str(manifest.get("versionCode")))

pages = json.loads((ROOT / "frontend" / "pages.json").read_text(encoding="utf-8"))
check("全局标题为知账", pages.get("globalStyle", {}).get("navigationBarTitleText") == "知账",
      str(pages.get("globalStyle")))

print(f"\n全部通过：{PASSED} 项断言")
