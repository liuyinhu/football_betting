"""预测服务层：把训练好的强度模型 + 泊松/DC 分布 + 投注决策
封装成简单的函数，供 Web 后端（server/app.py）调用。

可切换的预测引擎（engine）：
    "dc" —— Dixon-Coles 解析式泊松（默认）。由攻防强度直接解析出赛前 λ。
    "nn" —— 神经网络（纯 NumPy MLP 泊松回归，models/nn_predictor.py）。
            用与 DC 相同的特征拟合出赛前 λ；下游概率/大小球/比分/半全场
            以及实时场面修正全部复用同一套泊松逻辑，只是 λ 的来源不同。

    两个引擎产出的都是「赛前 λ_home, λ_away」，因此可以无缝互换，
    保证对比公平——差异只在「泊松解析式」vs「神经网络拟合」。

对外主要函数（均可传 engine="dc"|"nn"）：
    available_engines() -> list
        返回当前可用引擎列表（nn 未训练时会标记 available=False）。
    prematch_probabilities(home_en, away_en, engine) -> dict
        赛前胜平负 / 大小球 / 双方进球 / 比分 TOP 概率。
    evaluate_bets(home_en, away_en, odds_dict, engine) -> list
        给定赔率，返回正 EV 的投注建议。
"""
from __future__ import annotations
from dataclasses import replace
from typing import Dict, List, Optional

import numpy as np

from core.state import MatchState, OddsSnapshot
from models.poisson_live import (
    outcome_probabilities, final_score_distribution, half_full_distribution,
    live_half_full_distribution,
)
from strategy.decision import (
    evaluate, _ev, _kelly,
    MIN_EDGE, KELLY_FRACTION, MAX_STAKE_PER_BET, MIN_ODDS, MAX_ODDS,
)
from data.train_strength import load as load_strength, expected_lambdas, MODEL_PATH

# 默认引擎；请求未显式指定 engine 时使用。
# 设为 "nn"（神经网络泊松回归）——在 goals 验证中 MAE/大小球/胜平负均优于 DC；
# 若 nn 模型尚未训练，运行时会自动回退到 "dc"（见 _effective_default）。
DEFAULT_ENGINE = "nn"

# 引擎元信息（供前端展示 / 校验）；顺序即前端按钮从左到右的展示顺序
_ENGINE_META = {
    "nn": {"id": "nn", "name": "神经网络 (MLP 泊松回归)", "kind": "神经网络"},
    "dc": {"id": "dc", "name": "Dixon-Coles 泊松", "kind": "解析式"},
}

# 全局缓存强度模型，避免每次请求都读磁盘
_MODEL: Optional[Dict] = None
# 缓存已加载的神经网络泊松回归器
_NN_REG = None


def _model() -> Dict:
    global _MODEL
    if _MODEL is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                "强度模型不存在，请先运行: python3 -m data.train_strength")
        _MODEL = load_strength()
    return _MODEL


def _nn_available() -> bool:
    """神经网络模型（进球泊松回归）是否已训练并存在。"""
    from models.nn_predictor import POISSON_MODEL_PATH
    return POISSON_MODEL_PATH.exists() and MODEL_PATH.exists()


def _nn_reg():
    """惰性加载并缓存神经网络泊松回归器。"""
    global _NN_REG
    if _NN_REG is None:
        from models.nn_predictor import MLPPoissonRegressor, POISSON_MODEL_PATH
        if not POISSON_MODEL_PATH.exists():
            raise FileNotFoundError(
                "神经网络模型不存在，请先运行: "
                "python3 -m data.train_nn --goals --save")
        _NN_REG = MLPPoissonRegressor.load()
    return _NN_REG


def _effective_default() -> str:
    """实际生效的默认引擎：DEFAULT_ENGINE 为 nn 但模型未训练时回退到 dc。"""
    if DEFAULT_ENGINE == "nn" and not _nn_available():
        return "dc"
    return DEFAULT_ENGINE


def _resolve_engine(engine: Optional[str]) -> str:
    """规范化引擎名；未知或未提供时回退到（实际生效的）默认引擎。

    此外，若请求了 nn 但模型未训练，也会回退到 dc，避免默认引擎失效。
    """
    e = (engine or "").lower()
    if e not in _ENGINE_META:
        return _effective_default()
    if e == "nn" and not _nn_available():
        return "dc"
    return e


def available_engines() -> List[Dict]:
    """返回引擎列表及可用状态（nn 未训练时 available=False）。

    default 标记的是「实际生效的默认引擎」：若配置默认为 nn 但未训练，
    则把 dc 标为默认，保证前端选中的默认引擎一定可用。
    """
    eff_default = _effective_default()
    out: List[Dict] = []
    for meta in _ENGINE_META.values():
        item = dict(meta)
        item["available"] = True if meta["id"] == "dc" else _nn_available()
        item["default"] = (meta["id"] == eff_default)
        out.append(item)
    return out


