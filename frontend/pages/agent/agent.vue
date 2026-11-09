<script setup>
import { computed, nextTick, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  apiAgentApproval, apiAgentMemories, apiAgentRun, apiAgentScan, apiAgentSession,
  apiAgentSessions, apiAgentUndo, apiDeleteAgentMemory, apiDeleteAgentSession,
  apiParseReceipt, apiTranscribeVoice,
} from '../../api/index.js'
import NotificationBell from '../../components/notification-bell.vue'
import AgentToolSheet from '../../components/agent-tool-sheet.vue'
import ChatWelcome from '../../components/agent/chat-welcome.vue'
import ChatComposer from '../../components/agent/chat-composer.vue'
import AgentRunMessage from '../../components/agent/agent-run-message.vue'
import SessionHistorySheet from '../../components/agent/session-history-sheet.vue'
import { refreshNotifications } from '../../store/notifications.js'
import store from '../../store/user.js'

const draft = ref('')
const loading = ref(false)
const error = ref(null)
const sessionId = ref('')
const sessionRuns = ref([])
const pendingText = ref('')
const deciding = ref(false)
const showTools = ref(false)
const pendingReceipt = ref([])
const historyOpen = ref(false)
const sessions = ref([])
const historyLoading = ref(false)
const memories = ref([])
const recording = ref(false)
const voiceLoading = ref(false)
const imageLoading = ref(false)
const receiptFocus = ref(false)
const scrollAnchor = ref('')

const showWelcome = computed(() =>
  !sessionRuns.value.length && !pendingText.value && !loading.value && !error.value)
const lastRun = computed(() =>
  sessionRuns.value.length ? sessionRuns.value[sessionRuns.value.length - 1] : null)
const composerPlaceholder = computed(() => {
  if (lastRun.value?.status === 'awaiting_approval') {
    return '继续追问：换一个方案 / 只调整 100 元 / 选择第二种方案'
  }
  return '发消息给知账……'
})

const PHRASES = [
  '你好',
  '你是谁',
  '本月消费怎么样',
  '查看我的资产',
  '检查订阅',
  '这个月预算还剩多少',
]

let recorder = null
try {
  recorder = uni.getRecorderManager ? uni.getRecorderManager() : null
} catch (e) {
  recorder = null
}

if (recorder && recorder.onStop) {
  recorder.onStop(async (res) => {
    recording.value = false
    if (!res || !res.tempFilePath) return
    voiceLoading.value = true
    error.value = null
    try {
      const data = await apiTranscribeVoice(res.tempFilePath)
      draft.value = data.text || ''
      uni.showToast({ title: '已转写，可编辑后发送', icon: 'none' })
      scrollToBottom()
    } catch (e) {
      error.value = {
        message: e.message || '语音识别失败，请改用文字输入',
        text: '',
      }
    } finally {
      voiceLoading.value = false
    }
  })
  recorder.onError(() => {
    recording.value = false
    voiceLoading.value = false
    uni.showToast({ title: '录音失败，请检查麦克风权限或改用文字', icon: 'none' })
  })
}

function sessionStorageKey() {
  return `agent_current_session_${store.user?.id || 'guest'}`
}

function saveSession() {
  if (sessionId.value) {
    uni.setStorageSync(sessionStorageKey(), sessionId.value)
  } else {
    uni.removeStorageSync(sessionStorageKey())
  }
}

function clearSessionState() {
  sessionId.value = ''
  sessionRuns.value = []
  draft.value = ''
  pendingText.value = ''
  error.value = null
  saveSession()
}

function scrollToBottom() {
  nextTick(() => {
    scrollAnchor.value = ''
    nextTick(() => { scrollAnchor.value = 'chat-bottom' })
  })
}

function scrollToTop() {
  nextTick(() => {
    scrollAnchor.value = ''
    nextTick(() => { scrollAnchor.value = 'chat-top' })
  })
}

