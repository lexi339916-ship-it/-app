# PROJECT_MEMORY.md

> 项目持续记忆档案。每次会话开始先读本文件；工作结束前更新「快照 / 待办 / 最近变更」。
> 详细方案见 `计划.md`，长期规则见 `AGENTS.md`，本轮审查见 `docs/competition/audit_2026-11-05.md`。

---

## 0. 快照

- 更新时间：2026-11-09
- 当前阶段：**v2.1.0，记录页与设置中心完成**：待办保留原任务月历并新增时间轴/提醒/地点/小知内容点评，点选日期只显示当天，再点取消显示全部；加号移至「今天」日期行右侧放大悬浮；想法与心情使用独立彩色月历、时间轴、一句话记录和内容驱动小知点评；每条记录最多 6 张压缩照片。新增独立设置页统一头像、用户名、账号安全、服务器与关于；此前资产、Agent、统一消息中心、对话式工作台均已完成。外部 P0（AI Key、稳定服务器、Docker、视频/用户测试）仍待条件
- 赛事：第二届全国人工智能应用创新大赛 · 通用赛道 · 消费领域
- 作品名：**知账 · 家庭消费健康 Agent**（暂定）
- 关键截止：**2026-11-10 24:00 报名/作品提交**；校赛 11-11~11-20；区域赛 11-21~12-11；总决赛 12-25~12-27
- 演示账号：`judge_demo / judge2026`

---

## 1. 当前可运行状态

- 后端：`http://127.0.0.1:8000`（uvicorn，后台运行）
- API 文档：`http://127.0.0.1:8000/docs`
- 前端 H5：`http://127.0.0.1:8080`（`deploy/h5` 预构建，`deploy/proxy_server.py` 同源代理）
- 演示数据：`backend/smart_life.db`；`judge_demo` 有 65 笔账单、3 个订阅、1 个目标、11 条便签/待办（5 个待办 + 6 条想法/心情，含 3 张演示照片）
- H5 重建：`python tools/build_h5.py`（需要 Node；会覆盖 `deploy/h5`；Windows 下需先停 8080 静态服务）
- **注意**：改 `frontend/` 后要重建 H5；改后端后要重启 uvicorn（当前未开 --reload）

### 本轮新增（2026-11-05）

- **消费健康诊断**：`GET /api/consumption-health/report`，五项指标（预算 30% / 目标 25% / 订阅 15% / 结构 15% / 计划 15%），每项带 formula/inputs/source/period/as_of；覆盖率 <50% 不给总分。
- **健康前端**：首页健康概览卡、完整报告页 `pages/health/report`、Agent 页入口、我的页入口。
- **主动预警补强**：基于健康报告生成，覆盖预算超支/用完/接近上限、订阅涨价/低频/重复、目标延期/停滞、分类/总支出变化、异常大额、计划采购；忽略后 7 天冷却、最多再提醒 2 次；风险升级重新未读。
- **预算语义**：新增 `used_up`（刚好 100%）与 `over100`（真正超出）区分，避免“超支 0 元”。
- **多轮对话**：`agent_runs.session_id/parent_run_id/turn_index`；会话历史/摘要 API；追问“换预算来源 / 只调整 N 元 / 选择替代方案”；旧审批自动 superseded；前端对话线程与“新对话”。
- **消费决策模拟器**：`POST /api/decision-simulator/simulate`；按近 3 月结余/分类预算/储蓄目标计算购买后的预算冲击、目标差额/延期，并给出“现在买/下月买/压缩支出”三方案；前端 `pages/simulator/simulator`。
- **CSV 账单导入**：`/api/imports/preview|preview-file|confirm`；支持通用/微信/支付宝常见表头、UTF-8/GBK、预览去重、错误行、勾选确认；写入 `source=csv`；前端 `pages/import/import`。
- **评测硬化**：100 条（dev/test 各 50）、94 项流程/数据库断言、53 项多轮断言、62 项模拟器断言、47 项 CSV 断言；报告含工具/参数/金额/审批/未审批写入/延迟/成本/解析来源。
- **中文数字**：修复 `一百二=120`、`十五块五=15.5`、`三个月/两年`、`计划一下` 误判 1 元；56 项断言。
- **安全**：登录失败限流（5 次/15 分钟）、密码/验证码/卡号字母数字脱敏、启动默认密钥/CORS 告警、交付检查脚本 `tools/delivery_check.py`。
- **测试时间炸弹**：`tests/smoke_test.py` 固定 `2026-12-01` 改为相对日期。

