"""AI 接口：自然语言记账草稿、便签草稿、月度消费总结。

安全设计：草稿不直接落库，必须由用户确认后走 /api/bills 保存；
每次调用限流并写日志；输出经结构校验与脱敏。
"""
import base64
import io
import re
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from PIL import Image
from sqlalchemy import extract, func, or_, select
from sqlalchemy.orm import Session

from app import config
from app.deps import get_current_user, get_db
from app.models import Bill, BillCategory, User
from app.schemas import (
    AskIn, AskOut, BillDraft, CategoryStatItem, InsightOut, NoteDraft,
    ParseBillIn, ParseBillOut, ParseNoteIn, ParseNoteOut, ParseReceiptOut,
    ReceiptDraft, SummaryOut,
)
from app.services import ai_service
from app.services.ai_service import (
    AIServiceError, PROMPT_VERSION, build_ask_step1_messages,
    build_ask_step2_messages, build_insight_messages, build_parse_bill_messages,
    build_parse_note_messages, build_receipt_messages, build_summary_messages,
    check_rate_limit, ensure_configured, log_call, mask_sensitive,
)

router = APIRouter()


def _category_names(db: Session, user: User) -> list[str]:
    rows = db.scalars(select(BillCategory).where(
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id))).all()
    names = sorted({r.name for r in rows})
    return names or ["其他"]


