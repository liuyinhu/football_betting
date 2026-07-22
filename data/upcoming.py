"""从中国足协官方 API 拉取「未开赛」的中超赛程（用于赛前预测）。

与 cfa_loader.py 互补：
    - cfa_loader 只取 **已完赛**（Played）场次，用于训练强度模型；
    - 本模块只取 **未开赛**（Fixture）场次，用于前端展示「接下来 N 场」的赛前预测。

对外主函数：
    upcoming_matches(limit=10, competition="CSL") -> List[dict]
        返回按开赛时间升序排列的未来赛程，每项含：
        {
          "match_id": 稳定整数 id,
          "date": "2026-07-25", "time": "19:35:00",
          "datetime": "2026-07-25 19:35:00",
          "week": 20,
          "home_zh": 中文主队, "away_zh": 中文客队,
          "home_en": 标准英文主队, "away_en": 标准英文客队,
        }
"""
from __future__ import annotations
import datetime as _dt
import json
import ssl
import urllib.request
from typing import Dict, List

from .cfa_loader import BASE, DEFAULT_COMPETITION, _std_team_name, _stable_fixture_id, _ctx


def _fetch_week(week: int, competition: str) -> dict:
    url = f"{BASE}?week={week}&competition_code={competition}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") != 200:
        raise RuntimeError(f"CFA API 返回异常: {payload.get('status')} {payload.get('msg')}")
    return payload["data"]


def _to_dict(m: dict) -> dict:
    home_zh = (m.get("home_contestant_name") or "").strip()
    away_zh = (m.get("away_contestant_name") or "").strip()
    return {
        "match_id": _stable_fixture_id(m["id"]),
        "date": m.get("local_date") or "",
        "time": (m.get("local_time") or "")[:8],
        "datetime": (m.get("local_date_timeStr") or "").strip(),
        "week": int(m.get("week") or 0),
        "status": m.get("match_status") or "",
        "home_zh": home_zh,
        "away_zh": away_zh,
        "home_en": _std_team_name(home_zh),
        "away_en": _std_team_name(away_zh),
    }


def upcoming_matches(limit: int = 10,
                     competition: str = DEFAULT_COMPETITION,
                     include_postponed: bool = False) -> List[dict]:
    """返回按开赛时间升序的未来 N 场赛程（默认只含状态为 Fixture 的未赛场）。

    参数：
        limit             需要返回的场次数量
        competition       CSL(中超) / CFL1(中甲) / CFL2(中乙)
        include_postponed 是否把 Postponed(延期) 场次也算进来
    """
    first = _fetch_week(1, competition)
    max_week = int(first.get("max_week") or 30)

    wanted = {"Fixture"} | ({"Postponed"} if include_postponed else set())
    today = _dt.date.today().isoformat()

    rows: List[dict] = []
    cache: Dict[int, dict] = {1: first}
    for wk in range(1, max_week + 1):
        data = cache.get(wk) or _fetch_week(wk, competition)
        for m in data.get("list", []):
            if m.get("match_status") in wanted:
                d = _to_dict(m)
                # 只保留今天及以后的比赛，过滤掉历史里残留的延期未补赛
                if d["date"] and d["date"] >= today:
                    rows.append(d)

    rows.sort(key=lambda r: (r["date"], r["time"]))
    return rows[:limit]


if __name__ == "__main__":
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    for i, r in enumerate(upcoming_matches(n), 1):
        print(f"{i:2d}. {r['datetime']}  第{r['week']}轮  "
              f"{r['home_zh']} vs {r['away_zh']}  "
              f"[{r['home_en']} / {r['away_en']}]")
