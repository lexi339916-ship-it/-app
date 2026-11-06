<script setup>
import { computed, ref, watch } from 'vue'
import AgentEvidenceCards from './agent-evidence-cards.vue'
import ApprovalCard from './approval-card.vue'

const props = defineProps({
  run: { type: Object, required: true },
  deciding: { type: Boolean, default: false },
})
const emit = defineEmits(['decide', 'undo', 'retry'])

const planOpen = ref(false)
const traceOpen = ref(false)

const STATUS = {
  running: '处理中',
  awaiting_approval: '待确认',
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
  (props.run.approvals || []).filter(a => a.status === 'pending'))
const hasUndo = computed(() =>
  props.run.status === 'completed'
  && (props.run.approvals || []).some(a => a.status === 'approved'))
const verified = computed(() => {
  for (const a of props.run.approvals || []) {
    const verify = a.diff?.verify
    if (verify && verify.all_ok) return true
  }
  return false
})
const chips = computed(() => {
  const ev = props.run.evidence || {}
  const out = []
  if (ev.source) out.push('数据：' + ev.source)
  if (ev.as_of) out.push('截至 ' + String(ev.as_of).replace('T', ' ').slice(0, 16))
  if (ev.model) out.push('模型：' + ev.model)
  return out
})
const showExecution = computed(() => {
  const steps = props.run.steps || []
  return steps.length > 3 || (props.run.approvals || []).length > 0
    || steps.some(s => ['approval', 'execute', 'verify'].includes(s.step_type))
})

watch(() => props.run.status, (status) => {
  if (status === 'awaiting_approval') traceOpen.value = true
}, { immediate: true })

function statusLabel(status) {
  return STATUS[status] || status || '处理中'
}

function toolLabel(tool) {
  return TOOL_LABELS[tool] || tool || '步骤'
}

function stepTypeLabel(type) {
  return { plan: '计划', tool: '工具', approval: '审批', execute: '执行',
    verify: '校验', policy: '安全', clarify: '澄清', error: '错误' }[type] || type
}

function formatTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 16) : ''
}

function togglePlan() { planOpen.value = !planOpen.value }
function toggleTrace() { traceOpen.value = !traceOpen.value }
</script>

<template>
  <view class="run-block">
    <!-- 用户消息 -->
    <view class="user-line">
      <view class="user-bubble">{{ run.goal }}</view>
    </view>

    <!-- AI 消息 -->
    <view class="ai-line">
      <image class="ai-avatar" src="/static/doodles/cat.png" mode="widthFix" />
      <view class="ai-main">
        <view class="ai-meta">
          <text class="ai-name">知账 AI</text>
          <text :class="['status-badge', 'status-' + run.status]">{{ statusLabel(run.status) }}</text>
          <text class="ai-time">{{ formatTime(run.created_at) }}</text>
        </view>

        <view :class="['ai-bubble', run.status === 'failed' && 'bubble-error']">
          <text class="answer">{{ run.answer || (run.status === 'running' ? '正在查询真实数据…' : '') }}</text>

          <AgentEvidenceCards :cards="run.evidence?.cards || []" />

          <view v-if="chips.length" class="evidence-row">
            <text class="evidence-chip" v-for="c in chips" :key="c">{{ c }}</text>
          </view>

          <view v-if="showExecution && run.plan && run.plan.length" class="plan-wrap">
            <view class="plan-head" @click="togglePlan">
              <text class="mini-title">执行计划</text>
              <text class="mini-action">{{ planOpen ? '收起' : '展开' }}</text>
            </view>
            <view v-if="planOpen" class="plan-list">
              <view class="plan-item" v-for="(p, i) in run.plan" :key="i">
                <text class="plan-no">{{ i + 1 }}</text>
                <text class="plan-text">{{ p }}</text>
              </view>
            </view>
          </view>

          <view v-if="showExecution && run.steps && run.steps.length" class="trace-wrap">
            <view class="trace-head" @click="toggleTrace">
              <text class="mini-title">执行过程 · {{ run.steps.length }} 步</text>
              <text class="mini-action">{{ traceOpen ? '收起' : '展开' }}</text>
            </view>
            <view v-if="traceOpen" class="trace-list">
              <view class="trace-item" v-for="s in run.steps" :key="s.seq">
                <text :class="['trace-dot', s.status === 'error' ? 'dot-error' : (s.status === 'wait' ? 'dot-wait' : 'dot-ok')]" />
                <view class="trace-main">
                  <text class="trace-name">{{ toolLabel(s.tool_name) }}</text>
                  <text class="trace-desc">{{ stepTypeLabel(s.step_type) }} · {{ s.status === 'error' ? (s.error || '失败') : (s.status === 'wait' ? '等待中' : '完成') }}</text>
                </view>
                <text class="trace-seq">{{ s.seq }}</text>
              </view>
            </view>
          </view>

          <ApprovalCard v-for="a in pendingApprovals" :key="a.id"
            :approval="a" :deciding="deciding"
            @decide="(approval, decision, edits) => emit('decide', approval, decision, edits)" />

          <view v-if="run.status === 'completed' && hasUndo" class="result-row">
            <text class="verify-text">{{ verified ? '已执行并校验通过' : '已执行' }}</text>
            <text class="undo-link" @click="emit('undo', run)">撤销这次执行</text>
          </view>

          <view v-if="run.status === 'completed' && !hasUndo && (run.approvals || []).length" class="result-row">
            <text class="verify-text">{{ verified ? '已执行并校验通过' : '已处理' }}</text>
          </view>

          <view v-if="run.status === 'failed'" class="run-error">
            <text class="run-error-text">{{ run.answer || '处理失败，请重试' }}</text>
            <text class="retry-link" @click="emit('retry', run)">重试</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.run-block { margin-bottom: 24rpx; }
