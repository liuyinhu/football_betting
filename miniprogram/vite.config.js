import { defineConfig } from 'vite'
import uni from '@dcloudio/vite-plugin-uni'

// uni-app + Vue3 构建配置
// 微信小程序：npm run dev:mp-weixin  → 产物在 dist/dev/mp-weixin，用微信开发者工具打开
export default defineConfig({
  plugins: [uni()],
})
