<script setup>
import { computed, ref } from 'vue'
import { onPullDownRefresh, onShow } from '@dcloudio/uni-app'
import {
  apiAddAssetAccount, apiAddAssetLiability, apiAdjustAssetAccount,
  apiAdjustAssetLiability, apiAssetOverview, apiAssetTransactions,
  apiDeleteAssetAccount, apiDeleteAssetLiability, apiRepayAssetLiability,
  apiAssetTransfer, apiUpdateAssetAccount, apiUpdateAssetLiability,
} from '../../api/assets.js'
import {
  assetMeta, fmtMoney, liabilityMeta, txLabel,
} from '../../common/asset-meta.js'
import AssetFormSheet from '../../components/assets/asset-form-sheet.vue'
import store from '../../store/user.js'

const overview = ref({})
const loading = ref(false)
const error = ref(null)
const activeTab = ref('accounts')
const hideAmounts = ref(false)

const transactions = ref([])
const txTotal = ref(0)
const txPage = ref(1)
const txLoading = ref(false)
const txAccountId = ref(null)
const txType = ref('')

const sheetVisible = ref(false)
const sheetKind = ref('account')
const sheetItem = ref(null)
const saving = ref(false)

const accounts = computed(() => {
  const order = ['cash', 'bank', 'wechat', 'alipay', 'savings', 'other']
  return [...(overview.value.accounts || [])].sort(
    (a, b) => order.indexOf(a.type) - order.indexOf(b.type))
})
const liabilities = computed(() => overview.value.liabilities || [])
const hasMoreTx = computed(() => transactions.value.length < txTotal.value)
const activeAccounts = computed(() => accounts.value.filter(a => a.is_active !== false))

function hideKey() {
  return `asset_hide_${store.user?.id || 'guest'}`
}

function loadHide() {
  hideAmounts.value = !!uni.getStorageSync(hideKey())
}

function toggleHide() {
  hideAmounts.value = !hideAmounts.value
  uni.setStorageSync(hideKey(), hideAmounts.value)
}

function money(value) {
  if (hideAmounts.value) return '••••••'
  return '¥' + fmtMoney(value)
}

function plain(value) {
  return hideAmounts.value ? '••••' : '¥' + fmtMoney(value)
}

function shortTime(value) {
  if (!value) return '暂无记录'
  return String(value).slice(0, 16).replace('T', ' ')
}

function typeLabel(a) {
  return assetMeta(a.type).label
}

function debtTypeLabel(l) {
  return liabilityMeta(l.type).label
}

function dueText(l) {
  if (l.status === 'repaid' || Number(l.outstanding || 0) <= 0) return '已还清'
  if (!l.due_date) return '未设置还款日'
  if (l.is_overdue) return `已逾期 ${Math.abs(Number(l.days_left || 0))} 天`
  if (Number(l.days_left) === 0) return '今天还款'
  if (Number(l.days_left) > 0) return `${l.days_left} 天后还款`
  return l.due_date
}

function dueClass(l) {
  if (l.status === 'repaid') return 'due-done'
  if (l.is_overdue) return 'due-over'
  if (Number(l.days_left) <= 3) return 'due-soon'
  return ''
}

