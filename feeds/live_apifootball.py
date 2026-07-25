"""真实实时数据源：API-Football (v3) 的进行中比赛。

启用条件：
    环境变量 API_FOOTBALL_KEY 已设置。未设置时 is_enabled() 返回 False，
    后端据此告知前端「未启用实时更新」。

数据来源：
    GET /fixtures?live=all&league=169   当前所有进行中的中超比赛（含分钟、比分、事件）
    GET /fixtures/statistics?fixture=ID 该场实时场面统计（射门/射正/角球/控球/红牌）

把上述实时数据映射为项目内部的 MatchState（分钟、比分、射门…），
再由预测服务用时变泊松模型算实时概率。接入本模块后，前后端其余代码不变。

对外主函数：
    is_enabled() -> bool
        是否配置了 API key（决定实时功能是否可用）。
    live_states() -> List[Tuple[dict, MatchState]]
        当前所有进行中的中超比赛 (赛程信息, 实时状态)。
"""
from __future__ import annotations
import os
import time
from typing import Dict, List, Optional, Tuple

from core.state import MatchState
from data.team_names import zh_to_en

# 默认拉取中超（CSL）；可用环境变量覆盖，便于测试其他联赛。
LEAGUE_ID = int(os.environ.get("LIVE_LEAGUE_ID", "169"))

# 视为「进行中」的 API-Football 状态码（1H/HT/2H/加时/点球/中断补时）
_LIVE_STATUS = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT", "SUSP"}

# 实时结果缓存 TTL（秒）。与前端 30s 轮询节奏一致，避免重复消耗 API 配额。
_CACHE_TTL = float(os.environ.get("LIVE_CACHE_TTL", "25"))
_CACHE: dict = {"ts": 0.0, "data": None}


def is_enabled() -> bool:
    """是否配置了 API-Football key（决定实时功能是否可用）。"""
    return bool(os.environ.get("API_FOOTBALL_KEY", "").strip())


def _model_team_name(af_name: str) -> str:
    """把 API-Football 英文队名映射到强度模型使用的英文名。

    绝大多数中超队名两边一致，直接返回；个别经中文别名兜底转换。
    """
    if not af_name:
        return af_name
    # 先尝试英文名直接命中模型（调用方会再校验）
    en = zh_to_en(af_name)  # zh_to_en 也能吃部分英文别名，命中则用标准名
    return en or af_name


def _stat_map(stats_entry: dict) -> Dict[str, object]:
    return {it.get("type"): it.get("value")
            for it in (stats_entry.get("statistics") or [])}


def _to_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _parse_possession(v) -> Optional[float]:
    if isinstance(v, str) and v.endswith("%"):
        try:
            return float(v.rstrip("%"))
        except ValueError:
            return None
    return None


