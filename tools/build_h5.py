# -*- coding: utf-8 -*-
"""一键构建 uni-app H5，输出到 deploy/h5。

用法：
    python tools/build_h5.py
    python tools/build_h5.py --skip-install   # 已有 node_modules 时复用缓存

要求：Node.js 18+。没有系统 Node 时，脚本会尝试使用项目内 `.runtime/node-*/node.exe`。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
OUTPUT = ROOT / "deploy" / "h5"

PACKAGE_JSON = {
    "name": "cansai-h5",
    "version": "0.0.0",
    "private": True,
    "scripts": {"dev:h5": "uni", "build:h5": "uni build"},
    "dependencies": {
        "@dcloudio/uni-app": "3.0.0-5030420261029002",
        "@dcloudio/uni-components": "3.0.0-5030420261029002",
        "@dcloudio/uni-h5": "3.0.0-5030420261029002",
        "vue": "^3.4.21",
        "vue-i18n": "^9.1.9",
    },
    "devDependencies": {
        "@dcloudio/uni-cli-shared": "3.0.0-5030420261029002",
        "@dcloudio/vite-plugin-uni": "3.0.0-5030420261029002",
        "@vue/runtime-core": "^3.4.21",
        "rollup": "4.14.3",
        "vite": "5.2.8",
    },
}

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <script>
      var coverSupport = 'CSS' in window && typeof CSS.supports === 'function' &&
        (CSS.supports('top: env(a)') || CSS.supports('top: constant(a)'))
      document.write('<meta name="viewport" content="width=device-width, user-scalable=no, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0' + (coverSupport ? ', viewport-fit=cover' : '') + '" />')
    </script>
    <title>知账 · 家庭消费健康 Agent</title>
    <!--preload-links-->
    <!--app-context-->
  </head>
  <body>
    <div id="app"><!--app-html--></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
"""

VITE_CONFIG = """import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

export default defineConfig({
  plugins: [uni()],
})
"""


def find_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    candidates = sorted((ROOT / ".runtime").glob("node-*/node.exe"))
    return str(candidates[-1]) if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    node = find_node()
    if not node:
        raise SystemExit("未找到 Node.js。请安装 Node 18+，或把便携 Node 放到 .runtime/node-*/node.exe。")
    node_dir = str(Path(node).parent)
    env = {**os.environ, "PATH": node_dir + os.pathsep + os.environ.get("PATH", "")}

    build_dir = Path(tempfile.mkdtemp(prefix="cansai-h5-"))
    src = build_dir / "src"
    src.mkdir(parents=True)
    for name in ("App.vue", "main.js", "manifest.json", "pages.json",
                 "api", "common", "components", "pages", "static", "store"):
        source = FRONTEND / name
        target = src / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    (build_dir / "package.json").write_text(
        json.dumps(PACKAGE_JSON, ensure_ascii=False, indent=2), encoding="utf-8")
    (build_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (build_dir / "vite.config.js").write_text(VITE_CONFIG, encoding="utf-8")

    npm = "npm.cmd" if os.name == "nt" else "npm"
    npm_path = str(Path(node).parent / npm) if os.name == "nt" else npm

    def run_npm(args: list[str]) -> None:
        command = ["cmd", "/c", npm_path, *args] if os.name == "nt" else [npm, *args]
        subprocess.run(command, cwd=build_dir, env=env, check=True)

    print(f"构建目录：{build_dir}")
    if not args.skip_install:
        run_npm(["install", "--registry=https://registry.npmmirror.com",
                 "--no-audit", "--no-fund"])
    run_npm(["run", "build:h5"])

    built = build_dir / "dist" / "build" / "h5"
    if not built.exists():
        raise SystemExit("构建产物不存在，请检查 uni-app 构建日志。")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    shutil.copytree(built, OUTPUT)
    print(f"已输出到 {OUTPUT}")


if __name__ == "__main__":
    main()
