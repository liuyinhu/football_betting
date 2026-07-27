import { createSSRApp } from 'vue'
import App from './App.vue'

// uni-app + Vue3 入口
// 注意：必须返回 { app } 对象，不能直接返回 app 实例。
// 否则框架调用 createApp().app.mount(...) 时 .app 为 undefined，
// 导致 "Cannot read property 'mount' of undefined"，App 启动失败、所有页面注册不上。
export function createApp() {
  const app = createSSRApp(App)
  return { app }
}
