/**
 * 轻量用户状态管理（基于 Vue3 reactive 的模块级单例）。
 * 职责：保存 token 与用户信息，同步本地缓存，供各页面共享。
 */
import { reactive } from 'vue'

const state = reactive({
  token: uni.getStorageSync('token') || '',
  refreshToken: uni.getStorageSync('refresh_token') || '',
  user: uni.getStorageSync('user') || null,
})

export function setLogin(token, refreshToken, user) {
  state.token = token
  if (refreshToken) state.refreshToken = refreshToken
  state.user = user
  uni.setStorageSync('token', token)
  if (refreshToken) uni.setStorageSync('refresh_token', refreshToken)
  uni.setStorageSync('user', user)
}

export function setUser(user) {
  state.user = user
  uni.setStorageSync('user', user)
}

export function clearLogin() {
  state.token = ''
  state.refreshToken = ''
  state.user = null
  uni.removeStorageSync('token')
  uni.removeStorageSync('refresh_token')
  uni.removeStorageSync('user')
}

export function isLogged() {
  return !!state.token
}

export default state
