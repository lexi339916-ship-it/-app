"""Agent 工具注册表与只读查询工具。

工具分两类：
- read：只查询当前用户数据，不写库；
- write：不直接执行，由 orchestrator 生成 diff，用户审批后才由 execute 执行。

数字计算全部在 SQL/Python 中完成，模型只负责自然语言理解与表达。
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from app.models import (
    Bill, BillCategory, CategoryBudget, Note, SavingsGoal, Subscription, User,
)

MAX_AMOUNT = Decimal("9999999999.99")


# ---------------- 通用 ----------------

def current_month() -> str:
    return date.today().strftime("%Y-%m")


def month_key(value: date | datetime | None = None) -> str:
    return (value or date.today()).strftime("%Y-%m")


def q2(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def visible_categories(db: Session, user: User, type_: str = "expense") -> list[BillCategory]:
    return db.scalars(select(BillCategory).where(
        BillCategory.type == type_,
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    ).order_by(BillCategory.id)).all()


def resolve_category(db: Session, user: User, name: str,
                     type_: str = "expense") -> BillCategory | None:
    name = (name or "").strip()
    if not name:
        return None
    return db.scalar(select(BillCategory).where(
        BillCategory.name == name,
        BillCategory.type == type_,
        (BillCategory.user_id.is_(None)) | (BillCategory.user_id == user.id),
    ).limit(1))


def month_condition(user_id: int, month: str, type_: str | None = None):
    year, mon = int(month[:4]), int(month[5:7])
    cond = [Bill.user_id == user_id,
            extract("year", Bill.bill_date) == year,
            extract("month", Bill.bill_date) == mon]
    if type_ in ("income", "expense"):
        cond.append(Bill.type == type_)
    return cond


def month_sum(db: Session, user_id: int, month: str, type_: str) -> Decimal:
    value = db.scalar(select(func.coalesce(func.sum(Bill.amount), 0))
                      .where(*month_condition(user_id, month, type_))) or 0
    return q2(value)


def summarize_month(db: Session, user_id: int, month: str) -> dict:
    income = month_sum(db, user_id, month, "income")
    expense = month_sum(db, user_id, month, "expense")
    count = db.scalar(select(func.count()).where(*month_condition(user_id, month))) or 0
    top_rows = db.execute(
        select(BillCategory.name, func.coalesce(func.sum(Bill.amount), 0))
        .join(Bill, Bill.category_id == BillCategory.id)
        .where(*month_condition(user_id, month, "expense"))
        .group_by(BillCategory.name)
        .order_by(func.sum(Bill.amount).desc()).limit(5)).all()
    return {
        "month": month, "income": income, "expense": expense,
        "net": q2(income - expense), "count": count,
        "top_categories": [{"category": name, "amount": q2(total)}
                           for name, total in top_rows],
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "source": "bills",
    }


def query_bills(db: Session, user_id: int, month: str, type_: str | None = None,
                limit: int = 8) -> list[dict]:
    rows = db.scalars(
        select(Bill).where(*month_condition(user_id, month, type_))
        .order_by(Bill.bill_date.desc(), Bill.id.desc()).limit(max(1, min(limit, 20)))).all()
    result = []
    for row in rows:
        cat = db.get(BillCategory, row.category_id) if row.category_id else None
        result.append({
            "id": row.id, "type": row.type, "amount": q2(row.amount),
            "category": cat.name if cat else "未分类",
            "bill_date": row.bill_date.isoformat(), "remark": row.remark or "",
            "source": row.source or "manual",
        })
    return result


def largest_bill(db: Session, user_id: int, month: str) -> dict | None:
    row = db.scalar(select(Bill).where(*month_condition(user_id, month, "expense"))
                    .order_by(Bill.amount.desc(), Bill.id.desc()).limit(1))
    if row is None:
        return None
    cat = db.get(BillCategory, row.category_id) if row.category_id else None
    return {"id": row.id, "amount": q2(row.amount),
            "category": cat.name if cat else "未分类",
            "bill_date": row.bill_date.isoformat(), "remark": row.remark or ""}


def spent_map(db: Session, user_id: int, month: str) -> dict[int, Decimal]:
    rows = db.execute(
        select(Bill.category_id, func.coalesce(func.sum(Bill.amount), 0))
        .where(*month_condition(user_id, month, "expense"))
        .group_by(Bill.category_id)).all()
    return {cid: q2(total) for cid, total in rows if cid is not None}


def budget_overview(db: Session, user: User, month: str) -> dict:
    spent = spent_map(db, user.id, month)
    budgets = {b.category_id: b for b in db.scalars(
        select(CategoryBudget).where(CategoryBudget.user_id == user.id,
                                     CategoryBudget.month == month)).all()}
    items = []
    for cat in visible_categories(db, user, "expense"):
        budget = budgets.get(cat.id)
        amount = q2(budget.amount) if budget else Decimal("0")
        used = spent.get(cat.id, Decimal("0"))
        ratio = float(used / amount) if amount > 0 else 0.0
        if budget is None:
            status = "none"
        elif ratio > 1:
            status = "over100"
        elif ratio >= 1:
            status = "used_up"
        elif ratio >= 0.8:
            status = "near80"
        else:
            status = "ok"
        items.append({
            "category_id": cat.id, "category": cat.name,
            "amount": amount, "spent": used,
            "remaining": q2(amount - used),
            "usage_ratio": round(ratio, 4), "status": status,
            "source": budget.source if budget else "manual",
            "before_amount": amount,
        })
    total_budget = sum((i["amount"] for i in items), Decimal("0"))
    total_spent = sum((i["spent"] for i in items), Decimal("0"))
    items.sort(key=lambda i: (i["status"] == "none", -i["usage_ratio"]))
    return {
        "month": month, "total_budget": q2(total_budget),
        "total_spent": q2(total_spent), "items": items,
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "source": "category_budgets+bills",
    }


def avg_monthly_net(db: Session, user_id: int, months: int = 3) -> Decimal:
    today = date.today()
    total = Decimal("0")
    for i in range(months):
        year, month = today.year, today.month - i
        while month < 1:
            year, month = year - 1, month + 12
        key = f"{year:04d}-{month:02d}"
        total += month_sum(db, user_id, key, "income") - month_sum(db, user_id, key, "expense")
    return q2(total / months)


def category_monthly_average(db: Session, user_id: int, months: int = 3) -> list[dict]:
    """近 N 个月各分类月均支出，用于目标规划的预算建议。"""
    today = date.today()
    keys = []
    for i in range(months):
        year, month = today.year, today.month - i
        while month < 1:
            year, month = year - 1, month + 12
        keys.append(f"{year:04d}-{month:02d}")
    by_cat: dict[int, Decimal] = {}
    for key in keys:
        rows = db.execute(
            select(Bill.category_id, func.coalesce(func.sum(Bill.amount), 0))
            .where(*month_condition(user_id, key, "expense"))
            .group_by(Bill.category_id)).all()
        for cid, total in rows:
            if cid is not None:
                by_cat[cid] = by_cat.get(cid, Decimal("0")) + q2(total)
    cats = {c.id: c.name for c in visible_categories(db, db.get(User, user_id), "expense")}
    result = [{"category_id": cid, "category": cats.get(cid, "其他"),
               "monthly_avg": q2(total / months)}
              for cid, total in by_cat.items()]
    result.sort(key=lambda x: x["monthly_avg"], reverse=True)
    return result


def list_subscriptions(db: Session, user_id: int) -> list[dict]:
    rows = db.scalars(select(Subscription).where(Subscription.user_id == user_id)
                      .order_by(Subscription.status, Subscription.day_of_month)).all()
    return [{
        "id": s.id, "name": s.name, "amount": q2(s.amount),
        "previous_amount": q2(s.previous_amount) if s.previous_amount is not None else None,
        "usage_90d": int(s.usage_90d or 0), "status": s.status,
        "day_of_month": s.day_of_month, "remark": s.remark or "",
    } for s in rows]


def list_goals(db: Session, user_id: int) -> list[dict]:
    rows = db.scalars(select(SavingsGoal).where(SavingsGoal.user_id == user_id)
                      .order_by(SavingsGoal.created_at.desc())).all()
    avg_net = avg_monthly_net(db, user_id, 3)
    result = []
    for g in rows:
        saved = q2(g.saved_amount)
        target = q2(g.target_amount)
        remaining = max(Decimal("0"), target - saved)
        result.append({
            "id": g.id, "name": g.name, "target_amount": target,
            "saved_amount": saved, "remaining": remaining,
            "progress_ratio": round(float(saved / target), 4) if target > 0 else 0.0,
            "avg_monthly_net": avg_net,
            "estimated_months": (float(remaining / avg_net)
                                 if avg_net > 0 and remaining > 0 else None),
        })
    return result


def list_todos(db: Session, user_id: int, limit: int = 8) -> list[dict]:
    rows = db.scalars(select(Note).where(
        Note.user_id == user_id, Note.note_type == "todo", Note.status == "open")
        .order_by(Note.due_at.asc(), Note.id.desc()).limit(limit)).all()
    return [{
        "id": n.id, "title": n.title, "content": n.content or "",
        "due_at": n.due_at.isoformat() if n.due_at else None,
        "priority": n.priority,
    } for n in rows]


def subscription_issues(db: Session, user_id: int) -> list[dict]:
    """订阅体检：涨价、低频、同月重复扣款。

    同一订阅同时涨价+低频时只生成一条 issue，年化影响按“暂停后能省多少”计算，
    避免把“涨价多花的钱”和“全年订阅费”重复相加。
    """
    issues: list[dict] = []
    for s in db.scalars(select(Subscription).where(
            Subscription.user_id == user_id, Subscription.status == "active")).all():
        current = q2(s.amount)
        previous = q2(s.previous_amount) if s.previous_amount is not None else None
        price_up = bool(previous and current > previous)
        low_usage = int(s.usage_90d or 0) <= 1
        if not price_up and not low_usage:
            continue
        parts = []
        if price_up:
            parts.append(f"从 ¥{previous} 涨到 ¥{current}")
        if low_usage:
            parts.append(f"近 90 天只用了 {int(s.usage_90d or 0)} 次")
        if price_up and low_usage:
            kind = "price_up_low_usage"
            annual = q2(current * 12)
        elif price_up:
            kind = "price_up"
            annual = q2((current - previous) * 12)
        else:
            kind = "low_usage"
            annual = q2(current * 12)
        issues.append({
            "kind": kind, "subscription_id": s.id, "name": s.name,
            "previous_amount": previous, "current_amount": current,
            "annual_impact": annual, "usage_90d": int(s.usage_90d or 0),
            "message": f"{s.name} " + "，".join(parts) + f"；按暂停估算年化影响 ¥{annual}",
        })

    month = current_month()
    dup_rows = db.execute(
        select(Bill.remark, Bill.amount, func.count())
        .where(*month_condition(user_id, month, "expense"),
               Bill.source == "subscription")
        .group_by(Bill.remark, Bill.amount)
        .having(func.count() > 1)).all()
    for remark, amount, count in dup_rows:
        issues.append({
            "kind": "duplicate", "name": remark or "订阅扣费",
            "current_amount": q2(amount), "count": int(count),
            "annual_impact": q2(Decimal(str(amount)) * (count - 1)),
            "message": f"{remark or '订阅扣费'} 本月出现 {count} 次，可能重复扣款",
        })
    # 涨价/涨价+低频优先展示，其次按年化影响从高到低
    issues.sort(key=lambda i: (i["kind"] not in ("price_up", "price_up_low_usage"),
                               -float(i.get("annual_impact") or 0)))
    return issues


# ---------------- 自然语言槽位（无模型时的规则兜底） ----------------

_CATEGORY_KEYWORDS = {
    "餐饮": ["吃", "饭", "咖啡", "奶茶", "早餐", "午餐", "晚餐", "外卖", "拉面", "火锅"],
    "交通": ["打车", "地铁", "公交", "油", "停车", "高铁", "机票", "滴滴"],
    "购物": ["买", "淘宝", "京东", "衣服", "鞋", "超市", "日用品"],
    "住房": ["房租", "水电", "物业", "住宿"],
    "学习": ["书", "课程", "培训", "学费", "考试"],
    "娱乐": ["电影", "游戏", "会员", "KTV", "演出"],
    "医疗": ["药", "医院", "挂号", "体检"],
    "通讯": ["话费", "流量", "宽带"],
}


def guess_category(text: str, categories: list[str]) -> str:
    for name, words in _CATEGORY_KEYWORDS.items():
        if any(w in text for w in words) and name in categories:
            return name
    return "其他" if "其他" in categories else (categories[0] if categories else "其他")


def parse_bill_fallback(text: str, categories: list[str]) -> dict:
    clean = text.replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)", clean)
    amount = Decimal(match.group(1)) if match else None
    if amount is None:
        cn_match = re.search(r"([零一二两三四五六七八九十百千万]+)\s*(元|块)?", clean)
        if cn_match:
            number = _cn_to_int(cn_match.group(1))
            if number:
                amount = Decimal(number)
    # 口语金额：十五块五 / 3块5 / 十二元八角 → 15.5 / 3.5 / 12.8
    if amount is not None:
        decimal_match = re.search(r"(?:元|块)\s*([零一二两三四五六七八九])(?:毛|角)?", clean)
        if decimal_match:
            amount += Decimal(_CN_DIGITS[decimal_match.group(1)]) / Decimal("10")
        else:
            decimal_match = re.search(r"(?:元|块)\s*(\d)(?:毛|角)?", clean)
            if decimal_match:
                amount += Decimal(decimal_match.group(1)) / Decimal("10")
    income_words = ["收入", "工资", "退款", "收到", "红包", "报销", "到账"]
    type_ = "income" if any(w in text for w in income_words) else "expense"
    category = guess_category(text, categories)
    remark = text.strip()[:60]
    bill_date = date.today()
    if "前天" in text:
        bill_date = date.today() - timedelta(days=2)
    elif "昨天" in text:
        bill_date = date.today() - timedelta(days=1)
    elif "明天" in text:
        bill_date = date.today() + timedelta(days=1)
    return {
        "type": type_, "amount": amount, "category": category,
        "bill_date": bill_date.isoformat(), "remark": remark,
        "missing_fields": [] if amount is not None else ["amount"],
    }


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def _cn_to_int(text: str) -> int | None:
    """把常见中文数字转成整数。

    支持 十五、三千、一万、两百，以及口语省略单位：
    一百二=120、三千五=3500、一万二=12000、一千二=1200、两百五=250；
    带“零”时按字面处理：一百零二=102、一千零五十=1050。
    """
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    section = 0
    number = 0
    last_unit = 0
    zero_flag = False
    for char in text:
        if char in _CN_DIGITS:
            if char == "零":
                zero_flag = True
                number = 0
            else:
                number = _CN_DIGITS[char]
        elif char in _CN_UNITS:
            unit = _CN_UNITS[char]
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
                number = 0
            else:
                section += (number or 1) * unit
                number = 0
            last_unit = unit
            zero_flag = False
        else:
            return None
    if number:
        # 口语省略：最后一个数字承接上一个单位的下一档
        if last_unit in (10, 100, 1000, 10000) and not zero_flag:
            number *= max(1, last_unit // 10)
        section += number
    return total + section


def _parse_number(token: str, unit: str | None) -> Decimal | None:
    if token.isdigit() or re.fullmatch(r"\d+\.\d+", token):
        value = Decimal(token)
    else:
        number = _cn_to_int(token)
        if number is None:
            return None
        value = Decimal(number)
    if unit == "万":
        value *= 10000
    elif unit == "千":
        value *= 1000
    return value


def parse_goal(text: str) -> dict:
    """解析目标金额与周期；缺金额或缺周期时返回 missing，由编排器澄清。

    支持：3个月/半年/一年/X年、每月存500、中文数字（三千/一万/两百）、
    以及“3个月存3000”“半年存1万”这类组合。
    """
    text = text.strip()
    months: int | None = None
    monthly_amount: Decimal | None = None

    # 周期：支持阿拉伯数字和中文数字（3个月/三个月/两年/半年/一年）
    match = re.search(r"(\d+)\s*个?\s*月", text)
    if match:
        months = int(match.group(1))
    else:
        match = re.search(r"([零一二两三四五六七八九十百]+)\s*个?\s*月", text)
        if match:
            months = _cn_to_int(match.group(1))
    if months is None:
        if "半年" in text:
            months = 6
        elif re.search(r"一年|1\s*年", text):
            months = 12
        else:
            match = re.search(r"(\d+)\s*年", text)
            if match:
                months = int(match.group(1)) * 12
            else:
                match = re.search(r"([零一二两三四五六七八九十百]+)\s*年", text)
                if match:
                    value = _cn_to_int(match.group(1))
                    months = value * 12 if value else None

    # 每月存 X
    match = re.search(
        r"(?:每月|每个月)\s*(?:存|攒|存下)?\s*"
        r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+)\s*(万|千|元|块)?",
        text)
    if match:
        monthly_amount = _parse_number(match.group(1), match.group(2))

    # 总金额：排除周期数字（3个月/1年）和每月金额。
    # 先去掉“一下/一点/一起”等口语词，避免把“计划一下”里的“一”当成 1 元。
    amount_text = text
    for word in ("一下", "一起", "一样", "一直", "一定", "一点", "一些",
                 "一份", "一边", "一次"):
        amount_text = amount_text.replace(word, "")
    candidates: list[Decimal] = []
    for match in re.finditer(
            r"(\d+(?:\.\d+)?|[零一二两三四五六七八九十百千万]+)\s*(万|千|元|块)?",
            amount_text):
        start, end = match.span()
        tail = text[end:end + 3]
        if "月" in tail or "年" in tail or "个" in tail:
            continue
        value = _parse_number(match.group(1), match.group(2))
        if value is None or value <= 0:
            continue
        candidates.append(value)
    amount = max(candidates) if candidates else None
    if monthly_amount is not None and amount == monthly_amount:
        amount = None
    if amount is None and monthly_amount is not None and months:
        amount = monthly_amount * months

    if amount is None and monthly_amount is None:
        missing = ["target_amount"]
    elif months is None:
        missing = ["months"]
    else:
        missing = []

    if "旅行" in text:
        name = "旅行基金"
    elif "电脑" in text:
        name = "买电脑"
    elif "房" in text:
        name = "买房"
    elif "车" in text:
        name = "买车"
    else:
        # 没有明确消费对象时不要从“在半年内攒下”里截出“在内下”这类碎片
        name = "储蓄目标"

    return {
        "amount": amount,
        "months": months,
        "monthly_amount": monthly_amount,
        "missing": missing,
        "name": name[:50],
    }
