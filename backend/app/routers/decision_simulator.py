"""消费决策模拟接口：输入购买金额，返回预算冲击、目标差额与可选方案。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import SavingsGoal, User
from app.schemas import DecisionSimulationIn, DecisionSimulationOut
from app.services import decision_simulator
from app.services.agent import tools

router = APIRouter()


@router.post("/simulate", response_model=DecisionSimulationOut)
def simulate(data: DecisionSimulationIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """测算“现在买 X 元会不会影响预算/储蓄目标”；所有金额由后端计算。"""
    category = (data.category or "").strip()
    visible = [c.name for c in tools.visible_categories(db, user, "expense")]
    if category not in visible:
        raise HTTPException(400, "分类不存在或不可用")
    if data.goal_id is not None:
        goal = db.get(SavingsGoal, data.goal_id)
        if goal is None or goal.user_id != user.id:
            raise HTTPException(404, "储蓄目标不存在")
    return decision_simulator.simulate(
        db, user, data.amount, category, data.goal_id, data.horizon_months)
