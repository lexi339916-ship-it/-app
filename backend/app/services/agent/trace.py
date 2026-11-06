"""Agent 轨迹与审批的持久化工具。

约定：
- 只记录可验证的步骤（计划、工具调用、审批、执行、校验），不保存模型原始思维链；
- 所有 JSON 字段统一用 ensure_ascii=False 存储，便于前端直接展示；
- 审批必须幂等：重复批准不会重复执行。
"""
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AgentApproval, AgentRun, AgentStep

# 审批默认有效期：30 分钟，避免旧方案在数据变化后仍可执行
APPROVAL_TTL_MINUTES = 30


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(text: str, default):
    try:
        return json.loads(text) if text else default
    except (json.JSONDecodeError, TypeError):
        return default


def create_run(db: Session, user_id: int, goal: str, mode: str = "auto",
               session_id: str = "", parent_run_id: int | None = None) -> AgentRun:
    turn_index = 0
    if session_id:
        turn_index = int(db.scalar(select(func.count()).where(
            AgentRun.user_id == user_id,
            AgentRun.session_id == session_id)) or 0)
    run = AgentRun(user_id=user_id, session_id=(session_id or "")[:64],
                   parent_run_id=parent_run_id, turn_index=turn_index,
                   goal=goal[:500], mode=mode, status="running")
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def add_step(db: Session, run: AgentRun, step_type: str, tool_name: str = "",
             args: dict | None = None, result: dict | None = None,
             status: str = "ok", error: str = "",
             started_at: datetime | None = None) -> AgentStep:
    seq = (db.scalar(select(func.max(AgentStep.seq))
                     .where(AgentStep.run_id == run.id)) or 0) + 1
    step = AgentStep(
        run_id=run.id, seq=seq, step_type=step_type, tool_name=tool_name,
        args_json=dumps(args or {}), result_json=dumps(result or {}),
        status=status, error=(error or "")[:255],
        started_at=started_at or datetime.now(), finished_at=datetime.now())
    db.add(step)
    db.commit()
    db.refresh(step)
    return step


def set_plan(db: Session, run: AgentRun, plan: list[str],
             evidence: dict | None = None) -> None:
    run.plan_json = dumps(plan)
    if evidence is not None:
        run.evidence_json = dumps(evidence)
    db.commit()


def set_answer(db: Session, run: AgentRun, answer: str) -> None:
    run.answer = (answer or "")[:4000]
    db.commit()


def finish_run(db: Session, run: AgentRun, status: str, answer: str,
               evidence: dict | None = None, cost: float = 0.0,
               latency_ms: int = 0) -> None:
    run.status = status
    run.answer = (answer or "")[:4000]
    if evidence is not None:
        run.evidence_json = dumps(evidence)
    run.cost = Decimal(str(round(cost, 4)))
    run.latency_ms = max(0, int(latency_ms))
    run.finished_at = None if status == "awaiting_approval" else datetime.now()
    db.commit()


def create_approval(db: Session, run: AgentRun, diff: dict,
                    action_type: str = "multi",
                    step_id: int | None = None) -> AgentApproval:
    key = f"run-{run.id}-{uuid.uuid4().hex}"
    row = AgentApproval(
        run_id=run.id, step_id=step_id, action_type=action_type,
        diff_json=dumps(diff), status="pending", idempotency_key=key,
        expires_at=datetime.now() + timedelta(minutes=APPROVAL_TTL_MINUTES))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def serialize_run(db: Session, run: AgentRun) -> dict:
    steps = db.scalars(select(AgentStep).where(AgentStep.run_id == run.id)
                       .order_by(AgentStep.seq)).all()
    approvals = db.scalars(select(AgentApproval).where(AgentApproval.run_id == run.id)
                           .order_by(AgentApproval.id)).all()
    evidence = loads(run.evidence_json, {})
    return {
        "run_id": run.id,
        "status": run.status,
        "goal": run.goal,
        "mode": run.mode,
        "session_id": run.session_id or "",
        "parent_run_id": run.parent_run_id,
        "turn_index": run.turn_index or 0,
        "plan": loads(run.plan_json, []),
        "answer": run.answer or "",
        "evidence": evidence,
        "steps": [{
            "seq": s.seq,
            "step_type": s.step_type,
            "tool_name": s.tool_name or "",
            "args": loads(s.args_json, {}),
            "result": loads(s.result_json, {}),
            "status": s.status,
            "error": s.error or "",
            "started_at": s.started_at,
            "finished_at": s.finished_at,
        } for s in steps],
        "approvals": [{
            "id": a.id,
            "run_id": a.run_id,
            "action_type": a.action_type,
            "diff": loads(a.diff_json, {}),
            "status": a.status,
            "created_at": a.created_at,
            "expires_at": a.expires_at,
            "decided_at": a.decided_at,
        } for a in approvals],
        "cost": float(run.cost or 0),
        "latency_ms": run.latency_ms or 0,
        "model": evidence.get("model", ""),
        "created_at": run.created_at,
        "finished_at": run.finished_at,
    }
