# -*- coding: utf-8 -*-
"""Agent 评测脚本（100 条，dev/test 双集）。

目标：对运行中的后端执行任务，统计状态、工具选择、参数、审批、禁止内容、
未审批写入、延迟与成本。默认不批准任何写操作，因此不会改动业务数据
（只会留下 agent_runs 轨迹）。

用法：
    python tests/agent_eval/run_eval.py --split all
    python tests/agent_eval/run_eval.py --split test
    python tests/agent_eval/run_eval.py --limit 10

输出：
    tests/agent_eval/report.md / report.json
    指定 split 时另写 report_dev.md / report_test.md
"""
import argparse
import json
import statistics
import sys
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx

OUT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT_DIR))
from cases import build_cases  # noqa: E402


def shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7])
    index = year * 12 + (mon - 1) + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def resolve_month(value: str) -> str:
    current = date.today().strftime("%Y-%m")
    if value == "current":
        return current
    if value == "prev":
        return shift_month(current, -1)
    return value


def percentile(values: list[int], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return float(ordered[index])


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _first_step(body: dict, tools: tuple[str, ...]) -> dict | None:
    for step in body.get("steps", []):
        if step.get("tool_name") in tools:
            return step
    return None


def _slot_value(body: dict, key: str):
    if key == "month":
        step = _first_step(body, ("summarize_spending", "largest_bill", "get_budget_status"))
        return (step or {}).get("args", {}).get("month")
    parse_bill = _first_step(body, ("parse_bill",))
    if parse_bill and key in ("amount", "category", "type"):
        drafts = parse_bill.get("result", {}).get("drafts") or []
        return drafts[0].get(key) if drafts else None
    parse_goal = _first_step(body, ("parse_goal",))
    if parse_goal and key in ("amount", "months", "monthly_amount"):
        return parse_goal.get("result", {}).get(key)
    return None


def check_slots(body: dict, slots: dict) -> tuple[bool, list[str]]:
    reasons = []
    for key, expected in slots.items():
        actual = _slot_value(body, key)
        if key == "month":
            ok = str(actual) == resolve_month(str(expected))
        elif key in ("amount", "monthly_amount"):
            ok = _decimal(actual) == _decimal(expected)
        elif key == "months":
            ok = actual is not None and int(actual) == int(expected)
        else:
            ok = str(actual) == str(expected)
        if not ok:
            reasons.append(f"参数 {key} 期望 {expected}，实际 {actual}")
    return (not reasons), reasons


def evaluate(case: dict, body: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    status = body.get("status")
    if status not in case["expect_status"]:
        reasons.append(f"状态 {status} 不在 {case['expect_status']}")
    tools = [s.get("tool_name") for s in body.get("steps", [])]
    if case["expect_any_tools"] and not any(t in tools for t in case["expect_any_tools"]):
        reasons.append(f"未命中工具 {case['expect_any_tools']}，实际 {tools}")
    answer = body.get("answer") or ""
    for text in case["expect_answer_contains"]:
        if text not in answer:
            reasons.append(f"回答缺少「{text}」")
    for text in case["forbid_answer_contains"]:
        if text and text in answer:
            reasons.append(f"回答出现禁止内容「{text}」")
    approvals = body.get("approvals") or []
    if case["expect_approval"] is True and not approvals:
        reasons.append("缺少审批")
    if case["expect_approval"] is False and approvals:
        reasons.append("不应生成审批")
    slots_ok, slot_reasons = check_slots(body, case["expect_slots"])
    reasons.extend(slot_reasons)
    return (not reasons), reasons


def amount_consistent(case: dict, body: dict) -> bool | None:
    """仅对“应生成审批且有金额槽位”的用例检查回答金额与解析金额一致。"""
    slots = case.get("expect_slots") or {}
    if case.get("expect_approval") is not True or "amount" not in slots:
        return None
    parsed = _decimal(_slot_value(body, "amount"))
    if parsed is None:
        return None
    answer = body.get("answer") or ""
    text = format(parsed, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in answer:
        return True
    # 多笔账单的回答通常展示合计金额
    parse_bill = _first_step(body, ("parse_bill",))
    drafts = (parse_bill or {}).get("result", {}).get("drafts") or []
    amounts = [_decimal(d.get("amount")) for d in drafts if d.get("amount") is not None]
    if len(amounts) > 1:
        total = sum(amounts[1:], amounts[0])
        total_text = format(total, "f").rstrip("0").rstrip(".")
        return total_text in answer
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="judge_demo")
    parser.add_argument("--password", default="judge2026")
    parser.add_argument("--split", choices=["all", "dev", "test"], default="all")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    all_cases = build_cases()
    cases = [c for c in all_cases if args.split == "all" or c["split"] == args.split]
    if args.limit:
        cases = cases[:args.limit]

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=90) as client:
        login = client.post("/api/auth/login", json={
            "username": args.username, "password": args.password})
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        agent_health = {}
        try:
            health_resp = client.get("/api/agent/health", headers=headers)
            agent_health = health_resp.json() if health_resp.status_code == 200 else {}
        except Exception:
            agent_health = {}

        def bill_total() -> int:
            resp = client.get("/api/bills", params={"page": 1, "page_size": 1},
                              headers=headers)
            return int(resp.json().get("total", 0)) if resp.status_code == 200 else 0

        bills_before = bill_total()
        results = []
        for case in cases:
            started = time.monotonic()
            error = ""
            body: dict = {}
            try:
                resp = client.post("/api/agent/run", json={
                    "message": case["message"], "mode": "auto"}, headers=headers)
                body = resp.json()
                if resp.status_code != 200:
                    error = f"HTTP {resp.status_code}: {body}"
            except Exception as exc:
                error = str(exc)
            latency = int((time.monotonic() - started) * 1000)
            passed, reasons = (False, [error]) if error else evaluate(case, body)
            slots_ok, slot_reasons = (False, [error]) if error else check_slots(
                body, case["expect_slots"])
            results.append({
                **case, "passed": passed, "reasons": reasons,
                "status": body.get("status", ""),
                "answer": body.get("answer", ""),
                "tools": [s.get("tool_name") for s in body.get("steps", [])],
                "approvals": len(body.get("approvals", [])),
                "approval_statuses": [a.get("status") for a in body.get("approvals", [])],
                "latency_ms": latency,
                "run_id": body.get("run_id"),
                "cost": float(body.get("cost", 0) or 0),
                "parser": (body.get("evidence") or {}).get("parser", ""),
                "amount_consistent": amount_consistent(case, body),
                "slots_ok": slots_ok,
                "slot_reasons": slot_reasons,
            })
            mark = "PASS" if passed else "FAIL"
            print(f"[{mark}] {case['id']} {case['split']} {case['category']} {latency}ms")
        bills_after = bill_total()

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    latencies = [r["latency_ms"] for r in results]

    def rate(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    tool_cases = [r for r in results if r["expect_any_tools"]]
    tool_ok = sum(1 for r in tool_cases
                  if any(t in r["tools"] for t in r["expect_any_tools"]))
    param_cases = [r for r in results if r["expect_slots"]]
    param_ok = sum(1 for r in param_cases if r["slots_ok"])
    amount_cases = [r for r in results if r["amount_consistent"] is not None]
    amount_ok = sum(1 for r in amount_cases if r["amount_consistent"])
    forbid_cases = [r for r in results if r["forbid_answer_contains"]]
    forbid_hits = sum(1 for r in forbid_cases
                      if any(t in r["answer"] for t in r["forbid_answer_contains"]))
    approval_cases = [r for r in results if r["expect_approval"] is not None]
    approval_ok = sum(1 for r in approval_cases
                      if (r["approvals"] > 0) == r["expect_approval"])
    approved_count = sum(1 for r in results for s in r["approval_statuses"]
                         if s == "approved")
    unauthorized_writes = max(0, bills_after - bills_before) + approved_count

    def group(field: str) -> dict:
        result: dict[str, dict] = {}
        for r in results:
            key = r[field]
            item = result.setdefault(key, {"total": 0, "passed": 0})
            item["total"] += 1
            item["passed"] += 1 if r["passed"] else 0
        return result

    total_cost = sum(r["cost"] for r in results)
    ai_parser_cases = sum(1 for r in results if r["parser"] == "ai")
    rule_parser_cases = sum(1 for r in results if r["parser"] == "rule")
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "username": args.username,
        "split": args.split,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": rate(passed, total),
        "tool_selection_accuracy": rate(tool_ok, len(tool_cases)),
        "tool_cases": len(tool_cases),
        "parameter_accuracy": rate(param_ok, len(param_cases)),
        "parameter_cases": len(param_cases),
        "amount_consistency_rate": rate(amount_ok, len(amount_cases)),
        "amount_cases": len(amount_cases),
        "forbidden_content_hits": forbid_hits,
        "forbidden_cases": len(forbid_cases),
        "approval_consistency_rate": rate(approval_ok, len(approval_cases)),
        "approval_cases": len(approval_cases),
        "unauthorized_writes": unauthorized_writes,
        "bills_before": bills_before,
        "bills_after": bills_after,
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "p95_latency_ms": percentile(latencies, 95),
        "total_cost": round(total_cost, 4),
        "avg_cost": round(total_cost / total, 4) if total else 0,
        "cost_note": "成本来自后端 agent_runs.cost 的估算值，不是真实 token 账单。",
        "ai_configured": bool(agent_health.get("ai_configured")),
        "model": agent_health.get("model", ""),
        "ai_parser_cases": ai_parser_cases,
        "rule_parser_cases": rule_parser_cases,
        "by_category": group("category"),
        "by_split": group("split"),
        "results": results,
    }

    suffix = "" if args.split == "all" else f"_{args.split}"
    (OUT_DIR / f"report{suffix}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Agent 评测报告（团队自测）",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 后端：{report['base_url']}",
        f"- 账号：{report['username']}",
        f"- 数据集：{args.split}（dev/test 为预设划分；仍为团队自测，不是第三方认证）",
        f"- 用例：{total}，通过：{passed}，失败：{total - passed}，"
        f"成功率：{report['pass_rate'] * 100:.1f}%",
        f"- 工具选择准确率：{report['tool_selection_accuracy'] * 100:.1f}%"
        f"（{tool_ok}/{len(tool_cases)}）",
        f"- 参数准确率：{report['parameter_accuracy'] * 100:.1f}%"
        f"（{param_ok}/{len(param_cases)}）",
        f"- 金额一致性：{report['amount_consistency_rate'] * 100:.1f}%"
        f"（{amount_ok}/{len(amount_cases)}，启发式）",
        f"- 审批一致性：{report['approval_consistency_rate'] * 100:.1f}%"
        f"（{approval_ok}/{len(approval_cases)}）",
        f"- 禁止内容命中：{forbid_hits} 次 / {len(forbid_cases)} 条安全用例",
        f"- 未审批写入：{unauthorized_writes}（账单变化 {bills_after - bills_before}，"
        f"已批准动作 {approved_count}）",
        f"- 平均延迟：{report['avg_latency_ms']}ms，P95：{report['p95_latency_ms']}ms",
        f"- 成本：¥{report['total_cost']:.4f}（平均 ¥{report['avg_cost']:.4f}/任务；估算值）",
        f"- 记账解析：模型 {ai_parser_cases} 条 / 规则降级 {rule_parser_cases} 条"
        f"（AI 配置：{'是' if report['ai_configured'] else '否'}，模型：{report['model'] or '未配置'}）",
        "",
        "## 分类通过率",
        "",
        "| 类别 | 通过/总数 | 通过率 |",
        "|---|---|---|",
    ]
    for name, item in report["by_category"].items():
        lines.append(f"| {name} | {item['passed']}/{item['total']} | "
                     f"{item['passed'] / item['total'] * 100:.1f}% |")
    lines += ["", "## 数据集通过率", "", "| 数据集 | 通过/总数 | 通过率 |", "|---|---|---|"]
    for name, item in report["by_split"].items():
        lines.append(f"| {name} | {item['passed']}/{item['total']} | "
                     f"{item['passed'] / item['total'] * 100:.1f}% |")
    lines += ["", "## 失败用例", ""]
    failures = [r for r in results if not r["passed"]]
    if not failures:
        lines.append("无。")
    else:
        lines += ["| 编号 | 数据集 | 输入 | 状态 | 原因 |", "|---|---|---|---|---|"]
        for r in failures:
            reason = "；".join(r["reasons"])[:300]
            lines.append(f"| {r['id']} | {r['split']} | {r['message']} | "
                         f"{r['status']} | {reason} |")
    lines += [
        "",
        ("**注意**：本次运行模型解析 0 条，记账解析走规则降级（可能触发每日 AI 配额）；"
         "模型路径未在本次结果中覆盖，需在配额恢复后重跑。" if ai_parser_cases == 0 and report["ai_configured"] else ""),
        "",
        "## 指标口径与局限",
        "",
        "- 任务成功率：状态、工具、关键文本、审批存在性与参数槽位全部满足才算通过。",
        "- 数字幻觉率未做严格逐字段对照；本报告用“金额一致性 + 禁止内容命中”做启发式检查。",
        "- 审批、撤销、并发、数据库回查等严格断言见 `tests/agent_eval/run_flow_eval.py`。",
        "- 模型解析有波动，换模型/提示词后需重新跑基线；不能把本报告当作第三方认证。",
        "",
        "## 复现",
        "",
        "```bash",
        "python tools/seed_demo.py",
        "python tests/agent_eval/run_eval.py --split all",
        "python tests/agent_eval/run_flow_eval.py",
        "```",
    ]
    (OUT_DIR / f"report{suffix}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n完成：{passed}/{total} 通过，报告已写入 {OUT_DIR / f'report{suffix}.md'}")
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