### 本轮收口与合并（2026-11-05）

- **AI 入口合并**：删除 `pages/ai/assistant.vue` 及路由；截图记账/任务提取/消费总结迁入 Agent 工具抽屉；首页截图草稿通过 `agent_pending_receipt` 进 Agent 确认。
- **统一消息中心**：新增 `GET /api/notifications/summary|list`、`POST /api/notifications/{source}/{id}/action`；聚合 `budget_alerts` 与 `agent_notifications`，按业务键折叠；首页/Agent 右上角消息按钮 + 未读角标 + Agent Tab 角标；我的页消息入口。
- **预算合并**：`pages/budget/plan.vue` 合并为预算中心内弹层；`pages/budget/alerts.vue` 下线；首页/我的/统计移除旧整月预算；`category_budgets` 作为唯一写入源，`/api/budgets` 只读投影。
- **头像**：`users.avatar` + `POST/DELETE /api/auth/avatar`；256×256 JPEG data URL，2MB 上限，去 EXIF；我的页点击上传、长按恢复默认；刷新/重新登录保留。
- **版本统一**：后端 `app/version.py`，前端 `common/app-info.js`、manifest、pages.json、H5 标题统一为“知账 · 家庭消费健康 Agent v2.0.0”。
- **账单来源**：`BillIn.source` 扩展 `agent/csv/subscription`；编辑保留原来源。
- **测试新增**：头像 14、统一通知 33、预算一致性 14、版本 13。
- **浏览器验收**：Agent 工具抽屉（全部 9 个工具）、消息中心进入后红点自动清零、预算方案弹层、头像上传/刷新、v2.0.0 关于页、健康报告分类饼图均已走通。
- **消息入口收敛**：首页/我的不再显示消息按钮或消息卡；消息只在 Agent 页右上角进入；进入消息中心自动把两套通知标为已读，返回后角标消失。
- **账单分类筛选**：账单页新增分类选择抽屉（全部/最近使用/支出分类/收入分类），支持 `category_id` 与类型组合筛选、分页、日历当日明细；月度统计同步按分类过滤，日历热力与汇总不再与列表口径冲突；类型切换自动清除冲突分类，空结果提供一键清除。后端新增 `GET /api/bills?category_id=`、`GET /api/statistics/monthly?category_id=`；17 项断言。
- **个人资产管理（2026-11-06）**：新增 `asset_accounts/asset_liabilities/asset_transactions` 三张表；支持现金/银行/微信/支付宝/储蓄，以及房产/车辆/理财/贵重物品等固定资产，信用卡/分期/借款/房贷等负债；账户增删改、余额调整、转账、还款、欠款调整、流水查询、净资产变化拆解。转账只写两条资产流水，不生成账单、不计入消费。`bills.account_id` 支持新建账单同步余额；`bills.liability_id` 支持信用卡/分期消费自动增加负债，编辑/删除自动冲正；旧账单补关联账户不追溯。前端 `/pages/assets/assets` 从「我的」第一项进入；76 项断言。
- **Agent 资产联动（2026-11-06）**：新增 `asset/simulate` 意图；Agent 可查询总资产/可动用资产/固定资产/负债/净资产，分析本月净资产变化（消费/收入/转账/负债/手动调整、账单关联覆盖率），做购买模拟（预算/目标/可动用资产/应急金），储蓄计划会读取资产上下文但不会把固定资产当作已存目标；38 项断言，100/100 Agent 评测与 94/94 流程评测保持通过。
- **Agent 对话式工作台 v2（2026-11-06）**：`pages/agent/agent` 改为自定义导航 + 欢迎场景 + 独立消息滚动区 + 固定输入区；顶部「知账 AI / 你的个人消费管理助手」+ 提醒/历史/新建；欢迎页四个紧凑场景（我的资产/消费分析/储蓄规划/订阅检查）；用户右侧气泡、AI 左侧气泡；普通回答简洁，复杂任务才显示真实执行计划/工具轨迹；资产/净资产/购买模拟/健康诊断结构化卡；审批卡支持改金额/预算后确认或拒绝，执行后校验与撤销；历史会话抽屉（标题/预览/轮数/继续/软删除）与记忆管理；输入区支持多行文本、语音 ASR、图片 OCR、工具菜单和发送，并增加常用语提示（你好/你是谁/本月消费/我的资产/检查订阅/预算剩余）。移除固定模式切换，前端统一 auto；新增 `chat` 意图，简单问候/身份/感谢由确定性话术回答，不调用模型、不编造业务数字。工具菜单改为「智能分析 / 账单与管理」两组紧凑列表，保留全部 9 个真实工具；提醒不再铺首页，统一进入提醒中心分组查看/交给 Agent/忽略。后端新增 health 意图与通知 group 筛选；`apiTranscribeVoice` 重新接回。新增 `tests/agent_health_test.py` 17 项、通知分组 4 项；100/100 Agent 评测、94/94 流程评测通过。

