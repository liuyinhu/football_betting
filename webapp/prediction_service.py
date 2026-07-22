"""预测服务层：把训练好的强度模型 + 泊松/DC 分布 + 投注决策
封装成简单的函数，供 Web 后端（server/app.py）调用。

对外主要函数：
    prematch_probabilities(home_en, away_en) -> dict
        赛前胜平负 / 大小球 / 双方进球 / 比分 TOP 概率。
    evaluate_bets(home_en, away_en, odds_dict) -> list
        给定赔率，返回正 EV 的投注建议。
"""
from __future__ import annotations
from typing import Dict, List, Optional

from core.state import MatchState, OddsSnapshot
from models.poisson_live import (
    outcome_probabilities, final_score_distribution, half_full_distribution,
)
from strategy.decision import evaluate
from data.train_strength import load as load_strength, expected_lambdas, MODEL_PATH

# 全局缓存强度模型，避免每次请求都读磁盘
_MODEL: Optional[Dict] = None


def _model() -> Dict:
    global _MODEL
    if _MODEL is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                "强度模型不存在，请先运行: python3 -m data.train_strength")
        _MODEL = load_strength()
    return _MODEL


def _build_state(home_en: str, away_en: str) -> MatchState:
    """构建赛前 minute=0、比分 0-0 的比赛状态，λ 来自训练模型。"""
    model = _model()
    lam_h, lam_a = expected_lambdas(model, home_en, away_en)
    return MatchState(
        match_id="PREMATCH", minute=0, score_h=0, score_a=0,
        prior_lambda_h=lam_h, prior_lambda_a=lam_a,
    )


def prematch_probabilities(home_en: str, away_en: str) -> Dict:
    """返回赛前各市场概率与 λ、比分 TOP 分布。"""
    state = _build_state(home_en, away_en)
    probs = outcome_probabilities(state)
    dist = final_score_distribution(state)
    top = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:6]
    hf = half_full_distribution(state)

    signs = ("home", "draw", "away")
    half_full = [
        {"ht": ht, "ft": ft, "prob": hf[f"{ht}/{ft}"]}
        for ht in signs for ft in signs
    ]

    return {
        "lambda_home": round(state.prior_lambda_h, 3),
        "lambda_away": round(state.prior_lambda_a, 3),
        "outcome": {
            "home": probs["home"],
            "draw": probs["draw"],
            "away": probs["away"],
        },
        "over_under": {
            "over_1.5": probs["over_1.5"], "under_1.5": probs["under_1.5"],
            "over_2.5": probs["over_2.5"], "under_2.5": probs["under_2.5"],
            "over_3.5": probs["over_3.5"], "under_3.5": probs["under_3.5"],
        },
        "btts": {"yes": probs["btts_yes"], "no": probs["btts_no"]},
        "top_scores": [
            {"score": f"{h}-{a}", "prob": p} for (h, a), p in top
        ],
        "half_full": half_full,
        "ht_outcome": {
            "home": hf["ht_home"], "draw": hf["ht_draw"], "away": hf["ht_away"],
        },
    }


def _build_odds(odds_in: Dict) -> OddsSnapshot:
    """把前端传来的赔率字典转成 OddsSnapshot。

    期望结构（字段均可选，缺失/0 表示不下该市场）：
        {
          "home": 1.8, "draw": 3.5, "away": 4.2,
          "over":  {"2.5": 2.0, "1.5": 1.3},
          "under": {"2.5": 1.8},
          "exact": {"1-0": 6.5, "2-1": 8.0}
        }
    """
    odds = OddsSnapshot(match_id="PREMATCH", minute=0)

    def _pos(v):
        try:
            v = float(v)
            return v if v > 1.0 else None
        except (TypeError, ValueError):
            return None

    odds.home = _pos(odds_in.get("home"))
    odds.draw = _pos(odds_in.get("draw"))
    odds.away = _pos(odds_in.get("away"))

    for line, v in (odds_in.get("over") or {}).items():
        o = _pos(v)
        if o:
            odds.over[float(line)] = o
    for line, v in (odds_in.get("under") or {}).items():
        o = _pos(v)
        if o:
            odds.under[float(line)] = o
    for score, v in (odds_in.get("exact") or {}).items():
        o = _pos(v)
        if o:
            try:
                h, a = map(int, str(score).split("-"))
                odds.exact[(h, a)] = o
            except ValueError:
                continue
    return odds


# 市场标识 -> 中文说明
_MARKET_ZH = {
    "1X2:home": "主胜", "1X2:draw": "平局", "1X2:away": "客胜",
}


def _market_label(market: str) -> str:
    if market in _MARKET_ZH:
        return _MARKET_ZH[market]
    if market.startswith("OU:over"):
        return f"大 {market[len('OU:over'):]} 球"
    if market.startswith("OU:under"):
        return f"小 {market[len('OU:under'):]} 球"
    if market.startswith("CS:"):
        return f"精确比分 {market[3:]}"
    return market


def evaluate_bets(home_en: str, away_en: str, odds_in: Dict) -> List[Dict]:
    """给定赔率，返回正 EV 投注建议列表（已按 EV 降序）。"""
    state = _build_state(home_en, away_en)
    odds = _build_odds(odds_in)
    recs = evaluate(state, odds)
    return [
        {
            "market": r.market,
            "market_zh": _market_label(r.market),
            "odds": r.odds,
            "model_prob": r.model_prob,
            "edge": r.edge,
            "stake_fraction": r.stake_fraction,
            "reason": r.reason,
        }
        for r in recs
    ]
