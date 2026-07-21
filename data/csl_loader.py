"""从 openfootball/world 仓库(公有领域数据)下载并解析中超历史赛果。

数据 URL 格式：
    https://raw.githubusercontent.com/openfootball/world/master/asia/china/{year}_cn1.txt

我们关心的行示例：
    18:00  Shandong Taishan   v Changchun Yatai   4-2 (3-0)
    (开场时间可能缺失；括号内的半场比分也是可选的)
"""
from __future__ import annotations
import re
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List

BASE_URL = "https://raw.githubusercontent.com/openfootball/world/master/asia/china/{year}_cn1.txt"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "csl_raw"

# 匹配一行已完赛的赛事, 结尾带最终比分如 "4-2" 或 "4-2 (3-0)"
_MATCH_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s+)?"          # 可选的开场时间
    r"(.+?)\s+v\s+(.+?)\s+"               # 主队 v 客队
    r"(\d+)-(\d+)"                        # 全场比分
    r"(?:\s*\(\d+-\d+\))?\s*$"            # 可选的半场比分
)


@dataclass
class Match:
    season: int      # 赛季
    home: str        # 主队
    away: str        # 客队
    hg: int          # 主队进球
    ag: int          # 客队进球


def _fetch(year: int, force: bool = False) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{year}_cn1.txt"
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8")
    url = BASE_URL.format(year=year)
    # macOS 自带 Python 常缺失 CA 证书；先尝试正常方式, 再回退到 certifi,
    # 最后回退到不验证证书的上下文。
    ctx = None
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = None
    try:
        with urllib.request.urlopen(url, timeout=30, context=ctx) as resp:
            text = resp.read().decode("utf-8")
    except ssl.SSLError:
        unverified = ssl._create_unverified_context()
        with urllib.request.urlopen(url, timeout=30, context=unverified) as resp:
            text = resp.read().decode("utf-8")
    cache.write_text(text, encoding="utf-8")
    return text


def parse_season(year: int, force: bool = False) -> List[Match]:
    text = _fetch(year, force)
    matches: List[Match] = []
    for line in text.splitlines():
        # 跳过表头 / 注释 / 比赛日标记行
        if not line.strip() or line.lstrip().startswith(("#", "=", "▪", "»")):
            continue
        m = _MATCH_RE.match(line)
        if not m:
            continue
        home, away, hg, ag = m.group(1).strip(), m.group(2).strip(), int(m.group(3)), int(m.group(4))
        matches.append(Match(year, home, away, hg, ag))
    return matches


def load_matches(years: List[int], force: bool = False) -> List[Match]:
    all_m: List[Match] = []
    for y in years:
        try:
            season = parse_season(y, force)
            all_m.extend(season)
            print(f"  {y} 赛季: {len(season)} 场")
        except Exception as e:
            print(f"  {y} 赛季下载/解析失败: {e}")
    return all_m


if __name__ == "__main__":
    ms = load_matches(list(range(2018, 2026)))
    print(f"\n总计 {len(ms)} 场比赛")
    teams = sorted({t for m in ms for t in (m.home, m.away)})
    print(f"涉及球队 {len(teams)} 支")
    print("示例:", ms[0] if ms else "无")
