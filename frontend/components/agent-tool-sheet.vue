<script setup>
import { computed, ref, watch } from 'vue'
import {
  apiAddBill, apiAddNote, apiBillCheck, apiCategories, apiParseNote,
} from '../api/index.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  initialReceipt: { type: Array, default: () => [] },
  focus: { type: String, default: '' }, // receipt 时直接展示截图草稿
})
const emit = defineEmits(['close', 'action'])

const panel = ref('')
const categories = ref([])
const receiptDrafts = ref([])
const noteText = ref('')
const noteDrafts = ref([])
const loading = ref(false)
const saving = ref(false)
const error = ref(null)

const categoryNames = computed(() => categories.value.map(c => c.name))

const GROUPS = [
  {
    key: 'analysis',
    title: '智能分析',
    desc: '基于真实账单与资产数据',
    tools: [
      { key: 'summary', label: '消费总结', desc: '本月收支与主要支出', icon: '📊', bg: '#EFF1FF' },
      { key: 'health', label: '消费健康诊断', desc: '预算、目标、订阅、结构', icon: '🩺', bg: '#E9F8F2' },
      { key: 'simulator', label: '消费决策模拟', desc: '买之前先测算影响', icon: '🧮', bg: '#FFF6E7' },
    ],
  },
  {
    key: 'manage',
    title: '账单与管理',
    desc: '记账、导入与现有管理页',
    tools: [
      { key: 'csv', label: 'CSV 导入', desc: '微信 / 支付宝 / 通用', icon: '📥', bg: '#E9F8F2' },
      { key: 'budget', label: '预算管理', desc: '分类预算与调度', icon: '💰', bg: '#FFEFF2' },
      { key: 'note', label: '任务提取', desc: '一句话拆成待办', icon: '🗒️', bg: '#F4F0FF' },
      { key: 'subscriptions', label: '订阅管理', desc: '涨价 / 低频体检', icon: '🔁', bg: '#F6F4FB' },
      { key: 'goals', label: '储蓄目标', desc: '目标 / 挑战 / 进度', icon: '🎯', bg: '#FFEDEE' },
    ],
  },
]

const ACTIONS = {
  summary: { type: 'chat', prompt: '本月收支怎么样？主要支出有哪些？' },
  health: { type: 'chat', prompt: '帮我做一次消费健康诊断' },
  simulator: { type: 'navigate', url: '/pages/simulator/simulator' },
  note: { type: 'panel', panel: 'note' },
  csv: { type: 'navigate', url: '/pages/import/import?pick=1' },
  budget: { type: 'navigate', url: '/pages/budget/center' },
  subscriptions: { type: 'navigate', url: '/pages/subscriptions/list' },
  goals: { type: 'navigate', url: '/pages/goals/goals' },
}

async function loadCategories() {
  if (categories.value.length) return
  try {
    const res = await apiCategories()
    categories.value = res.items || []
  } catch (e) { /* 分类失败不阻塞 */ }
}

function categoryIndex(name) {
  const i = categoryNames.value.indexOf(name)
  return i >= 0 ? i : 0
}

function setCategory(draft, e) {
  draft.category = categoryNames.value[Number(e.detail.value)] || draft.category
}

function fillReceipt(list) {
  receiptDrafts.value = (list || []).map((d, i) => ({
    ...d,
    key: `${Date.now()}-${i}`,
    bill_date: d.bill_date || new Date().toISOString().slice(0, 10),
    remark: d.remark || d.merchant || '',
  }))
}

function initPanel() {
  if (props.focus === 'receipt' || props.initialReceipt.length) {
    panel.value = 'receipt'
    fillReceipt(props.initialReceipt)
  } else if (props.focus === 'note') {
    panel.value = 'note'
  } else {
    panel.value = ''
  }
  error.value = null
}

watch(() => props.visible, (v) => {
  if (v) {
    loadCategories()
    initPanel()
  }
}, { immediate: true })
watch(() => props.initialReceipt, () => {
  if (props.visible) {
    panel.value = 'receipt'
    fillReceipt(props.initialReceipt)
  }
})

