/**
 * Vite 插件：构建后注入微信小程序 AppID
 *
 * 微信小程序的 AppID 出现在 project.config.json 中，
 * uni-app 构建时会从 manifest.json 读取 mp-weixin.appid 写入产物，
 * 但 manifest.json 是静态 JSON，无法在编译时通过环境变量替换。
 *
 * 本插件在 closeBundle 阶段读取 VITE_WX_APPID 环境变量，
 * 注入到 dist 中的 project.config.json，保持源码干净。
 *
 * 用法：
 *   VITE_WX_APPID=wx1234567890 npm run build:mp-weixin
 *   VITE_WX_APPID=wx1234567890 npm run dev:mp-weixin:prod
 *
 * 不设时，保持 uni-app 默认值 "touristappid"（游客模式）。
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

export default function injectWxAppid() {
  const appid = process.env.VITE_WX_APPID

  return {
    name: 'inject-wx-appid',
    enforce: 'post',
    closeBundle() {
      if (!appid) return

      // 构建产物路径
      const configPath = resolve(
        process.cwd(),
        'dist',
        'build',
        'mp-weixin',
        'project.config.json',
      )

      // dev 模式也可能有产物
      const devConfigPath = resolve(
        process.cwd(),
        'dist',
        'dev',
        'mp-weixin',
        'project.config.json',
      )

      for (const p of [configPath, devConfigPath]) {
        try {
          const raw = readFileSync(p, 'utf-8')
          const json = JSON.parse(raw)
          json.appid = appid
          writeFileSync(p, JSON.stringify(json, null, 2) + '\n', 'utf-8')
          console.log(`✅ [inject-wx-appid] ${p} → appid = "${appid}"`)
        } catch {
          // 文件不存在则跳过（build 产物只有一种目录）
        }
      }
    },
  }
}
