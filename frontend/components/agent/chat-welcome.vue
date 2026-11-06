<script setup>
const emit = defineEmits(['ask'])

const PROMPTS = [
  { icon: '📊', label: '帮我分析本月消费', desc: '收支、分类、预算执行' },
  { icon: '🏦', label: '查看我的个人资产', desc: '可动用、固定资产、负债' },
  { icon: '🔁', label: '帮我检查订阅支出', desc: '涨价、低频、重复扣款' },
  { icon: '🎯', label: '帮我规划储蓄目标', desc: '按月拆解、预算与复盘' },
  { icon: '🧮', label: '这个月预算还有多少？', desc: '剩余额度与超支风险' },
  { icon: '🛍️', label: '如果购买一件商品，会影响我的储蓄计划吗？', desc: '购买前先测算影响' },
]
</script>

<template>
  <view class="welcome">
    <view class="welcome-head">
      <image class="welcome-cat" src="/static/doodles/cat.png" mode="widthFix" />
      <view class="welcome-text">
        <text class="welcome-title">你好，我是知账 AI 助手。</text>
        <text class="welcome-sub">我可以帮你分析消费、管理资产、规划预算，让每一笔钱都更清晰。</text>
      </view>
    </view>

    <view class="prompt-grid">
      <view class="prompt-card" v-for="p in PROMPTS" :key="p.label" @click="emit('ask', p.label)">
        <view class="prompt-icon">{{ p.icon }}</view>
        <view class="prompt-main">
          <text class="prompt-label">{{ p.label }}</text>
          <text class="prompt-desc">{{ p.desc }}</text>
        </view>
        <text class="prompt-arrow">›</text>
      </view>
    </view>
    <text class="welcome-hint">也可以直接输入问题；涉及写入时会先出方案，由你确认。</text>
  </view>
</template>

<style scoped>
.welcome { padding: 20rpx 4rpx 30rpx; }
.welcome-head { display: flex; align-items: flex-start; gap: 18rpx; padding: 10rpx 6rpx 26rpx; }
.welcome-cat { width: 92rpx; height: 76rpx; flex-shrink: 0; }
.welcome-text { flex: 1; min-width: 0; }
.welcome-title { display: block; font-size: 38rpx; font-weight: 800; color: #3A3F58; line-height: 1.4; }
.welcome-sub { display: block; font-size: 25rpx; color: #8A90A8; line-height: 1.7; margin-top: 8rpx; }
.prompt-grid { display: flex; flex-direction: column; gap: 14rpx; }
.prompt-card { display: flex; align-items: center; gap: 16rpx; padding: 20rpx 20rpx;
  background: rgba(255, 253, 248, .92); border: 1rpx solid #F0EDF8;
  border-radius: 22rpx; box-shadow: 0 8rpx 22rpx rgba(124, 139, 255, .07); }
.prompt-card:active { background: #F4F0FF; }
.prompt-icon { width: 62rpx; height: 62rpx; border-radius: 20rpx; background: #EFF1FF;
  display: flex; align-items: center; justify-content: center; font-size: 30rpx; flex-shrink: 0; }
.prompt-main { flex: 1; min-width: 0; }
.prompt-label { display: block; font-size: 26rpx; font-weight: 600; color: #3A3F58;
  line-height: 1.45; }
.prompt-desc { display: block; font-size: 21rpx; color: #A6AAC2; margin-top: 4rpx; }
.prompt-arrow { font-size: 32rpx; color: #C3C7DA; flex-shrink: 0; }
.welcome-hint { display: block; text-align: center; font-size: 21rpx; color: #A6AAC2;
  line-height: 1.7; margin-top: 26rpx; }
</style>
