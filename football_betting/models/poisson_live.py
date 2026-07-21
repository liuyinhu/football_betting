"""Live in-play score probability predictor based on time-varying Poisson model.

Idea:
1. Each team has a *residual* goal rate lambda for the remaining minutes.
2. lambda is derived from pre-match prior + in-play adjustments driven by
   shots on target, corners, dangerous attacks, xG, red-card difference, etc.
3. Residual goals ~ Poisson(lambda_remaining). Final score distribution =
   current score + independent Poisson draws for both teams.
4. Small correction for low-score correlation (Dixon-Coles rho).
"""
from __future__ import annotations
import math
from typing import Dict, Tuple

from scipy.stats import poisson

from ..core.state import MatchState


# ---- weights of in-play features on residual lambda (tunable / learnable) ----
FEATURE_WEIGHTS = {
    "sot":       0.045,   # each extra shot-on-target above opponent adds
    "corner":    0.012,
    "danger":    0.004,
    "xg":        0.30,    # xG diff is very informative
    "possession":0.004,   # per % above 50
}

# red card penalty (multiplicative on lambda of the reduced side)
RED_CARD_PENALTY = 0.65


def _adjust_lambda(base_lambda: float,
                   own_feats: Dict[str, float],
                   opp_feats: Dict[str, float],
                   red_own: int,
                   red_opp: int) -> float:
    """Adjust a team's per-90 lambda based on live tempo & xG differences."""
    delta = 0.0
    for k, w in FEATURE_WEIGHTS.items():
        delta += w * (own_feats.get(k, 0.0) - opp_feats.get(k, 0.0))

    # exponential adjustment so lambda stays > 0
    lam = base_lambda * math.exp(delta)

    # red card penalties compound
    lam *= RED_CARD_PENALTY ** red_own
    lam /= RED_CARD_PENALTY ** red_opp   # opp weakened → we score more
    return max(lam, 0.01)


def compute_residual_lambdas(state: MatchState) -> Tuple[float, float]:
    """Compute expected residual goals for each side for the rest of the match."""
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
    """Dixon-Coles low-score correction."""
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
    """Return P(final_score = (H, A)) as a dict."""
    lam_h, lam_a = compute_residual_lambdas(state)

    dist: Dict[Tuple[int, int], float] = {}
    total = 0.0
    for i in range(max_extra_goals + 1):
        for j in range(max_extra_goals + 1):
            p = poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
            p *= _dc_tau(i, j, lam_h, lam_a)
            dist[(state.score_h + i, state.score_a + j)] = p
            total += p

    # normalize (tail truncation + DC correction can shift mass slightly)
    if total > 0:
        for k in dist:
            dist[k] /= total
    return dist


def outcome_probabilities(state: MatchState) -> Dict[str, float]:
    """Return P(home win), P(draw), P(away win) and useful market probs."""
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