def _coerce_amount(value) -> Decimal | None:
    """金额容错转换：接受数字或"32元"这类字符串；无法确定时返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        amount = Decimal(str(round(float(value), 2)))
        return amount.quantize(Decimal("0.01")) if amount > 0 else None
    if isinstance(value, str):
        text = value.strip().replace("元", "").replace("块", "").replace("￥", "").replace("¥", "")
        try:
            amount = Decimal(text)
            return amount.quantize(Decimal("0.01")) if amount > 0 else None
        except InvalidOperation:
            return None
    return None


def _coerce_date(value) -> date | None:
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(value.strip()[:10], fmt).date()
            except ValueError:
                continue
    return None


def _validate_bill_drafts(data: dict, categories: list[str]) -> tuple[list[BillDraft], str]:
    """把模型 JSON 转成受控草稿：类型白名单、金额/日期校验、分类兜底、备注脱敏。"""
    raw_bills = data.get("bills")
    if not isinstance(raw_bills, list):
        raise AIServiceError(502, "AI 返回缺少 bills 数组，请重试或手动记账。")

    drafts: list[BillDraft] = []
    for item in raw_bills[:10]:  # 最多 10 条，防止异常输出
        if not isinstance(item, dict):
            continue
        bill_type = item.get("type") if item.get("type") in ("income", "expense") else "expense"
        amount = _coerce_amount(item.get("amount"))
        bill_date = _coerce_date(item.get("bill_date"))
        category = str(item.get("category") or "").strip()
        missing = [f for f in item.get("missing_fields", []) if isinstance(f, str)][:5]

        if not category or category not in categories:
            category = "其他"
            if "category" not in missing:
                missing.append("category")
        if amount is None and "amount" not in missing:
            missing.append("amount")
        if bill_date is None and "bill_date" not in missing:
            missing.append("bill_date")

        remark = mask_sensitive(str(item.get("remark") or "")[:200])
        drafts.append(BillDraft(
            type=bill_type, amount=amount, category=category,
            bill_date=bill_date, remark=remark, missing_fields=missing))

    notice = str(data.get("notice") or "")[:200]
    masked = any(
        mask_sensitive(str(item.get("remark") or "")[:200])
        != str(item.get("remark") or "")[:200]
        for item in raw_bills if isinstance(item, dict))
    if masked:
        notice = (notice + " 已检测到备注中的疑似敏感数字并自动脱敏，请勿在记账内容中提交密码等信息。").strip()[:200]
    # 一致性校验：已解析出草稿时，清除矛盾的“未识别”提示
    if drafts and "未识别到记账内容" in notice:
        notice = notice.replace("未识别到记账内容", "").strip()
    return drafts, notice


@router.post("/parse-bill", response_model=ParseBillOut)
async def parse_bill(req: ParseBillIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    ensure_configured()
    check_rate_limit(db, user.id)

    categories = _category_names(db, user)
    messages = build_parse_bill_messages(req.text, categories)
    retry_hint = (
        "你的上一次输出不是合法 JSON。请严格按照用户最后一次输入的文本重新输出："
        '只允许一个 JSON 对象，不要任何解释或 Markdown。注意：上面示例仅为格式参考，禁止照抄示例内容；'
        '如果用户输入与记账无关，必须返回 {"bills": [], "notice": "未识别到记账内容"}。')
    start = time.monotonic()
    try:
        data = await ai_service.chat_json(messages, retry_hint=retry_hint)
        drafts, notice = _validate_bill_drafts(data, categories)
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="parse_bill", status="success",
                 latency_ms=latency, input_chars=len(req.text))
        return ParseBillOut(drafts=drafts, notice=notice,
                            prompt_version=PROMPT_VERSION,
                            model=config.AI_MODEL, latency_ms=latency)
    except AIServiceError as exc:
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="parse_bill", status="error",
                 latency_ms=latency, input_chars=len(req.text),
                 error_msg=exc.message)
        if exc.kind == "format":
            # 两次都无法得到合法 JSON：按“未识别到记账内容”温和降级，提示用户换说法
            return ParseBillOut(
                drafts=[], notice="未能从这段文本中识别到记账内容，请换一种说法，或使用手动记账。",
                prompt_version=PROMPT_VERSION, model=config.AI_MODEL, latency_ms=latency)
        raise exc


def _coerce_due_at(value) -> datetime | None:
    """容错解析模型返回的截止时间：ISO 格式或"X月X日 HH:MM"等写法。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    # 兼容 "10月23日 18:00" / "10月23日" 写法（补当前年份）
    m = re.match(r"^(\d{1,2})月(\d{1,2})日(?:\s*(\d{1,2}):(\d{2}))?$", text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        hour, minute = int(m.group(3) or 18), int(m.group(4) or 0)
        year = date.today().year
        try:
            result = datetime(year, month, day, hour, minute)
        except ValueError:
            return None
        # 明显早于今天半年以上，按明年处理（如跨年输入"1月5日"）
        if (date.today() - result.date()).days > 180:
            result = result.replace(year=year + 1)
        return result
    return None


def _validate_note_drafts(data: dict) -> tuple[list[NoteDraft], str]:
    """把模型 JSON 转成受控任务草稿：多任务拆分、时间解析、优先级白名单、备注脱敏。"""
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise AIServiceError(502, "AI 返回缺少 items 数组，请重试。", kind="format")

    drafts: list[NoteDraft] = []
    for item in raw_items[:10]:  # 上限 10 条，防止异常输出
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:100]
        if not title:
            continue  # 无标题的条目没有保存价值
        missing = [f for f in item.get("missing_fields", []) if isinstance(f, str)][:5]
        drafts.append(NoteDraft(
            title=title,
            content=mask_sensitive(str(item.get("content") or "")[:2000]),
            note_type=item.get("note_type") if item.get("note_type") in ("note", "todo") else "note",
            due_at=_coerce_due_at(item.get("due_at")),
            priority=item.get("priority") if item.get("priority") in ("high", "medium", "low") else "medium",
            missing_fields=missing))
    return drafts, str(data.get("notice") or "")[:200]


@router.post("/parse-note", response_model=ParseNoteOut)
async def parse_note(req: ParseNoteIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    ensure_configured()
    check_rate_limit(db, user.id)

    messages = build_parse_note_messages(req.text, date.today().isoformat())
    retry_hint = (
        "你的上一次输出不是合法 JSON。请严格按照用户最后一次输入的文本重新输出："
        '只允许一个 JSON 对象，不要任何解释或 Markdown；禁止照抄示例内容；'
        '如果与便签无关，必须返回 {"items": [], "notice": "未识别到便签内容"}。')
    start = time.monotonic()
    try:
        data = await ai_service.chat_json(messages, retry_hint=retry_hint)
        drafts, notice = _validate_note_drafts(data)
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="parse_note", status="success",
                 latency_ms=latency, input_chars=len(req.text))
        return ParseNoteOut(drafts=drafts, notice=notice,
                            prompt_version=PROMPT_VERSION,
                            model=config.AI_MODEL, latency_ms=latency)
    except AIServiceError as exc:
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="parse_note", status="error",
                 latency_ms=latency, input_chars=len(req.text), error_msg=exc.message)
        if exc.kind == "format":
            return ParseNoteOut(
                drafts=[], notice="未能从这段文本中整理出任务，请换一种说法，或手动创建。",
                prompt_version=PROMPT_VERSION, model=config.AI_MODEL, latency_ms=latency)
        raise exc


