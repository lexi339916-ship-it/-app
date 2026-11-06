/** 与后端 REST API 一一对应的接口封装 */
import http, { getBaseUrl } from './request.js'
import store from '../store/user.js'

// ---- 认证 ----
export const apiRegister = (data) => http.post('/api/auth/register', data)
export const apiLogin = (data) => http.post('/api/auth/login', data)
export const apiMe = () => http.get('/api/auth/me')
export const apiUpdateMe = (data) => http.put('/api/auth/me', data)
export const apiDeleteAvatar = () => http.delete('/api/auth/avatar')

// ---- 分类 ----
export const apiCategories = (type) => http.get('/api/categories', type ? { type } : {})
export const apiAddCategory = (data) => http.post('/api/categories', data)

// ---- 账单 ----
export const apiBills = (params) => http.get('/api/bills', params)
export const apiAddBill = (data) => http.post('/api/bills', data)
export const apiBill = (id) => http.get(`/api/bills/${id}`)
export const apiUpdateBill = (id, data) => http.put(`/api/bills/${id}`, data)
export const apiDeleteBill = (id) => http.delete(`/api/bills/${id}`)

// ---- 便签 ----
export const apiNotes = (params) => http.get('/api/notes', params)
export const apiAddNote = (data) => http.post('/api/notes', data)
export const apiNote = (id) => http.get(`/api/notes/${id}`)
export const apiUpdateNote = (id, data) => http.put(`/api/notes/${id}`, data)
export const apiDeleteNote = (id) => http.delete(`/api/notes/${id}`)

// ---- 预算 ----
export const apiBudget = (month) => http.get('/api/budgets', { month })
export const apiSetBudget = (data) => http.put('/api/budgets', data)

// ---- 储蓄目标 ----
export const apiGoals = () => http.get('/api/goals')
export const apiAddGoal = (data) => http.post('/api/goals', data)
export const apiDepositGoal = (id, amount) => http.post(`/api/goals/${id}/deposit`, { amount })
export const apiDeleteGoal = (id) => http.delete(`/api/goals/${id}`)
// 存入记录：查看 / 改金额 / 删除某一笔
export const apiGoalDeposits = (id) => http.get(`/api/goals/${id}/deposits`)
export const apiUpdateDeposit = (id, amount) => http.put(`/api/goals/deposits/${id}`, { amount })
export const apiDeleteDeposit = (id) => http.delete(`/api/goals/deposits/${id}`)

// ---- 生活挑战 ----
export const apiChallenges = () => http.get('/api/challenges')
export const apiAddChallenge = (data) => http.post('/api/challenges', data)
export const apiDeleteChallenge = (id) => http.delete(`/api/challenges/${id}`)

// ---- 自动订阅扣费（用户手动录入的周期固定支出，不抓取第三方续费状态） ----
export const apiSubscriptions = () => http.get('/api/subscriptions')
export const apiAddSubscription = (data) => http.post('/api/subscriptions', data)
export const apiUpdateSubscription = (id, data) => http.put(`/api/subscriptions/${id}`, data)
export const apiToggleSubscription = (id) => http.post(`/api/subscriptions/${id}/toggle`, {})
export const apiDeleteSubscription = (id) => http.delete(`/api/subscriptions/${id}`)
// 进账单页/打开小程序时调用：后端按服务器日期补生成到期账单，并返回扣费前1天提醒
export const apiSubscriptionSync = () => http.post('/api/subscriptions/sync', {})

// ---- 统计 ----
export const apiMonthlyStats = (month, categoryId) =>
  http.get('/api/statistics/monthly',
    categoryId != null ? { month, category_id: categoryId } : { month })
export const apiCategoryStats = (month, type) => http.get('/api/statistics/categories', { month, type })
export const apiChannelStats = (month, type) => http.get('/api/statistics/channels', { month, type })
export const apiProfileStats = () => http.get('/api/statistics/profile')

