"""数据源接口 + 用于离线测试/演示的模拟数据源。"""
from __future__ import annotations
import random
from typing import Iterator, Tuple

from ..core.state import MatchState, OddsSnapshot


class SimulatedFeed:
    """为一场合成比赛生成有合理性的实时数据流。

    每一个 tick 前进 1 分钟, 并随机更新统计数据/赔率。
    用于在没有真实数据源的情况下测试整个流程。
    """

    def __init__(self,
                 match_id: str = "SIM-001",
                 prior_lambda_h: float = 1.5,
                 prior_lambda_a: float = 1.1,
                 seed: int | None = 42):
        self.match_id = match_id
        self.rng = random.Random(seed)
        self.state = MatchState(
            match_id=match_id,
            minute=0,
            prior_lambda_h=prior_lambda_h,
            prior_lambda_a=prior_lambda_a,
        )
        # 以先验值派生的合理赔率作为起点
        self.book_margin = 1.06  # 6% 的菣佣(overround)

    # ---------- 辅助方法 ----------
    def _maybe_goal(self, lam_per_min: float) -> bool:
        return self.rng.random() < lam_per_min

    def _bump(self, mean: float) -> int:
        # 粗略的每分钟类泊松增量
        return 1 if self.rng.random() < mean else 0

    # ---------- 主接口 ----------
    def step(self) -> Tuple[MatchState, OddsSnapshot]:
        s = self.state
        s.minute += 1

        # 每分钟进球概率
        p_goal_h = s.prior_lambda_h / 90 * (1.15 if s.possession_h > 55 else 1.0)
        p_goal_a = s.prior_lambda_a / 90 * (1.15 if s.possession_h < 45 else 1.0)
        if self._maybe_goal(p_goal_h): s.score_h += 1
        if self._maybe_goal(p_goal_a): s.score_a += 1

        # 节奏统计
        s.shots_h += self._bump(0.18); s.shots_a += self._bump(0.14)
        s.sot_h  += self._bump(0.06); s.sot_a  += self._bump(0.05)
        s.corners_h += self._bump(0.08); s.corners_a += self._bump(0.07)
        s.dangerous_attacks_h += self._bump(0.9); s.dangerous_attacks_a += self._bump(0.8)
        s.fouls_h += self._bump(0.12); s.fouls_a += self._bump(0.13)
        if self.rng.random() < 0.008: s.yellow_h += 1
        if self.rng.random() < 0.008: s.yellow_a += 1
        if self.rng.random() < 0.0015: s.red_h += 1
        if self.rng.random() < 0.0015: s.red_a += 1

        # xG 大致按射正比例累加
        s.xg_h += 0.11 * (1 if self._maybe_goal(0.05) else 0) + self._bump(0.06) * 0.09
        s.xg_a += 0.11 * (1 if self._maybe_goal(0.045) else 0) + self._bump(0.05) * 0.09

        # 控球率随机游走
        s.possession_h = max(30, min(70, s.possession_h + self.rng.uniform(-1.5, 1.5)))

        odds = self._synth_odds()
        return s, odds

    def _synth_odds(self) -> OddsSnapshot:
        """非常粗略的模拟庄家：用当前状态的泊松概率 + 菣佣
        + 少量随机噪声, 使模型有时能找到价值。"""
        from ..models.poisson_live import outcome_probabilities, final_score_distribution
        probs = outcome_probabilities(self.state)

        def to_odds(p: float) -> float | None:
            if p <= 1e-4: return None
            # 加上菣佣与噪声
            noisy = p * self.book_margin * self.rng.uniform(0.90, 1.10)
            noisy = min(max(noisy, 1e-3), 0.98)
            return round(1 / noisy, 2)

        snap = OddsSnapshot(
            match_id=self.match_id,
            minute=self.state.minute,
            home=to_odds(probs["home"]),
            draw=to_odds(probs["draw"]),
            away=to_odds(probs["away"]),
        )
        for line in (1.5, 2.5, 3.5):
            snap.over[line]  = to_odds(probs[f"over_{line}"])  or 99.0
            snap.under[line] = to_odds(probs[f"under_{line}"]) or 99.0

        # 当前比分附近的几个精确比分市场
        dist = final_score_distribution(self.state)
        top_scores = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:6]
        for score, p in top_scores:
            o = to_odds(p)
            if o: snap.exact[score] = o
        return snap

    def run(self, minutes: int = 90) -> Iterator[Tuple[MatchState, OddsSnapshot]]:
        for _ in range(minutes):
            yield self.step()
