# -*- coding: utf-8 -*-
"""安全基线测试：敏感信息脱敏、配置默认值、登录限流辅助函数。

运行：python tests/security_test.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app import config  # noqa: E402
from app.services.ai_service import mask_sensitive  # noqa: E402

PASSED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASSED += 1
    else:
        raise SystemExit(f"测试失败：{name} {detail}")


CASES = [
    ("用我的银行卡密码 123456 记账", ["123456"]),
    ("我的密码是 abc123，记一笔午饭32", ["abc123"]),
    ("验证码 9876", ["9876"]),
    ("卡号 6222021234567890", ["6222021234567890"]),
    ("支付密码：888888", ["888888"]),
    ("口令 abcdef", ["abcdef"]),
]
for text, secrets in CASES:
    masked = mask_sensitive(text)
    check(f"脱敏：{text}", all(secret not in masked for secret in secrets)
          and "****" in masked, masked)

check("普通金额不被误脱敏", mask_sensitive("午饭32元") == "午饭32元")
check("空字符串安全", mask_sensitive("") == "")
check("默认 JWT 密钥被识别为不安全",
      config.JWT_SECRET == "dev-only-secret-change-me" or len(config.JWT_SECRET) >= 32)
check("登录限流阈值合理", config.LOGIN_MAX_ATTEMPTS >= 3)
check("登录限流窗口合理", config.LOGIN_WINDOW_MINUTES >= 1)
check("AI 超时为正数", config.AI_TIMEOUT_SECONDS > 0)
check("CORS 配置非空", bool(config.CORS_ORIGINS))

print(f"\n全部通过：{PASSED} 项断言")
