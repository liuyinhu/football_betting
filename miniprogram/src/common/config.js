// 后端 API 基地址配置。
//
// ⚠️ 微信小程序只能请求 https:// 且已在「微信公众平台 → 开发管理 → 服务器域名 →
//    request 合法域名」里配置过的域名，不能用 IP / localhost。
//
// 开发调试时，可在「微信开发者工具 → 详情 → 本地设置」勾选
//   “不校验合法域名、web-view、TLS 版本以及 HTTPS 证书”，
//   即可临时访问本地后端（如 http://127.0.0.1:5001）。
//
// 正式发布前，请把 BASE_URL 换成你已备案 + HTTPS 的后端域名。

// 开发环境：本机 Flask（需在开发者工具关闭域名校验）
const DEV_BASE = 'http://127.0.0.1:5001'
// 生产环境：替换为你的 HTTPS 域名（必须 ICP 备案 + SSL 证书）
//   示例：'https://api.example.com'
const PROD_BASE = 'https://api.your-domain.com'

// #ifdef MP-WEIXIN
export const BASE_URL = process.env.NODE_ENV === 'development' ? DEV_BASE : PROD_BASE
// #endif

// #ifndef MP-WEIXIN
export const BASE_URL = DEV_BASE
// #endif
