"""赛前比分预测器（神经网络泊松回归版）。

用「进球回归模型」(data/nn_goals.json) 预测未来一场比赛:
  - 主/客队预期进球 λ
  - 最可能的比分 TOP 若干
  - 胜平负概率、大小球概率、双方进球概率
  - 若提供赔率文件, 额外给出价值投注推荐(EV + 凯利仓位)

前置: 先用全部已有数据训练并保存模型:
    python3 -m data.train_nn --goals --save

用法:
    python3 predict_score.py 主队 客队
    python3 predict_score.py "Shanghai Port" "Beijing Guoan"
    python3 predict_score.py 上海海港 北京国安 --top 12

    # 实时(滚球)预测: 给当前分钟和比分, 预测最终比分
    python3 predict_score.py 上海海港 北京国安 --minute 60 --score 1-0

    # 指定赔率文件, 输出价值投注推荐:
    python3 predict_score.py 上海海港 北京国安 --odds odds.json
    # 生成赔率文件模板:
    python3 predict_score.py --odds-template

    # 从 JSON 文件读全部输入(队名/分钟/比分/赔率), 兼容 predict.py 的中文格式:
    python3 predict_score.py match_cn.json
"""
from __future__ import annotations
import sys
import math
import json
from pathlib import Path
from typing import Dict

import numpy as np


def _fuzzy_find_team(name: str, teams: Dict) -> str | None:
    """把中文/英文队名匹配到模型中的键(复用 predict.py 的逻辑)。"""
    if name in teams:
        return name
    try:
        from data.team_names import zh_to_en
        mapped = zh_to_en(name)
        if mapped and mapped in teams:
            return mapped
    except Exception:
        pass
    low = name.lower().strip()
    for t in teams:
        if t.lower() == low:
            return t
    cands = [t for t in teams if low in t.lower() or t.lower() in low]
    if len(cands) == 1:
        return cands[0]
    import difflib
    close = difflib.get_close_matches(name, list(teams), n=1, cutoff=0.6)
    return close[0] if close else (cands[0] if cands else None)


def _zh(name: str) -> str:
    try:
        from data.team_names import en_to_zh
        return en_to_zh(name) or name
    except Exception:
        return name


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _parse_json_checked(raw: str, path: str) -> dict:
    """解析 JSON, 并检测重复键(json 默认静默保留最后一个, 易致输入错误)。

    发现任一层级有重复键时, 打印醒目警告(指出键名+被丢弃的值)。
    """
    dup_warnings: list = []

    def hook(pairs):
        seen = {}
        for k, v in pairs:
            if k in seen:
                dup_warnings.append((k, seen[k], v))
            seen[k] = v
        return seen

    try:
        from predict import _strip_json_comments
        raw = _strip_json_comments(raw)
    except Exception:
        pass
    data = json.loads(raw, object_pairs_hook=hook)
    if dup_warnings:
        print("⚠️  检测到赔率文件中有重复的键 (JSON 只会保留最后一个, 前面的被忽略):")
        for k, old, new in dup_warnings:
            print(f"    键 \"{k}\" 重复 → 已忽略 {old}, 实际生效 {new}")
        print(f"    请检查 {path} 是否输入错误。\n")
    return data


