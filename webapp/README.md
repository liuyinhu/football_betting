# 中超赛前预测 Web 应用（前后端分离）

用前端展示接下来 **10 场中超**（可调 5/10/15/20）的预测结果：
默认仅展示**预测概率**；手动输入**赔率**后给出**正期望值（EV）投注建议**。

架构：**前端 (Vue 3) → 后端 (Flask) → 预测模型 (Dixon-Coles/泊松)**

```
浏览器  ──HTTP──▶  Vite 开发服务器 (:5173)
                      │  /api/* 反向代理
                      ▼
                 Flask 后端 (:5001)
                      │  调用
                      ▼
   webapp/prediction_service.py
     ├─ data/upcoming.py        （中国足协官方 API：未来赛程）
     ├─ data/train_strength.py  （已训练的球队攻防强度）
     ├─ models/poisson_live.py  （时变泊松 + Dixon-Coles 比分分布）
     └─ strategy/decision.py    （EV 过滤 + 分数凯利仓位）
```

## 目录结构

```
webapp/                     # 后端（Python / Flask）
├── app.py                  # Flask 入口，定义 REST API
├── prediction_service.py   # 预测服务层：封装模型调用
└── requirements.txt        # 后端额外依赖（flask, flask-cors）

frontend/                   # 前端（Vue 3 + Vite）
├── index.html
├── package.json
├── vite.config.js          # 开发服务器 + /api 代理配置
└── src/
    ├── main.js
    ├── App.vue             # 主页面：赛程列表 + 工具栏
    ├── style.css
    ├── api.js              # 后端接口封装
    └── components/
        └── MatchCard.vue   # 单场比赛卡片：概率展示 + 赔率输入 + 投注建议

data/upcoming.py            # 新增：拉取「未开赛」赛程（赛前预测用）
start_web.sh                # 一键启动脚本（同时起前后端）
```

## 快速开始

### 方式一：一键脚本（推荐）

```bash
./start_web.sh
```

脚本会自动启动后端（:5001）与前端（:5173），并在首次运行时安装前端依赖。
启动后浏览器打开：**http://127.0.0.1:5173/**

> ⚠️ Vite 5 需要 **Node.js ≥ 18**。若系统默认 node 过旧，脚本会自动使用
> `~/.n/bin/node`（若存在）。也可用 nvm/n 自行切换到 Node 18+。

### 方式二：手动分别启动

**1) 后端**

```bash
# 安装依赖（首次）
python3 -m pip install -r requirements.txt        # scipy/numpy
python3 -m pip install -r webapp/requirements.txt  # flask/flask-cors

# 启动（默认 :5001）
python3 -m webapp.app
```

**2) 前端**（另开一个终端）

```bash
cd frontend
npm install      # 首次
npm run dev      # 启动，默认 http://127.0.0.1:5173/
```

## 前置条件：强度模型

后端预测依赖已训练的球队强度模型 `data/csl_strength.json`。
若不存在，先在项目根目录运行：

```bash
python3 -m data.train_strength
```

## API 说明

### `GET /api/health`
健康检查，返回 `{"status": "ok"}`。

### `GET /api/matches?limit=10`
返回接下来 N 场未开赛中超，**每场附带赛前预测概率**（不含赔率建议）。
这满足「不输入赔率则仅展示预测概率」的需求。

响应示例（节选）：

```json
{
  "count": 10,
  "matches": [
    {
      "match_id": 912345678,
      "date": "2026-07-25", "time": "17:30:00",
      "datetime": "2026-07-25 17:30:00", "week": 20,
      "home_zh": "青岛海牛", "away_zh": "天津津门虎",
      "home_en": "Qingdao Jonoon", "away_en": "Tianjin Teda",
      "prediction": {
        "lambda_home": 1.3, "lambda_away": 1.1,
        "outcome": { "home": 0.403, "draw": 0.274, "away": 0.323 },
        "over_under": { "over_2.5": 0.55, "under_2.5": 0.45, "...": 0 },
        "btts": { "yes": 0.58, "no": 0.42 },
        "top_scores": [ { "score": "1-1", "prob": 0.13 } ],
        "ht_outcome": { "home": 0.37, "draw": 0.39, "away": 0.24 },
        "half_full": [
          { "ht": "home", "ft": "home", "prob": 0.297 },
          { "ht": "draw", "ft": "home", "prob": 0.158 }
        ]
      }
    }
  ]
}
```

> `half_full` 为**半全场 (HT/FT)** 9 种组合概率，`ht`=半场结果、`ft`=全场结果
> （`home`/`draw`/`away`）；`ht_outcome` 为半场胜平负边际概率。

### `POST /api/predict`
给定一场比赛 + 赔率，返回预测概率与投注建议。
`odds` 留空则只返回概率（`recommendations` 为空数组）。

请求体：

```json
{
  "home_en": "SHANGHAI SIPG",
  "away_en": "Shanghai Shenhua",
  "odds": {
    "home": 1.8, "draw": 3.5, "away": 4.5,
    "over":  { "2.5": 2.0 },
    "under": { "2.5": 1.8 },
    "exact": { "1-0": 6.5 },
    "htft":  { "home/home": 4.0, "away/away": 8.0 }
  }
}
```

> 也可用中文队名字段 `home_zh` / `away_zh`，后端会自动映射。
> `htft` 为**半全场**赔率，key = `"半场/全场"`（取值 `home`/`draw`/`away`），
> 例如 `"home/away"` = 半场主队领先、全场客队反超。

响应中 `recommendations` 为按 EV 降序排列的正期望值投注：

```json
{
  "recommendations": [
    {
      "market": "1X2:away", "market_zh": "客胜",
      "odds": 4.5, "model_prob": 0.323,
      "edge": 0.454, "stake_fraction": 0.02,
      "reason": "模型概率=0.323 vs 赔率隐含概率=0.222"
    }
  ]
}
```

## 投注建议规则（见 `strategy/decision.py`）

- **EV ≥ 3%** 才推荐（`MIN_EDGE`）
- 仓位 = **1/4 凯利**，并封顶为总资金 **2%**（`KELLY_FRACTION` / `MAX_STAKE_PER_BET`）
- 过滤赔率 < 1.20 或 > 15 的市场

## 半全场 (HT/FT) 预测（见 `models/poisson_live.py`）

前端每张比赛卡片可展开「半全场胜负预测」，展示 **半场结果 × 全场结果** 的 9 格概率矩阵。

原理：把整场进球率 λ 按上/下半场占比拆成两段**独立泊松**过程，
联合求和得到 9 种组合。上半场进球占比 `FIRST_HALF_GOAL_FRACTION = 0.43`
由 `data/apifootball_raw` 全部分钟级进球事件校准（868 场 / 2652 球，上半场 43.0%、下半场 57.0%）。
低比分相关性仍施加 Dixon-Coles 修正。

> 交叉验证：由 HT/FT 反推的全场胜平负边际，与原单段模型结果高度一致（差异 < 1.5%）。

## 说明

- 赛程数据来自**中国足协官方 API**（免费、无需鉴权，队名/升降级最新准确）。
- 后端对赛程结果做 10 分钟缓存，避免频繁请求官方接口。

> ⚠️ 本项目仅供**学习 / 研究**。中国大陆赌博违法，且长期战胜高效博彩公司极其困难，
> 模型不保证盈利，请勿用于真实赌博。