async function load() {
  loading.value = true
  error.value = null
  try {
    overview.value = await apiAssetOverview()
    if (activeTab.value === 'transactions') await loadTransactions(true)
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

async function loadTransactions(reset = true) {
  if (reset) {
    txPage.value = 1
    transactions.value = []
  }
  txLoading.value = true
  try {
    const params = {
      page: txPage.value,
      page_size: 20,
    }
    if (txAccountId.value != null) params.account_id = txAccountId.value
    if (txType.value) params.type = txType.value
    const res = await apiAssetTransactions(params)
    const items = res.items || []
    transactions.value = reset ? items : transactions.value.concat(items)
    txTotal.value = res.total || 0
  } catch (e) {
    error.value = e
  } finally {
    txLoading.value = false
  }
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'transactions') loadTransactions(true)
}

function filterByAccount(account) {
  txAccountId.value = account.id
  activeTab.value = 'transactions'
  loadTransactions(true)
}

function clearTxFilter() {
  txAccountId.value = null
  loadTransactions(true)
}

function loadMoreTx() {
  if (!hasMoreTx.value || txLoading.value) return
  txPage.value += 1
  loadTransactions(false)
}

function openAccountCreate() {
  sheetKind.value = 'account'
  sheetItem.value = null
  sheetVisible.value = true
}

function openAccountEdit(item) {
  sheetKind.value = 'editAccount'
  sheetItem.value = item
  sheetVisible.value = true
}

function openBalance(item) {
  sheetKind.value = 'balance'
  sheetItem.value = item
  sheetVisible.value = true
}

function openLiabilityCreate() {
  sheetKind.value = 'liability'
  sheetItem.value = null
  sheetVisible.value = true
}

function openLiabilityEdit(item) {
  sheetKind.value = 'editLiability'
  sheetItem.value = item
  sheetVisible.value = true
}

function openRepay(item) {
  sheetKind.value = 'repay'
  sheetItem.value = item
  sheetVisible.value = true
}

function openAdjust(item) {
  sheetKind.value = 'adjust'
  sheetItem.value = item
  sheetVisible.value = true
}

function openTransfer() {
  if (activeAccounts.value.length < 2) {
    uni.showToast({ title: '至少需要两个账户才能转账', icon: 'none' })
    return
  }
  sheetKind.value = 'transfer'
  sheetItem.value = null
  sheetVisible.value = true
}

function closeSheet() {
  if (saving.value) return
  sheetVisible.value = false
  sheetItem.value = null
}

async function submitSheet(payload) {
  saving.value = true
  try {
    if (sheetKind.value === 'account') {
      await apiAddAssetAccount(payload)
      toast('账户已创建')
    } else if (sheetKind.value === 'editAccount') {
      await apiUpdateAssetAccount(sheetItem.value.id, payload)
      toast('账户已更新')
    } else if (sheetKind.value === 'balance') {
      await apiAdjustAssetAccount(sheetItem.value.id, payload)
      toast('余额已调整')
    } else if (sheetKind.value === 'liability') {
      await apiAddAssetLiability(payload)
      toast('负债已创建')
    } else if (sheetKind.value === 'editLiability') {
      await apiUpdateAssetLiability(sheetItem.value.id, payload)
      toast('负债已更新')
    } else if (sheetKind.value === 'repay') {
      await apiRepayAssetLiability(sheetItem.value.id, payload)
      toast('还款已记录')
    } else if (sheetKind.value === 'adjust') {
      await apiAdjustAssetLiability(sheetItem.value.id, payload)
      toast('欠款已调整')
    } else if (sheetKind.value === 'transfer') {
      await apiAssetTransfer(payload)
      toast('转账已完成，不计入消费')
    }
    sheetVisible.value = false
    sheetItem.value = null
    await load()
  } catch (e) {
    /* 统一请求层已提示，保留弹层让用户修改 */
  } finally {
    saving.value = false
  }
}

function toast(title) {
  uni.showToast({ title, icon: 'none' })
}

function deleteAccount(item) {
  uni.showModal({
    title: '删除账户',
    content: `确定删除「${item.name}」吗？有历史流水时会停用并保留记录，避免审计丢失。`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        const result = await apiDeleteAssetAccount(item.id)
        toast(result.message || (result.archived ? '账户已停用' : '账户已删除'))
        await load()
      } catch (e) { /* 统一提示 */ }
    },
  })
}

function deleteLiability(item) {
  uni.showModal({
    title: '删除负债',
    content: `确定删除「${item.name}」吗？有还款记录时会停用并保留记录。`,
    success: async (res) => {
      if (!res.confirm) return
      try {
        const result = await apiDeleteAssetLiability(item.id)
        toast(result.message || (result.archived ? '负债已停用' : '负债已删除'))
        await load()
      } catch (e) { /* 统一提示 */ }
    },
  })
}

function txTone(tx) {
  if (tx.liability_id) return tx.direction === 'in' ? 'tone-warn' : 'tone-in'
  if (tx.type === 'transfer_out') return 'tone-neutral'
  if (tx.type === 'transfer_in') return 'tone-neutral'
  return tx.direction === 'in' ? 'tone-in' : 'tone-out'
}

