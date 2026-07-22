"""中超赛前预测 Web 后端（Flask）。

前后端分离架构：  Vue 前端  ->  本后端 (REST API)  ->  预测模型

接口：
    GET  /api/health
        健康检查。

    GET  /api/matches?limit=10
        返回接下来 N 场未开赛中超，每场附带赛前预测概率（不含赔率建议）。
        这满足「不输入赔率则仅展示预测概率」的需求。

    GET  /api/live
        当前进行中的中超比赛：分钟、比分、场面统计 + 实时更新的预测概率。
        实时数据来自 API-Football，仅当环境变量 API_FOOTBALL_KEY 已设置时启用；
        未设置时返回 {"live_enabled": false}，前端提示「未启用实时更新」。
        （如需用模拟数据演示，可设 LIVE_SOURCE=sim。）

    POST /api/predict
        body: {
          "home_en": "SHANGHAI SIPG",   // 也可传 home_zh
          "away_en": "Shanghai Shenhua",
          "odds": { "home":1.8, "draw":3.5, "away":4.2,
                    "over":{"2.5":2.0}, "under":{"2.5":1.8},
                    "exact":{"1-0":6.5} }
        }
        返回该场预测概率 + 基于赔率的正 EV 投注建议。

运行：
    python3 -m webapp.app                       # 默认 0.0.0.0:5001（无实时）
    API_FOOTBALL_KEY=xxx python3 -m webapp.app   # 启用真实实时数据
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# 确保能 import 到项目根的 core/models/strategy/data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, jsonify, request
from flask_cors import CORS

from data.upcoming import upcoming_matches
from data.team_names import zh_to_en, en_to_zh
from webapp.prediction_service import (
    prematch_probabilities, evaluate_bets, live_probabilities,
)

# 实时数据源选择：
#   默认使用 API-Football 真实源（feeds.live_apifootball）；
#   设 LIVE_SOURCE=sim 时改用模拟数据源（feeds.live_sim_manager），用于本地演示。
if os.environ.get("LIVE_SOURCE", "").lower() == "sim":
    from feeds.live_sim_manager import live_states as _live_states

    def _live_enabled() -> bool:
        return True

    _LIVE_DEMO = True
else:
    from feeds.live_apifootball import live_states as _live_states, is_enabled as _live_enabled

    _LIVE_DEMO = False

app = Flask(__name__)
CORS(app)  # 允许 Vue 开发服务器跨域访问


# 简单的赛程缓存（避免频繁打 CFA API），TTL 10 分钟
_MATCH_CACHE: dict = {"ts": 0.0, "limit": 0, "data": None}
_CACHE_TTL = 600

# 实时接口缓存，TTL 30 秒（与前端轮询节奏一致，避免重复计算）
_LIVE_CACHE: dict = {"ts": 0.0, "data": None}
_LIVE_TTL = 30


def _resolve_teams(home_en, away_en, home_zh, away_zh):
    """把中文/英文队名统一解析为模型使用的英文名。"""
    h = home_en or (zh_to_en(home_zh) if home_zh else None) or home_zh
    a = away_en or (zh_to_en(away_zh) if away_zh else None) or away_zh
    return h, a


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/matches")
def matches():
    """接下来 N 场未赛中超 + 各自赛前预测概率。"""
    import time
    try:
        limit = int(request.args.get("limit", 10))
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 30))

    now = time.time()
    if (_MATCH_CACHE["data"] is not None
            and _MATCH_CACHE["limit"] >= limit
            and now - _MATCH_CACHE["ts"] < _CACHE_TTL):
        fixtures = _MATCH_CACHE["data"][:limit]
    else:
        try:
            fixtures = upcoming_matches(max(limit, 10))
        except Exception as e:
            return jsonify({"error": f"获取赛程失败: {e}"}), 502
        _MATCH_CACHE.update(ts=now, limit=max(limit, 10), data=fixtures)
        fixtures = fixtures[:limit]

    out = []
    for m in fixtures:
        item = dict(m)
        try:
            item["prediction"] = prematch_probabilities(m["home_en"], m["away_en"])
        except Exception as e:
            item["prediction"] = None
            item["prediction_error"] = str(e)
        out.append(item)
    return jsonify({"count": len(out), "matches": out})


@app.get("/api/live")
def live():
    """当前「进行中」比赛的实时状态 + 实时预测。

    - 未配置 API_FOOTBALL_KEY（且非模拟模式）时，返回 live_enabled=false，
      前端据此提示「未启用实时更新」。
    - 否则返回每场：比赛分钟、实时比分、射门/射正/角球/红牌等场面统计，
      以及基于当前状态动态更新的胜平负/大小球/比分概率。
    前端每 30 秒轮询一次即可看到分钟、比分与预测同步推进。
    """
    import time
    now = time.time()

    # 实时功能开关：无 key 时明确告知前端未启用
    if not _live_enabled():
        return jsonify({
            "live_enabled": False,
            "count": 0,
            "matches": [],
            "note": "未启用实时更新：服务器未配置 API_FOOTBALL_KEY 环境变量。",
        })

    if (_LIVE_CACHE["data"] is not None
            and now - _LIVE_CACHE["ts"] < _LIVE_TTL):
        return jsonify(_LIVE_CACHE["data"])

    try:
        pairs = _live_states()
    except Exception as e:
        return jsonify({"error": f"获取实时比赛失败: {e}"}), 502

    out = []
    for fixture, state in pairs:
        home_en = fixture.get("home_en")
        away_en = fixture.get("away_en")
        item = {
            "match_id": fixture.get("match_id"),
            "home_zh": fixture.get("home_zh") or (en_to_zh(home_en) or home_en),
            "away_zh": fixture.get("away_zh") or (en_to_zh(away_en) or away_en),
            "home_en": home_en,
            "away_en": away_en,
            "minute": state.minute,
            "status": fixture.get("status_long"),
            "finished": (fixture.get("status_short") == "FT") or state.minute >= 90,
            "score": {"home": state.score_h, "away": state.score_a},
            "stats": {
                "shots": {"home": state.shots_h, "away": state.shots_a},
                "sot": {"home": state.sot_h, "away": state.sot_a},
                "corners": {"home": state.corners_h, "away": state.corners_a},
                "red": {"home": state.red_h, "away": state.red_a},
                "possession_home": round(state.possession_h, 1),
            },
        }
        try:
            item["prediction"] = live_probabilities(state)
        except Exception as e:
            item["prediction"] = None
            item["prediction_error"] = str(e)
        out.append(item)

    payload = {
        "live_enabled": True,
        "count": len(out),
        "matches": out,
        "server_time": now,
        "source": "simulated" if _LIVE_DEMO else "api-football",
    }
    if _LIVE_DEMO:
        payload["note"] = "演示模式：实时数据由模拟数据源生成，非真实比赛。"
    _LIVE_CACHE.update(ts=now, data=payload)
    return jsonify(payload)


@app.post("/api/predict")
def predict():
    """给定一场比赛 + 赔率，返回预测概率与投注建议。"""
    data = request.get_json(silent=True) or {}
    home, away = _resolve_teams(
        data.get("home_en"), data.get("away_en"),
        data.get("home_zh"), data.get("away_zh"),
    )
    if not home or not away:
        return jsonify({"error": "缺少主/客队参数 (home_en 或 home_zh)"}), 400

    try:
        prediction = prematch_probabilities(home, away)
    except KeyError as e:
        return jsonify({"error": f"球队不在模型中: {e}"}), 404
    except Exception as e:
        return jsonify({"error": f"预测失败: {e}"}), 500

    odds = data.get("odds") or {}
    recommendations = []
    if odds:
        try:
            recommendations = evaluate_bets(home, away, odds)
        except Exception as e:
            return jsonify({"error": f"投注评估失败: {e}"}), 500

    return jsonify({
        "home_en": home, "away_en": away,
        "home_zh": en_to_zh(home) or home,
        "away_zh": en_to_zh(away) or away,
        "prediction": prediction,
        "has_odds": bool(odds),
        "recommendations": recommendations,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    # threaded=True 避免单线程被一个慢请求阻塞
    app.run(host="0.0.0.0", port=port, debug=debug, threaded=True)
