"""Download & parse Chinese Super League (中超) historical results
from the openfootball/world repository (public domain data).

Data URL pattern:
    https://raw.githubusercontent.com/openfootball/world/master/asia/china/{year}_cn1.txt

Line example we care about:
    18:00  Shandong Taishan   v Changchun Yatai   4-2 (3-0)
    (time may be missing; halftime score in parens is optional)
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

# matches a played fixture line ending with a final score like "4-2" or "4-2 (3-0)"
_MATCH_RE = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s+)?"          # optional kickoff time
    r"(.+?)\s+v\s+(.+?)\s+"               # home v away
    r"(\d+)-(\d+)"                        # full-time score
    r"(?:\s*\(\d+-\d+\))?\s*$"            # optional halftime score
)


@dataclass
class Match:
    season: int
    home: str
    away: str
    hg: int          # home goals
    ag: int          # away goals


def _fetch(year: int, force: bool = False) -> str:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{year}_cn1.txt"
    if cache.exists() and not force:
        return cache.read_text(encoding="utf-8")
    url = BASE_URL.format(year=year)
    # macOS system Python often lacks CA certs; try normal first, fall back to
    # certifi, then to an unverified context as a last resort.
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
        # skip headers / comments / matchday markers
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
