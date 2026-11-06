<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  approval: { type: Object, required: true },
  deciding: { type: Boolean, default: false },
})
const emit = defineEmits(['decide'])

const editBillAmount = ref('')
const originalBillAmount = ref('')
const editBudgets = ref({})
const originalBudgets = ref({})

function billAction(approval) {
  return (approval?.diff?.actions || []).find(a => a.action === 'create_bill')
}

function budgetItems(approval) {
  return (approval?.diff?.actions || [])
    .filter(a => a.action === 'set_category_budgets')
    .flatMap(a => a.items || [])
}

function init() {
  const bill = billAction(props.approval)
  editBillAmount.value = bill ? bill.bill.amount : ''
  originalBillAmount.value = bill ? bill.bill.amount : ''
  const items = budgetItems(props.approval)
  const edit = {}
  const originals = {}
  for (const item of items) {
    edit[item.category_id] = item.amount
    originals[item.category_id] = item.amount
  }
  editBudgets.value = edit
  originalBudgets.value = originals
}

watch(() => props.approval, init, { immediate: true, deep: true })

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
  if (action.action === 'create_task') return action.note?.title || ''
  if (action.action === 'pause_subscription') return action.subscription_name || ''
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

function approve() {
  const edits = {}
  if (editBillAmount.value !== '' &&
      String(editBillAmount.value) !== String(originalBillAmount.value)) {
    edits.bill_amount = editBillAmount.value
  }
  const changed = {}
  for (const key of Object.keys(editBudgets.value)) {
    if (String(editBudgets.value[key]) !== String(originalBudgets.value[key])) {
      changed[key] = editBudgets.value[key]
    }
  }
  if (Object.keys(changed).length) edits.budgets = changed
  emit('decide', props.approval, 'approved', edits)
}

function reject() {
  emit('decide', props.approval, 'rejected', {})
}

function budgetItemsList() {
  return budgetItems(props.approval)
}
</script>

<template>
  <view class="approval-card">
    <view class="approval-head">
      <text class="approval-title">等待你确认</text>
      <text class="approval-expire" v-if="approval.expires_at">
        有效至 {{ String(approval.expires_at).replace('T', ' ').slice(11, 16) }}
      </text>
    </view>
    <text class="approval-summary">{{ approval.diff?.summary }}</text>

    <view class="impact" v-if="impactText(approval)">
      <text>{{ impactText(approval) }}</text>
    </view>

    <view class="action-list">
      <view class="action-item" v-for="(act, i) in (approval.diff?.actions || [])" :key="i">
        <text class="action-label">{{ actionLabel(act.action) }}</text>
        <text class="action-detail">{{ actionDetail(act) }}</text>
      </view>
    </view>

    <view class="edit-box" v-if="billAction(approval) || budgetItemsList().length">
      <text class="edit-title">确认前可直接修改</text>
      <view class="edit-row" v-if="billAction(approval)">
        <text class="edit-label">账单金额</text>
        <input class="edit-input" type="digit" v-model="editBillAmount" />
        <text class="edit-unit">元</text>
      </view>
      <view class="edit-row" v-for="item in budgetItemsList()" :key="'b' + item.category_id">
        <text class="edit-label">{{ item.category_name || item.category_id }}</text>
        <input class="edit-input" type="digit" v-model="editBudgets[item.category_id]" />
        <text class="edit-unit">元</text>
        <text class="edit-before" v-if="item.before">原 ¥{{ item.before }}</text>
      </view>
    </view>

    <view class="approval-btns">
      <button class="approve-btn" :disabled="deciding" @click="approve">
        {{ deciding ? '处理中…' : '确认执行' }}
      </button>
      <button class="reject-btn" :disabled="deciding" @click="reject">暂不执行</button>
    </view>
    <text class="approval-hint">批准后才会写入账单/预算/任务；执行后可撤销。</text>
  </view>
</template>

<style scoped>
.approval-card { margin-top: 16rpx; background: #FFFAF0; border: 2rpx solid #F5D9A8;
  border-radius: 20rpx; padding: 18rpx; }
.approval-head { display: flex; align-items: center; justify-content: space-between; gap: 10rpx; }
.approval-title { font-size: 25rpx; font-weight: 800; color: #C1823F; }
.approval-expire { font-size: 19rpx; color: #B08A55; }
.approval-summary { display: block; font-size: 23rpx; color: #5A5F78; line-height: 1.7; margin-top: 8rpx;
  word-break: break-word; }
.impact { margin-top: 10rpx; background: #FFF3D9; border-radius: 12rpx; padding: 10rpx 12rpx;
  font-size: 21rpx; color: #A56A1F; line-height: 1.6; }
.action-list { margin-top: 10rpx; }
.action-item { display: flex; gap: 10rpx; padding: 5rpx 0; align-items: flex-start; }
.action-label { flex-shrink: 0; font-size: 19rpx; font-weight: 700; color: #6C7BF5;
  background: #EFF1FF; border-radius: 999rpx; padding: 3rpx 10rpx; }
.action-detail { font-size: 21rpx; color: #4A4F6B; line-height: 1.5; word-break: break-word; }
.edit-box { margin-top: 12rpx; background: #FFFDF8; border: 1rpx dashed #E8C98F;
  border-radius: 14rpx; padding: 10rpx 12rpx; }
.edit-title { display: block; font-size: 19rpx; color: #B08A55; margin-bottom: 6rpx; }
.edit-row { display: flex; align-items: center; gap: 8rpx; padding: 5rpx 0; }
.edit-label { width: 110rpx; font-size: 20rpx; color: #5A5F78; flex-shrink: 0; }
.edit-input { flex: 1; height: 52rpx; background: #FFF3D9; border-radius: 9rpx;
  padding: 0 10rpx; font-size: 23rpx; color: #3A3F58; }
.edit-unit { font-size: 19rpx; color: #8A90A8; }
.edit-before { font-size: 18rpx; color: #A6AAC2; flex-shrink: 0; }
.approval-btns { display: flex; gap: 10rpx; margin-top: 14rpx; }
.approve-btn, .reject-btn { flex: 1; height: 64rpx; line-height: 64rpx; border-radius: 14rpx;
  font-size: 24rpx; font-weight: 700; margin: 0; }
.approve-btn { background: linear-gradient(135deg, #7C8BFF, #A78BFA); color: #fff; }
.reject-btn { background: #FFFDF8; color: #8A90A8; border: 1rpx solid #E9E6F4; }
.approve-btn:disabled, .reject-btn:disabled { opacity: .55; }
.approval-hint { display: block; font-size: 18rpx; color: #A6AAC2; margin-top: 9rpx; line-height: 1.5; }
</style>