// ---- AI ----
export const apiParseBill = (text) => http.post('/api/ai/parse-bill', { text })
export const apiParseNote = (text) => http.post('/api/ai/parse-note', { text })
export const apiSummary = (period = 'month') => http.get('/api/ai/summary', { period })
export const apiInsight = (refresh = false) => http.get('/api/ai/insight', refresh ? { refresh: 1 } : {})
export const apiAsk = (question) => http.post('/api/ai/ask', { question })

// ---- Agent 工作台 ----
export const apiAgentRun = (message, mode = 'auto', sessionId = null, parentRunId = null) =>
  http.post('/api/agent/run', {
    message,
    mode,
    ...(sessionId ? { session_id: sessionId } : {}),
    ...(parentRunId ? { parent_run_id: parentRunId } : {}),
  })
export const apiAgentRuns = (limit = 8) => http.get('/api/agent/runs', { limit })
export const apiAgentSession = (sessionId) => http.get(`/api/agent/sessions/${sessionId}`)
export const apiAgentSessions = (limit = 10) => http.get('/api/agent/sessions', { limit })
export const apiAgentRunDetail = (runId) => http.get(`/api/agent/runs/${runId}`)
export const apiAgentApproval = (approvalId, decision, edits = {}) =>
  http.post(`/api/agent/approvals/${approvalId}`, { decision, edits })
export const apiAgentUndo = (runId) => http.post(`/api/agent/runs/${runId}/undo`, {})
export const apiAgentScan = () => http.post('/api/agent/proactive/scan', {})
export const apiAgentNotifications = (status = '', limit = 20) =>
  http.get('/api/agent/notifications', { status, limit })
export const apiAgentNotificationAction = (id, action) =>
  http.post(`/api/agent/notifications/${id}/action`, { action })
export const apiAgentUnreadCount = () => http.get('/api/agent/notifications/unread-count')
export const apiAgentHealth = () => http.get('/api/agent/health')
export const apiAgentMemories = () => http.get('/api/agent/memories')
export const apiDeleteAgentMemory = (id) => http.delete(`/api/agent/memories/${id}`)

// ---- 消费健康诊断（后端确定性计算，模型不参与分数） ----
export const apiHealthReport = (month) =>
  http.get('/api/consumption-health/report', month ? { month } : {})

// ---- 消费决策模拟（买之前先算一算） ----
export const apiSimulateDecision = (data) =>
  http.post('/api/decision-simulator/simulate', data)

// ---- AI 消费预警 & 预算中心（新增模块，独立于旧的整月预算接口） ----
// 预算中心总览：所有支出分类的预算 + 已花 + 占比 + 状态
export const apiBudgetOverview = (month) => http.get('/api/budget-center/overview', { month })
// 手动设置单个分类的月度预算（upsert）
export const apiSetCategoryBudget = (data) => http.put('/api/budget-center/category', data)
// 批量写入分类预算（AI 方案采纳 / 编辑后保存）
export const apiSetCategoryBudgetsBatch = (data) => http.put('/api/budget-center/batch', data)
// 记账保存成功后追加调用：检查该账单触发的预警（80% / 100% / 异常大额）
export const apiBillCheck = (billId) => http.post('/api/budget-center/check', { bill_id: billId })
// AI 读取历史账单，推荐初始预算方案（month 是查询参数，拼在 URL 上）
export const apiBudgetRecommend = (month) => http.post(`/api/budget-center/recommend?month=${month}`, {})
// 自然语言存钱目标 → AI 自动分配各分类预算
export const apiAllocateGoal = (data) => http.post('/api/budget-center/allocate-goal', data)
// 一键采纳 AI 预算方案（未改动金额时直接按服务端方案写入）
export const apiApplyPlan = (planId) => http.post(`/api/budget-center/plans/${planId}/apply`, {})
// 弹性调度建议：把结余分类的额度调配给快超支的分类
export const apiRebalance = (month) => http.get('/api/budget-center/rebalance', { month })
// 待办计划采购联动：识别大额采购并预判资金压力
export const apiPlannedPurchase = (month) => http.get('/api/budget-center/planned-purchase', { month })
// 预警消息中心：列表 / 未读数 / 操作（read 已读、dismissed 忽略、accepted 采纳）
export const apiBudgetAlerts = (params) => http.get('/api/budget-center/alerts', params)
export const apiAlertUnreadCount = () => http.get('/api/budget-center/alerts/unread-count')
export const apiAlertAction = (id, action) => http.post(`/api/budget-center/alerts/${id}/action`, { action })

