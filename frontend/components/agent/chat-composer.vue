<script setup>
const props = defineProps({
  modelValue: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  recording: { type: Boolean, default: false },
  transcribing: { type: Boolean, default: false },
  imageLoading: { type: Boolean, default: false },
  placeholder: { type: String, default: '发消息给知账……' },
})
const emit = defineEmits([
  'update:modelValue', 'send', 'voice-start', 'voice-stop', 'attach', 'tools',
])

function onInput(e) {
  emit('update:modelValue', e.detail.value)
}

function send() {
  if (props.loading || !props.modelValue.trim()) return
  emit('send')
}

function startVoice() {
  if (props.loading || props.transcribing) return
  emit('voice-start')
}

function stopVoice() {
  emit('voice-stop')
}
</script>

<template>
  <view class="composer-wrap">
    <view v-if="recording || transcribing" class="record-bar">
      <view class="record-wave">
        <text v-for="i in 5" :key="i" class="wave-bar" :style="{ animationDelay: (i * 0.1) + 's' }" />
      </view>
      <text class="record-text">{{ transcribing ? '正在识别语音…' : '正在听… 松开结束' }}</text>
      <text class="record-hint">识别失败可改用文字</text>
    </view>

    <view class="composer">
      <view class="composer-input-wrap">
        <textarea class="composer-input" :value="modelValue" :disabled="loading"
          auto-height :maxlength="500" :adjust-position="true" :cursor-spacing="24"
          confirm-type="send" :placeholder="transcribing ? '正在识别语音…' : placeholder"
          placeholder-class="composer-ph" @input="onInput" @confirm="send" />
      </view>
      <view class="composer-actions">
        <view class="icon-btn plus" @click="emit('tools')">
          <text>＋</text>
        </view>
        <view class="icon-btn image-btn" @click="emit('attach')">
          <text>{{ imageLoading ? '…' : '🖼' }}</text>
        </view>
        <view :class="['icon-btn mic', recording && 'mic-on']"
          @touchstart.prevent="startVoice" @touchend.prevent="stopVoice"
          @touchcancel.prevent="stopVoice" @mousedown.prevent="startVoice"
          @mouseup.prevent="stopVoice" @mouseleave="stopVoice">
          <text>🎙</text>
        </view>
        <view :class="['send-btn', (loading || !modelValue.trim()) && 'send-off']" @click="send">
          <text>{{ loading ? '…' : '↑' }}</text>
        </view>
      </view>
    </view>
    <view class="composer-foot">
      <text class="foot-note">写操作需审批 · 不做投资建议 / 自动转账</text>
    </view>
  </view>
</template>

<style scoped>
.composer-wrap { background: rgba(255, 253, 248, .96); border-top: 1rpx solid #F0EDF8;
  padding: 12rpx 20rpx calc(12rpx + env(safe-area-inset-bottom)); }
.record-bar { display: flex; align-items: center; gap: 12rpx; margin-bottom: 10rpx;
  padding: 12rpx 18rpx; background: #F4F0FF; border-radius: 16rpx; }
.record-wave { display: flex; align-items: center; gap: 4rpx; height: 30rpx; }
.wave-bar { width: 6rpx; height: 12rpx; border-radius: 3rpx; background: #6C7BF5;
  animation: wave 0.6s ease-in-out infinite alternate; }
@keyframes wave { from { height: 8rpx; } to { height: 28rpx; } }
.record-text { flex: 1; font-size: 23rpx; color: #5A54B8; font-weight: 600; }
.record-hint { font-size: 20rpx; color: #A6AAC2; }
.composer { display: flex; align-items: flex-end; gap: 10rpx; }
.composer-input-wrap { flex: 1; min-width: 0; background: #F6F4FB; border: 1rpx solid #E9E6F4;
  border-radius: 26rpx; padding: 12rpx 18rpx; box-sizing: border-box; }
.composer-input { width: 100%; min-height: 48rpx; max-height: 170rpx; font-size: 27rpx;
  line-height: 1.6; color: #3A3F58; overflow-y: auto; }
.composer-ph { color: #B7BCCE; }
.composer-actions { display: flex; align-items: center; gap: 8rpx; flex-shrink: 0; }
.icon-btn { width: 62rpx; height: 62rpx; border-radius: 31rpx; display: flex;
  align-items: center; justify-content: center; font-size: 28rpx; color: #6C7BF5;
  background: #F2F1FF; }
.icon-btn:active { opacity: .75; }
.mic { font-size: 25rpx; }
.mic-on { background: #6C7BF5; color: #fff; }
.send-btn { width: 68rpx; height: 68rpx; border-radius: 34rpx; display: flex;
  align-items: center; justify-content: center; font-size: 36rpx; font-weight: 800;
  color: #fff; background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  box-shadow: 0 8rpx 18rpx rgba(124, 139, 255, .28); }
.send-off { background: #D9DCEA; box-shadow: none; color: #fff; }
.composer-foot { display: flex; align-items: center; justify-content: space-between;
  padding: 8rpx 6rpx 0; }
.foot-note { font-size: 19rpx; color: #B0B4C8; }
</style>