@router.get("/summary", response_model=SummaryOut)
async def summary(month: str = Query(default=""), period: str = Query(default="month"),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """消费总结：period=month 按月；period=week 汇总最近 7 天。数据全部由后端计算。"""
    today = date.today()
    if period == "week":
        start_day = today - timedelta(days=6)
        label = f"本周（{start_day.month}月{start_day.day}日~{today.month}月{today.day}日）"
        base_condition = [Bill.user_id == user.id,
                          Bill.bill_date >= start_day, Bill.bill_date <= today]
        empty_hint = "本周暂无账单数据"
    else:
        month = month or today.strftime("%Y-%m")
        base_condition = [
            Bill.user_id == user.id,
            extract("year", Bill.bill_date) == int(month[:4]),
            extract("month", Bill.bill_date) == int(month[5:7]),
        ]
        label = f"{month} 月"
        empty_hint = f"{month} 月暂无账单数据"

    income = Decimal(str(db.scalar(select(func.coalesce(func.sum(Bill.amount), 0)).where(
        *base_condition, Bill.type == "income")) or 0))
    expense = Decimal(str(db.scalar(select(func.coalesce(func.sum(Bill.amount), 0)).where(
        *base_condition, Bill.type == "expense")) or 0))
    top_rows = db.execute(
        select(BillCategory.name, func.sum(Bill.amount))
        .join(Bill, Bill.category_id == BillCategory.id)
        .where(*base_condition, Bill.type == "expense")
        .group_by(BillCategory.name)
        .order_by(func.sum(Bill.amount).desc()).limit(5)).all()
    top_categories = [
        CategoryStatItem(category=name, amount=Decimal(str(amount)), ratio=0.0)
        for name, amount in top_rows]

    if income == 0 and expense == 0:
        # 无数据时不调用模型，直接给出确定提示（成本控制 + 防幻觉）
        return SummaryOut(
            month=label, income=income, expense=expense, net=income - expense,
            top_categories=top_categories,
            summary=f"{empty_hint}，请先记录收支后再生成分析。",
            notice="未调用 AI：该时段无数据。",
            prompt_version=PROMPT_VERSION, model=config.AI_MODEL or "-")

    ensure_configured()
    check_rate_limit(db, user.id)
    stats = {"income": income, "expense": expense,
             "net": income - expense,
             "top_categories": [{"category": c.category, "amount": c.amount}
                                for c in top_categories]}
    messages = build_summary_messages(label, stats)
    start = time.monotonic()
    try:
        data = await ai_service.chat_json(messages, temperature=0.3)
        text = str(data.get("summary") or "").strip()[:500]
        if not text:
            raise AIServiceError(502, "AI 未返回分析内容，请重试。")
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="summary", status="success",
                 latency_ms=latency, input_chars=len(label))
        return SummaryOut(
            month=label, income=income, expense=expense, net=income - expense,
            top_categories=top_categories, summary=text,
            notice="分析由 AI 基于真实统计数据生成，仅供参考。",
            prompt_version=PROMPT_VERSION, model=config.AI_MODEL)
    except AIServiceError as exc:
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="summary", status="error",
                 latency_ms=latency, input_chars=len(label), error_msg=exc.message)
        raise exc


# ---------------- 支付截图识别 ----------------

_RECEIPT_STATUS = {"success", "pending", "refunded", "failed", "unknown"}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _check_duplicate(db: Session, user: User, amount: Decimal | None,
                     bill_date) -> tuple[bool, str]:
    """近 7 天同金额（±0.01）的支出 → 疑似重复（确定性规则，不是模型猜测）。"""
    if amount is None:
        return False, ""
    anchor = bill_date or date.today()
    rows = db.scalars(select(Bill).where(
        Bill.user_id == user.id, Bill.type == "expense",
        Bill.bill_date >= anchor - timedelta(days=7),
        Bill.bill_date <= anchor + timedelta(days=1))).all()
    for row in rows:
        if abs(Decimal(str(row.amount)) - amount) <= Decimal("0.01"):
            cat = db.get(BillCategory, row.category_id) if row.category_id else None
            hint = (f"疑似与 {row.bill_date} 的 ¥{row.amount}"
                    f"（{cat.name if cat else '未分类'}）重复，请核对后再保存")
            return True, hint
    return False, ""


