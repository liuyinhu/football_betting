# 中超赛事数据分析 · 微信小程序（uni-app + Vue 3）

本目录是一个**赛事数据分析 / 概率科普**定位的微信小程序，基于 **uni-app + Vue 3**。
展示中超赛事数据与模型概率分析，**不含任何赔率输入、投注建议、下注功能**，与博彩无关。

后端复用根项目的 Flask 服务（`../webapp/app.py`），小程序仅调用其中**只读的数据/概率接口**。

---

## 定位与合规说明（重要）

为满足微信小程序审核对"博彩/赌博"类内容的限制，本版本已做**去投注化改造**：

| 已移除 ❌ | 已保留 ✅ |
|---|---|
| 赔率输入（胜平负/大小球/半全场/比分） | 赛程与球队信息 |
| 投注建议 / EV / 凯利仓位 | 胜平负 / 大小球 / 双方进球 **概率** |
| `/api/predict`、`/api/live/predict` 调用 | 最可能比分、半全场概率矩阵 |
| "获取投注建议"等诱导性文案 | 实时比分、射门/射正/角球/控球等**赛事数据** |

所有页面文案统一为"赛事数据 / 概率分析 / 科普"，并保留免责声明。
建议提交审核时选择 **工具 / 体育资讯** 类目，切勿选竞猜/博彩相关类目。

---

## 目录结构

```
miniprogram/
├── package.json           # 依赖与脚本
├── vite.config.js         # uni-app + vite 构建配置
├── index.html             # H5 入口（编译到微信小程序时忽略）
└── src/
    ├── main.js            # 应用入口（createSSRApp）
    ├── App.vue            # 全局样式 / 深色主题变量
    ├── manifest.json      # uni-app 应用配置（appid 等）
    ├── pages.json         # 页面路由 + 底部 tabBar
    ├── common/
    │   ├── config.js      # 后端 BASE_URL 配置（开发/生产）
    │   ├── request.js     # uni.request 封装
    │   └── api.js         # 3 个只读接口（engines / matches / live）
    ├── components/
    │   ├── EngineBar.vue      # 预测引擎切换条（dc/nn）
    │   ├── MatchCard.vue      # 赛前概率分析卡片
    │   └── LiveMatchCard.vue  # 实时赛事数据 + 概率卡片
    └── pages/
        ├── prematch/prematch.vue  # 赛事数据分析页
        └── live/live.vue          # 实时赛事数据页（30 秒轮询）
```

---

## 快速开始

### 1. 安装依赖

```bash
cd miniprogram
npm install
```

> 若安装 uni-app 依赖遇到网络问题，也可用 **HBuilderX** 创建 uni-app 项目后
> 把 `src/` 内容拷进去（自带运行环境，免 npm 配置）。

### 2. 启动后端（项目根目录）

```bash
cd ..
python3 -m webapp.app                       # 无实时数据
API_FOOTBALL_KEY=你的key python3 -m webapp.app   # 启用实时赛事数据
```

后端默认监听 `http://127.0.0.1:5001`。

### 3. 编译到微信小程序

```bash
cd miniprogram
npm run dev:mp-weixin
```

产物在 `dist/dev/mp-weixin/`，用**微信开发者工具**「导入项目」选择该目录。

### 4. 本地联调

微信开发者工具「详情 → 本地设置」勾选
「**不校验合法域名、web-view、TLS 版本以及 HTTPS 证书**」，
即可临时访问本地后端 `http://127.0.0.1:5001`。

---

## 上线前必做

1. **后端 HTTPS + ICP 备案域名**，把 `src/common/config.js` 的 `PROD_BASE` 改成你的域名。
2. **微信后台配置 request 合法域名**（加入后端域名白名单）。
3. **填写小程序 AppID**（`src/manifest.json` → `mp-weixin.appid`）。
4. **选对服务类目**：工具 / 体育资讯类，避开竞猜/博彩类目。

---

## 后端接口（仅使用只读数据接口）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/engines` | 可用分析引擎列表（dc/nn） |
| GET | `/api/matches?limit=10&engine=dc` | 接下来 N 场 + 赛前概率 |
| GET | `/api/live?engine=dc` | 进行中比赛数据 + 实时概率 |

> `/api/predict`、`/api/live/predict`（赔率投注建议）**本小程序不再调用**，
> 后端可保留供网页版使用，互不影响。
