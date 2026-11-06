<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  apiAgentRun, apiAgentRuns, apiAgentApproval, apiAgentUndo, apiAgentScan,
  apiAgentMemories, apiDeleteAgentMemory, apiAgentNotificationAction,
  apiAgentSession,
} from '../../api/index.js'
import NotificationBell from '../../components/notification-bell.vue'
import AgentToolSheet from '../../components/agent-tool-sheet.vue'
import { refreshNotifications } from '../../store/notifications.js'

const goal = ref('')
const mode = ref('auto')
const loading = ref(false)
const error = ref(null)
const run = ref(null)
const recentRuns = ref([])
const sessionId = ref('')
const sessionRuns = ref([])
const showTools = ref(false)
const pendingReceipt = ref([])
const scanItems = ref([])
const scanLoading = ref(false)
const deciding = ref(false)
const memories = ref([])

const examples = [
  '午饭花了32元，微信付的',
  '查看我的个人资产',
  '如果花3000元买手机，会影响储蓄目标吗',
  '帮我检查一下订阅，看看有没有涨价或低频的',
  '3个月存3000元去旅行',
  '这个月钱主要花在哪里？',
]

const modes = [
  { key: 'auto', label: '自动' },
  { key: 'query', label: '查询' },
  { key: 'plan', label: '规划' },
  { key: 'action', label: '记账' },
]

const STATUS = {
  running: '规划中',
  awaiting_approval: '等待确认',
  completed: '已完成',
  needs_input: '需要补充',
  failed: '未完成',
  rejected: '已取消',
  undone: '已撤销',
  expired: '已过期',
  superseded: '已被替代',
}

const TOOL_LABELS = {
  intent_router: '理解意图',
  parse_bill: '解析记账',
  get_budget_status: '查询预算',
  get_subscriptions: '查询订阅',
  detect_subscription_issues: '订阅体检',
  parse_goal: '解析目标',
  get_cashflow: '查询收支',
  summarize_spending: '汇总支出',
  largest_bill: '最大支出',
  get_goals: '查询目标',
  get_todos: '查询待办',
  get_asset_overview: '查询资产',
  get_net_worth_change: '分析净资产变化',
  parse_purchase: '解析购买金额',
  simulate_purchase: '测算购买影响',
  asset_write_boundary: '资产操作边界',
  approval_required: '等待审批',
  approval_replanned: '重规划',
  execute_approved_action: '执行动作',
  verify_result: '校验结果',
  undo_approved_action: '撤销执行',
  request_missing_slot: '请求补充',
  approval_expired: '审批过期',
  execute_failed: '执行失败',
}

const pendingApprovals = computed(() =>
  (run.value?.approvals || []).filter(a => a.status === 'pending'))

const hasUndo = computed(() =>
  (run.value?.approvals || []).some(a => a.status === 'approved'))

const canFollowup = computed(() =>
  run.value?.status === 'awaiting_approval' && pendingApprovals.value.length > 0)

const followupExamples = [
  '不想动娱乐预算，还有其他方案吗？',
  '只调整 100 元',
  '选择第二种方案',
]

function billAction(approval) {
  return (approval?.diff?.actions || []).find(a => a.action === 'create_bill')
}

function budgetItems(approval) {
  return (approval?.diff?.actions || [])
    .filter(a => a.action === 'set_category_budgets')
    .flatMap(a => a.items || [])
}

function prepareEdits(r) {
  if (!r?.approvals) return
  for (const approval of r.approvals) {
    const bill = billAction(approval)
    if (bill) {
      approval.editBillAmount = bill.bill.amount
      approval.originalBillAmount = bill.bill.amount
    }
    const items = budgetItems(approval)
    if (items.length) {
      approval.editBudgets = {}
      approval.originalBudgets = {}
      for (const item of items) {
        approval.editBudgets[item.category_id] = item.amount
        approval.originalBudgets[item.category_id] = item.amount
      }
    }
  }
}

function memoryLabel(memory) {
  if (memory.kind === 'merchant_category') {
    return `商户「${memory.key}」→ ${memory.value?.category || '未知分类'}`
  }
  if (memory.kind === 'goal') {
    return `目标「${memory.value?.name || ''}」¥${memory.value?.target_amount || ''}`
  }
  if (memory.kind === 'preference') {
    return `偏好：${memory.key}`
  }
  return `${memory.kind}：${memory.key}`
}

