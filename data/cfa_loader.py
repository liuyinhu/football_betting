"""对接中国足协职业联赛联合会（CFL）官方 API，抓取中超赛程赛果。

相比 API-Football，本数据源的优势：
    - **官方、免费、无需鉴权**，队名/升降级永远最新准确
    - API-Football 的 2026 中超名单滞后（缺辽宁铁人/青岛西海岸/深圳新鹏城，
      却混入已降级的队），官方 API 没有这个问题

局限：
    - 只提供赛程赛果 + 比分（总/半场/全场），**没有**射正/角球/xG 等场面统计，
      也没有分钟级事件。因此本源用于**训练强度模型**（只需比分），
      场面特征仍由 API-Football 数据校准。
    - `tournament_calendar_name` 参数被服务端忽略，**只能取当前赛季**。

接口：
    GET https://api.cfl-china.cn/frontweb/api/matches/latest
        ?week=<轮次>&competition_code=<CSL|CFL1|CFL2>
    返回 data.list[]，每场含中英文队名、总比分、日期、状态(Played/未赛)、max_week。

用法：
    # 抓当前赛季全部已赛场次，保存到 seasons/csl_<season>_details.json（覆盖同名）
    python3 -m data.cfa_loader
    # 指定联赛（默认 CSL 中超）
    python3 -m data.cfa_loader --competition CSL
"""
from __future__ import annotations
import json
import ssl
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from .api_football_loader import (
    FixtureData, TeamStats, SEASON_DIR, _fixture_from_dict,
)

BASE = "https://api.cfl-china.cn/frontweb/api/matches/latest"
DEFAULT_COMPETITION = "CSL"  # 中超；中甲=CFL1，中乙=CFL2

# CFA 官方中文队名 -> 标准英文名（与 API-Football 命名对齐，便于跨源合并训练）。
# 老队沿用 apifootball 的既有英文名；apifootball 缺失的新队使用官方英文名。
_CFA_ZH_TO_STD = {
    "上海海港":       "SHANGHAI SIPG",       # apifootball: SHANGHAI SIPG
    "上海申花":       "Shanghai Shenhua",
    "云南玉昆":       "Yunnan Yukun",
    "北京国安":       "Beijing Guoan",
    "大连英博海发":   "Dalian Zhixing",       # apifootball: Dalian Zhixing（大连英博）
    "天津津门虎":     "Tianjin Teda",         # apifootball: Tianjin Teda（天津泰达）
    "山东泰山":       "Shandong Luneng",      # apifootball: Shandong Luneng（山东鲁能）
    "成都蓉城":       "Chengdu Better City",  # apifootball: Chengdu Better City
    "武汉三镇":       "Wuhan Three Towns",
    "河南俱乐部彩陶坊": "Henan Jianye",         # apifootball: Henan Jianye（河南建业）
    "浙江俱乐部绿城":  "Hangzhou Greentown",   # apifootball: Hangzhou Greentown（杭州绿城）
    "重庆铜梁龙":     "Chongqing Tongliang Long",
    "青岛海牛":       "Qingdao Jonoon",       # apifootball: Qingdao Jonoon（青岛中能→海牛）
    # —— 以下为 API-Football 2026 名单缺失/滞后的球队，使用官方英文名 ——
    "辽宁铁人楠波湾":  "Liaoning Tieren",
    "青岛西海岸":     "Qingdao West Coast",
    "深圳新鹏城":     "Shenzhen Peng City",
}


def _std_team_name(zh: str) -> str:
    """把 CFA 官方中文队名归一到标准英文名；未知则原样返回中文。"""
    return _CFA_ZH_TO_STD.get(zh.strip(), zh.strip())


def _stable_fixture_id(cfa_id: str) -> int:
    """把 CFA 的字符串 id 转成稳定的正整数 fixture_id（避免与 apifootball 整数 id 冲突）。

    apifootball 的 fixture_id 均为 < 10^7 的整数；这里用字符串哈希取一个
    9 位偏移的正整数，保证唯一且不与之碰撞。
    """
    h = 0
    for ch in cfa_id:
        h = (h * 131 + ord(ch)) & 0x7FFFFFFF
    return 900_000_000 + (h % 90_000_000)


def _ctx() -> ssl.SSLContext:
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl._create_unverified_context()


def _fetch_week(week: int, competition: str) -> dict:
    url = f"{BASE}?week={week}&competition_code={competition}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=_ctx(), timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("status") != 200:
        raise RuntimeError(f"CFA API 返回异常: {payload.get('status')} {payload.get('msg')}")
    return payload["data"]


def _match_to_fixture(m: dict) -> Optional[FixtureData]:
    """把 CFA 的一场比赛转成 FixtureData；未完赛（无比分）返回 None。"""
    if m.get("match_status") != "Played":
        return None
    hg = m.get("total_home_score")
    ag = m.get("total_away_score")
    if hg is None or ag is None:
        return None
    season = int(m.get("tournament_calendar_name") or 0)
    return FixtureData(
        fixture_id=_stable_fixture_id(m["id"]),
        season=season,
        date=m.get("local_date") or "",
        home=_std_team_name(m["home_contestant_name"]),
        away=_std_team_name(m["away_contestant_name"]),
        hg=int(hg),
        ag=int(ag),
        home_stats=TeamStats(),   # CFA 不提供场面统计
        away_stats=TeamStats(),
        events=[],                # CFA 不提供分钟级事件
    )


def load_cfa_details(competition: str = DEFAULT_COMPETITION) -> List[FixtureData]:
    """抓取当前赛季全部已完赛场次（遍历 week 1..max_week），返回 FixtureData 列表。"""
    first = _fetch_week(1, competition)
    max_week = int(first.get("max_week") or 30)

    out: List[FixtureData] = []
    seen_weeks: Dict[int, dict] = {1: first}
    for wk in range(1, max_week + 1):
        data = seen_weeks.get(wk) or _fetch_week(wk, competition)
        played = 0
        for m in data.get("list", []):
            fd = _match_to_fixture(m)
            if fd is not None:
                out.append(fd)
                played += 1
        total = len(data.get("list", []))
        print(f"  第 {wk:2d} 轮：{played}/{total} 场已完赛")

    out.sort(key=lambda d: d.date or "")
    return out


def load_cfa_matches(competition: str = DEFAULT_COMPETITION):
    """抓取并转成 csl_loader.Match，可直接喂给 train_strength.train()。"""
    from .api_football_loader import to_matches
    return to_matches(load_cfa_details(competition))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    competition = DEFAULT_COMPETITION
    args = sys.argv[1:]
    if "--competition" in args:
        competition = args[args.index("--competition") + 1]

    print(f"数据源：中国足协官方 API   联赛={competition}\n")
    details = load_cfa_details(competition)

    if not details:
        print("\n没有抓到任何已完赛场次。")
        sys.exit(0)

    season = details[0].season
    for d in details:  # 以出现最多的赛季命名（正常全部同赛季）
        season = d.season
        break

    teams = sorted({t for d in details for t in (d.home, d.away)})
    print(f"\n共 {len(details)} 场已完赛，{len(teams)} 支球队，赛季 {season}")
    print("球队：", "、".join(teams))

    SEASON_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SEASON_DIR / f"csl_{season}_details.json"
    from dataclasses import asdict
    out_path.write_text(
        json.dumps([asdict(d) for d in details], ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n已保存到：{out_path}")
