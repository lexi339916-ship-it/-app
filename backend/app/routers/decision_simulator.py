"""消费决策模拟接口：输入购买金额，返回预算冲击、目标差额与可选方案。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import AssetAccount, SavingsGoal, User
from app.schemas import DecisionSimulationIn, DecisionSimulationOut
from app.services import asset_service, decision_simulator
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
    if data.account_id is not None:
        account = db.get(AssetAccount, data.account_id)
        if account is None or account.user_id != user.id or not account.is_active:
            raise HTTPException(404, "资产账户不存在或已停用")
        if account.type not in asset_service.LIQUID_ASSET_TYPES:
            raise HTTPException(400, "购买测算请选择现金/银行/微信/支付宝/储蓄账户")
    return decision_simulator.simulate(
        db, user, data.amount, category, data.goal_id, data.horizon_months,
        data.account_id)
