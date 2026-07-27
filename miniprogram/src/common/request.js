// 基于 uni.request 的请求封装（替代网页版的 fetch）。
import { BASE_URL } from './config.js'

// 统一请求：成功返回 data，失败抛出带 message 的 Error（与网页版 request 行为一致）
export function request(path, options = {}) {
  return new Promise((resolve, reject) => {
    uni.request({
      url: BASE_URL + path,
      method: options.method || 'GET',
      data: options.data,
      header: {
        'Content-Type': 'application/json',
        ...(options.header || {}),
      },
      timeout: options.timeout || 15000,
      success: (res) => {
        const data = res.data || {}
        // 2xx 视为成功
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data)
        } else {
          reject(new Error(data.error || `请求失败 (${res.statusCode})`))
        }
      },
      fail: (err) => {
        reject(new Error(err.errMsg || '网络请求失败'))
      },
    })
  })
}