def _build_state(fx: dict, stats_by_team: Dict[int, Dict[str, object]],
                 model: dict) -> Tuple[dict, MatchState]:
    """把一场 API-Football 实时 fixture 转成 (赛程信息, MatchState)。"""
    from data.train_strength import expected_lambdas

    status = fx["fixture"]["status"]
    minute = _to_int(status.get("elapsed"), 0)
    teams = fx["teams"]
    goals = fx["goals"]
    home_af = teams["home"]["name"]
    away_af = teams["away"]["name"]
    home_en = _model_team_name(home_af)
    away_en = _model_team_name(away_af)

    # 赛前 λ 先验：模型里有则用模型，否则退到默认值
    try:
        lam_h, lam_a = expected_lambdas(model, home_en, away_en)
    except Exception:
        lam_h, lam_a = 1.4, 1.1

    hs = stats_by_team.get(teams["home"]["id"], {})
    as_ = stats_by_team.get(teams["away"]["id"], {})
    poss_h = _parse_possession(hs.get("Ball Possession"))

    # 半场比分：仅当比赛已进入下半场/中场后 API 才提供 score.halftime；
    # 未定时用 -1 标记（仍在上半场），供实时半全场预测判断阶段。
    status_short = status.get("short")
    ht = (fx.get("score") or {}).get("halftime") or {}
    ht_h_raw, ht_a_raw = ht.get("home"), ht.get("away")
    if ht_h_raw is not None and ht_a_raw is not None and status_short != "1H":
        ht_score_h = _to_int(ht_h_raw)
        ht_score_a = _to_int(ht_a_raw)
    else:
        ht_score_h = ht_score_a = -1

    state = MatchState(
        match_id=str(fx["fixture"]["id"]),
        minute=min(minute, 90),
        score_h=_to_int(goals.get("home"), 0),
        score_a=_to_int(goals.get("away"), 0),
        shots_h=_to_int(hs.get("Total Shots")),
        shots_a=_to_int(as_.get("Total Shots")),
        sot_h=_to_int(hs.get("Shots on Goal")),
        sot_a=_to_int(as_.get("Shots on Goal")),
        corners_h=_to_int(hs.get("Corner Kicks")),
        corners_a=_to_int(as_.get("Corner Kicks")),
        yellow_h=_to_int(hs.get("Yellow Cards")),
        yellow_a=_to_int(as_.get("Yellow Cards")),
        red_h=_to_int(hs.get("Red Cards")),
        red_a=_to_int(as_.get("Red Cards")),
        possession_h=poss_h if poss_h is not None else 50.0,
        prior_lambda_h=lam_h,
        prior_lambda_a=lam_a,
        ht_score_h=ht_score_h,
        ht_score_a=ht_score_a,
    )

    fixture_info = {
        "match_id": fx["fixture"]["id"],
        "home_en": home_en,
        "away_en": away_en,
        # 中文名：模型英文名可反查；否则用 API-Football 原名
        "home_zh": _en_to_zh_safe(home_en) or home_af,
        "away_zh": _en_to_zh_safe(away_en) or away_af,
        "status_short": status.get("short"),
        "status_long": status.get("long"),
    }
    return fixture_info, state


def _en_to_zh_safe(en: str) -> Optional[str]:
    from data.team_names import en_to_zh
    try:
        return en_to_zh(en)
    except Exception:
        return None


def _fetch_live_raw() -> List[dict]:
    """拉取当前所有进行中的中超比赛（原始 fixture 列表）。"""
    from data.api_football_loader import _request
    data = _request("/fixtures", {"live": "all", "league": LEAGUE_ID})
    return data.get("response", []) or []


def _fetch_stats(fixture_id: int) -> Dict[int, Dict[str, object]]:
    """拉取某场实时统计，返回 {team_id: {统计名: 值}}；失败返回空。"""
    from data.api_football_loader import _request
    try:
        data = _request("/fixtures/statistics", {"fixture": fixture_id})
    except Exception:
        return {}
    out: Dict[int, Dict[str, object]] = {}
    for entry in data.get("response", []) or []:
        tid = (entry.get("team") or {}).get("id")
        if tid is not None:
            out[tid] = _stat_map(entry)
    return out


def live_states() -> List[Tuple[dict, MatchState]]:
    """返回当前所有进行中的中超比赛 (赛程信息, 实时状态)。

    带 25 秒缓存，避免前端 30s 轮询时重复打 API。
    """
    if not is_enabled():
        return []

    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["data"]

    from data.train_strength import load as load_strength
    try:
        model = load_strength()
    except Exception:
        model = {"teams": {}}

    fixtures = _fetch_live_raw()
    # 只保留确实处于进行中的场次
    fixtures = [f for f in fixtures
                if (f["fixture"]["status"].get("short") in _LIVE_STATUS)]

    out: List[Tuple[dict, MatchState]] = []
    for fx in fixtures:
        stats = _fetch_stats(fx["fixture"]["id"])
        out.append(_build_state(fx, stats, model))

    _CACHE.update(ts=now, data=out)
    return out
