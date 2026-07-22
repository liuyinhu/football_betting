"""实时预测「演示」数据源管理器（步骤 1：无外部依赖）。

目的：
    在没有真实 in-play 数据源的情况下，用 SimulatedFeed 驱动几场「正在进行」
    的中超比赛，让前端可以每 30 秒拉一次、看到分钟/比分/射门实时推进，
    并据此刷新预测概率。等接入真实实时源时，只需替换本模块即可。

核心思路：
    - 启动时挑选接下来 N 场真实中超对阵（真实队名 + 模型 λ 先验）。
    - 每场比赛「假装」在服务器启动时开球，按墙上时钟推进比赛分钟：
        match_minute = 实际经过秒数 / SECONDS_PER_MATCH_MINUTE
    - 收到请求时把该场的 SimulatedFeed 步进到目标分钟，返回当前 MatchState。
    - SimulatedFeed 只向前步进且带固定 seed，因此推进是确定性的、可复现。

对外主函数：
    live_states() -> List[Tuple[dict, MatchState]]
        返回当前所有「进行中」比赛的赛程信息 + 实时状态快照。
"""
from __future__ import annotations
import time
from typing import Dict, List, Optional, Tuple

from core.state import MatchState
from feeds.simulated import SimulatedFeed

# 每「比赛分钟」对应多少「真实秒」。默认 6 秒/分钟 =>
#   一场 90 分钟比赛约 9 分钟真实时间跑完；30 秒轮询一次约推进 5 分钟。
SECONDS_PER_MATCH_MINUTE = 6.0

# 演示同时进行的比赛场数
LIVE_MATCH_COUNT = 4

# 全场分钟数（含少量补时上限）
MATCH_TOTAL_MINUTES = 90


class _LiveMatch:
    """单场「进行中」的模拟比赛。"""

    def __init__(self, fixture: dict, lam_h: float, lam_a: float,
                 kickoff_ts: float, seed: int):
        self.fixture = fixture
        self.kickoff_ts = kickoff_ts
        self.feed = SimulatedFeed(
            match_id=str(fixture.get("match_id", "SIM")),
            prior_lambda_h=lam_h,
            prior_lambda_a=lam_a,
            seed=seed,
        )
        self._stepped_to = 0  # 已步进到的分钟

    def target_minute(self, now: float) -> int:
        elapsed = max(0.0, now - self.kickoff_ts)
        m = int(elapsed / SECONDS_PER_MATCH_MINUTE)
        return min(m, MATCH_TOTAL_MINUTES)

    def state_at(self, now: float) -> MatchState:
        """把内部 feed 步进到目标分钟并返回状态。"""
        target = self.target_minute(now)
        while self._stepped_to < target:
            self.feed.step()
            self._stepped_to += 1
        return self.feed.state

    @property
    def finished_at(self) -> float:
        return self.kickoff_ts + MATCH_TOTAL_MINUTES * SECONDS_PER_MATCH_MINUTE


# 进程级单例：首次调用时构建，之后复用
_MANAGER: Optional["_LiveSimManager"] = None


class _LiveSimManager:
    def __init__(self) -> None:
        self._matches: List[_LiveMatch] = []
        self._built = False

    def _build(self) -> None:
        """挑选真实对阵并初始化模拟比赛（延迟到首次请求时执行）。"""
        from data.upcoming import upcoming_matches
        from data.train_strength import load as load_strength, expected_lambdas

        model = load_strength()
        try:
            fixtures = upcoming_matches(max(LIVE_MATCH_COUNT, 4))
        except Exception:
            fixtures = []

        now = time.time()
        # 让几场比赛处于不同进度：分别在 3/10/25/45 分钟前开球
        offsets_min = [3, 10, 25, 45, 60, 75]
        built: List[_LiveMatch] = []
        for i, fx in enumerate(fixtures[:LIVE_MATCH_COUNT]):
            try:
                lam_h, lam_a = expected_lambdas(model, fx["home_en"], fx["away_en"])
            except Exception:
                lam_h, lam_a = 1.4, 1.1
            off = offsets_min[i % len(offsets_min)]
            kickoff = now - off * SECONDS_PER_MATCH_MINUTE
            built.append(_LiveMatch(fx, lam_h, lam_a, kickoff, seed=100 + i))

        self._matches = built
        self._built = True

    def states(self) -> List[Tuple[dict, MatchState]]:
        if not self._built:
            self._build()
        now = time.time()
        out: List[Tuple[dict, MatchState]] = []
        for lm in self._matches:
            out.append((lm.fixture, lm.state_at(now)))
        return out


def _manager() -> _LiveSimManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = _LiveSimManager()
    return _MANAGER


def live_states() -> List[Tuple[dict, MatchState]]:
    """返回当前所有「进行中」比赛的 (赛程信息, 实时状态)。"""
    return _manager().states()
