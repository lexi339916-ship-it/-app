<script setup>
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  apiCsvTemplate, apiPreviewCsvText, apiPreviewCsvFile, apiConfirmCsv,
} from '../../api/imports.js'

const text = ref('')
const filename = ref('')
const preview = ref(null)
const importing = ref(false)
const previewing = ref(false)
const error = ref(null)
const imported = ref(null)

const rows = computed(() => preview.value?.rows || [])
const selectedRows = computed(() => rows.value.filter(r => r.include))
const canConfirm = computed(() => selectedRows.value.length > 0 && !importing.value)

function money(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(2)
}

function typeText(type) {
  return type === 'income' ? '收入' : '支出'
}

function toggle(row) {
  if (row.errors && row.errors.length) return
  row.include = !row.include
}

function selectAll() {
  rows.value.forEach(row => {
    if (!(row.errors && row.errors.length)) row.include = true
  })
}

function clearAll() {
  rows.value.forEach(row => { row.include = false })
}

async function fillSample() {
  try {
    const res = await apiCsvTemplate()
    text.value = res.csv || ''
    filename.value = '示例账单.csv'
    preview.value = null
    imported.value = null
  } catch (e) {
    error.value = e
  }
}

async function doPreview() {
  if (!text.value.trim()) {
    uni.showToast({ title: '先粘贴 CSV 内容或选择文件', icon: 'none' })
    return
  }
  previewing.value = true
  error.value = null
  imported.value = null
  try {
    preview.value = await apiPreviewCsvText(text.value, filename.value || 'paste.csv')
  } catch (e) {
    error.value = e
  } finally {
    previewing.value = false
  }
}

function chooseFile() {
  if (!uni.chooseFile) {
    uni.showToast({ title: '当前环境请直接粘贴 CSV 文本', icon: 'none' })
    return
  }
  uni.chooseFile({
    count: 1,
    extension: ['.csv', '.txt'],
    success: async (res) => {
      const path = res.tempFilePaths && res.tempFilePaths[0]
      if (!path) return
      const file = (res.tempFiles && res.tempFiles[0]) || {}
      filename.value = file.name || 'upload.csv'
      previewing.value = true
      error.value = null
      imported.value = null
      try {
        preview.value = await apiPreviewCsvFile(path, filename.value)
        text.value = ''
      } catch (e) {
        error.value = e
      } finally {
        previewing.value = false
      }
    },
    fail: () => {
      uni.showToast({ title: '未选择文件，可直接粘贴 CSV', icon: 'none' })
    },
  })
}

async function confirmImport() {
  if (!canConfirm.value) return
  importing.value = true
  error.value = null
  try {
    const payload = selectedRows.value.map(row => ({
      row_no: row.row_no,
      bill_date: row.bill_date,
      amount: String(row.amount),
      type: row.type,
      category: row.category,
      remark: row.remark,
      pay_channel: row.pay_channel,
      funding_account: row.funding_account,
    }))
    imported.value = await apiConfirmCsv(payload, preview.value?.filename || filename.value)
    rows.value.forEach(row => { row.include = false })
    uni.showToast({ title: '导入完成', icon: 'none' })
  } catch (e) {
    error.value = e
  } finally {
    importing.value = false
  }
}

function reset() {
  text.value = ''
  filename.value = ''
  preview.value = null
  imported.value = null
  error.value = null
}

onLoad((options) => {
  if (options && options.pick === '1') {
    setTimeout(() => chooseFile(), 300)
  }
})
</script>