def _validate_receipt_draft(db: Session, user: User, data: dict) -> ReceiptDraft:
    """校验视觉模型输出：缺失即待确认、分类白名单、状态白名单、重复检测。"""
    categories = _category_names(db, user)
    amount = _coerce_amount(data.get("amount"))
    bill_date = _coerce_date(data.get("bill_date"))
    bill_time = str(data.get("bill_time") or "").strip()[:5]
    status = data.get("status") if data.get("status") in _RECEIPT_STATUS else "unknown"
    pay_channel = str(data.get("pay_channel") or "").strip()[:20]
    funding = str(data.get("funding_account") or "").strip()[:40]
    # 证据校验：账户名必须出现在模型逐字列出的可见文字清单中，否则视为“未显示”
    visible = data.get("visible_texts")
    visible_texts = [str(t) for t in visible if isinstance(t, str)] \
        if isinstance(visible, list) else []
    evidence = str(data.get("funding_account_evidence") or "").strip()[:80]
    if funding and not any(funding in t for t in visible_texts):
        funding = ""
    merchant = mask_sensitive(str(data.get("merchant") or "").strip()[:60])
    category = str(data.get("category") or "").strip()[:40]

    missing = [f for f in data.get("missing_fields", []) if isinstance(f, str)][:8]
    if not category or category not in categories:
        category = "其他"
        if "category" not in missing:
            missing.append("category")
    if amount is None and "amount" not in missing:
        missing.append("amount")
    if bill_date is None and "bill_date" not in missing:
        missing.append("bill_date")
    if not pay_channel and "pay_channel" not in missing:
        missing.append("pay_channel")
    if not funding and "funding_account" not in missing:
        missing.append("funding_account")

    bill_type = "income" if status == "refunded" else (
        "income" if data.get("type") == "income" and status != "failed" else "expense")
    duplicate, hint = _check_duplicate(db, user, amount, bill_date)

    return ReceiptDraft(
        type=bill_type, amount=amount, merchant=merchant, category=category,
        bill_date=bill_date, bill_time=bill_time,
        remark=merchant or str(data.get("remark") or "").strip()[:200],
        status=status, pay_channel=pay_channel, funding_account=funding,
        missing_fields=missing, duplicate_suspect=duplicate, duplicate_hint=hint)


@router.post("/parse-receipt", response_model=ParseReceiptOut)
async def parse_receipt(file: UploadFile = File(...),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """上传支付截图/小票，视觉模型提取字段并生成待确认草稿（不直接入库）。"""
    ensure_configured()
    check_rate_limit(db, user.id)

    raw = await file.read()
    if len(raw) > _MAX_IMAGE_BYTES:
        raise HTTPException(400, "图片不能超过 5MB，请压缩后重试")
    if not raw:
        raise HTTPException(400, "上传的文件为空")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
        img = img.convert("RGB")
    except Exception:
        raise HTTPException(400, "无法解析该图片，请上传 jpg/png/webp 格式")

    # 压缩到最长边 1280，控制视觉模型 token 成本
    img.thumbnail((1280, 1280))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    categories = _category_names(db, user)
    messages = build_receipt_messages(data_url, categories)
    start = time.monotonic()
    try:
        data = await ai_service.chat_json(
            messages, model=config.AI_VISION_MODEL,
            retry_hint='只输出一个 JSON 对象（以 {"found"...} 开头），不要任何解释或 Markdown。')
        latency = int((time.monotonic() - start) * 1000)
        if not bool(data.get("found", True)):
            log_call(db, user_id=user.id, feature="parse_receipt", status="success",
                     latency_ms=latency, input_chars=len(raw),
                     model=config.AI_VISION_MODEL)
            return ParseReceiptOut(
                found=False, drafts=[], notice=str(data.get("notice") or "未识别到支付信息")[:200],
                prompt_version=PROMPT_VERSION, model=config.AI_VISION_MODEL,
                latency_ms=latency)
        draft = _validate_receipt_draft(db, user, data)
        notice = str(data.get("notice") or "")[:200]
        if draft.status == "failed":
            log_call(db, user_id=user.id, feature="parse_receipt", status="success",
                     latency_ms=latency, input_chars=len(raw),
                     model=config.AI_VISION_MODEL)
            return ParseReceiptOut(
                found=True, drafts=[], notice="识别到交易失败/未完成，未生成账单草稿。",
                prompt_version=PROMPT_VERSION, model=config.AI_VISION_MODEL,
                latency_ms=latency)
        log_call(db, user_id=user.id, feature="parse_receipt", status="success",
                 latency_ms=latency, input_chars=len(raw), model=config.AI_VISION_MODEL)
        return ParseReceiptOut(
            found=True, drafts=[draft], notice=notice,
            prompt_version=PROMPT_VERSION, model=config.AI_VISION_MODEL,
            latency_ms=latency)
    except AIServiceError as exc:
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="parse_receipt", status="error",
                 latency_ms=latency, input_chars=len(raw),
                 error_msg=exc.message, model=config.AI_VISION_MODEL)
        raise exc

