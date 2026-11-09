<script setup>
import { ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { apiNotes, apiAddNote, apiUpdateNote } from '../../api/index.js'
import { buildEntryTip, buildTodoTip } from '../../common/note-tips.js'
import store from '../../store/user.js'

const TZ = new Date().getTimezoneOffset() * 60000
function nowLocal() { return new Date(Date.now() - TZ) }
function fmtDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function addDays(dateStr, delta) {
  const d = new Date(dateStr + 'T00:00:00')
  d.setDate(d.getDate() + delta)
  return fmtDate(d)
}

const todayStr = fmtDate(nowLocal())
const tomorrowStr = addDays(todayStr, 1)

// ---------- 记录类型 ----------
const TYPES = [
  { key: 'todo', label: '待办', icon: '✓', desc: '任务、截止时间与月历', hint: '把要做的事，安排得明明白白' },
  { key: 'idea', label: '想法', icon: '✦', desc: '灵感、片段与突然想到', hint: '把灵光一现，轻轻收好' },
  { key: 'mood', label: '心情', icon: '♥', desc: '此刻情绪与生活碎片', hint: '把今天的心情，留在这里' },
]
const entryType = ref('todo')
const typeMenu = ref(false)
const currentType = computed(() => TYPES.find(t => t.key === entryType.value) || TYPES[0])
const isTodo = computed(() => entryType.value === 'todo')
const entryLabel = computed(() => currentType.value.label)
const entryIcon = computed(() => currentType.value.icon)
const entryHint = computed(() => currentType.value.hint)
const entryColor = computed(() => (entryType.value === 'mood' ? 'rose' : 'lilac'))
const quickPlaceholder = computed(() =>
  entryType.value === 'mood' ? '一句话轻松记录心情…' : '一句话轻松记录想法…')
const avatarUrl = computed(() =>
  (store.user && store.user.avatar) || '/static/doodles/cat.png')

const loading = ref(false)
const loadError = ref('')
const keyword = ref('')

const openTodos = ref([])
const doneTodos = ref([])
const entryItems = ref([])

// ---------- 任务颜色（与编辑页一致） ----------
const TASK_COLORS = {
  lilac: '#EFDFE9', sky: '#D2EFF1', mint: '#DEF6D6',
  peach: '#BDE4DD', sand: '#FFE8C9', rose: '#FED2DF',
}
function taskColor(c) { return TASK_COLORS[c] || TASK_COLORS.lilac }

// ---------- 数据 ----------
let loadSeq = 0
async function load() {
  const seq = ++loadSeq
  loading.value = true
  loadError.value = ''
  try {
    if (isTodo.value) {
      const [openRes, doneRes] = await Promise.all([
        apiNotes({ note_type: 'todo', status: 'open', q: keyword.value, page: 1, page_size: 100 }),
        apiNotes({ note_type: 'todo', status: 'done', q: keyword.value, page: 1, page_size: 100 }),
      ])
      if (seq !== loadSeq) return
      openTodos.value = openRes.items
      doneTodos.value = doneRes.items
    } else {
      const res = await apiNotes({
        note_type: 'note', entry_type: entryType.value, page: 1, page_size: 200,
      })
      if (seq !== loadSeq) return
      entryItems.value = res.items
    }
  } catch (e) {
    if (seq === loadSeq) {
      loadError.value = (e && e.message) || '加载失败，请检查网络后重试'
    }
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

function switchType(key) {
  if (entryType.value === key) { typeMenu.value = false; return }
  entryType.value = key
  typeMenu.value = false
  keyword.value = ''
  focusDate.value = ''
  load()
}

function setView(v) { viewMode.value = v }
function clearSearch() { keyword.value = ''; load() }

async function toggleDone(n) {
  if (n.note_type !== 'todo') return
  const next = n.status === 'open' ? 'done' : 'open'
  try {
    await apiUpdateNote(n.id, {
      title: n.title, content: n.content, location: n.location || '',
      images: entryPhotos(n),
      note_type: n.note_type, entry_type: n.entry_type || 'note',
      status: next, due_at: n.due_at, priority: n.priority,
      pinned: n.pinned, color: n.color || 'lilac',
    })
    if (next === 'done') uni.showToast({ title: '已完成 ✓', icon: 'none' })
    load()
  } catch (e) { /* 统一提示 */ }
}

async function togglePin(n) {
  try {
    await apiUpdateNote(n.id, {
      title: n.title, content: n.content, location: n.location || '',
      images: entryPhotos(n),
      note_type: n.note_type, entry_type: n.entry_type || 'note',
      status: n.status, due_at: n.due_at, priority: n.priority,
      pinned: !n.pinned, color: n.color || 'lilac',
    })
    uni.showToast({ title: n.pinned ? '已取消置顶' : '已置顶', icon: 'none' })
    load()
  } catch (e) { /* 统一提示 */ }
}

// ---------- 截止时间 ----------
function dueInfo(n) {
  if (!n.due_at || n.note_type !== 'todo') return null
  const s = String(n.due_at)
  const d = s.slice(0, 10)
  const hm = s.slice(11, 16) || '18:00'
  if (n.status === 'open' && d < todayStr) {
    const days = Math.max(1, Math.round((new Date(todayStr) - new Date(d)) / 86400000))
    return { text: `已逾期 ${days} 天`, cls: 'due-over' }
  }
  if (d === todayStr) return { text: `今天 ${hm}`, cls: 'due-today' }
  if (d === tomorrowStr) return { text: `明天 ${hm}`, cls: 'due-soon' }
  return { text: `${Number(d.slice(5, 7))}月${Number(d.slice(8))}日 ${hm}`, cls: 'due-normal' }
}

const PRIORITY_META = {
  high: { label: '高', cls: 'pri-high' },
  low: { label: '低', cls: 'pri-low' },
}

// ---------- 待办月历（保留原有任务日历） ----------
const viewMode = ref('calendar')      // calendar 月历 / list 清单 / board 看板
const calToday = nowLocal()
const calYear = ref(calToday.getFullYear())
const calMonth = ref(calToday.getMonth() + 1)   // 1-12
const calSelected = ref('')

const calTitle = computed(() => `${calYear.value}年${calMonth.value}月`)

const tasksByDate = computed(() => {
  const map = {}
  for (const n of [...openTodos.value, ...doneTodos.value]) {
    if (!n.due_at) continue
    const d = String(n.due_at).slice(0, 10)
    if (!map[d]) map[d] = []
    map[d].push(n)
  }
  for (const key of Object.keys(map)) {
    map[key].sort((a, b) =>
      (a.status === 'done') - (b.status === 'done') ||
      String(a.due_at).localeCompare(String(b.due_at)))
  }
  return map
})

const calCells = computed(() => {
  const first = new Date(calYear.value, calMonth.value - 1, 1)
  const offset = (first.getDay() + 6) % 7   // 周一开头
  const start = new Date(first)
  start.setDate(1 - offset)
  const cells = []
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    const date = fmtDate(d)
    const tasks = tasksByDate.value[date] || []
    cells.push({
      key: date,
      date,
      day: d.getDate(),
      inMonth: d.getMonth() === calMonth.value - 1,
      isToday: date === todayStr,
      selected: date === calSelected.value,
      tags: tasks.slice(0, 2),
      more: Math.max(0, tasks.length - 2),
    })
  }
  return cells
})

const weekDaysHeader = ['一', '二', '三', '四', '五', '六', '日']

function shiftMonth(delta) {
  let y = calYear.value
  let m = calMonth.value + delta
  if (m < 1) { y -= 1; m = 12 }
  else if (m > 12) { y += 1; m = 1 }
  calYear.value = y
  calMonth.value = m
  calSelected.value = ''
}

function goToday() {
  const d = nowLocal()
  calYear.value = d.getFullYear()
  calMonth.value = d.getMonth() + 1
  calSelected.value = todayStr
}

function selectCell(c) {
  // 再点一次已选日期 = 取消筛选，恢复全部任务
  if (calSelected.value === c.date) {
    calSelected.value = ''
    return
  }
  calSelected.value = c.date
  if (!c.inMonth) {
    calYear.value = Number(c.date.slice(0, 4))
    calMonth.value = Number(c.date.slice(5, 7))
  }
}

const selectedDateLabel = computed(() =>
  calSelected.value ? timelineDateLabel(calSelected.value) : '')

function shortTitle(title) {
  return title.length > 5 ? title.slice(0, 5) : title
}

function taskTime(n) {
  return String(n.due_at || '').slice(11, 16) || '18:00'
}

function reminderTime(n) {
  const raw = String(n.due_at || '')
  if (!raw) return ''
  const due = raw.slice(11, 16)
  if (!due || n.status === 'done') return due
  const d = new Date(raw.replace(' ', 'T'))
  if (Number.isNaN(d.getTime())) return due
  d.setMinutes(d.getMinutes() - 10)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function todoTip(n) {
  return buildTodoTip(n)
}

function entryTip(n) {
  return buildEntryTip(n, entryType.value)
}

function entryPhotos(n) {
  const list = Array.isArray(n.images) ? n.images.filter(Boolean) : []
  if (list.length) return list
  return n.image ? [n.image] : []
}

function previewPhoto(n, index = 0) {
  const urls = entryPhotos(n)
  if (!urls.length) return
  uni.previewImage({ urls, current: urls[index] || urls[0] })
}

const todoTimelineGroups = computed(() => {
  const all = [...openTodos.value, ...doneTodos.value]
  const map = new Map()
  const undated = []
  for (const n of all) {
    const date = n.due_at ? String(n.due_at).slice(0, 10) : ''
    if (!date) { undated.push(n); continue }
    if (!map.has(date)) map.set(date, [])
    map.get(date).push(n)
  }
  function group(date) {
    return {
      key: date,
      label: timelineDateLabel(date),
      items: map.get(date).slice().sort((a, b) =>
        (a.status === 'done') - (b.status === 'done') ||
        String(b.due_at || '').localeCompare(String(a.due_at || ''))),
    }
  }
  const dates = Array.from(map.keys())
  const future = dates.filter(d => d > todayStr).sort()
  const past = dates.filter(d => d < todayStr).sort().reverse()
  const groups = []
  if (map.has(todayStr)) groups.push(group(todayStr))
  groups.push(...future.map(group), ...past.map(group))
  if (undated.length) {
    groups.push({
      key: 'undated',
      label: '未安排时间',
      items: undated.slice().sort((a, b) =>
        String(b.updated_at || '').localeCompare(String(a.updated_at || ''))),
    })
  }
  return groups
})

const todoVisibleGroups = computed(() => {
  if (!calSelected.value) return todoTimelineGroups.value
  return todoTimelineGroups.value.filter(g => g.key === calSelected.value)
})

// ---------- 待办统计 ----------
const openCount = computed(() => openTodos.value.length)
const doneCount = computed(() => doneTodos.value.length)
const overdueCount = computed(() =>
  openTodos.value.filter(n => n.due_at && String(n.due_at).slice(0, 10) < todayStr).length)

// ---------- 待办清单 / 看板 ----------
const listGroups = computed(() => {
  const g = { overdue: [], today: [], week: [], later: [] }
  const weekEnd = addDays(todayStr, 7)
  for (const n of openTodos.value) {
    const d = n.due_at ? String(n.due_at).slice(0, 10) : ''
    if (!d) g.later.push(n)
    else if (d < todayStr) g.overdue.push(n)
    else if (d === todayStr) g.today.push(n)
    else if (d <= weekEnd) g.week.push(n)
    else g.later.push(n)
  }
  for (const key of Object.keys(g)) {
    g[key].sort((a, b) => String(a.due_at || '9999').localeCompare(String(b.due_at || '9999')))
  }
  return [
    { key: 'overdue', label: '已逾期', items: g.overdue, cls: 'g-over' },
    { key: 'today', label: '今天', items: g.today, cls: 'g-today' },
    { key: 'week', label: '本周', items: g.week, cls: 'g-week' },
    { key: 'later', label: '以后 / 未安排', items: g.later, cls: 'g-later' },
  ].filter(x => x.items.length)
})

function isOverdue(n) {
  const d = n.due_at ? String(n.due_at).slice(0, 10) : ''
  return !!d && d < todayStr
}

const boardColumns = computed(() => [
  { key: 'overdue', label: '逾期', cls: 'col-over', items: openTodos.value.filter(isOverdue) },
  { key: 'open', label: '待办', cls: 'col-open', items: openTodos.value.filter(n => !isOverdue(n)) },
  { key: 'done', label: '已完成', cls: 'col-done', items: doneTodos.value },
])

// ---------- 想法 / 心情月历 ----------
const entryToday = nowLocal()
const entryYear = ref(entryToday.getFullYear())
const entryMonth = ref(entryToday.getMonth() + 1)
const focusDate = ref('')

const entryMonthTitle = computed(() => `${entryYear.value}年${entryMonth.value}月`)
const entryMonthKey = computed(() =>
  `${entryYear.value}-${String(entryMonth.value).padStart(2, '0')}`)

function createdDate(n) { return String(n.created_at || '').slice(0, 10) }

const recordedDates = computed(() => {
  const set = new Set()
  for (const n of entryItems.value) {
    const d = createdDate(n)
    if (d) set.add(d)
  }
  return set
})

const entryMonthDays = computed(() => {
  let count = 0
  for (const d of recordedDates.value) {
    if (d.slice(0, 7) === entryMonthKey.value) count += 1
  }
  return count
})

const entryCalCells = computed(() => {
  const first = new Date(entryYear.value, entryMonth.value - 1, 1)
  const offset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(1 - offset)
  const cells = []
  for (let i = 0; i < 42; i += 1) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    const date = fmtDate(d)
    cells.push({
      key: date,
      date,
      day: d.getDate(),
      inMonth: d.getMonth() === entryMonth.value - 1,
      recorded: recordedDates.value.has(date),
      isToday: date === todayStr,
      selected: date === focusDate.value,
    })
  }
  return cells
})

function shiftEntryMonth(delta) {
  let y = entryYear.value
  let m = entryMonth.value + delta
  if (m < 1) { y -= 1; m = 12 }
  else if (m > 12) { y += 1; m = 1 }
  entryYear.value = y
  entryMonth.value = m
  focusDate.value = ''
}

function entryGoToday() {
  const d = nowLocal()
  entryYear.value = d.getFullYear()
  entryMonth.value = d.getMonth() + 1
  focusDate.value = ''
}

function pickEntryDate(c) {
  if (!c.inMonth || !c.recorded) return
  focusDate.value = focusDate.value === c.date ? '' : c.date
}

const focusLabel = computed(() => {
  if (!focusDate.value) return ''
  const d = new Date(focusDate.value + 'T00:00:00')
  return `${d.getMonth() + 1}月${d.getDate()}日`
})

// ---------- 想法 / 心情时间轴 ----------
function timelineDateLabel(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const week = `周${'日一二三四五六'[d.getDay()]}`
  const body = `${d.getMonth() + 1}月${d.getDate()}日(${week})`
  if (dateStr === todayStr) return `今天 ${body}`
  if (dateStr === addDays(todayStr, -1)) return `昨天 ${body}`
  if (d.getFullYear() !== nowLocal().getFullYear()) return `${d.getFullYear()}年${body}`
  return body
}

function entryTime(n) {
  const s = String(n.created_at || '')
  return s.slice(11, 16) || '--:--'
}

const entryGroups = computed(() => {
  const map = new Map()
  for (const n of entryItems.value) {
    const d = createdDate(n)
    if (!d) continue
    if (focusDate.value && d !== focusDate.value) continue
    if (!map.has(d)) map.set(d, [])
    map.get(d).push(n)
  }
  return Array.from(map.entries())
    .sort((a, b) => b[0].localeCompare(a[0]))
    .map(([date, items]) => ({
      date,
      label: timelineDateLabel(date),
      items: items.slice().sort((a, b) =>
        String(b.created_at || '').localeCompare(String(a.created_at || ''))),
    }))
})

const entryTotal = computed(() => entryItems.value.length)

// ---------- 一句话记录 ----------
const quickDraft = ref('')
const quickSaving = ref(false)

function splitQuickText(raw) {
  const text = raw.trim()
  if (!text) return null
  const lines = text.split(/\n+/).map(s => s.trim()).filter(Boolean)
  if (lines.length > 1) {
    return {
      title: lines[0].slice(0, 100),
      content: lines.slice(1).join('\n').slice(0, 5000),
    }
  }
  const match = text.match(/^(.{1,40}?[。！？!?；;])\s*(.+)$/s)
  if (match && match[2]) {
    return { title: match[1].slice(0, 100), content: match[2].slice(0, 5000) }
  }
  return {
    title: text.slice(0, 100),
    content: text.length > 100 ? text.slice(100).trim().slice(0, 5000) : '',
  }
}

async function saveQuick() {
  if (quickSaving.value || isTodo.value) return
  const parsed = splitQuickText(quickDraft.value)
  if (!parsed) {
    uni.showToast({ title: '先写一句话吧', icon: 'none' })
    return
  }
  quickSaving.value = true
  try {
    await apiAddNote({
      title: parsed.title,
      content: parsed.content,
      note_type: 'note',
      entry_type: entryType.value,
      status: 'open',
      due_at: null,
      priority: 'medium',
      pinned: false,
      color: entryColor.value,
    })
    quickDraft.value = ''
    const d = nowLocal()
    entryYear.value = d.getFullYear()
    entryMonth.value = d.getMonth() + 1
    focusDate.value = ''
    uni.showToast({ title: '已记下', icon: 'success' })
    load()
  } catch (e) { /* 统一提示 */ } finally {
    quickSaving.value = false
  }
}

// ---------- 跳转 ----------
function goEdit(id) {
  uni.navigateTo({ url: '/pages/notes/edit?id=' + id })
}

function goNewTaskFor(date) {
  const target = date && date !== 'undated' ? date : todayStr
  calSelected.value = target
  uni.navigateTo({ url: `/pages/notes/edit?type=todo&date=${target}` })
}

function goNewTask() {
  goNewTaskFor(calSelected.value)
}

function goNewEntry() {
  uni.navigateTo({ url: `/pages/notes/edit?type=${entryType.value}` })
}

function goAgent() {
  uni.switchTab({ url: '/pages/agent/agent' })
}

function goProfile() {
  uni.switchTab({ url: '/pages/profile/profile' })
}

onShow(load)
</script>

<template>
  <view class="record-page" :class="'theme-' + entryType">
    <view class="status-space" />

    <!-- 顶部：记录 / AI助手 / 类型切换 / 头像 -->
    <view class="record-head">
      <view class="head-copy">
        <view class="head-title-row">
          <text class="record-title">记录</text>
          <text class="ai-link" @click="goAgent">AI助手 ↗</text>
        </view>
        <text class="record-sub">{{ entryHint }}</text>
      </view>
      <view class="head-right">
        <view class="type-pill" @click="typeMenu = true">
          <text class="type-icon">{{ currentType.icon }}</text>
          <text class="type-name">{{ currentType.label }}</text>
          <text class="type-caret">⌄</text>
        </view>
        <image class="head-avatar" :src="avatarUrl" mode="aspectFill" @click="goProfile" />
      </view>
    </view>

    <view v-if="loadError" class="error-banner">
      <text class="error-text">{{ loadError }}</text>
      <text class="error-retry" @click="load">重试</text>
    </view>

    <!-- ===== 待办：保留原任务日历 ===== -->
    <block v-if="isTodo">
      <view class="todo-tools">
        <view class="search-box">
          <input class="search-input" v-model="keyword" confirm-type="search"
            placeholder="搜索待办任务" placeholder-class="ph" @confirm="load" />
          <text v-if="keyword" class="search-clear" @click="clearSearch">×</text>
          <text class="search-btn" @click="load">搜索</text>
        </view>
      </view>

      <view class="view-switch">
        <text :class="['v-btn', viewMode === 'calendar' && 'v-active']" @click="setView('calendar')">月历</text>
        <text :class="['v-btn', viewMode === 'list' && 'v-active']" @click="setView('list')">清单</text>
        <text :class="['v-btn', viewMode === 'board' && 'v-active']" @click="setView('board')">看板</text>
        <text class="v-stat">待办 {{ openCount }} · 逾期 {{ overdueCount }} · 完成 {{ doneCount }}</text>
      </view>

      <view v-if="loading" class="loading-strip">正在加载任务…</view>

      <!-- 月历视图 -->
      <block v-if="viewMode === 'calendar'">
        <view class="glass cal-head">
          <text class="cal-title">{{ calTitle }}</text>
          <view class="cal-actions">
            <text class="cal-btn" @click="shiftMonth(-1)">‹</text>
            <text class="cal-today-btn" @click="goToday">今天</text>
            <text class="cal-btn" @click="shiftMonth(1)">›</text>
          </view>
        </view>

        <view class="glass cal-panel">
          <view class="cal-week">
            <text v-for="w in weekDaysHeader" :key="w" :class="{ wk: w === '六' || w === '日' }">{{ w }}</text>
          </view>
          <view class="cal-grid">
            <view v-for="c in calCells" :key="c.key"
              class="cal-cell"
              :class="{ dim: !c.inMonth, sel: c.selected, today: c.isToday }"
              @click="selectCell(c)">
              <text class="cal-num">{{ c.day }}</text>
              <view class="cal-tags" v-if="c.tags.length">
                <view class="cal-tag" v-for="t in c.tags" :key="t.id"
                  :style="{ background: taskColor(t.color) }">
                  <text class="tag-text">{{ shortTitle(t.title) }}</text>
                </view>
                <text v-if="c.more" class="cal-more">+{{ c.more }}</text>
              </view>
            </view>
          </view>
        </view>

        <!-- 日历下方：待办时间轴 -->
        <view class="todo-feed">
          <view v-if="calSelected" class="todo-filter">
            <text>只看 {{ selectedDateLabel }}</text>
            <text class="todo-filter-clear" @click="calSelected = ''">查看全部</text>
          </view>

          <view v-for="(g, gIdx) in todoVisibleGroups" :key="g.key" class="todo-group">
            <view class="todo-date-head">
              <view class="todo-date-square" />
              <text class="todo-date-label">{{ g.label }}</text>
              <text class="todo-date-count">{{ g.items.length }} 项</text>
              <view v-if="gIdx === 0" class="todo-date-add" @click.stop="goNewTaskFor(g.key)">＋</view>
            </view>

            <view v-for="(n, idx) in g.items" :key="n.id" class="todo-row">
              <view class="todo-time">
                <text>{{ g.key === 'undated' || !n.due_at ? '—' : taskTime(n) }}</text>
              </view>
              <view class="todo-rail">
                <view class="todo-rail-dot" :class="{ done: n.status === 'done' }" />
                <view v-if="idx < g.items.length - 1" class="todo-rail-line" />
              </view>

              <view class="todo-card" :class="{ 'todo-card-done': n.status === 'done' }"
                @click="goEdit(n.id)">
                <view class="todo-card-top">
                  <view class="todo-badge"><text class="todo-badge-icon">⏰</text>待办</view>
                  <text v-if="n.due_at" class="todo-remind">⏰ {{ reminderTime(n) }}</text>
                  <text v-else class="todo-remind todo-remind-none">未设提醒</text>
                </view>

                <view class="todo-main">
                  <view class="todo-check" :class="{ checked: n.status === 'done' }"
                    @click.stop="toggleDone(n)">
                    {{ n.status === 'done' ? '✓' : '' }}
                  </view>
                  <view class="todo-copy">
                    <view class="todo-title-row">
                      <text class="todo-title">{{ n.title }}</text>
                      <text v-if="PRIORITY_META[n.priority]" class="pri-tag"
                        :class="PRIORITY_META[n.priority].cls">
                        {{ PRIORITY_META[n.priority].label }}
                      </text>
                      <image v-if="n.pinned" class="pin-mark" src="/static/icons/act_pin.png" mode="widthFix" />
                    </view>
                    <text v-if="n.content" class="todo-desc">{{ n.content }}</text>
                  </view>
                </view>

                <view v-if="n.location" class="todo-loc">
                  <text class="todo-loc-icon">⌖</text>
                  <text>{{ n.location }}</text>
                </view>

                <view class="todo-ai-tip">
                  <text class="todo-ai-name">小知：</text>
                  <text class="todo-ai-text">{{ todoTip(n) }}</text>
                </view>
              </view>
            </view>
          </view>

          <view v-if="!todoVisibleGroups.length && !loading" class="glass day-empty">
            <image class="empty-animal" src="/static/doodles/rabbit.png" mode="widthFix" />
            <text>{{ calSelected ? '这一天还没有待办' : '还没有待办' }}，点下面按钮添加</text>
            <view class="empty-add" @click="goNewTaskFor(calSelected || todayStr)">＋ 新建任务</view>
          </view>
        </view>
      </block>

      <!-- 清单视图 -->
      <block v-else-if="viewMode === 'list'">
        <view v-for="g in listGroups" :key="g.key" class="group">
          <view class="group-head">
            <view class="g-dot" :class="g.cls" />
            <text class="group-title">{{ g.label }}</text>
            <text class="group-count">{{ g.items.length }}</text>
          </view>
          <view class="glass task-card" v-for="n in g.items" :key="n.id" @click="goEdit(n.id)">
            <view class="check" @click.stop="toggleDone(n)"></view>
            <view class="task-color" :style="{ background: taskColor(n.color) }" />
            <view class="task-main">
              <view class="t-title-row">
                <text class="t-title">{{ n.title }}</text>
                <text v-if="PRIORITY_META[n.priority]" class="pri-tag" :class="PRIORITY_META[n.priority].cls">
                  {{ PRIORITY_META[n.priority].label }}
                </text>
                <image v-if="n.pinned" class="pin-mark" src="/static/icons/act_pin.png" mode="widthFix" />
              </view>
              <text class="t-note" v-if="n.content">{{ n.content }}</text>
              <view class="t-meta">
                <text v-if="dueInfo(n)" class="due" :class="dueInfo(n).cls">⏰ {{ dueInfo(n).text }}</text>
                <text v-else class="due due-none">无截止时间</text>
              </view>
            </view>
            <text class="pin-btn" :class="n.pinned && 'pin-on'" @click.stop="togglePin(n)">
              {{ n.pinned ? '取消' : '置顶' }}
            </text>
          </view>
        </view>
        <view v-if="!listGroups.length && !loading" class="glass day-empty">
          <image class="empty-animal" src="/static/doodles/rabbit.png" mode="widthFix" />
          <text>今天没有待办，轻松一天</text>
        </view>
      </block>

      <!-- 看板视图 -->
      <block v-else>
        <view class="board-v" v-if="openCount || doneCount">
          <view class="glass board-sec" v-for="col in boardColumns" :key="col.key">
            <view class="board-head" :class="col.cls">
              <text>{{ col.label }}</text>
              <text class="board-count">{{ col.items.length }}</text>
            </view>
            <view class="b-row" v-for="n in col.items" :key="n.id"
              :class="{ 'task-done': n.status === 'done' }" @click="goEdit(n.id)">
              <view class="task-color" :style="{ background: taskColor(n.color) }" />
              <view class="b-main">
                <text class="b-title">{{ n.title }}</text>
                <view class="b-meta">
                  <text v-if="dueInfo(n)" class="due" :class="dueInfo(n).cls">{{ dueInfo(n).text }}</text>
                  <text v-else class="due due-none">无截止时间</text>
                  <text v-if="PRIORITY_META[n.priority]" class="pri-tag" :class="PRIORITY_META[n.priority].cls">
                    {{ PRIORITY_META[n.priority].label }}
                  </text>
                </view>
              </view>
              <text class="b-done-btn" v-if="col.key !== 'done'" @click.stop="toggleDone(n)">完成</text>
            </view>
            <view v-if="!col.items.length" class="b-empty">暂无</view>
          </view>
        </view>
        <view v-else-if="!loading" class="glass day-empty">
          <image class="empty-animal" src="/static/doodles/rabbit.png" mode="widthFix" />
          <text>还没有任务，点右下角新建</text>
        </view>
      </block>

      <view v-if="viewMode !== 'calendar'" class="fab" @click="goNewTask">＋</view>
    </block>

    <!-- ===== 想法 / 心情 ===== -->
    <block v-else>
      <view class="entry-calendar" :class="'calendar-' + entryType">
        <view class="month-head">
          <text class="month-title">{{ entryMonthTitle }}</text>
          <view class="month-nav">
            <text class="nav-arrow" @click="shiftEntryMonth(-1)">‹</text>
            <text class="today-mini" @click="entryGoToday">今天</text>
            <text class="nav-arrow" @click="shiftEntryMonth(1)">›</text>
          </view>
        </view>

        <text class="cheer">太棒了！你本月已经记录了 <text class="cheer-num">{{ entryMonthDays }}</text> 天</text>

        <view class="week-head">
          <text v-for="w in weekDaysHeader" :key="'e' + w">{{ w }}</text>
        </view>
        <view class="month-grid">
          <view v-for="c in entryCalCells" :key="'e' + c.key"
            class="mcell"
            :class="{
              muted: !c.inMonth,
              'is-recorded': c.recorded,
              'is-today': c.isToday,
              'is-selected': c.selected,
            }"
            @click="pickEntryDate(c)">
            <text class="mday">{{ c.day }}</text>
            <text v-if="c.recorded" class="mico">{{ entryIcon }}</text>
          </view>
        </view>
      </view>

      <view v-if="focusDate" class="focus-bar">
        <text>只看 {{ focusLabel }} 的记录</text>
        <text class="focus-clear" @click="focusDate = ''">查看全部</text>
      </view>

      <view id="record-timeline" class="timeline">
        <view v-if="loading" class="entry-loading">
          <view class="skeleton" v-for="i in 2" :key="i" />
        </view>

        <block v-else-if="entryGroups.length">
          <view v-for="g in entryGroups" :key="g.date" class="tl-group">
            <view class="tl-date">
              <view class="tl-square" />
              <text class="tl-date-text">{{ g.label }}</text>
              <text class="tl-count">{{ g.items.length }} 条</text>
            </view>

            <view v-for="(n, idx) in g.items" :key="n.id" class="entry-row">
              <view class="entry-time">
                <text class="time-main">{{ entryTime(n) }}</text>
              </view>
              <view class="entry-rail">
                <view class="rail-dot" />
                <view v-if="idx < g.items.length - 1" class="rail-line" />
              </view>
              <view class="entry-card" :class="'card-' + entryType" @click="goEdit(n.id)">
                <view class="card-tape" />
                <view class="card-top">
                  <view class="entry-badge" :class="'badge-' + entryType">
                    <text class="badge-icon">{{ entryIcon }}</text>
                    <text>{{ entryLabel }}</text>
                  </view>
                  <text class="card-arrow">›</text>
                </view>
                <text class="card-title">{{ n.title }}</text>
                <text v-if="n.content" class="card-body">{{ n.content }}</text>
                <view v-if="entryPhotos(n).length" class="entry-photos">
                  <image v-for="(src, idx) in entryPhotos(n)" :key="idx"
                    class="entry-photo" :src="src" mode="aspectFill"
                    @click.stop="previewPhoto(n, idx)" />
                </view>
                <view class="entry-ai-tip">
                  <text class="entry-ai-name">小知：</text>
                  <text class="entry-ai-text">{{ entryTip(n) }}</text>
                </view>
              </view>
            </view>
          </view>
        </block>

        <view v-else class="entry-empty">
          <image class="empty-animal" src="/static/doodles/rabbit.png" mode="widthFix" />
          <text class="empty-title">还没有{{ entryLabel }}记录</text>
          <text class="empty-sub">在下方写一句话，就可以开始</text>
        </view>
      </view>

      <view class="quick-dock">
        <view class="quick-bar" @keyup.enter.stop.prevent="saveQuick">
          <text class="quick-plus" @click="goNewEntry">＋</text>
          <input class="quick-input" v-model="quickDraft" :placeholder="quickPlaceholder"
            placeholder-class="quick-ph" confirm-type="send" :maxlength="500"
            @confirm="saveQuick" />
          <view class="quick-send" :class="{ 'send-on': quickDraft.trim() && !quickSaving }" @click="saveQuick">
            <text>{{ quickSaving ? '…' : '→' }}</text>
          </view>
        </view>
      </view>
    </block>

    <!-- 类型下拉 -->
    <view v-if="typeMenu" class="type-mask" @click="typeMenu = false">
      <view class="type-pop" @click.stop>
        <view v-for="t in TYPES" :key="t.key"
          class="type-row" :class="{ 'type-row-on': entryType === t.key }"
          @click="switchType(t.key)">
          <view class="type-bubble" :class="'bubble-' + t.key">{{ t.icon }}</view>
          <view class="type-copy">
            <text class="type-label">{{ t.label }}</text>
            <text class="type-desc">{{ t.desc }}</text>
          </view>
          <text v-if="entryType === t.key" class="type-check">✓</text>
        </view>
      </view>
    </view>
  </view>
</template>

<style scoped>
.record-page {
  min-height: 100vh;
  padding-bottom: 60rpx;
  color: #3A3F58;
  background-color: #FBF8F1;
}
.theme-todo {
  --accent: #C9943C;
  --accent-strong: #A97725;
  --soft: #FFF4DC;
  --softer: #FFFBF0;
  --line: #F1DFC0;
  --tape: #F5D9A8;
  background: linear-gradient(180deg, #FBF8F1 0%, #FDFBF6 58%, #FFFDF9 100%);
}
.theme-idea {
  --accent: #7A5FD3;
  --accent-strong: #5F43C0;
  --soft: #F0E9FF;
  --softer: #F9F5FF;
  --line: #E3D8FB;
  --tape: #D9C8FF;
  --ai-bg: #F2ECFF;
  --ai-text: #6D6186;
  background: linear-gradient(180deg, #F5F0FF 0%, #FBF8FF 58%, #FFFDF9 100%);
}
.theme-mood {
  --accent: #D95D80;
  --accent-strong: #C04468;
  --soft: #FFE6ED;
  --softer: #FFF5F7;
  --line: #F7D3DF;
  --tape: #F6C2D1;
  --ai-bg: #FFF0F4;
  --ai-text: #856571;
  background: linear-gradient(180deg, #FFF0F4 0%, #FFF8FA 58%, #FFFDF9 100%);
}
.status-space { height: var(--status-bar-height, 0px); }

/* ---------- 顶部 ---------- */
.record-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  padding: 26rpx 28rpx 12rpx;
}
.head-copy { min-width: 0; }
.head-title-row { display: flex; align-items: center; gap: 14rpx; }
.record-title {
  font-size: 52rpx;
  line-height: 1.15;
  font-weight: 900;
  letter-spacing: 4rpx;
  color: #3B3350;
}
.ai-link {
  font-size: 22rpx;
  font-weight: 700;
  color: var(--accent-strong);
  background: rgba(255, 253, 250, .72);
  border: 1rpx solid var(--line);
  border-radius: 999rpx;
  padding: 6rpx 14rpx;
  white-space: nowrap;
}
.record-sub {
  display: block;
  margin-top: 8rpx;
  font-size: 24rpx;
  color: #9A90A8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.head-right { display: flex; align-items: center; gap: 14rpx; flex-shrink: 0; }
.type-pill {
  display: flex;
  align-items: center;
  gap: 7rpx;
  height: 62rpx;
  padding: 0 18rpx;
  border-radius: 999rpx;
  background: rgba(255, 253, 250, .92);
  border: 2rpx solid var(--line);
  box-shadow: 0 8rpx 22rpx rgba(94, 70, 110, .08);
}
.type-pill:active { opacity: .8; }
.type-icon { color: var(--accent); font-size: 28rpx; font-weight: 900; line-height: 1; }
.type-name { color: #443A52; font-size: 27rpx; font-weight: 800; }
.type-caret { color: #ADA3B5; font-size: 22rpx; margin-top: -4rpx; }
.head-avatar {
  width: 66rpx;
  height: 66rpx;
  border-radius: 50%;
  background: var(--soft);
  border: 4rpx solid rgba(255, 255, 255, .92);
  box-shadow: 0 8rpx 20rpx rgba(94, 70, 110, .12);
}

.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20rpx;
  margin: 10rpx 24rpx 0;
  padding: 16rpx 22rpx;
  border-radius: 20rpx;
  background: #FFF0F0;
  color: #C55858;
  font-size: 24rpx;
}
.error-text { flex: 1; min-width: 0; }
.error-retry { flex-shrink: 0; font-weight: 800; }

/* ---------- 待办：原任务界面 ---------- */
.todo-tools { padding: 8rpx 24rpx 0; }
.search-box {
  display: flex;
  align-items: center;
  gap: 12rpx;
  height: 76rpx;
  padding: 0 20rpx 0 26rpx;
  border-radius: 999rpx;
  background: #FFFDF8;
  border: 1rpx solid #E9E5F4;
  box-shadow: 0 8rpx 22rpx rgba(124, 139, 255, .08);
}
.search-input { flex: 1; height: 100%; font-size: 27rpx; }
.ph { color: #C3C7DA; }
.search-clear { color: #B5A9C0; font-size: 32rpx; line-height: 1; padding: 0 4rpx; }
.search-btn { color: #9A742E; font-size: 26rpx; font-weight: 700; }
.loading-strip { margin: 14rpx 30rpx 0; font-size: 24rpx; color: #9A90A8; }

.glass {
  background: #FFFDF8;
  border: 1rpx solid #E9E5F4;
  box-shadow: 0 10rpx 26rpx rgba(124, 139, 255, .10);
  border-radius: 28rpx;
}

.view-switch { display: flex; align-items: center; gap: 12rpx; margin: 18rpx 24rpx 6rpx; flex-wrap: wrap; }
.v-btn {
  font-size: 26rpx;
  color: #6F748C;
  background: #FFFDF8;
  border-radius: 999rpx;
  padding: 8rpx 24rpx;
  border: 1rpx solid rgba(255, 255, 255, .7);
}
.v-active { background: #8B7FE8; color: #fff; font-weight: 700; }
.v-stat { margin-left: auto; font-size: 24rpx; color: #6F748C; }

.cal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8rpx 24rpx 12rpx;
  padding: 18rpx 22rpx;
}
.cal-title { font-size: 32rpx; font-weight: 800; color: #4A4F6B; letter-spacing: 1rpx; }
.cal-actions { display: flex; align-items: center; gap: 12rpx; }
.cal-btn { font-size: 38rpx; color: #6B7089; padding: 0 10rpx; }
.cal-today-btn {
  font-size: 25rpx;
  color: #6C7BF5;
  background: #EFF1FF;
  border-radius: 999rpx;
  padding: 8rpx 20rpx;
}

.cal-panel { margin: 0 8rpx 14rpx; padding: 12rpx 4rpx 10rpx; }
.cal-week { display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 8rpx; }
.cal-week text { text-align: center; font-size: 24rpx; color: #6F748C; }
.cal-week .wk { color: #C77BA6; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2rpx; }
.cal-cell {
  min-height: 136rpx;
  border-radius: 16rpx;
  padding: 6rpx 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  box-sizing: border-box;
  border: 2rpx solid transparent;
}
.cal-cell.dim .cal-num { color: #C3C7DA; }
.cal-cell.today { border-color: #C9BFF0; }
.cal-cell.sel { background: #EFEAFE; border: 2rpx dashed #8B7FE8; }
.cal-num { font-size: 26rpx; font-weight: 700; color: #4A4F6B; text-align: center; line-height: 32rpx; }
.cal-cell.today .cal-num { color: #8B7FE8; font-weight: 800; }
.cal-tags { display: flex; flex-direction: column; gap: 3rpx; margin-top: 2rpx; min-width: 0; }
.cal-tag {
  display: flex;
  align-items: center;
  border-radius: 8rpx;
  padding: 2rpx;
  overflow: hidden;
  max-width: 100%;
  box-sizing: border-box;
}
.tag-text {
  flex: 1;
  min-width: 0;
  font-size: 18rpx;
  color: #2F3448;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cal-more { font-size: 20rpx; color: #6F748C; padding-left: 4rpx; }

.day-tasks { margin: 0 24rpx; padding: 22rpx 22rpx 12rpx; }
.day-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14rpx;
  border-bottom: 1rpx dashed rgba(231, 227, 244, .9);
}
.day-head-left { display: flex; flex-direction: column; gap: 4rpx; }
.day-date { font-size: 30rpx; font-weight: 800; color: #4A4F6B; }
.day-count { font-size: 24rpx; color: #7A7F96; }
.day-add { font-size: 26rpx; color: #6C7BF5; font-weight: 600; }
.day-list { display: flex; flex-direction: column; }
.task-row { display: flex; align-items: flex-start; gap: 14rpx; padding: 18rpx 0; border-bottom: 1rpx dashed rgba(231, 227, 244, .8); }
.task-row:last-child { border-bottom: none; }
.task-done .t-title { text-decoration: line-through; color: #A6AAC2; }
.task-done { opacity: .78; }
.check {
  width: 42rpx;
  height: 42rpx;
  border-radius: 21rpx;
  border: 3rpx solid #D6D9E8;
  flex-shrink: 0;
  margin-top: 2rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 26rpx;
  background: rgba(255, 253, 248, .7);
}
.check.checked { background: #1FA97F; border-color: #1FA97F; }
.task-color { width: 12rpx; align-self: stretch; border-radius: 6rpx; flex-shrink: 0; margin-top: 2rpx; }
.task-main { flex: 1; min-width: 0; }
.t-title-row { display: flex; align-items: center; gap: 10rpx; flex-wrap: wrap; }
.t-title { font-size: 29rpx; font-weight: 600; color: #3A3F58; }
.t-note {
  display: block;
  font-size: 25rpx;
  color: #6F748C;
  margin-top: 6rpx;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.t-meta { display: flex; align-items: center; gap: 14rpx; margin-top: 8rpx; }
.t-time { font-size: 24rpx; color: #6F748C; }
.t-done-label { font-size: 23rpx; color: #1FA97F; background: #E9F8F2; border-radius: 8rpx; padding: 2rpx 10rpx; }
.pri-tag { font-size: 22rpx; border-radius: 8rpx; padding: 2rpx 10rpx; font-weight: 700; }
.pri-high { background: #FFEDEE; color: #E45858; }
.pri-low { background: rgba(244, 242, 250, .9); color: #8A90A8; }
.pin-mark { width: 26rpx; height: 26rpx; }
.day-empty { padding: 40rpx 10rpx; text-align: center; font-size: 26rpx; color: #A6AAC2; }
.empty-animal { width: 140rpx; display: block; margin: 0 auto 10rpx; }
.empty-add {
  width: 240rpx;
  height: 66rpx;
  margin: 22rpx auto 0;
  border-radius: 999rpx;
  background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  color: #fff;
  font-size: 25rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8rpx 20rpx rgba(124, 139, 255, .26);
}

/* ---------- 待办时间轴（日历下方） ---------- */
.todo-feed { margin: 18rpx 24rpx 0; }
.todo-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 6rpx 4rpx 12rpx;
  padding: 12rpx 18rpx;
  border-radius: 16rpx;
  background: rgba(255, 253, 250, .78);
  border: 1rpx dashed #E6DCCB;
  font-size: 23rpx;
  color: #7A7167;
}
.todo-filter-clear { color: #6C7BF5; font-weight: 700; }
.todo-group { margin-bottom: 10rpx; }
.todo-date-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12rpx;
  margin: 14rpx 4rpx 12rpx;
  padding-right: 108rpx;
}
.todo-date-square {
  width: 14rpx;
  height: 14rpx;
  border-radius: 4rpx;
  background: #5C73D8;
  transform: rotate(8deg);
}
.todo-date-label { font-size: 29rpx; font-weight: 800; color: #3F4775; letter-spacing: .5rpx; }
.todo-date-count { margin-left: auto; font-size: 22rpx; color: #A6AAC2; }
.todo-date-add {
  position: absolute;
  top: -36rpx;
  right: -2rpx;
  z-index: 6;
  width: 96rpx;
  height: 96rpx;
  border-radius: 50%;
  border: 4rpx solid rgba(255, 255, 255, .9);
  background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  color: #fff;
  font-size: 56rpx;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 14rpx 30rpx rgba(124, 139, 255, .38);
}

.todo-row { display: flex; align-items: stretch; }
.todo-time { width: 78rpx; flex-shrink: 0; padding-top: 18rpx; }
.todo-time text { font-size: 23rpx; color: #8C93A8; }
.todo-rail { width: 28rpx; flex-shrink: 0; position: relative; }
.todo-rail-dot {
  position: absolute;
  top: 25rpx;
  left: 8rpx;
  width: 11rpx;
  height: 11rpx;
  border-radius: 50%;
  background: #F2B45C;
  box-shadow: 0 0 0 5rpx #FFF9EE;
  z-index: 1;
}
.todo-rail-dot.done { background: #1FA97F; box-shadow: 0 0 0 5rpx #EEFAF5; }
.todo-rail-line {
  position: absolute;
  top: 38rpx;
  bottom: -10rpx;
  left: 13rpx;
  width: 2rpx;
  background: #E8DFD0;
}

.todo-card {
  flex: 1;
  min-width: 0;
  margin-bottom: 22rpx;
  padding: 18rpx 20rpx 18rpx;
  border-radius: 24rpx;
  background: #FFFDF8;
  border: 1rpx solid #EEE6D8;
  box-shadow: 0 10rpx 26rpx rgba(157, 120, 62, .08);
}
.todo-card:active { opacity: .9; }
.todo-card-done { background: #FFFEFA; }
.todo-card-top { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.todo-badge {
  display: inline-flex;
  align-items: center;
  gap: 5rpx;
  padding: 4rpx 13rpx;
  border-radius: 999rpx;
  background: #FFF2D8;
  color: #B87918;
  font-size: 21rpx;
  font-weight: 700;
}
.todo-badge-icon { font-size: 19rpx; }
.todo-remind {
  padding: 4rpx 12rpx;
  border-radius: 999rpx;
  background: #FFF5DF;
  color: #B87918;
  font-size: 21rpx;
  font-weight: 600;
  flex-shrink: 0;
}
.todo-remind-none { background: #F6F2EA; color: #A69D91; font-weight: 500; }

.todo-main { display: flex; align-items: flex-start; gap: 14rpx; margin-top: 12rpx; }
.todo-check {
  width: 38rpx;
  height: 38rpx;
  border-radius: 50%;
  border: 3rpx solid #D9CDB9;
  flex-shrink: 0;
  margin-top: 3rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 24rpx;
  background: #FFFDF8;
}
.todo-check.checked { background: #1FA97F; border-color: #1FA97F; }
.todo-copy { flex: 1; min-width: 0; }
.todo-title-row { display: flex; align-items: center; gap: 9rpx; flex-wrap: wrap; }
.todo-title { font-size: 30rpx; line-height: 1.5; font-weight: 700; color: #3A3F58; word-break: break-all; }
.todo-card-done .todo-title { color: #5B6177; }
.todo-desc {
  display: block;
  margin-top: 4rpx;
  font-size: 25rpx;
  line-height: 1.65;
  color: #7A7F96;
  word-break: break-all;
}
.todo-loc { display: flex; align-items: center; gap: 7rpx; margin: 10rpx 0 0 52rpx; font-size: 22rpx; color: #9AA0B5; }
.todo-loc-icon { color: #B9AEA0; font-size: 24rpx; }

.todo-ai-tip {
  display: flex;
  align-items: flex-start;
  margin-top: 14rpx;
  padding: 12rpx 16rpx;
  border-radius: 14rpx;
  background: #EFF5FF;
  line-height: 1.65;
}
.todo-ai-name { flex-shrink: 0; font-size: 22rpx; font-weight: 800; color: #4D7BD6; }
.todo-ai-text { font-size: 22rpx; color: #6B7A99; word-break: break-all; }

.group { margin-top: 8rpx; }
.group-head { display: flex; align-items: center; gap: 10rpx; margin: 16rpx 28rpx 6rpx; }
.g-dot { width: 14rpx; height: 14rpx; border-radius: 7rpx; }
.g-over { background: #E45858; }
.g-today { background: #F2B45C; }
.g-week { background: #6C7BF5; }
.g-later { background: #B9AEDC; }
.group-title { font-size: 27rpx; font-weight: 700; color: #4A4F6B; }
.group-count { font-size: 24rpx; color: #A6AAC2; }
.task-card { display: flex; align-items: flex-start; margin: 12rpx 24rpx; padding: 20rpx 18rpx; gap: 12rpx; }
.task-card:active { opacity: .85; }
.due { font-size: 24rpx; }
.due-over { color: #E45858; font-weight: 700; }
.due-today { color: #F2A93B; font-weight: 600; }
.due-soon { color: #6C7BF5; }
.due-normal { color: #7A7F96; }
.due-none { color: #9AA0B5; }
.pin-btn { font-size: 25rpx; color: #A6AAC2; padding: 6rpx 0 6rpx 10rpx; flex-shrink: 0; }
.pin-on { color: #6C7BF5; font-weight: 700; }

.board-v { padding: 0 24rpx; display: flex; flex-direction: column; gap: 16rpx; margin-top: 10rpx; }
.board-sec { padding: 20rpx 22rpx 12rpx; }
.board-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 28rpx;
  font-weight: 800;
  padding-bottom: 12rpx;
  border-bottom: 1rpx dashed rgba(231, 227, 244, .9);
}
.board-count { font-size: 24rpx; color: #8A90A8; }
.col-over .board-head { color: #E45858; }
.col-open .board-head { color: #6C7BF5; }
.col-done .board-head { color: #1FA97F; }
.b-row { display: flex; align-items: flex-start; gap: 14rpx; padding: 16rpx 0; border-bottom: 1rpx dashed rgba(231, 227, 244, .8); }
.b-row:last-child { border-bottom: none; }
.b-main { flex: 1; min-width: 0; }
.b-title { font-size: 28rpx; font-weight: 600; color: #3A3F58; }
.b-meta { display: flex; align-items: center; gap: 10rpx; margin-top: 8rpx; flex-wrap: wrap; }
.b-done-btn {
  font-size: 25rpx;
  color: #6C7BF5;
  border: 2rpx solid #C9CFFF;
  border-radius: 999rpx;
  padding: 6rpx 18rpx;
  flex-shrink: 0;
}
.b-empty { text-align: center; font-size: 25rpx; color: #C3C7DA; padding: 22rpx 0; }

.fab {
  position: fixed;
  right: 40rpx;
  bottom: 200rpx;
  width: 108rpx;
  height: 108rpx;
  border-radius: 54rpx;
  background: linear-gradient(135deg, #7C8BFF, #A78BFA);
  color: #fff;
  font-size: 56rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12rpx 28rpx rgba(124, 139, 255, .35);
  z-index: 10;
}
.fab:active { opacity: .85; }

/* ---------- 想法 / 心情月历 ---------- */
.entry-calendar {
  margin: 18rpx 24rpx 0;
  padding: 24rpx 22rpx 18rpx;
  border-radius: 38rpx;
  background: linear-gradient(150deg, var(--soft) 0%, var(--softer) 72%, rgba(255, 253, 250, .96) 100%);
  border: 1rpx solid var(--line);
  box-shadow: 0 16rpx 38rpx rgba(94, 70, 110, .09);
}
.month-head { display: flex; align-items: center; justify-content: space-between; }
.month-title { font-size: 34rpx; font-weight: 900; color: #3F3454; letter-spacing: 1rpx; }
.month-nav { display: flex; align-items: center; gap: 10rpx; }
.nav-arrow {
  width: 48rpx;
  height: 48rpx;
  border-radius: 50%;
  background: rgba(255, 255, 255, .6);
  color: var(--accent-strong);
  font-size: 34rpx;
  line-height: 44rpx;
  text-align: center;
}
.today-mini {
  font-size: 22rpx;
  font-weight: 700;
  color: var(--accent-strong);
  background: rgba(255, 255, 255, .65);
  border-radius: 999rpx;
  padding: 8rpx 16rpx;
}
.cheer { display: block; margin-top: 10rpx; font-size: 24rpx; color: var(--accent-strong); font-weight: 600; }
.cheer-num { font-size: 32rpx; font-weight: 900; padding: 0 6rpx; }
.week-head { display: grid; grid-template-columns: repeat(7, 1fr); margin: 16rpx 0 6rpx; }
.week-head text { text-align: center; font-size: 21rpx; color: var(--accent); opacity: .68; }
.month-grid { display: grid; grid-template-columns: repeat(7, 1fr); row-gap: 4rpx; }
.mcell {
  min-height: 78rpx;
  border-radius: 18rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rpx;
  border: 2rpx solid transparent;
  box-sizing: border-box;
}
.mcell.muted { opacity: .22; }
.mcell.is-recorded { background: rgba(255, 255, 255, .5); }
.mday { font-size: 25rpx; font-weight: 650; color: #4A4058; line-height: 1.2; }
.mico { font-size: 17rpx; line-height: 17rpx; color: var(--accent); }
.mcell.is-today { border-color: var(--accent); }
.mcell.is-selected {
  background: linear-gradient(145deg, var(--accent), var(--accent-strong));
  box-shadow: 0 8rpx 18rpx rgba(94, 70, 110, .16);
}
.mcell.is-selected .mday,
.mcell.is-selected .mico { color: #fff; }

.focus-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 16rpx 28rpx 0;
  padding: 14rpx 20rpx;
  border-radius: 18rpx;
  background: rgba(255, 253, 250, .82);
  border: 1rpx dashed var(--line);
  font-size: 24rpx;
  color: #756B80;
}
.focus-clear { color: var(--accent-strong); font-weight: 700; }

/* ---------- 时间轴 ---------- */
.timeline { padding: 24rpx 24rpx 0; }
.tl-group { margin-bottom: 8rpx; }
.tl-date { display: flex; align-items: center; gap: 12rpx; margin: 8rpx 4rpx 14rpx; }
.tl-square { width: 14rpx; height: 14rpx; border-radius: 4rpx; background: var(--accent); transform: rotate(8deg); }
.tl-date-text { font-size: 30rpx; font-weight: 800; color: #40364F; letter-spacing: .5rpx; }
.tl-count { margin-left: auto; font-size: 22rpx; color: #A69DAD; }

.entry-row { display: flex; align-items: stretch; }
.entry-time { width: 82rpx; flex-shrink: 0; padding-top: 18rpx; }
.time-main { font-size: 23rpx; color: #9A90A8; }
.entry-rail { width: 30rpx; flex-shrink: 0; position: relative; }
.rail-dot {
  position: absolute;
  top: 26rpx;
  left: 9rpx;
  width: 10rpx;
  height: 10rpx;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 5rpx var(--softer);
  z-index: 1;
}
.rail-line {
  position: absolute;
  top: 38rpx;
  bottom: -8rpx;
  left: 13rpx;
  width: 2rpx;
  background: var(--line);
}
.entry-card {
  flex: 1;
  min-width: 0;
  position: relative;
  margin-bottom: 24rpx;
  padding: 22rpx 24rpx 20rpx;
  border-radius: 26rpx;
  background: #FFFDFB;
  border: 1rpx solid #F1EAF0;
  box-shadow: 0 12rpx 30rpx rgba(94, 70, 110, .09);
}
.entry-card:active { transform: translateY(2rpx); opacity: .9; }
.card-tape {
  position: absolute;
  top: -8rpx;
  left: 50%;
  width: 78rpx;
  height: 16rpx;
  border-radius: 4rpx;
  background: var(--tape);
  opacity: .68;
  transform: translateX(-50%) rotate(-2deg);
}
.card-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10rpx; }
.entry-badge {
  display: inline-flex;
  align-items: center;
  gap: 6rpx;
  padding: 4rpx 14rpx;
  border-radius: 999rpx;
  background: var(--soft);
  color: var(--accent-strong);
  font-size: 21rpx;
  font-weight: 700;
}
.badge-icon { font-size: 19rpx; line-height: 1; }
.card-arrow { color: #C2B8C8; font-size: 30rpx; line-height: 1; }
.card-title {
  display: block;
  font-size: 31rpx;
  line-height: 1.5;
  font-weight: 800;
  color: #3D3552;
  word-break: break-all;
}
.card-body {
  display: block;
  margin-top: 10rpx;
  font-size: 27rpx;
  line-height: 1.85;
  color: #6D6478;
  white-space: pre-wrap;
  word-break: break-all;
}
.entry-photos {
  display: flex;
  flex-wrap: wrap;
  gap: 10rpx;
  margin-top: 14rpx;
}
.entry-photo {
  width: 152rpx;
  height: 152rpx;
  flex-shrink: 0;
  border-radius: 14rpx;
  background: var(--soft);
  border: 1rpx solid var(--line);
}
.entry-ai-tip {
  display: flex;
  align-items: flex-start;
  margin-top: 14rpx;
  padding: 12rpx 16rpx;
  border-radius: 14rpx;
  background: var(--ai-bg);
  line-height: 1.65;
}
.entry-ai-name {
  flex-shrink: 0;
  font-size: 22rpx;
  font-weight: 800;
  color: var(--accent-strong);
}
.entry-ai-text {
  font-size: 22rpx;
  color: var(--ai-text);
  word-break: break-all;
}

.entry-loading { padding: 6rpx 0; }
.skeleton {
  height: 180rpx;
  margin: 0 0 22rpx 112rpx;
  border-radius: 26rpx;
  background: linear-gradient(90deg, rgba(255, 253, 250, .62), rgba(255, 255, 255, .94), rgba(255, 253, 250, .62));
  background-size: 200% 100%;
  animation: shimmer 1.4s linear infinite;
}
@keyframes shimmer {
  0% { background-position: 120% 0; }
  100% { background-position: -80% 0; }
}
.entry-empty { padding: 60rpx 20rpx 80rpx; text-align: center; }
.empty-title { display: block; font-size: 28rpx; font-weight: 700; color: #70667B; }
.empty-sub { display: block; margin-top: 8rpx; font-size: 23rpx; color: #A69DAD; }

/* ---------- 底部一句话记录 ---------- */
.quick-dock {
  position: fixed;
  left: 24rpx;
  right: 24rpx;
  bottom: calc(112rpx + env(safe-area-inset-bottom));
  z-index: 20;
}
.quick-bar {
  display: flex;
  align-items: center;
  height: 92rpx;
  padding: 0 12rpx 0 18rpx;
  border-radius: 999rpx;
  background: rgba(255, 253, 250, .97);
  border: 1rpx solid var(--line);
  box-shadow: 0 16rpx 40rpx rgba(94, 70, 110, .16);
}
.quick-plus {
  width: 56rpx;
  height: 56rpx;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--soft);
  color: var(--accent-strong);
  font-size: 34rpx;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.quick-input { flex: 1; height: 100%; padding: 0 16rpx; font-size: 26rpx; }
.quick-ph { color: #B7AEBB; }
.quick-send {
  width: 62rpx;
  height: 62rpx;
  flex-shrink: 0;
  border-radius: 50%;
  background: #E9E2E6;
  color: #fff;
  font-size: 32rpx;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
}
.quick-send.send-on {
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  box-shadow: 0 8rpx 18rpx rgba(94, 70, 110, .2);
}

/* ---------- 类型下拉 ---------- */
.type-mask { position: fixed; inset: 0; z-index: 50; background: rgba(52, 42, 62, .05); }
.type-pop {
  position: fixed;
  top: calc(var(--status-bar-height, 0px) + 128rpx);
  right: 104rpx;
  width: 340rpx;
  padding: 12rpx;
  border-radius: 28rpx;
  background: #FFFDFB;
  border: 1rpx solid #F0E7F2;
  box-shadow: 0 26rpx 64rpx rgba(60, 40, 80, .2);
}
.type-pop::before {
  content: '';
  position: absolute;
  top: -12rpx;
  right: 86rpx;
  width: 24rpx;
  height: 24rpx;
  background: #FFFDFB;
  border-left: 1rpx solid #F0E7F2;
  border-top: 1rpx solid #F0E7F2;
  transform: rotate(45deg);
}
.type-row { display: flex; align-items: center; gap: 14rpx; padding: 14rpx 12rpx; border-radius: 20rpx; }
.type-row-on { background: var(--softer); }
.type-bubble {
  width: 54rpx;
  height: 54rpx;
  flex-shrink: 0;
  border-radius: 18rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 26rpx;
  font-weight: 900;
  background: #F6F1FA;
  color: #7A5FD3;
}
.bubble-todo { background: #FFF3DA; color: #B8842B; }
.bubble-idea { background: #EFE7FF; color: #6E51C9; }
.bubble-mood { background: #FFE7EE; color: #D35D80; }
.type-copy { flex: 1; min-width: 0; }
.type-label { display: block; font-size: 27rpx; font-weight: 800; color: #3D3552; }
.type-desc { display: block; margin-top: 2rpx; font-size: 21rpx; color: #A49BAE; }
.type-check { color: var(--accent); font-size: 26rpx; font-weight: 900; }
</style>
