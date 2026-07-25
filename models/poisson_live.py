"""基于时变泊松模型的实时比分概率预测器。

核心思路：
1. 每支球队在剩余时间内有一个「剩余」进球率 lambda。
2. lambda 由赛前先验值 + 实时场面修正得到，场面因素包括：
   射正、角球、危险进攻、xG、红牌差等。
3. 剩余进球数 ~ Poisson(lambda_remaining)。最终比分分布 =
   当前比分 + 两队各自独立的泊松抽样。
4. 对低比分相关性做小幅修正(Dixon-Coles rho)。
5. 半全场(HT/FT)预测：把整场进球率按上/下半场占比拆成两段独立泊松过程。
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


def adjusted_lambdas_90(state: MatchState) -> Tuple[float, float]:
    """返回两队经场面修正后的**全场(per-90)** 进球率 lambda。

    与 compute_residual_lambdas 的区别：这里不乘剩余时间比例，
    是「若整场按当前节奏踢满 90 分钟」的期望进球率。
    半全场预测按上下半场拆分时需要它。
    """
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
    lam_h_90 = _adjust_lambda(state.prior_lambda_h, home_feats, away_feats,
                              state.red_h, state.red_a)
    lam_a_90 = _adjust_lambda(state.prior_lambda_a, away_feats, home_feats,
                              state.red_a, state.red_h)
    return lam_h_90, lam_a_90


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


# ---------------------------------------------------------------------------
# 半全场 (HT/FT) 预测
# ---------------------------------------------------------------------------
# 上半场进球占比：由 data/apifootball_raw 全部分钟级进球事件校准
#   (868 场 / 2652 球：上半场 43.0%、下半场 57.0%)
FIRST_HALF_GOAL_FRACTION = 0.43


def _half_score_distribution(lam_h: float, lam_a: float,
                             max_goals: int = 6) -> Dict[Tuple[int, int], float]:
    """给定某半场两队的进球率, 返回该半场比分 (主, 客) 的概率分布。"""
    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
            p *= _dc_tau(i, j, lam_h, lam_a)
            dist[(i, j)] = p
            total += p
    if total > 0:
        for k in dist:
            dist[k] /= total
    return dist


def _sign(h: int, a: int) -> str:
    """比分 -> 胜平负标识: 'home' / 'draw' / 'away'。"""
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def half_full_distribution(state: MatchState,
                           max_goals: int = 6) -> Dict[str, float]:
    """返回半全场 (HT/FT) 9 种组合的概率。

    仅支持**赛前**预测 (minute=0, 比分 0-0)；把整场进球率按
    上/下半场占比拆成两段独立泊松过程, 联合求和得到:
        - 半场比分  = 上半场比分
        - 全场比分  = 上半场 + 下半场比分

    返回 key 形如 "home/home"、"draw/away" (前=半场, 后=全场), 共 9 项;
    另附 3 个边际: "ht_home"/"ht_draw"/"ht_away" (半场胜平负边际概率)。
    """
    lam_h_90, lam_a_90 = adjusted_lambdas_90(state)

    f1 = FIRST_HALF_GOAL_FRACTION
    f2 = 1.0 - f1
    # 上半场 / 下半场各自的进球率
    d1 = _half_score_distribution(lam_h_90 * f1, lam_a_90 * f1, max_goals)
    d2 = _half_score_distribution(lam_h_90 * f2, lam_a_90 * f2, max_goals)

    signs = ("home", "draw", "away")
    combo: Dict[str, float] = {f"{ht}/{ft}": 0.0 for ht in signs for ft in signs}
    ht_marg: Dict[str, float] = {s: 0.0 for s in signs}

    for (h1, a1), p1 in d1.items():
        ht = _sign(h1, a1)
        ht_marg[ht] += p1
        for (h2, a2), p2 in d2.items():
            ft = _sign(h1 + h2, a1 + a2)
            combo[f"{ht}/{ft}"] += p1 * p2

    result = dict(combo)
    result["ht_home"] = ht_marg["home"]
    result["ht_draw"] = ht_marg["draw"]
    result["ht_away"] = ht_marg["away"]
    return result


def _poisson_score_dist(lam_h: float, lam_a: float,
                        max_goals: int = 6) -> Dict[Tuple[int, int], float]:
    """给定两队进球率, 返回增量比分 (主, 客) 的概率分布 (含 DC 修正+归一化)。

    与 _half_score_distribution 相同, 语义上表示「某一段时间内新增的进球」。
    """
    return _half_score_distribution(lam_h, lam_a, max_goals)


def live_half_full_distribution(state: MatchState,
                                max_goals: int = 6) -> Dict[str, object]:
    """实时半全场 (HT/FT) 预测, 依据当前分钟与比分动态计算。

    两种情形:
      1) 仍在上半场 (minute < 45 且半场比分未定):
         半场比分 = 当前比分 + 上半场剩余时间的新增进球;
         全场比分 = 半场比分 + 整个下半场的新增进球。
      2) 已进入下半场 / 中场 (半场比分已定 ht_score_*):
         半场结果已确定 → 只有该半场符号对应的那一行组合可能发生,
         其余 6 个组合为「不可能」(概率 0, 并在 impossible 里标记);
         全场比分 = 当前比分 + 下半场剩余时间的新增进球。

    返回:
      {
        "home/home": p, ... (9 项组合概率, 已归一到可能组合上),
        "ht_home"/"ht_draw"/"ht_away": 半场胜平负边际概率,
        "ht_decided": bool,               # 半场结果是否已确定
        "ht_actual": "home"/"draw"/"away"/None,  # 已确定时的半场符号
        "impossible": ["home/away", ...], # 因赛程进程已不可能出现的组合
      }
    """
    lam_h_90, lam_a_90 = adjusted_lambdas_90(state)
    f1 = FIRST_HALF_GOAL_FRACTION
    f2 = 1.0 - f1
    signs = ("home", "draw", "away")
    combo: Dict[str, float] = {f"{ht}/{ft}": 0.0 for ht in signs for ft in signs}
    ht_marg: Dict[str, float] = {s: 0.0 for s in signs}

    ht_decided = state.ht_score_h >= 0 and state.ht_score_a >= 0
    ht_h = ht_a = 0
    # 保险: 分钟已过半场但数据源没给半场比分时, 用「当前比分」兜底当作半场比分
    if not ht_decided and state.minute >= 45:
        ht_h, ht_a = state.score_h, state.score_a
        ht_decided = True
    elif ht_decided:
        ht_h, ht_a = state.ht_score_h, state.ht_score_a

    if not ht_decided:
        # —— 情形 1: 上半场进行中 ——
        rem1_frac = max(0.0, min(1.0, (45 - state.minute) / 45.0))
        # 上半场剩余新增进球分布
        d_rem1 = _poisson_score_dist(lam_h_90 * f1 * rem1_frac,
                                     lam_a_90 * f1 * rem1_frac, max_goals)
        # 整个下半场新增进球分布
        d_2nd = _poisson_score_dist(lam_h_90 * f2, lam_a_90 * f2, max_goals)
        for (rh, ra), p1 in d_rem1.items():
            ht_h = state.score_h + rh
            ht_a = state.score_a + ra
            ht = _sign(ht_h, ht_a)
            ht_marg[ht] += p1
            for (sh, sa), p2 in d_2nd.items():
                ft = _sign(ht_h + sh, ht_a + sa)
                combo[f"{ht}/{ft}"] += p1 * p2
        impossible: list = []
        ht_actual = None
    else:
        # —— 情形 2: 半场已定, 只算下半场剩余 ——
        ht_actual = _sign(ht_h, ht_a)
        ht_marg[ht_actual] = 1.0
        rem2_frac = max(0.0, min(1.0, (90 - state.minute) / 45.0))
        d_rem2 = _poisson_score_dist(lam_h_90 * f2 * rem2_frac,
                                     lam_a_90 * f2 * rem2_frac, max_goals)
        for (sh, sa), p in d_rem2.items():
            ft = _sign(state.score_h + sh, state.score_a + sa)
            combo[f"{ht_actual}/{ft}"] += p
        # 半场符号已确定, 其它两行的组合都不可能
        impossible = [f"{ht}/{ft}" for ht in signs if ht != ht_actual
                      for ft in signs]

    result: Dict[str, object] = dict(combo)
    result["ht_home"] = ht_marg["home"]
    result["ht_draw"] = ht_marg["draw"]
    result["ht_away"] = ht_marg["away"]
    result["ht_decided"] = ht_decided
    result["ht_actual"] = ht_actual
    result["impossible"] = impossible
    return result
