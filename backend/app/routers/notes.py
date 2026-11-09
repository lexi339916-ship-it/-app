"""便签与任务接口：CRUD、搜索、视图过滤（今天/近期/已完成）、优先级、置顶与记录照片。"""
import base64
import io
import json
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, ImageOps
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Note, User
from app.schemas import NoteIn, NoteOut, NotePageOut

router = APIRouter()

NOTE_PHOTO_MAX_BYTES = 6 * 1024 * 1024
NOTE_PHOTO_MAX_SIDE = 1280
NOTE_PHOTO_QUALITY = 80


def _make_note_photo(data: bytes) -> str:
    """校验并压缩记录照片，去掉 EXIF 后返回 data URL；不保存原图。"""
    if not data:
        raise HTTPException(400, "图片为空，请重新选择。")
    if len(data) > NOTE_PHOTO_MAX_BYTES:
        raise HTTPException(413, "照片不能超过 6MB，请压缩后再试。")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((NOTE_PHOTO_MAX_SIDE, NOTE_PHOTO_MAX_SIDE), Image.LANCZOS)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "无法识别这张图片，请选择 JPG/PNG/WebP 图片。")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=NOTE_PHOTO_QUALITY, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _to_out(row: Note) -> NoteOut:
    overdue = (
        row.note_type == "todo" and row.status == "open"
        and row.due_at is not None and row.due_at < datetime.now())
    photos = []
    if row.images:
        try:
            parsed = json.loads(row.images)
            if isinstance(parsed, list):
                photos = [x for x in parsed if isinstance(x, str) and x]
        except Exception:
            photos = []
    if not photos and row.image:
        photos = [row.image]
    return NoteOut(
        id=row.id, title=row.title, content=row.content,
        image=photos[0] if photos else "", images=photos,
        location=row.location or "", note_type=row.note_type,
        entry_type=row.entry_type or "note",
        status=row.status, due_at=row.due_at,
        priority=row.priority, pinned=bool(row.pinned), color=row.color or "lilac",
        is_overdue=overdue, created_at=row.created_at, updated_at=row.updated_at)


def _get_owned(db: Session, user: User, note_id: int) -> Note:
    row = db.get(Note, note_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "便签不存在")
    return row


@router.get("", response_model=NotePageOut)
def list_notes(
    q: str = "",
    note_type: str = "",
    entry_type: str = "",
    status: str = "",
    view: str = "",          # ""全部 / today今天 / upcoming近期 / done已完成
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conditions = [Note.user_id == user.id]
    if q:
        conditions.append((Note.title + Note.content).like(f"%{q}%"))
    if note_type in ("note", "todo"):
        conditions.append(Note.note_type == note_type)
    if entry_type == "idea":
        # 兼容升级前的普通便签：旧数据没有 entry_type 细分，统一归入「想法」
        conditions += [Note.note_type == "note",
                       or_(Note.entry_type == "idea", Note.entry_type == "note")]
    elif entry_type == "mood":
        conditions += [Note.note_type == "note", Note.entry_type == "mood"]
    elif entry_type == "note":
        conditions.append(Note.entry_type == "note")
    if status in ("open", "done"):
        conditions.append(Note.status == status)

    now = datetime.now()
    today_start = datetime.combine(now.date(), time.min)
    tomorrow_start = today_start + timedelta(days=1)

    if view == "today":
        # 今天到期 + 已逾期（仍未完成）
        conditions += [Note.note_type == "todo", Note.status == "open",
                       Note.due_at.isnot(None), Note.due_at < tomorrow_start]
    elif view == "upcoming":
        # 明天及以后到期的未完成任务
        conditions += [Note.note_type == "todo", Note.status == "open",
                       Note.due_at.isnot(None), Note.due_at >= tomorrow_start]
    elif view == "done":
        conditions += [Note.note_type == "todo", Note.status == "done"]

    total = db.scalar(select(func.count()).where(*conditions)) or 0
    pending = db.scalar(select(func.count()).where(
        Note.user_id == user.id, Note.note_type == "todo", Note.status == "open")) or 0

    # 排序：置顶 → 未完成在前 → 有截止时间的在前（按时间）→ 优先级 → 最近更新
    priority_order = case(
        (Note.priority == "high", 0), (Note.priority == "medium", 1), else_=2)
    if entry_type in ("idea", "mood"):
        # 想法/心情按记录时间倒序，方便时间轴浏览
        order_by = [Note.created_at.desc(), Note.id.desc()]
    else:
        order_by = [
            Note.pinned.desc(),
            case((Note.status == "open", 0), else_=1),
            Note.due_at.is_(None),
            Note.due_at.asc(),
            priority_order.asc(),
            Note.updated_at.desc(),
        ]
    rows = db.scalars(
        select(Note).where(*conditions)
        .order_by(*order_by)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return NotePageOut(items=[_to_out(r) for r in rows], total=total, pending_count=pending)


def _payload(data: NoteIn) -> dict:
    """归一化类型与照片：数据库存 JSON 数组，旧单图字段保留兼容。"""
    payload = data.model_dump()
    if payload["note_type"] == "todo":
        payload["entry_type"] = "note"
    elif payload["entry_type"] in ("idea", "mood"):
        payload["note_type"] = "note"
    photos = [x for x in payload.pop("images", []) if x]
    legacy = payload.get("image") or ""
    if not photos and legacy:
        photos = [legacy]
    photos = photos[:6]
    payload["images"] = json.dumps(photos, ensure_ascii=False) if photos else ""
    payload["image"] = ""  # 新记录统一写 images，避免重复存 base64
    return payload


@router.post("", response_model=NoteOut)
def create_note(data: NoteIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = Note(user_id=user.id, **{**_payload(data), "pinned": int(data.pinned)})
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/photo")
async def upload_note_photo(file: UploadFile = File(...),
                            user: User = Depends(get_current_user)):
    """上传想法/心情照片：仅返回压缩后的 data URL，由前端随记录一起保存。"""
    data = await file.read(NOTE_PHOTO_MAX_BYTES + 1)
    return {"image": _make_note_photo(data)}


@router.get("/{note_id}", response_model=NoteOut)
def get_note(note_id: int, user: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    return _to_out(_get_owned(db, user, note_id))


@router.put("/{note_id}", response_model=NoteOut)
def update_note(note_id: int, data: NoteIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = _get_owned(db, user, note_id)
    for key, value in _payload(data).items():
        setattr(row, key, int(value) if key == "pinned" else value)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{note_id}")
def delete_note(note_id: int, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = _get_owned(db, user, note_id)
    db.delete(row)
    db.commit()
    return {"ok": True}
