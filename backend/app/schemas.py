"""接口出入参契约（Pydantic）。"""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import version

# ---------- 认证 ----------

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=32)
    nickname: str = Field(default="", max_length=30)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=32)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    nickname: str
    avatar: str = ""
    created_at: datetime

    @field_validator("avatar", mode="before")
    @classmethod
    def _avatar_none_to_empty(cls, value):
        return value or ""


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10)


class ProfileUpdateIn(BaseModel):
    nickname: str = Field(default="", max_length=30)
    old_password: str = Field(default="", max_length=32)
    new_password: str = Field(default="", max_length=32)


# ---------- 分类 ----------

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    type: Literal["income", "expense"]


class CategoryOut(BaseModel):
    id: int
    name: str
    type: str
    is_system: bool


# ---------- 账单 ----------

class BillIn(BaseModel):
    type: Literal["income", "expense"]
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: str = Field(min_length=1, max_length=40)
    bill_date: date
    remark: str = Field(default="", max_length=200)
    # manual=手动录入；ai=AI 草稿确认后保存；receipt=截图识别确认后保存（可追溯）
    source: Literal["manual", "ai", "receipt", "agent", "csv", "subscription"] = "manual"
    pay_channel: str = Field(default="", max_length=20)
    funding_account: str = Field(default="", max_length=40)
    # 可选：关联资产账户；新建账单会同步账户余额，旧账单补关联不追溯
    account_id: int | None = None


class BillOut(BaseModel):
    id: int
    type: str
    amount: Decimal
    category: str
    category_id: int | None
    account_id: int | None = None
    account_name: str = ""
    bill_date: date
    remark: str
    source: str
    pay_channel: str
    funding_account: str
    created_at: datetime


class BillPageOut(BaseModel):
    items: list[BillOut]
    total: int
    page: int
    page_size: int


# ---------- 便签 ----------

class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(default="", max_length=5000)
    note_type: Literal["note", "todo"] = "note"
    status: Literal["open", "done"] = "open"
    due_at: datetime | None = None
    priority: Literal["high", "medium", "low"] = "medium"
    pinned: bool = False
    color: str = Field(default="lilac", max_length=20)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    content: str
    note_type: str
    status: str
    due_at: datetime | None
    priority: str
    pinned: bool
    color: str
    is_overdue: bool
    created_at: datetime
    updated_at: datetime


class NotePageOut(BaseModel):
    items: list[NoteOut]
    total: int
    pending_count: int


# ---------- 预算 ----------

class BudgetIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class BudgetOut(BaseModel):
    month: str
    amount: Decimal
    spent: Decimal
    remaining: Decimal
    usage_ratio: float  # 0~1，已用比例


# ---------- 统计 ----------

class DayPoint(BaseModel):
    date: date
    expense: Decimal
    income: Decimal


class MonthlyStatsOut(BaseModel):
    month: str
    income: Decimal
    expense: Decimal
    net: Decimal
    count: int
    days: list[DayPoint]


class CategoryStatItem(BaseModel):
    category: str
    amount: Decimal
    ratio: float


class CategoryStatsOut(BaseModel):
    month: str
    type: str
    total: Decimal
    items: list[CategoryStatItem]


class ChannelStatItem(BaseModel):
    channel: str
    amount: Decimal
    count: int
    ratio: float


class ChannelStatsOut(BaseModel):
    month: str          # 空字符串表示全部时间
    type: str
    total: Decimal
    items: list[ChannelStatItem]


class ProfileStatsOut(BaseModel):
    """个人中心统计卡片数据。"""
    total_bills: int
    total_days: int
    total_notes: int
    pending_todos: int


# ---------- 储蓄目标 ----------

class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class GoalDepositIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class GoalDepositOut(BaseModel):
    """单笔存入记录（支持事后修改/删除某一笔）。"""
    model_config = ConfigDict(from_attributes=True)
    id: int
    goal_id: int
    amount: Decimal
    created_at: datetime