// ---- 统一消息中心（聚合预算预警 + Agent 通知） ----
export const apiNotificationSummary = () => http.get('/api/notifications/summary')
export const apiUnifiedNotifications = (params = {}) => http.get('/api/notifications', params)
export const apiUnifiedNotificationAction = (source, id, action) =>
  http.post(`/api/notifications/${source}/${id}/action`, { action })
export const apiMarkAllNotificationsRead = () =>
  http.post('/api/notifications/read-all', {})

/** 上传头像（multipart） */
export const apiUploadAvatar = (filePath) => new Promise((resolve, reject) => {
  uni.uploadFile({
    url: getBaseUrl() + '/api/auth/avatar',
    filePath,
    name: 'file',
    timeout: 60000,
    header: store.token ? { Authorization: 'Bearer ' + store.token } : {},
    success(res) {
      let body = {}
      try { body = JSON.parse(res.data) } catch (e) { body = {} }
      if (res.statusCode >= 200 && res.statusCode < 300) {
        resolve(body)
      } else {
        const message = body.message || `头像上传失败（${res.statusCode}）`
        uni.showToast({ title: message, icon: 'none' })
        reject({ status: res.statusCode, message, body })
      }
    },
    fail() {
      const message = '头像上传失败，请检查网络'
      uni.showToast({ title: message, icon: 'none' })
      reject({ status: -1, message, body: null })
    },
  })
})

/** 上传支付截图（multipart），返回识别草稿 */
export const apiParseReceipt = (filePath) => new Promise((resolve, reject) => {
  uni.uploadFile({
    url: getBaseUrl() + '/api/ai/parse-receipt',
    filePath,
    name: 'file',
    timeout: 60000,
    header: store.token ? { Authorization: 'Bearer ' + store.token } : {},
    success(res) {
      let body = {}
      try { body = JSON.parse(res.data) } catch (e) { body = {} }
      if (res.statusCode >= 200 && res.statusCode < 300) {
        resolve(body)
      } else {
        const message = body.message || `上传失败（${res.statusCode}）`
        uni.showToast({ title: message, icon: 'none' })
        reject({ status: res.statusCode, message, body })
      }
    },
    fail() {
      const message = '网络连接失败，请检查后端服务'
      uni.showToast({ title: message, icon: 'none' })
      reject({ status: -1, message, body: null })
    },
  })
})

/** 上传录音并转写为文字（按住说话） */
export const apiTranscribeVoice = (filePath) => new Promise((resolve, reject) => {
  uni.uploadFile({
    url: getBaseUrl() + '/api/voice/transcribe',
    filePath,
    name: 'file',
    timeout: 60000,
    header: store.token ? { Authorization: 'Bearer ' + store.token } : {},
    success(res) {
      let body = {}
      try { body = JSON.parse(res.data) } catch (e) { body = {} }
      if (res.statusCode >= 200 && res.statusCode < 300) {
        resolve(body)
      } else {
        const message = body.message || `语音识别失败（${res.statusCode}）`
        uni.showToast({ title: message, icon: 'none', duration: 2500 })
        reject({ status: res.statusCode, message, body })
      }
    },
    fail() {
      const message = '语音上传失败，请检查网络或改用文字'
      uni.showToast({ title: message, icon: 'none' })
      reject({ status: -1, message, body: null })
    },
  })
})
