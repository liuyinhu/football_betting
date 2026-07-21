# 足球实时预测与投注推荐系统

一个 Python 框架，输入**实时比赛状态**（比分、分钟、射门、角球、犯规、红牌、xG 等）
和**实时市场赔率**，输出：

1. 实时比分 / 胜平负概率（时变泊松模型 + Dixon-Coles 修正）
2. 正期望值（EV）的投注推荐
3. 带风险上限的分数凯利（Kelly）仓位建议

> ⚠️ 本项目为**学习 / 研究**框架。中国大陆赌博违法，且长期战胜高效博彩公司极其困难，请仅用于模拟研究。

## 项目结构

```
qqq/                        # 项目根目录（在此运行所有命令）
├── core/state.py            # 数据类：MatchState、OddsSnapshot、BetRecommendation
├── models/poisson_live.py   # 时变泊松 + DC 比分/胜平负分布、FEATURE_WEIGHTS
├── strategy/decision.py     # EV 过滤 + 分数凯利仓位
├── feeds/simulated.py       # 模拟实时数据源（用于演示与回测）
├── backtest/paper_trader.py # 简易纸面交易引擎
├── data/                    # 数据加载、训练、验证、队名映射（详见下方）
│   ├── csl_loader.py            # Match 数据类 + openfootball 赛果加载（备用）
│   ├── train_strength.py        # Dixon-Coles/泊松 MLE 训练攻防强度
│   ├── validate.py              # walk-forward 验证
│   ├── team_names.py            # 中文队名 / 别名映射（对齐 API-Football 命名）
│   ├── api_football_loader.py   # API-Football 拉取 + 合并去重加载器
│   ├── analyze_apifootball.py   # 进球分布/相关性/权重校准分析
│   ├── csl_strength.json        # 训练产出的强度模型
│   └── apifootball_raw/         # API-Football 数据（唯一训练数据源）
│       ├── cache/                   # 单场缓存 fixture_<id>.json（不入库）
│       └── seasons/                 # 赛季汇总 csl_<season>_details.json
├── predict.py               # 交互式 / JSON 文件预测入口
└── main.py                  # 端到端可运行演示
```

## 数据来源

本项目**统一使用 API-Football 数据**（`data/apifootball_raw/`）训练与分析：

| 用途 | 说明 |
|------|------|
| **攻防强度模型**（赛前 λ） | 由所有已拉取赛季的赛果 MLE 拟合（Dixon-Coles/泊松） |
| **实时特征权重** `FEATURE_WEIGHTS` | 由分钟级事件 + 射正/角球/xG 等场面统计校准 |

数据经 `load_all_details()` 按 `fixture_id` **合并去重**后统一训练，队名自洽
（如 `SHANGHAI SIPG`=上海海港、`Shandong Luneng`=山东泰山），中文映射见 `team_names.py`。

> 说明：早期版本曾用 openfootball（`csl_raw/`）训练强度，因其与 API-Football
> 队名风格不一致，现已**全面切换为 API-Football 单一数据源**。`csl_loader.py`
> 仅保留 `Match` 数据类供训练器复用。

## 安装

```bash
pip install -r requirements.txt
```

> 所有命令都在**项目根目录**（`qqq/`）下运行。

## 运行演示（单场模拟比赛）

```bash
python3 main.py
```

## 蒙特卡洛回测（500 场）

```bash
python3 main.py mc 500
```

## 预测真实比赛

详见 [USAGE.md](USAGE.md)，涵盖训练中超模型、赛前预测、实时预测、中文队名 / 中文字段等完整用法。

```bash
# 用全部已拉取的 API-Football 数据训练强度模型
python3 -m data.train_strength

# walk-forward 验证（默认：2024+2025 训练、2026 测试）
python3 -m data.validate

# 生成带中文注释的 JSON 输入模板，编辑后预测
python3 predict.py -t
python3 predict.py match.example.json
```

## 拉取真实中超数据（API-Football）

本项目的训练/分析数据均来自 API-Football（**分钟级事件 + 射正/角球/xG 场面统计**）：

```bash
# 设置 API key
export API_FOOTBALL_KEY=你的key

# 单赛季：拉 2026 赛季最新 10 场（自动倒序、本地缓存、遇限速自动重试）
python3 -m data.api_football_loader 2026 --limit 10

# 单赛季：拉整个赛季
python3 -m data.api_football_loader 2025 --all

# 跨赛季：拉全局最新 200 场（自动从当前赛季往回补齐）
python3 -m data.api_football_loader --latest 200
```

- 缓存写入 `data/apifootball_raw/cache/`，汇总写入 `data/apifootball_raw/seasons/`
- 免费档约 100 请求/天、仅可拉 2022–2024；Pro 档 7500 请求/天、可拉当前赛季
- 提速：`export API_FOOTBALL_DELAY=0.3`（Pro 档限速 300/分钟）

分析这些数据（不消耗配额），校准特征权重：

```bash
python3 -m data.analyze_apifootball 2024
```

输出：进球分钟分布、各特征与进球的相关性、泊松回归对 `FEATURE_WEIGHTS` 的校准建议。

## 接入真实数据源

实现一个与 `SimulatedFeed` 接口一致的类：

```python
class MyLiveFeed:
    def step(self) -> tuple[MatchState, OddsSnapshot]: ...
```

然后接入同一套评估流程：

```python
from strategy.decision import evaluate
state, odds = feed.step()
for rec in evaluate(state, odds):
    print(rec)
```

推荐的真实数据源：
- **比赛统计**：API-Football、SportMonks、Understat
- **赔率**：Betfair 交易所 API（最佳）、Pinnacle、OddsPortal

## 可调参数

`strategy/decision.py`：
- `MIN_EDGE` — 下注所需的最小 EV（默认 3%）
- `KELLY_FRACTION` — 凯利比例（默认 1/4）
- `MAX_STAKE_PER_BET` — 单注硬上限（默认 2%）
- `MIN_ODDS`、`MAX_ODDS` — 过滤极端赔率

`models/poisson_live.py`：
- `FEATURE_WEIGHTS` — 各项场面统计对 λ 的推动权重
- `RED_CARD_PENALTY` — 一方减员至 10 人时的 λ 乘数

## 后续方向

- 用真实的 websocket / REST 数据源替换 `SimulatedFeed`
- 扩大 API-Football 样本量（80+ 场）后重跑 `analyze_apifootball`，稳健校准 `FEATURE_WEIGHTS`
- 用历史逐分钟数据学习时变强度曲线（LightGBM）
- 增加整赛季的 walk-forward 回测
- 增加持久化（SQLite）+ Telegram / 企业微信 通知
