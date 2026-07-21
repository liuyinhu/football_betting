"""投注决策引擎：EV 过滤 + 分数凯利仓位 + 风险上限。"""
from __future__ import annotations
from typing import Dict, List, Tuple

from ..core.state import MatchState, OddsSnapshot, BetRecommendation
from ..models.poisson_live import outcome_probabilities, final_score_distribution


# ---------- 配置 ----------
MIN_EDGE = 0.03          # EV 需 ≥ 3% 才下注
KELLY_FRACTION = 0.25    # 1/4 凯利
MAX_STAKE_PER_BET = 0.02 # 单注上限: 总资金的 2%
MIN_ODDS = 1.20          # 避开赔率过低的超级热门
MAX_ODDS = 15.0          # 避开赔率过高的冷门(方差大)


def _kelly(p: float, odds: float) -> float:
    b = odds - 1.0
    if b <= 0:
        return 0.0
    f = (b * p - (1 - p)) / b
    return max(0.0, f)


def _ev(p: float, odds: float) -> float:
    """每 1 单位投注的期望利润。"""
    return p * (odds - 1.0) - (1 - p)


def evaluate(state: MatchState, odds: OddsSnapshot) -> List[BetRecommendation]:
    """评估所有支持的市场, 返回正期望值(EV)的投注列表。"""
    recs: List[BetRecommendation] = []

    probs = outcome_probabilities(state)

    # ---- 胜平负 1X2 ----
    market_map: List[Tuple[str, str, float | None]] = [
        ("1X2:home", "home", odds.home),
        ("1X2:draw", "draw", odds.draw),
        ("1X2:away", "away", odds.away),
    ]
    for name, key, o in market_map:
        rec = _make_rec(name, probs[key], o)
        if rec: recs.append(rec)

    # ---- 大小球 ----
    for line, o in odds.over.items():
        key = f"over_{line}"
        if key in probs:
            rec = _make_rec(f"OU:over{line}", probs[key], o)
            if rec: recs.append(rec)
    for line, o in odds.under.items():
        key = f"under_{line}"
        if key in probs:
            rec = _make_rec(f"OU:under{line}", probs[key], o)
            if rec: recs.append(rec)

    # ---- 精确比分 ----
    if odds.exact:
        dist = final_score_distribution(state)
        for score, o in odds.exact.items():
            p = dist.get(score, 0.0)
            rec = _make_rec(f"CS:{score[0]}-{score[1]}", p, o)
            if rec: recs.append(rec)

    # 按 EV 降序排列
    recs.sort(key=lambda r: r.edge, reverse=True)
    return recs


def _make_rec(name: str, p: float, o: float | None) -> BetRecommendation | None:
    if o is None or o < MIN_ODDS or o > MAX_ODDS:
        return None
    edge = _ev(p, o)
    if edge < MIN_EDGE:
        return None
    kelly = _kelly(p, o)
    stake = min(kelly * KELLY_FRACTION, MAX_STAKE_PER_BET)
    if stake <= 0:
        return None
    reason = f"模型概率={p:.3f} vs 赔率隐含概率={1/o:.3f}"
    return BetRecommendation(name, o, p, edge, stake, reason)