.user-line { display: flex; justify-content: flex-end; padding: 8rpx 0 14rpx; }
.user-bubble { max-width: 78%; background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  color: #fff; font-size: 27rpx; line-height: 1.6; padding: 16rpx 20rpx;
  border-radius: 22rpx 22rpx 6rpx 22rpx; box-shadow: 0 8rpx 18rpx rgba(124, 139, 255, .18);
  word-break: break-word; }
.ai-line { display: flex; align-items: flex-start; gap: 12rpx; }
.ai-avatar { width: 62rpx; height: 54rpx; flex-shrink: 0; margin-top: 4rpx; }
.ai-main { flex: 1; min-width: 0; }
.ai-meta { display: flex; align-items: center; gap: 8rpx; padding: 0 4rpx 8rpx; }
.ai-name { font-size: 22rpx; font-weight: 700; color: #5A54B8; }
.ai-time { font-size: 18rpx; color: #B0B4C8; margin-left: auto; }
.status-badge { font-size: 18rpx; font-weight: 700; border-radius: 999rpx; padding: 3rpx 10rpx;
  background: #EFF1FF; color: #6C7BF5; }
.status-completed { background: #E9F8F2; color: #1FA97F; }
.status-awaiting_approval { background: #FFF6E7; color: #D98A32; }
.status-failed, .status-rejected, .status-expired { background: #FFEDEE; color: #E45858; }
.status-undone { background: #F4F2FA; color: #6B7089; }
.status-superseded { background: #F4F2FA; color: #8A90A8; }
.ai-bubble { background: #FFFDF8; border: 1rpx solid #F0EDF8; border-radius: 6rpx 22rpx 22rpx 22rpx;
  padding: 18rpx 18rpx 16rpx; box-shadow: 0 8rpx 22rpx rgba(124, 139, 255, .07); }
.bubble-error { border-color: #F7C7C7; background: #FFF9F9; }
.answer { display: block; font-size: 27rpx; line-height: 1.75; color: #3A3F58;
  white-space: pre-wrap; word-break: break-word; }
.evidence-row { display: flex; flex-wrap: wrap; gap: 8rpx; margin-top: 12rpx; }
.evidence-chip { font-size: 18rpx; color: #6C7BF5; background: #F2F1FF; border-radius: 999rpx;
  padding: 4rpx 10rpx; }
.plan-wrap, .trace-wrap { margin-top: 14rpx; border-top: 1rpx dashed #F0EDF8; padding-top: 12rpx; }
.plan-head, .trace-head { display: flex; align-items: center; justify-content: space-between; }
.mini-title { font-size: 21rpx; font-weight: 700; color: #5A5F78; }
.mini-action { font-size: 19rpx; color: #6C7BF5; }
.plan-item { display: flex; align-items: flex-start; gap: 10rpx; padding: 6rpx 0; }
.plan-no { width: 30rpx; height: 30rpx; line-height: 30rpx; text-align: center; flex-shrink: 0;
  font-size: 18rpx; font-weight: 700; color: #6C7BF5; background: #EFF1FF; border-radius: 50%; }
.plan-text { font-size: 22rpx; color: #4A4F6B; line-height: 1.55; }
.trace-item { display: flex; align-items: center; gap: 10rpx; padding: 8rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.trace-item:last-child { border-bottom: none; }
.trace-dot { width: 12rpx; height: 12rpx; border-radius: 50%; flex-shrink: 0; }
.dot-ok { background: #1FA97F; }
.dot-wait { background: #F2A93B; }
.dot-error { background: #E45858; }
.trace-main { flex: 1; min-width: 0; }
.trace-name { display: block; font-size: 21rpx; font-weight: 600; color: #3A3F58; }
.trace-desc { display: block; font-size: 18rpx; color: #A6AAC2; margin-top: 2rpx;
  word-break: break-word; }
.trace-seq { font-size: 18rpx; color: #C3C7DA; }
.result-row { display: flex; align-items: center; justify-content: space-between; gap: 10rpx;
  margin-top: 14rpx; padding-top: 12rpx; border-top: 1rpx dashed #F0EDF8; }
.verify-text { font-size: 20rpx; color: #1FA97F; }
.undo-link { font-size: 20rpx; color: #8A90A8; }
.run-error { display: flex; align-items: center; justify-content: space-between; gap: 12rpx;
  margin-top: 12rpx; background: #FFEDEE; border-radius: 12rpx; padding: 10rpx 12rpx; }
.run-error-text { flex: 1; font-size: 21rpx; color: #C94F4F; line-height: 1.5; }
.retry-link { font-size: 21rpx; color: #6C7BF5; flex-shrink: 0; }
</style>
