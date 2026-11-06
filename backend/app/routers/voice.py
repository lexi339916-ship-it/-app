"""语音转写接口：录音上传 → OpenAI 兼容 ASR → 返回文字。

设计边界：
- 只做“按住说话”的一次性转写，不做唤醒词/后台持续监听；
- 音频只在内存中处理，不落库、不写日志；
- 未配置 ASR 时返回 503，前端提示改用文字；
- 转写结果交给现有 Agent/记账解析，不新增一套记账逻辑。
"""
import time

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import config
from app.deps import get_current_user, get_db
from app.models import User
from app.schemas import VoiceTranscribeOut
from app.services import ai_service

router = APIRouter()
MAX_AUDIO_BYTES = 5 * 1024 * 1024


async def _call_asr(filename: str, data: bytes, content_type: str) -> dict:
    """调用 OpenAI 兼容 /audio/transcriptions；独立出来便于测试替换。"""
    async with httpx.AsyncClient(timeout=config.ASR_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            config.ASR_BASE_URL + "/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.ASR_API_KEY}"},
            data={"model": config.ASR_MODEL},
            files={"file": (filename or "voice.mp3", data,
                            content_type or "audio/mpeg")},
        )
    if resp.status_code != 200:
        raise HTTPException(502, f"语音识别服务返回错误（HTTP {resp.status_code}），请改用文字。")
    try:
        body = resp.json()
    except Exception:
        raise HTTPException(502, "语音识别返回格式异常，请改用文字。")
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(422, "没有识别到语音内容，请靠近麦克风重试或改用文字。")
    return {"text": text, "provider": "openai-compatible"}


@router.post("/transcribe", response_model=VoiceTranscribeOut)
async def transcribe(file: UploadFile = File(...),
                     user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    """上传一段录音并转写为文字；失败时前端应回退到文字输入。"""
    if not (config.ASR_BASE_URL and config.ASR_API_KEY):
        raise HTTPException(
            503, "语音服务未配置：请在后端 .env 中设置 ASR_BASE_URL/ASR_API_KEY，或直接改用文字输入。")

    data = await file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(400, "音频为空，请重新录制。")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "音频不能超过 5MB，请缩短录音。")

    ai_service.check_rate_limit(db, user.id)
    started = time.monotonic()
    try:
        result = await _call_asr(file.filename or "voice.mp3", data,
                                 file.content_type or "audio/mpeg")
        latency = int((time.monotonic() - started) * 1000)
        ai_service.log_call(db, user_id=user.id, feature="voice_transcribe",
                            status="success", latency_ms=latency,
                            input_chars=len(result["text"]),
                            model=config.ASR_MODEL or "asr")
        return VoiceTranscribeOut(
            text=result["text"], provider=result["provider"],
            model=config.ASR_MODEL, latency_ms=latency)
    except HTTPException as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_service.log_call(db, user_id=user.id, feature="voice_transcribe",
                            status="error", latency_ms=latency, input_chars=0,
                            error_msg=str(exc.detail), model=config.ASR_MODEL or "asr")
        raise
