/** CSV 导入页专用 API。 */
import http, { getBaseUrl } from './request.js'
import store from '../store/user.js'

export const apiCsvTemplate = () => http.get('/api/imports/template')

export const apiPreviewCsvText = (text, filename = '') =>
  http.post('/api/imports/preview', { text, filename })

export const apiConfirmCsv = (rows, filename = '') =>
  http.post('/api/imports/confirm', { rows, filename })

export const apiPreviewCsvFile = (filePath, filename = '') => new Promise((resolve, reject) => {
  uni.uploadFile({
    url: getBaseUrl() + '/api/imports/preview-file',
    filePath,
    name: 'file',
    timeout: 60000,
    header: store.token ? { Authorization: 'Bearer ' + store.token } : {},
    success(res) {
      let body = {}
      try { body = JSON.parse(res.data) } catch (e) { body = {} }
      if (res.statusCode >= 200 && res.statusCode < 300) {
        resolve(body)
      } else {
        const message = body.message || `预览失败（${res.statusCode}）`
        uni.showToast({ title: message, icon: 'none' })
        reject({ status: res.statusCode, message, body })
      }
    },
    fail() {
      const message = '文件上传失败，请检查网络或改用粘贴 CSV'
      uni.showToast({ title: message, icon: 'none' })
      reject({ status: -1, message, body: null })
    },
  })
})
