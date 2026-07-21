"""通过 API-Football (v3) 免费档拉取中超比赛的分钟级/事件级数据。

免费档限制（务必注意）：
    - 认证：请求头 x-apisports-key，key 从环境变量 API_FOOTBALL_KEY 读取
    - 配额：约 100 请求/天
    - 每场比赛需要 2 个请求（statistics + events），因此本模块会：
        * 本地缓存每场结果到 data/apifootball_raw/（避免重复消耗配额）
        * 提供 --limit 限制拉取场次
        * 请求间加入延时，避免触发限流

主要接口：
    /leagues                          查联赛 id（中超默认 169）
    /fixtures?league=169&season=2023  拉某赛季的赛程赛果
    /fixtures/statistics?fixture=ID   终场场面统计（射门/射正/角球/控球…）
    /fixtures/events?fixture=ID       带分钟的事件（进球/红黄牌/换人…）

用法：
    export API_FOOTBALL_KEY=你的key
    python3 -m football_betting.data.api_football_loader 2023 --limit 20
"""
from __future__ import annotations
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

BASE = "https://v3.football.api-sports.io"
CSL_LEAGUE_ID = 169  # 中超 Chinese Super League

# 数据根目录，下分两个子目录：
#   cache/   —— 单场缓存 fixture_<id>.json（避免重复消耗 API 配额，可随时删除重拉）
#   seasons/ —— 赛季汇总产物 csl_<season>_details.json（最终数据，供训练/分析读取）
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "apifootball_raw"
CACHE_DIR = DATA_DIR / "cache"        # 单场缓存
SEASON_DIR = DATA_DIR / "seasons"     # 赛季汇总

# 每次请求之间的间隔（秒）。免费档限速约 10 次/分钟，故设为 ≥6.5 秒
REQUEST_DELAY = 6.5


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class TeamStats:
    """一支球队的终场场面统计（缺失项为 None）。"""
    shots: Optional[int] = None            # 总射门
    shots_on: Optional[int] = None         # 射正
    corners: Optional[int] = None          # 角球
    possession: Optional[float] = None     # 控球率 %
    fouls: Optional[int] = None            # 犯规
    yellow: Optional[int] = None           # 黄牌
    red: Optional[int] = None              # 红牌
    xg: Optional[float] = None             # 预期进球（部分比赛无）


@dataclass
class FixtureData:
    fixture_id: int
    season: int
    date: str
    home: str
    away: str
    hg: Optional[int]                      # 主队进球
    ag: Optional[int]                      # 客队进球
    home_stats: TeamStats = field(default_factory=TeamStats)
    away_stats: TeamStats = field(default_factory=TeamStats)
    # 带分钟的事件列表：[{"minute": 23, "type": "Goal", "team": "...", "detail": "..."}]
    events: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 底层 HTTP
# ---------------------------------------------------------------------------
def _get_key() -> str:
    key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "未设置 API key。请先执行：export API_FOOTBALL_KEY=你的key\n"
            "免费 key 注册地址：https://www.api-football.com/"
        )
    return key


def _request(endpoint: str, params: dict, _retry: int = 1) -> dict:
    """发起一次 GET 请求，返回解析后的 JSON（response 字段）。

    遇到 429（限速）时自动等待 60 秒重试一次。
    """
    url = f"{BASE}{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"x-apisports-key": _get_key()})
    # macOS 自带 Python 常缺 CA 证书，做与 csl_loader 一致的回退
    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = None
    try:
        try:
            with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except ssl.SSLError:
            unverified = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=30, context=unverified) as resp:
                data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429 and _retry > 0:
            print("  · 触发限速(429)，等待 60 秒后重试…")
            time.sleep(60)
            return _request(endpoint, params, _retry - 1)
        raise

    # API-Football 把错误放在 errors 字段里（HTTP 仍是 200）
    errors = data.get("errors")
    if errors:
        raise RuntimeError(f"API 返回错误: {errors}")
    time.sleep(REQUEST_DELAY)
    return data


# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------
def _stat_value(name: str, items: List[dict]):
    """从 statistics 列表里按 type 取值。"""
    for it in items:
        if it.get("type") == name:
            return it.get("value")
    return None


def _to_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_possession(v) -> Optional[float]:
    # 形如 "58%"
    if isinstance(v, str) and v.endswith("%"):
        try:
            return float(v.rstrip("%"))
        except ValueError:
            return None
    return None


def _parse_team_stats(items: List[dict]) -> TeamStats:
    return TeamStats(
        shots=_to_int(_stat_value("Total Shots", items)),
        shots_on=_to_int(_stat_value("Shots on Goal", items)),
        corners=_to_int(_stat_value("Corner Kicks", items)),
        possession=_parse_possession(_stat_value("Ball Possession", items)),
        fouls=_to_int(_stat_value("Fouls", items)),
        yellow=_to_int(_stat_value("Yellow Cards", items)),
        red=_to_int(_stat_value("Red Cards", items)),
        xg=(lambda x: float(x) if x not in (None, "") else None)(
            _stat_value("expected_goals", items)),
    )


# ---------------------------------------------------------------------------
# 高层拉取逻辑
# ---------------------------------------------------------------------------
def find_league_id(name: str = "Super League", country: str = "China") -> int:
    """按名称/国家查联赛 id（默认返回中超）。"""
    data = _request("/leagues", {"search": name, "country": country})
    for item in data.get("response", []):
        return item["league"]["id"]
    return CSL_LEAGUE_ID


def fetch_fixtures(season: int, league: int = CSL_LEAGUE_ID) -> List[dict]:
    """拉某赛季所有场次（1 个请求）。返回原始 fixture 列表。"""
    data = _request("/fixtures", {"league": league, "season": season})
    return data.get("response", [])


def fetch_statistics(fixture_id: int) -> List[dict]:
    """拉某场比赛的双方终场统计（1 个请求）。"""
    data = _request("/fixtures/statistics", {"fixture": fixture_id})
    return data.get("response", [])


def fetch_events(fixture_id: int) -> List[dict]:
    """拉某场比赛的带分钟事件（1 个请求）。"""
    data = _request("/fixtures/events", {"fixture": fixture_id})
    return data.get("response", [])


def _cache_path(fixture_id: int) -> Path:
    return CACHE_DIR / f"fixture_{fixture_id}.json"