def _prematch_lambdas(home_en: str, away_en: str, engine: str) -> tuple:
    """按所选引擎给出赛前 (λ_home, λ_away)。"""
    model = _model()
    if engine == "nn":
        # 神经网络回归：用与 DC 相同的特征拟合出整场 λ
        from data.train_nn import _features_for
        feats = _features_for(model, home_en, away_en)
        if feats is None:
            raise KeyError(f"{home_en} 或 {away_en}")
        lam = _nn_reg().predict_lambda(np.array([feats], dtype=float))[0]
        lam_h, lam_a = float(lam[0]), float(lam[1])
        # 与 DC 一致地做区间保护，避免极端值
        lam_h = min(max(lam_h, 0.2), 3.0)
        lam_a = min(max(lam_a, 0.2), 3.0)
        return lam_h, lam_a
    # 默认 Dixon-Coles 解析式
    return expected_lambdas(model, home_en, away_en)


def _build_state(home_en: str, away_en: str,
                 engine: str = DEFAULT_ENGINE) -> MatchState:
    """构建赛前 minute=0、比分 0-0 的比赛状态，λ 来自所选引擎。"""
    lam_h, lam_a = _prematch_lambdas(home_en, away_en, engine)
    return MatchState(
        match_id="PREMATCH", minute=0, score_h=0, score_a=0,
        prior_lambda_h=lam_h, prior_lambda_a=lam_a,
    )


def prematch_probabilities(home_en: str, away_en: str,
                           engine: str = DEFAULT_ENGINE) -> Dict:
    """返回赛前各市场概率与 λ、比分 TOP 分布。

    engine: "dc"(Dixon-Coles 解析式) | "nn"(神经网络泊松回归)。
    """
    engine = _resolve_engine(engine)
    state = _build_state(home_en, away_en, engine)
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
        "engine": engine,
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


def live_probabilities(state: MatchState, engine: str = DEFAULT_ENGINE,
                       home_en: Optional[str] = None,
                       away_en: Optional[str] = None) -> Dict:
    """给定一个「进行中」的实时状态，返回当前各市场概率与比分 TOP 分布。

    与 prematch_probabilities 的区别：这里直接接收带 minute/score/射门 的
    MatchState，模型按剩余时间 + 场面特征动态修正 λ。

    只要提供了 home_en/away_en，就按所选引擎（dc/nn）重新计算赛前先验 λ，
    覆盖传入 state 里的先验后再进入同一套实时修正逻辑，保证切换引擎时结果会变。
    注意：传入的 state 往往是被数据源缓存/复用的共享对象，这里必须在**副本**
    上修改先验，否则一次 nn 请求会污染该 state，导致之后的 dc 请求仍用 nn 的 λ。
    """
    engine = _resolve_engine(engine)
    if home_en and away_en:
        try:
            lam_h, lam_a = _prematch_lambdas(home_en, away_en, engine)
            # 在副本上改写先验，避免污染被数据源复用的共享 state
            state = replace(state, prior_lambda_h=lam_h, prior_lambda_a=lam_a)
        except Exception:
            # 模型不可用/球队缺失时静默沿用 state 已有的先验
            pass
    probs = outcome_probabilities(state)
    dist = final_score_distribution(state)
    top = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:6]

    # 实时半全场：按当前分钟/比分动态计算，下半场时部分组合已不可能
    hf = live_half_full_distribution(state)
    signs = ("home", "draw", "away")
    half_full = [
        {"ht": ht, "ft": ft, "prob": hf[f"{ht}/{ft}"]}
        for ht in signs for ft in signs
    ]

    return {
        "engine": engine,
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
        "ht_decided": hf["ht_decided"],
        "ht_actual": hf["ht_actual"],
        "hf_impossible": hf["impossible"],
    }


