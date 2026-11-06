"""认证接口：注册、登录、用户信息、头像。"""
import base64
import io
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.deps import get_current_user, get_db
from app.models import User
from app.schemas import (
    LoginIn, ProfileUpdateIn, RefreshIn, RegisterIn, TokenOut, UserOut,
)
from app.security import (
    create_refresh_token, create_token, decode_refresh_token,
    hash_password, verify_password,
)

router = APIRouter()

AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_SIZE = 256
AVATAR_QUALITY = 82


def _make_avatar(data: bytes) -> str:
    """校验图片、裁成正方形、缩放到 256×256，重新编码去掉 EXIF。"""
    if not data:
        raise HTTPException(400, "图片为空，请重新选择。")
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(413, "头像不能超过 2MB，请压缩后再试。")
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), method=Image.LANCZOS)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "无法识别这张图片，请选择 JPG/PNG/WebP 图片。")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=AVATAR_QUALITY, optimize=True)
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


# 进程内登录失败记录：key = username + client_ip -> 时间戳队列
_login_failures: dict[str, deque] = defaultdict(deque)
_login_lock = threading.Lock()


def _client_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{username.lower()}@{host}"


def _check_login_allowed(key: str) -> None:
    now = time.monotonic()
    window = max(1, config.LOGIN_WINDOW_MINUTES) * 60
    with _login_lock:
        queue = _login_failures[key]
        while queue and now - queue[0] > window:
            queue.popleft()
        if len(queue) >= max(1, config.LOGIN_MAX_ATTEMPTS):
            raise HTTPException(
                429, f"登录失败次数过多，请 {config.LOGIN_WINDOW_MINUTES} 分钟后再试。")


def _record_login_failure(key: str) -> None:
    with _login_lock:
        _login_failures[key].append(time.monotonic())


def _clear_login_failures(key: str) -> None:
    with _login_lock:
        _login_failures.pop(key, None)


@router.post("/register", response_model=TokenOut)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.username == data.username))
    if exists:
        raise HTTPException(400, "用户名已被注册")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        nickname=data.nickname or data.username,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenOut(
        access_token=create_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    key = _client_key(request, data.username)
    _check_login_allowed(key)
    user = db.scalar(select(User).where(User.username == data.username))
    if user is None or not verify_password(data.password, user.password_hash):
        _record_login_failure(key)
        raise HTTPException(400, "用户名或密码不正确")
    _clear_login_failures(key)
    return TokenOut(
        access_token=create_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenOut)
def refresh(data: RefreshIn, db: Session = Depends(get_db)):
    """用刷新令牌换取新的访问令牌（刷新令牌轮换）。"""
    user_id = decode_refresh_token(data.refresh_token)
    if user_id is None:
        raise HTTPException(401, "刷新令牌无效或已过期，请重新登录")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "用户不存在，请重新登录")
    return TokenOut(
        access_token=create_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/avatar", response_model=UserOut)
async def upload_avatar(file: UploadFile = File(...),
                        user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """上传头像：只保留压缩后的 256×256 JPEG data URL，不保存原图。"""
    data = await file.read(AVATAR_MAX_BYTES + 1)
    user.avatar = _make_avatar(data)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/avatar", response_model=UserOut)
def delete_avatar(user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    user.avatar = ""
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.put("/me", response_model=UserOut)
def update_me(data: ProfileUpdateIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if data.nickname:
        user.nickname = data.nickname
    if data.new_password:
        if len(data.new_password) < 6:
            raise HTTPException(400, "新密码长度不得少于 6 位")
        if not verify_password(data.old_password, user.password_hash):
            raise HTTPException(400, "原密码不正确")
        user.password_hash = hash_password(data.new_password)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)