### 本轮便签页改造（2026-11-09）

- **三模式**：顶部「记录 / AI助手」+ 类型下拉，支持待办、想法、心情；待办保留原月历/清单/看板，日历头部不再放加号；新建任务加号改为在「今天」日期行右侧放大悬浮，覆盖在任务卡上方；想法/心情使用主题色月历、记录天数、日期分组时间轴。
- **待办时间轴**：日历下方按日期分组，左侧时间、提醒时间、地点、优先级、完成勾选；提醒时间默认比截止时间提前 10 分钟，已完成任务显示截止时间；保留点击编辑与完成回写。
- **想法/心情**：月历标记有记录的日期，显示“太棒了！你本月已经记录了 N 天”；卡片包含时间、类型徽章、标题、正文、照片和小知点评；底部固定“一句话轻松记录…”输入，回车/发送写入真实接口。
- **小知点评**：改为严格内容驱动——每条提示先提取并引用记录标题/正文中的实际内容，再按主题（做饭、写作、学习、采购、运动、快递、房租、喝水、情绪等）给对应评价；未命中主题时只基于当前记录提示补充下一步/时间，不再套用无关通用夸奖。全部是前端确定性规则，不调用模型、不做心理诊断，统一以“小知”呈现，不另立 AI 人格；新增 `tests/note_tips_test.mjs` 17 项内容匹配测试。
- **照片**：新增 `POST /api/notes/photo`，单张输入 ≤6MB，服务端校验图片、去除 EXIF、最长边 1280、JPEG 80 后返回 data URL；每条记录最多 6 张，`notes.images` 以 JSON 数组保存，卡片用约 76px 小缩略图自动换行排列，支持多图预览。前端上传 401 自动续期一次；失败保留“改用文字”路径。
- **数据与头像**：`Note.entry_type`（note/idea/mood）、`location`、`image`；`database/schema.sql` 与启动 ALTER 同步；头部头像读取当前用户头像，未设置时回退猫头像。
- **测试**：`tests/notes_entries_test.py` 25 项（分类、地点、单图/多图、最多 6 张、旧便签兼容、用户隔离）；`tests/smoke_test.py` 59 项保持通过。

### 本轮设置中心与待办筛选（2026-11-09）