function statusLabel(status) {
  return STATUS[status] || status || '未知'
}

function toolLabel(tool) {
  return TOOL_LABELS[tool] || tool || '步骤'
}

function actionLabel(action) {
  return {
    create_bill: '写入账单',
    set_category_budgets: '调整预算',
    create_goal: '创建目标',
    create_task: '创建任务',
    pause_subscription: '暂停订阅',
    create_memory: '记住偏好',
  }[action] || action
}

function actionDetail(action) {
  if (!action) return ''
  if (action.action === 'create_bill') {
    const b = action.bill || {}
    return `${b.type === 'income' ? '收入' : '支出'} ¥${b.amount} · ${b.category} · ${b.bill_date}`
  }
  if (action.action === 'set_category_budgets') {
    return (action.items || []).map(i => `${i.category_name || i.category_id} ¥${i.amount}`).join('；')
  }
  if (action.action === 'create_goal') {
    return `${action.goal?.name || ''} · ¥${action.goal?.target_amount || ''}`
  }
  if (action.action === 'create_task') {
    return action.note?.title || ''
  }
  if (action.action === 'pause_subscription') {
    return action.subscription_name || ''
  }
  return ''
}

function impactText(approval) {
  const im = approval?.diff?.impact || {}
  if (im.budget) {
    return `预算 ¥${im.budget} · 已花 ¥${im.spent_before} → ¥${im.spent_after} · 记账后剩余 ¥${im.remaining_after}`
  }
  if (im.monthly_target) {
    return `每月需存 ¥${im.monthly_target} · 近 3 月平均结余 ¥${im.avg_monthly_net}`
  }
  if (im.issues) {
    return `发现 ${im.issues.length} 个订阅异常 · 年化影响 ¥${im.annual_impact_total}`
  }
  return ''
}

function evidenceChips(evidence) {
  const list = []
  if (!evidence) return list
  if (evidence.source) list.push('数据：' + evidence.source)
  if (evidence.parser) list.push('解析：' + (evidence.parser === 'ai' ? '模型' : '规则'))
  if (evidence.model) list.push('模型：' + evidence.model)
  if (evidence.as_of) list.push('截至 ' + String(evidence.as_of).replace('T', ' ').slice(0, 16))
  return list
}

function useExample(text) {
  goal.value = text
}

function useScan(item) {
  if (item.alert_type === 'budget') {
    goal.value = `帮我看看「${item.category}」预算，给我一个调整方案`
  } else if (item.alert_type === 'subscription') {
    goal.value = '帮我检查订阅，看看有没有涨价或低频的'
  } else if (item.alert_type === 'goal') {
    goal.value = '帮我重新规划储蓄目标'
  } else {
    goal.value = '帮我评估待办里的计划采购'
  }
  run.value = null
  sessionId.value = ''
  sessionRuns.value = []
  uni.pageScrollTo({ scrollTop: 0, duration: 200 })
}

async function runAgent() {
  const text = goal.value.trim()
  if (!text) {
    uni.showToast({ title: '先告诉我想做什么', icon: 'none' })
    return
  }
  loading.value = true
  error.value = null
  const parentId = sessionId.value && run.value?.session_id === sessionId.value
    ? run.value.run_id : null
  const previous = run.value
  run.value = null
  try {
    const result = await apiAgentRun(text, mode.value, sessionId.value || null, parentId)
    run.value = result
    if (result.session_id) sessionId.value = result.session_id
    prepareEdits(run.value)
    scanItems.value = []
    await loadSession()
    uni.pageScrollTo({ scrollTop: 420, duration: 250 })
  } catch (e) {
    run.value = previous
    error.value = e
  } finally {
    loading.value = false
  }
}

async function loadSession() {
  if (!sessionId.value) {
    sessionRuns.value = []
    return
  }
  try {
    sessionRuns.value = await apiAgentSession(sessionId.value)
  } catch (e) {
    sessionRuns.value = run.value ? [run.value] : []
  }
}