def predict(home: str, away: str, top_n: int = 8, max_goals: int = 8,
            odds_path: str | None = None, minute: int = 0,
            cur_h: int = 0, cur_a: int = 0,
            odds_dict: dict | None = None) -> None:
    from models.nn_predictor import MLPPoissonRegressor, POISSON_MODEL_PATH
    from data.train_strength import load as load_strength, MODEL_PATH
    from data.train_nn import _features_for

    # 检查模型是否已训练
    if not POISSON_MODEL_PATH.exists() or not MODEL_PATH.exists():
        raise SystemExit(
            "未找到已训练的模型。请先运行:\n"
            "    python3 -m data.train_nn --goals --save")

    strength = load_strength()
    teams = strength["teams"]
    h = _fuzzy_find_team(home, teams)
    a = _fuzzy_find_team(away, teams)
    if not h or not a:
        miss = home if not h else away
        raise SystemExit(
            f"球队 '{miss}' 未在训练数据中找到。\n"
            f"可用球队示例: {', '.join(list(teams)[:8])} ...")

    feats = _features_for(strength, h, a)
    if feats is None:
        raise SystemExit(f"无法为 {h} vs {a} 构造特征。")

    reg = MLPPoissonRegressor.load()
    lam = reg.predict_lambda(np.array([feats], dtype=float))[0]
    lam_full_h, lam_full_a = float(lam[0]), float(lam[1])

    # 实时: 把整场 λ 按剩余时间比例缩放, 得到"剩余时间内还会进的球"的期望
    minute = max(0, min(90, minute))
    live = minute > 0 or cur_h > 0 or cur_a > 0
    remain_frac = (90 - minute) / 90.0
    lam_h = lam_full_h * remain_frac   # 剩余时间的期望进球
    lam_a = lam_full_a * remain_frac

    # 用泊松分布组合出【剩余新增进球】矩阵, 再叠加当前比分得到最终比分
    ph_goals = [_poisson_pmf(i, lam_h) for i in range(max_goals)]
    pa_goals = [_poisson_pmf(j, lam_a) for j in range(max_goals)]
    score_probs = {}
    p_home = p_draw = p_away = 0.0
    over = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    p_btts = 0.0
    for i in range(max_goals):
        for j in range(max_goals):
            p = ph_goals[i] * pa_goals[j]
            fh, fa = cur_h + i, cur_a + j   # 最终比分 = 当前 + 新增
            score_probs[(fh, fa)] = score_probs.get((fh, fa), 0.0) + p
            if fh > fa:
                p_home += p
            elif fh == fa:
                p_draw += p
            else:
                p_away += p
            for line in over:
                if fh + fa > line:
                    over[line] += p
            if fh >= 1 and fa >= 1:
                p_btts += p
    tot = p_home + p_draw + p_away
    p_home, p_draw, p_away = p_home / tot, p_draw / tot, p_away / tot
    p_over25 = over[2.5]

    top = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:top_n]
    likely = top[0][0]

    hz, az = _zh(h), _zh(a)
    print("\n" + "=" * 58)
    if live:
        print(f"  实时比分预测   {hz} (主)  vs  {az} (客)")
        print(f"  当前 {minute}'  比分 {cur_h}-{cur_a}  (剩余 {90 - minute} 分钟)")
    else:
        print(f"  赛前比分预测   {hz} (主)  vs  {az} (客)")
    print("=" * 58)
    if live:
        print(f"\n整场预期 λ:   主队 {lam_full_h:.2f}   -   客队 {lam_full_a:.2f}")
        print(f"剩余预期 λ:   主队 {lam_h:.2f}   -   客队 {lam_a:.2f}   "
              f"(按剩余 {90 - minute} 分钟折算)")
    else:
        print(f"\n预期进球 λ:   主队 {lam_h:.2f}   -   客队 {lam_a:.2f}")
    print(f"最可能{'最终' if live else ''}比分:   {likely[0]} - {likely[1]}   "
          f"(概率 {top[0][1] / tot:.1%})")

    print(f"\n【{'最终' if live else ''}比分概率 TOP {top_n}】")
    for (i, j), p in top:
        bar = "█" * int(p / tot * 50)
        print(f"  {i}-{j}   {p / tot:6.2%}  {bar}")

    print("\n【胜平负】")
    print(f"  主胜 {p_home:.1%}   平局 {p_draw:.1%}   客胜 {p_away:.1%}")
    print("\n【进球盘口】")
    print(f"  大 2.5 {p_over25:.1%}   小 2.5 {1 - p_over25:.1%}")
    print(f"  双方进球 是 {p_btts:.1%}   否 {1 - p_btts:.1%}")
    print(f"  {'最终' if live else ''}总进球期望 {cur_h + cur_a + lam_h + lam_a:.2f}")

    # ---- 若提供赔率(文件或字典), 输出价值投注推荐 ----
    if odds_path or odds_dict:
        model_probs = {
            "home": p_home, "draw": p_draw, "away": p_away,
            "btts_yes": p_btts, "btts_no": 1 - p_btts,
        }
        for line, pv in over.items():
            model_probs[f"over_{line}"] = pv
            model_probs[f"under_{line}"] = 1 - pv
        # 归一化后的精确比分概率
        cs_probs = {k: v / tot for k, v in score_probs.items()}
        _report_value_bets(model_probs, cs_probs,
                            odds_path=odds_path, odds_dict=odds_dict)

    print("\n⚠️ 仅供学习研究，模型不保证准确，请勿用于真实赌博。")


