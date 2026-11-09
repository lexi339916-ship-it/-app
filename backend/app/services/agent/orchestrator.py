"""Agent 编排器：意图路由 + 多步工具调用 + 审批执行。

设计取舍（时间紧、可演示优先）：
- 账单自然语言解析优先用大模型，失败自动降级为规则解析；
- 预算/订阅/目标场景用确定性 SQL 计算，模型只负责表达，避免数字幻觉；
- 所有写操作先出 diff，用户批准后才执行；执行后写审计与撤销记录；
- 不保存模型原始思维链，只保存可验证的工具/审批轨迹。
"""
import calendar
import copy
import re
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app import config, version
from app.models import (
    AgentApproval, AgentMemory, AgentNotification, AgentRun, AgentStep, Bill, BillCategory,
    CategoryBudget, Note, SavingsGoal, Subscription, User,
)
from app.services import ai_service
from app.services.ai_service import AIServiceError, build_parse_bill_messages
from app.services import health_service, asset_service, decision_simulator
from app.services.agent import policy, tools, trace

VERSION = version.APP_VERSION
MAX_STEPS = 8


# ---------------- 对外入口 ----------------

async def run_agent(db: Session, user: User, message: str, mode: str = "auto",
                    session_id: str | None = None,
                    parent_run_id: int | None = None) -> dict:
    start = time.monotonic()
    # 敏感数字先脱敏，避免密码/验证码被当成金额或写入轨迹
    safe_message = ai_service.mask_sensitive(message)
    session_id = (session_id or uuid.uuid4().hex)[:64]
    last_run = _load_session_context(db, user, session_id, parent_run_id)
    run = trace.create_run(
        db, user.id, safe_message, mode, session_id=session_id,
        parent_run_id=last_run.id if last_run else None)
    try:
        if last_run is not None and _looks_like_followup(safe_message):
            trace.set_plan(db, run, [
                "读取上一轮目标与审批方案", "解析你的修改要求",
                "重新计算预算/目标影响", "生成新的待审批方案",
            ])
            trace.add_step(db, run, "plan", "load_session_context",
                           {"session_id": session_id, "parent_run_id": last_run.id},
                           {"last_goal": last_run.goal, "last_status": last_run.status})
            _run_followup(db, user, safe_message, run, start, last_run)
            return trace.serialize_run(db, run)

        intent = _detect_intent(safe_message, mode)
        trace.add_step(db, run, "plan", "intent_router",
                       {"message": safe_message, "mode": mode}, {"intent": intent})
        if intent == "bill":
            await _run_bill(db, user, safe_message, run, start)
        elif intent == "subscription":
            _run_subscription(db, user, safe_message, run, start)
        elif intent == "goal":
            _run_goal(db, user, safe_message, run, start)
        elif intent == "asset":
            _run_asset(db, user, safe_message, run, start)
        elif intent == "simulate":
            _run_simulate(db, user, safe_message, run, start)
        elif intent == "health":
            _run_health(db, user, safe_message, run, start)
        elif intent == "chat":
            _run_chat(db, user, safe_message, run, start)
        else:
            _run_query(db, user, safe_message, run, start)
    except policy.PolicyError as exc:
        trace.add_step(db, run, "policy", "policy_check", {}, {"error": str(exc)},
                       status="error", error=str(exc))
        trace.finish_run(db, run, "failed", f"这个操作没有通过安全校验：{exc}",
                         evidence={"model": config.AI_MODEL or "rule"},
                         latency_ms=_elapsed(start))
    except AIServiceError as exc:
        trace.add_step(db, run, "error", "ai_service", {}, {"message": exc.message},
                       status="error", error=exc.message)
        trace.finish_run(db, run, "failed", exc.message,
                         evidence={"model": config.AI_MODEL or "rule"},
                         latency_ms=_elapsed(start))
    except Exception as exc:  # 兜底：不把内部堆栈暴露给用户
        trace.add_step(db, run, "error", "orchestrator", {}, {"message": str(exc)},
                       status="error", error=str(exc))
        trace.finish_run(db, run, "failed", "处理过程中出现异常，请稍后重试或手动操作。",
                         evidence={"model": config.AI_MODEL or "rule"},
                         latency_ms=_elapsed(start))
    return trace.serialize_run(db, run)


def _detect_intent(message: str, mode: str) -> str:
    if mode == "query":
        return "query"
    if mode == "plan":
        return "goal"
    if mode == "action":
        return "bill"
    text = message.lower()
    # 简单问候/身份/感谢：不进入业务查询，也不调用模型编数字
    chat_markers = ("你好", "您好", "嗨", "hi", "hello", "你是谁", "你叫什么",
                    "你能做什么", "你能帮我做什么", "介绍一下你自己", "介绍一下自己",
                    "谢谢", "感谢", "怎么用")
    business_words = ("账单", "消费", "预算", "订阅", "目标", "资产", "负债",
                      "记账", "记一笔", "花了", "花钱", "存", "攒", "买", "查",
                      "余额", "收入", "支出", "账户", "健康", "模拟",
                      "午饭", "晚饭", "早饭", "打车", "工资", "退款", "元", "块")
    if (len(text) <= 30 and any(k in text for k in chat_markers)
            and not any(k in text for k in business_words)):
        return "chat"
    # 购买模拟必须先于记账/目标：用户问的是“如果买”，不是“已经买了”
    if re.search(r"(如果|假如).{0,16}(买|购买|换|入手)|"
                 r"(会影响|影响).{0,12}(目标|预算|储蓄)|买了?会", text):
        return "simulate"
    # 明确的记账动作 + 金额优先，避免“信用卡消费 300”被资产查询截走
    if any(k in text for k in ("记账", "记一笔", "花了", "付了", "买了", "收到",
                               "工资", "还款")) and re.search(
            r"\d+(?:\.\d+)?\s*(元|块|万|千)|[零一二两三四五六七八九十百千万]+\s*(元|块|万|千)",
            text):
        return "bill"
    # 消费健康诊断：只读报告，不进入记账/资产查询
    if any(k in text for k in ("健康诊断", "消费健康", "健康分", "健康报告", "诊断一下消费")):
        return "health"
    # 资产/负债查询：排除“预算余额”等预算问题
    if "预算" not in text and any(k in text for k in (
            "资产", "净资产", "负债", "欠款", "信用卡", "房贷", "车贷", "房产",
            "存款", "余额", "理财", "基金", "账户", "还款", "转账")):
        return "asset"
    # 明确的“查看/查询”措辞优先，避免“几个订阅”“目标进度”被当成行动任务
    if any(k in text for k in ("几个", "多少个", "哪些", "进度", "列表", "查看",
                               "最贵", "最大")):
        return "query"
    if any(k in text for k in ("订阅", "会员", "续费", "涨价", "自动扣费",
                               "重复扣款", "固定支出", "扣款")):
        return "subscription"
    if any(k in text for k in ("存", "攒", "目标", "旅行", "买房", "买电脑",
                               "计划", "规划", "电脑")):
        return "goal"
    if any(k in text for k in ("多少", "哪里", "排行", "统计", "对比", "占比", "情况", "分析")):
        return "query"
    if any(k in text for k in ("记账", "记一笔", "花了", "付了", "买了", "收到",
                               "工资", "退款", "消费", "午饭", "晚饭", "早饭",
                               "打车", "充", "交", "买")):
        return "bill"
    if re.search(r"\d+(?:\.\d+)?\s*(元|块|万|千)", text):
        return "bill"
    # 中文数字金额：咖啡十五块五、停车费五块、话费一百零二
    if re.search(r"[零一二两三四五六七八九十百千万]+\s*(元|块|万|千)", text):
        return "bill"
    return "query"


