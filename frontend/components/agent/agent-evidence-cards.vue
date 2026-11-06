<script setup>
import { computed } from 'vue'

const props = defineProps({
  cards: { type: Array, default: () => [] },
})
const list = computed(() => (props.cards || []).filter(c => c && c.type))

function num(value) {
  const n = Number(value || 0)
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function money(value) {
  return '¥' + num(value)
}

function signed(value) {
  const n = Number(value || 0)
  return (n > 0 ? '+' : '') + '¥' + num(n)
}

function pct(value) {
  return Math.round(Number(value || 0) * 100) + '%'
}

function shortDate(value) {
  return value ? String(value).slice(0, 16).replace('T', ' ') : ''
}

const COMPONENT_LABELS = {
  consumption: '消费',
  income: '收入',
  transfer: '转账',
  liability: '负债',
  manual: '手动调整',
}

function componentRows(data) {
  const components = data?.components || {}
  return Object.keys(COMPONENT_LABELS)
    .filter(key => components[key] !== undefined)
    .map(key => ({ key, label: COMPONENT_LABELS[key], value: components[key] }))
}

function goalText(goal) {
  if (!goal) return ''
  if (goal.delay_days > 0) return `「${goal.name}」预计延期 ${goal.delay_days} 天`
  if (goal.extra_days > 0) return `「${goal.name}」完成时间晚约 ${goal.extra_days} 天`
  return `「${goal.name}」进度基本不受影响`
}
</script>

<template>
  <view v-if="list.length" class="evidence-list">
    <view v-for="(card, index) in list" :key="index" class="evidence-card">
      <!-- 资产总览 -->
      <template v-if="card.type === 'asset_overview'">
        <view class="ev-head">
          <text class="ev-title">资产概览</text>
          <text class="ev-date">{{ shortDate(card.data?.as_of) }}</text>
        </view>
        <view class="ev-grid three">
          <view class="ev-cell">
            <text class="ev-label">总资产</text>
            <text class="ev-value">{{ money(card.data?.total_assets) }}</text>
          </view>
          <view class="ev-cell">
            <text class="ev-label">总负债</text>
            <text class="ev-value danger">{{ money(card.data?.total_liabilities) }}</text>
          </view>
          <view class="ev-cell">
            <text class="ev-label">净资产</text>
            <text class="ev-value">{{ money(card.data?.net_worth) }}</text>
          </view>
        </view>
        <view class="ev-split">
          <text>可动用 {{ money(card.data?.liquid_assets) }}</text>
          <text>固定资产 {{ money(card.data?.fixed_assets) }}</text>
        </view>
        <view v-if="card.data?.accounts?.length" class="ev-lines">
          <view class="ev-line" v-for="a in card.data.accounts.slice(0, 3)" :key="a.id">
            <text class="ev-line-name">{{ a.name }}</text>
            <text class="ev-line-value">{{ money(a.balance) }}</text>
          </view>
        </view>
      </template>

      <!-- 净资产变化 -->
      <template v-else-if="card.type === 'net_worth_change'">
        <view class="ev-head">
          <text class="ev-title">净资产变化</text>
          <text class="ev-date">{{ card.data?.month || shortDate(card.data?.as_of) }}</text>
        </view>
        <view class="ev-net">
          <text class="ev-net-label">本月净资产变动</text>
          <text :class="['ev-net-value', Number(card.data?.net_worth_change) < 0 ? 'danger' : 'positive']">
            {{ signed(card.data?.net_worth_change) }}
          </text>
        </view>
        <view class="ev-lines">
          <view class="ev-line" v-for="row in componentRows(card.data)" :key="row.key">
            <text class="ev-line-name">{{ row.label }}</text>
            <text :class="['ev-line-value', Number(row.value) < 0 ? 'danger' : 'positive']">
              {{ signed(row.value) }}
            </text>
          </view>
        </view>
        <view class="ev-foot">
          <text>账单关联覆盖率 {{ pct(card.data?.coverage_ratio) }}</text>
          <text v-if="Number(card.data?.unlinked_expense) > 0">
            未关联支出 {{ money(card.data?.unlinked_expense) }}
          </text>
        </view>
      </template>

      <!-- 购买模拟 -->
      <template v-else-if="card.type === 'simulation'">
        <view class="ev-head">
          <text class="ev-title">购买模拟</text>
          <text class="ev-date">{{ card.data?.category }} · {{ money(card.data?.amount) }}</text>
        </view>
        <view class="ev-lines">
          <view class="ev-line">
            <text class="ev-line-name">分类预算</text>
            <text class="ev-line-value">
              <template v-if="card.data?.purchase?.available">
                {{ money(card.data.purchase.budget_remaining_before) }} →
                {{ money(card.data.purchase.budget_remaining_after) }}
              </template>
              <template v-else>未设置预算</template>
            </text>
          </view>
          <view class="ev-line" v-if="card.data?.goal">
            <text class="ev-line-name">储蓄目标</text>
            <text :class="['ev-line-value', card.data.goal.delay_days > 0 ? 'danger' : '']">
              {{ goalText(card.data.goal) }}
            </text>
          </view>
          <view class="ev-line" v-if="card.data?.asset?.available">
            <text class="ev-line-name">可动用资产</text>
            <text class="ev-line-value">
              {{ money(card.data.asset.liquid_assets_before) }} →
              {{ money(card.data.asset.liquid_assets_after) }}
            </text>
          </view>
          <view class="ev-line" v-if="card.data?.asset?.available">
            <text class="ev-line-name">净资产</text>
            <text class="ev-line-value">
              {{ money(card.data.asset.net_worth_before) }} →
              {{ money(card.data.asset.net_worth_after) }}
            </text>
          </view>
        </view>
        <view v-if="card.data?.asset?.available && !card.data.asset.sufficient" class="ev-warn">
          {{ card.data.asset.message }}
        </view>
        <view v-if="card.data?.recommendations?.length" class="ev-recos">
          <view class="ev-reco" v-for="(r, i) in card.data.recommendations.slice(0, 2)" :key="i">
            <text class="ev-reco-title">{{ r.title }}</text>
            <text class="ev-reco-detail">{{ r.detail }}</text>
          </view>
        </view>
      </template>
    </view>
  </view>
</template>

<style scoped>
.evidence-list { margin-top: 16rpx; display: flex; flex-direction: column; gap: 12rpx; }
.evidence-card { background: #F7F5FF; border: 1rpx solid #E9E6F4; border-radius: 20rpx;
  padding: 18rpx 18rpx 16rpx; }
.ev-head { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.ev-title { font-size: 24rpx; font-weight: 800; color: #5A54B8; }
.ev-date { font-size: 19rpx; color: #A6AAC2; }
.ev-grid { display: flex; gap: 10rpx; margin-top: 14rpx; }
.ev-grid.three .ev-cell { flex: 1; min-width: 0; }
.ev-cell { background: rgba(255, 253, 248, .9); border-radius: 14rpx; padding: 12rpx 10rpx; }
.ev-label { display: block; font-size: 19rpx; color: #9AA0B8; }
.ev-value { display: block; font-size: 24rpx; font-weight: 800; color: #3A3F58; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ev-value.danger { color: #E45858; }
.ev-split { display: flex; justify-content: space-between; gap: 12rpx; margin-top: 10rpx;
  font-size: 19rpx; color: #8A90A8; }
.ev-lines { margin-top: 10rpx; }
.ev-line { display: flex; align-items: flex-start; justify-content: space-between; gap: 12rpx;
  padding: 8rpx 0; border-bottom: 1rpx dashed #EAE6F5; }
.ev-line:last-child { border-bottom: none; }
.ev-line-name { font-size: 21rpx; color: #8A90A8; flex-shrink: 0; }
.ev-line-value { font-size: 21rpx; color: #4A4F6B; text-align: right; line-height: 1.5;
  word-break: break-word; }
.ev-line-value.positive { color: #1FA97F; }
.ev-line-value.danger { color: #E45858; }
.ev-net { display: flex; align-items: baseline; justify-content: space-between; gap: 12rpx;
  margin-top: 14rpx; }
.ev-net-label { font-size: 21rpx; color: #8A90A8; }
.ev-net-value { font-size: 30rpx; font-weight: 800; }
.ev-net-value.positive { color: #1FA97F; }
.ev-net-value.danger { color: #E45858; }
.ev-foot { display: flex; justify-content: space-between; gap: 10rpx; margin-top: 10rpx;
  font-size: 18rpx; color: #A6AAC2; }
.ev-warn { margin-top: 10rpx; background: #FFF6E7; color: #A56A1F; border-radius: 12rpx;
  padding: 10rpx 12rpx; font-size: 20rpx; line-height: 1.6; }
.ev-recos { margin-top: 12rpx; display: flex; flex-direction: column; gap: 8rpx; }
.ev-reco { background: rgba(255, 253, 248, .85); border-radius: 12rpx; padding: 10rpx 12rpx; }
.ev-reco-title { display: block; font-size: 21rpx; font-weight: 700; color: #5A5F78; }
.ev-reco-detail { display: block; font-size: 19rpx; color: #8A90A8; line-height: 1.6; margin-top: 3rpx; }
</style>
