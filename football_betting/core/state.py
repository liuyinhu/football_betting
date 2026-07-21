"""Data models for match state and betting markets."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MatchState:
    """Snapshot of a live match at a specific minute."""
    match_id: str
    minute: int                 # 0-90+
    score_h: int = 0
    score_a: int = 0
    # attacking / momentum features
    shots_h: int = 0
    shots_a: int = 0
    sot_h: int = 0              # shots on target
    sot_a: int = 0
    corners_h: int = 0
    corners_a: int = 0
    dangerous_attacks_h: int = 0
    dangerous_attacks_a: int = 0
    possession_h: float = 50.0
    # discipline
    fouls_h: int = 0
    fouls_a: int = 0
    yellow_h: int = 0
    yellow_a: int = 0
    red_h: int = 0
    red_a: int = 0
    # priors (pre-match expected goals)
    prior_lambda_h: float = 1.4
    prior_lambda_a: float = 1.1
    # optional xG (in-play cumulative)
    xg_h: float = 0.0
    xg_a: float = 0.0

    @property
    def remaining(self) -> int:
        return max(0, 90 - self.minute)

    @property
    def red_diff(self) -> int:
        return self.red_h - self.red_a


@dataclass
class OddsSnapshot:
    """Current market odds for a match (decimal odds)."""
    match_id: str
    minute: int
    # 1X2
    home: Optional[float] = None
    draw: Optional[float] = None
    away: Optional[float] = None
    # over/under (line -> odds)
    over: Dict[float, float] = field(default_factory=dict)   # e.g. {2.5: 2.10}
    under: Dict[float, float] = field(default_factory=dict)
    # exact scores (score tuple -> odds)
    exact: Dict[tuple, float] = field(default_factory=dict)


@dataclass
class BetRecommendation:
    market: str                 # "1X2:home", "OU:over2.5", "CS:2-1", ...
    odds: float
    model_prob: float
    edge: float                 # EV in profit units (per 1 unit stake)
    stake_fraction: float       # fraction of bankroll
    reason: str = ""

    def __repr__(self) -> str:
        return (f"<Bet {self.market} @ {self.odds:.2f} "
                f"p={self.model_prob:.3f} edge={self.edge:+.3f} "
                f"stake={self.stake_fraction:.3%} | {self.reason}>")