- **独立设置页**：新增 `/pages/settings/settings`，统一头像更换/恢复默认、展示用户名修改、登录账号只读、账号与安全（修改密码）、服务器地址、关于系统、退出登录；我的页只保留概览、常用功能和设置入口。
- **版本 2.1.0**：`app-info.js`、`version.py`、manifest（versionCode 210）、版本测试同步；关于系统改为当前最新能力和 v2.1.0 更新日志。
- **待办筛选**：日历默认不选中任何日期，时间轴显示全部；点击某一天只显示该天任务，再点同一天或“查看全部”恢复全部；切换月份清除筛选；选中无任务日期时显示空态并可直接按该日期新建。
- **测试**：`tests/version_test.py` 13/13（2.1.0）；`tests/smoke_test.py` 59/59；H5 已重建并浏览器验证设置页、关于展开、我的页入口、日期筛选/取消与悬浮加号。

### 收尾审计（2026-11-09）

- 确定性测试 23 个脚本全部通过（758 项断言）；后端日志无 Traceback；`/api/health` 与 Agent health 均为 2.1.0，Agent 9 个工具、AI 已配置。
- 交付检查：13 项通过、4 项警告；警告为本地 `backend/.env`、21 个数据库文件、缺少演示视频、匿名检查待人工完成。Release 包已排除密钥/数据库。
- 待处理风险：CORS 仍为 `*`；公开 HTTPS 地址、Docker 实跑、视频、5–8 名用户验证仍缺；AI Key 需在供应商控制台轮换。
- 代码层非阻断问题：记录照片以 base64 存在 `notes.images`，列表一次返回最多 200 条，图片多时响应会变大；`NoteOut.image` 为首图兼容字段，会重复一份首图；密码修改不会使旧 refresh token 失效；头像/截图/语音上传仍未复用 401 自动续期；设置/我的页错误态主要依赖全局 toast。
- 演示库有 2 条非 seed 记录（“今天下午做一份拌面”“不想工作”），正式演示前决定保留或 `python tools/seed_demo.py` 重置。

### 之前已完成

- Agent 四张表、`/api/agent/*`、三英雄场景、审批/撤销/审计、前端工作台、演示数据、Docker/Nginx 部署文件。
- 记忆、目标周期、多笔账单、审批过期/原子/真实校验/编辑、主动通知、订阅计费幂等、语音转写接口。

### 最近测试结果（2026-11-05 真实运行）

- `python tests/smoke_test.py`：**59/59**
- `python tests/agent_smoke.py`：**64/64**
- `python tests/subscription_sync_test.py`：**13/13**
- `python tests/voice_smoke.py`：**7/7**（mock ASR）
- `python tests/health_report_test.py`：**52/52**
- `python tests/proactive_alerts_test.py`：**32/32**
- `python tests/chinese_number_test.py`：**56/56**
- `python tests/security_test.py`：**13/13**
- `python tests/multi_turn_test.py`：**53/53**
- `python tests/decision_simulator_test.py`：**62/62**
- `python tests/csv_import_test.py`：**47/47**
- `python tests/avatar_test.py`：**14/14**
- `python tests/notifications_test.py`：**37/37**（含提醒分组筛选）
- `python tests/budget_consistency_test.py`：**14/14**
- `python tests/version_test.py`：**13/13**（v2.1.0，manifest versionCode 210）
- `python tests/bills_filter_test.py`：**17/17**（分类、类型组合、月度统计、用户隔离）
- `python tests/assets_test.py`：**76/76**（账户/负债/固定资产/转账/账单与负债联动/用户隔离/Decimal 精度）
- `python tests/agent_assets_test.py`：**38/38**（资产查询/净资产变化/购买模拟/储蓄计划/用户隔离）
- `python tests/agent_session_test.py`：**16/16**（历史标题/预览、继续会话、软删除、审计保留、跨用户）
- `python tests/agent_health_test.py`：**17/17**（健康诊断意图、真实报告卡、无审批、用户隔离）
- `python tests/agent_chat_test.py`：**16/16**（你好/你是谁/谢谢、业务问候不误判）
- `python tests/notes_entries_test.py`：**25/25**（待办/想法/心情分类、地点、单图/多图与最多 6 张、旧便签兼容、用户隔离）
- `node --experimental-default-type=module tests/note_tips_test.mjs`：**17/17**（拌面/周报/读书/绿植/情绪/喝水/房租等提示必须引用原文并命中正确主题）
- `python tests/agent_eval/run_eval.py --split all`：**100/100**；工具 100%、参数 100%、金额一致性 100%、审批一致性 100%、未审批写入 0；模型 21 条 + 规则 8 条；平均 1135ms，P95 6183ms
- `python tests/agent_eval/run_eval.py --split test`：**50/50**；模型 11 条 + 规则 3 条；平均 979ms，P95 5164ms
- `python tests/agent_eval/run_flow_eval.py`：**94/94**

