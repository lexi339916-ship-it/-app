# -*- coding: utf-8 -*-
"""交付前检查：密钥、数据库、构建产物、评测报告、PPT/视频大小。

不读取、不打印任何密钥内容；只报告文件是否存在与风险。
运行：python tools/delivery_check.py
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".runtime", "node_modules", "unpackage", "dist", "__pycache__",
             ".git", ".idea", ".vscode", "h5"}
PASS, WARN, FAIL = [], [], []


def add(bucket: list, text: str) -> None:
    bucket.append(text)


def iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


# 1) 密钥文件
env_files = [p for p in iter_files() if p.name == ".env" or p.name.endswith(".env.local")]
if env_files:
    for p in env_files:
        add(WARN, f"发现本地密钥文件 {p.relative_to(ROOT)}：提交前删除并轮换密钥，只保留 .env.example")
else:
    add(PASS, "未发现 .env/.env.local 密钥文件")

# 2) 数据库文件
db_files = [p for p in iter_files() if p.suffix.lower() in (".db", ".sqlite", ".sqlite3")]
if db_files:
    total_mb = sum(p.stat().st_size for p in db_files) / 1024 / 1024
    names = "、".join(str(p.relative_to(ROOT)) for p in db_files[:6])
    add(WARN, f"发现 {len(db_files)} 个数据库文件（{total_mb:.1f}MB）：{names}；提交前删除")
else:
    add(PASS, "未发现数据库文件")

# 3) 代码中的疑似密钥（排除测试占位）
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"),
]
hits = []
for path in iter_files():
    if path.suffix.lower() not in (".py", ".js", ".vue", ".json", ".yml", ".yaml",
                                   ".md", ".example", ".txt"):
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(str(path.relative_to(ROOT)))
            break
if hits:
    add(FAIL, "代码/文档中发现疑似真实密钥：" + "、".join(sorted(set(hits))[:10]))
else:
    add(PASS, "未在代码/文档中发现疑似真实密钥")

# 4) 部署产物
h5_index = ROOT / "deploy" / "h5" / "index.html"
if h5_index.exists():
    add(PASS, "deploy/h5/index.html 存在（前端预构建产物）")
else:
    add(FAIL, "deploy/h5/index.html 不存在，前端无法部署")

# 5) 评测报告
for name in ("report.md", "flow_report.md", "report_test.md", "multi_turn_report.md", "decision_simulator_report.md", "csv_import_report.md"):
    path = ROOT / "tests" / "agent_eval" / name
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r"通过[：:]\s*(\d+)", text)
        rate = re.search(r"(\d+(?:\.\d+)?)%", text)
        add(PASS, f"tests/agent_eval/{name} 存在"
                  + (f"（通过 {match.group(1)}）" if match else "")
                  + (f"（成功率 {rate.group(0)}）" if rate else ""))
    else:
        add(WARN, f"缺少评测报告 tests/agent_eval/{name}")

# 6) PPT / 视频
ppt_files = [p for p in iter_files() if p.suffix.lower() in (".ppt", ".pptx")]
video_files = [p for p in iter_files() if p.suffix.lower() in (".mp4", ".mov", ".webm")]
if not ppt_files:
    add(WARN, "未发现 PPT 文件：按 20 页、16:9、≤50MB 准备")
for p in ppt_files:
    size_mb = p.stat().st_size / 1024 / 1024
    add(PASS if size_mb <= 50 else FAIL,
        f"{p.relative_to(ROOT)} 大小 {size_mb:.1f}MB（要求 ≤50MB）")
if not video_files:
    add(WARN, "未发现演示视频：按 ≤6 分钟、MP4、≤300MB 准备")
for p in video_files:
    size_mb = p.stat().st_size / 1024 / 1024
    add(PASS if size_mb <= 300 else FAIL,
        f"{p.relative_to(ROOT)} 大小 {size_mb:.1f}MB（要求 ≤300MB）")

# 7) .gitignore 关键项
gitignore = (ROOT / ".gitignore")
text = gitignore.read_text(encoding="utf-8", errors="ignore") if gitignore.exists() else ""
missing = [item for item in (".env", "*.db", "node_modules/", "unpackage/")
           if item not in text]
if missing:
    add(FAIL, ".gitignore 缺少：" + "、".join(missing))
else:
    add(PASS, ".gitignore 已覆盖密钥、数据库与构建产物")

# 8) 匿名材料人工项
add(WARN, "匿名检查需人工完成：PPT/视频/演示页不得出现学校、单位、姓名、Logo、水印；检查文件元数据")

print("=" * 60)
print("交付检查结果")
print("=" * 60)
for title, bucket in (("PASS", PASS), ("WARN", WARN), ("FAIL", FAIL)):
    for item in bucket:
        print(f"[{title}] {item}")
print("-" * 60)
print(f"通过 {len(PASS)} 项，警告 {len(WARN)} 项，失败 {len(FAIL)} 项")
if FAIL:
    raise SystemExit(1)