def _load_odds(path: str) -> dict:
    """读取赔率 JSON 文件。支持中英文键和 // 注释。"""
    raw = Path(path).read_text(encoding="utf-8")
    d = _parse_json_checked(raw, path)
    # 中文键映射
    alias = {"主胜": "home", "平局": "draw", "平": "draw", "客胜": "away",
             "大球": "over", "小球": "under", "大": "over", "小": "under",
             "双方进球": "btts_yes", "精确比分": "exact", "比分": "exact"}
    return {alias.get(k, k): v for k, v in d.items()}


def _report_value_bets(probs: dict, cs_probs: dict,
                       odds_path: str | None = None,
                       odds_dict: dict | None = None) -> None:
    """用模型概率 + 赔率, 输出正 EV 的价值投注(EV + 凯利仓位)。"""
    from strategy.decision import (_ev, _kelly, MIN_EDGE, KELLY_FRACTION,
                                   MAX_STAKE_PER_BET, MIN_ODDS, MAX_ODDS)
    odds = odds_dict if odds_dict is not None else _load_odds(odds_path or "")
    recs = []  # (市场, 赔率, 模型概率, EV, 仓位)

    def consider(name: str, p: float, o):
        if o is None:
            return
        o = float(o)
        if o < MIN_ODDS or o > MAX_ODDS:
            return
        edge = _ev(p, o)
        if edge < MIN_EDGE:
            return
        stake = min(_kelly(p, o) * KELLY_FRACTION, MAX_STAKE_PER_BET)
        if stake > 0:
            recs.append((name, o, p, edge, stake))

    def consider_push(name: str, p_win: float, p_push: float, o):
        """处理带 push(和局退款) 的盘口, 如整数大小球线 3.0。
        EV = p_win*(o-1) - p_lose;  仓位按「排除退款后」的条件概率算凯利。"""
        if o is None:
            return
        o = float(o)
        if o < MIN_ODDS or o > MAX_ODDS:
            return
        p_lose = 1 - p_win - p_push
        edge = p_win * (o - 1) - p_lose
        if edge < MIN_EDGE:
            return
        active = p_win + p_lose  # 非退款概率
        p_cond = p_win / active if active > 0 else 0.0
        stake = min(_kelly(p_cond, o) * KELLY_FRACTION, MAX_STAKE_PER_BET)
        if stake > 0:
            note = f"{name}(净胜{p_win:.0%}/退{p_push:.0%})"
            recs.append((note, o, p_win, edge, stake))

    # 胜平负
    consider("胜平负:主胜", probs["home"], odds.get("home"))
    consider("胜平负:平局", probs["draw"], odds.get("draw"))
    consider("胜平负:客胜", probs["away"], odds.get("away"))

    # 大小球(从最终比分矩阵实时计算, 支持任意盘口线)
    def over_prob(line: float) -> float:
        return sum(p for (i, j), p in cs_probs.items() if i + j > line)

    def exact_total(line: float) -> float:
        return sum(p for (i, j), p in cs_probs.items() if i + j == line)

    def is_integer_line(line: float) -> bool:
        return abs(line - round(line)) < 1e-9

    for line, o in (odds.get("over") or {}).items():
        ln = float(line)
        pv = over_prob(ln)
        if is_integer_line(ln):
            # 整数线: 总进球==line 时退款(push)
            consider_push(f"大球 {line}", pv, exact_total(ln), o)
        else:
            consider(f"大球 {line}", pv, o)
    for line, o in (odds.get("under") or {}).items():
        ln = float(line)
        pv_under = 1 - over_prob(ln) - (exact_total(ln) if is_integer_line(ln) else 0.0)
        if is_integer_line(ln):
            consider_push(f"小球 {line}", pv_under, exact_total(ln), o)
        else:
            consider(f"小球 {line}", 1 - over_prob(ln), o)
    # 双方进球
    consider("双方进球:是", probs["btts_yes"], odds.get("btts_yes"))
    consider("双方进球:否", probs["btts_no"], odds.get("btts_no"))
    # 精确比分
    exact_odds = odds.get("exact") or {}
    exact_rows = []
    for k, o in exact_odds.items():
        try:
            sc = tuple(map(int, str(k).split("-")))
        except ValueError:
            continue
        pm = cs_probs.get(sc, 0.0)
        exact_rows.append((str(k), float(o), pm))
        consider(f"精确比分 {k}", pm, o)

    recs.sort(key=lambda r: r[3], reverse=True)
    print("\n【价值投注建议 (仅列出 EV≥3% 的)】")
    if not recs:
        print("  无。当前赔率下没有发现有价值的投注。")
    else:
        for name, o, p, edge, stake in recs:
            print(f"  ✅ {name:14s} 赔率 {o:5.2f}  模型概率 {p:.1%}  "
                  f"EV {edge:+.1%}  建议仓位 {stake:.2%}")
        print("  (仓位=占总资金比例, 已用 1/4 凯利并封顶 2%)")

    # 精确比分明细(即便未达 EV 门槛也列出, 方便对比)
    if exact_rows:
        print("\n【精确比分对比 (模型概率 vs 赔率隐含)】")
        for k, o, pm in sorted(exact_rows, key=lambda r: r[2], reverse=True):
            imp = 1 / o if o > 0 else 0.0
            ev = pm * (o - 1) - (1 - pm)
            flag = " ✅" if ev >= MIN_EDGE else ""
            print(f"  {k:>5s}  赔率 {o:5.2f}  模型 {pm:5.1%}  "
                  f"隐含 {imp:5.1%}  EV {ev:+6.1%}{flag}")


