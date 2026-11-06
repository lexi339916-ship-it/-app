"""SQLAlchemy ORM 模型，与 database/schema.sql 保持一致。"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    CHAR, BigInteger, Date, DateTime, DECIMAL, Enum, Index, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import MEDIUMTEXT

from app.database import Base

# 主键类型：MySQL 用 BIGINT；SQLite 需要 INTEGER 才能自增
PKType = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # 头像以 256×256 JPEG data URL 存储，避免引入静态文件目录和额外部署配置
    avatar: Mapped[str] = mapped_column(
        Text().with_variant(MEDIUMTEXT, "mysql"), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


class BillCategory(Base):
    __tablename__ = "bill_categories"
    __table_args__ = (UniqueConstraint("user_id", "name", "type", name="uq_category_user_name_type"),)

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    # user_id 为 NULL 表示系统预置分类，所有用户可见；非空表示用户自定义
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    type: Mapped[str] = mapped_column(Enum("income", "expense"), nullable=False)


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    type: Mapped[str] = mapped_column(Enum("income", "expense"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    bill_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # 数据来源可追溯：manual=手动录入，ai=AI 草稿确认后保存，receipt=截图识别，subscription=订阅自动扣费
    source: Mapped[str] = mapped_column(String(12), nullable=False, default="manual")
    # 支付渠道（如 微信支付/支付宝/银行卡）与扣款账户（如 零钱/工商银行储蓄卡）
    pay_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    funding_account: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (Index("idx_bill_user_date", "user_id", "bill_date"),)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    note_type: Mapped[str] = mapped_column(Enum("note", "todo"), nullable=False, default="note")
    status: Mapped[str] = mapped_column(Enum("open", "done"), nullable=False, default="open")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 任务管理扩展：优先级（high/medium/low）、置顶与任务颜色
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="lilac")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (Index("idx_note_user_status", "user_id", "status"),)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "month", name="uq_budget_user_month"),)

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    month: Mapped[str] = mapped_column(CHAR(7), nullable=False)  # 格式：2026-10
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)


class AICallLog(Base):
    """AI 调用日志：保留功能、提示词版本、模型、耗时与结果，满足可复现要求。"""
    __tablename__ = "ai_call_logs"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    feature: Mapped[str] = mapped_column(String(30), nullable=False)   # parse_bill / parse_note / summary
    prompt_version: Mapped[str] = mapped_column(String(10), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)   # success / error / limited
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_msg: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    input_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (Index("idx_ai_log_user_date", "user_id", "created_at"),)


class SavingsGoal(Base):
    """储蓄目标：目标金额 + 已存入金额；预计完成时间由后端按月均结余计算。"""
    __tablename__ = "savings_goals"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    saved_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)
    # Agent 目标规划：保存周期，避免审批后“3 个月”这个信息丢失
    target_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class GoalDeposit(Base):
    """储蓄目标的单笔存入记录：支持事后修改/删除某一笔，saved_amount 同步联动。"""
    __tablename__ = "goal_deposits"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    goal_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (Index("idx_goal_deposit_goal", "goal_id"),)


class Challenge(Base):
    """生活挑战：限定周期内某分类支出不超过上限；进度由上期对比与账单统计计算。"""
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    target_amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


# ========== AI 消费预警 & 预算模块（新增模型，不影响已有表） ==========


class CategoryBudget(Base):
    """分类月度预算：每用户每分类每月一条；source 标记手动设置或 AI 推荐。"""
    __tablename__ = "category_budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "month", name="uq_cb_user_cat_month"),
    )

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    category_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    month: Mapped[str] = mapped_column(CHAR(7), nullable=False)  # 格式：2026-10
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


class BudgetAlert(Base):
    """预警消息：80%提醒 / 100%超支 / 异常大额 / 弹性调度 / 计划采购，统一入消息中心。"""
    __tablename__ = "budget_alerts"
    __table_args__ = (
        # 同一分类同一月同一类型只推一次，防止重复打扰；anomaly 的 category 语义不同，单独处理
        UniqueConstraint("user_id", "category_id", "month", "alert_type", name="uq_alert_once"),
        Index("idx_alert_user_month", "user_id", "month", "status"),
    )

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    month: Mapped[str] = mapped_column(CHAR(7), nullable=False)
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    suggestion: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="")  # JSON 扩展数据
    related_bill_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="unread")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BudgetPlan(Base):
    """AI 预算方案：自然语言存钱目标/历史推荐 → 分配结果留痕，可一键采纳。"""
    __tablename__ = "budget_plans"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    month: Mapped[str] = mapped_column(CHAR(7), nullable=False)
    goal_text: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    income_estimate: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)
    total_budget: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False, default=0)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    applied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)


# ========== 自动订阅扣费（新增模型，不影响已有表） ==========


class Subscription(Base):
    """周期性固定支出订阅：由用户手动录入，不抓取任何第三方平台续费状态。

    - day_of_month：每月扣费日期（1~31，遇到小月自动取当月最后一天）
    - last_billed_month：已自动生成账单的月份（YYYY-MM），保证每月只生成一笔
    - remind_month：已推送过「扣费前 1 天」提醒的月份，避免同一条反复弹窗
    """
    __tablename__ = "subscriptions"
    __table_args__ = (Index("idx_sub_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    day_of_month: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    # 自动记账归入的支出分类；NULL 表示未指定，生成账单时归入「其他」
    category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # 订阅体检用：上一次价格（用于发现涨价）与近 90 天使用次数（用于发现低频订阅）
    previous_amount: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2), nullable=True)
    usage_90d: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    remind_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")  # active / paused
    last_billed_month: Mapped[str] = mapped_column(CHAR(7), nullable=False, default="")
    remind_month: Mapped[str] = mapped_column(CHAR(7), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)


# ========== 订阅计费记录（幂等 + 跨月补单） ==========

class SubscriptionBilling(Base):
    """订阅每月计费留痕：subscription_id + month 唯一，保证并发/重复 sync 不重复记账。"""
    __tablename__ = "subscription_billings"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    subscription_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    month: Mapped[str] = mapped_column(CHAR(7), nullable=False)
    bill_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(DECIMAL(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("subscription_id", "month", name="uq_sub_billing_sub_month"),
        Index("idx_sub_billing_user", "user_id", "month"),
    )


# ========== Agent 运行时（新增，不影响已有表） ==========

class AgentRun(Base):
    """一次 Agent 任务：goal 是用户原话，plan_json/answer/evidence_json 均可追溯。

    多轮对话：session_id 相同的任务属于同一对话，parent_run_id 指向上一轮，
    turn_index 从 0 递增；审批状态仍按 approval 独立，不跨轮混淆。
    """
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True)
    parent_run_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goal: Mapped[str] = mapped_column(String(500), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    answer: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    cost: Mapped[Decimal] = mapped_column(DECIMAL(10, 4), nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_agent_run_user", "user_id", "created_at"),
        Index("idx_agent_run_session", "user_id", "session_id", "turn_index"),
    )


class AgentStep(Base):
    """Agent 步骤：只记录工具调用/计划/审批等可验证动作，不存模型原始思维链。"""
    __tablename__ = "agent_steps"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(20), nullable=False)  # plan/tool/approval/execute/verify
    tool_name: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    args_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")
    error: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "seq", name="uq_agent_step_run_seq"),
        Index("idx_agent_step_run", "run_id", "seq"),
    )


class AgentApproval(Base):
    """写操作审批：先出 diff，用户批准后才执行；idempotency_key 保证重复批准不重复写入。"""
    __tablename__ = "agent_approvals"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    step_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action_type: Mapped[str] = mapped_column(String(30), nullable=False, default="multi")
    diff_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (Index("idx_agent_approval_run", "run_id", "status"),)


class AgentMemory(Base):
    """Agent 记忆：画像/目标/纠正/最近动作；用户可查看和删除。"""
    __tablename__ = "agent_memories"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="profile")
    mem_key: Mapped[str] = mapped_column(String(80), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("user_id", "kind", "mem_key", name="uq_agent_memory_user_kind_key"),
        Index("idx_agent_memory_user", "user_id", "kind"),
    )


class AgentNotification(Base):
    """主动扫描产生的通知：去重、未读/已读/忽略，作为 Agent 的“今日建议”。"""
    __tablename__ = "agent_notifications"

    id: Mapped[int] = mapped_column(PKType, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    suggestion: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    category: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    amount: Mapped[Decimal | None] = mapped_column(DECIMAL(12, 2), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="unread")
    dedupe_key: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_agent_notif_user_key"),
        Index("idx_agent_notif_user", "user_id", "status", "created_at"),
    )

