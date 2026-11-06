<script setup>
import { computed, ref, watch } from 'vue'
import {
  apiAddBill, apiAddNote, apiBillCheck, apiCategories, apiParseNote,
  apiParseReceipt, apiSummary,
} from '../api/index.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  initialReceipt: { type: Array, default: () => [] },
})
const emit = defineEmits(['close'])

const tab = ref('receipt')
const categories = ref([])
const receiptDrafts = ref([])
const noteText = ref('')
const noteDrafts = ref([])
const summaryText = ref('')
const loading = ref(false)
const saving = ref(false)
const error = ref(null)

const categoryNames = computed(() => categories.value.map(c => c.name))
const TOOLS = [
  { key: 'receipt', label: '截图记账', desc: '支付截图 / 小票', icon: '/static/icons/act_camera.png', bg: '#EEF1FF', panel: true },
  { key: 'note', label: '任务提取', desc: '一句话拆任务', icon: '/static/icons/act_note.png', bg: '#FFF6E7', panel: true },
  { key: 'summary', label: '消费总结', desc: '本月消费总结', icon: '/static/icons/act_sparkle.png', bg: '#F4F0FF', panel: true },
  { key: 'health', label: '消费健康诊断', desc: '五项健康指标', icon: '/static/icons/act_chart.png', bg: '#E9F8F2', route: '/pages/health/report' },
  { key: 'simulator', label: '消费决策模拟', desc: '买之前先算一算', icon: '/static/icons/act_target.png', bg: '#FFF7E9', route: '/pages/simulator/simulator' },
  { key: 'csv', label: 'CSV 账单导入', desc: '微信/支付宝/通用', icon: '/static/icons/act_note.png', bg: '#E9F8F2', route: '/pages/import/import' },
  { key: 'budget', label: '预算中心', desc: '分类预算 / AI 方案', icon: '/static/icons/act_wallet.png', bg: '#FFEFF2', route: '/pages/budget/center' },
  { key: 'subscriptions', label: '订阅管理', desc: '涨价 / 低频体检', icon: '/static/icons/act_wallet.png', bg: '#F6F4FB', route: '/pages/subscriptions/list' },
  { key: 'goals', label: '储蓄目标', desc: '目标 / 挑战 / 进度', icon: '/static/icons/act_target.png', bg: '#FFEDEE', route: '/pages/goals/goals' },
]
const currentTool = computed(() => TOOLS.find(t => t.key === tab.value) || TOOLS[0])

async function loadCategories() {
  if (categories.value.length) return
  try {
    const res = await apiCategories('expense')
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

function useInitialReceipt() {
  if (props.initialReceipt && props.initialReceipt.length) {
    tab.value = 'receipt'
    receiptDrafts.value = props.initialReceipt.map((d, i) => ({
      ...d,
      key: `init-${i}`,
      bill_date: d.bill_date || new Date().toISOString().slice(0, 10),
      remark: d.remark || d.merchant || '',
    }))
  }
}

watch(() => props.visible, (v) => {
  if (v) {
    loadCategories()
    useInitialReceipt()
  }
})
watch(() => props.initialReceipt, () => {
  if (props.visible) useInitialReceipt()
})

function chooseReceipt() {
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
      loading.value = true
      error.value = null
      try {
        const data = await apiParseReceipt(path)
        if (!data.found || !data.drafts || !data.drafts.length) {
          uni.showToast({ title: data.notice || '未识别到支付信息', icon: 'none' })
          return
        }
        receiptDrafts.value = data.drafts.map((d, i) => ({
          ...d,
          key: `${Date.now()}-${i}`,
          bill_date: d.bill_date || new Date().toISOString().slice(0, 10),
          remark: d.remark || d.merchant || '',
        }))
      } catch (e) {
        error.value = e
      } finally {
        loading.value = false
      }
    },
  })
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