def _elapsed(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


# ---------------- 记忆 ----------------

def _load_memories(db: Session, user: User) -> dict[str, dict[str, dict]]:
    """按 kind -> key -> value 读取当前用户记忆。"""
    rows = db.scalars(select(AgentMemory).where(AgentMemory.user_id == user.id)).all()
    result: dict[str, dict[str, dict]] = {}
    for row in rows:
        result.setdefault(row.kind, {})[row.mem_key] = trace.loads(row.value_json, {})
    return result


def _match_merchant_memory(memory: dict[str, dict[str, dict]], text: str) -> dict | None:
    """用“上次商户→分类”纠正本次分类（只匹配记忆键出现在文本中的情况）。"""
    for key, value in (memory.get("merchant_category") or {}).items():
        if key and key in text and value.get("category"):
            return {"key": key, "category": value["category"]}
    return None


# ---------------- 场景 1：记账 ----------------

async def _run_bill(db: Session, user: User, message: str, run: AgentRun,
                    start: float) -> None:
    trace.set_plan(db, run, [
        "理解记账意图", "解析金额/分类/日期/渠道", "查询本月预算",
        "评估记账后的预算影响", "生成待审批动作",
    ])
    expense_cats = [c.name for c in tools.visible_categories(db, user, "expense")]
    income_cats = [c.name for c in tools.visible_categories(db, user, "income")]
    all_cats = expense_cats + [c for c in income_cats if c not in expense_cats]

    drafts, parser, ai_latency = await _parse_bill(db, user, message, all_cats)
    trace.add_step(db, run, "tool", "parse_bill", {"text": message, "count": len(drafts)},
                   {"drafts": drafts})
    valid = [d for d in drafts if d.get("amount") is not None]
    if not valid:
        trace.add_step(db, run, "clarify", "request_missing_slot",
                       {"missing": ["amount"]}, {"question": "这笔消费多少钱？"},
                       status="wait")
        trace.finish_run(db, run, "needs_input",
                         "我还没听清金额。可以说“午饭三十二”或直接输入金额。",
                         evidence={"model": config.AI_MODEL or "rule", "parser": parser},
                         latency_ms=_elapsed(start))
        return

    memory = _load_memories(db, user)
    prepared: list[dict] = []
    memory_used = None
    for raw in valid[:5]:
        amount = tools.q2(raw["amount"])
        type_ = raw.get("type") if raw.get("type") in ("income", "expense") else "expense"
        category = raw.get("category") or "其他"
        if type_ == "expense" and category not in expense_cats:
            category = tools.guess_category(message, expense_cats)
        if type_ == "income" and category not in income_cats:
            category = "其他收入" if "其他收入" in income_cats else (income_cats[0] if income_cats else "其他")
        remark = (raw.get("remark") or "").strip()
        if len(remark) < 4 or remark in ("微信付的", "支付宝", "微信支付", "付了"):
            remark = message.strip()
        remark = remark[:200]
        if type_ == "expense":
            hit = _match_merchant_memory(memory, remark + " " + message)
            if hit and (category in ("其他", "") or category not in expense_cats):
                category = hit["category"]
                memory_used = hit
        prepared.append({
            "type": type_, "amount": amount, "category": category,
            "bill_date": _safe_date(raw.get("bill_date")),
            "remark": remark, "pay_channel": _infer_channel(message),
            "funding_account": "",
        })

    primary = prepared[0]
    total_amount = tools.q2(sum((p["amount"] for p in prepared), Decimal("0")))
    month = tools.current_month()
    overview = tools.budget_overview(db, user, month)
    trace.add_step(db, run, "tool", "get_budget_status", {"month": month},
                   {"total_budget": overview["total_budget"],
                    "total_spent": overview["total_spent"],
                    "items": [i for i in overview["items"] if i["amount"] > 0][:8]})
    category_item = next((i for i in overview["items"]
                          if i["category"] == primary["category"]), None)

    actions: list[dict] = [{
        "action": "create_bill",
        "bill": {
            "type": p["type"], "amount": str(p["amount"]), "category": p["category"],
            "bill_date": p["bill_date"].isoformat(), "remark": p["remark"],
            "pay_channel": p["pay_channel"], "funding_account": "",
        },
    } for p in prepared]
    impact: dict = {
        "amount": str(primary["amount"]), "category": primary["category"],
        "month": month, "parser": parser, "bills_count": len(prepared),
        "total_amount": str(total_amount),
        "bills": [{"amount": str(p["amount"]), "category": p["category"]} for p in prepared],
    }
    if memory_used:
        impact["memory_used"] = memory_used
    if len(prepared) == 1:
        answer = (f"识别为{('收入' if primary['type'] == 'income' else '支出')} "
                  f"¥{primary['amount']}，分类「{primary['category']}」。")
    else:
        answer = (f"识别到 {len(prepared)} 笔，共 ¥{total_amount}："
                  + "；".join(f"{p['category']} ¥{p['amount']}" for p in prepared) + "。")
    if memory_used:
        answer += f" 已按你上次的习惯归到「{memory_used['category']}」。"

    # 预算影响：用第一笔的分类做代表；多笔同分类时合并计算
    same_cat = [p for p in prepared
                if p["type"] == "expense" and p["category"] == primary["category"]]
    cat_amount = tools.q2(sum((p["amount"] for p in same_cat), Decimal("0")))
    if primary["type"] == "expense" and category_item and category_item["amount"] > 0:
        after = tools.q2(category_item["spent"] + cat_amount)
        budget = category_item["amount"]
        impact.update({
            "budget": str(budget), "spent_before": str(category_item["spent"]),
            "spent_after": str(after), "remaining_after": str(tools.q2(budget - after)),
        })
        if after > budget:
            shortfall = tools.q2(after - budget)
            surplus = _pick_surplus(overview["items"], primary["category"])
            if surplus is not None:
                move = tools.q2(min(max(shortfall, Decimal("50")),
                                    surplus["remaining"] / 2))
                move = max(Decimal("10"), (move / 10).quantize(Decimal("1")) * 10)
                if move > 0 and surplus["amount"] - move > 0:
                    actions.append({
                        "action": "set_category_budgets", "month": month,
                        "items": [
                            {"category_id": surplus["category_id"],
                             "category_name": surplus["category"],
                             "amount": str(tools.q2(surplus["amount"] - move)),
                             "before": str(surplus["amount"])},
                            {"category_id": category_item["category_id"],
                             "category_name": category_item["category"],
                             "amount": str(tools.q2(budget + move)),
                             "before": str(budget)},
                        ],
                        "reason": f"从「{surplus['category']}」调配 ¥{move} 避免「{primary['category']}」超支",
                    })
                    impact["rebalance"] = {
                        "from": surplus["category"], "to": primary["category"],
                        "amount": str(move),
                    }
            actions.append({
                "action": "create_task",
                "note": {
                    "title": f"本周控制「{primary['category']}」支出",
                    "content": (f"本月「{primary['category']}」已花 ¥{after}，"
                                f"预算 ¥{budget}。本周先暂停非必要消费。"),
                    "note_type": "todo",
                    "due_at": (date.today() + timedelta(days=7)).isoformat() + " 18:00:00",
                    "priority": "high",
                },
            })
            answer += (f" 记账后「{primary['category']}」将超出预算 ¥{shortfall}，"
                       f"我准备了调配和任务方案。")
        elif after >= budget * Decimal("0.8"):
            impact["warning"] = "记账后达到预算 80%"
            answer += (f" 记账后「{primary['category']}」将用到预算的 "
                       f"{round(float(after / budget) * 100)}%。")
        else:
            answer += f" 记账后「{primary['category']}」还剩 ¥{tools.q2(budget - after)}。"
    elif primary["type"] == "expense":
        answer += " 该分类还没有设置预算，建议在预算中心补充。"

    diff = {
        "summary": answer,
        "impact": impact,
        "evidence": {
            "budget_source": "category_budgets+bills",
            "month": month,
            "as_of": datetime.now().isoformat(timespec="seconds"),
        },
        "actions": actions,
        "success_message": (f"已记录 {len(prepared)} 笔账单，共 ¥{total_amount}，"
                            f"并完成相关预算/任务调整。"),
    }
    policy.validate_actions(db, user, actions)
    approval = trace.create_approval(db, run, diff, action_type="bill")
    trace.add_step(db, run, "approval", "approval_required",
                   {"approval_id": approval.id, "actions": len(actions)},
                   {"status": "pending", "approval_id": approval.id}, status="wait")
    trace.finish_run(db, run, "awaiting_approval",
                     answer + " 需要你确认后才会写入。",
                     evidence={"model": config.AI_MODEL or "rule", "parser": parser,
                               "memory_used": memory_used,
                               "as_of": datetime.now().isoformat(timespec="seconds")},
                     cost=0.002 if parser == "ai" else 0.0,
                     latency_ms=_elapsed(start))


async def _parse_bill(db: Session, user: User, message: str,
                      categories: list[str]) -> tuple[list[dict], str, int]:
    """优先模型解析；未配置/超时/格式错误时自动降级为规则解析。

    返回草稿列表，支持一句话里包含多笔消费。
    """
    if _vague_bill_request(message):
        return [], "rule", 0
    if config.AI_BASE_URL and config.AI_API_KEY and config.AI_MODEL:
        try:
            ai_service.check_rate_limit(db, user.id)
            started = time.monotonic()
            data = await ai_service.chat_json(
                build_parse_bill_messages(message, categories),
                retry_hint='只输出 {"bills": [...], "notice": ""} 形式的 JSON 对象。')
            bills = data.get("bills") if isinstance(data, dict) else None
            if isinstance(bills, list) and bills:
                drafts = []
                for raw in bills[:5]:
                    if not isinstance(raw, dict):
                        continue
                    amount = raw.get("amount")
                    drafts.append({
                        "type": raw.get("type") if raw.get("type") in ("income", "expense") else "expense",
                        "amount": str(amount) if amount is not None else None,
                        "category": raw.get("category") or "其他",
                        "bill_date": raw.get("bill_date") or date.today().isoformat(),
                        "remark": (raw.get("remark") or message)[:200],
                        "missing_fields": raw.get("missing_fields") or [],
                    })
                if drafts:
                    latency = int((time.monotonic() - started) * 1000)
                    ai_service.log_call(db, user_id=user.id, feature="agent_parse_bill",
                                        status="success", latency_ms=latency,
                                        input_chars=len(message))
                    return drafts, "ai", latency
        except AIServiceError as exc:
            try:
                ai_service.log_call(db, user_id=user.id, feature="agent_parse_bill",
                                    status="error", latency_ms=0,
                                    input_chars=len(message), error_msg=exc.message)
            except Exception:
                pass
        except Exception:
            pass
    return [tools.parse_bill_fallback(message, categories)], "rule", 0


def _vague_bill_request(message: str) -> bool:
    """“帮我记一笔”这类没有金额/单位的请求，不要被模型解析成 1 元。"""
    cleaned = message.replace("一笔", "").replace("一下", "").replace("一起", "")
    return not re.search(r"\d", cleaned) and not re.search(
        r"[零一二两三四五六七八九十百千万元块]", cleaned)


def _safe_date(value) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return date.today()


def _add_months(day: date, months: int) -> date:
    year = day.year + (day.month - 1 + months) // 12
    month = (day.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def _infer_channel(text: str) -> str:
    for name in ("微信", "支付宝", "银行卡", "云闪付", "现金"):
        if name in text:
            return name
    return ""


def _pick_surplus(items: list[dict], exclude_category: str) -> dict | None:
    candidates = [i for i in items
                  if i["category"] != exclude_category and i["status"] == "ok"
                  and i["remaining"] >= Decimal("50")]
    if not candidates:
        return None
    return max(candidates, key=lambda i: i["remaining"])


# ---------------- 场景 2：订阅体检 ----------------

def _run_subscription(db: Session, user: User, message: str, run: AgentRun,
                      start: float) -> None:
    trace.set_plan(db, run, [
        "扫描订阅与本月扣费", "识别涨价/低频/重复扣款",
        "估算年化影响", "生成待审批动作",
    ])
    subs = tools.list_subscriptions(db, user.id)
    trace.add_step(db, run, "tool", "get_subscriptions", {},
                   {"count": len(subs), "items": subs})
    issues = tools.subscription_issues(db, user.id)
    trace.add_step(db, run, "tool", "detect_subscription_issues", {},
                   {"count": len(issues), "items": issues})
    if not issues:
        trace.finish_run(db, run, "completed",
                         "我检查了你的订阅，暂时没有发现涨价、低频或重复扣款。",
                         evidence={"as_of": datetime.now().isoformat(timespec="seconds")},
                         latency_ms=_elapsed(start))
        return

    primary = issues[0]
    actions: list[dict] = []
    if primary["kind"] in ("price_up", "low_usage", "price_up_low_usage"):
        actions.append({
            "action": "pause_subscription",
            "subscription_id": primary["subscription_id"],
            "subscription_name": primary["name"],
            "reason": primary["message"],
        })
        actions.append({
            "action": "create_task",
            "note": {
                "title": f"月底复盘「{primary['name']}」是否恢复",
                "content": f"{primary['message']}。先暂停一个月，月底按实际使用情况决定是否恢复。",
                "note_type": "todo",
                "due_at": (date.today() + timedelta(days=30)).isoformat() + " 18:00:00",
                "priority": "medium",
            },
        })
        alternative = {
            "action": "create_task",
            "note": {
                "title": f"先观察「{primary['name']}」一个月",
                "content": f"暂不暂停。记录本月实际使用次数，月底再决定。{primary['message']}",
                "note_type": "todo",
                "due_at": (date.today() + timedelta(days=30)).isoformat() + " 18:00:00",
                "priority": "medium",
            },
            "label": "先不暂停，观察一个月",
        }
    else:
        actions.append({
            "action": "create_task",
            "note": {
                "title": "核对重复扣款",
                "content": f"{primary['message']}。建议核对账单并联系客服。",
                "note_type": "todo",
                "due_at": (date.today() + timedelta(days=2)).isoformat() + " 18:00:00",
                "priority": "high",
            },
        })
        alternative = None

    total_annual = sum((Decimal(str(i.get("annual_impact") or 0)) for i in issues), Decimal("0"))
    answer = (f"发现 {len(issues)} 个订阅异常，合计年化影响 ¥{tools.q2(total_annual)}。"
              f"最值得注意的是：{primary['message']}。")
    diff = {
        "summary": answer,
        "impact": {"issues": issues, "annual_impact_total": str(tools.q2(total_annual))},
        "evidence": {"source": "subscriptions+bills",
                     "as_of": datetime.now().isoformat(timespec="seconds")},
        "actions": actions,
        "alternatives": [alternative] if alternative else [],
        "success_message": f"已按你的选择处理「{primary['name']}」，并创建了复盘任务。",
    }
    policy.validate_actions(db, user, actions)
    approval = trace.create_approval(db, run, diff, action_type="subscription")
    trace.add_step(db, run, "approval", "approval_required",
                   {"approval_id": approval.id, "actions": len(actions)},
                   {"status": "pending", "approval_id": approval.id}, status="wait")
    trace.finish_run(db, run, "awaiting_approval",
                     answer + " 要暂停还是先观察一个月？",
                     evidence={"model": "rule", "as_of": datetime.now().isoformat(timespec="seconds")},
                     latency_ms=_elapsed(start))


# ---------------- 场景 3：目标规划 ----------------

def _run_goal(db: Session, user: User, message: str, run: AgentRun,
              start: float) -> None:
    trace.set_plan(db, run, [
        "解析目标金额与周期", "查询近 3 个月收支与分类均值",
        "判断可行性并拆解月度预算", "生成目标/预算/复盘任务",
    ])
    parsed = tools.parse_goal(message)
    trace.add_step(db, run, "tool", "parse_goal", {"text": message}, parsed)
    memory = _load_memories(db, user)
    existing_goal = (memory.get("goal") or {}).get("active_goal") or {}
    memory_used = None
    if not parsed["amount"] and not parsed.get("monthly_amount") and existing_goal:
        try:
            target = tools.q2(existing_goal.get("target_amount") or 0)
        except Exception:
            target = Decimal("0")
        if target > 0:
            parsed["amount"] = target
            parsed["name"] = existing_goal.get("name") or parsed["name"]
            parsed["months"] = parsed.get("months") or existing_goal.get("target_months")
            parsed["missing"] = ["months"] if not parsed["months"] else []
            memory_used = {"goal": existing_goal}
    if parsed["amount"] is None and parsed.get("monthly_amount") is not None and parsed.get("months"):
        parsed["amount"] = tools.q2(parsed["monthly_amount"] * parsed["months"])
        parsed["missing"] = []
    if parsed.get("missing"):
        missing = parsed["missing"]
        question = "想存多少钱？" if "target_amount" in missing else "准备存几个月？"
        answer = ("还差一个目标金额。可以说“3 个月存 3000 元去旅行”。"
                  if "target_amount" in missing
                  else "还差一个目标周期。可以说“3 个月”或“半年”。")
        trace.add_step(db, run, "clarify", "request_missing_slot",
                       {"missing": missing}, {"question": question},
                       status="wait")
        trace.finish_run(db, run, "needs_input", answer,
                         evidence={"model": "rule", "memory_used": memory_used},
                         latency_ms=_elapsed(start))
        return

    target = tools.q2(parsed["amount"])
    months = int(parsed["months"] or 1)
    target_date = _add_months(date.today(), months)
    monthly_target = tools.q2(target / months)
    avg_net = tools.avg_monthly_net(db, user.id, 3)
    overview = tools.budget_overview(db, user, tools.current_month())
    category_avg = tools.category_monthly_average(db, user.id, 3)
    trace.add_step(db, run, "tool", "get_cashflow",
                   {"months": 3}, {"avg_monthly_net": str(avg_net),
                                   "monthly_target": str(monthly_target)})
    trace.add_step(db, run, "tool", "get_budget_status",
                   {"month": tools.current_month()},
                   {"items": [i for i in overview["items"] if i["amount"] > 0][:8]})
    asset_overview = asset_service.overview(db, user)
    asset_context: dict = {}
    if asset_overview.has_data:
        asset_context = {
            "liquid_assets": str(asset_overview.liquid_assets),
            "fixed_assets": str(asset_overview.fixed_assets),
            "total_liabilities": str(asset_overview.total_liabilities),
            "net_worth": str(asset_overview.net_worth),
        }
        trace.add_step(db, run, "tool", "get_asset_overview", {}, asset_context)

    feasible = avg_net >= monthly_target
    actions: list[dict] = [{
        "action": "create_goal",
        "goal": {"name": parsed["name"], "target_amount": str(target),
                 "target_months": months, "target_date": target_date.isoformat()},
    }]
    adjustments = _build_goal_budget_adjustments(category_avg, monthly_target, overview)
    if adjustments:
        actions.append({
            "action": "set_category_budgets", "month": tools.current_month(),
            "items": adjustments,
            "reason": "把可自由支配的分类压一压，给储蓄目标腾出空间",
        })
    actions.append({
        "action": "create_task",
        "note": {
            "title": f"每周复盘「{parsed['name']}」进度",
            "content": f"目标 {months} 个月存 ¥{target}，每月需要 ¥{monthly_target}。每周日核对本周支出与储蓄进度。",
            "note_type": "todo",
            "due_at": (date.today() + timedelta(days=7)).isoformat() + " 18:00:00",
            "priority": "high",
        },
    })

    if feasible:
        answer = (f"目标「{parsed['name']}」需要 {months} 个月存 ¥{target}"
                  f"（每月 ¥{monthly_target}）；你近 3 个月平均结余 ¥{avg_net}，可行。")
    else:
        need_months = max(1, int((target / avg_net).to_integral_value()) + 1) if avg_net > 0 else None
        answer = (f"目标「{parsed['name']}」需要 {months} 个月存 ¥{target}"
                  f"（每月 ¥{monthly_target}），但你近 3 个月平均结余 ¥{avg_net}，压力较大。")
        if need_months:
            answer += f" 按当前结余，约需 {need_months} 个月；也可以把目标降到 ¥{tools.q2(avg_net * months)}。"
    if memory_used:
        answer += f" 我已沿用你上次的目标「{memory_used['goal'].get('name', parsed['name'])}」。"
    if adjustments:
        cut_total = sum((Decimal(str(i.get("before") or 0)) - Decimal(str(i["amount"]))
                         for i in adjustments), Decimal("0"))
        answer += (f" 先压缩约 ¥{tools.q2(cut_total)} 的可自由支配预算，"
                   f"剩余靠每月结余补齐，并创建每周复盘任务。")
    if asset_context:
        answer += (f" 你目前可动用资产 ¥{asset_context['liquid_assets']}，"
                   f"净资产 ¥{asset_context['net_worth']}；规划时建议至少保留 1 个月应急金。"
                   "固定资产不会自动计入目标已存金额。")
    diff = {
        "summary": answer,
        "impact": {
            "target": str(target), "months": months,
            "target_date": target_date.isoformat(),
            "monthly_target": str(monthly_target),
            "avg_monthly_net": str(avg_net), "feasible": feasible,
            "budget_adjustments": len(adjustments),
            "memory_used": memory_used,
            "assets": asset_context,
        },
        "evidence": {"source": "bills+category_budgets+assets",
                     "memory_used": memory_used,
                     "as_of": datetime.now().isoformat(timespec="seconds")},
        "actions": actions,
        "success_message": f"已创建「{parsed['name']}」目标，并写入预算与每周复盘任务。",
    }
    policy.validate_actions(db, user, actions)
    approval = trace.create_approval(db, run, diff, action_type="goal")
    trace.add_step(db, run, "approval", "approval_required",
                   {"approval_id": approval.id, "actions": len(actions)},
                   {"status": "pending", "approval_id": approval.id}, status="wait")
    trace.finish_run(db, run, "awaiting_approval",
                     answer + " 确认后我会写入目标、预算和任务。",
                     evidence={"model": "rule", "as_of": datetime.now().isoformat(timespec="seconds")},
                     latency_ms=_elapsed(start))


def _build_goal_budget_adjustments(category_avg: list[dict], monthly_target: Decimal,
                                  overview: dict) -> list[dict]:
    """从娱乐/购物/餐饮等可自由支配分类中压缩出月度储蓄额。"""
    if monthly_target <= 0 or not category_avg:
        return []
    discretionary = {"娱乐", "购物", "餐饮"}
    current = {i["category_id"]: i for i in overview["items"]}
    remaining_to_cut = monthly_target
    adjustments = []
    for item in category_avg:
        if item["category"] not in discretionary:
            continue
        if remaining_to_cut <= 0:
            break
        avg = item["monthly_avg"]
        if avg <= 0:
            continue
        cut = min(tools.q2(avg * Decimal("0.25")), remaining_to_cut)
        cut = max(Decimal("10"), (cut / 10).quantize(Decimal("1")) * 10)
        if cut <= 0:
            continue
        before = current.get(item["category_id"])
        new_amount = tools.q2(max(Decimal("0"), avg - cut))
        if before and before["amount"] > 0:
            new_amount = tools.q2(max(Decimal("0"), before["amount"] - cut))
        adjustments.append({
            "category_id": item["category_id"], "category_name": item["category"],
            "amount": str(new_amount),
            "before": str(before["amount"]) if before else None,
        })
        remaining_to_cut = tools.q2(remaining_to_cut - cut)
    return adjustments


# ---------------- 查询场景 ----------------

def _run_asset(db: Session, user: User, message: str, run: AgentRun,
               start: float) -> None:
    """只读资产查询：资产总览、负债、净资产变化；不自动转账/还款。"""
    text = message.lower()
    wants_change = any(k in text for k in ("为什么", "变化", "减少", "增加", "原因"))
    wants_action = any(k in text for k in ("转账", "还款")) and not wants_change
    if wants_action and not any(k in text for k in ("多少", "查询", "查看", "哪些")):
        trace.set_plan(db, run, ["识别资产操作", "检查安全边界"])
        trace.add_step(db, run, "policy", "asset_write_boundary",
                       {"message": message},
                       {"hint": "资产转账/还款需在资产管理页手动确认"})
        answer = ("资产转账和还款涉及真实余额变动，Agent 不会自动执行。"
                  "请到「我的 → 个人资产管理」操作；我可以在你操作后帮你分析净资产变化。")
        trace.finish_run(db, run, "completed", answer,
                         evidence={"source": "asset_policy",
                                   "intent": "asset_action",
                                   "as_of": datetime.now().isoformat(timespec="seconds")},
                         latency_ms=_elapsed(start))
        return

    if wants_change:
        trace.set_plan(db, run, [
            "读取本月资产流水", "拆分消费/收入/转账/负债/手动调整",
            "计算账单关联覆盖率", "解释净资产变化",
        ])
        analysis = asset_service.change_analysis(db, user)
        data = analysis.model_dump(mode="json")
        trace.add_step(db, run, "tool", "get_net_worth_change",
                       {"month": analysis.month}, data)
        answer = analysis.message
        if analysis.has_data and analysis.net_worth_change >= 0:
            answer = ("从账本看，本月净资产没有减少，实际变动为 "
                      f"+¥{analysis.net_worth_change}。" + answer)
        elif analysis.has_data:
            answer = (f"本月净资产减少了 ¥{abs(analysis.net_worth_change)}。" + answer)
        if analysis.has_data and analysis.coverage_ratio < 1:
            answer += (f" 当前有 {round(analysis.coverage_ratio * 100)}% 的支出已关联账户；"
                       "未关联部分不会改变账户余额，分析时已单独标注。")
        trace.finish_run(
            db, run, "completed", answer,
            evidence={
                "source": "asset_accounts+asset_liabilities+asset_transactions+bills",
                "intent": "asset_change", "as_of": analysis.as_of.isoformat(),
                "cards": [{"type": "net_worth_change", "data": data}],
            },
            latency_ms=_elapsed(start))
        return

    trace.set_plan(db, run, [
        "读取资产账户与负债", "计算总资产/可动用资产/总负债/净资产",
        "生成资产概览",
    ])
    overview = asset_service.overview(db, user)
    data = overview.model_dump(mode="json")
    trace.add_step(db, run, "tool", "get_asset_overview", {}, data)
    if not overview.has_data:
        answer = ("你还没有维护资产账户。可以到「我的 → 个人资产管理」添加银行卡、微信零钱、"
                  "房产、车辆或理财产品，我再帮你计算净资产和变化。")
    else:
        answer = (f"你当前总资产 ¥{overview.total_assets}，其中可动用 "
                  f"¥{overview.liquid_assets}、固定资产 ¥{overview.fixed_assets}；"
                  f"总负债 ¥{overview.total_liabilities}，净资产 ¥{overview.net_worth}。")
        if overview.accounts:
            answer += " 账户：" + "、".join(
                f"{a.name} ¥{a.balance}" for a in overview.accounts[:4]) + "。"
        if overview.liabilities:
            answer += " 负债：" + "、".join(
                f"{l.name} ¥{l.outstanding}" for l in overview.liabilities[:3]) + "。"
    trace.finish_run(
        db, run, "completed", answer,
        evidence={
            "source": "asset_accounts+asset_liabilities",
            "intent": "asset_overview", "as_of": data.get("as_of"),
            "cards": [{
                "type": "asset_overview" if overview.has_data else "asset_empty",
                "data": data,
            }],
        },
        latency_ms=_elapsed(start))


def _run_simulate(db: Session, user: User, message: str, run: AgentRun,
                  start: float) -> None:
    """购买决策模拟：复用 decision_simulator，加入可动用资产/净资产视角。"""
    trace.set_plan(db, run, [
        "解析购买金额与分类", "读取预算/目标/资产", "测算购买影响",
        "生成可执行建议",
    ])
    cats = [c.name for c in tools.visible_categories(db, user, "expense")]
    draft = tools.parse_bill_fallback(message, cats)
    amount = draft.get("amount")
    trace.add_step(db, run, "tool", "parse_purchase", {"text": message},
                   {"amount": str(amount) if amount is not None else None,
                    "category": draft.get("category")})
    if amount is None:
        trace.add_step(db, run, "clarify", "request_missing_slot",
                       {"missing": ["amount"]},
                       {"question": "想买的东西大概多少钱？"}, status="wait")
        trace.finish_run(db, run, "needs_input",
                         "这项购买模拟还差一个金额。可以说“如果花 3000 元买手机”。",
                         evidence={"intent": "simulate", "model": "rule",
                                   "as_of": datetime.now().isoformat(timespec="seconds")},
                         latency_ms=_elapsed(start))
        return
    category = draft.get("category") or "购物"
    if category not in cats:
        category = "其他" if "其他" in cats else (cats[0] if cats else "其他")
    result = decision_simulator.simulate(db, user, amount, category)
    trace.add_step(db, run, "tool", "simulate_purchase",
                   {"amount": str(amount), "category": category}, result)
    trace.finish_run(
        db, run, "completed", result["message"],
        evidence={
            "source": "decision_simulator+bills+budgets+goals+assets",
            "intent": "simulate", "as_of": result["as_of"],
            "cards": [{"type": "simulation", "data": result}],
        },
        latency_ms=_elapsed(start))


def _run_chat(db: Session, user: User, message: str, run: AgentRun,
              start: float) -> None:
    """简单问候/身份/感谢：确定性回复，不调用模型、不编造业务数字。"""
    text = message.lower()
    trace.set_plan(db, run, ["识别为日常对话", "返回助手能力与使用提示"])
    if any(k in text for k in ("谢谢", "感谢")):
        answer = ("不客气。需要查消费、看资产、检查订阅或规划储蓄时，直接告诉我就行。")
    elif any(k in text for k in ("你是谁", "你叫什么", "介绍一下", "你能做什么",
                                  "你能帮我做什么", "怎么用")):
        answer = ("我是知账 AI，你的个人消费管理助手。我可以帮你查本月收支、"
                  "分析消费结构、查看资产与负债、检查订阅、规划储蓄目标，"
                  "也可以在购买前做预算/目标影响测算。涉及写入时，我会先给出方案，"
                  "由你审批后才执行。")
    else:
        answer = ("你好，我是知账 AI。你可以直接说“本月消费怎么样”“查看我的资产”"
                  "或“帮我检查订阅”，我会基于你的真实账本和工具数据回答。")
    trace.finish_run(
        db, run, "completed", answer,
        evidence={"intent": "chat", "model": "rule",
                  "as_of": datetime.now().isoformat(timespec="seconds")},
        latency_ms=_elapsed(start))


def _run_health(db: Session, user: User, message: str, run: AgentRun,
                start: float) -> None:
    """消费健康诊断：复用 health_service 的确定性报告，模型不参与打分。"""
    trace.set_plan(db, run, [
        "读取账单、预算、目标与订阅", "计算五项健康指标",
        "生成覆盖率与改善建议",
    ])
    report = health_service.build_report(db, user)
    card_data = {
        "month": report.get("month"),
        "overall_score": report.get("overall_score"),
        "overall_level": report.get("overall_level"),
        "coverage": report.get("coverage"),
        "summary": report.get("summary"),
        "indicators": report.get("indicators", [])[:6],
        "recommendations": report.get("recommendations", [])[:3],
        "as_of": report.get("generated_at") or datetime.now().isoformat(timespec="seconds"),
    }
    trace.add_step(db, run, "tool", "get_health_report", {}, card_data)
    answer = report.get("summary") or "消费健康报告已生成。"
    recommendations = report.get("recommendations") or []
    if recommendations:
        answer += " 优先建议：" + recommendations[0].get("title", "") + "。"
    if (report.get("coverage") or 0) < 0.5:
        answer += " 当前指标覆盖率不足 50%，部分分数暂不计算；先补充账单、预算或目标数据。"
    trace.finish_run(
        db, run, "completed", answer,
        evidence={
            "source": "bills+budgets+goals+subscriptions+health_service",
            "intent": "health", "as_of": card_data["as_of"],
            "cards": [{"type": "health_report", "data": card_data}],
        },
        latency_ms=_elapsed(start))


def _query_month(text: str) -> str:
    """查询月份：支持“上个月/上月”，其余默认当前月。"""
    if "上个月" in text or "上月" in text:
        return _add_months(date.today(), -1).strftime("%Y-%m")
    return tools.current_month()


def _run_query(db: Session, user: User, message: str, run: AgentRun,
               start: float) -> None:
    trace.set_plan(db, run, ["理解查询意图", "选择只读工具", "执行查询", "基于真实数据回答"])
    text = message.lower()
    month = _query_month(text)
    evidence: dict = {"as_of": datetime.now().isoformat(timespec="seconds"),
                      "period": month}
    label = "本月" if month == tools.current_month() else month

    if "订阅" in text or "会员" in text:
        subs = tools.list_subscriptions(db, user.id)
        trace.add_step(db, run, "tool", "get_subscriptions", {}, {"count": len(subs), "items": subs})
        active = [s for s in subs if s["status"] == "active"]
        total = sum((Decimal(str(s["amount"])) for s in active), Decimal("0"))
        answer = f"你有 {len(active)} 个进行中的订阅，每月固定支出 ¥{tools.q2(total)}。"
        if active:
            answer += " " + "；".join(f"{s['name']} ¥{s['amount']}" for s in active[:5]) + "。"
        evidence["source"] = "subscriptions"

    elif "目标" in text or "存钱" in text:
        goals = tools.list_goals(db, user.id)
        trace.add_step(db, run, "tool", "get_goals", {}, {"count": len(goals), "items": goals})
        if goals:
            answer = "你的储蓄目标：" + "；".join(
                f"「{g['name']}」已存 ¥{g['saved_amount']}/¥{g['target_amount']}"
                f"（{round(g['progress_ratio'] * 100)}%）" for g in goals[:4]) + "。"
        else:
            answer = "你还没有储蓄目标。可以说“3 个月存 3000 元去旅行”。"
        evidence["source"] = "savings_goals"

    elif "待办" in text or "任务" in text:
        todos = tools.list_todos(db, user.id)
        trace.add_step(db, run, "tool", "get_todos", {}, {"count": len(todos), "items": todos})
        answer = (f"你有 {len(todos)} 个未完成待办。"
                  + ("最近的是：" + "、".join(t["title"] for t in todos[:5]) + "。"
                     if todos else "暂时没有待办。"))
        evidence["source"] = "notes"

    elif "最大" in text or "最贵" in text:
        row = tools.largest_bill(db, user.id, month)
        trace.add_step(db, run, "tool", "largest_bill", {"month": month}, row or {})
        answer = (f"{label}最大一笔支出是「{row['category']}」¥{row['amount']}（{row['bill_date']}）。"
                  if row else f"{label}还没有支出记录。")
        evidence["source"] = "bills"

    elif "预算" in text or "超支" in text or "额度" in text:
        overview = tools.budget_overview(db, user, month)
        trace.add_step(db, run, "tool", "get_budget_status", {"month": month},
                       {"total_budget": overview["total_budget"],
                        "total_spent": overview["total_spent"],
                        "items": [i for i in overview["items"] if i["amount"] > 0][:8]})
        tight = [i for i in overview["items"]
                 if i["status"] in ("near80", "used_up", "over100")]
        answer = (f"{label}分类预算合计 ¥{overview['total_budget']}，"
                  f"已花 ¥{overview['total_spent']}。")
        if tight:
            answer += " 需要关注：" + "、".join(
                f"{i['category']}已用{round(i['usage_ratio'] * 100)}%" for i in tight[:4]) + "。"
        else:
            answer += " 目前没有接近超支的分类。"
        evidence["source"] = "category_budgets+bills"

    else:
        stats = tools.summarize_month(db, user.id, month)
        trace.add_step(db, run, "tool", "summarize_spending", {"month": month}, stats)
        top = "、".join(f"{c['category']} ¥{c['amount']}" for c in stats["top_categories"][:3])
        answer = (f"{month} 收入 ¥{stats['income']}，支出 ¥{stats['expense']}，"
                  f"结余 ¥{stats['net']}，共 {stats['count']} 笔。")
        if top:
            answer += f" 主要支出：{top}。"
        evidence["source"] = "bills"

    trace.finish_run(db, run, "completed", answer, evidence=evidence,
                     latency_ms=_elapsed(start))


# ---------------- 多轮对话：追问与重规划 ----------------

FOLLOWUP_KEYS = (
    "其他方案", "还有别的", "换个方案", "换一个方案", "再给一个", "重新算",
    "不想动", "别动", "不要动", "保留", "只调整", "只调", "改成", "调成",
    "调整到", "调整为", "选择第", "方案二", "第二个", "就按第", "按第",
)


def _looks_like_followup(message: str) -> bool:
    return any(key in message for key in FOLLOWUP_KEYS)


def _load_session_context(db: Session, user: User, session_id: str,
                          parent_run_id: int | None) -> AgentRun | None:
    """读取上一轮任务；parent_run_id 必须属于当前用户和当前会话。"""
    if parent_run_id:
        row = db.get(AgentRun, parent_run_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(404, "上一轮任务不存在")
        if row.session_id and row.session_id != session_id:
            raise HTTPException(400, "上一轮任务不属于当前会话")
        return row
    return db.scalar(select(AgentRun).where(
        AgentRun.user_id == user.id,
        AgentRun.session_id == session_id,
    ).order_by(AgentRun.turn_index.desc(), AgentRun.id.desc()).limit(1))


def _latest_approval(db: Session, run: AgentRun) -> tuple[AgentApproval | None, dict]:
    row = db.scalar(select(AgentApproval).where(
        AgentApproval.run_id == run.id).order_by(AgentApproval.id.desc()).limit(1))
    return row, trace.loads(row.diff_json, {}) if row else {}


def _followup_kind(message: str) -> str:
    if re.search(r"第?[二2两]个?方案|方案二|选第?[二2两]个?|就按第?[二2两]", message):
        return "choose"
    if any(k in message for k in ("不想动", "别动", "不要动", "保留")):
        return "exclude"
    if any(k in message for k in ("只调整", "只调", "改成", "调成",
                                  "调整到", "调整为")):
        return "adjust"
    return "alternative"


def _extract_category(db: Session, user: User, message: str) -> str | None:
    names = [c.name for c in tools.visible_categories(db, user, "expense")]
    for name in names:
        if name in message:
            return name
    return None


def _extract_adjust_amount(message: str) -> Decimal | None:
    match = re.search(
        r"(?:只调整|只调|改成|调成|调整到|调整为)\s*(\d+(?:\.\d+)?)\s*元?", message)
    if match is None:
        match = re.search(r"(\d+(?:\.\d+)?)\s*元", message)
    if match is None:
        return None
    try:
        value = tools.q2(match.group(1))
    except Exception:
        return None
    return value if value > 0 else None


def _task_only_actions(actions: list[dict]) -> list[dict]:
    """去掉预算调配，只保留记账/目标/任务等动作；没有任务时补一个复盘任务。"""
    result = [copy.deepcopy(a) for a in actions
              if a.get("action") != "set_category_budgets"]
    if not any(a.get("action") == "create_task" for a in result):
        result.append({
            "action": "create_task",
            "note": {
                "title": "复核本次方案",
                "content": "按你的要求先不动预算，记录这次消费并在本周复核是否还超支。",
                "note_type": "todo",
                "due_at": (date.today() + timedelta(days=7)).isoformat() + " 18:00:00",
                "priority": "medium",
            },
        })
    return result


def _rebuild_without_category(db: Session, user: User, actions: list[dict],
                              impact: dict, excluded: str | None) -> tuple[list[dict], dict, str]:
    """用户不想动某个分类：优先换一个结余分类；没有就退化为只记账+任务。"""
    budget_actions = [a for a in actions
                      if a.get("action") == "set_category_budgets"]
    if not budget_actions:
        return copy.deepcopy(actions), copy.deepcopy(impact), "当前方案没有预算调配，不需要改。"

    total_items = sum(len(a.get("items", [])) for a in budget_actions)
    if total_items > 2:
        # 目标规划可能同时压缩多个分类：直接把被保留的分类从方案里拿掉
        new_actions: list[dict] = []
        removed = False
        for action in actions:
            if action.get("action") != "set_category_budgets":
                new_actions.append(copy.deepcopy(action))
                continue
            items = [copy.deepcopy(i) for i in action.get("items", [])
                     if i.get("category_name") != excluded]
            if len(items) != len(action.get("items", [])):
                removed = True
            if items:
                new_actions.append({**copy.deepcopy(action), "items": items})
        if not removed:
            return (copy.deepcopy(actions), copy.deepcopy(impact),
                    f"这个方案本来就没有动「{excluded}」，我保持原方案。")
        new_impact = copy.deepcopy(impact)
        return (new_actions, new_impact,
                f"按你的要求保留「{excluded}」预算，其他可自由支配分类继续压缩。")

    rebalance = impact.get("rebalance") or {}
    source = rebalance.get("from")
    target = rebalance.get("to")
    if not source or not target:
        return copy.deepcopy(actions), copy.deepcopy(impact), "当前方案没有可替换的预算来源。"
    if excluded and excluded != source:
        return (copy.deepcopy(actions), copy.deepcopy(impact),
                f"这个方案本来就没有动「{excluded}」的预算，我保持原方案。")

    overview = tools.budget_overview(db, user, tools.current_month())
    candidates = [i for i in overview["items"]
                  if i["category"] not in (source, target)
                  and i["status"] == "ok" and i["remaining"] >= Decimal("50")]
    if not candidates:
        new_actions = _task_only_actions(actions)
        new_impact = copy.deepcopy(impact)
        new_impact.pop("rebalance", None)
        return (new_actions, new_impact,
                "没有其他可调配的结余分类了，我改为只记录账单并创建控制任务，不动任何预算。")

    new_source = max(candidates, key=lambda i: i["remaining"])
    old_move = Decimal(str(rebalance.get("amount") or 0))
    move = min(old_move, tools.q2(new_source["remaining"] / 2))
    move = max(Decimal("10"), (move / 10).quantize(Decimal("1")) * 10)
    if move <= 0 or new_source["amount"] - move <= 0:
        new_actions = _task_only_actions(actions)
        new_impact = copy.deepcopy(impact)
        new_impact.pop("rebalance", None)
        return (new_actions, new_impact,
                "可调配金额不足，我改为只记录账单并创建控制任务，不动任何预算。")

    target_budget = Decimal(str(impact.get("budget") or 0))
    if target_budget <= 0:
        new_actions = _task_only_actions(actions)
        new_impact = copy.deepcopy(impact)
        new_impact.pop("rebalance", None)
        return (new_actions, new_impact,
                "目标分类还没有预算，我改为只记录账单并创建控制任务。")

    target_item = None
    for action in budget_actions:
        for item in action.get("items", []):
            if item.get("category_name") == target:
                target_item = item
                break
        if target_item:
            break
    if target_item is None:
        return copy.deepcopy(actions), copy.deepcopy(impact), "找不到目标分类预算，保持原方案。"

    new_items = [
        {"category_id": new_source["category_id"], "category_name": new_source["category"],
         "amount": str(tools.q2(new_source["amount"] - move)),
         "before": str(new_source["amount"])},
        {"category_id": target_item["category_id"], "category_name": target,
         "amount": str(tools.q2(target_budget + move)),
         "before": str(target_budget)},
    ]
    new_actions = []
    replaced = False
    for action in actions:
        if action.get("action") == "set_category_budgets" and not replaced:
            new_action = copy.deepcopy(action)
            new_action["items"] = new_items
            new_action["reason"] = (f"按你的要求不动「{source}」，"
                                    f"改从「{new_source['category']}」调配 ¥{move}")
            new_actions.append(new_action)
            replaced = True
        else:
            new_actions.append(copy.deepcopy(action))

    new_impact = copy.deepcopy(impact)
    new_impact["rebalance"] = {
        "from": new_source["category"], "to": target, "amount": str(move),
    }
    return (new_actions, new_impact,
            f"按你的要求不动「{source}」预算，改从「{new_source['category']}」"
            f"调配 ¥{move} 到「{target}」；账单和其他动作保留。")


def _rebuild_with_amount(actions: list[dict], impact: dict,
                         amount: Decimal | None) -> tuple[list[dict], dict, str] | None:
    if amount is None:
        return None
    budget_actions = [a for a in actions
                      if a.get("action") == "set_category_budgets"]
    if len(budget_actions) != 1 or len(budget_actions[0].get("items", [])) != 2:
        return None
    items = budget_actions[0]["items"]
    rebalance_name = (impact.get("rebalance") or {})
    from_item = next((i for i in items
                      if i.get("category_name") == rebalance_name.get("from")), None)
    to_item = next((i for i in items
                    if i.get("category_name") == rebalance_name.get("to")), None)
    if from_item is None or to_item is None:
        from_item = min(items, key=lambda i: Decimal(str(i.get("amount") or 0)))
        to_item = max(items, key=lambda i: Decimal(str(i.get("amount") or 0)))
    before_from = Decimal(str(from_item.get("before") or from_item["amount"]))
    before_to = Decimal(str(to_item.get("before") or to_item["amount"]))
    if before_from <= Decimal("10"):
        return None
    amount = min(amount, tools.q2(before_from - Decimal("10")))
    if amount <= 0:
        return None
    from_item["amount"] = str(tools.q2(before_from - amount))
    to_item["amount"] = str(tools.q2(before_to + amount))
    new_impact = copy.deepcopy(impact)
    rebalance = new_impact.get("rebalance") or {}
    rebalance["amount"] = str(amount)
    new_impact["rebalance"] = rebalance
    summary = (f"按你的要求把调配金额改为 ¥{amount}："
               f"「{rebalance.get('from')}」→「{rebalance.get('to')}」。")
    return copy.deepcopy(actions), new_impact, summary


def _build_followup_diff(db: Session, user: User, message: str, run: AgentRun,
                         last_run: AgentRun, approval: AgentApproval,
                         diff: dict, kind: str) -> dict | None:
    actions = [copy.deepcopy(a) for a in diff.get("actions") or []]
    impact = copy.deepcopy(diff.get("impact") or {})
    if not actions:
        return None

    if kind == "choose":
        alternatives = diff.get("alternatives") or []
        if alternatives:
            index = 1 if (("二" in message or "2" in message or "两" in message)
                          and len(alternatives) > 1) else 0
            alt = copy.deepcopy(alternatives[index])
            actions = [alt]
            summary = f"已按你选择的方案重新生成：{alt.get('label', '替代方案')}。"
        else:
            actions = _task_only_actions(actions)
            summary = "已按你的选择改为：只保留记账和任务，不动任何预算。"
    elif kind == "exclude":
        excluded = _extract_category(db, user, message)
        actions, impact, summary = _rebuild_without_category(
            db, user, actions, impact, excluded)
    elif kind == "adjust":
        amount = _extract_adjust_amount(message)
        rebuilt = _rebuild_with_amount(actions, impact, amount)
        if rebuilt is None:
            return None
        actions, impact, summary = rebuilt
    else:
        alternatives = diff.get("alternatives") or []
        if alternatives:
            alt = copy.deepcopy(alternatives[0])
            actions = [alt]
            summary = f"这是另一个可选方案：{alt.get('label', '替代方案')}。"
        else:
            actions = _task_only_actions(actions)
            summary = "我换了一个不动预算的方案：只保留记账/目标，并创建复盘任务。"

    if not actions:
        return None
    evidence = copy.deepcopy(diff.get("evidence") or {})
    evidence.update({
        "session_id": run.session_id,
        "parent_run_id": last_run.id,
        "followup": True,
        "followup_kind": kind,
        "as_of": datetime.now().isoformat(timespec="seconds"),
    })
    return {
        "summary": summary,
        "impact": impact,
        "evidence": evidence,
        "actions": actions,
        "success_message": summary + " 相关动作已执行。",
    }


def _supersede_approval(db: Session, last_run: AgentRun,
                        approval: AgentApproval) -> None:
    if approval.status == "pending":
        approval.status = "superseded"
        approval.decided_at = datetime.now()
    last_run.status = "superseded"
    last_run.answer = (last_run.answer + " 已被下一轮方案替代。")[:4000]
    last_run.finished_at = datetime.now()
    db.commit()
    _mark_approval_step(db, last_run, approval.id, "superseded")


def _run_followup(db: Session, user: User, message: str, run: AgentRun,
                  start: float, last_run: AgentRun) -> None:
    approval, diff = _latest_approval(db, last_run)
    if approval is None or not diff.get("actions"):
        trace.add_step(db, run, "clarify", "followup_without_context", {},
                       {"last_run_id": last_run.id}, status="wait")
        trace.finish_run(
            db, run, "needs_input",
            "上一轮没有可调整的审批方案。请重新描述目标，例如“午饭花了32元”。",
            evidence={"session_id": run.session_id, "parent_run_id": last_run.id},
            latency_ms=_elapsed(start))
        return

    kind = _followup_kind(message)
    new_diff = _build_followup_diff(
        db, user, message, run, last_run, approval, diff, kind)
    if new_diff is None:
        trace.add_step(db, run, "clarify", "followup_ambiguous",
                       {"message": message, "last_run_id": last_run.id},
                       {"question": "要调整哪个分类、调整多少？"}, status="wait")
        trace.finish_run(
            db, run, "needs_input",
            "我还没理解要改哪一项。可以说“不想动娱乐预算”“只调整 100 元”或“选择第二种方案”。",
            evidence={"session_id": run.session_id, "parent_run_id": last_run.id},
            latency_ms=_elapsed(start))
        return

    policy.validate_actions(db, user, new_diff["actions"])
    _supersede_approval(db, last_run, approval)
    new_approval = trace.create_approval(
        db, run, new_diff, action_type=f"followup_{kind}")
    trace.add_step(db, run, "approval", "approval_required",
                   {"approval_id": new_approval.id,
                    "actions": len(new_diff["actions"]), "followup": kind},
                   {"status": "pending", "approval_id": new_approval.id},
                   status="wait")
    trace.finish_run(
        db, run, "awaiting_approval",
        new_diff["summary"] + " 需要你确认后才会写入。",
        evidence=new_diff["evidence"],
        latency_ms=_elapsed(start))


# ---------------- 审批执行 / 撤销 ----------------

async def execute_approval(db: Session, user: User, approval_id: int,
                           decision: str, edits: dict | None = None) -> dict:
    approval = db.get(AgentApproval, approval_id)
    if approval is None:
        raise HTTPException(404, "审批不存在")
    run = db.get(AgentRun, approval.run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "审批不存在")
    if approval.status in ("approved", "rejected", "undone", "expired", "superseded"):
        return trace.serialize_run(db, run)

    now = datetime.now()
    if approval.expires_at and now > approval.expires_at:
        updated = db.execute(update(AgentApproval).where(
            AgentApproval.id == approval.id,
            AgentApproval.status == "pending",
        ).values(status="expired", decided_at=now))
        db.commit()
        db.refresh(approval)
        if updated.rowcount:
            run.status = "failed"
            run.answer = "审批已过期（30 分钟），请重新运行 Agent 生成新方案。"
            run.finished_at = now
            db.commit()
            trace.add_step(db, run, "approval", "approval_expired",
                           {"approval_id": approval.id}, {"status": "expired"},
                           status="wait")
        return trace.serialize_run(db, run)

    diff = trace.loads(approval.diff_json, {})

    if decision == "rejected":
        updated = db.execute(update(AgentApproval).where(
            AgentApproval.id == approval.id,
            AgentApproval.status == "pending",
        ).values(status="rejected", decided_at=now))
        db.commit()
        db.refresh(approval)
        if not updated.rowcount:
            return trace.serialize_run(db, run)
        _mark_approval_step(db, run, approval.id, "rejected")
        alternatives = diff.get("alternatives") or []
        if alternatives:
            alternative = alternatives[0]
            alt_diff = {
                "summary": "已根据你的拒绝生成替代方案。",
                "impact": diff.get("impact", {}),
                "evidence": diff.get("evidence", {}),
                "actions": [alternative],
                "success_message": alternative.get("label", "替代方案已执行"),
            }
            try:
                policy.validate_actions(db, user, [alternative])
                new_approval = trace.create_approval(
                    db, run, alt_diff, action_type="alternative")
                trace.add_step(db, run, "approval", "approval_replanned",
                               {"rejected_approval_id": approval.id},
                               {"new_approval_id": new_approval.id}, status="wait")
                run.status = "awaiting_approval"
                run.answer = ("好的，不暂停。我改成更温和的方案："
                              + alternative.get("note", {}).get("title", "先观察一个月")
                              + "。确认后我再写入。")
                db.commit()
            except policy.PolicyError:
                run.status = "rejected"
                run.answer = "已取消，没有写入任何数据。"
                run.finished_at = datetime.now()
                db.commit()
        else:
            run.status = "rejected"
            run.answer = "已取消，没有写入任何数据。"
            run.finished_at = datetime.now()
            db.commit()
        return trace.serialize_run(db, run)

    actions = diff.get("actions") or []
    try:
        _apply_edits(actions, edits or {}, diff)
        policy.validate_actions(db, user, actions)
        # 原子占用审批：两个并发请求只有一个能把 pending 改成 approved
        updated = db.execute(update(AgentApproval).where(
            AgentApproval.id == approval.id,
            AgentApproval.status == "pending",
        ).values(status="approved", decided_at=now))
        if not updated.rowcount:
            db.rollback()
            db.refresh(approval)
            return trace.serialize_run(db, run)
        undo: list[dict] = []
        for action in actions:
            undo.extend(_execute_action(db, user, action))
        db.flush()
        verification = _verify_actions(db, user, actions, undo)
        if not verification["all_ok"]:
            raise policy.PolicyError("执行校验未通过，已回滚，未写入任何数据")
        diff["undo"] = undo
        diff["verify"] = verification
        approval.diff_json = trace.dumps(diff)
        run.status = "completed"
        run.answer = diff.get("success_message") or "已执行。"
        run.finished_at = now
        db.commit()
        db.refresh(approval)
    except policy.PolicyError as exc:
        db.rollback()
        trace.add_step(db, run, "error", "execute_failed", {},
                       {"error": str(exc)}, status="error", error=str(exc))
        raise HTTPException(409, str(exc))
    except Exception as exc:
        db.rollback()
        trace.add_step(db, run, "error", "execute_failed", {},
                       {"error": str(exc)}, status="error", error=str(exc))
        raise HTTPException(500, "执行失败，已回滚，未写入任何数据。")

    trace.add_step(db, run, "execute", "execute_approved_action",
                   {"approval_id": approval.id},
                   {"executed": len(actions), "undo": len(undo)})
    trace.add_step(db, run, "verify", "verify_result", {},
                   verification)
    await _notify_after_execution(db, user, actions, undo)
    _mark_approval_step(db, run, approval.id, "approved")
    return trace.serialize_run(db, run)


async def _notify_after_execution(db: Session, user: User, actions: list[dict],
                                  undo: list[dict]) -> None:
    """Agent 写入账单/预算后，联动预算中心预警与整月预算口径。"""
    try:
        from app.routers.budget_center import (
            _alert_if_already_over, _check_budget_threshold, _sync_month_budget,
        )
    except Exception:
        return

    for item in undo:
        if item.get("action") != "delete_bill":
            continue
        bill = db.get(Bill, int(item["bill_id"]))
        if bill is None or bill.type != "expense" or not bill.category_id:
            continue
        category = db.get(BillCategory, bill.category_id)
        if category is None:
            continue
        try:
            await _check_budget_threshold(db, user, bill, category)
        except Exception:
            pass

    budget_months: set[str] = set()
    for action in actions:
        if action.get("action") != "set_category_budgets":
            continue
        month = action.get("month")
        budget_months.add(month)
        for item in action.get("items", []):
            try:
                _alert_if_already_over(db, user, int(item["category_id"]),
                                       month, Decimal(str(item["amount"])))
            except Exception:
                pass
    for month in budget_months:
        try:
            _sync_month_budget(db, user, month)
        except Exception:
            pass


def _verify_actions(db: Session, user: User, actions: list[dict],
                    undo: list[dict]) -> dict:
    """执行后回查数据库，确认金额/分类/任务/目标/订阅状态真的写对了。"""
    bill_ids = [u["bill_id"] for u in undo if u.get("action") == "delete_bill"]
    goal_ids = [u["goal_id"] for u in undo if u.get("action") == "delete_goal"]
    note_ids = [u["note_id"] for u in undo if u.get("action") == "delete_note"]
    checks: list[dict] = []
    bill_i = goal_i = note_i = 0

    for action in actions:
        kind = action.get("action")
        if kind == "create_bill" and bill_i < len(bill_ids):
            row = db.get(Bill, bill_ids[bill_i])
            bill_i += 1
            expected = tools.q2(action["bill"]["amount"])
            ok = (row is not None and row.user_id == user.id
                  and tools.q2(row.amount) == expected
                  and row.type == action["bill"]["type"]
                  and row.source == "agent"
                  and row.bill_date.isoformat() == str(action["bill"].get("bill_date"))[:10]
                  and (action["bill"].get("category_id") is None
                       or row.category_id == action["bill"].get("category_id")))
            checks.append({"action": kind, "ok": ok,
                           "detail": f"bill_id={getattr(row, 'id', None)} amount={expected}"})
        elif kind == "set_category_budgets":
            for item in action.get("items", []):
                row = db.scalar(select(CategoryBudget).where(
                    CategoryBudget.user_id == user.id,
                    CategoryBudget.category_id == int(item["category_id"]),
                    CategoryBudget.month == action["month"]))
                expected = tools.q2(item["amount"])
                if expected <= 0:
                    ok = row is None
                else:
                    ok = row is not None and tools.q2(row.amount) == expected
                checks.append({"action": kind, "ok": ok,
                               "detail": f"category_id={item['category_id']} amount={expected}"})
        elif kind == "create_goal" and goal_i < len(goal_ids):
            row = db.get(SavingsGoal, goal_ids[goal_i])
            goal_i += 1
            expected = tools.q2(action["goal"]["target_amount"])
            expected_months = action["goal"].get("target_months")
            ok = (row is not None and row.user_id == user.id
                  and tools.q2(row.target_amount) == expected
                  and (expected_months is None or row.target_months == expected_months))
            checks.append({"action": kind, "ok": ok,
                           "detail": f"goal_id={getattr(row, 'id', None)} amount={expected}"})
        elif kind == "create_task" and note_i < len(note_ids):
            row = db.get(Note, note_ids[note_i])
            note_i += 1
            ok = (row is not None and row.user_id == user.id
                  and row.status == "open" and row.note_type == "todo")
            checks.append({"action": kind, "ok": ok,
                           "detail": f"note_id={getattr(row, 'id', None)}"})
        elif kind == "pause_subscription":
            row = db.get(Subscription, int(action["subscription_id"]))
            ok = row is not None and row.user_id == user.id and row.status == "paused"
            checks.append({"action": kind, "ok": ok,
                           "detail": f"subscription_id={action['subscription_id']} status={getattr(row, 'status', None)}"})

    return {"all_ok": all(c["ok"] for c in checks), "checks": checks}


def _mark_approval_step(db: Session, run: AgentRun, approval_id: int, decision: str) -> None:
    """把等待中的审批步骤标记为已决策，避免轨迹长期显示“等待中”。"""
    steps = db.scalars(select(AgentStep).where(
        AgentStep.run_id == run.id,
        AgentStep.tool_name.in_(("approval_required", "approval_replanned")))).all()
    for step in steps:
        args = trace.loads(step.args_json, {})
        result = trace.loads(step.result_json, {})
        if (args.get("approval_id") == approval_id
                or result.get("approval_id") == approval_id
                or result.get("new_approval_id") == approval_id):
            result["decision"] = decision
            result["decided_at"] = datetime.now().isoformat(timespec="seconds")
            step.result_json = trace.dumps(result)
            step.status = "ok"
            db.commit()
            return


def _apply_edits(actions: list[dict], edits: dict, diff: dict) -> None:
    """审批前修改金额/预算；改完必须重算摘要和成功文案，避免“改成 50 仍显示 32”。"""
    if not edits:
        return
    bill_changed = False
    bill_amount = edits.get("bill_amount")
    if bill_amount is not None:
        try:
            new_amount = tools.q2(bill_amount)
        except Exception:
            raise policy.PolicyError("修改后的账单金额格式不正确")
        for action in actions:
            if action.get("action") == "create_bill":
                if new_amount != tools.q2(action["bill"]["amount"]):
                    action["bill"]["amount"] = str(new_amount)
                    bill_changed = True
                break
    budgets = edits.get("budgets")
    budgets_changed = False
    if isinstance(budgets, dict):
        for action in actions:
            if action.get("action") != "set_category_budgets":
                continue
            for item in action.get("items", []):
                key = str(item.get("category_id"))
                if key in budgets:
                    try:
                        new_amount = tools.q2(budgets[key])
                    except Exception:
                        raise policy.PolicyError("修改后的预算金额格式不正确")
                    if new_amount != tools.q2(item["amount"]):
                        item["amount"] = str(new_amount)
                        budgets_changed = True

    if not bill_changed and not budgets_changed:
        return

    if bill_changed:
        impact = diff.setdefault("impact", {})
        bill_action = next((a for a in actions if a.get("action") == "create_bill"), None)
        if bill_action:
            new_amount = Decimal(bill_action["bill"]["amount"])
            impact["amount"] = str(new_amount)
            if impact.get("spent_before") is not None and impact.get("budget") is not None:
                spent_after = tools.q2(Decimal(impact["spent_before"]) + new_amount)
                impact["spent_after"] = str(spent_after)
                impact["remaining_after"] = str(tools.q2(Decimal(impact["budget"]) - spent_after))

    bill_actions = [a for a in actions if a.get("action") == "create_bill"]
    if bill_actions:
        total = sum((Decimal(a["bill"]["amount"]) for a in bill_actions), Decimal("0"))
        diff["summary"] = (f"已按你的修改更新方案：{len(bill_actions)} 笔账单，"
                           f"共 ¥{tools.q2(total)}。")
        diff["success_message"] = (f"已按你的修改记录 {len(bill_actions)} 笔账单，"
                                   f"共 ¥{tools.q2(total)}，并完成相关预算/任务调整。")
    elif budgets_changed:
        diff["summary"] = "已按你的修改更新预算方案。"
        diff["success_message"] = "已按你的修改执行预算调整。"


def _execute_action(db: Session, user: User, action: dict) -> list[dict]:
    kind = action.get("action")
    undo: list[dict] = []

    if kind == "create_bill":
        bill = action["bill"]
        category = tools.resolve_category(db, user, bill.get("category", ""), bill.get("type", "expense"))
        if category is None:
            raise policy.PolicyError(f"分类「{bill.get('category')}」不存在")
        row = Bill(
            user_id=user.id, category_id=category.id, type=bill["type"],
            amount=Decimal(str(bill["amount"])), bill_date=_safe_date(bill.get("bill_date")),
            remark=(bill.get("remark") or "")[:200], source="agent",
            pay_channel=(bill.get("pay_channel") or "")[:20],
            funding_account=(bill.get("funding_account") or "")[:40])
        db.add(row)
        db.flush()
        undo.append({"action": "delete_bill", "bill_id": row.id})
        _remember(db, user, "merchant_category", (row.remark or "")[:80],
                  {"category": category.name, "amount": str(row.amount)})

    elif kind == "set_category_budgets":
        month = action["month"]
        for item in action.get("items", []):
            cid = int(item["category_id"])
            amount = Decimal(str(item["amount"]))
            row = db.scalar(select(CategoryBudget).where(
                CategoryBudget.user_id == user.id,
                CategoryBudget.category_id == cid,
                CategoryBudget.month == month))
            before = str(row.amount) if row else None
            if amount <= 0:
                if row:
                    db.delete(row)
            elif row is None:
                db.add(CategoryBudget(user_id=user.id, category_id=cid,
                                      month=month, amount=amount, source="ai"))
            else:
                row.amount = amount
                row.source = "ai"
            undo.append({"action": "restore_budget", "category_id": cid,
                         "month": month, "before": before})

    elif kind == "create_goal":
        goal = action["goal"]
        target_months = int(goal.get("target_months") or 0) or None
        target_date = _safe_date(goal["target_date"]) if goal.get("target_date") else None
        row = SavingsGoal(user_id=user.id, name=str(goal["name"])[:50],
                          target_amount=Decimal(str(goal["target_amount"])),
                          saved_amount=Decimal("0"),
                          target_months=target_months, target_date=target_date)
        db.add(row)
        db.flush()
        undo.append({"action": "delete_goal", "goal_id": row.id})
        _remember(db, user, "goal", "active_goal",
                  {"name": row.name, "target_amount": str(row.target_amount),
                   "target_months": row.target_months,
                   "target_date": row.target_date.isoformat() if row.target_date else None})

    elif kind == "create_task":
        note = action["note"]
        due_at = None
        if note.get("due_at"):
            try:
                due_at = datetime.fromisoformat(str(note["due_at"]))
            except ValueError:
                due_at = None
        row = Note(user_id=user.id, title=str(note["title"])[:100],
                   content=str(note.get("content") or "")[:5000],
                   note_type="todo", status="open", due_at=due_at,
                   priority=str(note.get("priority") or "medium"),
                   pinned=0, color=str(note.get("color") or "lilac"))
        db.add(row)
        db.flush()
        undo.append({"action": "delete_note", "note_id": row.id})

    elif kind == "pause_subscription":
        sub_id = int(action["subscription_id"])
        row = db.get(Subscription, sub_id)
        if row is None or row.user_id != user.id:
            raise policy.PolicyError("订阅不存在")
        before = row.status
        row.status = "paused"
        undo.append({"action": "set_subscription_status",
                     "subscription_id": sub_id, "before": before})
        _remember(db, user, "preference", "subscription_pause",
                  {"subscription_id": sub_id, "name": row.name})

    elif kind == "create_memory":
        _remember(db, user, str(action.get("kind") or "profile"),
                  str(action["key"]), action.get("value") or {})

    return undo


def undo_run(db: Session, user: User, run_id: int) -> dict:
    run = db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    approval = db.scalar(select(AgentApproval).where(
        AgentApproval.run_id == run.id, AgentApproval.status == "approved")
        .order_by(AgentApproval.id.desc()).limit(1))
    if approval is None:
        raise HTTPException(400, "没有可撤销的已执行动作")
    diff = trace.loads(approval.diff_json, {})
    undo = diff.get("undo") or []
    try:
        for item in reversed(undo):
            _apply_undo(db, user, item)
        approval.status = "undone"
        run.status = "undone"
        run.answer = "已撤销上一次执行，相关数据已恢复。"
        run.finished_at = datetime.now()
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "撤销失败，数据未改变。")
    trace.add_step(db, run, "execute", "undo_approved_action",
                   {"approval_id": approval.id}, {"undone": len(undo)})
    return trace.serialize_run(db, run)


def _apply_undo(db: Session, user: User, item: dict) -> None:
    kind = item.get("action")
    if kind == "delete_bill":
        row = db.get(Bill, int(item["bill_id"]))
        if row and row.user_id == user.id:
            db.delete(row)
    elif kind == "delete_goal":
        row = db.get(SavingsGoal, int(item["goal_id"]))
        if row and row.user_id == user.id:
            db.delete(row)
    elif kind == "delete_note":
        row = db.get(Note, int(item["note_id"]))
        if row and row.user_id == user.id:
            db.delete(row)
    elif kind == "restore_budget":
        row = db.scalar(select(CategoryBudget).where(
            CategoryBudget.user_id == user.id,
            CategoryBudget.category_id == int(item["category_id"]),
            CategoryBudget.month == item["month"]))
        before = item.get("before")
        if before is None:
            if row:
                db.delete(row)
        elif row:
            row.amount = Decimal(str(before))
        else:
            db.add(CategoryBudget(user_id=user.id,
                                  category_id=int(item["category_id"]),
                                  month=item["month"],
                                  amount=Decimal(str(before)), source="manual"))
    elif kind == "set_subscription_status":
        row = db.get(Subscription, int(item["subscription_id"]))
        if row and row.user_id == user.id:
            row.status = item.get("before") or "active"


# ---------------- 主动扫描 ----------------

# 用户忽略的同类风险，冷却 7 天后可再次提醒；每项最多再提醒 2 次，避免打扰
DISMISS_COOLDOWN_DAYS = 7
MAX_REMINDERS = 2
SEVERITY = {"critical": 0, "warn": 1, "info": 2}


def scan_proactive(db: Session, user: User) -> list[dict]:
    """基于消费健康报告生成主动风险，覆盖预算/订阅/目标/行为变化/异常/计划采购。

    所有金额与风险等级都来自 health_service 的确定性计算；模型不参与。
    """
    month = tools.current_month()
    report = health_service.build_report(db, user, month)
    items: list[dict] = []

    def add(alert_type: str, level: str, title: str, message: str,
            suggestion: str, category: str, impact: Decimal | None,
            dedupe: str, trigger: str, related: dict | None = None,
            source: str = "") -> None:
        items.append({
            "alert_type": alert_type, "level": level,
            "title": title[:80], "message": message[:300],
            "suggestion": suggestion[:300], "category": category[:40],
            "amount": health_service.q2(impact) if impact is not None else None,
            "payload": {
                "dedupe": dedupe[:120], "trigger": trigger[:300],
                "impact_amount": str(health_service.q2(impact)) if impact is not None else None,
                "related": related or {}, "month": month, "source": source,
            },
        })

    # 1) 预算即将超支 / 已超支
    for item in report["categories"]:
        if item["budget_status"] == "over100":
            over = abs(item["remaining"])
            add("budget", "critical", f"「{item['category']}」预算已超支",
                f"已花 ¥{item['amount']} / 预算 ¥{item['budget']}，"
                f"超出 ¥{over}，使用率 {round((item['usage_ratio'] or 0) * 100)}%。",
                "可以让 Agent 生成调配方案，或本周暂停该分类的非必要支出。",
                item["category"], over,
                f"budget:{item['category_id']}:{month}",
                f"分类支出 ¥{item['amount']} 超过预算 ¥{item['budget']}",
                {"category_id": item["category_id"], "budget": str(item["budget"]),
                 "spent": str(item["amount"])},
                "category_budgets + bills")
        elif item["budget_status"] == "used_up":
            add("budget", "warn", f"「{item['category']}」预算已用完",
                f"已花 ¥{item['amount']} / 预算 ¥{item['budget']}，剩余 ¥0；"
                "后续支出会直接超支。",
                "如果本月还有必要支出，可以提前从结余分类调配额度。",
                item["category"], None,
                f"budget:{item['category_id']}:{month}",
                f"分类支出刚好用完预算 ¥{item['budget']}",
                {"category_id": item["category_id"], "budget": str(item["budget"]),
                 "spent": str(item["amount"])},
                "category_budgets + bills")
        elif item["budget_status"] == "near80":
            add("budget", "warn", f"「{item['category']}」预算即将用完",
                f"已花 ¥{item['amount']} / 预算 ¥{item['budget']}，"
                f"剩余 ¥{item['remaining']}，使用率 {round((item['usage_ratio'] or 0) * 100)}%。",
                "提前规划剩余额度；如果不够，可以让 Agent 从结余分类调配。",
                item["category"], item["remaining"],
                f"budget:{item['category_id']}:{month}",
                f"分类支出达到预算的 {round((item['usage_ratio'] or 0) * 100)}%",
                {"category_id": item["category_id"], "budget": str(item["budget"]),
                 "spent": str(item["amount"])},
                "category_budgets + bills")

    # 2) 订阅涨价 / 低频 / 重复扣款
    for issue in report["subscriptions"]["issues"]:
        kind = issue["kind"]
        if kind == "duplicate":
            title = f"「{issue['name']}」可能重复扣款"
            level = "warn"
            dedupe = f"subscription:duplicate:{issue['name']}:{month}"
        elif kind in ("price_up", "price_up_low_usage"):
            title = f"订阅「{issue['name']}」涨价"
            level = "warn"
            dedupe = f"subscription:{issue['subscription_id']}:{kind}:{month}"
        else:
            title = f"订阅「{issue['name']}」使用频率低"
            level = "info"
            dedupe = f"subscription:{issue['subscription_id']}:{kind}:{month}"
        add("subscription", level, title,
            issue["message"] + f"；按暂停估算年化影响 ¥{issue['annual_impact']}。",
            "可以让 Agent 暂停订阅，或创建月底复盘任务后再决定。",
            "订阅", issue["annual_impact"], dedupe,
            issue["message"], {"subscription_id": issue["subscription_id"],
                               "kind": kind},
            "subscriptions + bills")

    # 3) 储蓄目标延期 / 停滞
    for goal in report["goals"]:
        if goal["status"] == "delayed":
            add("goal", "warn", f"「{goal['name']}」预计延期",
                f"按近 3 个月平均结余 ¥{goal['avg_monthly_net']} 估算，"
                f"预计 {goal['projected_finish']} 完成，目标日期 {goal['target_date']}，"
                f"延期约 {goal['delay_days']} 天。",
                f"每月需存 ¥{goal['required_monthly']}；可以压缩可自由支配预算或调整目标周期。",
                "储蓄目标", goal["remaining"], f"goal:{goal['id']}:{month}",
                f"预计完成日晚于目标日期 {goal['delay_days']} 天",
                {"goal_id": goal["id"], "target_date": str(goal["target_date"]),
                 "projected_finish": str(goal["projected_finish"])},
                "savings_goals + bills")
        elif goal["status"] == "stalled":
            add("goal", "critical", f"「{goal['name']}」进度停滞",
                f"近 3 个月平均结余为 ¥{goal['avg_monthly_net']}，"
                f"目标还差 ¥{goal['remaining']}，当前结余无法推进目标。",
                "先恢复正向结余，再拆解每月储蓄额；也可以让 Agent 重新规划。",
                "储蓄目标", goal["remaining"], f"goal:{goal['id']}:{month}",
                "近 3 个月平均结余 <= 0", {"goal_id": goal["id"]},
                "savings_goals + bills")

    # 4) 消费行为明显变化（分类环比 + 总支出环比）
    # 只取变化最大的 2 个分类 + 1 条总支出变化，避免把通知列表塞满
    for change in report["changes"][:2]:
        if change["kind"] != "category_up":
            continue
        add("spending_change", "warn", change["title"], change["detail"],
            "可以给该分类设置预算上限，或检查是否有一次性大额支出。",
            change["category"], abs(change["change_amount"]),
            f"change:{change['category']}:{month}:up",
            change["detail"], {"category": change["category"]},
            "bills")

    overview = report["overview"]
    if (overview["prev_expense"] > 0 and overview["expense_change_amount"] >= 500
            and (overview["expense_change_ratio"] or 0) >= 0.3):
        add("spending_change", "warn", "本月总支出明显高于上月",
            f"本月 ¥{overview['expense']}，上月 ¥{overview['prev_expense']}，"
            f"增加 ¥{overview['expense_change_amount']}（"
            f"{round((overview['expense_change_ratio'] or 0) * 100)}%）。",
            "先看是哪个分类涨得多，再决定压缩预算还是接受一次性支出。",
            "总支出", overview["expense_change_amount"], f"spending:{month}:up",
            "总支出环比增幅 >= 30% 且增加 >= ¥500",
            {"prev_expense": str(overview["prev_expense"]),
             "expense": str(overview["expense"])}, "bills")

    # 5) 异常大额
    for anomaly in report["anomalies"]:
        add("anomaly", "warn", anomaly["title"], anomaly["detail"],
            "确认是否是一次性必要支出；如果不是，建议给该分类设置提醒。",
            anomaly["category"], anomaly["amount"],
            f"anomaly:{anomaly['source_ids'][0] if anomaly['source_ids'] else anomaly['bill_date']}",
            anomaly["detail"], {"category": anomaly["category"],
                                "bill_date": anomaly["bill_date"]},
            "bills")

    # 6) 计划采购：待办标题/内容里能识别出金额时，提示资金压力
    budget_remaining = report["budget"]["remaining"]
    for todo in tools.list_todos(db, user.id, limit=12):
        text = f"{todo['title']} {todo['content']}"
        match = re.search(r"(\d+(?:\.\d+)?)", text)
        if not match or not any(k in text for k in ("买", "换", "采购", "预算", "付")):
            continue
        amount = Decimal(match.group(1))
        if amount < 100:
            continue
        pressure = (f"本月预算剩余 ¥{budget_remaining}，这笔预计占剩余的 "
                    f"{round(float(amount / budget_remaining) * 100)}%。"
                    if budget_remaining > 0 else "本月预算已无剩余，这笔支出会直接造成超支。")
        add("planned_purchase", "info", "计划采购提醒",
            f"待办「{todo['title']}」可能是一笔约 ¥{amount} 的支出。{pressure}",
            "提前留出预算，或让 Agent 评估资金压力。",
            "购物", amount, f"planned:{todo['id']}:{month}",
            f"待办中包含金额 ¥{amount}", {"note_id": todo["id"]},
            "notes")

    items.sort(key=lambda i: (SEVERITY.get(i["level"], 9),
                              -float(i["amount"] or 0)))
    return items[:12]


def _notification_key(item: dict, month: str) -> str:
    payload = item.get("payload") or {}
    if payload.get("dedupe"):
        return str(payload["dedupe"])[:120]
    # 兼容旧格式
    kind = item.get("alert_type")
    if kind == "budget":
        return f"budget:{payload.get('category_id')}:{month}"
    if kind == "subscription":
        sid = payload.get("subscription_id")
        if sid:
            return f"subscription:{sid}:{month}:{payload.get('kind')}"
        return f"subscription:duplicate:{month}:{payload.get('name')}"
    if kind == "goal":
        return f"goal:{payload.get('id')}:{month}"
    if kind == "planned_purchase":
        return f"planned:{payload.get('id')}:{month}"
    return f"{kind}:{item.get('title')}:{month}"


def scan_and_persist(db: Session, user: User) -> tuple[list[dict], int]:
    """主动扫描并持久化通知：同月同项只保留一条；已忽略的按冷却规则再提醒。"""
    month = tools.current_month()
    items = scan_proactive(db, user)
    now = datetime.now()
    result: list[dict] = []
    for item in items:
        key = _notification_key(item, month)[:120]
        row = db.scalar(select(AgentNotification).where(
            AgentNotification.user_id == user.id,
            AgentNotification.dedupe_key == key))
        payload = item.get("payload") or {}
        if row is None:
            row = AgentNotification(
                user_id=user.id, alert_type=item["alert_type"],
                level=item.get("level", "info"), title=item["title"][:80],
                message=item["message"][:300], suggestion=(item.get("suggestion") or "")[:300],
                category=(item.get("category") or "")[:40],
                amount=item.get("amount"),
                payload_json=trace.dumps({**payload, "remind_count": 0}),
                status="unread", dedupe_key=key)
            db.add(row)
            db.commit()
            db.refresh(row)
        else:
            old_payload = trace.loads(row.payload_json, {})
            if row.status == "dismissed":
                # 忽略后冷却 7 天；最多再提醒 2 次
                last = row.read_at or row.created_at
                repeats = int(old_payload.get("remind_count") or 0)
                if (now - last).days < DISMISS_COOLDOWN_DAYS or repeats >= MAX_REMINDERS:
                    continue
                payload["remind_count"] = repeats + 1
                row.status = "unread"
                row.read_at = None
                row.created_at = now
            else:
                payload["remind_count"] = int(old_payload.get("remind_count") or 0)
                # 风险升级（如 near80 → over100）时重新变成未读
                if (SEVERITY.get(item.get("level", "info"), 9)
                        < SEVERITY.get(row.level, 9) and row.status == "read"):
                    row.status = "unread"
                    row.read_at = None
            row.level = item.get("level", row.level)
            row.title = item["title"][:80]
            row.message = item["message"][:300]
            row.suggestion = (item.get("suggestion") or "")[:300]
            row.category = (item.get("category") or "")[:40]
            row.amount = item.get("amount")
            row.payload_json = trace.dumps(payload)
            db.commit()
        result.append({**item, "id": row.id, "status": row.status})
    unread = db.scalar(select(func.count()).where(
        AgentNotification.user_id == user.id,
        AgentNotification.status == "unread")) or 0
    return result, int(unread)


def list_notifications(db: Session, user: User, status: str = "",
                       limit: int = 20) -> list[dict]:
    conditions = [AgentNotification.user_id == user.id]
    if status in ("unread", "read", "dismissed"):
        conditions.append(AgentNotification.status == status)
    rows = db.scalars(select(AgentNotification).where(*conditions)
                      .order_by(AgentNotification.created_at.desc())
                      .limit(max(1, min(limit, 50)))).all()
    return [{
        "id": row.id, "alert_type": row.alert_type, "level": row.level,
        "title": row.title, "message": row.message, "suggestion": row.suggestion or "",
        "category": row.category or "", "amount": row.amount,
        "payload": trace.loads(row.payload_json, {}), "status": row.status,
        "created_at": row.created_at,
    } for row in rows]


def notification_action(db: Session, user: User, notification_id: int,
                        action: str) -> dict:
    row = db.get(AgentNotification, notification_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "通知不存在")
    row.status = action
    row.read_at = datetime.now()
    db.commit()
    db.refresh(row)
    return {
        "id": row.id, "alert_type": row.alert_type, "level": row.level,
        "title": row.title, "message": row.message, "suggestion": row.suggestion or "",
        "category": row.category or "", "amount": row.amount,
        "payload": trace.loads(row.payload_json, {}), "status": row.status,
        "created_at": row.created_at,
    }


def notification_unread_count(db: Session, user: User) -> int:
    return int(db.scalar(select(func.count()).where(
        AgentNotification.user_id == user.id,
        AgentNotification.status == "unread")) or 0)


def _remember(db: Session, user: User, kind: str, key: str, value: dict) -> None:
    # 记忆可能来自备注/商户，写入前再做一次脱敏，避免敏感数字长期留存
    safe_key = ai_service.mask_sensitive(key[:80])
    payload = ai_service.mask_sensitive(trace.dumps(value))
    row = db.scalar(select(AgentMemory).where(
        AgentMemory.user_id == user.id, AgentMemory.kind == kind,
        AgentMemory.mem_key == safe_key))
    if row:
        row.value_json = payload
    else:
        db.add(AgentMemory(user_id=user.id, kind=kind,
                           mem_key=safe_key, value_json=payload))
    db.flush()


def list_memories(db: Session, user: User) -> list[dict]:
    rows = db.scalars(select(AgentMemory).where(AgentMemory.user_id == user.id)
                      .order_by(AgentMemory.updated_at.desc())).all()
    return [{"id": r.id, "kind": r.kind, "key": r.mem_key,
             "value": trace.loads(r.value_json, {}), "updated_at": r.updated_at}
            for r in rows]


def delete_memory(db: Session, user: User, memory_id: int) -> None:
    row = db.get(AgentMemory, memory_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "记忆不存在")
    db.delete(row)
    db.commit()


def tool_count() -> int:
    return 9  # 读工具：账单/汇总/预算/订阅/目标/待办/资产总览/净资产变化/健康诊断
