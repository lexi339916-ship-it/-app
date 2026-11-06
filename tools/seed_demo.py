"""生成/重置比赛演示账号 judge_demo 的数据。

用法（项目根目录）：
    python tools/seed_demo.py          # 重置并生成演示数据
    python tools/reset_demo.py         # 只重置后重新生成（同一个入口）

数据全部为合成数据，不包含任何真实用户信息。
"""
import calendar
import os
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if not (BACKEND / "app").exists():
    BACKEND = ROOT  # Docker 镜像中 app/ 与 tools/ 同级
sys.path.insert(0, str(BACKEND))

# 必须在导入 app.* 之前指定数据库，避免误写 .env 里的正式库
if "DATABASE_URL" not in os.environ:
    default_db = (BACKEND / "smart_life.db").resolve()
    os.environ["DATABASE_URL"] = f"sqlite:///{default_db.as_posix()}"

from sqlalchemy import select  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import _ensure_schema_patches, seed_default_categories  # noqa: E402
from app.models import (  # noqa: E402
    AICallLog, AgentApproval, AgentMemory, AgentNotification, AgentRun, AgentStep,
    AgentSessionArchive,
    AssetAccount, AssetLiability, AssetTransaction,
    Bill, BillCategory, Budget, BudgetAlert, BudgetPlan, CategoryBudget, Challenge,
    GoalDeposit, Note, SavingsGoal, Subscription, SubscriptionBilling, User,
)
from app.security import hash_password  # noqa: E402
from app.services import asset_service  # noqa: E402

DEMO_USERNAME = "judge_demo"
DEMO_PASSWORD = "judge2026"
CURRENT_MONTH = date.today().strftime("%Y-%m")
MONTHS = []
_today = date.today()
for offset in range(5, -1, -1):
    year, month = _today.year, _today.month - offset
    while month < 1:
        year, month = year - 1, month + 12
    MONTHS.append(f"{year:04d}-{month:02d}")


def _month_days(month_key: str) -> int:
    year, month = int(month_key[:4]), int(month_key[5:7])
    return calendar.monthrange(year, month)[1]


def _day(month_key: str, day: int) -> date:
    year, month = int(month_key[:4]), int(month_key[5:7])
    # 本月只生成今天及以前的账单，避免未来日期污染“最近账单”
    if month_key == CURRENT_MONTH:
        day = min(day, _today.day)
    return date(year, month, min(day, _month_days(month_key)))