---

## 2. 当前待办（按优先级）

### P0：提交前必须完成（外部事项）

- [x] **JWT 轮换**：已生成 64 位随机 JWT_SECRET 并重启后端
- [ ] **AI Key 轮换（外部控制台）**：必须在模型供应商控制台吊销旧 Key、生成新 Key；本机不能代办
- [x] **无密钥交付包**：`release/知账_提交包_20261109.zip`，已排除 `.env`/`*.db`/缓存/依赖；338 文件、0.94MB
- [~] **公网部署**：serveo 临时隧道曾验证 8/8，但连接不稳定、已断开；**当前没有可用的公网地址**，不能作为正式提交链接；稳定域名/服务器仍待提供
- [ ] **Docker 验证**：本机未安装 Docker，`docker compose config` + 完整启动尚未实跑
- [x] **PPT 20 页**：`docs/competition/知账_比赛PPT.pptx`，20 页、532KB、16:9；结构/越界/占位检查通过（本机无 LibreOffice，未做渲染级视觉 QA）
- [~] **6 分钟视频**：`docs/competition/video_script.md` 已更新到 100 条评测与新增能力；真实录屏未录制
- [ ] **用户验证**：5–8 名目标用户做 3 个任务，记录耗时/SUS/原话（不要编造）
- [~] **匿名检查**：PPT 已检查无学校/姓名/Logo，作者为“知账团队”；视频与演示页待录/待查
- [ ] **报名/缴费**：确认 11-10 24:00 前完成

### P1：系统继续补强

- [x] 多轮会话最小可用版本：`session_id/parent_run_id/turn_index`、前端对话线程、换来源/改金额/选替代方案；复杂多轮上下文仍可扩展
- [x] 消费决策模拟器最小可用版本：预算冲击、目标差额/延期、三方案对比；更复杂的收入变化/分期场景仍可扩展
- [ ] 语音真实端到端：麦克风、真实 ASR、噪声/空识别/超时/权限拒绝
- [ ] 成本/性能面板：真实 token 账单、`/api/agent/run` 频率限制
- [x] CSV 导入最小可用版本；家庭共享账本仍待开发

### P2：全国赛方向

- [ ] 家庭多角色审批
- [ ] 长期消费行为分析
- [ ] 多模态交互增强
- [ ] 更大规模用户验证
- [ ] 产业合作与试点验证

---

## 3. 已知问题 / 边界