async function loadSession(id, silent = false) {
  if (!id) return false
  try {
    const runs = await apiAgentSession(id)
    sessionId.value = id
    sessionRuns.value = runs || []
    saveSession()
    scrollToBottom()
    return true
  } catch (e) {
    if (!silent) {
      uni.showToast({ title: e.message || '会话加载失败', icon: 'none' })
      if (sessionId.value === id) clearSessionState()
      else uni.removeStorageSync(sessionStorageKey())
    }
    return false
  }
}

async function sendMessage(text) {
  if (loading.value) return
  const content = String(text === undefined ? draft.value : text).trim()
  if (!content) {
    uni.showToast({ title: '先告诉我想做什么', icon: 'none' })
    return
  }
  error.value = null
  draft.value = ''
  pendingText.value = content
  loading.value = true
  scrollToBottom()
  const parentRunId = lastRun.value && lastRun.value.session_id === sessionId.value
    ? lastRun.value.run_id : null
  try {
    const result = await apiAgentRun(
      content, 'auto', sessionId.value || null, parentRunId)
    sessionId.value = result.session_id || sessionId.value
    pendingText.value = ''
    const ok = result.session_id
      ? await loadSession(result.session_id, true)
      : false
    if (!ok) {
      sessionRuns.value.push(result)
      scrollToBottom()
    }
    saveSession()
  } catch (e) {
    pendingText.value = ''
    draft.value = content
    error.value = {
      message: e.message || '发送失败，请检查网络后重试',
      text: content,
    }
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function retryError() {
  if (!error.value || !error.value.text) return
  const text = error.value.text
  error.value = null
  sendMessage(text)
}

function newSession() {
  if (loading.value) {
    uni.showToast({ title: '正在处理，请稍候', icon: 'none' })
    return
  }
  clearSessionState()
  historyOpen.value = false
  uni.setStorageSync('agent_pending_receipt', '')
  uni.removeStorageSync('agent_pending_receipt')
  scrollToTop()
}

async function openHistory() {
  historyOpen.value = true
  historyLoading.value = true
  try {
    sessions.value = await apiAgentSessions(20)
  } catch (e) { /* 统一提示 */ } finally {
    historyLoading.value = false
  }
  loadMemories()
}

async function selectSession(s) {
  if (!s?.session_id) return
  historyOpen.value = false
  await loadSession(s.session_id)
}

function deleteSession(s) {
  uni.showModal({
    title: '删除会话',
    content: '会话会从历史中移除，但审计记录仍保留。确定删除吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiDeleteAgentSession(s.session_id)
        sessions.value = sessions.value.filter(item => item.session_id !== s.session_id)
        if (sessionId.value === s.session_id) clearSessionState()
        uni.showToast({ title: '已从历史移除', icon: 'none' })
      } catch (e) { /* 统一提示 */ }
    },
  })
}

async function loadMemories() {
  try {
    memories.value = await apiAgentMemories()
  } catch (e) { /* 记忆失败不影响主流程 */ }
}

function removeMemory(memory) {
  uni.showModal({
    title: '删除记忆',
    content: '删除后 Agent 不再使用这条记忆，确定吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        await apiDeleteAgentMemory(memory.id)
        memories.value = memories.value.filter(m => m.id !== memory.id)
        uni.showToast({ title: '已删除记忆', icon: 'none' })
      } catch (e) { /* 统一提示 */ }
    },
  })
}

function replaceRun(updated) {
  const index = sessionRuns.value.findIndex(r => r.run_id === updated.run_id)
  if (index >= 0) sessionRuns.value[index] = updated
  else sessionRuns.value.push(updated)
  scrollToBottom()
}

async function decide(approval, decision, edits) {
  if (deciding.value) return
  deciding.value = true
  try {
    const updated = await apiAgentApproval(approval.id, decision, edits || {})
    replaceRun(updated)
    loadMemories()
    uni.showToast({
      title: decision === 'approved' ? '已执行，可撤销' : '已暂不执行',
      icon: 'none',
    })
  } catch (e) {
    error.value = { message: e.message || '审批失败，请重试', text: '' }
  } finally {
    deciding.value = false
  }
}

