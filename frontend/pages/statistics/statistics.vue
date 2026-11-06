<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { apiMonthlyStats, apiCategoryStats, apiChannelStats } from '../../api/index.js'
import { categoryMeta, channelMeta } from '../../common/category-icons.js'

const month = ref('')
const stats = ref(null)
const catStats = ref([])
const catTotal = ref('0')
const channelStats = ref([])
const channelTotal = ref('0')
const statType = ref('expense')
const loading = ref(false)

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function shiftMonth(m, delta) {
  const [y, mo] = m.split('-').map(Number)
  const d = new Date(y, mo - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

async function load() {
  loading.value = true
  try {
    const [s, c, ch] = await Promise.all([
      apiMonthlyStats(month.value),
      apiCategoryStats(month.value, statType.value),
      apiChannelStats(month.value, 'expense').catch(() => null),
    ])
    stats.value = s
    catStats.value = c.items
    catTotal.value = c.total
    channelStats.value = ch ? ch.items : []
    channelTotal.value = ch ? ch.total : 0
  } catch (e) { /* 统一提示 */ } finally { loading.value = false }
}

function prevMonth() { month.value = shiftMonth(month.value, -1); load() }
function nextMonth() { month.value = shiftMonth(month.value, 1); load() }
function switchType(t) { statType.value = t; load() }

// 按日支出柱状图（纯 CSS 实现，无第三方图表依赖）
const dayBars = computed(() => {
  if (!stats.value) return []
  const days = stats.value.days
  const max = Math.max(...days.map(d => Number(d.expense)), 1)
  return days.map(d => ({
    label: String(d.date).slice(8, 10),
    height: Math.round((Number(d.expense) / max) * 100),
    has: Number(d.expense) > 0,
  }))
})

// 环形占比图（conic-gradient，按分类配色）
const donutStyle = computed(() => {
  if (!catStats.value.length) return 'conic-gradient(#EFEDF7 0% 100%)'
  let acc = 0
  const stops = catStats.value.map(c => {
    const start = acc
    acc += c.ratio * 100
    return `${categoryMeta(c.category).color} ${start.toFixed(1)}% ${Math.min(acc, 100).toFixed(1)}%`
  })
  return `conic-gradient(${stops.join(', ')})`
})

// 支付渠道环形图
const channelDonutStyle = computed(() => {
  if (!channelStats.value.length) return 'conic-gradient(#EFEDF7 0% 100%)'
  let acc = 0
  const stops = channelStats.value.map(c => {
    const start = acc
    acc += c.ratio * 100
    return `${channelMeta(c.channel).color} ${start.toFixed(1)}% ${Math.min(acc, 100).toFixed(1)}%`
  })
  return `conic-gradient(${stops.join(', ')})`
})

onShow(() => {
  if (!month.value) month.value = currentMonth()
  load()
})
</script>

<template>
  <view class="page">
    <view class="month-nav">
      <text class="arrow" @click="prevMonth">‹</text>
      <text class="month">{{ month }} 收支统计</text>
      <text class="arrow" @click="nextMonth">›</text>
    </view>

    <!-- 汇总卡片 -->
    <view class="sum-grid" v-if="stats">
      <view class="sum-card c-green">
        <text class="sum-num">¥{{ Number(stats.income).toFixed(2) }}</text>
        <text class="sum-label">收入</text>
      </view>
      <view class="sum-card c-blue">
        <text class="sum-num">¥{{ Number(stats.expense).toFixed(2) }}</text>
        <text class="sum-label">支出</text>
      </view>
      <view class="sum-card c-orange">
        <text class="sum-num">¥{{ Number(stats.net).toFixed(2) }}</text>
        <text class="sum-label">结余</text>
      </view>
    </view>

    <!-- 每日支出柱状图 -->
    <view class="card">
      <text class="block-title">每日支出分布</text>
      <view class="chart">
        <view class="col" v-for="(d, i) in dayBars" :key="i">
          <view class="col-bar" :class="{ 'col-has': d.has }" :style="{ height: d.height + '%' }" />
          <text class="col-label" v-if="i % 2 === 0">{{ d.label }}</text>
          <text class="col-label" v-else> </text>
        </view>
      </view>
    </view>

    <!-- 分类占比 -->
    <view class="card">
      <view class="row-between">
        <text class="block-title">分类占比</text>
        <view class="mini-tabs">
          <text :class="['mini-tab', statType === 'expense' && 'mini-active']" @click="switchType('expense')">支出</text>
          <text :class="['mini-tab', statType === 'income' && 'mini-active']" @click="switchType('income')">收入</text>
        </view>
      </view>
      <view v-if="!catStats.length" class="empty">本月暂无{{ statType === 'expense' ? '支出' : '收入' }}数据</view>
      <block v-else>
        <view class="donut-wrap">
          <view class="donut" :style="{ background: donutStyle }">
            <view class="donut-hole">
              <text class="donut-label">{{ statType === 'expense' ? '总支出' : '总收入' }}</text>
              <text class="donut-total">¥{{ Number(catTotal).toFixed(2) }}</text>
            </view>
          </view>
        </view>
        <view class="cat-row" v-for="c in catStats" :key="c.category">
          <view class="cat-line">
            <view class="cat-left">
              <image class="cat-emoji-img" :src="categoryMeta(c.category).img" mode="widthFix" />
              <text class="cat-name">{{ c.category }}</text>
              <text class="cat-pct">{{ Math.round(c.ratio * 100) }}%</text>
            </view>
            <text class="cat-amount">¥{{ Number(c.amount).toFixed(2) }}</text>
          </view>
          <view class="bar-track small">
            <view class="bar-fill"
              :style="{ width: (c.ratio * 100) + '%', background: categoryMeta(c.category).color }" />
          </view>
        </view>
      </block>
    </view>
    <!-- 支付渠道 -->
    <view class="card">
      <view class="row-between">
        <text class="block-title">支付渠道（支出）</text>
        <text class="muted">本月按平台统计</text>
      </view>
      <view v-if="!channelStats.length" class="empty">暂无渠道数据，记账时可选择支付渠道</view>
      <block v-else>
        <view class="donut-wrap">
          <view class="donut" :style="{ background: channelDonutStyle }">
            <view class="donut-hole">
              <text class="donut-label">总支出</text>
              <text class="donut-total">¥{{ Number(channelTotal).toFixed(2) }}</text>
            </view>
          </view>
        </view>
        <view class="cat-row" v-for="c in channelStats" :key="c.channel">
          <view class="cat-line">
            <view class="cat-left">
              <view class="ch-dot" :style="{ background: channelMeta(c.channel).color }" />
              <text class="cat-name">{{ c.channel }}</text>
              <text class="cat-pct">{{ Math.round(c.ratio * 100) }}% · {{ c.count }} 笔</text>
            </view>
            <text class="cat-amount">¥{{ Number(c.amount).toFixed(2) }}</text>
          </view>
          <view class="bar-track small">
            <view class="bar-fill"
              :style="{ width: (c.ratio * 100) + '%', background: channelMeta(c.channel).color }" />
          </view>
        </view>
      </block>
    </view>
  </view>
</template>

<style scoped>
.page { padding-bottom: 60rpx; }
.month-nav { display: flex; align-items: center; justify-content: center; gap: 24rpx; padding: 24rpx 0 8rpx; }
.arrow { font-size: 46rpx; color: #8A90A8; padding: 0 20rpx; }
.month { font-size: 32rpx; font-weight: 700; }

.sum-grid { display: flex; gap: 18rpx; margin: 16rpx 24rpx 0; }
.sum-card { flex: 1; border-radius: 24rpx; padding: 28rpx 0; text-align: center; color: #fff; }
.c-green { background: linear-gradient(135deg, #6BD3B2, #3FB894); }
.c-blue { background: linear-gradient(135deg, #8B97FF, #6C7BF5); }
.c-orange { background: linear-gradient(135deg, #FFC96B, #F2A93B); }
.sum-num { display: block; font-size: 34rpx; font-weight: 800; }
.sum-label { display: block; font-size: 25rpx; opacity: .9; margin-top: 8rpx; }

.row-between { display: flex; justify-content: space-between; align-items: center; }
.block-title { font-size: 30rpx; font-weight: 700; }
.muted { font-size: 26rpx; color: #8A90A8; }
.bar-track { height: 16rpx; background: #EFEDF7; border-radius: 8rpx; margin-top: 20rpx; overflow: hidden; }
.bar-track.small { height: 12rpx; margin-top: 12rpx; }
.bar-fill { height: 100%; background: #6C7BF5; border-radius: 8rpx; }

.chart { display: flex; align-items: flex-end; height: 260rpx; margin-top: 24rpx; gap: 4rpx; }
.col { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; height: 100%; }
.col-bar { width: 70%; background: #E9E6F4; border-radius: 6rpx 6rpx 0 0; min-height: 4rpx; }
.col-has { background: linear-gradient(180deg, #9DA9FF, #6C7BF5); }
.col-label { font-size: 20rpx; color: #A6AAC2; margin-top: 8rpx; }

.mini-tabs { display: flex; gap: 12rpx; }
.mini-tab { font-size: 26rpx; color: #8A90A8; background: #F6F4FB; border-radius: 26rpx; padding: 6rpx 22rpx; }
.mini-active { background: #6C7BF5; color: #fff; font-weight: 600; }

.cat-row { margin-top: 26rpx; }
.cat-line { display: flex; justify-content: space-between; align-items: center; }
.cat-left { display: flex; align-items: center; gap: 12rpx; }
.cat-emoji-img { width: 42rpx; height: 42rpx; }
.cat-name { font-size: 28rpx; font-weight: 600; }
.cat-pct { font-size: 25rpx; color: #8A90A8; background: #F6F4FB; border-radius: 10rpx;
  padding: 2rpx 12rpx; }
.cat-amount { font-size: 26rpx; color: #5A5F78; }

/* 环形占比图 */
.donut-wrap { display: flex; justify-content: center; padding: 30rpx 0 10rpx; }
.donut { width: 320rpx; height: 320rpx; border-radius: 50%; background: #EFEDF7;
  display: flex; align-items: center; justify-content: center; }
.donut-hole { width: 220rpx; height: 220rpx; border-radius: 50%; background: #FFFDF8;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  box-shadow: inset 0 0 0 2rpx #F1EFF9; }
.donut-label { font-size: 26rpx; color: #A6AAC2; }
.donut-total { font-size: 34rpx; font-weight: 800; color: #3A3F58; margin-top: 8rpx; }
.ch-dot { width: 20rpx; height: 20rpx; border-radius: 10rpx; }
</style>