# 进程内当日缓存：同一用户同一天只调用一次模型（成本控制）
_INSIGHT_CACHE: dict[int, tuple[str, str]] = {}


def _shift_month(month: str, delta: int) -> str:
    year, mon = int(month[:4]), int(month[5:7]) + delta
    while mon < 1:
        year, mon = year - 1, mon + 12
    while mon > 12:
        year, mon = year + 1, mon - 12
    return f"{year:04d}-{mon:02d}"


def _month_condition(user_id: int, month: str):
    return [
        Bill.user_id == user_id,
        extract("year", Bill.bill_date) == int(month[:4]),
        extract("month", Bill.bill_date) == int(month[5:7]),
    ]


def _global_stats(db: Session, user_id: int, month: str) -> dict:
    cond = _month_condition(user_id, month)
    income = Decimal(str(db.scalar(select(func.coalesce(func.sum(Bill.amount), 0))
                                    .where(*cond, Bill.type == "income")) or 0))
    expense = Decimal(str(db.scalar(select(func.coalesce(func.sum(Bill.amount), 0))
                                     .where(*cond, Bill.type == "expense")) or 0))
    count = db.scalar(select(func.count()).where(*cond)) or 0
    top_rows = db.execute(
        select(BillCategory.name, func.sum(Bill.amount))
        .join(Bill, Bill.category_id == BillCategory.id)
        .where(*cond, Bill.type == "expense")
        .group_by(BillCategory.name)
        .order_by(func.sum(Bill.amount).desc()).limit(3)).all()
    return {
        "income": income, "expense": expense, "net": income - expense, "count": count,
        "top_categories": [{"category": n, "amount": Decimal(str(a))} for n, a in top_rows],
    }


@router.get("/insight", response_model=InsightOut)
async def insight(refresh: bool = False, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """首页 AI 洞察：当日只调用一次模型；无数据或 AI 不可用时返回规则文案。"""
    today = date.today()
    month = today.strftime("%Y-%m")
    cached = _INSIGHT_CACHE.get(user.id)
    if cached and cached[0] == today.isoformat() and not refresh:
        return InsightOut(text=cached[1], month=month, cached=True,
                          model=config.AI_MODEL or "")

    stats = _global_stats(db, user.id, month)
    rule_text = (f"本月已支出 ¥{stats['expense']}，共 {stats['count']} 笔，"
                 f"继续记账可以看清消费结构")
    if stats["count"] == 0:
        text = "本月还没有账单，用一句话就能记一笔，试试 AI 记账吧"
        _INSIGHT_CACHE[user.id] = (today.isoformat(), text)
        return InsightOut(text=text, month=month, notice="本月暂无数据，未调用 AI")

    try:
        ensure_configured()
        check_rate_limit(db, user.id)
    except AIServiceError:
        return InsightOut(text=rule_text, month=month,
                          notice="AI 未启用或次数已用完，当前为基础提示")

    start = time.monotonic()
    try:
        data = await ai_service.chat_json(
            build_insight_messages(month, stats),
            retry_hint='你的上一次输出不是合法 JSON。请只输出 {"insight": "一句话"} 形式的 JSON 对象。')
        text = str(data.get("insight") or "").strip()[:150]
        if not text:
            raise AIServiceError(502, "AI 未返回洞察内容", kind="format")
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="insight", status="success",
                 latency_ms=latency, input_chars=0)
        _INSIGHT_CACHE[user.id] = (today.isoformat(), text)
        return InsightOut(text=text, month=month, model=config.AI_MODEL)
    except AIServiceError as exc:
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="insight", status="error",
                 latency_ms=latency, input_chars=0, error_msg=exc.message)
        return InsightOut(text=rule_text, month=month,
                          notice="AI 暂时不可用，当前为基础提示")