function undo(run) {
  uni.showModal({
    title: '撤销执行',
    content: '撤销后，本次写入的账单/预算/任务/目标会恢复原状。确定撤销吗？',
    success: async (res) => {
      if (!res.confirm) return
      try {
        const updated = await apiAgentUndo(run.run_id)
        replaceRun(updated)
        loadMemories()
        uni.showToast({ title: '已撤销', icon: 'none' })
      } catch (e) {
        error.value = { message: e.message || '撤销失败，请重试', text: '' }
      }
    },
  })
}

function retryRun(run) {
  sendMessage(run.goal)
}

function startVoice() {
  if (!recorder) {
    uni.showToast({ title: '当前设备不支持录音，请改用文字', icon: 'none' })
    return
  }
  if (recording.value || voiceLoading.value || loading.value) return
  recording.value = true
  error.value = null
  try {
    recorder.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3',
    })
  } catch (e) {
    recording.value = false
    uni.showToast({ title: '录音启动失败，请改用文字', icon: 'none' })
  }
}

function stopVoice() {
  if (!recorder || !recording.value) return
  recording.value = false
  try { recorder.stop() } catch (e) { /* ignore */ }
}

function chooseReceipt() {
  if (loading.value || imageLoading.value) return
  if (!uni.chooseImage) {
    uni.showToast({ title: '当前环境不支持选图，请用文字记账', icon: 'none' })
    return
  }
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: ['album', 'camera'],
    success: async (res) => {
      const path = res.tempFilePaths && res.tempFilePaths[0]
      if (!path) return
      imageLoading.value = true
      error.value = null
      try {
        const data = await apiParseReceipt(path)
        if (!data.found || !data.drafts || !data.drafts.length) {
          uni.showToast({ title: data.notice || '未识别到支付信息，请改用文字', icon: 'none' })
          return
        }
        pendingReceipt.value = data.drafts.map((d, i) => ({
          ...d,
          key: `${Date.now()}-${i}`,
          bill_date: d.bill_date || new Date().toISOString().slice(0, 10),
          remark: d.remark || d.merchant || '',
        }))
        receiptFocus.value = true
        showTools.value = true
      } catch (e) {
        error.value = {
          message: e.message || '图片识别失败，请重试或改用文字',
          text: '',
        }
      } finally {
        imageLoading.value = false
      }
    },
  })
}

function closeTools() {
  showTools.value = false
  pendingReceipt.value = []
  receiptFocus.value = false
}

function handleToolAction(action) {
  if (!action) return
  closeTools()
  if (action.type === 'chat') {
    sendMessage(action.prompt)
  } else if (action.type === 'navigate') {
    uni.navigateTo({ url: action.url })
  } else if (action.type === 'pick-image') {
    chooseReceipt()
  }
}

async function scan(silent = false) {
  try {
    await apiAgentScan()
    refreshNotifications()
  } catch (e) {
    if (!silent) error.value = { message: e.message || '提醒加载失败', text: '' }
  }
}

onShow(async () => {
  const pending = uni.getStorageSync('agent_pending_receipt')
  if (pending) {
    try {
      const drafts = JSON.parse(pending)
      if (Array.isArray(drafts) && drafts.length) {
        pendingReceipt.value = drafts
        receiptFocus.value = true
        showTools.value = true
      }
    } catch (e) { /* 忽略损坏缓存 */ }
    uni.removeStorageSync('agent_pending_receipt')
  }
  const pendingPrompt = uni.getStorageSync('agent_pending_prompt')
  if (pendingPrompt) {
    draft.value = String(pendingPrompt)
    uni.removeStorageSync('agent_pending_prompt')
    uni.showToast({ title: '提醒已交给 Agent，可编辑后发送', icon: 'none' })
  }
  if (!sessionId.value && !sessionRuns.value.length) {
    const saved = uni.getStorageSync(sessionStorageKey())
    if (saved) {
      try {
        const recent = await apiAgentSessions(20)
        if (recent.some(s => s.session_id === saved)) {
          const ok = await loadSession(saved, true)
          if (!ok) uni.removeStorageSync(sessionStorageKey())
        } else {
          uni.removeStorageSync(sessionStorageKey())
        }
      } catch (e) {
        /* 网络失败时保留本地会话 id，下次再试 */
      }
    }
  }
  scan(true)
  refreshNotifications()
})
</script>

