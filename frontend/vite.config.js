import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端开发服务器：把 /api 代理到后端 Flask (localhost:5001)
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // 允许通过域名访问（线上部署）。true 表示放行所有 Host，
    // 也可改为具体域名数组，如 ['liuyinhu.com', '.liuyinhu.com']
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:5001',
        changeOrigin: true,
      },
    },
  },
})