class GoalOut(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    remaining: Decimal
    progress_ratio: float          # 0~1（可超 1）
    estimated_finish: str | None    # 按近 3 个月平均月结余估算
    avg_monthly_net: Decimal
    target_months: int | None = None
    target_date: date | None = None


# ---------- 生活挑战 ----------

class ChallengeIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    category: str = Field(min_length=1, max_length=40)
    period_days: Literal[7, 30] = 7
    target_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class ChallengeOut(BaseModel):
    id: int
    name: str
    category: str
    period_days: int
    target_amount: Decimal
    start_date: date
    end_date: date
    current_spend: Decimal
    previous_spend: Decimal | None   # 上一个同长度周期的支出
    change_pct: float | None         # 环比变化百分比
    progress_ratio: float            # 当前已花 / 上限
    status: str                      # on_track / over / finished / failed
    days_left: int


# ---------- AI ----------

class ParseBillIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class BillDraft(BaseModel):
    """AI 生成的账单草稿：仅候选数据，必须经用户核对确认后才可保存。"""
    type: Literal["income", "expense"] = "expense"
    amount: Decimal | None = None
    category: str = "其他"
    bill_date: date | None = None
    remark: str = ""
    missing_fields: list[str] = Field(default_factory=list)


class ParseBillOut(BaseModel):
    drafts: list[BillDraft]
    notice: str = ""
    prompt_version: str
    model: str
    latency_ms: int


class ParseNoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class NoteDraft(BaseModel):
    title: str = ""
    content: str = ""
    note_type: Literal["note", "todo"] = "note"
    due_at: datetime | None = None
    priority: Literal["high", "medium", "low"] = "medium"
    missing_fields: list[str] = Field(default_factory=list)


class ParseNoteOut(BaseModel):
    drafts: list[NoteDraft]
    notice: str = ""
    prompt_version: str
    model: str
    latency_ms: int


class ReceiptDraft(BaseModel):
    """截图识别出的账单草稿：字段缺失一律标记待确认，不猜测。"""
    type: Literal["income", "expense"] = "expense"
    amount: Decimal | None = None
    merchant: str = ""
    category: str = "其他"
    bill_date: date | None = None
    bill_time: str = ""
    remark: str = ""
    status: Literal["success", "pending", "refunded", "failed", "unknown"] = "unknown"
    pay_channel: str = ""
    funding_account: str = ""
    missing_fields: list[str] = Field(default_factory=list)
    duplicate_suspect: bool = False
    duplicate_hint: str = ""


class ParseReceiptOut(BaseModel):
    found: bool = True
    drafts: list[ReceiptDraft]
    notice: str = ""
    prompt_version: str
    model: str
    latency_ms: int


class SummaryOut(BaseModel):
    month: str
    income: Decimal
    expense: Decimal
    net: Decimal
    top_categories: list[CategoryStatItem]
    summary: str
    notice: str
    prompt_version: str
    model: str


class InsightOut(BaseModel):
    """首页 AI 洞察：一句话消费提示（当日缓存，失败时规则降级）。"""
    text: str
    month: str
    cached: bool = False
    model: str = ""
    notice: str = ""


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=200)


class AskOut(BaseModel):
    """问账本：模型选择查询工具 → 后端执行 → 生成回答（多步任务可追踪）。"""
    answer: str
    tool: str = ""
    tool_params: dict = Field(default_factory=dict)
    data_used: dict = Field(default_factory=dict)
    steps: list[str] = Field(default_factory=list)
    prompt_version: str
    model: str
    latency_ms: int


# ---------- AI 消费预警 & 预算模块（新增，不影响已有契约） ----------

class CategoryBudgetIn(BaseModel):
    """设置单个分类月度预算。"""
    category_id: int
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class CategoryBudgetItem(BaseModel):
    """预算中心列表项：预算 + 已花 + 占比 + 状态。"""
    category_id: int
    category: str
    amount: Decimal
    spent: Decimal
    remaining: Decimal
    usage_ratio: float                    # 0~1，可超过 1
    status: str                           # none未设预算 / ok / near80 / used_up / over100
    source: str = "manual"


class BudgetOverviewOut(BaseModel):
    month: str
    total_budget: Decimal                 # 已设分类预算之和
    total_spent: Decimal                  # 已设预算分类的合计支出
    items: list[CategoryBudgetItem]