def _build_odds(odds_in: Dict) -> OddsSnapshot:
    """把前端传来的赔率字典转成 OddsSnapshot。

    期望结构（字段均可选，缺失/0 表示不下该市场）：
        {
          "home": 1.8, "draw": 3.5, "away": 4.2,
          "over":  {"2.5": 2.0, "1.5": 1.3},
          "under": {"2.5": 1.8},
          "exact": {"1-0": 6.5, "2-1": 8.0},
          "htft":  {"home/home": 2.5, "draw/away": 15.0}
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


_SIGN_ZH = {"home": "主", "draw": "平", "away": "客"}


def _market_label(market: str) -> str:
    if market in _MARKET_ZH:
        return _MARKET_ZH[market]
    if market.startswith("OU:over"):
        return f"大 {market[len('OU:over'):]} 球"
    if market.startswith("OU:under"):
        return f"小 {market[len('OU:under'):]} 球"
    if market.startswith("CS:"):
        return f"精确比分 {market[3:]}"
    if market.startswith("HTFT:"):
        ht, ft = market[len("HTFT:"):].split("/")
        return f"半全场 {_SIGN_ZH.get(ht, ht)}/{_SIGN_ZH.get(ft, ft)}"
    return market


def _evaluate_half_full(state: MatchState, htft_in: Dict,
                        hf: Optional[Dict] = None) -> List[Dict]:
    """评估半全场 (HT/FT) 赔率, 返回正 EV 建议。

    htft_in 形如 {"home/home": 2.5, "draw/away": 15.0, ...}
    key = "半场/全场"，取值 home/draw/away。
    hf: 可传入已算好的半全场分布(赛前用 half_full_distribution，
        实时用 live_half_full_distribution)；缺省则按赛前分布计算。
    """
    if not htft_in:
        return []
    if hf is None:
        hf = half_full_distribution(state)
    recs: List[Dict] = []
    for combo, v in htft_in.items():
        try:
            o = float(v)
        except (TypeError, ValueError):
            continue
        if o <= 1.0 or o < MIN_ODDS or o > MAX_ODDS:
            continue
        p = hf.get(combo, 0.0)
        # 分布里非数值(如 ht_actual)或已不可能的组合跳过
        if not isinstance(p, (int, float)) or p <= 0:
            continue
        edge = _ev(p, o)
        if edge < MIN_EDGE:
            continue
        stake = min(_kelly(p, o) * KELLY_FRACTION, MAX_STAKE_PER_BET)
        if stake <= 0:
            continue
        market = f"HTFT:{combo}"
        recs.append({
            "market": market,
            "market_zh": _market_label(market),
            "odds": o,
            "model_prob": p,
            "edge": edge,
            "stake_fraction": stake,
            "reason": f"模型概率={p:.3f} vs 赔率隐含概率={1/o:.3f}",
        })
    return recs


def evaluate_bets(home_en: str, away_en: str, odds_in: Dict,
                  engine: str = DEFAULT_ENGINE) -> List[Dict]:
    """给定赔率，返回正 EV 投注建议列表（已按 EV 降序）。

    engine 决定赛前 λ 的来源（dc / nn），下游 EV/凯利决策逻辑一致。
    """
    engine = _resolve_engine(engine)
    state = _build_state(home_en, away_en, engine)
    odds = _build_odds(odds_in)
    recs = evaluate(state, odds)
    out = [
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
    # 半全场市场（core 的 OddsSnapshot 不含该市场，单独处理）
    out.extend(_evaluate_half_full(state, odds_in.get("htft") or {}))
    # 合并后按 EV 降序
    out.sort(key=lambda d: d["edge"], reverse=True)
    return out


def live_evaluate_bets(state: MatchState, odds_in: Dict,
                       engine: str = DEFAULT_ENGINE,
                       home_en: Optional[str] = None,
                       away_en: Optional[str] = None) -> List[Dict]:
    """实时投注建议：给定「进行中」的 state 与当前赔率，返回正 EV 建议列表。

    与 evaluate_bets 的区别：
      1. 直接使用带 minute/score/场面统计的实时 state（λ 会按剩余时间动态修正）；
      2. 半全场用 live_half_full_distribution（下半场已定的组合会被自动排除）；
      3. 若提供 home_en/away_en，则按所选引擎在**副本**上重算赛前先验 λ，
         保证切换引擎结果会变，且不污染被数据源复用的共享 state。
    """
    engine = _resolve_engine(engine)
    if home_en and away_en:
        try:
            lam_h, lam_a = _prematch_lambdas(home_en, away_en, engine)
            state = replace(state, prior_lambda_h=lam_h, prior_lambda_a=lam_a)
        except Exception:
            pass

    odds = _build_odds(odds_in)
    # 让赔率快照与实时 state 对齐（分钟数），语义更清晰
    odds.match_id = state.match_id
    odds.minute = state.minute

    recs = evaluate(state, odds)
    out = [
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
    # 半全场：用实时分布（下半场已定组合概率为 0，会被自动跳过）
    hf = live_half_full_distribution(state)
    out.extend(_evaluate_half_full(state, odds_in.get("htft") or {}, hf=hf))
    out.sort(key=lambda d: d["edge"], reverse=True)
    return out
