/**
 * 后端服务地址（默认值）。
 *
 * - 本地 H5 开发：默认 http://127.0.0.1:8000
 * - 公网 H5 部署：使用同源地址，由 Nginx 把 /api 反向代理到后端
 * - App/真机：在登录页「服务器设置」或「我的 → 服务器地址」填写局域网/公网地址
 */
function defaultBaseUrl() {
  // #ifdef H5
  if (typeof window !== 'undefined' && window.location) {
    const host = window.location.hostname
    if (host && host !== 'localhost' && host !== '127.0.0.1') {
      return window.location.origin
    }
  }
  // #endif
  return 'http://127.0.0.1:8000'
}

export const BASE_URL = defaultBaseUrl()
