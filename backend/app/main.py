"""应用入口：路由注册、跨域、统一错误格式、启动初始化。"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app import config
from app.database import Base, engine, SessionLocal
from app.models import BillCategory
from app.routers import (
    agent, ai, assets, auth, bills, budget_center, budgets, categories, challenges,
    consumption_health, decision_simulator, goals, imports, notes, notifications,
    statistics, subscriptions, voice,
)
from app.services.ai_service import AIServiceError
from app import version

DEFAULT_CATEGORIES = [
    ("餐饮", "expense"), ("交通", "expense"), ("购物", "expense"), ("住房", "expense"),
    ("学习", "expense"), ("娱乐", "expense"), ("医疗", "expense"), ("通讯", "expense"),
    ("其他", "expense"),
    ("工资", "income"), ("兼职", "income"), ("理财", "income"),
    ("红包", "income"), ("退款", "income"), ("其他收入", "income"),
]


def seed_default_categories() -> None:
    """幂等写入系统预置分类（user_id 为 NULL 表示所有用户可见）。"""
    db = SessionLocal()
    try:
        for name, type_ in DEFAULT_CATEGORIES:
            exists = db.query(BillCategory).filter_by(
                user_id=None, name=name, type=type_).first()
            if exists is None:
                db.add(BillCategory(user_id=None, name=name, type=type_))
        db.commit()
    finally:
        db.close()


def _ensure_schema_patches() -> None:
    """老库轻量迁移：create_all 不会给已有表补列，这里按需 ALTER。

    覆盖：订阅分类/涨价/使用频次、储蓄目标周期、Agent 审批过期时间。
    """
    patches = {
        "users": {
            "avatar": "ALTER TABLE users ADD COLUMN avatar MEDIUMTEXT",
        },
        "bills": {
            "account_id": "ALTER TABLE bills ADD COLUMN account_id BIGINT",
            "liability_id": "ALTER TABLE bills ADD COLUMN liability_id BIGINT",
        },
        "notes": {
            "entry_type": "ALTER TABLE notes ADD COLUMN entry_type VARCHAR(10) NOT NULL DEFAULT 'note'",
            "location": "ALTER TABLE notes ADD COLUMN location VARCHAR(100) NOT NULL DEFAULT ''",
            "image": "ALTER TABLE notes ADD COLUMN image MEDIUMTEXT",
        },
        "subscriptions": {
            "category_id": "ALTER TABLE subscriptions ADD COLUMN category_id BIGINT",
            "previous_amount": "ALTER TABLE subscriptions ADD COLUMN previous_amount DECIMAL(12, 2)",
            "usage_90d": "ALTER TABLE subscriptions ADD COLUMN usage_90d INTEGER NOT NULL DEFAULT 0",
        },
        "savings_goals": {
            "target_months": "ALTER TABLE savings_goals ADD COLUMN target_months INTEGER",
            "target_date": "ALTER TABLE savings_goals ADD COLUMN target_date DATE",
        },
        "agent_approvals": {
            "expires_at": "ALTER TABLE agent_approvals ADD COLUMN expires_at DATETIME",
        },
        "agent_runs": {
            "session_id": "ALTER TABLE agent_runs ADD COLUMN session_id VARCHAR(64) NOT NULL DEFAULT ''",
            "parent_run_id": "ALTER TABLE agent_runs ADD COLUMN parent_run_id BIGINT",
            "turn_index": "ALTER TABLE agent_runs ADD COLUMN turn_index INTEGER NOT NULL DEFAULT 0",
        },
    }
    for table, columns in patches.items():
        try:
            existing = {c["name"] for c in inspect(engine).get_columns(table)}
        except Exception:
            continue
        for column, ddl in columns.items():
            if column not in existing:
                with engine.begin() as conn:
                    conn.execute(text(ddl))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发环境便捷建表；正式部署请使用 database/schema.sql 初始化 MySQL
    Base.metadata.create_all(bind=engine)
    _ensure_schema_patches()
    seed_default_categories()
    _warn_insecure_defaults()
    yield


def _warn_insecure_defaults() -> None:
    """启动时提示不安全的默认配置，不打印任何密钥内容。"""
    logger = logging.getLogger("uvicorn.error")
    if config.JWT_SECRET == "dev-only-secret-change-me":
        logger.warning("安全提示：JWT_SECRET 仍是开发默认值，公网演示前必须更换为随机长串。")
    if "*" in config.CORS_ORIGINS:
        logger.warning("安全提示：CORS_ORIGINS 仍为 *，公网部署应改为前端域名白名单。")
    if config.DATABASE_URL.startswith("sqlite") and "///./" not in config.DATABASE_URL:
        logger.warning("部署提示：当前使用 SQLite 文件库，正式环境建议 MySQL 8。")


app = FastAPI(
    title=f"{version.APP_NAME} API",
    version=version.APP_VERSION,
    description=version.DESCRIPTION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])
app.include_router(assets.router, prefix="/api/assets", tags=["个人资产"])
app.include_router(categories.router, prefix="/api/categories", tags=["分类"])
app.include_router(bills.router, prefix="/api/bills", tags=["账单"])
app.include_router(notes.router, prefix="/api/notes", tags=["便签"])
app.include_router(budgets.router, prefix="/api/budgets", tags=["预算"])
app.include_router(budget_center.router, prefix="/api/budget-center", tags=["预算预警中心"])
app.include_router(goals.router, prefix="/api/goals", tags=["储蓄目标"])
app.include_router(challenges.router, prefix="/api/challenges", tags=["生活挑战"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["自动订阅扣费"])
app.include_router(statistics.router, prefix="/api/statistics", tags=["统计"])
app.include_router(consumption_health.router, prefix="/api/consumption-health",
                   tags=["消费健康诊断"])
app.include_router(decision_simulator.router, prefix="/api/decision-simulator",
                   tags=["消费决策模拟"])
app.include_router(imports.router, prefix="/api/imports", tags=["CSV 账单导入"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["统一消息中心"])
app.include_router(voice.router, prefix="/api/voice", tags=["语音"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI"])


# 统一错误响应：{"code": HTTP状态码, "message": 提示信息}
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code,
                        content={"code": exc.status_code, "message": str(exc.detail)})


@app.exception_handler(AIServiceError)
async def ai_exception_handler(request: Request, exc: AIServiceError):
    # AI 层异常（未配置/超时/限流/格式错误）统一转为用户可读提示
    return JSONResponse(status_code=exc.status,
                        content={"code": exc.status, "message": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = first.get("msg", "参数错误")
    field = f"字段 {loc}：" if loc else ""
    return JSONResponse(status_code=422,
                        content={"code": 422, "message": f"{field}参数校验失败（{msg}）"})


@app.get("/api/health", tags=["系统"])
def health():
    return {"ok": True, "service": version.API_SERVICE_NAME,
            "name": version.APP_NAME, "version": version.APP_VERSION}