def reset_demo(db, user: User) -> None:
    run_ids = select(AgentRun.id).where(AgentRun.user_id == user.id)
    db.query(AgentStep).filter(AgentStep.run_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(AgentApproval).filter(AgentApproval.run_id.in_(run_ids)).delete(synchronize_session=False)
    db.query(AgentRun).filter(AgentRun.user_id == user.id).delete(synchronize_session=False)
    db.query(AgentMemory).filter(AgentMemory.user_id == user.id).delete(synchronize_session=False)
    db.query(AgentNotification).filter(AgentNotification.user_id == user.id).delete(synchronize_session=False)
    db.query(AgentSessionArchive).filter(AgentSessionArchive.user_id == user.id).delete(synchronize_session=False)
    db.query(AssetTransaction).filter(AssetTransaction.user_id == user.id).delete(synchronize_session=False)
    db.query(AssetAccount).filter(AssetAccount.user_id == user.id).delete(synchronize_session=False)
    db.query(AssetLiability).filter(AssetLiability.user_id == user.id).delete(synchronize_session=False)
    db.query(GoalDeposit).filter(GoalDeposit.user_id == user.id).delete(synchronize_session=False)
    db.query(Bill).filter(Bill.user_id == user.id).delete(synchronize_session=False)
    db.query(Note).filter(Note.user_id == user.id).delete(synchronize_session=False)
    db.query(SavingsGoal).filter(SavingsGoal.user_id == user.id).delete(synchronize_session=False)
    db.query(Subscription).filter(Subscription.user_id == user.id).delete(synchronize_session=False)
    db.query(SubscriptionBilling).filter(SubscriptionBilling.user_id == user.id).delete(synchronize_session=False)
    db.query(CategoryBudget).filter(CategoryBudget.user_id == user.id).delete(synchronize_session=False)
    db.query(Budget).filter(Budget.user_id == user.id).delete(synchronize_session=False)
    db.query(BudgetAlert).filter(BudgetAlert.user_id == user.id).delete(synchronize_session=False)
    db.query(BudgetPlan).filter(BudgetPlan.user_id == user.id).delete(synchronize_session=False)
    db.query(Challenge).filter(Challenge.user_id == user.id).delete(synchronize_session=False)
    db.query(AICallLog).filter(AICallLog.user_id == user.id).delete(synchronize_session=False)
    db.commit()


def add_bill(db, user: User, cats: dict[str, int], month: str, day: int,
             category: str, amount: str, remark: str, type_: str = "expense",
             source: str = "manual", channel: str = "微信") -> None:
    db.add(Bill(
        user_id=user.id, category_id=cats.get(category), type=type_,
        amount=Decimal(amount), bill_date=_day(month, day), remark=remark,
        source=source, pay_channel=channel if type_ == "expense" else "",
        funding_account=""))


def seed_assets(db, user: User, cats: dict[str, int]) -> None:
    """合成资产演示数据：4 个账户、2 个负债、1 笔转账、部分账单关联。

    这些数据只用于演示；不包含真实用户账户，也不代表真实余额。
    """
    db.flush()
    now = datetime.now()
    opening_at = now - timedelta(days=180)
    bank = AssetAccount(
        user_id=user.id, name="招商银行储蓄卡", type="bank",
        institution="招商银行", account_hint="6789",
        balance=Decimal("18600.00"), note="工资卡", is_active=1)
    wechat = AssetAccount(
        user_id=user.id, name="微信零钱", type="wechat",
        institution="微信", balance=Decimal("2000.00"), is_active=1)
    alipay = AssetAccount(
        user_id=user.id, name="支付宝余额", type="alipay",
        institution="支付宝", balance=Decimal("1240.00"), is_active=1)
    savings = AssetAccount(
        user_id=user.id, name="应急储蓄", type="savings",
        institution="招商银行", balance=Decimal("8000.00"),
        note="至少保留 1 个月开支", is_active=1)
    property_asset = AssetAccount(
        user_id=user.id, name="自住房产", type="property",
        institution="不动产", balance=Decimal("800000.00"),
        note="按当前估值（演示数据）", is_active=1)
    vehicle = AssetAccount(
        user_id=user.id, name="家用车", type="vehicle",
        institution="家用车", balance=Decimal("80000.00"),
        note="按当前二手估值（演示数据）", is_active=1)
    investment = AssetAccount(
        user_id=user.id, name="稳健理财", type="investment",
        institution="银行理财", balance=Decimal("30000.00"),
        note="低风险理财，不构成投资建议（演示数据）", is_active=1)
    valuables = AssetAccount(
        user_id=user.id, name="收藏与贵重物品", type="valuables",
        balance=Decimal("20000.00"), note="按保守估值（演示数据）", is_active=1)
    accounts = [bank, wechat, alipay, savings,
                property_asset, vehicle, investment, valuables]
    db.add_all(accounts)
    db.flush()

    # 初始余额流水放在半年前，避免污染“本月净资产变化”演示
    for account in accounts:
        amount = Decimal(str(account.balance))
        db.add(AssetTransaction(
            user_id=user.id, account_id=account.id, type="opening",
            direction="in", amount=amount, before_amount=Decimal("0"),
            after_amount=amount, note="初始余额", source="manual",
            status="posted", created_at=opening_at))

    # 账户间转账：只写两条流水，不生成账单
    transfer_at = now - timedelta(days=2)
    group = f"demo-transfer-{user.id}"
    bank.balance = Decimal("18100.00")
    alipay.balance = Decimal("1740.00")
    db.add_all([
        AssetTransaction(
            user_id=user.id, account_id=bank.id, type="transfer_out",
            direction="out", amount=Decimal("500.00"),
            before_amount=Decimal("18600.00"), after_amount=Decimal("18100.00"),
            note="转到支付宝余额", source="manual", transfer_group_id=group,
            status="posted", created_at=transfer_at),
        AssetTransaction(
            user_id=user.id, account_id=alipay.id, type="transfer_in",
            direction="in", amount=Decimal("500.00"),
            before_amount=Decimal("1240.00"), after_amount=Decimal("1740.00"),
            note="来自招商银行储蓄卡", source="manual", transfer_group_id=group,
            status="posted", created_at=transfer_at),
    ])

    # 负债：信用卡 + 教育分期
    card = AssetLiability(
        user_id=user.id, name="招行信用卡", type="credit_card",
        outstanding=Decimal("1280.00"),
        due_date=date.today() + timedelta(days=10),
        remark="本月账单", status="active", is_active=1)
    installment = AssetLiability(
        user_id=user.id, name="课程分期", type="installment",
        outstanding=Decimal("600.00"),
        due_date=date.today() + timedelta(days=20),
        remark="还有 3 期", status="active", is_active=1)
    mortgage = AssetLiability(
        user_id=user.id, name="房贷余额", type="personal_loan",
        outstanding=Decimal("400000.00"), due_date=None,
        remark="按当前剩余贷款估算（演示数据）",
        status="active", is_active=1)
    db.add_all([card, installment, mortgage])
    db.flush()
    for liability in (card, installment, mortgage):
        amount = Decimal(str(liability.outstanding))
        db.add(AssetTransaction(
            user_id=user.id, liability_id=liability.id,
            type="liability_increase", direction="in", amount=amount,
            before_amount=Decimal("0"), after_amount=amount,
            note="初始欠款", source="manual", status="posted",
            created_at=now - timedelta(days=90)))

    # 当前月部分账单关联账户，给净资产变化/覆盖率演示提供真实联动
    links = [
        ("每月工资", bank),
        ("房租", bank),
        ("日常餐饮", wechat),
        ("日用品与网购", alipay),
    ]
    for remark, account in links:
        bill = db.scalar(
            select(Bill).where(Bill.user_id == user.id, Bill.remark == remark)
            .order_by(Bill.bill_date.desc(), Bill.id.desc()).limit(1))
        if bill and bill.bill_date.strftime("%Y-%m") == CURRENT_MONTH:
            bill.account_id = account.id
            asset_service.post_bill_movement(db, user, bill)


def seed(db, user: User) -> None:
    cats = {}
    for row in db.scalars(select(BillCategory).where(BillCategory.user_id.is_(None))).all():
        cats.setdefault(row.name, row.id)

    # 近 6 个月：收入 + 固定/日常支出，保证目标规划有真实历史
    for index, month in enumerate(MONTHS):
        add_bill(db, user, cats, month, 10, "工资", "9000.00", "每月工资",
                 type_="income", channel="")
        add_bill(db, user, cats, month, 1, "住房", "2500.00", "房租", channel="银行卡")
        add_bill(db, user, cats, month, 6, "交通", "120.00", "地铁公交", channel="支付宝")
        add_bill(db, user, cats, month, 8, "通讯", "100.00", "手机话费", channel="支付宝")
        add_bill(db, user, cats, month, 12, "学习", "100.00", "课程/书籍", channel="微信")
        # 可自由支配支出：近 6 个月逐月略增，给目标规划留出压缩空间
        food = ["980.00", "1020.00", "1060.00", "1100.00", "1140.00", "1180.00"][index]
        shopping = ["500.00", "520.00", "540.00", "560.00", "570.00", "580.00"][index]
        entertainment = ["320.00", "340.00", "360.00", "380.00", "400.00", "420.00"][index]
        add_bill(db, user, cats, month, 3, "餐饮", food, "日常餐饮", channel="微信")
        add_bill(db, user, cats, month, 5, "购物", shopping, "日用品与网购", channel="支付宝")
        add_bill(db, user, cats, month, 7, "娱乐", entertainment, "电影/游戏/会员", channel="微信")
        add_bill(db, user, cats, month, 9, "其他", "80.00", "杂项", channel="微信")
        if month != CURRENT_MONTH:
            add_bill(db, user, cats, month, 4, "餐饮", "60.00", "朋友聚餐", channel="微信")
            add_bill(db, user, cats, month, 11, "交通", "80.00", "打车", channel="微信")

    # 本月分类预算：餐饮 1180/1200 接近上限，方便演示“记账后超支→调配”
    budgets = {
        "餐饮": "1200.00", "交通": "400.00", "购物": "600.00", "娱乐": "500.00",
        "住房": "2500.00", "学习": "300.00", "医疗": "200.00", "通讯": "100.00",
        "其他": "200.00",
    }
    for name, amount in budgets.items():
        if name in cats:
            db.add(CategoryBudget(user_id=user.id, category_id=cats[name],
                                  month=CURRENT_MONTH, amount=Decimal(amount),
                                  source="manual"))
    db.add(Budget(user_id=user.id, month=CURRENT_MONTH, amount=Decimal("6000.00")))

    # 订阅：视频会员涨价 + 低频；健身会员低频；云存储正常
    video_cat = cats.get("娱乐")
    cloud_cat = cats.get("通讯")
    db.add(Subscription(
        user_id=user.id, name="视频会员", day_of_month=15, amount=Decimal("30.00"),
        category_id=video_cat, previous_amount=Decimal("25.00"), usage_90d=1,
        remark="去年 25 元，本月涨到 30 元", remind_enabled=1, status="active",
        last_billed_month="", remind_month=""))
    db.add(Subscription(
        user_id=user.id, name="健身会员", day_of_month=5, amount=Decimal("199.00"),
        category_id=video_cat, previous_amount=None, usage_90d=0,
        remark="近 3 个月没去过", remind_enabled=1, status="active",
        last_billed_month="", remind_month=""))
    db.add(Subscription(
        user_id=user.id, name="云存储", day_of_month=20, amount=Decimal("12.00"),
        category_id=cloud_cat, previous_amount=None, usage_90d=8,
        remark="每月自动续费", remind_enabled=1, status="active",
        last_billed_month="", remind_month=""))

    # 本月一条订阅扣费账单（用于订阅体检/统计）
    add_bill(db, user, cats, CURRENT_MONTH, 2, "娱乐", "30.00",
             "视频会员 · 自动订阅扣费", source="subscription", channel="微信")

    # 储蓄目标 + 待办
    db.add(SavingsGoal(user_id=user.id, name="旅行基金",
                       target_amount=Decimal("3000.00"), saved_amount=Decimal("500.00")))
    notes = [
        ("月底复盘视频会员是否恢复", "视频会员涨价了，先暂停一个月，月底按使用情况决定。", 2, "high"),
        ("买一双跑鞋 600", "计划采购，提前留出预算。", 10, "medium"),
        ("交下个月房租 2500", "每月固定支出，别忘了。", 5, "high"),
    ]
    for title, content, days, priority in notes:
        db.add(Note(user_id=user.id, title=title, content=content,
                    note_type="todo", status="open",
                    due_at=datetime.now() + timedelta(days=days),
                    priority=priority, pinned=0, color="lilac"))

    seed_assets(db, user, cats)
    db.commit()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_schema_patches()
    seed_default_categories()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.username == DEMO_USERNAME))
        if user is None:
            user = User(username=DEMO_USERNAME, password_hash=hash_password(DEMO_PASSWORD),
                        nickname="演示用户")
            db.add(user)
            db.commit()
            db.refresh(user)
        reset_demo(db, user)
        seed(db, user)
        bills = db.query(Bill).filter(Bill.user_id == user.id).count()
        notes_count = db.query(Note).filter(Note.user_id == user.id).count()
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).count()
        print(f"演示账号已就绪：{DEMO_USERNAME} / {DEMO_PASSWORD}")
        print(f"数据：{bills} 笔账单、{notes_count} 条便签/待办、{subs} 个订阅、"
              f"当前月 {CURRENT_MONTH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
