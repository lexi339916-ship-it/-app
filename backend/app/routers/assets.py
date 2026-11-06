"""个人资产管理接口：账户、负债、流水、转账与净资产变化。

所有接口按 JWT 当前用户隔离；请求体不接收 user_id。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.schemas import (
    AssetAccountChangeIn, AssetAccountIn, AssetAccountOut, AssetAccountUpdateIn,
    AssetChangeAnalysisOut, AssetDeleteOut, AssetLiabilityAdjustIn,
    AssetLiabilityIn, AssetLiabilityOut, AssetLiabilityRepayIn,
    AssetLiabilityUpdateIn, AssetOverviewOut, AssetTransactionPageOut,
    AssetTransferIn, AssetTransferOut,
)
from app.services import asset_service

router = APIRouter()


@router.get("/overview", response_model=AssetOverviewOut)
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """总资产、总负债、净资产与账户/负债明细。"""
    return asset_service.overview(db, user)


@router.get("/accounts", response_model=list[AssetAccountOut])
def accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return asset_service.overview(db, user).accounts


@router.post("/accounts", response_model=AssetAccountOut)
def create_account(data: AssetAccountIn, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return asset_service.create_account(db, user, data)


@router.put("/accounts/{account_id}", response_model=AssetAccountOut)
def update_account(account_id: int, data: AssetAccountUpdateIn,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return asset_service.update_account(db, user, account_id, data)


@router.delete("/accounts/{account_id}", response_model=AssetDeleteOut)
def delete_account(account_id: int, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return asset_service.archive_account(db, user, account_id)


@router.post("/accounts/{account_id}/restore", response_model=AssetAccountOut)
def restore_account(account_id: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    return asset_service.restore_account(db, user, account_id)


@router.post("/accounts/{account_id}/adjust", response_model=AssetAccountOut)
def adjust_account(account_id: int, data: AssetAccountChangeIn,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """手动增加/减少余额，或把余额调整到指定值；每次都会写流水。"""
    return asset_service.adjust_account(db, user, account_id, data)


@router.post("/transfers", response_model=AssetTransferOut)
def transfer(data: AssetTransferIn, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    """账户间转账：只写两条资产流水，不生成账单，不计入消费。"""
    return asset_service.transfer(db, user, data)


@router.get("/transactions", response_model=AssetTransactionPageOut)
def transactions(account_id: int | None = None, liability_id: int | None = None,
                 type: str = "", month: str = "", page: int = 1,
                 page_size: int = 20, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return asset_service.list_transactions(
        db, user, account_id=account_id, liability_id=liability_id,
        type_=type, month=month, page=page, page_size=page_size)


@router.get("/liabilities", response_model=list[AssetLiabilityOut])
def liabilities(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return asset_service.overview(db, user).liabilities


@router.post("/liabilities", response_model=AssetLiabilityOut)
def create_liability(data: AssetLiabilityIn, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return asset_service.create_liability(db, user, data)


@router.put("/liabilities/{liability_id}", response_model=AssetLiabilityOut)
def update_liability(liability_id: int, data: AssetLiabilityUpdateIn,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return asset_service.update_liability(db, user, liability_id, data)


@router.delete("/liabilities/{liability_id}", response_model=AssetDeleteOut)
def delete_liability(liability_id: int, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return asset_service.archive_liability(db, user, liability_id)


@router.post("/liabilities/{liability_id}/restore", response_model=AssetLiabilityOut)
def restore_liability(liability_id: int, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return asset_service.restore_liability(db, user, liability_id)


@router.post("/liabilities/{liability_id}/repay", response_model=AssetLiabilityOut)
def repay_liability(liability_id: int, data: AssetLiabilityRepayIn,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """从指定资产账户还款；账户与负债同时减少，净资产不变。"""
    return asset_service.repay_liability(db, user, liability_id, data)


@router.post("/liabilities/{liability_id}/adjust", response_model=AssetLiabilityOut)
def adjust_liability(liability_id: int, data: AssetLiabilityAdjustIn,
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return asset_service.adjust_liability(db, user, liability_id, data)


@router.get("/change-analysis", response_model=AssetChangeAnalysisOut)
def change_analysis(month: str = "", user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """净资产变化拆解：消费、收入、转账、负债、手动调整。"""
    return asset_service.change_analysis(db, user, month)
