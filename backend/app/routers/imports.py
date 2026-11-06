"""CSV 账单导入接口：预览、文件预览、确认导入。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.schemas import (
    CsvConfirmIn, CsvConfirmOut, CsvPreviewIn, CsvPreviewOut,
)
from app.services import csv_import

router = APIRouter()

TEMPLATE = """日期,金额,类型,分类,备注,支付渠道,扣款账户
2026-11-01,32.50,支出,餐饮,午饭,微信支付,零钱
2026-11-02,21.00,支出,交通,打车,支付宝,余额
2026-11-03,800.00,收入,兼职,家教,银行卡,储蓄卡
"""


@router.get("/template")
def template():
    """示例 CSV，供前端“填入示例”使用。"""
    return {"csv": TEMPLATE}


@router.post("/preview", response_model=CsvPreviewOut)
def preview(data: CsvPreviewIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """粘贴 CSV 文本后预览：字段、合计、重复与错误行。"""
    try:
        return csv_import.preview_text(db, user, data.text, data.filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/preview-file", response_model=CsvPreviewOut)
async def preview_file(file: UploadFile = File(...),
                       user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """上传 CSV 文件预览（支持 UTF-8/GBK）。"""
    data = await file.read(csv_import.MAX_FILE_BYTES + 1)
    try:
        return csv_import.preview_file(db, user, data, file.filename or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/confirm", response_model=CsvConfirmOut)
def confirm(data: CsvConfirmIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """确认导入勾选的行；重复行自动跳过，写入 source=csv 的账单。"""
    try:
        return csv_import.confirm(db, user, data.rows, data.filename)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
