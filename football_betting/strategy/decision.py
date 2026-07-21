"""Betting decision engine: EV filter + fractional Kelly staking + risk caps."""
from __future__ import annotations
from typing import Dict, List, Tuple

from ..core.state import MatchState, OddsSnapshot, BetRecommendation
from ..models.poisson_live import outcome_probabilities, final_score_distribution


# ---------- config ----------
MIN_EDGE = 0.03          # need ≥ 3% EV to place a bet
KELLY_FRACTION = 0.25    # 1/4 Kelly
MAX_STAKE_PER_BET = 0.02 # cap: 2% of bankroll per bet
MIN_ODDS = 1.20          # avoid low-liquidity extreme favorites
MAX_ODDS = 15.0          # avoid long-shot variance


def _kelly(p: float, odds: float) -> float:
    b = odds - 1.0
    if b <= 0:
        return 0.0
    f = (b * p - (1 - p)) / b
    return max(0.0, f)


def _ev(p: float, odds: float) -> float:
    """Expected profit per 1 unit stake."""
    return p * (odds - 1.0) - (1 - p)


def evaluate(state: MatchState, odds: OddsSnapshot) -> List[BetRecommendation]:
    """Evaluate all supported markets, return list of positive-EV bets."""
    recs: List[BetRecommendation] = []

    probs = outcome_probabilities(state)

    # ---- 1X2 ----
    market_map: List[Tuple[str, str, float | None]] = [
        ("1X2:home", "home", odds.home),
        ("1X2:draw", "draw", odds.draw),
        ("1X2:away", "away", odds.away),
    ]
    for name, key, o in market_map:
        rec = _make_rec(name, probs[key], o)
        if rec: recs.append(rec)

    # ---- Over/Under ----
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

    # ---- Correct score ----
    if odds.exact:
        dist = final_score_distribution(state)
        for score, o in odds.exact.items():
            p = dist.get(score, 0.0)
            rec = _make_rec(f"CS:{score[0]}-{score[1]}", p, o)
            if rec: recs.append(rec)

    # sort by edge desc
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
    reason = f"model_p={p:.3f} vs implied={1/o:.3f}"
    return BetRecommendation(name, o, p, edge, stake, reason)