# ---------------- 问账本（工具调用） ----------------

_ASK_TOOLS = {"monthly_summary", "category_summary", "top_categories", "largest_bill",
              "category_compare", "budget_suggestion", "savings_calc", "channel_summary"}


def _execute_ask_tool(db: Session, user: User, tool: str, params: dict) -> dict:
    """执行模型选择的查询工具，只返回当前用户的聚合数据（不返回明细隐私）。"""
    this_month = date.today().strftime("%Y-%m")
    month = this_month if str(params.get("month") or "this") == "this" \
        else _shift_month(this_month, -1)
    cond = _month_condition(user.id, month)

    if tool == "monthly_summary":
        stats = _global_stats(db, user.id, month)
        return {"month": month, "income": str(stats["income"]),
                "expense": str(stats["expense"]), "net": str(stats["net"]),
                "count": stats["count"]}
    if tool == "category_summary":
        name = str(params.get("category") or "").strip()
        cat = db.scalar(select(BillCategory).where(
            BillCategory.name == name,
            (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id)).limit(1))
        if cat is None:
            return {"month": month, "category": name, "found": False,
                    "message": "分类不存在"}
        amount = db.scalar(select(func.coalesce(func.sum(Bill.amount), 0))
                           .where(*cond, Bill.category_id == cat.id)) or 0
        count = db.scalar(select(func.count())
                          .where(*cond, Bill.category_id == cat.id)) or 0
        return {"month": month, "category": name, "found": True,
                "amount": str(Decimal(str(amount))), "count": count}
    if tool == "top_categories":
        try:
            n = max(1, min(int(params.get("n") or 3), 5))
        except (TypeError, ValueError):
            n = 3
        rows = db.execute(
            select(BillCategory.name, func.sum(Bill.amount))
            .join(Bill, Bill.category_id == BillCategory.id)
            .where(*cond, Bill.type == "expense")
            .group_by(BillCategory.name)
            .order_by(func.sum(Bill.amount).desc()).limit(n)).all()
        return {"month": month,
                "items": [{"category": name, "amount": str(Decimal(str(a)))}
                          for name, a in rows]}
    if tool == "largest_bill":
        row = db.scalar(select(Bill).where(*cond, Bill.type == "expense")
                        .order_by(Bill.amount.desc()).limit(1))
        if row is None:
            return {"month": month, "found": False}
        cat = db.get(BillCategory, row.category_id) if row.category_id else None
        return {"month": month, "found": True, "amount": str(row.amount),
                "category": cat.name if cat else "未分类",
                "bill_date": row.bill_date.isoformat(), "remark": row.remark}
    if tool == "category_compare":
        name = str(params.get("category") or "").strip()
        cat = db.scalar(select(BillCategory).where(
            BillCategory.name == name,
            (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id)).limit(1))
        if cat is None:
            return {"category": name, "found": False, "message": "分类不存在"}
        this_month = date.today().strftime("%Y-%m")
        last_month = _shift_month(this_month, -1)

        def month_sum(m: str) -> Decimal:
            return Decimal(str(db.scalar(
                select(func.coalesce(func.sum(Bill.amount), 0)).where(
                    Bill.user_id == user.id, Bill.category_id == cat.id,
                    extract("year", Bill.bill_date) == int(m[:4]),
                    extract("month", Bill.bill_date) == int(m[5:7]))) or 0))

        cur, prev = month_sum(this_month), month_sum(last_month)
        diff = cur - prev
        pct = round(float(diff / prev * 100), 1) if prev > 0 else None
        return {"category": name, "current_month": this_month,
                "current_amount": str(cur.quantize(Decimal("0.01"))),
                "previous_month": last_month,
                "previous_amount": str(prev.quantize(Decimal("0.01"))),
                "diff": str(diff.quantize(Decimal("0.01"))), "change_pct": pct}
    if tool == "budget_suggestion":
        try:
            months_n = max(1, min(int(params.get("months") or 3), 6))
        except (TypeError, ValueError):
            months_n = 3
        today = date.today()
        month_list = [_shift_month(today.strftime("%Y-%m"), -i) for i in range(months_n)]
        # 每月条件为 (year == y and month == m)，多月之间取 or
        month_conditions = [
            (extract("year", Bill.bill_date) == int(m[:4]))
            & (extract("month", Bill.bill_date) == int(m[5:7]))
            for m in month_list]
        rows = db.execute(
            select(BillCategory.name, func.sum(Bill.amount))
            .join(Bill, Bill.category_id == BillCategory.id)
            .where(Bill.user_id == user.id, Bill.type == "expense",
                   or_(*month_conditions))
            .group_by(BillCategory.name)).all()
        items = [{
            "category": name,
            "total": str(Decimal(str(total)).quantize(Decimal("0.01"))),
            "monthly_avg": str((Decimal(str(total)) / months_n).quantize(Decimal("0.01"))),
        } for name, total in rows]
        items.sort(key=lambda x: float(x["monthly_avg"]), reverse=True)
        total_avg = sum((Decimal(i["monthly_avg"]) for i in items), Decimal("0"))
        return {"months": months_n, "items": items,
                "total_monthly_avg": str(total_avg.quantize(Decimal("0.01")))}
    if tool == "savings_calc":
        try:
            daily = Decimal(str(params.get("daily_amount") or 0))
        except Exception:
            daily = Decimal("0")
        if daily <= 0:
            return {"error": "daily_amount 无效"}
        return {"daily_amount": str(daily),
                "monthly_saving": str((daily * 30).quantize(Decimal("0.01"))),
                "yearly_saving": str((daily * 365).quantize(Decimal("0.01"))),
                "basis": "按每月30天估算"}
    if tool == "channel_summary":
        rows = db.execute(
            select(Bill.pay_channel, func.sum(Bill.amount), func.count())
            .where(*cond, Bill.type == "expense")
            .group_by(Bill.pay_channel)).all()
        items = [{"channel": (name or "未记录"),
                  "amount": str(Decimal(str(amount)).quantize(Decimal("0.01"))),
                  "count": count}
                 for name, amount, count in rows]
        items.sort(key=lambda i: float(i["amount"]), reverse=True)
        return {"month": month, "items": items}
    return {"error": "不支持的工具"}