function txSign(tx) {
  return tx.direction === 'in' ? '+' : '-'
}

function sourceLabel(source) {
  return { manual: '手动', bill: '账单', subscription: '订阅', import: '导入', agent: 'Agent' }[source] || source || ''
}

function refresh() {
  load()
}

loadHide()
onShow(load)
onPullDownRefresh(async () => {
  await load()
  uni.stopPullDownRefresh()
})
</script>

<template>
  <view class="page">
    <!-- 总览 -->
    <view class="summary-card">
      <view class="summary-head">
        <view class="summary-title">
          <image class="summary-icon" src="/static/icons/act_wallet.png" mode="widthFix" />
          <text>个人资产</text>
        </view>
        <text class="eye-btn" @click="toggleHide">{{ hideAmounts ? '显示金额' : '隐藏金额' }}</text>
      </view>
      <view class="net-block">
        <text class="net-label">净资产</text>
        <text class="net-value">{{ money(overview.net_worth) }}</text>
      </view>
      <view class="summary-grid">
        <view class="summary-cell">
          <text class="cell-label">总资产</text>
          <text class="cell-value">{{ money(overview.total_assets) }}</text>
        </view>
        <view class="summary-divider" />
        <view class="summary-cell">
          <text class="cell-label">总负债</text>
          <text class="cell-value debt">{{ money(overview.total_liabilities) }}</text>
        </view>
      </view>
      <view class="summary-foot">
        <text>最近更新：{{ shortTime(overview.last_updated_at) }}</text>
        <text>手动维护</text>
      </view>
    </view>
    <text class="disclaimer">仅记录你手动维护的账户，不连接真实银行、微信或支付宝账户。</text>

    <!-- 分段 -->
    <view class="tabs">
      <text :class="['tab', activeTab === 'accounts' && 'tab-on']" @click="switchTab('accounts')">
        资产账户 {{ accounts.length }}
      </text>
      <text :class="['tab', activeTab === 'liabilities' && 'tab-on']" @click="switchTab('liabilities')">
        负债 {{ liabilities.length }}
      </text>
      <text :class="['tab', activeTab === 'transactions' && 'tab-on']" @click="switchTab('transactions')">
        变动记录
      </text>
    </view>

    <view v-if="error" class="card error-card">
      <text class="error-text">{{ error.message || '加载失败，请稍后重试' }}</text>
      <button class="btn btn-outline retry-btn" @click="refresh">重新加载</button>
    </view>
    <view v-if="loading && !overview.has_data" class="card loading-card">正在读取资产数据…</view>

    <!-- 资产账户 -->
    <block v-if="activeTab === 'accounts'">
      <view class="section-head">
        <view>
          <text class="section-title">资产账户</text>
          <text class="section-sub">余额变动会留下流水</text>
        </view>
        <view class="head-actions">
          <text v-if="activeAccounts.length >= 2" class="head-action" @click="openTransfer">转账</text>
          <text class="head-action primary" @click="openAccountCreate">＋ 账户</text>
        </view>
      </view>

      <view v-if="!accounts.length && !loading" class="card empty-card">
        <text class="empty-title">还没有资产账户</text>
        <text class="empty-sub">添加银行卡、微信零钱或现金，开始看净资产。</text>
        <button class="btn btn-primary empty-btn" @click="openAccountCreate">添加第一个账户</button>
      </view>

      <view class="card account-card" v-for="a in accounts" :key="a.id">
        <view class="account-top">
          <view class="type-icon" :style="{ background: assetMeta(a.type).bg }">
            <text>{{ assetMeta(a.type).icon }}</text>
          </view>
          <view class="account-main">
            <view class="row-between">
              <text class="item-name">{{ a.name }}</text>
              <text class="item-amount">{{ money(a.balance) }}</text>
            </view>
            <view class="meta-row">
              <text class="type-chip" :style="{ color: assetMeta(a.type).color, background: assetMeta(a.type).bg }">
                {{ typeLabel(a) }}
              </text>
              <text v-if="a.institution" class="meta-text">{{ a.institution }}</text>
              <text v-if="a.account_hint" class="meta-text">尾号 {{ a.account_hint }}</text>
            </view>
            <text class="time-text">更新于 {{ shortTime(a.updated_at) }}</text>
          </view>
        </view>
        <view class="row-actions">
          <text @click="openBalance(a)">调余额</text>
          <text @click="openAccountEdit(a)">编辑</text>
          <text @click="filterByAccount(a)">明细</text>
          <text class="danger" @click="deleteAccount(a)">删除</text>
        </view>
      </view>
    </block>

    <!-- 负债 -->
    <block v-if="activeTab === 'liabilities'">
      <view class="section-head">
        <view>
          <text class="section-title">负债管理</text>
          <text class="section-sub">还款会同时减少账户余额</text>
        </view>
        <text class="head-action primary" @click="openLiabilityCreate">＋ 负债</text>
      </view>

      <view v-if="!liabilities.length && !loading" class="card empty-card">
        <text class="empty-title">还没有登记负债</text>
        <text class="empty-sub">信用卡、分期或个人借款可以在这里统一管理。</text>
        <button class="btn btn-primary empty-btn" @click="openLiabilityCreate">添加负债</button>
      </view>

      <view class="card account-card" v-for="l in liabilities" :key="l.id">
        <view class="account-top">
          <view class="type-icon" :style="{ background: liabilityMeta(l.type).bg }">
            <text>{{ liabilityMeta(l.type).icon }}</text>
          </view>
          <view class="account-main">
            <view class="row-between">
              <text class="item-name">{{ l.name }}</text>
              <text class="item-amount debt">{{ money(l.outstanding) }}</text>
            </view>
            <view class="meta-row">
              <text class="type-chip" :style="{ color: liabilityMeta(l.type).color, background: liabilityMeta(l.type).bg }">
                {{ debtTypeLabel(l) }}
              </text>
              <text :class="['due-chip', dueClass(l)]">{{ dueText(l) }}</text>
            </view>
            <text v-if="l.remark" class="time-text">{{ l.remark }}</text>
            <text class="time-text">更新于 {{ shortTime(l.updated_at) }}</text>
          </view>
        </view>
        <view class="row-actions">
          <text v-if="l.status !== 'repaid' && Number(l.outstanding) > 0" @click="openRepay(l)">还款</text>
          <text @click="openAdjust(l)">调整欠款</text>
          <text @click="openLiabilityEdit(l)">编辑</text>
          <text class="danger" @click="deleteLiability(l)">删除</text>
        </view>
      </view>
    </block>

    <!-- 变动记录 -->
    <block v-if="activeTab === 'transactions'">
      <view class="section-head">
        <view>
          <text class="section-title">资产变动记录</text>
          <text class="section-sub">转账不计入消费支出</text>
        </view>
        <text v-if="txAccountId != null" class="head-action" @click="clearTxFilter">全部账户</text>
      </view>

      <view v-if="txAccountId != null" class="filter-chip">
        <text>筛选账户：{{ (accounts.find(a => a.id === txAccountId) || {}).name || txAccountId }}</text>
      </view>

      <view v-if="!transactions.length && !txLoading" class="card empty-card">
        <text class="empty-title">还没有变动记录</text>
        <text class="empty-sub">新增账户、调整余额或关联账单后，这里会出现流水。</text>
      </view>
      <view v-if="txLoading && !transactions.length" class="card loading-card">正在读取变动记录…</view>

      <view class="card tx-list" v-if="transactions.length">
        <view class="tx-row" v-for="t in transactions" :key="t.id">
          <view :class="['tx-icon', txTone(t)]">
            {{ t.direction === 'in' ? '↑' : '↓' }}
          </view>
          <view class="tx-main">
            <view class="row-between">
              <text class="item-name">{{ txLabel(t.type) }}</text>
              <text :class="['tx-amount', txTone(t)]">{{ txSign(t) }}{{ plain(t.amount) }}</text>
            </view>
            <text class="meta-text">
              {{ t.account_name || t.liability_name || '资产变动' }}
              <text v-if="t.note"> · {{ t.note }}</text>
            </text>
            <text class="time-text">
              {{ shortTime(t.created_at) }} · {{ plain(t.before_amount) }} → {{ plain(t.after_amount) }}
              <text v-if="sourceLabel(t.source)"> · {{ sourceLabel(t.source) }}</text>
            </text>
          </view>
        </view>
      </view>

      <view v-if="hasMoreTx" class="load-more" @click="loadMoreTx">
        {{ txLoading ? '加载中…' : '加载更多' }}
      </view>
    </block>

    <AssetFormSheet
      :visible="sheetVisible"
      :kind="sheetKind"
      :item="sheetItem"
      :accounts="activeAccounts"
      :saving="saving"
      @close="closeSheet"
      @submit="submitSheet"
    />
  </view>