def load_fixture_detail(fx: dict, use_cache: bool = True) -> FixtureData:
    """对单场比赛拉取 statistics + events（消耗 2 个请求），并缓存。"""
    fixture_id = fx["fixture"]["id"]
    cache = _cache_path(fixture_id)
    if use_cache and cache.exists():
        raw = json.loads(cache.read_text(encoding="utf-8"))
        return _fixture_from_dict(raw)

    teams = fx["teams"]
    goals = fx["goals"]
    fd = FixtureData(
        fixture_id=fixture_id,
        season=fx["league"]["season"],
        date=fx["fixture"]["date"],
        home=teams["home"]["name"],
        away=teams["away"]["name"],
        hg=goals.get("home"),
        ag=goals.get("away"),
    )

    # statistics：response 是双方各一项，用 team.id 对齐主客
    stats = fetch_statistics(fixture_id)
    home_id = teams["home"]["id"]
    for entry in stats:
        ts = _parse_team_stats(entry.get("statistics", []))
        if entry["team"]["id"] == home_id:
            fd.home_stats = ts
        else:
            fd.away_stats = ts

    # events：抽取分钟 + 类型 + 队名
    for ev in fetch_events(fixture_id):
        fd.events.append({
            "minute": (ev.get("time") or {}).get("elapsed"),
            "extra": (ev.get("time") or {}).get("extra"),
            "team": (ev.get("team") or {}).get("name"),
            "type": ev.get("type"),
            "detail": ev.get("detail"),
            "player": (ev.get("player") or {}).get("name"),
        })

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(asdict(fd), ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return fd


def _fixture_from_dict(d: dict) -> FixtureData:
    d = dict(d)
    d["home_stats"] = TeamStats(**d.get("home_stats", {}))
    d["away_stats"] = TeamStats(**d.get("away_stats", {}))
    return FixtureData(**d)


def load_season_details(season: int,
                        league: int = CSL_LEAGUE_ID,
                        limit: Optional[int] = None,
                        finished_only: bool = True,
                        latest_first: bool = True) -> List[FixtureData]:
    """拉某赛季的比赛明细。

    请求数 = 1（赛程） + 2 × 实际拉取的场次。
    limit 用于控制场次，避免超出免费档 100/天 的配额。
    latest_first=True 时按比赛日期倒序（最新的在前）再截取 limit。
    已缓存的场次不再消耗配额。
    """
    fixtures = fetch_fixtures(season, league)
    if finished_only:
        fixtures = [f for f in fixtures
                    if (f["fixture"].get("status") or {}).get("short") == "FT"]

    # 按日期排序：最新的在前
    fixtures.sort(key=lambda f: f["fixture"].get("date") or "",
                  reverse=latest_first)
    print(f"{season} 赛季共 {len(fixtures)} 场已完赛比赛"
          f"（{'最新→最早' if latest_first else '最早→最新'}）")

    if limit is not None:
        fixtures = fixtures[:limit]
        order = "最新" if latest_first else "最早"
        print(f"本次拉取{order} {len(fixtures)} 场（--limit）")

    out: List[FixtureData] = []
    for i, fx in enumerate(fixtures, 1):
        try:
            fd = load_fixture_detail(fx)
            out.append(fd)
            print(f"  [{i}/{len(fixtures)}] {fd.home} {fd.hg}-{fd.ag} {fd.away}  "
                  f"射正 {fd.home_stats.shots_on}-{fd.away_stats.shots_on}  "
                  f"角球 {fd.home_stats.corners}-{fd.away_stats.corners}  "
                  f"事件 {len(fd.events)}")
        except Exception as e:
            print(f"  [{i}] 拉取失败 fixture={fx['fixture']['id']}: {e}")
            break  # 多半是配额用尽，停止以免浪费
    return out


# ---------------------------------------------------------------------------
# 与现有训练器互通
# ---------------------------------------------------------------------------
def to_matches(details: List[FixtureData]):
    """把 FixtureData 转成 csl_loader.Match，可直接喂给 train_strength.train()。"""
    from .csl_loader import Match
    out = []
    for d in details:
        if d.hg is None or d.ag is None:
            continue
        out.append(Match(d.season, d.home, d.away, int(d.hg), int(d.ag)))
    return out


def load_saved_details(season: int) -> List[FixtureData]:
    """读取此前保存的赛季明细文件（不消耗 API 配额）。"""
    path = SEASON_DIR / f"csl_{season}_details.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到 {path}，请先运行拉取命令。")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [_fixture_from_dict(d) for d in raw]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    season = 2023
    limit: Optional[int] = 10  # 默认保守，避免一次跑光配额

    # 解析：第一个纯数字当赛季；--limit N / --all
    i = 0
    positional = [a for a in args if not a.startswith("--")]
    if positional:
        season = int(positional[0])
    if "--all" in args:
        limit = None
    elif "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx + 1])

    print(f"赛季={season}  limit={limit}")
    print("提示：免费档约 100 请求/天，每场消耗 2 个请求（statistics+events）。\n")

    details = load_season_details(season, limit=limit)

    # 汇总保存为一个赛季文件，便于后续训练使用
    out_path = SEASON_DIR / f"csl_{season}_details.json"
    SEASON_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([asdict(d) for d in details], ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n已保存 {len(details)} 场明细到: {out_path}")
