"""中超赛前预测 Web 后端（Flask）。

前后端分离架构：  Vue 前端  ->  本后端 (REST API)  ->  预测模型

接口：
    GET  /api/health
        健康检查。

    GET  /api/matches?limit=10
        返回接下来 N 场未开赛中超，每场附带赛前预测概率（不含赔率建议）。
        这满足「不输入赔率则仅展示预测概率」的需求。

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
    python3 -m webapp.app          # 默认 0.0.0.0:5001
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
from webapp.prediction_service import prematch_probabilities, evaluate_bets

app = Flask(__name__)
CORS(app)  # 允许 Vue 开发服务器跨域访问


# 简单的赛程缓存（避免频繁打 CFA API），TTL 10 分钟
_MATCH_CACHE: dict = {"ts": 0.0, "limit": 0, "data": None}
_CACHE_TTL = 600


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