function handleTool(tool) {
  const action = ACTIONS[tool.key]
  if (!action) return
  if (action.type === 'panel') {
    panel.value = action.panel
    error.value = null
    if (action.panel === 'note') loadCategories()
    return
  }
  emit('action', action)
}

async function saveReceipt(draft) {
  const amount = Number(draft.amount)
  if (!amount || amount <= 0) {
    uni.showToast({ title: '请填写正确金额', icon: 'none' }); return
  }
  saving.value = true
  try {
    const bill = await apiAddBill({
      type: draft.type === 'income' ? 'income' : 'expense',
      amount: amount.toFixed(2),
      category: draft.category || '其他',
      bill_date: draft.bill_date,
      remark: (draft.remark || draft.merchant || '').slice(0, 200),
      source: 'receipt',
      pay_channel: draft.pay_channel || '',
      funding_account: draft.funding_account || '',
    })
    try { await apiBillCheck(bill.id) } catch (e) { /* 预算预警失败不影响保存 */ }
    receiptDrafts.value = receiptDrafts.value.filter(d => d.key !== draft.key)
    uni.showToast({ title: '已保存到账单', icon: 'none' })
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}

async function parseNote() {
  if (!noteText.value.trim()) {
    uni.showToast({ title: '先输入要整理的内容', icon: 'none' }); return
  }
  loading.value = true
  error.value = null
  try {
    const data = await apiParseNote(noteText.value)
    noteDrafts.value = (data.drafts || []).map((d, i) => ({ ...d, key: `note-${Date.now()}-${i}` }))
    if (!noteDrafts.value.length) {
      uni.showToast({ title: data.notice || '未识别到任务内容', icon: 'none' })
    }
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

async function saveNote(draft) {
  if (!draft.title || !draft.title.trim()) {
    uni.showToast({ title: '任务标题不能为空', icon: 'none' }); return
  }
  saving.value = true
  try {
    await apiAddNote({
      title: draft.title.slice(0, 100),
      content: draft.content || '',
      note_type: draft.note_type === 'note' ? 'note' : 'todo',
      status: 'open',
      due_at: draft.due_at || null,
      priority: draft.priority || 'medium',
    })
    noteDrafts.value = noteDrafts.value.filter(d => d.key !== draft.key)
    uni.showToast({ title: '已保存到便签', icon: 'none' })
  } catch (e) {
    error.value = e
  } finally {
    saving.value = false
  }
}

function close() { emit('close') }
function back() { panel.value = ''; error.value = null }
</script>

<template>
  <view v-if="visible" class="mask" @click.self="close">
    <view class="sheet">
      <view class="sheet-head">
        <view class="sheet-title-row">
          <text v-if="panel" class="back-btn" @click="back">‹</text>
          <view>
            <text class="sheet-title">{{ panel === 'receipt' ? '截图记账' : (panel === 'note' ? '任务提取' : 'Agent 工具') }}</text>
            <text class="sheet-sub">{{ panel === 'receipt' ? '识别结果确认后才写入账单' : (panel === 'note' ? '一句话拆成可执行待办' : '选择工具，直接进入对应操作') }}</text>
          </view>
        </view>
        <text class="sheet-close" @click="close">×</text>
      </view>

      <view v-if="error" class="error-box">{{ error.message || '操作失败，请重试' }}</view>

      <!-- 工具菜单 -->
      <view v-if="!panel" class="tool-body">
        <view class="tool-group" v-for="group in GROUPS" :key="group.key">
          <view class="group-head">
            <text class="group-title">{{ group.title }}</text>
            <text class="group-desc">{{ group.desc }}</text>
          </view>
          <view class="tool-list">
            <view class="tool-row" v-for="tool in group.tools" :key="tool.key" @click="handleTool(tool)">
              <view class="tool-icon" :style="{ background: tool.bg }">{{ tool.icon }}</view>
              <view class="tool-main">
                <text class="tool-name">{{ tool.label }}</text>
                <text class="tool-desc">{{ tool.desc }}</text>
              </view>
              <text class="tool-arrow">›</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 截图草稿 -->
      <view v-if="panel === 'receipt'" class="panel-body">
        <view v-if="receiptDrafts.length" class="draft-list">
          <view class="draft" v-for="d in receiptDrafts" :key="d.key">
            <view class="draft-line">
              <text class="draft-label">金额</text>
              <input class="draft-input" type="digit" v-model="d.amount" />
              <text class="draft-unit">元</text>
            </view>
            <view class="draft-line">
              <text class="draft-label">分类</text>
              <picker class="draft-picker" :range="categoryNames" :value="categoryIndex(d.category)"
                @change="setCategory(d, $event)">
                <view class="picker-box">{{ d.category || '其他' }} <text class="arrow">⌄</text></view>
              </picker>
            </view>
            <view class="draft-line">
              <text class="draft-label">备注</text>
              <input class="draft-input" v-model="d.remark" maxlength="200" />
            </view>
            <view class="draft-line">
              <text class="draft-label">日期</text>
              <input class="draft-input" v-model="d.bill_date" placeholder="YYYY-MM-DD" />
            </view>
            <view class="draft-actions">
              <text class="muted">{{ d.type === 'income' ? '收入' : '支出' }} · {{ d.pay_channel || '未识别渠道' }}</text>
              <button class="btn small" :disabled="saving" @click="saveReceipt(d)">确认保存</button>
            </view>
          </view>
        </view>
        <view v-else class="empty-box">
          <text>还没有截图草稿</text>
          <text class="hint">识别失败时请改用文字记账。</text>
        </view>
        <button class="btn ghost reselect" @click="emit('action', { type: 'pick-image' })">重新选择截图</button>
      </view>

      <!-- 任务草稿 -->
      <view v-if="panel === 'note'" class="panel-body">
        <textarea class="note-input" v-model="noteText" auto-height maxlength="500"
          placeholder="例如：明天下午三点交报告，晚上买牛奶" />
        <button class="btn primary" :class="{ 'btn-off': loading }" :disabled="loading" @click="parseNote">
          {{ loading ? '整理中…' : '提取任务草稿' }}
        </button>
        <view v-if="noteDrafts.length" class="draft-list">
          <view class="draft" v-for="d in noteDrafts" :key="d.key">
            <input class="draft-input" v-model="d.title" maxlength="100" placeholder="任务标题" />
            <textarea class="draft-content" v-model="d.content" auto-height maxlength="500"
              placeholder="补充说明" />
            <view class="draft-actions">
              <text class="muted">{{ d.note_type === 'note' ? '便签' : '待办' }} · {{ d.priority || 'medium' }}</text>
              <button class="btn small" :disabled="saving" @click="saveNote(d)">确认保存</button>
            </view>
          </view>
        </view>
        <view v-else class="empty-box">
          <text>输入一段话，Agent 会拆成任务草稿。</text>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(35, 34, 58, .45);
  z-index: 999; display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 80vh; background: #FFFDF8; border-radius: 32rpx 32rpx 0 0;
  padding: 24rpx 28rpx 32rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.sheet-head { display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12rpx; flex-shrink: 0; }
.sheet-title-row { display: flex; align-items: flex-start; gap: 8rpx; min-width: 0; }
.back-btn { font-size: 42rpx; color: #6C7BF5; line-height: 1; padding: 0 6rpx 0 0; }
.sheet-title { display: block; font-size: 31rpx; font-weight: 800; color: #3A3F58; }
.sheet-sub { display: block; font-size: 20rpx; color: #A6AAC2; margin-top: 4rpx; }
.sheet-close { font-size: 40rpx; color: #A6AAC2; padding: 0 6rpx; line-height: 1; }
.tool-body { flex: 1; min-height: 0; overflow-y: auto; margin-top: 14rpx; }
.tool-group { margin-top: 8rpx; }
.group-head { display: flex; align-items: baseline; gap: 10rpx; padding: 8rpx 4rpx; }
.group-title { font-size: 23rpx; font-weight: 800; color: #5A54B8; }
.group-desc { font-size: 18rpx; color: #B0B4C8; }
.tool-list { background: #FAF9FF; border: 1rpx solid #F0EDF8; border-radius: 20rpx;
  overflow: hidden; }
.tool-row { display: flex; align-items: center; gap: 14rpx; padding: 16rpx 18rpx;
  border-bottom: 1rpx solid #F4F2FA; }
.tool-row:last-child { border-bottom: none; }
.tool-row:active { background: #F4F0FF; }
.tool-icon { width: 58rpx; height: 58rpx; border-radius: 18rpx; display: flex;
  align-items: center; justify-content: center; font-size: 28rpx; flex-shrink: 0; }
.tool-main { flex: 1; min-width: 0; }
.tool-name { display: block; font-size: 25rpx; font-weight: 700; color: #3A3F58; }
.tool-desc { display: block; font-size: 19rpx; color: #A6AAC2; margin-top: 3rpx; }
.tool-arrow { font-size: 30rpx; color: #C3C7DA; flex-shrink: 0; }
.panel-body { flex: 1; min-height: 0; overflow-y: auto; margin-top: 14rpx; }
.btn { margin: 0; border-radius: 18rpx; font-size: 26rpx; font-weight: 700; }
.btn.primary { color: #fff; background: linear-gradient(135deg, #7C8BFF, #A78BFA); }
.btn.ghost { color: #6C7BF5; background: #F2F1FF; }
.btn.small { height: 60rpx; line-height: 60rpx; font-size: 22rpx; padding: 0 20rpx; }
.btn-off { opacity: .55; }
.hint { display: block; font-size: 20rpx; color: #A6AAC2; line-height: 1.6; margin-top: 8rpx; }
.error-box { background: #FFEDEE; border-radius: 12rpx; padding: 10rpx 12rpx;
  font-size: 21rpx; color: #C94F4F; margin-top: 10rpx; flex-shrink: 0; }
.draft-list { margin-top: 12rpx; }
.draft { background: #FAF9FF; border: 1rpx solid #E9E6F4; border-radius: 16rpx;
  padding: 14rpx; margin-bottom: 12rpx; }
.draft-line { display: flex; align-items: center; gap: 10rpx; margin-bottom: 9rpx; }
.draft-label { width: 74rpx; font-size: 21rpx; color: #8A90A8; flex-shrink: 0; }
.draft-input { flex: 1; height: 56rpx; background: #FFF; border: 1rpx solid #E9E6F4;
  border-radius: 10rpx; padding: 0 12rpx; font-size: 24rpx; color: #3A3F58; }
.draft-unit { font-size: 20rpx; color: #8A90A8; }
.draft-picker { flex: 1; }
.picker-box { height: 56rpx; line-height: 56rpx; background: #FFF; border: 1rpx solid #E9E6F4;
  border-radius: 10rpx; padding: 0 12rpx; font-size: 23rpx; color: #3A3F58; }
.arrow { float: right; color: #A6AAC2; }
.draft-actions { display: flex; align-items: center; justify-content: space-between;
  gap: 10rpx; margin-top: 10rpx; }
.muted { font-size: 19rpx; color: #A6AAC2; }
.note-input { width: 100%; min-height: 150rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 14rpx; padding: 14rpx; font-size: 24rpx; box-sizing: border-box; margin-bottom: 12rpx; }
.draft-content { width: 100%; min-height: 80rpx; background: #FFF; border: 1rpx solid #E9E6F4;
  border-radius: 10rpx; padding: 10rpx; font-size: 23rpx; box-sizing: border-box; margin-top: 8rpx; }
.empty-box { text-align: center; font-size: 22rpx; color: #8A90A8; padding: 34rpx 0; }
.reselect { margin-top: 14rpx; height: 68rpx; font-size: 24rpx; }
</style>