- `backend/.env` 仍含真实 AI Key（JWT_SECRET 已轮换）；`backend/smart_life.db` 是合成演示库。二者均**未进入** `release/` 交付包，但本机提交前仍建议删除/轮换 AI Key。
- `backend/.env` 的 `AI_DAILY_LIMIT=30`；连续跑多轮评测会触发限流并自动走规则降级，报告会显示模型/规则条数。
- Docker 未安装，`deploy/` 组合未实跑。serveo 临时隧道连接不稳定，多次断开；当前无可用公网地址。正式地址需云服务器 + 域名 + HTTPS，并用 `deploy/verify_public.py` 验收。
- 通知自动扫描只在前端 `onShow` 触发，没有后台定时任务/推送。
- 语音入口已重新接回 Agent 输入区，复用 `/api/voice/transcribe`；真实麦克风/ASR 链路尚未做端到端自动化。图片 OCR 的浏览器文件选择在 IAB 中不可自动化，只验证了入口与后端解析链路。
- Agent 对话页的“执行过程”是请求返回后的真实轨迹，不是逐秒流式进度；H5/真机键盘弹起仅做布局与 `100dvh`/`adjust-position` 处理，仍需真机复测。
- 会话标题取首轮用户原话，暂未使用模型生成标题；删除会话为软删除，审计轨迹保留。
- 多轮、模拟器、CSV 已实现最小闭环；本轮完成 AI 入口/预算/通知/版本/头像收口。更复杂的跨任务上下文、长对话摘要、收入变化/分期模拟、家庭协作未实现。
- 统一通知是“聚合读模型”：两张源表保留，旧接口兼容；彻底单表迁移未做。
- 个人资产是独立账本：资产账户只有显式关联 `account_id` 的新账单/已关联账单才影响余额，旧账单补关联不追溯；`bills.liability_id` 支持信用卡/分期消费自动增加负债，账户与负债互斥。Agent 不自动转账/还款，只做查询、模拟与规划审批。
- 资产账户/负债删除采用归档策略：有流水时保留记录并可在“已停用”中恢复；无流水时物理删除。
- 头像以 base64 存 `users.avatar`，登录响应会略增大；已限制 256×256/2MB。
- 便签照片以压缩后的 base64 存在 `notes.images` JSON 数组，单条最多 6 张，单张输入上限 6MB、输出最长边 1280 JPEG；旧 `notes.image` 保留兼容。未接对象存储/云端 CDN。小知点评与提醒是前端确定性文案规则，不是模型生成，也不构成心理诊断或专业建议。
- 旧整月预算 `/api/budgets` 仍保留兼容：无分类预算时可用，有分类预算时只读投影，PUT 返回 409。
- CSV 导入只做通用/微信/支付宝常见表头；特殊银行流水、加密文件、多币种未覆盖。
- `cost` 是估算值（AI 记账 0.002 元/次），不是真实 token 账单。
- 100/100 与 94/94 是团队自测；dev/test 是预设划分，不是严格盲测；不能写成第三方认证。
- 健康分覆盖不足 50% 时返回 `overall_score=null`，前端显示“数据不足”。
- H5 已重建；已用真实浏览器验证首页健康卡 → 健康报告 → Agent 审批卡 → 拒绝、三轮追问（换预算来源 → 只调整 100 元 → 拒绝）、决策模拟页（5000 元 / 改为 1000 元重新测算）和账单分类抽屉（截图确认布局，列表/日历/空态均走通）。

---

## 4. 关键路径

- 后端：`backend/app`
- Agent：`backend/app/services/agent/`
- 健康诊断：`backend/app/services/health_service.py`、`backend/app/routers/consumption_health.py`
- 决策模拟：`backend/app/services/decision_simulator.py`、`backend/app/routers/decision_simulator.py`
- 前端健康页：`frontend/pages/health/report.vue`
- 账单分类筛选：`frontend/pages/bills/list.vue`、`backend/app/routers/bills.py`、`backend/app/routers/statistics.py`
- 个人资产：`backend/app/services/asset_service.py`、`backend/app/routers/assets.py`、`frontend/pages/assets/assets.vue`、`frontend/components/assets/asset-form-sheet.vue`、`frontend/api/assets.js`
- Agent 资产联动：`backend/app/services/agent/orchestrator.py`（`_run_asset/_run_simulate`）、`backend/app/services/decision_simulator.py`、`tests/agent_assets_test.py`
- Agent 对话页：`frontend/pages/agent/agent.vue`、`frontend/components/agent/*`、`frontend/components/agent-tool-sheet.vue`、`backend/app/services/agent/orchestrator.py`（health）、`tests/agent_session_test.py`、`tests/agent_health_test.py`
- 记录/便签：`frontend/pages/notes/list.vue`、`frontend/pages/notes/edit.vue`、`frontend/common/note-tips.js`、`backend/app/routers/notes.py`、`tests/notes_entries_test.py`、`tests/note_tips_test.mjs`
- 设置中心：`frontend/pages/settings/settings.vue`、`frontend/pages/profile/profile.vue`、`frontend/common/app-info.js`、`backend/app/version.py`
- 前端模拟器：`frontend/pages/simulator/simulator.vue`、`frontend/api/simulator.js`
- 统一消息：`frontend/pages/notifications/notifications.vue`、`frontend/components/notification-bell.vue`、`frontend/store/notifications.js`
- 头像/版本：`frontend/common/app-info.js`、`backend/app/version.py`
- CSV 导入：`backend/app/services/csv_import.py`、`backend/app/routers/imports.py`、`frontend/pages/import/import.vue`、`frontend/api/imports.js`
- Agent 页：`frontend/pages/agent/agent.vue`
- 数据库：`database/schema.sql`（本轮 `agent_runs` 新增 `session_id/parent_run_id/turn_index`，启动时自动 ALTER）
- 演示数据：`tools/seed_demo.py`
- 测试：`tests/`、`tests/agent_eval/`
- 交付检查：`tools/delivery_check.py`
- 部署：`deploy/`
- 参赛材料：`docs/competition/`
- 计划：`计划.md`；规则：`AGENTS.md`

