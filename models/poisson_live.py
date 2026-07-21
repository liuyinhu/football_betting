"""基于时变泊松模型的实时比分概率预测器。

核心思路：
1. 每支球队在剩余时间内有一个「剩余」进球率 lambda。
2. lambda 由赛前先验值 + 实时场面修正得到，场面因素包括：
   射正、角球、危险进攻、xG、红牌差等。
3. 剩余进球数 ~ Poisson(lambda_remaining)。最终比分分布 =
   当前比分 + 两队各自独立的泊松抽样。
4. 对低比分相关性做小幅修正(Dixon-Coles rho)。
"""
from __future__ import annotations
import math
from typing import Dict, Tuple

from scipy.stats import poisson

from core.state import MatchState


# ---- 场面特征对剩余 lambda 的权重(可调节/可学习) ----
FEATURE_WEIGHTS = {
    "sot":       0.045,   # 每多一个领先对手的射正, 提升进球率
    "corner":    0.012,   # 角球差
    "danger":    0.004,   # 危险进攻差
    "xg":        0.30,    # xG 差信息量最大
    "possession":0.004,   # 控球率每高出 50% 的部分
}

# 红牌惩罚(对减员一方的 lambda 做乘法衰减)
RED_CARD_PENALTY = 0.65


def _adjust_lambda(base_lambda: float,
                   own_feats: Dict[str, float],
                   opp_feats: Dict[str, float],
                   red_own: int,
                   red_opp: int) -> float:
    """根据实时节奏与 xG 差值, 调整球队的全场(per-90) lambda。"""
    delta = 0.0
    for k, w in FEATURE_WEIGHTS.items():
        delta += w * (own_feats.get(k, 0.0) - opp_feats.get(k, 0.0))

    # 用指数调整, 保证 lambda 永远 > 0
    lam = base_lambda * math.exp(delta)

    # 红牌惩罚叠加
    lam *= RED_CARD_PENALTY ** red_own
    lam /= RED_CARD_PENALTY ** red_opp   # 对手减员 → 本队更容易进球
    return max(lam, 0.01)


def compute_residual_lambdas(state: MatchState) -> Tuple[float, float]:
    """计算两队在比赛剩余时间内的预期进球数。"""
    frac_left = state.remaining / 90.0
    if frac_left <= 0:
        return 0.0, 0.0

    home_feats = {
        "sot": state.sot_h,
        "corner": state.corners_h,
        "danger": state.dangerous_attacks_h,
        "xg": state.xg_h,
        "possession": state.possession_h - 50.0,
    }
    away_feats = {
        "sot": state.sot_a,
        "corner": state.corners_a,
        "danger": state.dangerous_attacks_a,
        "xg": state.xg_a,
        "possession": (100 - state.possession_h) - 50.0,
    }

    lam_h_90 = _adjust_lambda(state.prior_lambda_h,
                              home_feats, away_feats,
                              state.red_h, state.red_a)
    lam_a_90 = _adjust_lambda(state.prior_lambda_a,
                              away_feats, home_feats,
                              state.red_a, state.red_h)

    return lam_h_90 * frac_left, lam_a_90 * frac_left


def _dc_tau(i: int, j: int, lam_h: float, lam_a: float, rho: float = -0.10) -> float:
    """Dixon-Coles 低比分修正系数。"""
    if i == 0 and j == 0:
        return 1 - lam_h * lam_a * rho
    if i == 0 and j == 1:
        return 1 + lam_h * rho
    if i == 1 and j == 0:
        return 1 + lam_a * rho
    if i == 1 and j == 1:
        return 1 - rho
    return 1.0


def final_score_distribution(state: MatchState,
                             max_extra_goals: int = 6) -> Dict[Tuple[int, int], float]:
    """返回最终比分的概率分布 P(final_score = (主, 客))。"""
    lam_h, lam_a = compute_residual_lambdas(state)

    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for i in range(max_extra_goals + 1):
        for j in range(max_extra_goals + 1):
            p = poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
            p *= _dc_tau(i, j, lam_h, lam_a)
            dist[(state.score_h + i, state.score_a + j)] = p
            total += p

    # 归一化(尾部截断 + DC 修正会使总概率略有偏移)
    if total > 0:
        for k in dist:
            dist[k] /= total
    return dist


def outcome_probabilities(state: MatchState) -> Dict[str, float]:
    """返回主胜/平/客胜概率, 以及大小球、双方进球等常用市场概率。"""
    dist = final_score_distribution(state)
    p_home = p_draw = p_away = 0.0
    over_probs = {1.5: 0.0, 2.5: 0.0, 3.5: 0.0}
    btts_yes = 0.0

    for (h, a), p in dist.items():
        if h > a:
            p_home += p
        elif h == a:
            p_draw += p
        else:
            p_away += p
        total_goals = h + a
        for line in over_probs:
            if total_goals > line:
                over_probs[line] += p
        if h > 0 and a > 0:
            btts_yes += p

    return {
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "over_1.5": over_probs[1.5],
        "over_2.5": over_probs[2.5],
        "over_3.5": over_probs[3.5],
        "under_1.5": 1 - over_probs[1.5],
        "under_2.5": 1 - over_probs[2.5],
        "under_3.5": 1 - over_probs[3.5],
        "btts_yes": btts_yes,
        "btts_no": 1 - btts_yes,
    }
