"""消费健康诊断接口：只读，所有指标由后端业务公式计算。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.schemas import HealthReportOut
from app.services import health_service

router = APIRouter()


@router.get("/report", response_model=HealthReportOut)
def report(month: str = "", user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    """某月消费健康报告；month 为空时取当前月。"""
    try:
        result = health_service.build_report(db, user, month or None)
    except ValueError:
        raise HTTPException(400, "月份格式应为 YYYY-MM")
    return result