function newSession() {
  sessionId.value = ''
  sessionRuns.value = []
  run.value = null
  goal.value = ''
  error.value = null
}

function openThread(item) {
  run.value = item
  prepareEdits(item)
  uni.pageScrollTo({ scrollTop: 420, duration: 200 })
}

async function decide(approval, decision) {
  if (deciding.value) return
  deciding.value = true
  const edits = {}
  if (decision === 'approved') {
    if (approval.editBillAmount !== undefined && approval.editBillAmount !== ''
        && String(approval.editBillAmount) !== String(approval.originalBillAmount)) {
      edits.bill_amount = approval.editBillAmount
    }
    if (approval.editBudgets && approval.originalBudgets) {
      const changed = {}
      for (const key of Object.keys(approval.editBudgets)) {
        if (String(approval.editBudgets[key]) !== String(approval.originalBudgets[key])) {
          changed[key] = approval.editBudgets[key]
        }
      }
      if (Object.keys(changed).length) edits.budgets = changed
    }
  }
  try {
    run.value = await apiAgentApproval(approval.id, decision, edits)
    prepareEdits(run.value)
    await loadSession()
    loadMemories()
    uni.showToast({
      title: decision === 'approved' ? '已执行，可撤销' : '已拒绝',
      icon: 'none',
    })
  } catch (e) {
    error.value = e
  } finally {
    deciding.value = false
  }
}

async function undo() {
  if (!run.value) return
  uni.showModal({
    title: '撤销执行',
    content: '撤销后，本次写入的账单/预算/任务/目标会恢复原状。确定撤销吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        run.value = await apiAgentUndo(run.value.run_id)
        prepareEdits(run.value)
        await loadSession()
        loadMemories()
        uni.showToast({ title: '已撤销', icon: 'none' })
      } catch (e) {
        error.value = e
      }
    },
  })
}

async function scan(silent = false) {
  if (!silent) scanLoading.value = true
  try {
    const res = await apiAgentScan()
    scanItems.value = res.items || []
    refreshNotifications()
    if (!silent && !scanItems.value.length) {
      uni.showToast({ title: '今天没有需要特别提醒的', icon: 'none' })
    }
  } catch (e) {
    if (!silent) error.value = e
  } finally {
    if (!silent) scanLoading.value = false
  }
}

async function markScanItem(item, action) {
  if (!item.id) return
  try {
    await apiAgentNotificationAction(item.id, action)
    if (action === 'dismissed') {
      scanItems.value = scanItems.value.filter(s => s.id !== item.id)
    } else {
      item.status = 'read'
    }
  } catch (e) {
    error.value = e
  }
}

async function loadRecent() {
  try {
    recentRuns.value = await apiAgentRuns(5)
  } catch (e) { /* 最近任务失败不影响主流程 */ }
}

async function loadMemories() {
  try {
    memories.value = await apiAgentMemories()
  } catch (e) { /* 记忆失败不影响主流程 */ }
}

async function removeMemory(memory) {
  try {
    await apiDeleteAgentMemory(memory.id)
    memories.value = memories.value.filter(m => m.id !== memory.id)
    uni.showToast({ title: '已删除记忆', icon: 'none' })
  } catch (e) {
    error.value = e
  }
}

function openRecent(item) {
  run.value = item
  goal.value = item.goal
  sessionId.value = item.session_id || ''
  prepareEdits(run.value)
  loadSession()
}

function openTools() {
  showTools.value = true
}

function closeTools() {
  showTools.value = false
  pendingReceipt.value = []
}

onShow(() => {
  const pending = uni.getStorageSync('agent_pending_receipt')
  if (pending) {
    try {
      const drafts = JSON.parse(pending)
      if (Array.isArray(drafts) && drafts.length) {
        pendingReceipt.value = drafts
        showTools.value = true
      }
    } catch (e) { /* 忽略损坏的缓存 */ }
    uni.removeStorageSync('agent_pending_receipt')
  }
  loadRecent()
  loadMemories()
  scan(true)
  refreshNotifications()
})
</script>

