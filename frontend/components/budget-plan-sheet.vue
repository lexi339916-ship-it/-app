<script setup>
import { computed, ref, watch } from 'vue'
import { apiApplyPlan, apiSetCategoryBudgetsBatch } from '../api/index.js'
import { categoryMeta } from '../common/category-icons.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  plan: { type: Object, default: null },
})
const emit = defineEmits(['close', 'applied'])

const editAmounts = ref({})
const saveTargetEdit = ref('')
const dirty = ref(false)
const applying = ref(false)

const totalBudget = computed(() => {
  if (!props.plan) return 0
  return props.plan.items.reduce(
    (sum, it) => sum + (Number(editAmounts.value[it.category_id]) || 0), 0)
})

function init() {
  if (!props.plan || !props.plan.items) return
  const map = {}
  for (const it of props.plan.items) map[it.category_id] = String(Number(it.amount))
  editAmounts.value = map
  const save = (Number(props.plan.income_estimate) || 0) - (Number(props.plan.total_budget) || 0)
  saveTargetEdit.value = String(Math.max(0, Math.round(save)))
  dirty.value = false
}

watch(() => [props.visible, props.plan], () => {
  if (props.visible) init()
})

function markDirty() { dirty.value = true }

function onSaveTargetInput(e) {
  saveTargetEdit.value = e.detail.value
  const target = Number(e.detail.value)
  if (!props.plan || isNaN(target) || target < 0) return
  const income = Number(props.plan.income_estimate) || 0
  const newTotal = Math.round(income - target)
  if (newTotal <= 0) return
  const items = props.plan.items
  const oldTotal = items.reduce((s, it) => s + (Number(editAmounts.value[it.category_id]) || 0), 0)
  if (oldTotal <= 0) return
  const next = {}
  let assigned = 0
  for (const it of items) {
    const cur = Number(editAmounts.value[it.category_id]) || 0
    let v = Math.round((cur / oldTotal) * newTotal / 10) * 10
    if (v < 10) v = 10
    next[it.category_id] = v
    assigned += v
  }
  const diff = newTotal - assigned
  if (diff !== 0) {
    const biggest = items.reduce((a, b) => (next[a.category_id] >= next[b.category_id] ? a : b))
    next[biggest.category_id] = Math.max(10, next[biggest.category_id] + diff)
  }
  for (const k in next) editAmounts.value[k] = String(next[k])
  dirty.value = true
}

async function apply() {
  if (!props.plan || applying.value) return
  for (const it of props.plan.items) {
    const v = Number(editAmounts.value[it.category_id])
    if (!v || v <= 0) {
      uni.showToast({ title: `「${it.category}」金额不对哦`, icon: 'none' }); return
    }
  }
  applying.value = true
  try {
    if (dirty.value) {
      await apiSetCategoryBudgetsBatch({
        month: props.plan.month,
        source: 'ai',
        items: props.plan.items.map(it => ({
          category_id: it.category_id,
          month: props.plan.month,
          amount: Number(editAmounts.value[it.category_id]).toFixed(2),
        })),
      })
    } else {
      await apiApplyPlan(props.plan.id)
    }
    uni.showToast({ title: '预算已生效', icon: 'success' })
    emit('applied')
    emit('close')
  } catch (e) { /* 统一提示 */ } finally { applying.value = false }
}
</script>

<template>
  <view v-if="visible && plan" class="mask" @click.self="emit('close')">
    <view class="sheet">
      <view class="sheet-head">
        <text class="sheet-title">{{ String(plan.month).replace('-', ' 年 ') }} 月方案</text>
        <text class="sheet-close" @click="emit('close')">×</text>
      </view>
      <text class="sheet-sub">{{ plan.goal_text ? '按你的存钱目标分配' : '按历史消费习惯推荐' }} · 可修改金额后采纳</text>

      <view class="target-row">
        <text class="target-label">每月储蓄目标</text>
        <input class="target-input" type="digit" v-model="saveTargetEdit"
          @input="onSaveTargetInput" />
        <text class="target-unit">元</text>
      </view>

      <view class="plan-list">
        <view class="plan-row" v-for="it in plan.items" :key="it.category_id">
          <image class="plan-icon" :src="categoryMeta(it.category).img" mode="widthFix" />
          <text class="plan-name">{{ it.category }}</text>
          <input class="plan-input" type="digit" v-model="editAmounts[it.category_id]"
            @input="markDirty" />
          <text class="plan-unit">元</text>
        </view>
      </view>

      <view class="total-row">
        <text>分类预算合计</text>
        <text class="total-num">¥{{ Number(totalBudget).toFixed(0) }}</text>
      </view>

      <view class="sheet-actions">
        <button class="btn ghost" @click="emit('close')">取消</button>
        <button class="btn primary" :class="{ 'btn-off': applying }" :disabled="applying" @click="apply">
          {{ applying ? '写入中…' : '一键采纳' }}
        </button>
      </view>
    </view>
  </view>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(35, 34, 58, .45); z-index: 999;
  display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 82vh; overflow-y: auto; background: #FFFDF8;
  border-radius: 32rpx 32rpx 0 0; padding: 28rpx 28rpx 40rpx; box-sizing: border-box; }
.sheet-head { display: flex; align-items: center; justify-content: space-between; }
.sheet-title { font-size: 32rpx; font-weight: 800; color: #3A3F58; }
.sheet-close { font-size: 40rpx; color: #A6AAC2; padding: 0 8rpx; }
.sheet-sub { display: block; font-size: 22rpx; color: #8A90A8; margin-top: 6rpx; }
.target-row { display: flex; align-items: center; gap: 12rpx; margin: 18rpx 0;
  background: #F4F0FF; border-radius: 16rpx; padding: 14rpx 16rpx; }
.target-label { font-size: 24rpx; color: #5A54B8; font-weight: 700; flex: 1; }
.target-input { width: 180rpx; height: 60rpx; background: #FFF; border-radius: 12rpx;
  padding: 0 12rpx; font-size: 26rpx; text-align: right; }
.target-unit { font-size: 21rpx; color: #8A90A8; }
.plan-list { margin-top: 8rpx; }
.plan-row { display: flex; align-items: center; gap: 12rpx; padding: 12rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.plan-icon { width: 42rpx; height: 42rpx; }
.plan-name { flex: 1; font-size: 25rpx; color: #3A3F58; }
.plan-input { width: 180rpx; height: 60rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 12rpx; padding: 0 12rpx; font-size: 25rpx; text-align: right; }
.plan-unit { font-size: 21rpx; color: #8A90A8; }
.total-row { display: flex; justify-content: space-between; align-items: center;
  margin-top: 18rpx; font-size: 24rpx; color: #5A5F78; }
.total-num { font-size: 30rpx; font-weight: 800; color: #6C7BF5; }
.sheet-actions { display: flex; gap: 14rpx; margin-top: 20rpx; }
.btn { flex: 1; margin: 0; height: 76rpx; line-height: 76rpx; border-radius: 20rpx;
  font-size: 26rpx; font-weight: 700; }
.btn.primary { color: #FFF; background: linear-gradient(135deg, #7C8BFF, #A78BFA); }
.btn.ghost { color: #6C7BF5; background: #F2F1FF; }
.btn-off { opacity: .55; }
</style>