---

## 5. 最近变更

- 2026-11-04：Agent 四表、运行时、三场景、前端工作台、演示数据、Docker/Nginx 文件。
- 2026-11-04：记忆、目标周期、多笔账单、审批过期/原子/校验/编辑、主动通知、订阅计费幂等、语音转写接口。
- 2026-11-05：全面审查代码与测试，输出 `docs/competition/audit_2026-11-05.md`。
- 2026-11-05：新增消费健康诊断服务/API/前端页/首页卡/Agent 与我的入口；H5 重建。
- 2026-11-05：主动预警重构（7 类风险、去重、忽略冷却、风险升级）。
- 2026-11-05：新增 `used_up` 预算状态，修复“超支 0 元”。
- 2026-11-05：评测扩到 100 条 + 94 项流程断言；更新 `docs/competition/evaluation.md`。
- 2026-11-05：中文数字/目标周期/口语噪声修复；56 项断言。
- 2026-11-05：登录限流、敏感信息脱敏增强、交付检查脚本、测试时间炸弹修复。
- 2026-11-05：P1 多轮对话最小可用版本：会话字段/API、追问重规划、superseded 审批、前端对话线程；53 项断言。
- 2026-11-05：P1 消费决策模拟器：预算冲击/目标差额与延期/三方案；前端页面与 Agent/我的入口；62 项断言。
- 2026-11-05：P1 CSV 账单导入：通用/微信/支付宝表头、UTF-8/GBK、预览去重、确认导入；47 项断言。
- 2026-11-05：系统收口 v2.0.0：删除旧 AI 助手/预算方案页/预警页；统一消息中心、头像上传、Agent 工具抽屉、预算单写入口；新增 68 项相关断言。
- 2026-11-05：健康报告“分类消费结构”增加环形饼图（复用后端分类金额与分类配色）。
- 2026-11-06：v2.0.0 代码已推送到 GitHub `lexi339916-ship-it/-app`，commit `1f8637b`；仓库不含 `.env`、数据库、node_modules、release。
- 2026-11-06：账单页新增分类选择抽屉与分类筛选；`/api/bills`、`/api/statistics/monthly` 支持 `category_id`；H5 重建并用浏览器验证列表、日历、空态、类型冲突和最近使用；17 项断言。
- 2026-11-06：个人资产管理第一阶段完成：资产账户/负债/流水三表、`/api/assets/*`、账单账户联动与冲正、资产页/表单/我的入口；52 项断言，浏览器验证新增账户、负债还款、转账与流水。GitHub 提交 `54fae24` 已推送。
- 2026-11-06：资产模块扩展：房产/车辆/理财/贵重物品、可动用/固定资产拆分；信用卡/分期账单 `liability_id` 自动增加负债并支持编辑/删除冲正；Agent 资产查询/净资产变化/购买模拟/储蓄计划资产上下文；归档账户/负债可恢复；76+38 项断言，100/100 Agent 评测、94/94 流程评测通过。GitHub 提交 `5863632` 已推送。
- 2026-11-06：Agent 页面按用户要求回退到 1.0.0 工作台布局，保留新增资产/负债/购买模拟工具与标签，移除语音入口和前端语音封装；H5 已重建。后端会话摘要/软删除接口保留，页面不再展示历史抽屉。GitHub 提交 `44be14a` 已推送。
- 2026-11-06：Agent 对话式工作台 v2 完成：无模式切换、四个欢迎场景、固定输入区（文本/语音/图片/工具）、历史会话软删除、紧凑双组工具菜单、健康诊断 Agent 意图、提醒中心分组与交给 Agent；新增 health 17 项、通知分组 4 项；100/100 评测、94/94 流程通过；H5 重建并浏览器验收。GitHub 提交 `4767ea2` 已推送。
- 2026-11-07：Agent 新增常用语提示与简单对话：后端 `chat` 意图确定性回答问候/身份/感谢，带业务词的问候仍走原意图；新增 `tests/agent_chat_test.py` 16 项；100/100 评测、94/94 流程通过。GitHub 提交 `7e6045c` 已推送。
- 2026-11-07：Agent 输入区细化：拍照记账移到输入框上方固定快捷条；任务提取从智能分析移到「订阅管理」旁，并把欢迎页第四个快捷场景「订阅检查」替换为「任务提取」；常用语改为点击输入框后弹出的选择面板，选择后填入输入框；工具菜单移除重复的截图记账入口。GitHub 提交 `a79f646` 已推送。
- 2026-11-07：欢迎页第四个快捷场景正式替换为「任务提取」，点击直接打开任务草稿面板；订阅检查仍通过常用语和订阅管理访问。GitHub 提交 `89f96ea` 已推送。
- 2026-11-07：提醒中心筛选改为单行横向滚动胶囊，增加「收起/展开」开关；胶囊不换行、不压缩，默认展开，可收起只保留当前筛选摘要。GitHub 提交 `3002aba` 已推送。
- 2026-11-09：便签页三模式改版：待办保留原日历，下方新增日期分组时间轴、提醒时间、地点和小知温馨提醒；新建任务加号从日历头移到「今天」日期行右侧，放大并悬浮在任务卡上方；想法/心情新增主题月历、时间轴、一句话记录；头像读取当前用户。
- 2026-11-09：想法/心情加入小知点评和照片上传：`POST /api/notes/photo` 压缩去 EXIF，`notes.images` 支持最多 6 张、小缩略图自动换行；新增 `tests/notes_entries_test.py` 25 项，冒烟 59 项保持通过。小知点评改为严格引用记录内容，新增 `tests/note_tips_test.mjs` 17 项，杜绝无关通用点评。新建任务加号移到「今天」日期行右侧、放大并悬浮在任务卡上方。GitHub 提交 `ac4d421`、`4d3224f` 已推送。
- 2026-11-09：版本升到 2.1.0；新增独立设置页统一头像、用户名、账号安全、服务器、关于和退出；我的页收敛为概览/常用功能/设置入口。待办日历支持点日期只显示当天、再点取消显示全部；切换月份清除筛选。本地提交 `ff75b85` 已推送到 GitHub。
- 2026-11-05：外部 P0 部分完成：JWT 轮换；无密钥交付包 313 文件/0.85MB；PPT 20 页/532KB；serveo 临时公网 8/8 验证；AI Key 轮换与稳定服务器仍待外部条件。

---

## 6. 每次会话开始

1. 读本文件。
2. 读 `AGENTS.md`。
3. 检查 `http://127.0.0.1:8000/api/health` 和 `http://127.0.0.1:8080`。
4. 从「当前待办」第一项开始，不要重复已完成工作。
5. 结束前更新本文件的「快照 / 待办 / 最近变更」。
