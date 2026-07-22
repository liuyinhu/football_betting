"""赛前比分预测器（神经网络泊松回归版）。

用「进球回归模型」(data/nn_goals.json) 预测未来一场比赛:
  - 主/客队预期进球 λ
  - 最可能的比分 TOP 若干
  - 胜平负概率、大小球概率、双方进球概率

前置: 先用全部已有数据训练并保存模型:
    python3 -m data.train_nn --goals --save

用法:
    python3 predict_score.py 主队 客队
    python3 predict_score.py "Shanghai Port" "Beijing Guoan"
    python3 predict_score.py 上海海港 北京国安 --top 12
"""
from __future__ import annotations
import sys
import math
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


def predict(home: str, away: str, top_n: int = 8, max_goals: int = 8) -> None:
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
    lam_h, lam_a = float(lam[0]), float(lam[1])

    # 用泊松分布组合出比分矩阵
    ph_goals = [_poisson_pmf(i, lam_h) for i in range(max_goals)]
    pa_goals = [_poisson_pmf(j, lam_a) for j in range(max_goals)]
    score_probs = {}
    p_home = p_draw = p_away = 0.0
    p_over25 = p_btts = 0.0
    for i in range(max_goals):
        for j in range(max_goals):
            p = ph_goals[i] * pa_goals[j]
            score_probs[(i, j)] = p
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
            if i + j > 2.5:
                p_over25 += p
            if i >= 1 and j >= 1:
                p_btts += p
    tot = p_home + p_draw + p_away
    p_home, p_draw, p_away = p_home / tot, p_draw / tot, p_away / tot

    top = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:top_n]
    likely = top[0][0]

    hz, az = _zh(h), _zh(a)
    print("\n" + "=" * 58)
    print(f"  赛前比分预测   {hz} (主)  vs  {az} (客)")
    print("=" * 58)
    print(f"\n预期进球 λ:   主队 {lam_h:.2f}   -   客队 {lam_a:.2f}")
    print(f"最可能比分:   {likely[0]} - {likely[1]}   "
          f"(概率 {top[0][1] / tot:.1%})")

    print(f"\n【比分概率 TOP {top_n}】")
    for (i, j), p in top:
        bar = "█" * int(p / tot * 50)
        print(f"  {i}-{j}   {p / tot:6.2%}  {bar}")

    print("\n【胜平负】")
    print(f"  主胜 {p_home:.1%}   平局 {p_draw:.1%}   客胜 {p_away:.1%}")
    print("\n【进球盘口】")
    print(f"  大 2.5 {p_over25:.1%}   小 2.5 {1 - p_over25:.1%}")
    print(f"  双方进球 是 {p_btts:.1%}   否 {1 - p_btts:.1%}")
    print(f"  总进球期望 {lam_h + lam_a:.2f}")
    print("\n⚠️ 仅供学习研究，模型不保证准确，请勿用于真实赌博。")


def main() -> None:
    args = sys.argv[1:]
    top_n = 8
    if "--top" in args:
        k = args.index("--top")
        if k + 1 < len(args):
            top_n = int(args[k + 1])
        args = [a for i, a in enumerate(args)
                if i != k and i != k + 1]
    if len(args) < 2:
        raise SystemExit(
            "用法:  python3 predict_score.py 主队 客队 [--top N]\n"
            "示例:  python3 predict_score.py 上海海港 北京国安\n"
            "(需先运行: python3 -m data.train_nn --goals --save)")
    predict(args[0], args[1], top_n=top_n)


if __name__ == "__main__":
    main()
