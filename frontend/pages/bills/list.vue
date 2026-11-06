<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { apiBills, apiCategories, apiMonthlyStats } from '../../api/index.js'
import { categoryMeta, channelMeta } from '../../common/category-icons.js'
import { syncSubscriptions } from '../../common/subscription-notify.js'
import userState from '../../store/user.js'

// 本地日期（避免 toISOString 的 UTC 偏移）
const todayStr = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
  .toISOString().slice(0, 10)

const viewMode = ref('list')        // list 列表 / calendar 日历
const month = ref('')
const typeFilter = ref('')          // '' 全部 / expense / income
const subCount = ref(0)             // 进行中的订阅数（订阅同步接口返回）
const pageSize = 20

// 分类筛选
const categories = ref([])
const categoryId = ref(null)
const catOpen = ref(false)
const catLoading = ref(false)
const catError = ref('')
const recentIds = ref([])
let categoriesUserId = null

// 列表视图状态
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

// 日历视图状态
const monthDays = ref([])           // [{date, expense, income}]（当月每天）
const selectedDate = ref('')
const dayBills = ref([])
const dayLoading = ref(false)

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

function shiftMonth(m, delta) {
  const [y, mo] = m.split('-').map(Number)
  const d = new Date(y, mo - 1 + delta, 1)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

// 金额缩写：1 万以上显示 x.x万；整数不带小数，否则保留一位
function fmtAmount(v) {
  const n = Number(v)
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

// ---------- 日历网格 ----------
const expenseMax = computed(() =>
  Math.max(0, ...monthDays.value.map(d => Number(d.expense))))

const calCells = computed(() => {
  if (!monthDays.value.length) return []
  const [y, m] = month.value.split('-').map(Number)
  const lead = (new Date(y, m - 1, 1).getDay() + 6) % 7  // 周一开头
  const cells = []
  for (let i = 0; i < lead; i += 1) cells.push({ key: `b${i}`, blank: true })
  for (const d of monthDays.value) {
    const expense = Number(d.expense)
    const income = Number(d.income)
    cells.push({
      key: d.date,
      date: d.date,
      day: Number(d.date.slice(8)),
      expense,
      income,
      showExpense: expense > 0 && typeFilter.value !== 'income',
      showIncome: income > 0 && typeFilter.value !== 'expense',
      isToday: d.date === todayStr,
      selected: d.date === selectedDate.value,
      heat: expense > 0 && expenseMax.value > 0
        ? Math.min(0.16, 0.05 + 0.11 * (expense / expenseMax.value))
        : 0,
    })
  }
  while (cells.length % 7 !== 0) cells.push({ key: `e${cells.length}`, blank: true })
  // 手账贴纸感：交替轻微旋转 + 周末标记
  return cells.map((c, idx) => ({
    ...c,
    tilt: c.blank ? 0 : [(-0.9), 0, 0.9][idx % 3],
    isWeekend: !c.blank && (idx % 7 >= 5),
  }))
})

const monthSummary = computed(() => {
  let income = 0
  let expense = 0
  for (const d of monthDays.value) {
    income += Number(d.income)
    expense += Number(d.expense)
  }
  return { income, expense }
})

const selectedDayStat = computed(() =>
  monthDays.value.find(d => d.date === selectedDate.value) || { expense: 0, income: 0 })

const selectedDateLabel = computed(() => {
  if (!selectedDate.value) return ''
  const [y, m, d] = selectedDate.value.split('-').map(Number)
  const week = ['日', '一', '二', '三', '四', '五', '六'][new Date(y, m - 1, d).getDay()]
  return `${m}月${d}日 周${week}`
})

function defaultSelectedDate() {
  if (month.value === todayStr.slice(0, 7)) return todayStr
  const firstWithData = monthDays.value.find(d => Number(d.expense) > 0 || Number(d.income) > 0)
  return firstWithData ? firstWithData.date : `${month.value}-01`
}

// ---------- 分类筛选 ----------
const activeCategory = computed(() =>
  categories.value.find(c => c.id === categoryId.value) || null)
const activeCategoryName = computed(() => activeCategory.value?.name || '已选分类')
const expenseCategories = computed(() => categories.value.filter(c => c.type === 'expense'))
const incomeCategories = computed(() => categories.value.filter(c => c.type === 'income'))
const showExpenseGroup = computed(() => typeFilter.value !== 'income')
const showIncomeGroup = computed(() => typeFilter.value !== 'expense')
const recentCategories = computed(() => {
  const map = new Map(categories.value.map(c => [c.id, c]))
  return recentIds.value
    .map(id => map.get(id))
    .filter(c => c && (!typeFilter.value || c.type === typeFilter.value))
    .slice(0, 4)
})

function recentStorageKey() {
  return `bill_cat_recent_${userState.user?.id || 'guest'}`
}

function loadRecentCategories() {
  const saved = uni.getStorageSync(recentStorageKey())
  recentIds.value = Array.isArray(saved)
    ? saved.map(Number).filter(id => Number.isInteger(id)).slice(0, 6)
    : []
}

function rememberCategory(id) {
  recentIds.value = [id, ...recentIds.value.filter(x => x !== id)].slice(0, 6)
  uni.setStorageSync(recentStorageKey(), recentIds.value)
}

async function fetchCategories(force = false) {
  const uid = userState.user?.id || 0
  if (!force && categories.value.length && categoriesUserId === uid) return
  catLoading.value = true
  catError.value = ''
  try {
    const res = await apiCategories()
    categories.value = res.items || []
    categoriesUserId = uid
  } catch (e) {
    catError.value = '分类加载失败，点击重试'
  } finally {
    catLoading.value = false
  }
}

function openCat() {
  catOpen.value = true
  if (!categories.value.length && !catLoading.value) fetchCategories(true)
}

function closeCat() { catOpen.value = false }

function categoryParam() {
  return categoryId.value != null ? { category_id: categoryId.value } : {}
}

function reload() {
  if (viewMode.value === 'list') load(true)
  else loadDayBills()
}

function selectCategory(cat) {
  categoryId.value = cat ? cat.id : null
  if (cat) {
    if (typeFilter.value && cat.type !== typeFilter.value) typeFilter.value = cat.type
    rememberCategory(cat.id)
  }
  catOpen.value = false
  reload()
}

function clearCategory() {
  if (categoryId.value == null) return
  categoryId.value = null
  reload()
}

// ---------- 数据加载 ----------
async function loadDayBills() {
  if (!selectedDate.value) return
  dayLoading.value = true
  try {
    const res = await apiBills({
      start_date: selectedDate.value,
      end_date: selectedDate.value,
      type: typeFilter.value,
      ...categoryParam(),
      page: 1,
      page_size: 50,
    })
    dayBills.value = res.items
  } catch (e) { /* 统一提示 */ } finally { dayLoading.value = false }
}

async function load(reset = true) {
  if (reset) page.value = 1
  loading.value = true
  try {
    const stats = await apiMonthlyStats(month.value, categoryId.value)
    monthDays.value = stats.days
    if (viewMode.value === 'list') {
      const res = await apiBills({
        month: month.value,
        type: typeFilter.value,
        ...categoryParam(),
        page: page.value,
        page_size: pageSize,
      })
      items.value = reset ? res.items : items.value.concat(res.items)
      total.value = res.total
    } else {
      if (!selectedDate.value || !selectedDate.value.startsWith(month.value)) {
        selectedDate.value = defaultSelectedDate()
      }
      await loadDayBills()
    }
  } catch (e) { /* 统一提示 */ } finally { loading.value = false }
}

function toggleView() {
  viewMode.value = viewMode.value === 'list' ? 'calendar' : 'list'
  load(true)
}

function setType(t) {
  typeFilter.value = t
  // 类型切换后，若已选分类属于另一类型则自动清除，避免空结果
  if (t && activeCategory.value && activeCategory.value.type !== t) {
    categoryId.value = null
  }
  reload()
}

function prevMonth() { month.value = shiftMonth(month.value, -1); load(true) }
function nextMonth() { month.value = shiftMonth(month.value, 1); load(true) }

function loadMore() {
  if (items.value.length < total.value && !loading.value) {
    page.value += 1
    load(false)
  }
}

function goEdit(id, date) {
  let url = '/pages/bills/edit'
  if (id) url += '?id=' + id
  else if (date) url += '?date=' + date
  uni.navigateTo({ url })
}

function selectDay(cell) {
  if (cell.blank || !cell.date) return
  selectedDate.value = cell.date
  loadDayBills()
}

function goImport() { uni.navigateTo({ url: '/pages/import/import' }) }

function goSubscriptions() {
  uni.navigateTo({ url: '/pages/subscriptions/list' })
}

onShow(async () => {
  if (!month.value) month.value = currentMonth()
  loadRecentCategories()
  fetchCategories()
  // 先同步订阅（到达扣费日补生成账单），再统一拉一次列表，避免两次请求互相覆盖
  const res = await syncSubscriptions()
  if (res) subCount.value = res.active_count || 0
  load(true)
})
</script>

<template>
  <view class="page">
    <!-- 月份 / 视图切换 / 类型筛选 -->
    <view class="filter-bar">
      <view class="month-row">
        <view class="month-nav">
          <text class="arrow" @click="prevMonth">‹</text>
          <text class="month">{{ month }}</text>
          <text class="arrow" @click="nextMonth">›</text>
        </view>
        <text class="view-toggle" @click="toggleView">
          {{ viewMode === 'list' ? '▦ 日历' : '☰ 列表' }}
        </text>
      </view>
      <view class="type-tabs">
        <text :class="['tab', typeFilter === '' && 'tab-active']" @click="setType('')">全部</text>
        <text :class="['tab', typeFilter === 'expense' && 'tab-active']" @click="setType('expense')">支出</text>
        <text :class="['tab', typeFilter === 'income' && 'tab-active']" @click="setType('income')">收入</text>
      </view>
      <view class="filter-sub">
        <view class="filter-left">
          <view :class="['cat-filter', categoryId != null && 'cat-filter-on']" @click="openCat">
            <text class="cat-filter-ico">🏷️</text>
            <text class="cat-filter-name">{{ categoryId != null ? activeCategoryName : '全部分类' }}</text>
            <text v-if="categoryId == null" class="cat-filter-caret">▾</text>
          </view>
          <view v-if="categoryId != null" class="cat-filter-clear" @click="clearCategory">×</view>
        </view>
        <text class="filter-count" v-if="viewMode === 'list'">{{ total }} 笔</text>
      </view>
    </view>

    <!-- CSV 导入入口：账单页作为记录中心 -->
    <view class="sub-entry import-entry" @click="goImport">
      <image class="sub-entry-icon" src="/static/icons/act_note.png" mode="widthFix" />
      <view class="sub-entry-mid">
        <text class="sub-entry-title">导入 CSV 账单</text>
        <text class="sub-entry-sub">微信 / 支付宝 / 通用表头 · 预览去重后导入</text>
      </view>
      <text class="sub-entry-arrow">导入 ›</text>
    </view>

    <!-- 订阅管理入口（新增模块，原有记账流程不变） -->
    <view class="sub-entry" @click="goSubscriptions">
      <image class="sub-entry-icon" src="/static/icons/act_wallet.png" mode="widthFix" />
      <view class="sub-entry-mid">
        <text class="sub-entry-title">自动订阅扣费</text>
        <text class="sub-entry-sub">
          {{ subCount ? subCount + ' 项订阅进行中 · 到扣费日自动记账' : '房租、会员等固定支出自动记账' }}
        </text>
      </view>
      <text class="sub-entry-arrow">管理 ›</text>
    </view>

    <!-- ===== 列表视图 ===== -->
    <view class="list" v-if="viewMode === 'list' && items.length">
      <view class="bill-card" v-for="b in items" :key="b.id" @click="goEdit(b.id)">
        <view class="cat-icon" :style="{ background: categoryMeta(b.category).color + '22' }">
          <image class="cat-img" :src="categoryMeta(b.category).img" mode="widthFix" />
        </view>
        <view class="mid">
          <view class="mid-top">
            <text class="cat-name">{{ b.category }}</text>
            <text class="amount" :class="b.type === 'income' ? 'amount-in' : 'amount-out'">
              {{ b.type === 'income' ? '+' : '-' }}{{ Number(b.amount).toFixed(2) }}
            </text>
          </view>
          <view class="mid-bottom">
            <text class="remark">{{ b.remark || (b.type === 'income' ? '收入' : '支出') }}</text>
            <view class="row-right">
              <text v-if="b.pay_channel" class="channel-tag"
                :style="{ color: channelMeta(b.pay_channel).color, background: channelMeta(b.pay_channel).color + '18' }">
                {{ b.pay_channel }}
              </text>
              <text class="date">{{ b.bill_date.slice(5) }}<text v-if="b.source === 'ai'" class="ai-tag">AI</text><text v-if="b.source === 'receipt'" class="ai-tag">截图</text><text v-if="b.source === 'csv'" class="ai-tag">CSV</text><text v-if="b.source === 'agent'" class="ai-tag">Agent</text><text v-if="b.source === 'subscription'" class="ai-tag sub-tag">订阅</text></text>
            </view>
          </view>
        </view>
      </view>
      <view class="load-more" v-if="items.length < total" @click="loadMore">
        {{ loading ? '加载中…' : '加载更多' }}
      </view>
    </view>
    <view v-else-if="viewMode === 'list'" class="empty">
      <image class="empty-doodle" src="/static/doodles/cloud.png" mode="widthFix" />
      <text>该条件下暂无账单</text>
      <button v-if="categoryId != null" class="btn btn-ghost empty-reset" @click="clearCategory">
        清除分类筛选
      </button>
    </view>

    <!-- ===== 日历视图 ===== -->
    <block v-else>
      <view class="card cal-card">
        <view class="cal-summary">
          <text class="cal-sum-item">本月支出 <text class="out">¥{{ monthSummary.expense.toFixed(2) }}</text></text>
          <text class="cal-sum-item">收入 <text class="in">¥{{ monthSummary.income.toFixed(2) }}</text></text>
        </view>
        <view class="cal-week">
          <text v-for="w in ['一', '二', '三', '四', '五', '六', '日']" :key="w"
            :class="{ wk: w === '六' || w === '日' }">{{ w }}</text>
        </view>
        <view class="cal-grid">
          <view v-for="(c, idx) in calCells" :key="c.key"
            class="cal-cell"
            :class="{ 'cal-blank': c.blank, 'cal-selected': c.selected }"
            :style="!c.blank ? { transform: `rotate(${c.tilt}deg)`, background: c.heat ? `rgba(242, 126, 126, ${c.heat})` : '' } : {}"
            @click="selectDay(c)">
            <block v-if="!c.blank">
              <view class="cal-day" :class="{ 'cal-today': c.isToday, 'cal-weekend': c.isWeekend }">{{ c.day }}</view>
              <view v-if="c.showExpense || c.showIncome" class="cal-dot"
                :style="{ background: c.showExpense ? '#E45858' : '#1FA97F' }" />
              <text v-if="c.showExpense" class="cal-amount out">-{{ fmtAmount(c.expense) }}</text>
              <text v-if="c.showIncome" class="cal-amount in">+{{ fmtAmount(c.income) }}</text>
            </block>
          </view>
        </view>
      </view>

      <!-- 选中日期的明细 -->
      <view class="card day-panel" v-if="selectedDate">
        <image class="day-tape" src="/static/doodles/tape_mint.png" mode="widthFix" />
        <view class="day-head">
          <text class="day-title">{{ selectedDateLabel }}</text>
          <text class="day-sum">
            支 ¥{{ Number(selectedDayStat.expense).toFixed(2) }}
            <text v-if="Number(selectedDayStat.income) > 0" class="in">
              · 收 ¥{{ Number(selectedDayStat.income).toFixed(2) }}
            </text>
          </text>
        </view>
        <view v-if="dayBills.length">
          <view class="bill-card day-bill" v-for="b in dayBills" :key="b.id" @click="goEdit(b.id)">
            <view class="cat-icon sm" :style="{ background: categoryMeta(b.category).color + '22' }">
              <image class="cat-img" :src="categoryMeta(b.category).img" mode="widthFix" />
            </view>
            <view class="mid">
              <view class="mid-top">
                <text class="cat-name">{{ b.category }}</text>
                <text class="amount" :class="b.type === 'income' ? 'amount-in' : 'amount-out'">
                  {{ b.type === 'income' ? '+' : '-' }}{{ Number(b.amount).toFixed(2) }}
                </text>
              </view>
              <view class="mid-bottom">
                <text class="remark">{{ b.remark || (b.type === 'income' ? '收入' : '支出') }}</text>
                <view class="row-right">
                  <text v-if="b.pay_channel" class="channel-tag"
                    :style="{ color: channelMeta(b.pay_channel).color, background: channelMeta(b.pay_channel).color + '18' }">
                    {{ b.pay_channel }}
                  </text>
                  <text class="date" v-if="b.source === 'ai' || b.source === 'receipt' || b.source === 'subscription'">
                    <text class="ai-tag" :class="{ 'sub-tag': b.source === 'subscription' }">{{ b.source === 'receipt' ? '截图' : (b.source === 'subscription' ? '订阅' : (b.source === 'csv' ? 'CSV' : (b.source === 'agent' ? 'Agent' : 'AI'))) }}</text>
                  </text>
                </view>
              </view>
            </view>
          </view>
        </view>
        <view v-else-if="!dayLoading" class="day-empty">
          <text class="day-empty-text">这一天还没有账单</text>
          <button class="btn btn-ghost day-add" @click="goEdit(null, selectedDate)">＋ 为这天记一笔</button>
        </view>
      </view>
    </block>

    <!-- ===== 分类选择抽屉 ===== -->
    <view v-if="catOpen" class="sheet-mask" @click="closeCat">
      <view class="cat-sheet" @click.stop>
        <view class="sheet-handle" />
        <view class="sheet-head">
          <text class="sheet-title">选择分类</text>
          <text v-if="categoryId != null" class="sheet-reset" @click="selectCategory(null)">重置</text>
        </view>

        <scroll-view scroll-y class="cat-scroll">
          <view class="cat-group">
            <view :class="['cat-all', categoryId == null && 'on']" @click="selectCategory(null)">
              <view class="cat-all-ico">🗂️</view>
              <view class="cat-all-mid">
                <text class="cat-all-title">全部分类</text>
                <text class="cat-all-sub">不限制分类，查看所有账单</text>
              </view>
              <text v-if="categoryId == null" class="cat-check">✓</text>
            </view>
          </view>

          <view v-if="catLoading && !categories.length" class="cat-tip">正在加载分类…</view>
          <view v-else-if="catError && !categories.length" class="cat-tip cat-tip-error"
            @click="fetchCategories(true)">{{ catError }}</view>

          <view v-if="recentCategories.length" class="cat-group">
            <text class="cat-group-title">最近使用</text>
            <view class="cat-grid">
              <view v-for="c in recentCategories" :key="'recent-' + c.id"
                :class="['cat-item', categoryId === c.id && 'on']" @click="selectCategory(c)">
                <view class="cat-ico" :style="{ background: categoryMeta(c.name).color + '1f' }">
                  <image class="cat-img-sm" :src="categoryMeta(c.name).img" mode="widthFix" />
                </view>
                <text class="cat-item-name">{{ c.name }}</text>
                <text v-if="categoryId === c.id" class="cat-item-check">✓</text>
              </view>
            </view>
          </view>

          <view v-if="showExpenseGroup && expenseCategories.length" class="cat-group">
            <text class="cat-group-title">支出分类</text>
            <view class="cat-grid">
              <view v-for="c in expenseCategories" :key="'expense-' + c.id"
                :class="['cat-item', categoryId === c.id && 'on']" @click="selectCategory(c)">
                <view class="cat-ico" :style="{ background: categoryMeta(c.name).color + '1f' }">
                  <image class="cat-img-sm" :src="categoryMeta(c.name).img" mode="widthFix" />
                </view>
                <text class="cat-item-name">{{ c.name }}</text>
                <text v-if="categoryId === c.id" class="cat-item-check">✓</text>
              </view>
            </view>
          </view>

          <view v-if="showIncomeGroup && incomeCategories.length" class="cat-group">
            <text class="cat-group-title">收入分类</text>
            <view class="cat-grid">
              <view v-for="c in incomeCategories" :key="'income-' + c.id"
                :class="['cat-item', categoryId === c.id && 'on']" @click="selectCategory(c)">
                <view class="cat-ico" :style="{ background: categoryMeta(c.name).color + '1f' }">
                  <image class="cat-img-sm" :src="categoryMeta(c.name).img" mode="widthFix" />
                </view>
                <text class="cat-item-name">{{ c.name }}</text>
                <text v-if="categoryId === c.id" class="cat-item-check">✓</text>
              </view>
            </view>
          </view>
        </scroll-view>

        <view class="sheet-foot">
          <button class="btn btn-primary sheet-done" @click="closeCat">完成</button>
        </view>
      </view>
    </view>

    <!-- 悬浮新增按钮 -->
    <view class="fab" @click="viewMode === 'list' ? goEdit() : goEdit(null, selectedDate)">＋</view>
  </view>
</template>

<style scoped>
.page { padding-bottom: 140rpx; }
.filter-bar { background: #FFFDF8; padding: 20rpx 24rpx 6rpx; }
.month-row { position: relative; }
.month-nav { display: flex; align-items: center; justify-content: center; gap: 24rpx; }
.arrow { font-size: 42rpx; color: #8A90A8; padding: 0 20rpx; }
.month { font-size: 32rpx; font-weight: 700; }
.view-toggle { position: absolute; right: 0; top: 50%; transform: translateY(-50%);
  font-size: 26rpx; color: #6C7BF5; background: #EFF1FF; border-radius: 28rpx; padding: 8rpx 22rpx; }
.type-tabs { display: flex; gap: 20rpx; justify-content: center; margin: 18rpx 0 14rpx; }
.tab { font-size: 28rpx; color: #8A90A8; padding: 8rpx 30rpx; border-radius: 30rpx; background: #F6F4FB; }
.tab-active { color: #fff; background: #6C7BF5; font-weight: 600; }

/* 分类筛选入口 */
.filter-sub { display: flex; align-items: center; justify-content: space-between;
  gap: 16rpx; padding: 0 2rpx 14rpx; }
.filter-left { display: flex; align-items: center; gap: 10rpx; min-width: 0; max-width: 76%; }
.cat-filter { display: inline-flex; align-items: center; gap: 8rpx; max-width: 100%;
  padding: 10rpx 22rpx; border-radius: 999rpx; background: #FFFDF8;
  border: 1rpx dashed #D9D6E8; font-size: 26rpx; color: #5E6379; }
.cat-filter-on { background: #EFF1FF; border: 1rpx solid #B9C0FF; color: #5A66D8; font-weight: 600; }
.cat-filter-ico { font-size: 24rpx; }
.cat-filter-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat-filter-caret { font-size: 22rpx; color: #9AA0B8; }
.cat-filter-clear { flex-shrink: 0; width: 42rpx; height: 42rpx; border-radius: 21rpx;
  background: #EFF1FF; color: #6C7BF5; display: flex; align-items: center;
  justify-content: center; font-size: 30rpx; line-height: 1; }
.filter-count { font-size: 23rpx; color: #A6AAC2; flex-shrink: 0; }

/* 订阅管理入口 */
.sub-entry { display: flex; align-items: center; gap: 16rpx; margin: 14rpx 24rpx 0;
  padding: 20rpx 24rpx; background: #FFFDF8; border-radius: 24rpx;
  box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10); }
.sub-entry:active { opacity: .85; }
.sub-entry-icon { width: 56rpx; height: 56rpx; flex-shrink: 0; }
.sub-entry-mid { flex: 1; min-width: 0; }
.sub-entry-title { display: block; font-size: 29rpx; font-weight: 700; color: #3A3F58; }
.sub-entry-sub { display: block; font-size: 23rpx; color: #A6AAC2; margin-top: 4rpx;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sub-entry-arrow { flex-shrink: 0; font-size: 25rpx; color: #6C7BF5; font-weight: 600; }

/* ===== 列表 ===== */
.list { margin-top: 16rpx; }
.bill-card { display: flex; align-items: center; background: #FFFDF8; margin: 14rpx 24rpx;
  border-radius: 22rpx; padding: 24rpx 24rpx; box-shadow: 0 6rpx 24rpx rgba(124, 139, 255, .10); }
.bill-card:active { opacity: .85; }
.cat-icon { width: 84rpx; height: 84rpx; border-radius: 28rpx;
  display: flex; align-items: center; justify-content: center; margin-right: 22rpx; flex-shrink: 0; }
.cat-img { width: 64rpx; height: 64rpx; }
.cat-icon.sm { width: 68rpx; height: 68rpx; border-radius: 22rpx; }
.cat-icon.sm .cat-img { width: 46rpx; height: 46rpx; }
.mid { flex: 1; min-width: 0; }
.mid-top { display: flex; justify-content: space-between; align-items: center; }
.mid-bottom { display: flex; justify-content: space-between; align-items: center; margin-top: 10rpx; }
.cat-name { font-size: 30rpx; font-weight: 600; }
.remark { font-size: 25rpx; color: #A6AAC2; max-width: 380rpx; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.date { font-size: 25rpx; color: #A6AAC2; }
.row-right { display: flex; align-items: center; gap: 10rpx; }
.channel-tag { font-size: 23rpx; padding: 2rpx 12rpx; border-radius: 8rpx; font-weight: 600; }
.ai-tag { margin-left: 10rpx; background: #EFF1FF; color: #6C7BF5; border-radius: 8rpx;
  padding: 2rpx 10rpx; font-size: 23rpx; font-weight: 600; }
.sub-tag { background: #FFF3E0; color: #C7772B; }
.amount { font-size: 34rpx; font-weight: 800; }
.amount-in { color: #1FA97F; } .amount-out { color: #E45858; }
.load-more { text-align: center; color: #8A90A8; font-size: 26rpx; padding: 24rpx; }
.empty-doodle { width: 160rpx; display: block; margin: 0 auto 14rpx; opacity: .9; }
.empty-reset { width: 300rpx; margin: 24rpx auto 0; height: 70rpx; font-size: 26rpx; }

/* ===== 分类选择抽屉 ===== */
.sheet-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; z-index: 999;
  background: rgba(35, 38, 54, .42); display: flex; align-items: flex-end; }
.cat-sheet { width: 100%; background: #FFFDF8; border-radius: 34rpx 34rpx 0 0;
  padding: 14rpx 0 24rpx; display: flex; flex-direction: column; max-height: 82vh;
  animation: sheetFade .18s ease-out; }
@keyframes sheetFade { from { opacity: .82; } to { opacity: 1; } }
.sheet-handle { width: 64rpx; height: 8rpx; border-radius: 4rpx; background: #E2E0EC;
  margin: 4rpx auto 12rpx; }
.sheet-head { display: flex; align-items: center; justify-content: space-between;
  padding: 8rpx 32rpx 16rpx; }
.sheet-title { font-size: 32rpx; font-weight: 700; color: #3A3F58; }
.sheet-reset { font-size: 26rpx; color: #8A90A8; padding: 6rpx 14rpx; }
.cat-scroll { height: 54vh; padding: 0 28rpx; box-sizing: border-box; }
.cat-group { margin-bottom: 22rpx; }
.cat-group-title { display: block; font-size: 24rpx; color: #9A9FB6;
  letter-spacing: 1rpx; margin: 4rpx 4rpx 12rpx; }
.cat-all { display: flex; align-items: center; gap: 16rpx; padding: 18rpx 20rpx;
  border-radius: 20rpx; border: 2rpx solid transparent; background: #F7F5FC; }
.cat-all.on { border-color: #8C96F8; background: #F1F2FF; }
.cat-all-ico { width: 64rpx; height: 64rpx; border-radius: 20rpx; background: #FFFDF8;
  display: flex; align-items: center; justify-content: center; font-size: 32rpx; }
.cat-all-mid { flex: 1; min-width: 0; }
.cat-all-title { display: block; font-size: 28rpx; font-weight: 600; color: #3A3F58; }
.cat-all-sub { display: block; font-size: 22rpx; color: #A6AAC2; margin-top: 4rpx; }
.cat-check { color: #6C7BF5; font-size: 30rpx; font-weight: 700; }
.cat-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14rpx; }
.cat-item { position: relative; display: flex; flex-direction: column; align-items: center;
  gap: 8rpx; padding: 16rpx 6rpx 14rpx; border-radius: 20rpx;
  border: 2rpx solid transparent; background: #F9F8FD; }
.cat-item.on { border-color: #8C96F8; background: #F1F2FF; }
.cat-item:active { opacity: .85; }
.cat-ico { width: 70rpx; height: 70rpx; border-radius: 22rpx;
  display: flex; align-items: center; justify-content: center; }
.cat-img-sm { width: 48rpx; height: 48rpx; }
.cat-item-name { font-size: 24rpx; color: #4A4F6B; font-weight: 600; }
.cat-item-check { position: absolute; top: 6rpx; right: 8rpx; color: #6C7BF5;
  font-size: 22rpx; font-weight: 700; }
.cat-tip { text-align: center; font-size: 25rpx; color: #A6AAC2; padding: 30rpx 0; }
.cat-tip-error { color: #E45858; }
.sheet-foot { padding: 12rpx 28rpx 4rpx; border-top: 1rpx solid #F1EFF9; }
.sheet-done { width: 100%; height: 84rpx; line-height: 84rpx; font-size: 29rpx; border-radius: 24rpx; }

/* ===== 日历 ===== */
.cal-card { padding: 24rpx 18rpx 18rpx; }
.cal-summary { display: flex; justify-content: space-between; gap: 14rpx; padding: 0 6rpx 18rpx;
  border-bottom: 1rpx dashed #E7E3F4; }
.cal-sum-item { font-size: 26rpx; color: #7A7F96; background: #F6F4FB; border-radius: 999rpx;
  padding: 8rpx 18rpx; }
.out { color: #E45858; } .in { color: #1FA97F; }
.cal-week { display: grid; grid-template-columns: repeat(7, 1fr); margin: 16rpx 0 8rpx; }
.cal-week text { text-align: center; font-size: 24rpx; color: #8A90A8; letter-spacing: 1rpx; }
.cal-week .wk { color: #C77BA6; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8rpx; padding: 4rpx 2rpx 6rpx; }
.cal-cell { position: relative; min-height: 130rpx; border-radius: 18rpx; padding: 8rpx 2rpx 6rpx;
  display: flex; flex-direction: column; align-items: center; box-sizing: border-box;
  border: 2rpx solid transparent; background: #FFFDF8;
  box-shadow: 0 4rpx 10rpx rgba(124, 139, 255, .07); }
.cal-blank { background: transparent; box-shadow: none; }
.cal-selected { border: 2rpx dashed #6C7BF5; background-color: #FBFAFF; }
.cal-day { font-size: 26rpx; font-weight: 600; color: #4A4F6B; line-height: 40rpx;
  min-width: 40rpx; text-align: center; border-radius: 10rpx; padding: 0 4rpx; }
.cal-weekend { color: #C77BA6; }
.cal-today { background: linear-gradient(180deg, transparent 46%, rgba(255, 214, 140, .85) 46%,
  rgba(255, 214, 140, .85) 88%, transparent 88%); color: #7A5A1F; }
.cal-dot { position: absolute; top: 8rpx; right: 8rpx; width: 10rpx; height: 10rpx; border-radius: 5rpx; }
.cal-amount { font-size: 21rpx; line-height: 24rpx; max-width: 100%;
  overflow: hidden; white-space: nowrap; }
.cal-amount.out { color: #E45858; font-weight: 700; }
.cal-amount.in { color: #1FA97F; font-weight: 700; }

/* ===== 当日明细 ===== */
.day-panel { position: relative; padding: 34rpx 24rpx 24rpx; }
.day-tape { position: absolute; top: -14rpx; left: 44rpx; width: 120rpx; transform: rotate(-4deg); }
.day-head { display: flex; justify-content: space-between; align-items: center;
  padding-bottom: 16rpx; border-bottom: 1rpx solid #F1EFF9; }
.day-title { font-size: 32rpx; font-weight: 700; }
.day-sum { font-size: 25rpx; color: #8A90A8; }
.day-bill { margin: 16rpx 0 0; box-shadow: none; border: 1rpx solid #F1EFF9; padding: 20rpx; }
.day-empty { text-align: center; padding: 36rpx 0 20rpx; }
.day-empty-text { display: block; font-size: 26rpx; color: #A6AAC2; margin-bottom: 22rpx; }
.day-add { width: 340rpx; height: 72rpx; font-size: 28rpx; margin: 0 auto; }

.fab { position: fixed; right: 40rpx; bottom: 200rpx; width: 108rpx; height: 108rpx;
  border-radius: 54rpx; background: #6C7BF5; color: #fff; font-size: 56rpx;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 10rpx 30rpx rgba(124, 139, 255, .35); }
.fab:active { opacity: .85; }
</style>
