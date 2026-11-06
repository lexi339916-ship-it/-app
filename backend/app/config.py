"""集中读取环境变量配置。

约定：所有敏感信息（数据库口令、JWT 密钥、模型密钥）只通过环境变量或
后端 .env 文件注入，不得写死在代码、前端或版本库中。
"""
import os
from dotenv import load_dotenv

# 加载 backend/.env（存在时），不影响系统环境变量
load_dotenv()

def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default

# 数据库连接。默认 SQLite 便于快速体验；正式部署改为 MySQL：
# DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/smart_life
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./smart_life.db")

# JWT 配置
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = _int_env("TOKEN_EXPIRE_DAYS", 7)
# 刷新令牌有效期（天），用于无感续期；可在 .env 覆盖
REFRESH_TOKEN_EXPIRE_DAYS = _int_env("REFRESH_TOKEN_EXPIRE_DAYS", 30)

# 大模型服务配置（OpenAI 兼容 chat/completions 接口）
AI_BASE_URL = os.getenv("AI_BASE_URL", "").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "")
# 视觉模型（支付截图/小票识别），智谱 glm-4v-flash 免费
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", "glm-4v-flash")
AI_TIMEOUT_SECONDS = _int_env("AI_TIMEOUT_SECONDS", 30)
# 每用户每日 AI 调用上限，用于控制成本（课程要求：调用成本控制）
AI_DAILY_LIMIT = _int_env("AI_DAILY_LIMIT", 30)

# 登录失败限流：同一用户名+IP 在窗口内失败次数过多时暂时拒绝，防暴力破解
LOGIN_MAX_ATTEMPTS = _int_env("LOGIN_MAX_ATTEMPTS", 5)
LOGIN_WINDOW_MINUTES = _int_env("LOGIN_WINDOW_MINUTES", 15)

# 语音识别：OpenAI 兼容 /audio/transcriptions 接口。
# 需要单独配置；未配置时语音接口返回 503，前端改用文字。
ASR_BASE_URL = os.getenv("ASR_BASE_URL", "").rstrip("/")
ASR_API_KEY = os.getenv("ASR_API_KEY", "")
ASR_MODEL = os.getenv("ASR_MODEL", "whisper-1")
ASR_TIMEOUT_SECONDS = _int_env("ASR_TIMEOUT_SECONDS", 60)

# 跨域来源。生产部署应写明前端域名而不是 *
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
