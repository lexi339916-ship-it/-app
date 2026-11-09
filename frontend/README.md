# uni-app 前端

## 运行

1. 使用 **HBuilderX** 导入本目录（Vue 3 + `<script setup>`）。
2. 先启动后端（见 `backend/README.md`），默认地址 `http://127.0.0.1:8000`。
3. HBuilderX 中选择「运行 → 运行到浏览器」调试 H5；或使用 `python tools/build_h5.py` 输出到 `deploy/h5`。
4. 真机调试时，把 `common/config.js` 的 `BASE_URL` 改为电脑局域网 IP，或在“我的 → 服务器地址”里保存。

## 信息架构

| 模块 | 路径 | 说明 |
| --- | --- | --- |
| 登录/注册 | `pages/login`、`pages/register` | 登录态校验、刷新令牌 |
| 首页 | `pages/index/index` | 收支、消费健康卡、未读消息、最近账单、待办 |
| Agent | `pages/agent/agent` | 唯一 AI 入口：对话、欢迎场景、历史会话、工具菜单、语音/图片、审批与执行 |
| 账单 | `pages/bills/list`、`pages/bills/edit` | 列表/日历、手工记账、CSV 导入入口、订阅入口 |
| 消息中心 | `pages/notifications/notifications` | 聚合预算预警与 Agent 通知，已读/忽略/采纳 |
| 预算中心 | `pages/budget/center` | 分类预算、AI 方案弹层、调度、计划采购 |
| 消费健康 | `pages/health/report` | 五项指标、公式、来源、建议 |
| 决策模拟 | `pages/simulator/simulator` | 购买金额对预算/目标的影响与方案 |
| CSV 导入 | `pages/import/import` | 粘贴/文件、预览去重、勾选导入 |
| 目标/订阅 | `pages/goals/goals`、`pages/subscriptions/list` | 储蓄目标、挑战、订阅管理 |
| 统计 | `pages/statistics/statistics` | 收支、分类、渠道、每日分布 |
| 个人资产 | `pages/assets/assets` | 账户/负债/流水、余额调整、转账、还款、净资产 |
| 我的 | `pages/profile/profile` | 头像上传、资产入口、消息、预算、目标、订阅、关于/版本 |

旧 `pages/ai/assistant`、`pages/budget/plan`、`pages/budget/alerts` 已合并下线，不再保留独立路由。

## Agent 能力

- 对话式工作台：知账 AI 欢迎页、四个快捷场景（我的资产/消费分析/储蓄规划/任务提取）、用户/AI 气泡、固定输入区、独立消息滚动区。
- 文本记账/查询/目标/订阅/资产/购买模拟/健康诊断：`/api/agent/run`，前端统一 `auto`，写操作必须审批。
- 多轮对话：`session_id + parent_run_id`，旧审批自动 `superseded`；历史会话支持标题、预览、继续与软删除。
- 执行卡：仅复杂任务展示真实计划/工具轨迹；普通回答只显示正文和数据来源。
- 审批卡：可修改账单金额/分类预算后确认或拒绝；执行后显示校验结果与撤销。
- 工具菜单：两组紧凑列表——智能分析（消费总结、健康诊断、决策模拟）、账单与管理（CSV、预算、任务提取、订阅、目标）；欢迎页任务提取卡片直接打开任务草稿。
- 输入区：多行文本、语音 ASR、工具菜单、发送；拍照记账固定在输入框上方快捷条，识别后确认再写入。
- 常用语：点击输入框后弹出常用语面板（你好/你是谁/本月消费/我的资产/检查订阅/预算剩余），选择后填入输入框。
- 简单对话：你好、你是谁、谢谢等由后端确定性话术回答，不误走记账/查询。
- 提醒：Agent 首页只保留消息/提醒入口，详情进入提醒中心；筛选胶囊单行横向滚动，可收起/展开；支持分组、查看详情、交给 Agent、忽略。
- 头像：`POST /api/auth/avatar`，上传后压缩为 256×256 JPEG，刷新/重新登录仍保留。
- 消息：`GET /api/notifications/summary|list`，顶部消息按钮与 Agent Tab 角标共享未读数。

## 个人资产

- 入口：我的 → 常用功能第一项「个人资产管理」。
- 页面：`pages/assets/assets`，账户/负债/流水三个 Tab；表单在 `components/assets/asset-form-sheet.vue`。
- 资产类型：现金/银行/微信/支付宝/储蓄，房产/车辆/理财/贵重物品；总览区分可动用与固定资产。
- API：`api/assets.js`；金额由后端 Decimal 计算，前端只展示。
- 规则：转账不生成账单；账单只有显式关联 `account_id` 才影响账户余额，关联 `liability_id` 时自动增加负债。

## 状态与网络

- `store/user.js`：token + 用户信息 + 头像；`setUser` 统一刷新。
- `store/notifications.js`：统一未读状态与 TabBar 角标。
- `api/request.js`：Bearer Token、401 刷新一次、统一错误提示。
- `api/index.js`：业务 API 封装；上传类接口复用 `uni.uploadFile`。
- `common/app-info.js`：品牌、版本 2.1.0、能力列表、更新日志。
