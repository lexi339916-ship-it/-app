/**
 * 统一网络请求封装。
 * - 自动携带 Authorization: Bearer <token>
 * - 401 时先用刷新令牌续期一次并重试原请求；刷新失败则清空登录态并跳登录页
 * - 非 2xx 统一 toast 错误信息（后端格式 {"code":..,"message":..}）
 */
import { BASE_URL } from '../common/config.js'
import store, { clearLogin, setLogin } from '../store/user.js'

/** 当前生效的后端地址：优先使用本地保存的服务器地址（真机调试用） */
export function getBaseUrl() {
  const saved = uni.getStorageSync('api_base')
  return String(saved || BASE_URL).replace(/\/+$/, '')
}

// 单飞：同一时刻只发起一次刷新请求
let refreshPromise = null

export function refreshAccessToken() {
  if (refreshPromise) return refreshPromise
  const refreshToken = uni.getStorageSync('refresh_token')
  if (!refreshToken) return Promise.reject(new Error('NO_REFRESH_TOKEN'))

  const p = new Promise((resolve, reject) => {
    uni.request({
      url: getBaseUrl() + '/api/auth/refresh',
      method: 'POST',
      data: { refresh_token: refreshToken },
      header: { 'Content-Type': 'application/json' },
      timeout: 15000,
      success(res) {
        const body = res.data || {}
        if (res.statusCode >= 200 && res.statusCode < 300 && body.access_token) {
          setLogin(body.access_token, body.refresh_token, body.user)
          resolve(body.access_token)
        } else {
          reject(new Error('REFRESH_FAILED'))
        }
      },
      fail() {
        reject(new Error('REFRESH_NETWORK'))
      },
    })
  })
  refreshPromise = p.then(
    (v) => { refreshPromise = null; return v },
    (e) => { refreshPromise = null; throw e },
  )
  return refreshPromise
}

function toLogin(message) {
  clearLogin()
  uni.showToast({ title: message, icon: 'none' })
  setTimeout(() => {
    uni.reLaunch({ url: '/pages/login/login' })
  }, 600)
}

function request(options, retried = false) {
  const { url, method = 'GET', data = {}, header = {} } = options
  return new Promise((resolve, reject) => {
    const token = store.token
    uni.request({
      url: getBaseUrl() + url,
      method,
      data,
      timeout: 35000,
      header: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
        ...header,
      },
      success(res) {
        const status = res.statusCode
        const body = res.data
        if (status >= 200 && status < 300) {
          resolve(body)
          return
        }
        if (status === 401) {
          // 登录/注册/刷新接口本身不触发续期，避免循环
          const authEntry = ['/api/auth/login', '/api/auth/register', '/api/auth/refresh']
          const skipRefresh = authEntry.indexOf(url) !== -1
          if (!retried && !skipRefresh) {
            refreshAccessToken()
              .then(() => request(options, true))
              .then(resolve)
              .catch(() => {
                toLogin('登录已过期，请重新登录')
                reject({ status: 401, message: '登录已过期', body })
              })
            return
          }
          toLogin('请先登录')
          reject({ status: 401, message: '请先登录', body })
          return
        }
        const message = (body && body.message) || `请求失败（${status}）`
        if (status !== 429 && status !== 503) {
          uni.showToast({ title: message, icon: 'none' })
        }
        reject({ status, message, body })
      },
      fail() {
        const message = '网络连接失败，请检查后端服务是否启动'
        uni.showToast({ title: message, icon: 'none' })
        reject({ status: -1, message, body: null })
      },
    })
  })
}

export default {
  get(url, data) { return request({ url, method: 'GET', data }) },
  post(url, data) { return request({ url, method: 'POST', data }) },
  put(url, data) { return request({ url, method: 'PUT', data }) },
  delete(url) { return request({ url, method: 'DELETE' }) },
}