async function loadSummary() {
  loading.value = true
  error.value = null
  try {
    const data = await apiSummary('month')
    summaryText.value = data.summary || '本月还没有足够的数据。'
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

function close() { emit('close') }

function handleTool(tool) {
  if (tool.panel) {
    tab.value = tool.key
    error.value = null
    return
  }
  close()
  if (tool.route) uni.navigateTo({ url: tool.route })
}
</script>

<template>
  <view v-if="visible" class="mask" @click.self="close">
    <view class="sheet">
      <view class="sheet-head">
        <text class="sheet-title">Agent 工具</text>
        <text class="sheet-close" @click="close">×</text>
      </view>
      <view class="tool-grid">
        <view class="tool-card" v-for="tool in TOOLS" :key="tool.key"
          :class="{ active: tool.panel && tab === tool.key }" @click="handleTool(tool)">
          <view class="tool-icon" :style="{ background: tool.bg }">
            <image class="tool-img" :src="tool.icon" mode="widthFix" />
          </view>
          <view class="tool-body">
            <text class="tool-name">{{ tool.label }}</text>
            <text class="tool-desc">{{ tool.desc }}</text>
          </view>
        </view>
      </view>

      <text class="panel-title">当前：{{ currentTool.label }}</text>

      <view v-if="error" class="error-box">
        <text>{{ error.message || '操作失败，请重试' }}</text>
      </view>

      <!-- 截图记账 -->
      <view v-if="tab === 'receipt'">
        <button class="btn primary" :class="{ 'btn-off': loading }" :disabled="loading" @click="chooseReceipt">
          {{ loading ? '识别中…' : '选择支付截图 / 小票' }}
        </button>
        <text class="hint">识别后核对金额和分类，确认才会写入账单。</text>
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
          <text class="hint">支持支付截图、小票；识别失败时请改用文字记账。</text>
        </view>
      </view>

      <!-- 任务提取 -->
      <view v-if="tab === 'note'">
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
      </view>

      <!-- 消费总结 -->
      <view v-if="tab === 'summary'">
        <button class="btn primary" :class="{ 'btn-off': loading }" :disabled="loading" @click="loadSummary">
          {{ loading ? '生成中…' : '生成本月消费总结' }}
        </button>
        <text v-if="summaryText" class="summary-text">{{ summaryText }}</text>
        <view v-else class="empty-box">
          <text>用真实账单生成一段可读的消费总结</text>
        </view>
      </view>

    </view>
  </view>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(35, 34, 58, .45);
  z-index: 999; display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 82vh; overflow-y: auto; background: #FFFDF8;
  border-radius: 32rpx 32rpx 0 0; padding: 28rpx 28rpx 40rpx; box-sizing: border-box; }
.sheet-head { display: flex; align-items: center; justify-content: space-between; }
.sheet-title { font-size: 32rpx; font-weight: 800; color: #3A3F58; }
.sheet-close { font-size: 40rpx; color: #A6AAC2; padding: 0 8rpx; }
.tool-grid { display: flex; flex-wrap: wrap; gap: 14rpx; margin: 20rpx 0 12rpx; }
.tool-card { width: calc(50% - 7rpx); display: flex; align-items: center; gap: 12rpx;
  background: #FAF9FF; border: 1rpx solid #E9E6F4; border-radius: 18rpx; padding: 14rpx;
  box-sizing: border-box; }
.tool-card.active { border-color: #8B7FE8; background: #F4F0FF; }
.tool-icon { width: 54rpx; height: 54rpx; border-radius: 16rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; }
.tool-img { width: 38rpx; height: 38rpx; }
.tool-body { flex: 1; min-width: 0; }
.tool-name { display: block; font-size: 22rpx; font-weight: 700; color: #3A3F58;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-desc { display: block; font-size: 18rpx; color: #A6AAC2; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.panel-title { display: block; font-size: 22rpx; color: #6C7BF5; font-weight: 700;
  margin: 8rpx 0 12rpx; }
.btn { margin: 0; height: 78rpx; line-height: 78rpx; border-radius: 20rpx;
  font-size: 27rpx; font-weight: 700; }
.btn.primary { color: #FFF; background: linear-gradient(135deg, #7C8BFF, #A78BFA); }
.btn.small { height: 62rpx; line-height: 62rpx; font-size: 23rpx; padding: 0 22rpx; }
.btn-off { opacity: .55; }
.hint { display: block; font-size: 21rpx; color: #A6AAC2; line-height: 1.6; margin-top: 10rpx; }
.error-box { background: #FFEDEE; border-radius: 14rpx; padding: 12rpx 14rpx;
  font-size: 22rpx; color: #C94F4F; margin-bottom: 12rpx; }
.draft-list { margin-top: 16rpx; }
.draft { background: #FAF9FF; border: 1rpx solid #E9E6F4; border-radius: 18rpx;
  padding: 16rpx; margin-bottom: 14rpx; }
.draft-line { display: flex; align-items: center; gap: 10rpx; margin-bottom: 10rpx; }
.draft-label { width: 80rpx; font-size: 22rpx; color: #8A90A8; flex-shrink: 0; }
.draft-input { flex: 1; height: 60rpx; background: #FFF; border: 1rpx solid #E9E6F4;
  border-radius: 12rpx; padding: 0 14rpx; font-size: 25rpx; color: #3A3F58; }
.draft-unit { font-size: 21rpx; color: #8A90A8; }
.draft-picker { flex: 1; }
.picker-box { height: 60rpx; line-height: 60rpx; background: #FFF; border: 1rpx solid #E9E6F4;
  border-radius: 12rpx; padding: 0 14rpx; font-size: 24rpx; color: #3A3F58; }
.arrow { float: right; color: #A6AAC2; }
.draft-content { width: 100%; min-height: 100rpx; background: #FFF; border: 1rpx solid #E9E6F4;
  border-radius: 12rpx; padding: 12rpx; font-size: 24rpx; box-sizing: border-box; margin-top: 8rpx; }
.draft-actions { display: flex; align-items: center; justify-content: space-between; gap: 12rpx;
  margin-top: 12rpx; }
.muted { font-size: 20rpx; color: #A6AAC2; }
.note-input { width: 100%; min-height: 180rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 16rpx; padding: 16rpx; font-size: 25rpx; box-sizing: border-box; margin-bottom: 14rpx; }
.summary-text { display: block; margin-top: 18rpx; background: #FAF9FF; border-radius: 16rpx;
  padding: 18rpx; font-size: 25rpx; color: #4A4F6B; line-height: 1.8; }
.empty-box { margin-top: 18rpx; text-align: center; font-size: 23rpx; color: #8A90A8; }
.sheet-links { display: flex; gap: 24rpx; margin-top: 24rpx; padding-top: 18rpx;
  border-top: 1rpx dashed #F0EDF8; }
.link { font-size: 23rpx; color: #6C7BF5; }
</style>
