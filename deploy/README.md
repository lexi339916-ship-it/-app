# 部署说明（比赛演示版）

## 一、本地开发（当前已跑通）

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端：HBuilderX 导入 frontend/，运行到浏览器；或使用 deploy/h5 预构建产物
# 本地 H5 地址：http://127.0.0.1:8080
```

演示账号：

- 用户名：`judge_demo`
- 密码：`judge2026`
- 数据重置：`python tools/seed_demo.py`

## 二、Docker Compose（公网/服务器）

```bash
cd deploy
cp .env.example .env
# 编辑 .env：填入 AI_BASE_URL / AI_API_KEY / AI_MODEL，并把 JWT_SECRET 改成随机长串

docker compose up -d --build

# 首次启动后生成演示数据（可重复执行，会重置 judge_demo）
docker compose exec backend python tools/seed_demo.py
```

访问：

- 前端：`http://服务器IP:8080`
- 后端文档：`http://服务器IP:8000/docs`
- 演示账号：`judge_demo / judge2026`

语音功能需要 `ASR_BASE_URL` / `ASR_API_KEY`（OpenAI 兼容 `/audio/transcriptions`）；
未配置时语音按钮会提示“语音服务未配置”，文字输入不受影响。

数据保存在 `deploy/data/smart_life.db`（SQLite，演示用）；生产建议切 MySQL，
把 `DATABASE_URL` 改为 `mysql+pymysql://user:password@host:3306/smart_life`，
并先导入 `database/schema.sql`。

## 三、前端 H5 构建

仓库里 `deploy/h5` 是当前预构建产物。修改前端后重新构建：

```bash
python tools/build_h5.py
```

脚本会临时创建 uni-app CLI 工程、安装依赖、构建 H5，并覆盖 `deploy/h5`。
需要本机有 Node.js 18+；没有时可用项目内便携 Node（见 `.runtime/`）。

## 四、HTTPS 与域名

比赛演示建议用 Caddy/Nginx 在最外层加 HTTPS：

- Caddy：`your.domain { reverse_proxy 127.0.0.1:8080 }`
- 或云厂商负载均衡 → 8080。

`deploy/nginx.conf` 已把 `/api/` 反向代理到后端，前端在非 localhost 域名下会自动使用同源 API。

## 五、安全注意

- 不要把 `deploy/.env`、`deploy/data/`、`backend/.env`、`*.db` 提交到仓库。
- 演示账号只用于评委体验，密码在比赛结束后应更换。
- 公网演示前检查：登录限流、CORS 白名单、HTTPS、日志不含密钥和完整个人信息。
- 只用合成演示数据，不接入真实银行/支付宝/微信账号。

## 六、无 Docker 的公网演示（隧道/单端口）

如果服务器没有 Nginx，可用同源代理把 H5 和 `/api` 放在同一个端口：

```bash
# 1) 启动后端（8000）
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2) 启动同源代理（8080，静态 H5 + /api 反代）
cd ..
python deploy/proxy_server.py --port 8080 --backend http://127.0.0.1:8000

# 3) 用 cloudflared/ngrok/服务器反代暴露 8080
#    例如：cloudflared tunnel --url http://127.0.0.1:8080
#    或：  ssh -R 80:localhost:8080 serveo.net
```

验证公网地址（只读，不写数据）：

```bash
python deploy/verify_public.py --base-url https://your.domain
```

检查项：后端健康、`/docs`、前端首页、`judge_demo` 登录、健康报告、决策模拟器、CSV 模板、Agent 健康。

> 临时隧道地址不稳定，正式评审建议使用云服务器 + 域名 + HTTPS；隧道只作为兜底。

## 七、公网安全清单

- 替换 `JWT_SECRET` 为随机长串；不要使用默认值。
- `CORS_ORIGINS` 改成实际前端域名，不要长期保留 `*`。
- 只使用合成演示数据；不要上传真实账单。
- 不要提交 `backend/.env`、`deploy/.env`、`backend/smart_life.db`。
- 外网只暴露 80/443；8000/8080 不对公网开放。
- 演示前执行 `python tools/seed_demo.py` 重置数据与 AI 日志。
- 演示后如需停用，直接停止隧道/容器；比赛账号密码赛后更换。
