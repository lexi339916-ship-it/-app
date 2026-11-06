"""统一消息中心接口：聚合预算预警与 Agent 通知。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.schemas import (
    NotificationReadAllOut, NotificationSummaryOut, UnifiedNotificationActionIn,
    UnifiedNotificationOut,
)
from app.services import notification_service

router = APIRouter()


@router.get("/summary", response_model=NotificationSummaryOut)
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """未读总数、去重后未读数、分来源与等级统计。"""
    return notification_service.summary(db, user)


@router.get("", response_model=list[UnifiedNotificationOut])
def list_notifications(status: str = "", source: str = "", group: str = "",
                       limit: int = 50,
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """统一列表；source=budget/agent、group 可按提醒分组筛选。"""
    if source and source not in ("budget", "agent"):
        raise HTTPException(400, "source 只能是 budget 或 agent")
    if status and status not in ("unread", "read", "accepted", "dismissed"):
        raise HTTPException(400, "status 参数不正确")
    if group and group not in ("budget_over", "budget_near", "subscription",
                               "goal", "purchase", "other"):
        raise HTTPException(400, "group 参数不正确")
    return notification_service.list_notifications(
        db, user, status, source, limit, group)


@router.post("/read-all", response_model=NotificationReadAllOut)
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """进入消息中心时调用：把两套通知的未读标为已读。"""
    return notification_service.mark_all_read(db, user)


@router.post("/{source}/{notification_id}/action",
             response_model=UnifiedNotificationOut)
def action(source: str, notification_id: int, data: UnifiedNotificationActionIn,
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """已读/忽略/采纳；内部复用两套原有通知的动作逻辑。"""
    if source not in ("budget", "agent"):
        raise HTTPException(400, "source 只能是 budget 或 agent")
    try:
        result = notification_service.action(db, user, source, notification_id,
                                             data.action)
        if result is None:
            raise HTTPException(404, "消息不存在")
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc))