<template>
  <view class="chat-page">
    <!-- 顶部 -->
    <view class="chat-head">
      <view class="head-left">
        <image class="head-cat" src="/static/doodles/cat.png" mode="widthFix" />
        <view class="head-text">
          <text class="head-title">知账 AI</text>
          <text class="head-sub">你的个人消费管理助手</text>
        </view>
      </view>
      <view class="head-actions">
        <NotificationBell />
        <view class="round-btn" @click="openHistory">
          <text>🕘</text>
        </view>
        <view class="round-btn new-btn" @click="newSession">
          <text>＋</text>
        </view>
      </view>
    </view>

    <!-- 消息区 -->
    <scroll-view class="chat-scroll" scroll-y :scroll-into-view="scrollAnchor"
      scroll-with-animation>
      <view id="chat-top" class="anchor-top" />

      <ChatWelcome v-if="showWelcome" @ask="sendMessage" />

      <view v-for="r in sessionRuns" :key="r.run_id" :id="'run-' + r.run_id">
        <AgentRunMessage :run="r" :deciding="deciding"
          @decide="decide" @undo="undo" @retry="retryRun" />
      </view>

      <view v-if="pendingText" class="pending-line">
        <view class="pending-bubble">{{ pendingText }}</view>
      </view>

      <view v-if="loading" class="typing-line">
        <image class="typing-cat" src="/static/doodles/cat.png" mode="widthFix" />
        <view class="typing-bubble">
          <text class="typing-dots">···</text>
          <text class="typing-text">正在查询真实数据并生成方案…</text>
        </view>
      </view>

      <view v-if="error" class="error-banner">
        <text class="error-text">{{ error.message }}</text>
        <text v-if="error.text" class="error-retry" @click="retryError">重试</text>
        <text class="error-close" @click="error = null">×</text>
      </view>

      <view id="chat-bottom" class="anchor-bottom" />
    </scroll-view>

    <!-- 拍照记账快捷入口 -->
    <view class="capture-strip">
      <view :class="['capture-chip', imageLoading && 'capture-off']" @click="chooseReceipt">
        <text class="capture-icon">📷</text>
        <text>{{ imageLoading ? '识别中…' : '拍照记账' }}</text>
      </view>
      <text class="capture-hint">支付截图 / 小票 · 识别后确认再写入</text>
    </view>

    <!-- 输入区 -->
    <ChatComposer v-model="draft" :loading="loading" :recording="recording"
      :transcribing="voiceLoading" :phrases="PHRASES"
      :placeholder="composerPlaceholder"
      @send="sendMessage()" @voice-start="startVoice" @voice-stop="stopVoice"
      @tools="showTools = true" />

    <SessionHistorySheet :visible="historyOpen" :sessions="sessions"
      :memories="memories" :loading="historyLoading"
      :current-session-id="sessionId"
      @close="historyOpen = false" @select="selectSession"
      @delete="deleteSession" @new="newSession" @delete-memory="removeMemory" />

    <AgentToolSheet :visible="showTools" :initial-receipt="pendingReceipt"
      :focus="receiptFocus ? 'receipt' : ''"
      @close="closeTools" @action="handleToolAction" />
  </view>
</template>