<template>
  <view class="page">
    <view class="hero">
      <text class="hero-title">CSV 账单导入</text>
      <text class="hero-sub">微信 / 支付宝 / 通用表头 · 先预览去重，再确认写入</text>
    </view>

    <view class="card">
      <view class="row-between">
        <text class="card-title no-margin">选择数据</text>
        <text class="link" @click="fillSample">填入示例</text>
      </view>
      <view class="file-row">
        <button class="btn ghost small" @click="chooseFile">选择 CSV 文件</button>
        <text class="file-name">{{ filename || '未选择文件，可直接粘贴' }}</text>
      </view>
      <textarea class="csv-input" v-model="text" :maxlength="200000"
        placeholder="把 CSV 内容粘贴到这里，例如：&#10;日期,金额,类型,分类,备注&#10;2026-11-01,32.50,支出,餐饮,午饭"
        placeholder-class="ph" auto-height />
      <view class="action-row">
        <button class="btn primary" :class="{ 'btn-off': previewing }" :disabled="previewing" @click="doPreview">
          {{ previewing ? '解析中…' : '解析预览' }}
        </button>
        <button class="btn ghost" @click="reset">清空</button>
      </view>
      <text class="hint">支持 UTF-8 / GBK；单文件 ≤5MB；金额、日期无法识别的行会标红，不会导入。</text>
    </view>

    <view v-if="error" class="card state-error">
      <text class="state-title">操作失败</text>
      <text class="state-text">{{ error.message || '请检查 CSV 格式后重试' }}</text>
    </view>

    <template v-if="preview">
      <view class="card">
        <view class="row-between">
          <text class="card-title no-margin">预览结果</text>
          <text class="muted">{{ preview.filename || '粘贴内容' }}</text>
        </view>
        <view class="metric-grid">
          <view class="metric">
            <text class="metric-label">总行数</text>
            <text class="metric-value">{{ preview.total_rows }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">可导入</text>
            <text class="metric-value income">{{ preview.valid_rows - preview.duplicate_rows }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">重复</text>
            <text class="metric-value warn">{{ preview.duplicate_rows }}</text>
          </view>
          <view class="metric">
            <text class="metric-label">错误</text>
            <text class="metric-value expense">{{ preview.error_rows }}</text>
          </view>
        </view>
        <view class="total-row">
          <text>收入合计 ¥{{ money(preview.income_total) }}</text>
          <text>支出合计 ¥{{ money(preview.expense_total) }}</text>
          <text class="muted">编码 {{ preview.encoding }}</text>
        </view>
        <text class="notice" v-if="preview.notice">{{ preview.notice }}</text>
        <view class="select-row">
          <text class="link" @click="selectAll">全选可导入</text>
          <text class="link" @click="clearAll">取消全选</text>
          <text class="selected-count">已选 {{ selectedRows.length }} 笔</text>
        </view>
      </view>

      <view class="card">
        <text class="card-title">逐行确认</text>
        <view class="csv-row" v-for="row in rows" :key="row.row_no"
          :class="{ 'row-disabled': row.errors && row.errors.length }">
          <view class="check" :class="{ checked: row.include, disabled: row.errors && row.errors.length }"
            @click="toggle(row)">✓</view>
          <view class="row-main">
            <view class="row-line">
              <text class="row-date">{{ row.bill_date || row.raw_date || '日期无法识别' }}</text>
              <text :class="['row-amount', row.type === 'income' ? 'income' : 'expense']">
                {{ row.type === 'income' ? '+' : '-' }}¥{{ money(row.amount) }}
              </text>
            </view>
            <text class="row-desc">{{ row.category }} · {{ row.remark || '无备注' }}</text>
            <view class="row-tags">
              <text class="tag">{{ typeText(row.type) }}</text>
              <text class="tag" v-if="row.pay_channel">{{ row.pay_channel }}</text>
              <text class="tag" v-if="row.funding_account">{{ row.funding_account }}</text>
              <text class="tag warn" v-if="row.duplicate">{{ row.duplicate_reason }}</text>
              <text class="tag error" v-for="e in row.errors" :key="e">{{ e }}</text>
            </view>
          </view>
          <text class="row-no">#{{ row.row_no }}</text>
        </view>
      </view>

      <view class="card confirm-card">
        <view class="confirm-info">
          <text class="confirm-title">确认导入 {{ selectedRows.length }} 笔</text>
          <text class="confirm-sub">重复行会自动跳过；导入后可在账单页查看，source=csv。</text>
        </view>
        <button class="btn primary" :class="{ 'btn-off': !canConfirm }" :disabled="!canConfirm" @click="confirmImport">
          {{ importing ? '导入中…' : `确认导入 ${selectedRows.length} 笔` }}
        </button>
      </view>
    </template>

    <view v-if="imported" class="card success-card">
      <text class="success-title">导入完成</text>
      <text class="success-line">成功导入 {{ imported.imported_count }} 笔</text>
      <text class="success-line">跳过重复 {{ imported.skipped_duplicates }} 笔</text>
      <text class="success-line" v-if="imported.failed_count">失败 {{ imported.failed_count }} 笔</text>
      <text class="success-line">收入 ¥{{ money(imported.income_total) }} · 支出 ¥{{ money(imported.expense_total) }}</text>
      <text class="success-error" v-for="e in imported.errors" :key="e">{{ e }}</text>
      <button class="btn ghost small" @click="reset">再导入一份</button>
    </view>

    <view class="footer-note">
      <text>只解析你主动上传的 CSV，不联网读取任何平台；导入前请核对预览。</text>
    </view>
  </view>
</template>

<style scoped>
.page { padding: 18rpx 24rpx 80rpx; }
.hero { padding: 18rpx 8rpx 20rpx; }
.hero-title { display: block; font-size: 40rpx; font-weight: 800; color: #5A54B8; letter-spacing: 1rpx; }
.hero-sub { display: block; font-size: 23rpx; color: #8A90A8; margin-top: 6rpx; line-height: 1.6; }

.card { background: #FFFDF8; border-radius: 28rpx; padding: 26rpx; margin-bottom: 22rpx;
  box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .08); border: 1rpx solid #F0EDF8; }
.card-title { display: block; font-size: 30rpx; font-weight: 800; color: #3A3F58; margin-bottom: 16rpx; }
.no-margin { margin-bottom: 0; }
.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.muted { font-size: 22rpx; color: #A6AAC2; }
.link { font-size: 23rpx; color: #6C7BF5; }
.file-row { display: flex; align-items: center; gap: 14rpx; margin: 16rpx 0; }
.file-name { flex: 1; font-size: 22rpx; color: #8A90A8; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.csv-input { width: 100%; min-height: 220rpx; background: #FAF9FF; border: 1rpx solid #E9E6F4;
  border-radius: 18rpx; padding: 18rpx; font-size: 24rpx; box-sizing: border-box; }
.ph { color: #C3C7DA; }
.action-row { display: flex; gap: 14rpx; margin-top: 18rpx; }
.btn { flex: 1; margin: 0; height: 80rpx; line-height: 80rpx; border-radius: 22rpx;
  font-size: 27rpx; font-weight: 700; }
.btn.primary { color: #fff; background: linear-gradient(135deg, #7C8BFF 0%, #A78BFA 100%); }
.btn.ghost { color: #6C7BF5; background: #F2F1FF; }
.btn.small { flex: 0; height: 64rpx; line-height: 64rpx; font-size: 24rpx; padding: 0 24rpx; }
.btn-off { opacity: .55; }
.hint { display: block; font-size: 20rpx; color: #A6AAC2; line-height: 1.6; margin-top: 12rpx; }

.state-error { border-color: #FFD7D7; background: #FFF8F8; }
.state-title { display: block; font-size: 29rpx; font-weight: 800; color: #C94F4F; }
.state-text { display: block; font-size: 24rpx; color: #8A90A8; margin-top: 8rpx; line-height: 1.6; }

.metric-grid { display: flex; flex-wrap: wrap; gap: 12rpx; margin-top: 14rpx; }
.metric { width: calc(25% - 9rpx); background: #FAF9FF; border-radius: 16rpx; padding: 12rpx 10rpx;
  box-sizing: border-box; text-align: center; }
.metric-label { display: block; font-size: 20rpx; color: #8A90A8; }
.metric-value { display: block; font-size: 28rpx; font-weight: 800; color: #3A3F58; margin-top: 4rpx; }
.income { color: #1FA97F; }
.expense { color: #E45858; }
.warn { color: #D98A32; }
.total-row { display: flex; flex-wrap: wrap; gap: 18rpx; font-size: 22rpx; color: #5A5F78;
  margin-top: 14rpx; }
.notice { display: block; font-size: 21rpx; color: #A56A1F; background: #FFF6E7;
  border-radius: 12rpx; padding: 10rpx 12rpx; margin-top: 12rpx; line-height: 1.6; }
.select-row { display: flex; align-items: center; gap: 20rpx; margin-top: 14rpx; }
.selected-count { margin-left: auto; font-size: 22rpx; color: #6C7BF5; }

.csv-row { display: flex; align-items: flex-start; gap: 12rpx; padding: 14rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.csv-row:last-child { border-bottom: none; }
.row-disabled { opacity: .55; }
.check { width: 38rpx; height: 38rpx; line-height: 38rpx; border-radius: 10rpx; flex-shrink: 0;
  border: 2rpx solid #D9D3F5; color: transparent; text-align: center; font-size: 22rpx; margin-top: 4rpx; }
.check.checked { background: #6C7BF5; border-color: #6C7BF5; color: #fff; }
.check.disabled { background: #F4F2FA; border-color: #E4E2EE; }
.row-main { flex: 1; min-width: 0; }
.row-line { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.row-date { font-size: 23rpx; color: #5A5F78; }
.row-amount { font-size: 27rpx; font-weight: 800; }
.row-desc { display: block; font-size: 23rpx; color: #3A3F58; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-tags { display: flex; flex-wrap: wrap; gap: 8rpx; margin-top: 6rpx; }
.tag { font-size: 19rpx; color: #6B7089; background: #F4F2FA; border-radius: 999rpx; padding: 3rpx 10rpx; }
.tag.warn { background: #FFF6E7; color: #D98A32; }
.tag.error { background: #FFEDEE; color: #C94F4F; }
.row-no { font-size: 20rpx; color: #C3C7DA; flex-shrink: 0; }

.confirm-card { display: flex; align-items: center; gap: 18rpx; }
.confirm-info { flex: 1; min-width: 0; }
.confirm-title { display: block; font-size: 27rpx; font-weight: 800; color: #3A3F58; }
.confirm-sub { display: block; font-size: 21rpx; color: #8A90A8; margin-top: 4rpx; line-height: 1.5; }
.confirm-card .btn { flex: 0; padding: 0 24rpx; }

.success-card { background: #F4FCF8; border-color: #BFE9D8; }
.success-title { display: block; font-size: 30rpx; font-weight: 800; color: #1FA97F; }
.success-line { display: block; font-size: 24rpx; color: #4A4F6B; margin-top: 8rpx; }
.success-error { display: block; font-size: 21rpx; color: #C94F4F; margin-top: 4rpx; }
.success-card .btn { margin-top: 16rpx; }

.footer-note { padding: 8rpx 12rpx; font-size: 21rpx; color: #A6AAC2; line-height: 1.7; text-align: center; }
</style>