<template>
  <view class="page">
    <view class="hero">
      <image class="hero-cat" src="/static/doodles/cat.png" mode="widthFix" />
      <view class="hero-text">
        <text class="hero-title">知账 Agent</text>
        <text class="hero-sub">从记一笔，到做对下一步</text>
      </view>
      <NotificationBell />
    </view>

    <view class="card">
      <text class="card-title">今天想让我帮你做什么？</text>
      <textarea class="goal-input" v-model="goal" :maxlength="500" auto-height
        :disabled="loading"
        :placeholder="canFollowup ? '继续追问：不想动娱乐预算 / 只调整 100 元' : '例如：午饭花了32元，微信付的'"
        placeholder-class="ph" />
      <view class="mode-row">
        <text v-for="m in modes" :key="m.key"
          :class="['mode-chip', mode === m.key && 'mode-active']"
          @click="mode = m.key">{{ m.label }}</text>
      </view>
      <view class="example-row">
        <text class="example" v-for="e in examples" :key="e" @click="useExample(e)">{{ e }}</text>
      </view>
      <view class="followup-row" v-if="canFollowup">
        <text class="followup-label">可以继续追问：</text>
        <text class="example" v-for="f in followupExamples" :key="f" @click="useExample(f)">{{ f }}</text>
      </view>
      <view class="health-entry tool-entry" @click="openTools">
        <view class="health-entry-main">
          <text class="health-entry-title">Agent 工具</text>
          <text class="health-entry-sub">截图记账 · 任务提取 · 消费总结 · 资产/健康/模拟</text>
        </view>
        <text class="health-entry-arrow">›</text>
      </view>
      <view class="action-row">
        <button class="btn primary" :class="{ 'btn-off': loading }" :disabled="loading" @click="runAgent">
          {{ loading ? 'Agent 正在规划…' : (canFollowup ? '继续追问' : '运行 Agent') }}
        </button>
        <button class="btn ghost" :class="{ 'btn-off': scanLoading }" :disabled="scanLoading" @click="scan(false)">
          {{ scanLoading ? '扫描中…' : '扫描今日建议' }}
        </button>
      </view>
      <view class="state-box" v-if="error">
        <text class="state-text">{{ error.message || '请求失败，请稍后重试' }}</text>
        <view class="state-actions">
          <button class="btn ghost small" @click="runAgent">重试</button>
        </view>
      </view>
    </view>

    <!-- 主动提醒 -->
    <view class="card" v-if="scanItems.length">
      <view class="card-head">
        <text class="card-title">主动提醒</text>
        <text class="muted">为什么现在</text>
      </view>
      <view class="scan-item" v-for="(s, i) in scanItems" :key="i">
        <view class="scan-main">
          <text :class="['scan-level', 'level-' + s.level]">
            {{ s.level === 'critical' ? '超支' : (s.level === 'warn' ? '关注' : '提示') }}
          </text>
          <text class="scan-title">{{ s.title }}</text>
          <text class="scan-msg">{{ s.message }}</text>
        </view>
        <view class="scan-side">
          <text class="scan-go" @click="useScan(s)">交给 Agent ›</text>
          <view class="scan-actions">
            <text class="scan-action" @click="markScanItem(s, 'read')">已读</text>
            <text class="scan-action" @click="markScanItem(s, 'dismissed')">忽略</text>
          </view>
        </view>
      </view>
    </view>

    <!-- 多轮对话线程 -->
    <view class="card" v-if="sessionRuns.length">
      <view class="card-head">
        <text class="card-title">本轮对话</text>
        <text class="muted" @click="newSession">新对话</text>
      </view>
      <view class="thread-item" v-for="r in sessionRuns" :key="r.run_id" @click="openThread(r)">
        <text class="thread-turn">第 {{ (r.turn_index || 0) + 1 }} 轮</text>
        <view class="thread-main">
          <text class="thread-goal">{{ r.goal }}</text>
          <text class="thread-answer">{{ r.answer }}</text>
        </view>
        <text :class="['status-badge', 'thread-status', 'status-' + r.status]">{{ statusLabel(r.status) }}</text>
      </view>
      <text class="thread-hint" v-if="canFollowup">
        直接改条件即可重算：换预算来源、改调配金额、选择替代方案；旧审批会自动标记为“已被替代”。
      </text>
    </view>

    <!-- 运行结果 -->
    <view class="card" v-if="run">
      <view class="run-head">
        <text :class="['status-badge', 'status-' + run.status]">{{ statusLabel(run.status) }}</text>
        <text class="run-id">#{{ run.run_id }}</text>
      </view>
      <text class="answer">{{ run.answer }}</text>

      <view class="evidence-row" v-if="evidenceChips(run.evidence).length">
        <text class="evidence-chip" v-for="c in evidenceChips(run.evidence)" :key="c">{{ c }}</text>
      </view>

      <view class="plan" v-if="run.plan && run.plan.length">
        <text class="section-title">执行计划</text>
        <view class="plan-item" v-for="(p, i) in run.plan" :key="i">
          <text class="plan-no">{{ i + 1 }}</text>
          <text class="plan-text">{{ p }}</text>
        </view>
      </view>

      <view class="trace" v-if="run.steps && run.steps.length">
        <text class="section-title">工具轨迹</text>
        <view class="trace-item" v-for="s in run.steps" :key="s.seq">
          <text :class="['trace-dot', 'trace-' + s.status]" />
          <view class="trace-main">
            <text class="trace-name">{{ toolLabel(s.tool_name) }}</text>
            <text class="trace-desc">{{ s.step_type }} · {{ s.status === 'wait' ? '等待中' : '完成' }}</text>
          </view>
          <text class="trace-seq">{{ s.seq }}</text>
        </view>
      </view>

      <view class="approval" v-for="a in pendingApprovals" :key="a.id">
        <view class="approval-head">
          <text class="approval-title">等待你确认</text>
          <text class="approval-expire" v-if="a.expires_at">
            有效至 {{ String(a.expires_at).replace('T', ' ').slice(11, 16) }}
          </text>
        </view>
        <text class="approval-summary">{{ a.diff.summary }}</text>
        <view class="impact" v-if="impactText(a)">
          <text>{{ impactText(a) }}</text>
        </view>
        <view class="action-list">
          <view class="action-item" v-for="(act, i) in a.diff.actions" :key="i">
            <text class="action-label">{{ actionLabel(act.action) }}</text>
            <text class="action-detail">{{ actionDetail(act) }}</text>
          </view>
        </view>

        <!-- 审批可编辑：账单金额 + 分类预算 -->
        <view class="edit-box" v-if="billAction(a) || budgetItems(a).length">
          <text class="edit-title">批准前可修改</text>
          <view class="edit-row" v-if="billAction(a)">
            <text class="edit-label">账单金额</text>
            <input class="edit-input" type="digit" v-model="a.editBillAmount" />
            <text class="edit-unit">元</text>
          </view>
          <view class="edit-row" v-for="item in budgetItems(a)" :key="'b' + item.category_id">
            <text class="edit-label">{{ item.category_name || item.category_id }}</text>
            <input class="edit-input" type="digit" v-model="a.editBudgets[item.category_id]" />
            <text class="edit-unit">元</text>
            <text class="edit-before" v-if="item.before">原 ¥{{ item.before }}</text>
          </view>
        </view>

        <view class="approval-btns">
          <button class="btn primary small" :disabled="deciding" @click="decide(a, 'approved')">
            批准执行
          </button>
          <button class="btn ghost small" :disabled="deciding" @click="decide(a, 'rejected')">
            先不要
          </button>
        </view>
        <text class="approval-hint">批准后才会写入账单/预算/任务；执行后可撤销。</text>
      </view>

      <view class="result-row" v-if="run.status === 'completed'">
        <button v-if="hasUndo" class="btn ghost small" @click="undo">撤销上一次执行</button>
        <text class="meta">耗时 {{ run.latency_ms }}ms · 成本 ¥{{ Number(run.cost || 0).toFixed(4) }}</text>
      </view>
    </view>

    <!-- 记忆 -->
    <view class="card" v-if="memories.length">
      <view class="card-head">
        <text class="card-title">Agent 记忆</text>
        <text class="muted">可删除</text>
      </view>
      <view class="memory-row" v-for="m in memories" :key="m.id">
        <text class="memory-text">{{ memoryLabel(m) }}</text>
        <text class="memory-del" @click="removeMemory(m)">×</text>
      </view>
    </view>

    <!-- 最近任务 -->
    <view class="card" v-if="recentRuns.length && !run">
      <text class="section-title">最近任务</text>
      <view class="recent-item" v-for="r in recentRuns" :key="r.run_id" @click="openRecent(r)">
        <view class="recent-main">
          <text class="recent-goal">{{ r.goal }}</text>
          <text class="recent-answer">{{ r.answer }}</text>
        </view>
        <text class="recent-status">{{ statusLabel(r.status) }}</text>
      </view>
    </view>

    <AgentToolSheet :visible="showTools" :initial-receipt="pendingReceipt" @close="closeTools" />

    <view class="footer-note">
      <text>Agent 只生成草稿和待审批动作；写入前由你确认。不做投资建议、不自动转账。</text>
    </view>
  </view>
