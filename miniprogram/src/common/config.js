// 后端 API 基地址配置。
//
// ⚠️ 微信小程序只能请求 https:// 且已在「微信公众平台 → 开发管理 → 服务器域名 →
//    request 合法域名」里配置过的域名，不能用 IP / localhost。
//
// 开发调试时，可在「微信开发者工具 → 详情 → 本地设置」勾选
//   "不校验合法域名、web-view、TLS 版本以及 HTTPS 证书"，
//   即可临时访问本地后端（如 http://127.0.0.1:5001）。
//
// === 配置线上后端地址 ===
//
// 方式 1（推荐）：编译时通过环境变量传入，不用改代码
//   VITE_API_BASE=https://weixin.your-domain.com npm run build:mp-weixin
//   VITE_API_BASE=https://weixin.your-domain.com npm run dev:mp-weixin:prod
//
// 方式 2：直接改下面 __VITE_PROD_BASE__ 的 fallback 默认值
//
// === 配置微信 AppID ===
//
// 同样通过环境变量注入（由 vite-plugin-inject-appid.js 在构建后写入 project.config.json）：
//   VITE_WX_APPID=wx1234567890 npm run build:mp-weixin
// 不设时保持 uni-app 默认值 "touristappid"（游客模式，无法真机预览/上传）
//
// === 开发模式切换 ===
//   npm run dev:mp-weixin          → 本地后端 (http://127.0.0.1:5001)
//   npm run dev:mp-weixin:prod    → 线上后端（需同时设 VITE_API_BASE）

// 开发环境：本机 Flask（需在开发者工具关闭域名校验）
const DEV_BASE = 'http://127.0.0.1:5001'

// 生产环境线上地址：由 Vite define 注入 __VITE_PROD_BASE__，
//   来源 = 环境变量 VITE_API_BASE；未设时用下方的 fallback。
const __prodBaseFallback = 'https://weixin.your-domain.com'
const PROD_BASE = typeof __VITE_PROD_BASE__ !== 'undefined' && __VITE_PROD_BASE__
  ? __VITE_PROD_BASE__
  : __prodBaseFallback

// 开发/生产模式切换：__VITE_API_MODE__ 由 Vite define 注入
const apiMode = typeof __VITE_API_MODE__ !== 'undefined' ? __VITE_API_MODE__ : 'local'

// #ifdef MP-WEIXIN
export const BASE_URL = (process.env.NODE_ENV === 'production' || apiMode === 'prod') ? PROD_BASE : DEV_BASE
// #endif

// #ifndef MP-WEIXIN
export const BASE_URL = DEV_BASE
// #endif
