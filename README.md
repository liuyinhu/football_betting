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
├── models/nn_predictor.py   # 纯 NumPy MLP 三分类器(神经网络版, 零新增依赖)
├── strategy/decision.py     # EV 过滤 + 分数凯利仓位
├── feeds/simulated.py       # 模拟实时数据源（用于演示与回测）
├── backtest/paper_trader.py # 简易纸面交易引擎
├── data/                    # 数据加载、训练、验证、队名映射（详见下方）
│   ├── csl_loader.py            # Match 数据类 + openfootball 赛果加载（备用）
│   ├── train_strength.py        # Dixon-Coles/泊松 MLE 训练攻防强度
│   ├── train_nn.py              # 神经网络版训练/验证(含 --recent 日期切分+时间权重)
│   ├── experiment_time_weight.py # 时间权重对比实验(多档半衰期 × 多种子平均)
│   ├── validate.py              # walk-forward 验证
│   ├── team_names.py            # 中文队名 / 别名映射（含辽宁铁人等新队）
│   ├── api_football_loader.py   # API-Football 拉取 + 合并去重加载器
│   ├── cfa_loader.py            # 中国足协官方 API 拉取（当前赛季赛果，队名权威）
│   ├── analyze_apifootball.py   # 进球分布/相关性/权重校准分析
│   ├── csl_strength.json        # 训练产出的强度模型
│   └── apifootball_raw/         # API-Football 数据（唯一训练数据源）
│       ├── cache/                   # 单场缓存 fixture_<id>.json（不入库）
│       └── seasons/                 # 赛季汇总 csl_<season>_details.json
├── predict.py               # 交互式 / JSON 文件预测入口
└── main.py                  # 端到端可运行演示
```

## 数据来源

本项目用**两个互补数据源**，统一汇入 `data/apifootball_raw/seasons/`，经 `load_all_details()` 按 `fixture_id` 合并去重后训练：

| 数据源 | 负责赛季 | 提供内容 | 优势 |
|--------|---------|---------|------|
| **中国足协官方 API**（`cfa_loader.py`） | 当前赛季（2026） | 赛程赛果 + 比分 | 官方、免费、队名/升降级永远最新准确 |
| **API-Football**（`api_football_loader.py`） | 历史赛季（2023/2024/2025） | 赛果 + 射正/角球/xG + 分钟级事件 | 场面统计丰富，用于校准 `FEATURE_WEIGHTS` |

两源队名经归一化对齐（如 `SHANGHAI SIPG`=上海海港、`Shandong Luneng`=山东泰山），同一支队跨赛季自洽，中文映射见 `team_names.py`。

> 为什么引入官方源：API-Football 的 **2026 中超参赛名单滞后**（缺辽宁铁人、青岛西海岸、深圳新鹏城，却混入已降级的队）；中国足协官方 API 名单准确，故当前赛季改用官方数据。早期版本曾用 openfootball（`csl_loader.py` 仅保留 `Match` 数据类）。

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

# ★ 最简单：只给两个队名做赛前胜率预测
python3 predict.py 辽宁铁人 北京国安

# 赛前预测时并排显示「神经网络」概率(需先训练 NN 模型)
python3 predict.py 辽宁铁人 北京国安 --nn

# 生成带中文注释的 JSON 输入模板，编辑后预测（可填实时比分/赔率）
python3 predict.py -t
python3 predict.py match.example.json
```

## 神经网络版本（可选）

除默认的 Dixon-Coles/泊松解析模型外，项目还提供一个**纯 NumPy 实现的多层感知机(MLP)三分类器**作为对比/替代方案（零新增依赖，不引入 PyTorch/TensorFlow）。

它与 Dixon-Coles **共享同一份信息**：特征全部由已训练的攻防强度推导得到（主客攻防、主场优势、以及泊松式给出的赛前 λ），因此对比公平——差异只在「解析式」vs「神经网络拟合」。

```bash
# 训练并保存神经网络模型 (data/nn_strength.json)
# 默认走「按日期切分 + 温和时间权重」最优配置
python3 -m data.train_nn

# 按赛季 walk-forward 验证：神经网络 与 Dixon-Coles 并排对比
python3 -m data.train_nn --validate
python3 -m data.train_nn --validate 2024,2025 2026
```

### 按比赛日期切分 + 时间权重（推荐，最优配置）

用**测试集之前的全部数据**训练（2023/2024/2025 全年 + 2026 早期场次），
并对比赛按日期做**指数时间权重**（越近的比赛权重越大），预测 **2026 最近 N 场**：

