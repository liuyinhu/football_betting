# 中超足球预测使用指南

本指南面向实际使用，介绍如何**训练模型**、**赛前预测**、**实时预测**，以及如何用**中文队名 / 中文字段**编写输入文件。

> ⚠️ 本项目仅供学习研究。模型不保证盈利，请勿用于真实赌博。中国大陆赌博违法。

---

## 目录

- [1. 环境准备](#1-环境准备)
- [2. 快速开始](#2-快速开始)
- [3. 训练中超模型](#3-训练中超模型)
- [4. 拉取与分析 API-Football 数据](#4-拉取与分析-api-football-数据)
- [5. 赛前预测](#5-赛前预测)
- [6. 实时预测（比赛进行中）](#6-实时预测比赛进行中)
- [7. 输入文件字段说明](#7-输入文件字段说明)
- [8. 中文队名与中文字段](#8-中文队名与中文字段)
- [9. 输出结果解读](#9-输出结果解读)
- [10. 常见问题](#10-常见问题)

---

## 1. 环境准备

```bash
pip install -r football_betting/requirements.txt
```

依赖：`numpy`、`scipy`。

> 所有命令都在**项目根目录**（`qqq/`，即 `football_betting/` 的上一级）下运行，
> 使用 `python3 -m football_betting.xxx` 的模块方式，否则会报 `ModuleNotFoundError`。

---

## 2. 快速开始

```bash
# 1) 生成一个 JSON 输入模板（带中文注释）
python3 -m football_betting.predict -t

# 2) 编辑生成的 match.example.json 后，运行预测
python3 -m football_betting.predict match.example.json
```

也可以不带文件、纯交互式逐步输入：

```bash
python3 -m football_betting.predict
```

---

## 3. 训练中超模型

模型基于 [openfootball/world](https://github.com/openfootball/world) 的公开中超历史赛果，
用 Dixon-Coles / 泊松最大似然估计（MLE）拟合各队的**攻击力 / 防守力**。

```bash
# 默认：用近 3 个赛季（2023-2025）训练
python3 -m football_betting.data.train_strength

# 指定起止年份（如全量 8 赛季）
python3 -m football_betting.data.train_strength 2018 2025

# 只用最近 N 个赛季
python3 -m football_betting.data.train_strength 3
```

> 💡 强度模型只用 `csl_raw/`（openfootball）赛果训练——它队名统一、赛季完整。
> API-Football 数据队名风格不同，**不参与强度训练**，只用于第 4 节的特征分析。

**输出模型位置**：`football_betting/data/csl_strength.json`

模型内容（JSON）：

```json
{
  "teams": { "Shanghai Port": { "attack": 0.65, "defence": 0.42 }, ... },
  "home_adv": 0.247,
  "rho": -0.107,
  "n_matches": 559,
  "train_years": [2023, 2024, 2025],
  "converged": true
}
```

> 建议只用近几年数据训练：球队阵容和实力变化大，太旧的数据反而降低准确率。

### 验证模型效果

```bash
# 默认：用 2023-2024 训练，2025 测试
python3 -m football_betting.data.validate

# 自定义训练/测试赛季
python3 -m football_betting.data.validate 2023,2024 2025
```

输出准确率、对数损失（log-loss）以及与"永远猜主胜"基线的对比。

> 参考：用 2023-2024 训练、2025 测试，准确率约 **56%**，log-loss 约 **0.93**，均优于"永远猜主胜"基线（45.8% / 1.10）。

---

## 4. 拉取与分析 API-Football 数据

openfootball 只有**赛果比分**。要得到**分钟级事件**（进球/红黄牌/换人）和**场面统计**（射正、角球、控球、xG），可用 API-Football 免费档拉取。这类数据用于**校准实时特征权重 `FEATURE_WEIGHTS`**，不参与强度训练。

### 4.1 拉取数据

```bash
# 设置 API key（免费档：约 100 请求/天、10 请求/分钟）
export API_FOOTBALL_KEY=你的key

# 拉取 2024 赛季最新 10 场（自动按日期倒序、本地缓存、遇限速自动重试）
python3 -m football_betting.data.api_football_loader 2024 --limit 10

# 拉取整季（谨慎，每场消耗 2 个请求，易超配额）
python3 -m football_betting.data.api_football_loader 2024 --all
```

- 每场消耗 **2 个请求**（statistics + events），已缓存的场次**零消耗**
- 免费档实际可拉赛季为 **2022–2024**（更新赛季需付费）
- 数据分目录存储：
  - `data/apifootball_raw/cache/` — 单场缓存 `fixture_<id>.json`（已加入 `.gitignore`，可随时删除重拉）
  - `data/apifootball_raw/seasons/` — 赛季汇总 `csl_<season>_details.json`（最终产物）

### 4.2 分析数据 / 校准特征权重

```bash
python3 -m football_betting.data.analyze_apifootball 2024
```

输出三部分（**不消耗 API 配额**）：

1. **分钟级进球分布** — 验证进球强度随时间上升（支持时变泊松建模）
2. **特征相关性** — 各场面统计差值与进球的皮尔逊相关系数（实测 **xG ≈ 0.47、射正 ≈ 0.46** 最强，角球/控球几乎无关）
3. **泊松回归** — 拟合"特征差 → 进球数"，给出 `FEATURE_WEIGHTS` 校准建议

> ⚠️ 样本越大结论越稳。30~40 场时角球、控球可能出现伪信号（多重共线性），建议累积到 80+ 场再据此调权重。

---

## 5. 赛前预测

赛前预测只需给出**主客队名**，程序会自动从训练模型载入双方赛前预期进球 λ。

创建 `prematch.json`：

```jsonc
{
  "state": {
    "home_team": "上海海港",   // 主队（支持中文名）
    "away_team": "北京国安",   // 客队
    "minute": 0,               // 赛前 = 0
    "score_h": 0,
    "score_a": 0
  },
  "odds": {                    // 可选：填了才会给投注建议
    "home": 1.80,
    "draw": 3.60,
    "away": 4.20,
    "over":  { "2.5": 1.95 },
    "under": { "2.5": 1.85 }
  }
}
```

运行：

```bash
python3 -m football_betting.predict prematch.json
```

程序会打印：`✓ 已从训练模型载入赛前 λ: 上海海港 1.72 vs 北京国安 1.05`

---

## 6. 实时预测（比赛进行中）

比赛进行中，填入**当前比分、分钟、场面统计**（射正、角球、xG 等），
模型会结合剩余时间给出最终比分概率与投注建议。

```jsonc
{
  "state": {
    "home_team": "上海海港",
    "away_team": "北京国安",
    "minute": 60,             // 当前分钟
    "score_h": 1,
    "score_a": 0,
    "sot_h": 4, "sot_a": 2,   // 射正（对进球率影响最大）
    "corners_h": 5, "corners_a": 3,
    "xg_h": 1.3, "xg_a": 0.6, // 实时 xG（权重高）
    "red_h": 0, "red_a": 0    // 红牌（每张使该队 λ ×0.65）
  },
  "odds": {
    "home": 1.35, "draw": 4.50, "away": 9.00,
    "over":  { "2.5": 2.40 },
    "under": { "2.5": 1.60 }
  }
}
```

```bash
python3 -m football_betting.predict live.json
```

---

## 7. 输入文件字段说明

### `state` — 比赛场面

| 字段 | 含义 | 说明 |
|------|------|------|
| `home_team` / `away_team` | 主/客队名 | 填了可自动载入赛前 λ |
| `minute` | 当前分钟 | 赛前填 0，范围 0~90 |
| `score_h` / `score_a` | 主/客当前进球 | |
| `sot_h` / `sot_a` | 主/客射正 | 对进球率影响最大 |
| `shots_h` / `shots_a` | 主/客总射门 | |
| `corners_h` / `corners_a` | 主/客角球 | |
| `dangerous_attacks_h/a` | 危险进攻 | |
| `possession_h` | 主队控球率 % | 客队 = 100 − 此值 |
| `red_h` / `red_a` | 主/客红牌 | 每张使该队 λ ×0.65 |
| `xg_h` / `xg_a` | 实时期望进球 | 没有可填 0，权重高 |
| `prior_lambda_h/a` | 赛前预期进球 λ | 有队名时自动填充，可手动覆盖 |

### `odds` — 投注赔率（欧洲/小数赔率，可选）

| 字段 | 含义 |
|------|------|
| `home` / `draw` / `away` | 主胜 / 平局 / 客胜 |
| `over` / `under` | 大/小球，如 `{ "2.5": 1.95 }` |
| `exact` | 精确比分，如 `{ "2-1": 8.0 }`（键为"主-客"）|

> 不填 `odds` 也能预测概率，只是不会给投注建议。

### xG 是什么？

xG（Expected Goals，预期进球）衡量射门机会的质量：把每次射门按"进球概率"累加。
例如 xG=1.3 表示按机会质量估算应进约 1.3 球。它比"射门数"更能反映真实威胁，因此权重最高。

---

## 8. 中文队名与中文字段

### 中文队名

`home_team` / `away_team` 支持中文名及常见别名，例如：
`上海海港`、`北京国安`、`山东泰山`（鲁能）、`上海申花`、`河南队`、`大连英博` 等。
程序会自动映射到数据集英文名并做模糊匹配。

### 中文字段（key 也能用中文）

整份输入文件的 key 都可以写成中文：

```jsonc
{
  "比赛状态": {
    "主队": "河南队",
    "客队": "大连英博",
    "分钟": 27,
    "主队进球": 0,
    "客队进球": 1,
    "主队射正": 3,
    "客队射正": 2
  },
  "赔率": {
    "主胜": 2.10,
    "平": 3.30,
    "客胜": 3.50,
    "大球": { "2.5": 1.95 },
    "小球": { "2.5": 1.85 }
  }
}
```

常用中文字段对照：

| 中文 | 英文 |
|------|------|
| 比赛状态 / 场面 | state |
| 赔率 / 投注赔率 | odds |
| 主队 / 客队 | home_team / away_team |
| 分钟 / 时间 | minute |
| 主队进球 / 客队进球 | score_h / score_a |
| 主队射正 / 客队射正 | sot_h / sot_a |
| 主队角球 / 客队角球 | corners_h / corners_a |
| 主队控球率 | possession_h |
| 主队红牌 / 客队红牌 | red_h / red_a |
| 主胜 / 平 / 客胜 | home / draw / away |
| 大球 / 小球 | over / under |
| 精确比分 / 比分 | exact |

> 支持 `//` 与 `/* */` 注释，运行时会自动忽略，方便在输入文件里写备注。

---

## 9. 输出结果解读

```
============================================================
当前 27'  比分 0-1  (剩余 63 分钟)
============================================================
【最终比分概率 TOP 8】
  0-1   24.73%  █████████
  1-1   20.37%  ████████
  ...
【胜平负 / 大小球 / 双方进球】
  主胜 15.77%   平局 26.03%   客胜 58.20%
  大2.5 43.49%   小2.5 56.51%
  双方进球 是 59.83%   否 40.17%
【投注建议 (仅列出正期望值 EV≥3% 的)】
  ✅ 1X2:away       赔率  1.91  模型概率 58.20%  EV +11.2%  建议仓位 2.00%
```

- **最终比分概率**：模型预测的终场比分分布（取概率最高的 8 个）。
- **EV（期望值）**：`模型概率 × (赔率−1) − (1−概率)`，> 0 表示长期有价值。
- **建议仓位**：占总资金比例，采用 **1/4 凯利** 并封顶 2%，控制风险。

调参入口见 `strategy/decision.py`（`MIN_EDGE`、`KELLY_FRACTION`、`MAX_STAKE_PER_BET`）
和 `models/poisson_live.py`（`FEATURE_WEIGHTS`、`RED_CARD_PENALTY`）。

---

## 10. 常见问题

**Q: 报错 `ModuleNotFoundError: No module named 'football_betting'`？**
A: 必须在**项目根目录**（`football_betting/` 的上一级）运行，用 `python3 -m football_betting.predict`。

**Q: 提示"球队未在训练数据中找到"？**
A: 该队可能不在所选训练赛季里。换用更全的赛季重新训练，或在 `state` 里手动填 `prior_lambda_h/a`。

**Q: 有没有 2026 年数据？**
A: openfootball 数据源目前最新到 2025 赛季。API-Football 免费档可拉的赛季为 2022–2024，更新赛季需付费。

**Q: 为什么不把 openfootball 和 API-Football 数据合在一起训练？**
A: 两者队名风格不同（如 `Shanghai Port FC` vs `SHANGHAI SIPG`、`Shandong Taishan` vs `Shandong Luneng`），同一赛季 16 队里往往只有几个能对上。直接合并会把同一支队当成两个实体，污染攻防强度估计。因此**强度训练只用 openfootball**，API-Football 只用于特征分析。

**Q: API-Football 拉取报 429 / 配额用尽？**
A: 免费档限速约 10 请求/分钟、100 请求/天。加载器已内置 6.5 秒请求间隔与 429 自动重试；若当天配额用尽，等次日重置即可（已缓存的场次不再消耗）。

**Q: 模型 λ 出现异常极端值？**
A: 已在 `expected_lambdas()` 中把 λ 限制在 `[0.2, 3.0]` 合理区间。

**Q: 模拟回测怎么跑？**
A:
```bash
python3 -m football_betting.main          # 单场模拟
python3 -m football_betting.main mc 500   # 500 场蒙特卡洛
```