</template>

<style scoped>
.page { padding: 18rpx 24rpx 80rpx; }
.hero { display: flex; align-items: center; gap: 16rpx; padding: 18rpx 8rpx 24rpx; }
.hero-cat { width: 82rpx; height: 68rpx; }
.hero-text { flex: 1; min-width: 0; }
.hero-title { display: block; font-size: 38rpx; font-weight: 800; color: #5A54B8; letter-spacing: 1rpx; }
.hero-sub { display: block; font-size: 24rpx; color: #8A90A8; margin-top: 4rpx; }
.hero-link { font-size: 24rpx; color: #6C7BF5; flex-shrink: 0; }

.card { background: #FFFDF8; border-radius: 28rpx; padding: 26rpx; margin-bottom: 22rpx;
  box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .08); border: 1rpx solid #F0EDF8; }
.card-head { display: flex; align-items: center; justify-content: space-between; }
.card-title { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; margin-bottom: 16rpx; }
.muted { font-size: 22rpx; color: #A6AAC2; }
.section-title { display: block; font-size: 26rpx; font-weight: 700; color: #5A5F78; margin: 22rpx 0 12rpx; }

.goal-input { width: 100%; min-height: 150rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 20rpx; padding: 22rpx; font-size: 29rpx; box-sizing: border-box; }
.ph { color: #C3C7DA; }
.mode-row { display: flex; gap: 12rpx; margin: 16rpx 0 4rpx; }
.mode-chip { font-size: 24rpx; color: #8A90A8; background: #F6F4FB; border-radius: 999rpx;
  padding: 8rpx 22rpx; }
.mode-active { background: #6C7BF5; color: #fff; font-weight: 700; }
.example-row { display: flex; flex-wrap: wrap; gap: 12rpx; margin: 16rpx 0; }
.example { font-size: 24rpx; color: #6C7BF5; background: #EFF1FF; border-radius: 999rpx;
  padding: 8rpx 18rpx; }
.followup-row { display: flex; flex-wrap: wrap; align-items: center; gap: 10rpx;
  margin: 4rpx 0 8rpx; padding: 12rpx 14rpx; background: #FFFAF0;
  border: 1rpx dashed #F5D9A8; border-radius: 16rpx; }
.followup-label { font-size: 21rpx; color: #A56A1F; }
.thread-item { display: flex; align-items: flex-start; gap: 12rpx; padding: 14rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.thread-item:last-child { border-bottom: none; }
.thread-turn { flex-shrink: 0; font-size: 20rpx; color: #6C7BF5; background: #EFF1FF;
  border-radius: 999rpx; padding: 4rpx 12rpx; }
.thread-main { flex: 1; min-width: 0; }
.thread-goal { display: block; font-size: 24rpx; font-weight: 700; color: #3A3F58;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.thread-answer { display: block; font-size: 21rpx; color: #8A90A8; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.thread-status { flex-shrink: 0; font-size: 19rpx; padding: 4rpx 10rpx; }
.thread-hint { display: block; font-size: 21rpx; color: #A56A1F; line-height: 1.6;
  margin-top: 10rpx; background: #FFFAF0; border-radius: 12rpx; padding: 10rpx 12rpx; }
.status-superseded { background: #F4F2FA; color: #8A90A8; }
.health-entry { display: flex; align-items: center; gap: 14rpx; margin: 8rpx 0 4rpx;
  padding: 18rpx 20rpx; background: linear-gradient(135deg, #F4F0FF 0%, #EFF1FF 100%);
  border: 1rpx dashed #C9C2F2; border-radius: 20rpx; }
.health-entry-main { flex: 1; min-width: 0; }
.health-entry-title { display: block; font-size: 26rpx; font-weight: 800; color: #5A54B8; }
.health-entry-sub { display: block; font-size: 21rpx; color: #8A90A8; margin-top: 4rpx; }
.health-entry-arrow { font-size: 34rpx; color: #A9A2DB; }
.simulator-entry { background: linear-gradient(135deg, #FFF7E9 0%, #FFFDF8 100%);
  border-color: #E8C98F; }
.simulator-entry .health-entry-title { color: #A56A1F; }
.action-row { display: flex; gap: 16rpx; margin-top: 8rpx; }
.btn { flex: 1; margin: 0; height: 82rpx; line-height: 82rpx; border-radius: 22rpx;
  font-size: 28rpx; font-weight: 700; }
.btn.primary { color: #fff; background: linear-gradient(135deg, #7C8BFF 0%, #A78BFA 100%);
  box-shadow: 0 10rpx 22rpx rgba(124, 139, 255, .25); }
.btn.ghost { color: #6C7BF5; background: #F2F1FF; }
.btn.small { flex: 0; padding: 0 28rpx; height: 68rpx; line-height: 68rpx; font-size: 26rpx; }
.btn-off { opacity: .55; }

.state-box { margin-top: 18rpx; background: #FFEDEE; border-radius: 16rpx; padding: 18rpx 20rpx; }
.state-text { font-size: 25rpx; color: #C94F4F; line-height: 1.6; }
.state-actions { display: flex; justify-content: flex-end; gap: 14rpx; margin-top: 12rpx; }

.scan-item { display: flex; align-items: flex-start; gap: 14rpx; padding: 18rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.scan-item:last-child { border-bottom: none; }
.scan-main { flex: 1; min-width: 0; }
.scan-level { display: inline-block; font-size: 21rpx; font-weight: 700; border-radius: 999rpx;
  padding: 4rpx 14rpx; margin-right: 10rpx; background: #EFF1FF; color: #6C7BF5; }
.level-critical { background: #FFEDEE; color: #E45858; }
.level-warn { background: #FFF6E7; color: #D98A32; }
.scan-title { display: block; font-size: 27rpx; font-weight: 700; color: #3A3F58; margin-top: 8rpx; }
.scan-msg { display: block; font-size: 24rpx; color: #8A90A8; line-height: 1.6; margin-top: 4rpx; }
.scan-go { font-size: 24rpx; color: #6C7BF5; flex-shrink: 0; padding-top: 8rpx; }
.scan-side { display: flex; flex-direction: column; align-items: flex-end; gap: 8rpx; flex-shrink: 0; }
.scan-actions { display: flex; gap: 14rpx; }
.scan-action { font-size: 21rpx; color: #A6AAC2; }

.run-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12rpx; }
.status-badge { font-size: 22rpx; font-weight: 700; border-radius: 999rpx; padding: 6rpx 18rpx;
  background: #EFF1FF; color: #6C7BF5; }
.status-completed { background: #E9F8F2; color: #1FA97F; }
.status-awaiting_approval { background: #FFF6E7; color: #D98A32; }
.status-failed, .status-rejected, .status-expired { background: #FFEDEE; color: #E45858; }
.status-undone { background: #F4F2FA; color: #6B7089; }
.run-id { font-size: 22rpx; color: #C3C7DA; }
.answer { display: block; font-size: 29rpx; line-height: 1.8; color: #3A3F58;
  word-break: break-word; }

.evidence-row { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 16rpx; }
.evidence-chip { font-size: 21rpx; color: #6C7BF5; background: #F2F1FF; border-radius: 999rpx;
  padding: 5rpx 14rpx; }

.plan-item { display: flex; align-items: flex-start; gap: 14rpx; padding: 8rpx 0; }
.plan-no { width: 34rpx; height: 34rpx; line-height: 34rpx; text-align: center; flex-shrink: 0;
  font-size: 21rpx; font-weight: 700; color: #6C7BF5; background: #EFF1FF; border-radius: 50%; }
.plan-text { font-size: 26rpx; color: #4A4F6B; line-height: 1.6; }

.trace-item { display: flex; align-items: center; gap: 14rpx; padding: 12rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.trace-item:last-child { border-bottom: none; }
.trace-dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: #1FA97F; flex-shrink: 0; }
.trace-wait { background: #F2A93B; }
.trace-error { background: #E45858; }
.trace-main { flex: 1; min-width: 0; }
.trace-name { display: block; font-size: 25rpx; font-weight: 600; color: #3A3F58; }
.trace-desc { display: block; font-size: 21rpx; color: #A6AAC2; margin-top: 2rpx;
  word-break: break-word; }
.trace-seq { font-size: 21rpx; color: #C3C7DA; }

.approval { margin-top: 22rpx; background: #FFFAF0; border: 2rpx solid #F5D9A8;
  border-radius: 22rpx; padding: 22rpx; }
.approval-head { display: flex; align-items: center; justify-content: space-between; }
.approval-title { display: block; font-size: 27rpx; font-weight: 800; color: #C1823F; }
.approval-expire { font-size: 21rpx; color: #B08A55; }
.approval-summary { display: block; font-size: 26rpx; color: #5A5F78; line-height: 1.7; margin-top: 8rpx; }
.impact { margin-top: 12rpx; background: #FFF3D9; border-radius: 14rpx; padding: 14rpx 16rpx;
  font-size: 24rpx; color: #A56A1F; line-height: 1.6; }
.action-list { margin-top: 14rpx; }
.action-item { display: flex; gap: 12rpx; padding: 8rpx 0; }
.action-label { flex-shrink: 0; font-size: 22rpx; font-weight: 700; color: #6C7BF5;
  background: #EFF1FF; border-radius: 999rpx; padding: 4rpx 12rpx; height: 32rpx; line-height: 32rpx; }
.action-detail { font-size: 24rpx; color: #4A4F6B; line-height: 1.5;
  word-break: break-word; }
.edit-box { margin-top: 14rpx; background: #FFFDF8; border: 1rpx dashed #E8C98F;
  border-radius: 16rpx; padding: 14rpx 16rpx; }
.edit-title { display: block; font-size: 22rpx; color: #B08A55; margin-bottom: 8rpx; }
.edit-row { display: flex; align-items: center; gap: 10rpx; padding: 6rpx 0; }
.edit-label { width: 120rpx; font-size: 23rpx; color: #5A5F78; flex-shrink: 0; }
.edit-input { flex: 1; height: 58rpx; background: #FFF3D9; border-radius: 10rpx;
  padding: 0 14rpx; font-size: 26rpx; color: #3A3F58; }
.edit-unit { font-size: 22rpx; color: #8A90A8; }
.edit-before { font-size: 20rpx; color: #A6AAC2; flex-shrink: 0; }
.memory-row { display: flex; align-items: center; gap: 12rpx; padding: 12rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.memory-row:last-child { border-bottom: none; }
.memory-text { flex: 1; font-size: 24rpx; color: #4A4F6B; word-break: break-word; }
.memory-del { font-size: 32rpx; color: #C3C7DA; padding: 0 10rpx; }
.approval-btns { display: flex; gap: 14rpx; margin-top: 16rpx; }
.approval-hint { display: block; font-size: 21rpx; color: #A6AAC2; margin-top: 12rpx; }
.result-row { display: flex; align-items: center; justify-content: space-between; gap: 12rpx;
  margin-top: 20rpx; padding-top: 18rpx; border-top: 1rpx dashed #F0EDF8; }
.meta { font-size: 21rpx; color: #A6AAC2; }

.recent-item { display: flex; align-items: center; gap: 14rpx; padding: 16rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.recent-item:last-child { border-bottom: none; }
.recent-main { flex: 1; min-width: 0; }
.recent-goal { display: block; font-size: 26rpx; font-weight: 600; color: #3A3F58;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-answer { display: block; font-size: 22rpx; color: #A6AAC2; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.recent-status { font-size: 22rpx; color: #6C7BF5; flex-shrink: 0; }

.footer-note { padding: 8rpx 12rpx; font-size: 21rpx; color: #A6AAC2; line-height: 1.7;
  text-align: center; }
</style>