</template>

<style scoped>
.page { padding: 20rpx 24rpx 60rpx; }
.summary-card { position: relative; overflow: hidden; border-radius: 34rpx; padding: 30rpx;
  background: linear-gradient(135deg, #7568D8 0%, #8C7BF2 48%, #A99AF8 100%);
  box-shadow: 0 16rpx 38rpx rgba(108, 92, 210, .28); color: #fff; }
.summary-card::after { content: ''; position: absolute; right: -80rpx; top: -100rpx;
  width: 280rpx; height: 280rpx; border-radius: 50%; background: rgba(255, 255, 255, .10); }
.summary-head { display: flex; align-items: center; justify-content: space-between; position: relative; z-index: 1; }
.summary-title { display: flex; align-items: center; gap: 12rpx; font-size: 28rpx; font-weight: 700; }
.summary-icon { width: 48rpx; height: 48rpx; }
.eye-btn { font-size: 22rpx; color: rgba(255, 255, 255, .82); background: rgba(255, 255, 255, .16);
  border-radius: 999rpx; padding: 8rpx 18rpx; }
.net-block { position: relative; z-index: 1; margin: 26rpx 0 24rpx; }
.net-label { display: block; font-size: 23rpx; color: rgba(255, 255, 255, .72); }
.net-value { display: block; font-size: 62rpx; font-weight: 800; letter-spacing: 1rpx; margin-top: 6rpx; }
.summary-grid { position: relative; z-index: 1; display: flex; align-items: center;
  background: rgba(255, 255, 255, .14); border-radius: 22rpx; padding: 20rpx 8rpx; }
.summary-cell { flex: 1; text-align: center; min-width: 0; }
.cell-label { display: block; font-size: 22rpx; color: rgba(255, 255, 255, .70); }
.cell-value { display: block; font-size: 29rpx; font-weight: 700; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cell-value.debt { color: #FFE0E0; }
.summary-divider { width: 1rpx; height: 50rpx; background: rgba(255, 255, 255, .22); }
.summary-foot { position: relative; z-index: 1; display: flex; justify-content: space-between;
  font-size: 21rpx; color: rgba(255, 255, 255, .66); margin-top: 20rpx; }
.disclaimer { display: block; font-size: 21rpx; color: #A6AAC2; line-height: 1.6;
  margin: 16rpx 8rpx 0; }

.tabs { display: flex; gap: 12rpx; margin: 24rpx 0 8rpx; }
.tab { flex: 1; text-align: center; font-size: 25rpx; color: #8A90A8; background: #F6F4FB;
  border-radius: 999rpx; padding: 14rpx 0; }
.tab-on { background: #6C7BF5; color: #fff; font-weight: 700; box-shadow: 0 8rpx 18rpx rgba(108, 123, 245, .22); }

.section-head { display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16rpx; margin: 24rpx 6rpx 14rpx; }
.section-title { display: block; font-size: 31rpx; font-weight: 800; color: #3A3F58; }
.section-sub { display: block; font-size: 21rpx; color: #A6AAC2; margin-top: 4rpx; }
.head-actions { display: flex; align-items: center; gap: 12rpx; flex-shrink: 0; }
.head-action { font-size: 24rpx; color: #6C7BF5; background: #EFF1FF; border-radius: 999rpx;
  padding: 8rpx 18rpx; }
.head-action.primary { background: linear-gradient(135deg, #7C8BFF, #A78BFA); color: #fff; font-weight: 700; }

.error-card { border: 1rpx solid #FFD2D2; background: #FFF7F7; }
.loading-card { text-align: center; font-size: 25rpx; color: #A6AAC2; padding: 38rpx 20rpx; }
.error-text { display: block; font-size: 25rpx; color: #C94F4F; line-height: 1.6; }
.retry-btn { margin-top: 16rpx; height: 70rpx; font-size: 25rpx; }

.empty-card { text-align: center; padding: 48rpx 30rpx; }
.empty-title { display: block; font-size: 29rpx; font-weight: 700; color: #3A3F58; }
.empty-sub { display: block; font-size: 23rpx; color: #A6AAC2; line-height: 1.7; margin-top: 10rpx; }
.empty-btn { margin: 24rpx auto 0; width: 320rpx; height: 76rpx; font-size: 26rpx; }

.account-card { padding: 24rpx 24rpx 18rpx; }
.account-top { display: flex; align-items: flex-start; gap: 18rpx; }
.type-icon { width: 82rpx; height: 82rpx; border-radius: 26rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 38rpx; }
.account-main { flex: 1; min-width: 0; }
.row-between { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.item-name { font-size: 30rpx; font-weight: 700; color: #3A3F58; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.item-amount { font-size: 32rpx; font-weight: 800; color: #3A3F58; flex-shrink: 0; }
.item-amount.debt { color: #E45858; }
.meta-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8rpx; margin-top: 10rpx; }
.type-chip { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; font-weight: 600; }
.due-chip { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx;
  background: #F6F4FB; color: #8A90A8; }
.due-over { background: #FFEDEE; color: #E45858; }
.due-soon { background: #FFF6E7; color: #D98A32; }
.due-done { background: #E9F8F2; color: #1FA97F; }
.meta-text { display: block; font-size: 22rpx; color: #8A90A8; margin-top: 6rpx;
  line-height: 1.5; word-break: break-word; }
.time-text { display: block; font-size: 20rpx; color: #B0B4C8; margin-top: 6rpx; }
.row-actions { display: flex; justify-content: flex-end; gap: 20rpx; margin-top: 16rpx;
  padding-top: 14rpx; border-top: 1rpx dashed #F0EDF8; font-size: 23rpx; color: #6C7BF5; }
.row-actions .danger { color: #D98A8A; }

.filter-chip { display: inline-flex; align-items: center; gap: 8rpx; margin: 0 6rpx 14rpx;
  background: #EFF1FF; color: #5A54B8; border-radius: 999rpx; padding: 8rpx 18rpx; font-size: 22rpx; }
.tx-list { padding: 4rpx 24rpx; }
.tx-row { display: flex; align-items: flex-start; gap: 16rpx; padding: 20rpx 0;
  border-bottom: 1rpx dashed #F0EDF8; }
.tx-row:last-child { border-bottom: none; }
.tx-icon { width: 54rpx; height: 54rpx; border-radius: 18rpx; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 28rpx; font-weight: 800; }
.tx-main { flex: 1; min-width: 0; }
.tx-amount { font-size: 28rpx; font-weight: 800; flex-shrink: 0; }
.tone-in { background: #E9F8F2; color: #1FA97F; }
.tone-out { background: #FFEDEE; color: #E45858; }
.tone-warn { background: #FFF6E7; color: #D98A32; }
.tone-neutral { background: #EFF1FF; color: #6C7BF5; }
.tx-amount.tone-in, .tx-amount.tone-out, .tx-amount.tone-warn, .tx-amount.tone-neutral {
  background: transparent; }
.tx-amount.tone-out { color: #E45858; }
.tx-amount.tone-in { color: #1FA97F; }
.tx-amount.tone-warn { color: #D98A32; }
.tx-amount.tone-neutral { color: #6C7BF5; }
.load-more { text-align: center; font-size: 24rpx; color: #8A90A8; padding: 24rpx; }
</style>
