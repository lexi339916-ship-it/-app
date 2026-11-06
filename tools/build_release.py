# -*- coding: utf-8 -*-
"""生成比赛提交包：排除密钥、数据库、缓存和构建依赖，附带交付说明与清单。

用法：
    python tools/build_release.py
输出：
    release/知账_提交包_YYYYMMDD/      目录
    release/知账_提交包_YYYYMMDD.zip   压缩包
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = date.today().strftime("%Y%m%d")
NAME = f"知账_提交包_{STAMP}"
OUT = ROOT / "release" / NAME
ZIP = ROOT / "release" / f"{NAME}.zip"

IGNORE = shutil.ignore_patterns(
    ".env", "*.db", "*.db-*", "*.sqlite", "*.sqlite3", "*.pyc", "__pycache__",
    ".pytest_cache", ".mypy_cache", "node_modules", "unpackage", "dist",
    ".runtime", ".zcode", ".git", ".idea", ".vscode", "release", "*.log",
    "deploy/data", "backend/py",
)

COPY_DIRS = ["backend", "frontend", "deploy", "database", "tools", "tests", "docs"]
COPY_FILES = ["AGENTS.md", "PROJECT_MEMORY.md", "计划.md", "配置说明.md",
              ".gitignore", ".dockerignore"]


def copy_all() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for name in COPY_DIRS:
        src = ROOT / name
        if src.exists():
            shutil.copytree(src, OUT / name, ignore=IGNORE)
    for name in COPY_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, OUT / name)


def write_docs() -> None:
    (OUT / "交付说明.md").write_text(f"""# 知账 · 家庭消费健康 Agent — 交付说明

> 提交包生成日期：{STAMP}
> 演示账号：`judge_demo / judge2026`

## 1. 本地启动

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env     # 填写 AI_BASE_URL / AI_API_KEY / AI_MODEL / JWT_SECRET
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 另开终端，启动同源 H5（静态 + /api 反代）
cd ..
python deploy/proxy_server.py --port 8080 --backend http://127.0.0.1:8000
```

访问 `http://127.0.0.1:8080`，使用演示账号登录。首次启动或需要恢复演示数据：

```bash
python tools/seed_demo.py
```

## 2. 公网部署

- Docker：`cd deploy && cp .env.example .env`，填写后 `docker compose up -d --build`。
- 无 Docker：用 `deploy/proxy_server.py` 同源代理，外层用 Nginx/Caddy + HTTPS。
- 部署后验证：`python deploy/verify_public.py --base-url https://your.domain`。
- 详细步骤见 `deploy/README.md`。

## 3. 测试与证据

- 100 条 Agent 评测：`tests/agent_eval/report.md`
- 独立 test 划分 50 条：`tests/agent_eval/report_test.md`
- 流程/异常 94 项：`tests/agent_eval/flow_report.md`
- 多轮对话 53 项：`tests/agent_eval/multi_turn_report.md`
- 决策模拟 62 项：`tests/agent_eval/decision_simulator_report.md`
- CSV 导入 47 项：`tests/agent_eval/csv_import_report.md`

复现：

```bash
python tools/seed_demo.py
python tests/agent_eval/run_eval.py --split all
python tests/agent_eval/run_flow_eval.py
```

说明：以上均为团队自测，不是第三方认证；金额一致性等指标为启发式检查。

## 4. 安全边界

- 本包不包含 `.env`、数据库、录音、真实用户数据。
- 演示数据为合成数据；不接真实银行/支付宝/微信账号。
- 不做自动转账、投资建议、代客理财。
- 提交前请自行旋转 AI Key，并确认 `.env` 未被打包。

## 5. 已知限制

- Docker Compose 未在本机实跑（本机无 Docker）。
- 公网地址需自行部署后用 `deploy/verify_public.py` 验证。
- 语音真实 ASR/麦克风链路未做端到端验证；未配置 ASR 时返回 503。
- 消费决策模拟器基于历史结余确定性估算，不代表账户真实余额。
- CSV 导入覆盖常见微信/支付宝/通用表头，特殊银行格式未覆盖。
""", encoding="utf-8")

    (OUT / "SECURITY.md").write_text(f"""# 安全说明

- 提交包**不包含** `.env`、`*.db`、录音、真实用户数据或 `node_modules`。
- `JWT_SECRET` 已在开发环境轮换为随机长串；**AI API Key 必须在模型供应商控制台单独轮换**，本包不包含 Key。
- 演示账号 `judge_demo` 只用于合成数据演示，赛后请更换密码。
- 公网部署必须：HTTPS、`CORS_ORIGINS` 域名白名单、只暴露 80/443、登录限流、演示后重置数据。
- 若曾在任何聊天/文档/截图中暴露过 Key，请立即在供应商控制台吊销旧 Key。
""", encoding="utf-8")


def make_zip() -> None:
    ZIP.parent.mkdir(parents=True, exist_ok=True)
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in OUT.rglob("*"):
            if path.is_file():
                zf.write(path, Path(NAME) / path.relative_to(OUT))


def manifest() -> dict:
    files = []
    for path in OUT.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(OUT)).replace("\\", "/")
        if rel == "MANIFEST.json":
            continue
        data = path.read_bytes()
        files.append({
            "path": rel,
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    result = {"generated_at": date.today().isoformat(), "files": files,
              "count": len(files), "total_size": sum(f["size"] for f in files)}
    (OUT / "MANIFEST.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def verify() -> list[str]:
    problems = []
    forbidden_names = {".env", ".sqlite", ".sqlite3"}
    for path in OUT.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(OUT)).replace("\\", "/")
        name = path.name
        if name in forbidden_names or name.endswith((".db", ".db-journal", ".pyc")):
            problems.append(f"包含禁止文件：{rel}")
        if "/node_modules/" in f"/{rel}/" or "/unpackage/" in f"/{rel}/":
            problems.append(f"包含构建依赖：{rel}")
    secret_patterns = [
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
        re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
    ]
    for path in OUT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in (
                ".py", ".js", ".vue", ".json", ".yml", ".yaml", ".md", ".txt", ".example"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in secret_patterns:
            if pattern.search(text):
                problems.append(f"疑似密钥：{path.relative_to(OUT)}")
                break
    return problems


def main() -> None:
    copy_all()
    write_docs()
    meta = manifest()
    make_zip()
    problems = verify()
    print(f"输出目录：{OUT}")
    print(f"文件数：{meta['count']}，未压缩大小：{meta['total_size'] / 1024 / 1024:.2f}MB")
    print(f"压缩包：{ZIP}，大小：{ZIP.stat().st_size / 1024 / 1024:.2f}MB")
    if problems:
        print("检查失败：")
        for item in problems[:20]:
            print(" -", item)
        raise SystemExit(1)
    print("检查通过：无 .env / *.db / node_modules / 构建缓存 / 疑似密钥。")


if __name__ == "__main__":
    main()
