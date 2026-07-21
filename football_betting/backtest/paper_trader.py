"""简易回测 / 纸面模拟下注器。

对数据流的每个 tick：
- 选出最优的推荐投注(如果有)
- 按推荐仓位下注
- 终场时用实际最终比分结算
- 跟踪本金、ROI、命中率
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from ..core.state import BetRecommendation, MatchState, OddsSnapshot
from ..strategy.decision import evaluate


@dataclass
class OpenBet:
    minute_placed: int
    rec: BetRecommendation
    stake: float          # 以本金单位计

    def settle(self, final_state: MatchState) -> float:
        """返回盈亏(正=赢, 负=输)。"""
        win = _did_win(self.rec.market, final_state)
        if win is None:
            return 0.0  # 无法结算
        return self.stake * (self.rec.odds - 1) if win else -self.stake


def _did_win(market: str, s: MatchState) -> bool | None:
    kind, sel = market.split(":", 1)
    if kind == "1X2":
        if sel == "home": return s.score_h > s.score_a
        if sel == "draw": return s.score_h == s.score_a
        if sel == "away": return s.score_h < s.score_a
    if kind == "OU":
        # sel 形如 "over2.5" / "under2.5"
        side = "over" if sel.startswith("over") else "under"
        line = float(sel.replace("over", "").replace("under", ""))
        total = s.score_h + s.score_a
        return (total > line) if side == "over" else (total < line)
    if kind == "CS":
        h, a = map(int, sel.split("-"))
        return (s.score_h == h and s.score_a == a)
    return None


@dataclass
class PaperTrader:
    bankroll: float = 1.0
    max_open_per_match: int = 3
    dedupe: bool = True                # 不重复下同一市场
    open_bets: List[OpenBet] = field(default_factory=list)
    placed_markets: set = field(default_factory=set)
    history: list = field(default_factory=list)

    def on_tick(self, state: MatchState, odds: OddsSnapshot) -> None:
        if len(self.open_bets) >= self.max_open_per_match:
            return
        recs = evaluate(state, odds)
        for r in recs:
            if self.dedupe and r.market in self.placed_markets:
                continue
            stake = r.stake_fraction * self.bankroll
            self.open_bets.append(OpenBet(state.minute, r, stake))
            self.placed_markets.add(r.market)
            self.history.append({
                "minute": state.minute, "score": (state.score_h, state.score_a),
                "action": "PLACE", "rec": str(r), "stake": stake,
                "bankroll": self.bankroll,
            })
            if len(self.open_bets) >= self.max_open_per_match:
                break

    def settle(self, final_state: MatchState) -> dict:
        pnl = 0.0
        wins = 0
        for b in self.open_bets:
            p = b.settle(final_state)
            pnl += p
            if p > 0: wins += 1
            self.history.append({
                "minute": final_state.minute, "action": "SETTLE",
                "market": b.rec.market, "pnl": p,
            })
        self.bankroll += pnl
        return {
            "bets": len(self.open_bets),
            "wins": wins,
            "pnl": pnl,
            "final_bankroll": self.bankroll,
            "final_score": (final_state.score_h, final_state.score_a),
        }