<style scoped>
.chat-page { height: calc(100vh - var(--window-bottom, 0px));
  height: calc(100dvh - var(--window-bottom, 0px));
  padding-top: calc(var(--status-bar-height, 0px) + 6rpx);
  display: flex; flex-direction: column; overflow: hidden; box-sizing: border-box; }
.chat-head { flex-shrink: 0; display: flex; align-items: center; justify-content: space-between;
  gap: 12rpx; padding: 8rpx 20rpx 14rpx; }
.head-left { display: flex; align-items: center; gap: 12rpx; min-width: 0; }
.head-cat { width: 70rpx; height: 58rpx; flex-shrink: 0; }
.head-text { min-width: 0; }
.head-title { display: block; font-size: 32rpx; font-weight: 800; color: #4F49A8;
  letter-spacing: 1rpx; }
.head-sub { display: block; font-size: 20rpx; color: #8A90A8; margin-top: 2rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head-actions { display: flex; align-items: center; gap: 8rpx; flex-shrink: 0; }
.round-btn { width: 56rpx; height: 56rpx; border-radius: 28rpx; background: #FFFDF8;
  border: 1rpx solid #E9E6F4; display: flex; align-items: center; justify-content: center;
  font-size: 25rpx; color: #6C7BF5; box-shadow: 0 5rpx 14rpx rgba(124, 139, 255, .08); }
.new-btn { background: linear-gradient(135deg, #7C8BFF, #A78BFA); color: #fff;
  border: none; font-weight: 800; font-size: 30rpx; }
.chat-scroll { flex: 1; height: 0; min-height: 0; padding: 0 22rpx; box-sizing: border-box; }
.anchor-top { height: 4rpx; }
.anchor-bottom { height: 24rpx; }
.capture-strip { flex-shrink: 0; display: flex; align-items: center; gap: 12rpx;
  padding: 6rpx 20rpx 8rpx; background: rgba(255, 253, 248, .86); }
.capture-chip { display: inline-flex; align-items: center; gap: 6rpx; flex-shrink: 0;
  font-size: 21rpx; font-weight: 700; color: #5A54B8; background: #EFF1FF;
  border: 1rpx solid #DFE2FF; border-radius: 999rpx; padding: 8rpx 18rpx; }
.capture-chip:active { background: #E4E6FF; }
.capture-off { opacity: .55; }
.capture-icon { font-size: 21rpx; }
.capture-hint { font-size: 18rpx; color: #B0B4C8; }
.pending-line { display: flex; justify-content: flex-end; padding: 8rpx 0 14rpx; }
.pending-bubble { max-width: 78%; background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  color: #fff; font-size: 27rpx; line-height: 1.6; padding: 16rpx 20rpx;
  border-radius: 22rpx 22rpx 6rpx 22rpx; opacity: .82; word-break: break-word; }
.typing-line { display: flex; align-items: flex-start; gap: 12rpx; padding: 4rpx 0 18rpx; }
.typing-cat { width: 56rpx; height: 48rpx; flex-shrink: 0; }
.typing-bubble { display: flex; align-items: center; gap: 10rpx; background: #FFFDF8;
  border: 1rpx solid #F0EDF8; border-radius: 6rpx 20rpx 20rpx 20rpx; padding: 14rpx 16rpx; }
.typing-dots { font-size: 26rpx; color: #6C7BF5; letter-spacing: 2rpx; }
.typing-text { font-size: 21rpx; color: #8A90A8; }
.error-banner { display: flex; align-items: center; gap: 12rpx; margin: 8rpx 0 16rpx;
  padding: 14rpx 16rpx; border-radius: 16rpx; background: #FFEDEE; }
.error-text { flex: 1; font-size: 22rpx; color: #C94F4F; line-height: 1.5; }
.error-retry { font-size: 22rpx; color: #6C7BF5; flex-shrink: 0; }
.error-close { font-size: 30rpx; color: #C94F4F; flex-shrink: 0; padding: 0 4rpx; }
</style>