class CategoryBudgetBatchIn(BaseModel):
    """批量写入分类预算（AI 方案一键采纳）。"""
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    source: Literal["manual", "ai"] = "manual"
    items: list[CategoryBudgetIn] = Field(min_length=1, max_length=30)


class BillCheckIn(BaseModel):
    """记账保存后由前端追加调用：传入刚保存的账单ID，返回触发的预警。"""
    bill_id: int


class AlertOut(BaseModel):
    id: int
    alert_type: str
    level: str
    category: str = ""
    month: str
    title: str
    message: str
    suggestion: str = ""
    payload: dict = Field(default_factory=dict)
    related_bill_id: int | None = None
    status: str
    created_at: datetime


class BillCheckOut(BaseModel):
    alerts: list[AlertOut] = Field(default_factory=list)


class AlertPageOut(BaseModel):
    items: list[AlertOut]
    total: int
    unread_count: int


class AlertActionIn(BaseModel):
    """对预警消息的操作：read 已读 / dismissed 忽略 / accepted 采纳（弹性调配）。"""
    action: Literal["read", "dismissed", "accepted"]


class GoalAllocateIn(BaseModel):
    """自然语言存钱目标 → AI 分配预算。"""
    goal_text: str = Field(min_length=2, max_length=200)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class BudgetPlanItem(BaseModel):
    category_id: int
    category: str
    amount: Decimal
    reason: str = ""                      # AI 给出的分配理由


class BudgetPlanOut(BaseModel):
    id: int
    month: str
    goal_text: str = ""
    income_estimate: Decimal
    total_budget: Decimal
    items: list[BudgetPlanItem]
    comment: str = ""                     # AI 对方案的一句话说明
    applied: bool = False
    prompt_version: str = ""
    model: str = ""


class RebalanceSuggestion(BaseModel):
    """弹性调度建议：从结余分类调配额度到快超支分类。"""
    alert_id: int | None = None
    from_category_id: int
    from_category: str
    to_category_id: int
    to_category: str
    amount: Decimal                       # 建议调配金额
    message: str                          # 柔和建议文案（区分刚性/冲动消费）
    from_remaining: Decimal
    to_usage_ratio: float


class PlannedPurchaseOut(BaseModel):
    """待办联动：识别到的计划大额采购 + 资金压力预判。"""
    note_id: int
    title: str
    due_at: datetime | None = None
    estimated_amount: Decimal | None = None
    category: str = ""
    pressure_message: str = ""            # AI 资金压力提示文案


# ---------- 自动订阅扣费（新增，不影响已有契约） ----------

class SubscriptionIn(BaseModel):
    """用户手动录入的周期固定支出（不抓取任何第三方平台续费状态）。"""
    name: str = Field(min_length=1, max_length=60)
    day_of_month: int = Field(ge=1, le=31, description="每月扣费日期；小月自动取最后一天")
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category_id: int | None = Field(default=None, description="自动记账归入的支出分类；为空归入「其他」")
    usage_90d: int | None = Field(default=None, ge=0, le=1000,
                                  description="近 90 天使用次数；不填则新建默认 5，编辑时保持不变")
    remark: str = Field(default="", max_length=200)
    remind_enabled: bool = True


class SubscriptionOut(BaseModel):
    id: int
    name: str
    day_of_month: int
    amount: Decimal
    category_id: int | None = None        # 自动记账归入的支出分类，空表示「其他」
    previous_amount: Decimal | None = None  # 上次价格，用于订阅体检发现涨价
    usage_90d: int = 0                     # 近 90 天使用次数，用于发现低频订阅
    remark: str
    remind_enabled: bool
    status: str                          # active 进行中 / paused 已暂停
    next_charge_date: date               # 下一个扣费日（按服务器日期计算）
    days_left: int                       # 距下次扣费还有几天
    last_billed_month: str               # 已自动记账的月份，空表示本月尚未扣费
    created_at: datetime


class SubscriptionReminder(BaseModel):
    """扣费前 1 天的提醒项，由前端弹窗展示。"""
    id: int
    name: str
    amount: Decimal
    charge_date: date                    # 明天（实际扣费日）
    days_left: int
    remark: str = ""


