# -*- coding: utf-8 -*-
"""公网部署验证：只读检查健康、登录、健康报告、模拟器、CSV 模板、Agent 健康。

用法：
    python deploy/verify_public.py --base-url https://your.domain
"""
from __future__ import annotations

import argparse
import sys

import httpx

PASSED = 0
FAILED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"[PASS] {name}")
    else:
        FAILED += 1
        print(f"[FAIL] {name}  -- {detail}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", default="judge_demo")
    parser.add_argument("--password", default="judge2026")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=30, follow_redirects=True) as client:
        r = client.get("/api/health")
        check("后端健康 /api/health", r.status_code == 200 and r.json().get("ok") is True,
              r.text[:200])
        r = client.get("/docs")
        check("API 文档 /docs", r.status_code == 200, str(r.status_code))
        r = client.get("/")
        check("前端首页可访问", r.status_code == 200 and ("id=\"app\"" in r.text or "知账" in r.text),
              r.text[:200])
        r = client.post("/api/auth/login", json={
            "username": args.username, "password": args.password})
        check("演示账号可登录", r.status_code == 200 and bool(r.json().get("access_token")),
              r.text[:200])
        if r.status_code != 200:
            print("\n部署验证失败：登录不通过，后续接口跳过。")
            raise SystemExit(1)
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        r = client.get("/api/consumption-health/report", headers=headers)
        check("消费健康报告", r.status_code == 200
              and len(r.json().get("indicators", [])) == 5, r.text[:200])
        r = client.post("/api/decision-simulator/simulate", headers=headers,
                        json={"amount": "1000", "category": "购物", "horizon_months": 3})
        check("消费决策模拟器", r.status_code == 200 and "message" in r.json(),
              r.text[:200])
        r = client.get("/api/imports/template")
        check("CSV 导入模板", r.status_code == 200 and "csv" in r.json(),
              r.text[:200])
        r = client.get("/api/agent/health")
        check("Agent 健康检查", r.status_code == 200, r.text[:200])
    print(f"\n通过 {PASSED} 项，失败 {FAILED} 项")
    if FAILED:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