@router.post("/ask", response_model=AskOut)
async def ask(req: AskIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """问账本：模型规划查询 → 后端执行 → 模型组织回答（多步任务可追踪）。"""
    ensure_configured()
    check_rate_limit(db, user.id)

    month = date.today().strftime("%Y-%m")
    categories = _category_names(db, user)
    start = time.monotonic()
    try:
        plan = await ai_service.chat_json(
            build_ask_step1_messages(req.question, month, categories),
            retry_hint='只输出 {"tool": "工具名", "params": {}} 形式的 JSON 对象。')
        tool = str(plan.get("tool") or "unsupported")
        params = plan.get("params") if isinstance(plan.get("params"), dict) else {}
        steps = ["理解问题并选择查询工具"]

        if tool not in _ASK_TOOLS:
            answer = ("这个问题我还回答不了。可以试试问我：本月收支多少、"
                      "某个分类花了多少、最大的支出是什么。")
            latency = int((time.monotonic() - start) * 1000)
            log_call(db, user_id=user.id, feature="ask", status="success",
                     latency_ms=latency, input_chars=len(req.question))
            return AskOut(answer=answer, tool="unsupported", steps=steps,
                          prompt_version=PROMPT_VERSION, model=config.AI_MODEL,
                          latency_ms=latency)

        result = _execute_ask_tool(db, user, tool, params)
        steps.append(f"执行数据查询（{tool}）")

        data = await ai_service.chat_json(
            build_ask_step2_messages(req.question, tool, params, result),
            retry_hint='只输出 {"answer": "回答内容"} 形式的 JSON 对象。')
        answer = str(data.get("answer") or "").strip()[:200]
        if not answer:
            raise AIServiceError(502, "AI 未返回回答，请重试。", kind="format")
        steps.append("基于查询结果生成回答")

        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="ask", status="success",
                 latency_ms=latency, input_chars=len(req.question))
        return AskOut(answer=answer, tool=tool, tool_params=params,
                      data_used=result, steps=steps,
                      prompt_version=PROMPT_VERSION, model=config.AI_MODEL,
                      latency_ms=latency)
    except AIServiceError as exc:
        latency = int((time.monotonic() - start) * 1000)
        log_call(db, user_id=user.id, feature="ask", status="error",
                 latency_ms=latency, input_chars=len(req.question),
                 error_msg=exc.message)
        raise exc
