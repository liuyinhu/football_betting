import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'
import injectWxAppid from './vite-plugin-inject-appid.js'

// uni-app + Vue3 构建配置
// 微信小程序：npm run dev:mp-weixin  → 产物在 dist/dev/mp-weixin，用微信开发者工具打开
//
// === 环境变量 ===
//
// VITE_API_BASE  — 线上后端地址（生产环境的 API 域名）
//   示例：VITE_API_BASE=https://weixin.example.com
//   未设时使用 config.js 里的 fallback（https://weixin.your-domain.com）
//
// VITE_API_MODE  — 开发模式下的后端选择
//   'local'（默认）→ 本地后端 http://127.0.0.1:5001
//   'prod'         → 线上后端（配合 VITE_API_BASE 使用）
//
// VITE_WX_APPID  — 微信小程序 AppID
//   示例：VITE_WX_APPID=wx1234567890abcdef
//   构建后自动注入到 project.config.json，源码中无需硬编码
//   不设时保持 uni-app 默认值 "touristappid"（游客模式）
//
// === 用法 ===
//   npm run dev:mp-weixin                        → 本地后端
//   VITE_API_BASE=https://wx.example.com npm run dev:mp-weixin:prod  → 线上后端（热更新）
//   VITE_API_BASE=https://wx.example.com npm run build:mp-weixin    → 生产构建
//   VITE_WX_APPID=wx1234567890 VITE_API_BASE=https://wx.example.com npm run build:mp-weixin → 全注入

const apiMode = process.env.VITE_API_MODE || 'local'
const apiBase = process.env.VITE_API_BASE || ''

export default defineConfig({
  plugins: [uni(), injectWxAppid()],
  define: {
    __VITE_API_MODE__: JSON.stringify(apiMode),
    __VITE_PROD_BASE__: JSON.stringify(apiBase),
  },
})
