# -*- coding: utf-8 -*-
"""中文数字归一化测试（语音/文本记账共用规则层）。

覆盖 ≥20 条：十五、三十二、一百二、一百零二、三千五、一万二、十五块五 等。
运行：python tests/chinese_number_test.py
"""
import sys
from decimal import Decimal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.agent import tools  # noqa: E402

PASSED = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASSED
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f"  -- {detail}" if detail and not cond else ""))
    if cond:
        PASSED += 1
    else:
        raise SystemExit(f"测试失败：{name} {detail}")


# ---------- 整数 ----------
INT_CASES = [
    ("十五", 15),
    ("二十", 20),
    ("三十二", 32),
    ("一百", 100),
    ("一百二", 120),
    ("一百零二", 102),
    ("一百零五", 105),
    ("一百二十三", 123),
    ("两百", 200),
    ("两百五", 250),
    ("三百六十", 360),
    ("一千", 1000),
    ("一千二", 1200),
    ("一千零五十", 1050),
    ("一千二百三十四", 1234),
    ("三千五", 3500),
    ("五千", 5000),
    ("八千", 8000),
    ("一万", 10000),
    ("一万二", 12000),
    ("一万零二百", 10200),
    ("两万五", 25000),
]
for text, expected in INT_CASES:
    value = tools._cn_to_int(text)
    check(f"中文整数 {text} → {expected}", value == expected, str(value))

# ---------- 金额（含口语小数） ----------
CATS = ["餐饮", "交通", "购物", "娱乐", "其他", "工资", "其他收入"]


def amount_of(text: str) -> Decimal | None:
    return tools.parse_bill_fallback(text, CATS)["amount"]


AMOUNT_CASES = [
    ("午饭三十二", Decimal("32")),
    ("打车十五块", Decimal("15")),
    ("咖啡十五块五", Decimal("15.5")),
    ("地铁3块5", Decimal("3.5")),
    ("奶茶十二元八角", Decimal("12.8")),
    ("买书一百二", Decimal("120")),
    ("房租一千二", Decimal("1200")),
    ("工资八千", Decimal("8000")),
    ("收到红包两百五", Decimal("250")),
    ("买电脑一万二", Decimal("12000")),
    ("停车费五块", Decimal("5")),
    ("话费一百零二", Decimal("102")),
]
for text, expected in AMOUNT_CASES:
    value = amount_of(text)
    check(f"金额 {text} → {expected}", value == expected, str(value))

# ---------- 类型与分类 ----------
check("工资识别为收入", tools.parse_bill_fallback("工资八千", CATS)["type"] == "income")
check("退款识别为收入", tools.parse_bill_fallback("退款到账 25 元", CATS)["type"] == "income")
check("午饭识别为餐饮", tools.parse_bill_fallback("午饭三十二", CATS)["category"] == "餐饮")
check("打车识别为交通", tools.parse_bill_fallback("打车十五块", CATS)["category"] == "交通")
check("买书识别为学习或购物",
      tools.parse_bill_fallback("买书一百二", CATS + ["学习"])["category"] in ("学习", "购物"))

# ---------- 边界 ----------
check("空字符串不猜金额", tools.parse_bill_fallback("午饭", CATS)["amount"] is None)
check("无金额标记 missing", "amount" in tools.parse_bill_fallback("记账", CATS)["missing_fields"])
check("数字原文优先", amount_of("午饭 32.5 元") == Decimal("32.5"))


# ---------- 目标周期中文数字 ----------
GOAL_CASES = [
    ("三个月存三千去旅行", 3000, 3),
    ("六个月存六千买电脑", 6000, 6),
    ("两年存5万买车", 50000, 24),
    ("每个月存三百，存一年", 3600, 12),
]
for text, amount, months in GOAL_CASES:
    parsed = tools.parse_goal(text)
    check(f"目标 {text} 金额 {amount}",
          parsed["amount"] == Decimal(amount), str(parsed))
    check(f"目标 {text} 周期 {months}", parsed["months"] == months, str(parsed))


# ---------- 意图与口语噪声 ----------
from app.services.agent import orchestrator  # noqa: E402
check("中文金额意图识别", orchestrator._detect_intent("咖啡十五块五", "auto") == "bill")
check("中文金额意图识别2", orchestrator._detect_intent("停车费五块", "auto") == "bill")
check("计划一下不误判金额", tools.parse_goal("计划一下")["amount"] is None)
check("计划一下缺金额", "target_amount" in tools.parse_goal("计划一下")["missing"])
check("存一点钱不误判金额", tools.parse_goal("我想存一点钱")["amount"] is None)
check("预算查询意图", orchestrator._detect_intent("本月预算用了多少", "auto") == "query")

print(f"\n全部通过：{PASSED} 项断言")