def write_odds_template(path: str = "odds.example.json") -> None:
    template = '''{
  // ===== 赛前赔率文件 (小数/欧洲赔率, 支持 // 注释) =====
  //   运行: python3 predict_score.py 主队 客队 --odds odds.example.json
  //   只填你关心的盘口即可, 未填的会自动跳过

  "home": 1.55,          // 主胜赔率
  "draw": 3.80,          // 平局赔率
  "away": 7.50,          // 客胜赔率

  "over":  { "2.5": 2.40 },   // 大球, 可加 "1.5"/"3.5"
  "under": { "2.5": 1.60 },   // 小球

  "btts_yes": 1.90,      // 双方进球 是 (可选)
  "btts_no": 1.85,       // 双方进球 否 (可选)

  "exact": {             // 精确比分赔率(可选), 键 "主-客"
    "2-0": 5.5,
    "1-0": 4.2,
    "2-1": 8.0
  }
}
'''
    Path(path).write_text(template, encoding="utf-8")
    print(f"已生成赔率模板: {path}")
    print(f"编辑后运行: python3 predict_score.py 主队 客队 --odds {path}")


def build_from_json(path: str) -> dict:
    """解析比赛 JSON 文件(兼容 predict.py 的嵌套中文键格式)。

    返回 dict: {home, away, minute, cur_h, cur_a, odds}
    支持两种结构:
      1) 嵌套: {"比赛状态": {...}, "赔率": {...}}  (match_cn.json 风格)
      2) 扁平: {"主队":..., "分钟":..., "主胜":...}
    """
    raw = Path(path).read_text(encoding="utf-8")
    data = _parse_json_checked(raw, path)

    # 顶层键归一: 比赛状态/场面 -> state, 赔率 -> odds
    top = {}
    for k, v in data.items():
        if k in ("比赛状态", "场面", "state"):
            top["state"] = v
        elif k in ("赔率", "投注赔率", "odds"):
            top["odds"] = v
        else:
            top[k] = v
    # 若没有嵌套 state, 则整个顶层就是场面
    state = top.get("state", data)

    state_alias = {
        "主队": "home", "客队": "away", "主队名": "home", "客队名": "away",
        "home_team": "home", "away_team": "away",
        "分钟": "minute", "比赛分钟": "minute", "时间": "minute",
        "主队进球": "score_h", "客队进球": "score_a",
        "主队比分": "score_h", "客队比分": "score_a",
        "score_h": "score_h", "score_a": "score_a",
    }
    s = {state_alias.get(k, k): v for k, v in state.items()}

    home = s.get("home")
    away = s.get("away")
    if not home or not away:
        raise SystemExit(f"{path} 缺少主队/客队(home/away 或 主队/客队)。")

    # 赔率: 归一中文键
    odds_raw = top.get("odds", {})
    odds_alias = {"主胜": "home", "平局": "draw", "平": "draw", "客胜": "away",
                  "大球": "over", "小球": "under", "大": "over", "小": "under",
                  "双方进球": "btts_yes", "精确比分": "exact", "比分": "exact"}
    odds = {odds_alias.get(k, k): v for k, v in odds_raw.items()}

    return {
        "home": home, "away": away,
        "minute": int(s.get("minute", 0) or 0),
        "cur_h": int(s.get("score_h", 0) or 0),
        "cur_a": int(s.get("score_a", 0) or 0),
        "odds": odds if odds else None,
    }


