"""CSV 账单导入：解析微信/支付宝/通用表头，预览 + 确认导入。

约束：
- 只解析用户主动上传的 CSV，不联网读取任何平台；
- 金额用 Decimal，日期严格校验，无法识别的行进入错误列表，不猜；
- 导入前做“已有账单 + 文件内”双重去重；
- 所有操作按 user_id 隔离，写入 source=csv 的账单。
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bill, User
from app.services.agent import tools

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_ROWS = 5000
PREVIEW_LIMIT = 500
CONFIRM_LIMIT = 1000

DATE_KEYS = ["交易时间", "交易创建时间", "付款时间", "交易日期", "日期", "date", "time"]
AMOUNT_KEYS = ["金额(元)", "金额（元）", "金额", "交易金额", "amount", "money"]
TYPE_KEYS = ["收/支", "收支", "收 支", "类型", "type"]
CATEGORY_KEYS = ["分类", "交易分类", "category"]
PARTY_KEYS = ["交易对方", "商户名称", "对方", "merchant", "counterparty"]
GOODS_KEYS = ["商品名称", "商品", "交易说明", "goods", "description"]
NOTE_KEYS = ["备注", "说明", "remark", "note"]
PAY_KEYS = ["支付方式", "支付渠道", "渠道", "pay_channel"]
ACCOUNT_KEYS = ["扣款账户", "账户", "funding_account"]
STATUS_KEYS = ["当前状态", "交易状态", "状态", "status"]


def _norm(value: str) -> str:
    return (value or "").strip().lstrip("\ufeff").replace(" ", "").lower()


def _find(headers: list[str], keys: list[str]) -> str | None:
    normalized = {_norm(h): h for h in headers}
    for key in keys:
        if _norm(key) in normalized:
            return normalized[_norm(key)]
    for h in headers:
        nh = _norm(h)
        for key in keys:
            if _norm(key) and _norm(key) in nh:
                return h
    return None


def _map_columns(headers: list[str]) -> dict[str, str]:
    mapping = {
        "date": _find(headers, DATE_KEYS),
        "amount": _find(headers, AMOUNT_KEYS),
        "type": _find(headers, TYPE_KEYS),
        "category": _find(headers, CATEGORY_KEYS),
        "party": _find(headers, PARTY_KEYS),
        "goods": _find(headers, GOODS_KEYS),
        "note": _find(headers, NOTE_KEYS),
        "pay_channel": _find(headers, PAY_KEYS),
        "funding_account": _find(headers, ACCOUNT_KEYS),
        "status": _find(headers, STATUS_KEYS),
    }
    return {k: v for k, v in mapping.items() if v}


def _decode(data: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文件编码，请另存为 UTF-8 或 GBK 后再试")


def _delimiter(text: str) -> str:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        return ","


def _parse_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.replace("年", "-").replace("月", "-").replace("日", "")
    raw = raw.replace("/", "-").replace(".", "-").strip()
    raw = re.sub(r"\s+", " ", raw)
    if re.fullmatch(r"\d{8}", raw):
        try:
            return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
        except ValueError:
            return None
    raw = raw.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _parse_amount(value: str) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return None
    raw = raw.replace(",", "").replace("¥", "").replace("￥", "")
    raw = raw.replace("元", "").replace(" ", "").replace('"', "")
    match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not match:
        return None
    try:
        return tools.q2(abs(Decimal(match.group(0))))
    except (InvalidOperation, ValueError):
        return None


def _parse_type(raw_type: str, raw_amount: str, status: str) -> str | None:
    text = (raw_type or "").strip().lower()
    if "不计收支" in text:
        return None
    if "收入" in text or text in ("收", "income", "in"):
        return "income"
    if "支出" in text or text in ("支", "expense", "out"):
        return "expense"
    if "退款" in (status or "") and "收入" not in text:
        return "income"
    try:
        amount = Decimal((raw_amount or "0").replace(",", "").replace("¥", ""))
        if amount < 0:
            return "expense"
    except (InvalidOperation, ValueError):
        pass
    return "expense"


def _channel(value: str, filename: str) -> tuple[str, str]:
    raw = (value or "").strip()
    channel = ""
    for name in ("微信", "支付宝", "银行卡", "云闪付", "现金"):
        if name in raw:
            channel = name
            break
    if not channel:
        lower = (filename or "").lower()
        if "微信" in lower or "wechat" in lower:
            channel = "微信"
        elif "支付宝" in lower or "alipay" in lower:
            channel = "支付宝"
        elif "银行" in lower or "bank" in lower:
            channel = "银行卡"
    account = ""
    if any(k in raw for k in ("卡", "零钱", "余额", "花呗")):
        account = raw[:40]
    return channel[:20], account


def _row_payload(db: Session, user: User, row: dict, mapping: dict[str, str],
                 filename: str) -> dict:
    def get(field: str) -> str:
        header = mapping.get(field)
        return (row.get(header, "") or "").strip() if header else ""

    raw_date = get("date")
    raw_amount = get("amount")
    raw_type = get("type")
    status = get("status")
    parsed_date = _parse_date(raw_date)
    amount = _parse_amount(raw_amount)
    type_ = _parse_type(raw_type, raw_amount, status)
    errors: list[str] = []
    if parsed_date is None:
        errors.append("日期无法识别")
    if amount is None or amount <= 0:
        errors.append("金额无法识别")
    if type_ is None:
        errors.append("不计收支，已跳过")
    if any(k in status for k in ("关闭", "失败", "已撤销")):
        errors.append(f"交易状态为「{status}」，已跳过")

    expense_cats = [c.name for c in tools.visible_categories(db, user, "expense")]
    income_cats = [c.name for c in tools.visible_categories(db, user, "income")]
    provided_category = get("category")
    remark_parts = [get("party"), get("goods"), get("note")]
    remark = " · ".join(dict.fromkeys([p for p in remark_parts if p]))[:200]
    if type_ == "income":
        category = provided_category if provided_category in income_cats else ""
        if not category:
            category = next((name for name in income_cats if name in remark), "")
        if not category:
            category = "其他收入" if "其他收入" in income_cats else (
                income_cats[0] if income_cats else "其他")
    else:
        if provided_category in expense_cats:
            category = provided_category
        else:
            category = tools.guess_category(remark, expense_cats)
    channel, account = _channel(get("pay_channel"), filename)
    explicit_account = get("funding_account")
    return {
        "date": parsed_date,
        "amount": amount,
        "type": type_ or "expense",
        "category": category,
        "remark": remark or category,
        "pay_channel": channel,
        "funding_account": (explicit_account or account)[:40],
        "errors": errors,
        "raw_date": raw_date,
        "raw_amount": raw_amount,
    }


def _duplicate_reason(db: Session, user_id: int, row: dict) -> str:
    if row["date"] is None or row["amount"] is None:
        return ""
    existing = db.scalar(select(Bill.id).where(
        Bill.user_id == user_id, Bill.bill_date == row["date"],
        Bill.amount == row["amount"], Bill.remark == row["remark"]).limit(1))
    return "与已有账单重复" if existing else ""


def _preview_rows(db: Session, user: User, text: str, filename: str,
                  encoding: str = "utf-8") -> dict:
    delimiter = _delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    if not headers:
        raise ValueError("CSV 没有表头或内容为空")
    mapping = _map_columns(headers)
    if "date" not in mapping or "amount" not in mapping:
        raise ValueError("至少需要日期和金额两列（支持日期/交易时间、金额/金额(元)）")
    rows_out: list[dict] = []
    seen: set[tuple] = set()
    total_rows = 0
    valid_rows = duplicate_rows = error_rows = 0
    income_total = Decimal("0")
    expense_total = Decimal("0")
    for index, raw in enumerate(reader, start=1):
        if index > MAX_ROWS:
            break
        total_rows += 1
        payload = _row_payload(db, user, raw, mapping, filename)
        reason = ""
        if not payload["errors"]:
            key = (payload["date"], payload["amount"], payload["remark"])
            if key in seen:
                reason = "文件内重复"
            else:
                seen.add(key)
                reason = _duplicate_reason(db, user.id, payload)
        duplicate = bool(reason)
        if payload["errors"]:
            error_rows += 1
        elif duplicate:
            duplicate_rows += 1
            valid_rows += 1
        else:
            valid_rows += 1
            if payload["type"] == "income":
                income_total += payload["amount"]
            else:
                expense_total += payload["amount"]
        if len(rows_out) < PREVIEW_LIMIT:
            rows_out.append({
                "row_no": index,
                "bill_date": payload["date"],
                "amount": payload["amount"],
                "type": payload["type"],
                "category": payload["category"],
                "remark": payload["remark"],
                "pay_channel": payload["pay_channel"],
                "funding_account": payload["funding_account"],
                "include": not payload["errors"] and not duplicate,
                "duplicate": duplicate,
                "duplicate_reason": reason,
                "errors": payload["errors"],
                "raw_date": payload["raw_date"],
                "raw_amount": payload["raw_amount"],
            })
    notice = ""
    if total_rows >= MAX_ROWS:
        notice = f"文件超过 {MAX_ROWS} 行，只解析了前 {MAX_ROWS} 行。"
    elif total_rows > PREVIEW_LIMIT:
        notice = f"共 {total_rows} 行，预览只展示前 {PREVIEW_LIMIT} 行；确认时只导入勾选的行。"
    return {
        "filename": filename,
        "encoding": encoding,
        "delimiter": delimiter,
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "duplicate_rows": duplicate_rows,
        "error_rows": error_rows,
        "income_total": tools.q2(income_total),
        "expense_total": tools.q2(expense_total),
        "truncated": total_rows > PREVIEW_LIMIT,
        "columns": mapping,
        "rows": rows_out,
        "notice": notice,
    }


def preview_text(db: Session, user: User, text: str, filename: str = "") -> dict:
    if len(text) > MAX_TEXT_CHARS:
        raise ValueError("文本过大，最多 2MB")
    return _preview_rows(db, user, text, filename)


def preview_file(db: Session, user: User, data: bytes, filename: str = "") -> dict:
    if not data:
        raise ValueError("文件为空")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("文件不能超过 5MB")
    try:
        text, encoding = _decode(data)
    except ValueError as exc:
        raise ValueError(str(exc))
    return _preview_rows(db, user, text, filename, encoding)


def confirm(db: Session, user: User, rows: list, filename: str = "") -> dict:
    if len(rows) > CONFIRM_LIMIT:
        raise ValueError(f"一次最多导入 {CONFIRM_LIMIT} 行")
    expense_cats = [c.name for c in tools.visible_categories(db, user, "expense")]
    income_cats = [c.name for c in tools.visible_categories(db, user, "income")]
    imported = skipped = failed = 0
    income_total = Decimal("0")
    expense_total = Decimal("0")
    created_ids: list[int] = []
    errors: list[str] = []
    seen: set[tuple] = set()
    for row in rows:
        row_no = getattr(row, "row_no", 0) or 0
        amount = tools.q2(row.amount)
        category = row.category if row.category in (
            income_cats if row.type == "income" else expense_cats) else ""
        if not category:
            category = (tools.guess_category(row.remark, expense_cats)
                        if row.type == "expense"
                        else ("其他收入" if "其他收入" in income_cats
                              else (income_cats[0] if income_cats else "其他")))
        key = (row.bill_date, amount, row.remark)
        if key in seen or _duplicate_reason(
                db, user.id, {"date": row.bill_date, "amount": amount, "remark": row.remark}):
            skipped += 1
            continue
        seen.add(key)
        try:
            category_row = tools.resolve_category(db, user, category, row.type)
            if category_row is None:
                raise ValueError(f"分类「{category}」不存在")
            with db.begin_nested():
                bill = Bill(
                    user_id=user.id, category_id=category_row.id,
                    type=row.type, amount=amount, bill_date=row.bill_date,
                    remark=(row.remark or category)[:200], source="csv",
                    pay_channel=(row.pay_channel or "")[:20],
                    funding_account=(row.funding_account or "")[:40])
                db.add(bill)
                db.flush()
            created_ids.append(bill.id)
            imported += 1
            if row.type == "income":
                income_total += amount
            else:
                expense_total += amount
        except Exception as exc:
            failed += 1
            errors.append(f"第 {row_no or '?'} 行：{exc}")
    db.commit()
    return {
        "imported_count": imported,
        "skipped_duplicates": skipped,
        "failed_count": failed,
        "income_total": tools.q2(income_total),
        "expense_total": tools.q2(expense_total),
        "created_ids": created_ids,
        "errors": errors[:20],
    }