```bash
# 训练"2026 最近 30 场之前"的全部数据(半衰期365天时间权重), 预测最近 30 场
python3 -m data.train_nn --recent
python3 -m data.train_nn --recent 30

# 调整时间权重半衰期(天): 越小越偏重近期; 0=等权(无时间权重)
python3 -m data.train_nn --recent 30 --half-life 450
python3 -m data.train_nn --recent 30 --half-life 0
```

在 838 场训练 / 2026 最近 30 场测试下的验证参考值（30 种子平均）：

| 方案 | 准确率 | log-loss |
|------|------|------|
| 无时间权重（等权） | 62.00% | 0.9753 |
| **时间衰减 半衰期 450 天（默认，最优）** | **63.00%** | **0.9733** |
| 时间衰减 半衰期 365 天 | 62.22% | 0.9748 |
| 时间衰减 半衰期 180 天 | 55.00% | 0.9921 |
| 时间衰减 半衰期 90 天 | 46.33% | 1.0480 |

> **关键结论**：时间权重要「温和」才有增益（半衰期≈**450 天**最优，比等权 +1%）；
> 经 15/30 种子细扫，最优点在 450~500 天区间，比初版的 365 天略好且更稳；
> 一旦衰减过强（半衰期 ≤180 天），会把历史赛季权重压到接近 0、等于只用极少近期数据，
> 准确率反而急剧下滑。**样本量比新鲜度更重要**。

早期在小数据（480～630 场，2024+2025 训练、2026 全季测试）下的参考值：

| 指标 | 神经网络(MLP) | Dixon-Coles |
|------|--------------|-------------|
| 准确率 | ~50.6% | ~51.9% |
| log-loss | ~1.06 | ~1.05 |

> 数据翻倍（加入 2023）后 NN 准确率从 ~51% 提升到 **~63%**，印证了「加数据是提升关键」。
> NN 通过 **early stopping + L2 正则** 抑制过拟合，样本量越大发挥空间越大。

### 进球数预测（泊松回归）

除了「胜平负三分类」，还提供一个**直接预测主客队进球数**的泊松回归模型
（`MLPPoissonRegressor`）：网络输出 log(λ_home)、log(λ_away)，用**泊松负对数似然**
做损失。由 λ 可反推胜平负、大小球、精确比分等所有盘口，评估维度更丰富。

```bash
# 验证进球数预测(默认最近50场/等权), 与 Dixon-Coles 并排
python3 -m data.train_nn --goals
python3 -m data.train_nn --goals 50 --half-life 450

# ★ 用【全部已有数据】训练并保存, 用于预测未来比赛
python3 -m data.train_nn --goals --save
```

在 818 场训练 / 2026 最近 50 场测试下的参考值（10 种子平均）：

| 指标 | 神经网络(泊松) | Dixon-Coles |
|------|--------------|-------------|
| 进球 MAE ↓ | **1.033** | 1.069 |
| 进球 RMSE ↓ | **1.288** | 1.368 |
| 胜平负准确率 ↑ | **44.0%** | 42.0% |
| 大小球 2.5 准确率 ↑ | **59.6%** | 46.0% |
| 胜平负 log-loss ↓ | **1.161** | 1.220 |

> 用「进球数」作训练目标后，NN 泊松回归在**所有指标上都优于** Dixon-Coles 解析式，
> 尤其大小球命中率显著领先（59.6% vs 46.0%）——因为它直接优化进球期望，
> 比只优化胜平负方向能更好地捕捉比分尺度。

### 预测未来比赛比分

训练好模型后（`--goals --save`，会用**全部已有数据**训练并同时保存攻防强度模型），
直接用 `predict_score.py` 预测任意两队的赛前比分：

```bash
# 只需给主队、客队名(支持中文/英文, 自动模糊匹配)
python3 predict_score.py 北京国安 长春亚泰
python3 predict_score.py "Shanghai Shenhua" "Wuhan Three Towns" --top 12

# 实时(滚球)预测: 给当前分钟+比分, 预测最终比分
python3 predict_score.py 北京国安 长春亚泰 --minute 60 --score 1-0

# 指定赔率文件 -> 额外输出价值投注推荐(EV + 凯利仓位)
python3 predict_score.py --odds-template            # 先生成赔率模板
python3 predict_score.py 北京国安 长春亚泰 --odds odds.example.json

# 从 JSON 文件读全部输入(队名/分钟/比分/赔率), 兼容 predict.py 的中文字段格式
python3 predict_score.py match_cn.json
```

