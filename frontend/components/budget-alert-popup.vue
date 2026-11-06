<script setup>
/**
 * 预算预警弹窗（全局复用组件）
 *
 * 使用场景：
 * 1. 记账保存成功后，/api/budget-center/check 返回的预警逐条弹出；
 * 2. 弹窗文案由后端生成（AI 柔和文案或模板降级），本组件只负责展示；
 * 3. 多条预警排队展示，点「知道啦」看下一条，全部看完触发 close 事件。
 */
import { ref, computed, watch } from 'vue'

const props = defineProps({
  // 预警列表（AlertOut 数组），由父页面传入
  alerts: { type: Array, default: () => [] },
})
const emit = defineEmits(['close'])

// 待展示队列：传入新列表时重置
const queue = ref([])
watch(() => props.alerts, (list) => {
  if (list && list.length) queue.value = [...list]
}, { immediate: true })

// 当前正在展示的预警
const current = computed(() => queue.value[0] || null)

// 等级视觉：info 蓝紫 / warn 暖橙 / critical 柔红
const LEVEL_META = {
  info: { label: '小提醒', cls: 'lv-info' },
  warn: { label: '预算预警', cls: 'lv-warn' },
  critical: { label: '超支提醒', cls: 'lv-critical' },
}
const levelMeta = computed(() => LEVEL_META[current.value?.level] || LEVEL_META.info)

// 80% 提醒：展示已花 / 剩余；超支：展示已花 / 超出；异常大额：展示这笔 / 历史均值
const numbers = computed(() => {
  const a = current.value
  if (!a) return []
  const p = a.payload || {}
  const fmt = (v) => Number(v || 0).toFixed(2)
  if (a.alert_type === 'budget_80') {
    return [
      { label: '本月已花', value: `¥${fmt(p.spent)}` },
      { label: '剩余额度', value: `¥${fmt(p.remaining)}` },
    ]
  }
  if (a.alert_type === 'budget_100') {
    return [
      { label: '本月已花', value: `¥${fmt(p.spent)}` },
      { label: '超出预算', value: `¥${fmt(p.over)}` },
    ]
  }
  if (a.alert_type === 'anomaly') {
    return [
      { label: '这笔支出', value: `¥${fmt(p.amount)}` },
      { label: `${p.category || '该分类'}以往单笔均值`, value: `¥${fmt(p.avg)}` },
    ]
  }
  if (a.alert_type === 'rebalance') {
    return [{ label: '建议调配', value: `¥${fmt(p.amount)}` }]
  }
  return []
})

/** 关闭当前这条，展示下一条；队列清空后通知父页面 */
function ack() {
  queue.value.shift()
  if (!queue.value.length) emit('close')
}

/** 弹性调度类预警：跳转到消息中心处理（采纳/忽略） */
function goAlerts() {
  queue.value = []
  emit('close')
  uni.navigateTo({ url: '/pages/notifications/notifications' })
}
</script>

<template>
  <view v-if="current" class="popup-mask">
    <view class="popup-card">
      <!-- 顶部等级标签 -->
      <view class="badge-row">
        <text :class="['level-badge', levelMeta.cls]">{{ levelMeta.label }}</text>
        <text v-if="queue.length > 1" class="queue-hint">{{ queue.length }} 条提醒</text>
      </view>

      <text class="popup-title">{{ current.title }}</text>
      <text class="popup-message">{{ current.message }}</text>

      <!-- 关键数字（已花/剩余/均值等） -->
      <view v-if="numbers.length" class="num-row">
        <view v-for="n in numbers" :key="n.label" class="num-item">
          <text class="num-value">{{ n.value }}</text>
          <text class="num-label">{{ n.label }}</text>
        </view>
      </view>

      <!-- 柔和建议 -->
      <view v-if="current.suggestion" class="tip-box">
        <text class="tip-text">{{ current.suggestion }}</text>
      </view>

      <view class="btn-row">
        <button v-if="current.alert_type === 'rebalance'" class="btn btn-outline half" @click="goAlerts">去调配</button>
        <button :class="['btn btn-primary', current.alert_type === 'rebalance' ? 'half' : '']" @click="ack">知道啦</button>
      </view>
    </view>
  </view>
</template>

<style scoped>
/* 遮罩层 */
.popup-mask {
  position: fixed;
  inset: 0;
  background: rgba(58, 63, 88, 0.38);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
  padding: 48rpx;
  box-sizing: border-box;
}

/* 手账风卡片 */
.popup-card {
  width: 100%;
  background: #FFFDF8;
  border-radius: 34rpx;
  padding: 40rpx 36rpx 36rpx;
  box-shadow: 0 18rpx 48rpx rgba(124, 139, 255, 0.22);
  border: 1rpx solid rgba(255, 255, 255, 0.95);
  box-sizing: border-box;
}

.badge-row { display: flex; justify-content: space-between; align-items: center; }
.level-badge {
  font-size: 24rpx;
  font-weight: 700;
  padding: 6rpx 20rpx;
  border-radius: 999rpx;
  letter-spacing: 1rpx;
}
.lv-info { background: #EFF1FF; color: #6C7BF5; }
.lv-warn { background: #FFF3E0; color: #F5A623; }
.lv-critical { background: #FFEDEE; color: #F27E7E; }
.queue-hint { font-size: 24rpx; color: #A6AAC2; }

.popup-title {
  display: block;
  font-size: 36rpx;
  font-weight: 800;
  color: #3A3F58;
  margin-top: 24rpx;
  letter-spacing: 1rpx;
}
.popup-message {
  display: block;
  font-size: 28rpx;
  color: #5A5F78;
  line-height: 1.8;
  margin-top: 16rpx;
}

/* 关键数字 */
.num-row {
  display: flex;
  gap: 18rpx;
  margin-top: 26rpx;
}
.num-item {
  flex: 1;
  background: #FAF9FF;
  border: 1rpx solid #E9E6F4;
  border-radius: 22rpx;
  padding: 20rpx 12rpx;
  text-align: center;
}
.num-value { display: block; font-size: 34rpx; font-weight: 800; color: #6C7BF5; }
.num-label { display: block; font-size: 24rpx; color: #A6AAC2; margin-top: 6rpx; }

/* 建议气泡 */
.tip-box {
  margin-top: 22rpx;
  background: #F2FBF7;
  border-radius: 20rpx;
  padding: 18rpx 22rpx;
}
.tip-text { font-size: 26rpx; color: #33B98E; line-height: 1.7; }

.btn-row { display: flex; gap: 18rpx; margin-top: 32rpx; }
.btn-row .btn { flex: 1; height: 84rpx; font-size: 30rpx; }
</style>