class SubscriptionSyncOut(BaseModel):
    """进入账单页/打开小程序时调用：补生成到期账单 + 返回提醒。"""
    created_count: int = 0
    created_amount: Decimal = Decimal("0")
    active_count: int = 0
    reminders: list[SubscriptionReminder] = Field(default_factory=list)


# ---------- Agent 运行时 ----------

class AgentRunIn(BaseModel):
    message: str = Field(min_length=2, max_length=500)
    mode: Literal["auto", "query", "plan", "action"] = "auto"
    # 多轮对话：同一 session_id 视为同一线程；parent_run_id 指向上一轮
    session_id: str | None = Field(default=None, max_length=64)
    parent_run_id: int | None = None


class AgentSessionSummaryOut(BaseModel):
    session_id: str
    turn_count: int
    last_goal: str = ""
    last_status: str = ""
    last_at: datetime | None = None


class AgentStepOut(BaseModel):
    seq: int
    step_type: str
    tool_name: str = ""
    args: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    status: str = "ok"
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AgentApprovalOut(BaseModel):
    id: int
    run_id: int
    action_type: str
    diff: dict = Field(default_factory=dict)
    status: str
    created_at: datetime
    expires_at: datetime | None = None
    decided_at: datetime | None = None


class AgentRunOut(BaseModel):
    run_id: int
    status: str
    goal: str
    mode: str
    session_id: str = ""
    parent_run_id: int | None = None
    turn_index: int = 0
    plan: list[str] = Field(default_factory=list)
    answer: str = ""
    evidence: dict = Field(default_factory=dict)
    steps: list[AgentStepOut] = Field(default_factory=list)
    approvals: list[AgentApprovalOut] = Field(default_factory=list)
    cost: float = 0.0
    latency_ms: int = 0
    model: str = ""
    created_at: datetime
    finished_at: datetime | None = None


class AgentApprovalIn(BaseModel):
    decision: Literal["approved", "rejected"]
    edits: dict = Field(default_factory=dict)


class AgentScanItem(BaseModel):
    id: int | None = None
    alert_type: str
    level: str = "info"
    title: str
    message: str
    suggestion: str = ""
    category: str = ""
    amount: Decimal | None = None
    payload: dict = Field(default_factory=dict)
    status: str = "unread"


class AgentScanOut(BaseModel):
    items: list[AgentScanItem] = Field(default_factory=list)
    unread_count: int = 0
    scanned_at: datetime


class AgentNotificationOut(BaseModel):
    id: int
    alert_type: str
    level: str
    title: str
    message: str
    suggestion: str = ""
    category: str = ""
    amount: Decimal | None = None
    payload: dict = Field(default_factory=dict)
    status: str
    created_at: datetime


class AgentNotificationActionIn(BaseModel):
    action: Literal["read", "dismissed"]


class UnifiedNotificationOut(BaseModel):
    source: Literal["budget", "agent"]
    id: int
    alert_type: str
    level: str = "info"
    title: str
    message: str
    suggestion: str = ""
    category: str = ""
    amount: Decimal | None = None
    status: str = "unread"
    month: str = ""
    created_at: datetime
    read_at: datetime | None = None
    dedupe_key: str = ""
    remind_count: int = 0
    target_route: str = ""
    payload: dict = Field(default_factory=dict)
    related_count: int = 1


class NotificationSummaryOut(BaseModel):
    total_unread: int
    unique_unread: int
    budget_unread: int
    agent_unread: int
    by_level: dict[str, int] = Field(default_factory=dict)
    as_of: datetime


class UnifiedNotificationActionIn(BaseModel):
    action: Literal["read", "dismissed", "accepted"]


class NotificationReadAllOut(BaseModel):
    marked: int
    as_of: datetime


class AgentHealthOut(BaseModel):
    ok: bool = True
    service: str = version.AGENT_SERVICE_NAME
    version: str = version.APP_VERSION
    ai_configured: bool = False
    model: str = ""
    tools: int = 0


