"""Agent 接口：任务运行、轨迹、审批、撤销、主动扫描、记忆。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import config, version
from app.deps import get_current_user, get_db
from app.models import AgentRun, AgentSessionArchive, User
from app.schemas import (
    AgentApprovalIn, AgentHealthOut, AgentMemoryOut, AgentNotificationActionIn,
    AgentNotificationOut, AgentRunIn, AgentRunOut, AgentScanOut,
    AgentSessionDeleteOut, AgentSessionSummaryOut,
)
from app.services.agent import orchestrator, trace

router = APIRouter()


def _get_owned_run(db: Session, user: User, run_id: int) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    return run


@router.post("/run", response_model=AgentRunOut)
async def run_agent(data: AgentRunIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """运行一次 Agent 任务：自动路由到记账/订阅/目标/查询场景。

    传 session_id + parent_run_id 时进入多轮对话；追问会基于上一轮审批重规划。
    """
    return await orchestrator.run_agent(
        db, user, data.message, data.mode,
        session_id=data.session_id, parent_run_id=data.parent_run_id)


@router.get("/sessions", response_model=list[AgentSessionSummaryOut])
def list_sessions(limit: int = 10, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """最近的多轮会话摘要（按最后活动时间倒序；已删除的会话不返回）。"""
    limit = max(1, min(limit, 30))
    archived = select(AgentSessionArchive.session_id).where(
        AgentSessionArchive.user_id == user.id)
    rows = db.execute(
        select(AgentRun.session_id, func.count(AgentRun.id),
               func.max(AgentRun.created_at))
        .where(AgentRun.user_id == user.id, AgentRun.session_id != "",
               AgentRun.session_id.not_in(archived))
        .group_by(AgentRun.session_id)
        .order_by(func.max(AgentRun.created_at).desc())
        .limit(limit)).all()
    result = []
    for session_id, count, last_at in rows:
        last = db.scalar(select(AgentRun).where(
            AgentRun.user_id == user.id, AgentRun.session_id == session_id)
            .order_by(AgentRun.turn_index.desc(), AgentRun.id.desc()).limit(1))
        first = db.scalar(select(AgentRun).where(
            AgentRun.user_id == user.id, AgentRun.session_id == session_id)
            .order_by(AgentRun.turn_index, AgentRun.id).limit(1))
        result.append(AgentSessionSummaryOut(
            session_id=session_id, turn_count=int(count),
            title=(first.goal if first else ""),
            preview=((last.answer or "")[:80] if last else ""),
            last_goal=(last.goal if last else ""),
            last_status=(last.status if last else ""),
            last_at=last_at))
    return result


@router.get("/sessions/{session_id}", response_model=list[AgentRunOut])
def get_session(session_id: str, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """读取一次多轮会话的全部轮次，按 turn_index 正序。"""
    session_id = session_id[:64]
    archived = db.scalar(select(AgentSessionArchive.id).where(
        AgentSessionArchive.user_id == user.id,
        AgentSessionArchive.session_id == session_id).limit(1))
    if archived is not None:
        raise HTTPException(404, "会话不存在或已删除")
    rows = db.scalars(select(AgentRun).where(
        AgentRun.user_id == user.id,
        AgentRun.session_id == session_id,
    ).order_by(AgentRun.turn_index, AgentRun.id)).all()
    if not rows:
        raise HTTPException(404, "会话不存在")
    return [trace.serialize_run(db, row) for row in rows]


@router.delete("/sessions/{session_id}", response_model=AgentSessionDeleteOut)
def delete_session(session_id: str, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """从历史中删除会话：软删除，保留 agent_runs/steps/approvals 审计。"""
    session_id = session_id[:64]
    exists = db.scalar(select(AgentRun.id).where(
        AgentRun.user_id == user.id,
        AgentRun.session_id == session_id).limit(1))
    if exists is None:
        raise HTTPException(404, "会话不存在")
    archived = db.scalar(select(AgentSessionArchive.id).where(
        AgentSessionArchive.user_id == user.id,
        AgentSessionArchive.session_id == session_id).limit(1))
    if archived is None:
        db.add(AgentSessionArchive(user_id=user.id, session_id=session_id))
        db.commit()
    return AgentSessionDeleteOut(ok=True, session_id=session_id, archived=True)


@router.get("/runs", response_model=list[AgentRunOut])
def list_runs(limit: int = 8, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """最近的任务轨迹，便于刷新后恢复。"""
    limit = max(1, min(limit, 20))
    rows = db.scalars(select(AgentRun).where(AgentRun.user_id == user.id)
                      .order_by(AgentRun.id.desc()).limit(limit)).all()
    return [trace.serialize_run(db, row) for row in rows]


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_run(run_id: int, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    return trace.serialize_run(db, _get_owned_run(db, user, run_id))


@router.post("/approvals/{approval_id}", response_model=AgentRunOut)
async def decide_approval(approval_id: int, data: AgentApprovalIn,
                          user: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """批准或拒绝写操作；批准后执行并写审计，拒绝后按需生成替代方案。"""
    return await orchestrator.execute_approval(
        db, user, approval_id, data.decision, data.edits)


@router.post("/runs/{run_id}/undo", response_model=AgentRunOut)
def undo(run_id: int, user: User = Depends(get_current_user),
         db: Session = Depends(get_db)):
    """撤销最近一次已执行动作。"""
    return orchestrator.undo_run(db, user, run_id)


@router.post("/proactive/scan", response_model=AgentScanOut)
def scan(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """主动扫描预算/订阅/目标/计划采购；持久化为通知并返回未读数。"""
    items, unread = orchestrator.scan_and_persist(db, user)
    return AgentScanOut(items=items, unread_count=unread, scanned_at=datetime.now())


@router.get("/notifications", response_model=list[AgentNotificationOut])
def notifications(status: str = "", limit: int = 20,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return orchestrator.list_notifications(db, user, status, limit)


@router.get("/notifications/unread-count")
def notifications_unread_count(user: User = Depends(get_current_user),
                               db: Session = Depends(get_db)):
    return {"count": orchestrator.notification_unread_count(db, user)}


@router.post("/notifications/{notification_id}/action", response_model=AgentNotificationOut)
def notification_action(notification_id: int, data: AgentNotificationActionIn,
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    return orchestrator.notification_action(db, user, notification_id, data.action)


@router.get("/memories", response_model=list[AgentMemoryOut])
def memories(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return orchestrator.list_memories(db, user)


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: int, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    orchestrator.delete_memory(db, user, memory_id)
    return {"ok": True}


@router.get("/health", response_model=AgentHealthOut)
def health():
    return AgentHealthOut(
        service=version.AGENT_SERVICE_NAME,
        version=version.APP_VERSION,
        ai_configured=bool(config.AI_BASE_URL and config.AI_API_KEY and config.AI_MODEL),
        model=config.AI_MODEL or "",
        tools=orchestrator.tool_count(),
    )
