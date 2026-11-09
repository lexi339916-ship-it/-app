<script setup>
const emit = defineEmits(['ask', 'tool'])

const SCENES = [
  { key: 'assets', icon: '🏦', label: '我的资产', desc: '资产、负债与净资产', prompt: '查看我的个人资产' },
  { key: 'spending', icon: '📊', label: '消费分析', desc: '本月支出与分类', prompt: '帮我分析本月消费' },
  { key: 'goal', icon: '🎯', label: '储蓄规划', desc: '目标拆解与预算', prompt: '帮我规划储蓄目标' },
  { key: 'note', icon: '🗒️', label: '任务提取', desc: '一句话拆成待办', tool: 'note' },
]

function openScene(scene) {
  if (scene.tool) emit('tool', scene.tool)
  else emit('ask', scene.prompt)
}
</script>

<template>
  <view class="welcome">
    <view class="welcome-title-row">
      <image class="welcome-cat" src="/static/doodles/cat.png" mode="widthFix" />
      <view class="welcome-copy">
        <text class="welcome-title">你好，今天想了解什么？</text>
        <text class="welcome-sub">我可以帮你管理资产、分析消费、规划预算。</text>
      </view>
    </view>

    <view class="scene-grid">
      <view class="scene" v-for="s in SCENES" :key="s.key" @click="openScene(s)">
        <view class="scene-icon">{{ s.icon }}</view>
        <view class="scene-main">
          <text class="scene-label">{{ s.label }}</text>
          <text class="scene-desc">{{ s.desc }}</text>
        </view>
        <text class="scene-arrow">›</text>
      </view>
    </view>
    <text class="welcome-hint">也可以直接描述你的问题，涉及写入会先出方案由你确认。</text>

    <view class="tips-card">
      <view class="tip-row"><text class="tip-ico">🔒</text><text>数据只来自你的账本和工具，不编造金额</text></view>
      <view class="tip-row"><text class="tip-ico">✅</text><text>写操作先出 diff，由你审批后才执行</text></view>
      <view class="tip-row"><text class="tip-ico">💬</text><text>可以继续追问，历史会话可随时恢复</text></view>
    </view>
  </view>
</template>

<style scoped>
.welcome { padding: 18rpx 4rpx 24rpx; }
.welcome-title-row { display: flex; align-items: flex-start; gap: 16rpx; padding: 4rpx 6rpx 22rpx; }
.welcome-cat { width: 78rpx; height: 64rpx; flex-shrink: 0; }
.welcome-copy { flex: 1; min-width: 0; }
.welcome-title { display: block; font-size: 36rpx; font-weight: 800; color: #3A3F58; line-height: 1.4; }
.welcome-sub { display: block; font-size: 24rpx; color: #8A90A8; line-height: 1.6; margin-top: 6rpx; }
.scene-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12rpx; }
.scene { display: flex; align-items: center; gap: 10rpx; padding: 18rpx 16rpx;
  background: rgba(255, 253, 248, .92); border: 1rpx solid #F0EDF8; border-radius: 20rpx;
  box-shadow: 0 6rpx 18rpx rgba(124, 139, 255, .06); }
.scene:active { background: #F4F0FF; }
.scene-icon { width: 54rpx; height: 54rpx; border-radius: 18rpx; background: #EFF1FF;
  display: flex; align-items: center; justify-content: center; font-size: 27rpx; flex-shrink: 0; }
.scene-main { flex: 1; min-width: 0; }
.scene-label { display: block; font-size: 25rpx; font-weight: 700; color: #3A3F58; }
.scene-desc { display: block; font-size: 19rpx; color: #A6AAC2; margin-top: 3rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scene-arrow { font-size: 28rpx; color: #C3C7DA; flex-shrink: 0; }
.welcome-hint { display: block; text-align: center; font-size: 20rpx; color: #A6AAC2;
  line-height: 1.6; margin-top: 20rpx; }
.tips-card { margin-top: 22rpx; background: rgba(255, 253, 248, .72); border: 1rpx dashed #E4E0F2;
  border-radius: 18rpx; padding: 14rpx 18rpx; }
.tip-row { display: flex; align-items: center; gap: 10rpx; padding: 5rpx 0;
  font-size: 20rpx; color: #8A90A8; line-height: 1.5; }
.tip-ico { font-size: 20rpx; flex-shrink: 0; }
</style>