输出示例：

```
  赛前比分预测   北京国安 (主)  vs  长春亚泰 (客)
预期进球 λ:   主队 2.54   -   客队 0.88
最可能比分:   2 - 0   (概率 10.6%)
【比分概率 TOP 8】  2-0 10.6% / 2-1 9.3% / 3-0 9.0% / 1-0 8.3% ...
【胜平负】         主胜 73.2%   平局 15.9%   客胜 10.9%
【进球盘口】       大2.5 66.1%   双方进球 是 53.8%   总进球期望 3.43
【价值投注建议】   ✅ 大球2.5 赔率2.40 EV +58.6% 仓位2.00%  (需 --odds)
```

> 模型会输出主/客队**预期进球 λ**，再用泊松分布组合出完整比分矩阵，
> 从而给出最可能比分、TOP 比分榜及各类盘口概率。
> 传入 `--odds 文件` 后，会用模型概率对比赔率隐含概率，筛出 **EV≥3%** 的
> 价值投注并按 1/4 凯利给出建议仓位（封顶 2%）。赔率文件支持 `home/draw/away`、
> `over/under`、`btts_yes/no`、`exact`（精确比分）等盘口，只填关心的即可。
>
> **实时预测**（`--minute N --score H-A`）：把整场 λ 按剩余时间比例折算
> （`λ_剩余 = λ × (90-分钟)/90`），再叠加当前已进球数得到**最终比分**分布。
> 例如第 60 分钟 1-0 时，主胜概率会因领先+时间不多而显著上升。
>
> **JSON 文件模式**（`predict_score.py match_cn.json`）：一次性从文件读入队名、
> 分钟、比分、赔率，兼容 `predict.py` 的嵌套中文字段格式
> （`比赛状态`/`赔率`）。大小球支持**任意盘口线**（如 3.0），自动从比分矩阵计算。
>
> **整数盘口线退款(push)**：如大小球 3.0、精确让分等整数线，当总进球恰好等于该
> 线时按规则**退还本金**（不赢不输）。程序会正确扣除这部分概率，EV 更准确
> （例：小球 3 会显示「净胜 45% / 退 22%」而非虚高的 67%）。
>
> **精确比分对比**：填了 `exact` 后，除价值投注推荐外，还会额外列出所有精确比分的
> **模型概率 vs 赔率隐含概率 vs EV** 明细，方便对比（即便未达 3% 门槛也显示）。
>
> **重复键检测**：JSON 默认对重复键静默保留最后一个，极易埋坑。程序解析时会逐层
> 检查，一旦发现重复键（如同一比分写了多个赔率）立即醒目报警，指出被忽略的值。

## 拉取真实中超数据

### 方式一：中国足协官方 API（推荐，当前赛季）

官方、免费、无需鉴权，队名/升降级永远最新准确（含辽宁铁人等新升班马）：

```bash
# 抓取当前赛季（2026）全部已完赛场次，保存到 seasons/csl_2026_details.json
python3 -m data.cfa_loader
```

- 数据源：`https://api.cfl-china.cn`（中超 CSL / 中甲 CFL1 / 中乙 CFL2）
- 只提供赛程赛果 + 比分，**无**射正/角球/xG，故仅用于训练强度模型
- 只能取当前赛季（服务端忽略历史赛季参数）

### 方式二：API-Football（历史赛季 + 场面统计）

提供**分钟级事件 + 射正/角球/xG**，用于校准 `FEATURE_WEIGHTS`：

```bash
# 设置 API key
export API_FOOTBALL_KEY=你的key

# 单赛季：拉 2025 赛季最新 10 场（自动倒序、本地缓存、遇限速自动重试）
python3 -m data.api_football_loader 2025 --limit 10

# 单赛季：拉整个赛季
python3 -m data.api_football_loader 2025 --all
```

- 缓存写入 `data/apifootball_raw/cache/`，汇总写入 `data/apifootball_raw/seasons/`
- 免费档约 100 请求/天、仅可拉 2022–2024；Pro 档 7500 请求/天、可拉当前赛季
- 提速：`export API_FOOTBALL_DELAY=0.3`（Pro 档限速 300/分钟）
- ⚠️ 其当前赛季参赛名单可能滞后，**当前赛季请优先用方式一（官方 API）**

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
