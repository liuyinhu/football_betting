# 中超足球赛前预测与投注推荐系统

一个用 Python 写的中超（中国足球超级联赛）比赛预测工具。你只要告诉它**两支球队**，它就能算出：

- 这场比赛**谁赢的概率**（主胜 / 平局 / 客胜）
- **最可能的比分**（如 2:0、1:1）
- 大小球、双方是否都进球等各种玩法的概率
- 如果你再输入**赔率**，它会告诉你**哪些投注"长期看有利可图"**，并建议下多少注

它有两种用法：**网页版**（点点鼠标，推荐新手）和**命令行版**（敲命令，更灵活）。

> ⚠️ **重要提示**：本项目仅供**学习和研究**。在中国大陆参与赌博是违法的；而且长期战胜博彩公司极其困难，本模型**不保证盈利**，请勿用于真实赌博。

---

## 一、准备工作（只需做一次）

### 1. 确认电脑装了 Python

打开终端（Mac 的"终端"、Windows 的"命令提示符"），输入：

```bash
python3 --version
```

能看到 `Python 3.x.x` 就说明装好了。没有的话请先去 [python.org](https://www.python.org/) 下载安装。

### 2. 下载本项目并安装依赖

```bash
# 进入项目文件夹（下面命令都要在这个文件夹里运行）
cd qqq

# 安装依赖（只需要 numpy 和 scipy 两个库）
pip install -r requirements.txt
```

### 3. 训练模型（第一次使用必做）

模型需要"学习"历史比赛数据才能预测。运行下面这条命令，它会自动完成学习并保存结果：

```bash
python3 -m data.train_strength
```

看到类似 `converged: true` 就成功了，会生成一个 `data/csl_strength.json` 文件。

> 📌 **小知识**：这一步是让程序根据每支球队过去的战绩，算出它们的"进攻能力"和"防守能力"。之后所有预测都基于它。

---

## 二、网页版（推荐新手）

网页版最简单：一个页面列出**接下来 10 场中超比赛**，每场都有预测概率；想看投注建议就输入赔率。

### 启动

```bash
./start_web.sh
```

这条命令会自动启动前端和后端，然后你在浏览器里打开：

**http://127.0.0.1:5173/**

按 `Ctrl + C` 可以停止。

> ⚠️ 网页前端需要 **Node.js 18 或更高版本**（一个运行网页程序的工具，需另行安装）。
> 脚本会自动帮你安装网页依赖，首次启动会稍慢，请耐心等待。

### 怎么用

1. 打开页面，能看到接下来 10 场比赛，每场都显示了**胜平负概率条**、大小球、最可能比分、半全场矩阵等。
2. 想要投注建议？点某场比赛下方的输入框，填入你在博彩网站看到的**赔率**。
3. 可以只填主胜/平局/客胜，也可以展开填**大小球 / 半全场 / 比分**赔率（都是可选的）。
4. 点"获取投注建议"，程序会列出**值得下注**（长期期望为正）的选项和建议仓位。

### 实时预测（比赛进行中）

页面顶部有「**赛前预测 / 实时预测**」两个标签。切到"实时预测"后：

- 页面会列出**当前正在进行的中超比赛**，显示**比赛分钟、实时比分、射门/射正/角球/控球**等场面数据；
- 每 **30 秒自动刷新**一次，预测概率会随比赛进程动态更新；
- 无需操作，看着数据和预测实时变化即可。

> ⚠️ **实时功能需要数据源 API key**。实时比分来自 [API-Football](https://www.api-football.com/)，
> 只有在启动后端时提供 `API_FOOTBALL_KEY` 环境变量才会启用；否则实时页会提示"未启用实时更新"（赛前预测不受影响）。

开启实时预测的启动方式：

```bash
API_FOOTBALL_KEY=你的key ./start_web.sh
```

（当前若没有正在进行的中超比赛，实时页会显示"当前没有进行中的中超比赛"，属正常。）

### 遇到问题？

- 页面打不开：确认 `./start_web.sh` 那个终端窗口没有关，且没有报错。
- 后端 / 前端日志分别在 `/tmp/csl_backend.log` 和 `/tmp/csl_frontend.log`，出错时可以查看。

---

## 三、命令行版

不想开网页、想快速查一场，或者想做更多定制，可以用命令行。

### 最简单：给两个队名，看谁赢

```bash
python3 predict.py 辽宁铁人 北京国安
```

程序会输出双方胜率、最可能比分、大小球等。队名支持中文和常见别名（如"山东泰山"也可写"鲁能"），会自动模糊匹配。

### 看详细比分预测

```bash
python3 predict_score.py 北京国安 长春亚泰
```

输出示例：

```
  赛前比分预测   北京国安 (主)  vs  长春亚泰 (客)
预期进球:     主队 2.54   -   客队 0.88
最可能比分:   2 - 0   (概率 10.6%)
【比分概率 TOP 8】  2-0 10.6% / 2-1 9.3% / 3-0 9.0% / 1-0 8.3% ...
【胜平负】         主胜 73.2%   平局 15.9%   客胜 10.9%
【进球盘口】       大2.5 66.1%   双方进球 是 53.8%
```

### 加上赔率，得到投注建议

先生成一个赔率模板文件，填好后再预测：

```bash
python3 predict_score.py --odds-template                       # 生成 odds.example.json 模板
python3 predict_score.py 北京国安 长春亚泰 --odds odds.example.json
```

带 `--odds` 后会多出**价值投注建议**：程序对比"模型算的概率"和"赔率隐含的概率"，
筛出期望收益 ≥ 3% 的选项，并按 1/4 凯利公式建议下注比例（最多押总资金的 2%）。

### 比赛进行中的实时预测

比赛踢到一半，输入当前分钟和比分，预测最终结果：

```bash
python3 predict_score.py 北京国安 长春亚泰 --minute 60 --score 1-0
```

（原理：把整场进球预期按剩余时间折算，再加上已经进的球。）

---

## 四、用文件输入更复杂的信息（进阶）

如果想输入射正、角球、xG、红牌等更详细的场面数据，可以写一个 JSON 文件。
所有字段和队名**都支持中文**：

```jsonc
{
  "比赛状态": {
    "主队": "上海海港", "客队": "北京国安",
    "分钟": 60, "主队进球": 1, "客队进球": 0,
    "主队射正": 4, "客队射正": 2,      // 射正对进球影响最大
    "主队角球": 5, "客队角球": 3,
    "主队红牌": 0, "客队红牌": 0        // 每张红牌使该队进球预期 ×0.65
  },
  "赔率": {                            // 可选，填了才给投注建议
    "主胜": 1.35, "平局": 4.50, "客胜": 9.00,
    "大球": { "2.5": 2.40 }, "小球": { "2.5": 1.60 },
    "精确比分": { "1-1": 7.10 }        // 键为「主-客」
  }
}
```

保存为 `my_match.json` 后运行：

```bash
python3 predict.py my_match.json
```

> 💡 项目自带示例 `match_cn.json`，可直接 `python3 predict.py match_cn.json` 试跑。
> 想要空白模板：`python3 predict.py -t`。文件里支持 `//` 注释。

**xG 是什么？** xG（预期进球）衡量射门机会的质量——把每次射门按"进球可能性"累加。
xG=1.3 表示按机会质量估算约该进 1.3 球，比单纯数"射门数"更能反映威胁，所以权重最高。

---

## 五、更新比赛数据

程序自带的数据可能不是最新的。想拉最新赛果：

```bash
# 推荐：中国足协官方 API，免费、无需注册，当前赛季队名最准（含新升班马）
python3 -m data.cfa_loader
```

拉完记得**重新训练**：`python3 -m data.train_strength`。

> 还有一个数据源 API-Football（提供射正/角球/xG 等更细的历史数据），需要注册 API key，
> 用于校准模型。新手一般用不到，进阶说明见下方。

---

## 六、进阶内容

<details>
<summary>点击展开：模型验证、神经网络版、参数调整、数据源细节</summary>

### 验证模型准确率

```bash
python3 -m data.validate               # 默认 2024+2025 训练、2026 测试
python3 -m data.validate 2024,2025 2026
```

参考：准确率约 **49.6%** / log-loss 约 **1.04**，优于「永远猜主胜」基线（48.7% / 1.10）。

### 神经网络版本（可选）

除默认的 Dixon-Coles 解析模型外，还有一个纯 NumPy 实现的神经网络（MLP），零新增依赖：

```bash
python3 -m data.train_nn                       # 训练胜平负三分类器
python3 -m data.train_nn --validate            # 与 Dixon-Coles 并排对比
python3 -m data.train_nn --recent 30 --half-life 450   # 日期切分 + 时间权重
python3 -m data.train_nn --goals --save        # 进球数泊松回归，训练并保存
```

结论：**样本量比数据新鲜度更重要**。加入更多历史赛季后准确率从 ~51% 升到 **~63%**。

### API-Football 数据源

```bash
export API_FOOTBALL_KEY=你的key
python3 -m data.api_football_loader 2024 --limit 10   # 拉最新 10 场
python3 -m data.api_football_loader 2024 --all        # 拉整季
python3 -m data.analyze_apifootball 2024              # 分析、校准特征权重
```

两个数据源统一汇入 `data/apifootball_raw/seasons/`，按比赛 ID 合并去重后训练，队名已对齐。
**当前赛季用官方 API**（API-Football 的 2026 参赛名单滞后）。免费档约 100 请求/天，已内置缓存与重试。

### 可调参数

| 位置 | 参数 | 说明 |
|------|------|------|
| `strategy/decision.py` | `MIN_EDGE` | 下注最小期望收益（默认 3%） |
| | `KELLY_FRACTION` | 凯利比例（默认 1/4） |
| | `MAX_STAKE_PER_BET` | 单注上限（默认总资金 2%） |
| | `MIN_ODDS` / `MAX_ODDS` | 过滤过低 / 过高的赔率 |
| `models/poisson_live.py` | `FEATURE_WEIGHTS` | 各场面统计对进球预期的权重 |
| | `RED_CARD_PENALTY` | 减员至 10 人时的进球预期乘数 |

### 模拟回测

```bash
python3 main.py              # 单场模拟演示
python3 main.py mc 500       # 500 场蒙特卡洛回测
```

</details>

---

## 七、常见问题

**Q：运行时报 `ModuleNotFoundError: No module named 'core'` / `data`？**
A：必须在**项目根目录**（`qqq/`）里运行。顶层脚本用 `python3 predict.py`，子模块用 `python3 -m data.xxx`。

**Q：提示"球队未在训练数据中找到"？**
A：这支队不在你训练用的赛季里。跑 `python3 -m data.cfa_loader` 拉最新数据后重新训练。

**Q：网页版启动失败 / 打不开？**
A：确认装了 Node.js 18+；查看 `/tmp/csl_frontend.log` 和 `/tmp/csl_backend.log` 里的报错信息。

**Q：投注建议为什么经常是空的？**
A：只有当模型认为"某个赔率明显偏高、长期有利可图"（期望收益 ≥ 3%）时才推荐。多数赔率被博彩公司定得很准，没有价值属正常。

---

## 项目结构（给想读代码的人）

```
qqq/
├── core/state.py             # 数据结构：比赛状态 / 赔率 / 投注建议
├── models/poisson_live.py    # 核心模型：时变泊松 + Dixon-Coles（比分/胜平负/半全场）
├── models/nn_predictor.py    # 神经网络版（纯 NumPy）
├── strategy/decision.py      # 投注决策：EV 过滤 + 凯利仓位
├── data/                     # 数据加载 / 训练 / 验证 / 队名映射
│   ├── train_strength.py         # 训练攻防强度 → csl_strength.json
│   ├── cfa_loader.py             # 中国足协官方 API（当前赛季）
│   ├── api_football_loader.py    # API-Football（历史赛季 + 场面统计）
│   └── upcoming.py               # 拉未开赛赛程（网页版用）
├── predict.py                # 通用预测入口
├── predict_score.py          # 比分预测入口
├── main.py                   # 演示 + 蒙特卡洛回测
├── webapp/                   # 网页后端（Flask，端口 5001）
├── frontend/                 # 网页前端（Vue 3 + Vite，端口 5173）
└── start_web.sh              # 一键启动前后端
```

**网页版技术架构**：浏览器 → Vite 前端(:5173) →（`/api` 代理）→ Flask 后端(:5001) → 预测模型。
后端主要接口：`GET /api/matches?limit=10`（返回赛程+预测）、`POST /api/predict`（传赔率、返回投注建议）、
`GET /api/live`（进行中比赛的实时状态+预测，需配置 `API_FOOTBALL_KEY`，否则返回 `live_enabled:false`）。
实时数据源模块：`feeds/live_apifootball.py`（真实源）与 `feeds/live_sim_manager.py`（模拟源，设 `LIVE_SOURCE=sim` 启用）。