def main() -> None:
    args = sys.argv[1:]
    if "--odds-template" in args:
        write_odds_template()
        return
    top_n = 8
    if "--top" in args:
        k = args.index("--top")
        if k + 1 < len(args):
            top_n = int(args[k + 1])
        args = [a for i, a in enumerate(args)
                if i != k and i != k + 1]

    # 单个已存在的文件参数 -> JSON 模式(队名/分钟/比分/赔率全从文件读)
    file_args = [a for a in args if not a.startswith("--")]
    if len(file_args) == 1 and Path(file_args[0]).exists():
        cfg = build_from_json(file_args[0])
        predict(cfg["home"], cfg["away"], top_n=top_n,
                minute=cfg["minute"], cur_h=cfg["cur_h"], cur_a=cfg["cur_a"],
                odds_dict=cfg["odds"])
        return

    odds_path = None
    if "--odds" in args:
        k = args.index("--odds")
        if k + 1 < len(args):
            odds_path = args[k + 1]
            if not Path(odds_path).exists():
                raise SystemExit(f"赔率文件不存在: {odds_path}\n"
                                 f"可先生成模板: python3 predict_score.py --odds-template")
        args = [a for i, a in enumerate(args)
                if i != k and i != k + 1]
    # --minute N: 实时预测的当前分钟
    minute = 0
    if "--minute" in args:
        k = args.index("--minute")
        if k + 1 < len(args):
            minute = int(args[k + 1])
        args = [a for i, a in enumerate(args)
                if i != k and i != k + 1]
    # --score H-A: 当前比分(如 1-0)
    cur_h = cur_a = 0
    if "--score" in args:
        k = args.index("--score")
        if k + 1 < len(args):
            try:
                cur_h, cur_a = map(int, args[k + 1].split("-"))
            except ValueError:
                raise SystemExit("--score 格式应为 主-客, 例如 --score 1-0")
        args = [a for i, a in enumerate(args)
                if i != k and i != k + 1]
    if len(args) < 2:
        raise SystemExit(
            "用法:  python3 predict_score.py 主队 客队 [选项]\n"
            "  或:  python3 predict_score.py match_cn.json   (从文件读全部输入)\n"
            "  --top N          显示前 N 个比分\n"
            "  --odds 文件      指定赔率文件, 输出价值投注\n"
            "  --minute N       实时预测: 当前比赛分钟(0~90)\n"
            "  --score H-A      实时预测: 当前比分, 如 --score 1-0\n"
            "示例:\n"
            "  python3 predict_score.py 上海海港 北京国安\n"
            "  python3 predict_score.py 上海海港 北京国安 --minute 60 --score 1-0\n"
            "  python3 predict_score.py 上海海港 北京国安 --odds odds.json\n"
            "  python3 predict_score.py match_cn.json\n"
            "生成赔率模板: python3 predict_score.py --odds-template\n"
            "(需先运行: python3 -m data.train_nn --goals --save)")
    predict(args[0], args[1], top_n=top_n, odds_path=odds_path,
            minute=minute, cur_h=cur_h, cur_a=cur_a)


if __name__ == "__main__":
    main()