class AgentMemoryOut(BaseModel):
    id: int
    kind: str
    key: str
    value: dict = Field(default_factory=dict)
    updated_at: datetime


class VoiceTranscribeOut(BaseModel):
    text: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0


# ---------- 消费健康诊断 ----------
# 所有分数/金额均由后端 health_service 计算；这里只定义对外契约。

class HealthIndicatorOut(BaseModel):
    key: str
    name: str
    score: float | None = None
    level: str
    available: bool
    formula: str
    explanation: str
    inputs: dict = Field(default_factory=dict)
    source: str
    period: str
    as_of: str


class HealthOverviewOut(BaseModel):
    income: Decimal
    expense: Decimal
    net: Decimal
    savings_rate: float | None = None
    bill_count: int
    days_elapsed: int
    days_in_month: int
    avg_daily_expense: Decimal
    projected_expense: Decimal | None = None
    prev_expense: Decimal
    expense_change_amount: Decimal
    expense_change_ratio: float | None = None
    history_avg_expense: Decimal | None = None


class HealthCategoryOut(BaseModel):
    category_id: int | None = None
    category: str
    amount: Decimal
    ratio: float
    prev_amount: Decimal
    change_amount: Decimal
    change_ratio: float | None = None
    budget: Decimal
    budget_source: str
    usage_ratio: float | None = None
    budget_status: str
    remaining: Decimal


class HealthBudgetOut(BaseModel):
    available: bool
    total_budget: Decimal
    total_spent: Decimal
    remaining: Decimal
    usage_ratio: float | None = None
    over_count: int
    used_up_count: int = 0
    near_count: int
    overrun_amount: Decimal
    unbudgeted_amount: Decimal
    budgeted_category_count: int


