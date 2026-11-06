/** 统一未读状态：首页、Agent、我的、TabBar 共用。 */
import { reactive } from 'vue'
import { apiNotificationSummary } from '../api/index.js'

export const notificationState = reactive({
  total: 0,
  unique: 0,
  budget: 0,
  agent: 0,
  byLevel: {},
  loaded: false,
  loading: false,
})

function setBadge(value) {
  const text = value > 99 ? '99+' : String(value)
  try {
    if (value > 0) {
      uni.setTabBarBadge({ index: 2, text })
    } else {
      uni.removeTabBarBadge({ index: 2 })
    }
  } catch (e) { /* 非 tab 环境忽略 */ }
}

export async function refreshNotifications() {
  if (notificationState.loading) return notificationState
  notificationState.loading = true
  try {
    const data = await apiNotificationSummary()
    notificationState.total = data.total_unread || 0
    notificationState.unique = data.unique_unread || 0
    notificationState.budget = data.budget_unread || 0
    notificationState.agent = data.agent_unread || 0
    notificationState.byLevel = data.by_level || {}
    notificationState.loaded = true
    setBadge(notificationState.unique)
  } catch (e) {
    /* 未登录或网络失败时保持旧值，不阻塞页面 */
  } finally {
    notificationState.loading = false
  }
  return notificationState
}

export function clearNotificationBadge() {
  notificationState.total = 0
  notificationState.unique = 0
  notificationState.budget = 0
  notificationState.agent = 0
  setBadge(0)
}

export function goNotifications() {
  uni.navigateTo({ url: '/pages/notifications/notifications' })
}