class HealthGoalOut(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    remaining: Decimal
    progress_ratio: float
    target_date: date | None = None
    required_monthly: Decimal | None = None
    projected_finish: date | None = None
    delay_days: int | None = None
    status: str
    score: float | None = None
    avg_monthly_net: Decimal
    expected_progress: float | None = None


class HealthSubscriptionIssueOut(BaseModel):
    kind: str
    subscription_id: int | None = None
    name: str
    message: str
    previous_amount: Decimal | None = None
    current_amount: Decimal | None = None
    annual_impact: Decimal
    usage_90d: int | None = None
    count: int | None = None


class HealthSubscriptionOut(BaseModel):
    available: bool
    active_count: int
    monthly_amount: Decimal
    month_spent: Decimal
    prev_month_spent: Decimal
    change_amount: Decimal
    change_ratio: float | None = None
    share_of_expense: float | None = None
    monthly_income: Decimal | None = None
    income_burden: float | None = None
    issues: list[HealthSubscriptionIssueOut] = Field(default_factory=list)
    score: float | None = None


class HealthChangeOut(BaseModel):
    kind: str
    title: str
    detail: str
    category: str = ""
    amount: Decimal
    change_amount: Decimal | None = None
    change_ratio: float | None = None
    bill_date: str = ""
    source_ids: list[int] = Field(default_factory=list)


class HealthPlanOut(BaseModel):
    available: bool
    total: int
    done: int
    open: int
    score: float | None = None
    formula: str


class HealthRecommendationOut(BaseModel):
    title: str
    detail: str
    impact_amount: Decimal | None = None
    priority: str
    action_hint: str
    source: str


class HealthReportOut(BaseModel):
    month: str
    period_start: date
    period_end: date
    generated_at: str
    overview: HealthOverviewOut
    categories: list[HealthCategoryOut] = Field(default_factory=list)
    budget: HealthBudgetOut
    goals: list[HealthGoalOut] = Field(default_factory=list)
    subscriptions: HealthSubscriptionOut
    changes: list[HealthChangeOut] = Field(default_factory=list)
    anomalies: list[HealthChangeOut] = Field(default_factory=list)
    plan: HealthPlanOut
    indicators: list[HealthIndicatorOut] = Field(default_factory=list)
    overall_score: float | None = None
    overall_level: str
    weights: dict[str, float] = Field(default_factory=dict)
    weights_used: dict[str, float] = Field(default_factory=dict)
    coverage: float = 0.0
    summary: str
    recommendations: list[HealthRecommendationOut] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    disclaimer: str


# ---------- 消费决策模拟器 ----------

class DecisionSimulationIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    category: str = Field(default="购物", min_length=1, max_length=40)
    goal_id: int | None = None
    horizon_months: int = Field(default=3, ge=1, le=36)


class DecisionPurchaseOut(BaseModel):
    available: bool
    source: str
    category: str
    category_budget: Decimal
    category_spent: Decimal
    budget_remaining_before: Decimal
    budget_remaining_after: Decimal
    over_budget: bool
    over_amount: Decimal
    total_budget: Decimal
    total_spent: Decimal
    monthly_net_after: Decimal


class DecisionCashflowOut(BaseModel):
    available: bool
    months: list[str] = Field(default_factory=list)
    monthly_income: Decimal
    monthly_expense: Decimal
    monthly_net: Decimal
    monthly_net_after: Decimal
    bill_count: int


class DecisionGoalOut(BaseModel):
    id: int
    name: str
    target_amount: Decimal
    saved_amount: Decimal
    remaining: Decimal
    progress_ratio: float
    target_date: date | None = None
    months_left: float
    projected_saved_before: Decimal
    projected_saved_after: Decimal
    gap_before: Decimal
    gap_after: Decimal
    projected_finish_before: date | None = None
    projected_finish_after: date | None = None
    delay_days: int | None = None
    extra_days: int | None = None
    status: str


class DecisionScenarioOut(BaseModel):
    key: str
    title: str
    description: str
    budget_impact: Decimal | None = None
    goal_delay_days: int | None = None
    goal_gap_after: Decimal | None = None
    feasible: bool
    monthly_cut: Decimal
    impact_amount: Decimal


class DecisionRecommendationOut(BaseModel):
    title: str
    detail: str
    impact_amount: Decimal | None = None
    priority: str
    action_hint: str


class DecisionSimulationOut(BaseModel):
    available: bool
    missing: list[str] = Field(default_factory=list)
    message: str
    as_of: str
    amount: Decimal
    category: str
    horizon_months: int
    purchase: DecisionPurchaseOut
    cashflow: DecisionCashflowOut
    goal: DecisionGoalOut | None = None
    scenarios: list[DecisionScenarioOut] = Field(default_factory=list)
    recommendations: list[DecisionRecommendationOut] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    disclaimer: str



# ---------- CSV 账单导入 ----------

class CsvRowIn(BaseModel):
    row_no: int = 0
    bill_date: date
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    type: Literal["income", "expense"] = "expense"
    category: str = Field(default="其他", max_length=40)
    remark: str = Field(default="", max_length=200)
    pay_channel: str = Field(default="", max_length=20)
    funding_account: str = Field(default="", max_length=40)


class CsvPreviewRowOut(BaseModel):
    row_no: int
    bill_date: date | None = None
    amount: Decimal | None = None
    type: str = "expense"
    category: str = "其他"
    remark: str = ""
    pay_channel: str = ""
    funding_account: str = ""
    include: bool = True
    duplicate: bool = False
    duplicate_reason: str = ""
    errors: list[str] = Field(default_factory=list)
    raw_date: str = ""
    raw_amount: str = ""


class CsvPreviewIn(BaseModel):
    text: str = Field(min_length=1, max_length=2_000_000)
    filename: str = Field(default="", max_length=120)


class CsvPreviewOut(BaseModel):
    filename: str = ""
    encoding: str = "utf-8"
    delimiter: str = ","
    total_rows: int
    valid_rows: int
    duplicate_rows: int
    error_rows: int
    income_total: Decimal
    expense_total: Decimal
    truncated: bool = False
    columns: dict[str, str] = Field(default_factory=dict)
    rows: list[CsvPreviewRowOut] = Field(default_factory=list)
    notice: str = ""


class CsvConfirmIn(BaseModel):
    rows: list[CsvRowIn] = Field(min_length=1, max_length=1000)
    filename: str = Field(default="", max_length=120)


class CsvConfirmOut(BaseModel):
    imported_count: int
    skipped_duplicates: int
    failed_count: int
    income_total: Decimal
    expense_total: Decimal
    created_ids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------- 个人资产管理 ----------
# 金额全部使用 Decimal；账户/负债/流水均按 user_id 隔离。

AssetAccountType = Literal["cash", "bank", "wechat", "alipay", "savings", "other"]
AssetLiabilityType = Literal["credit_card", "installment", "personal_loan", "other"]


class AssetAccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: AssetAccountType = "other"
    institution: str = Field(default="", max_length=50)
    account_hint: str = Field(default="", max_length=32)
    balance: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    note: str = Field(default="", max_length=200)

    @field_validator("account_hint")
    @classmethod
    def _only_last_four(cls, value):
        # 隐私保护：即使前端误传完整账号，也只保留后 4 位
        return (value or "").strip()[-4:]


class AssetAccountUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: AssetAccountType = "other"
    institution: str = Field(default="", max_length=50)
    account_hint: str = Field(default="", max_length=32)
    note: str = Field(default="", max_length=200)

    @field_validator("account_hint")
    @classmethod
    def _only_last_four(cls, value):
        return (value or "").strip()[-4:]


class AssetAccountOut(BaseModel):
    id: int
    name: str
    type: str
    institution: str
    account_hint: str
    balance: Decimal
    note: str
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class AssetAccountChangeIn(BaseModel):
    kind: Literal["increase", "decrease", "adjust"]
    amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    target_balance: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    note: str = Field(default="", max_length=200)


class AssetLiabilityIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: AssetLiabilityType = "other"
    outstanding: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date | None = None
    remark: str = Field(default="", max_length=200)


class AssetLiabilityUpdateIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    type: AssetLiabilityType = "other"
    due_date: date | None = None
    remark: str = Field(default="", max_length=200)


class AssetLiabilityOut(BaseModel):
    id: int
    name: str
    type: str
    outstanding: Decimal
    due_date: date | None = None
    remark: str
    status: str
    is_active: bool = True
    days_left: int | None = None
    is_overdue: bool = False
    created_at: datetime
    updated_at: datetime


class AssetLiabilityRepayIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    account_id: int
    note: str = Field(default="", max_length=200)


class AssetLiabilityAdjustIn(BaseModel):
    target_outstanding: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    note: str = Field(default="", max_length=200)


class AssetTransferIn(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    note: str = Field(default="", max_length=200)


class AssetTransactionOut(BaseModel):
    id: int
    account_id: int | None = None
    liability_id: int | None = None
    account_name: str = ""
    liability_name: str = ""
    type: str
    direction: str
    amount: Decimal
    before_amount: Decimal
    after_amount: Decimal
    note: str
    source: str
    related_bill_id: int | None = None
    transfer_group_id: str = ""
    status: str
    created_at: datetime


class AssetTransactionPageOut(BaseModel):
    items: list[AssetTransactionOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


class AssetTransferOut(BaseModel):
    ok: bool = True
    transfer_group_id: str
    from_account: AssetAccountOut
    to_account: AssetAccountOut
    transactions: list[AssetTransactionOut] = Field(default_factory=list)


class AssetOverviewOut(BaseModel):
    total_assets: Decimal
    total_liabilities: Decimal
    net_worth: Decimal
    account_count: int
    liability_count: int
    accounts: list[AssetAccountOut] = Field(default_factory=list)
    liabilities: list[AssetLiabilityOut] = Field(default_factory=list)
    last_updated_at: datetime | None = None
    as_of: datetime
    has_data: bool = False


class AssetChangeAnalysisOut(BaseModel):
    month: str
    net_worth_change: Decimal
    components: dict[str, Decimal] = Field(default_factory=dict)
    linked_expense: Decimal
    total_expense: Decimal
    unlinked_expense: Decimal
    coverage_ratio: float = 0.0
    has_data: bool = False
    transfer_count: int = 0
    transfer_gross: Decimal = Decimal("0")
    message: str = ""
    as_of: datetime


class AssetDeleteOut(BaseModel):
    ok: bool = True
    archived: bool = False
    message: str = ""
