"""数据模型：比赛状态与投注市场。"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MatchState:
    """某一分钟时刻的实时比赛状态快照。"""
    match_id: str
    minute: int                 # 当前分钟数 0-90+
    score_h: int = 0            # 主队进球
    score_a: int = 0            # 客队进球
    # 进攻 / 势头特征
    shots_h: int = 0            # 主队总射门
    shots_a: int = 0            # 客队总射门
    sot_h: int = 0              # 主队射正
    sot_a: int = 0              # 客队射正
    corners_h: int = 0          # 主队角球
    corners_a: int = 0          # 客队角球
    dangerous_attacks_h: int = 0  # 主队危险进攻
    dangerous_attacks_a: int = 0  # 客队危险进攻
    possession_h: float = 50.0    # 主队控球率(%)
    # 纪律(犯规/黄红牌)
    fouls_h: int = 0            # 主队犯规
    fouls_a: int = 0            # 客队犯规
    yellow_h: int = 0           # 主队黄牌
    yellow_a: int = 0           # 客队黄牌
    red_h: int = 0              # 主队红牌
    red_a: int = 0              # 客队红牌
    # 先验(赛前预期进球 λ)
    prior_lambda_h: float = 1.4
    prior_lambda_a: float = 1.1
    # 可选的实时累计 xG(预期进球)
    xg_h: float = 0.0
    xg_a: float = 0.0

    @property
    def remaining(self) -> int:
        """剩余比赛分钟数。"""
        return max(0, 90 - self.minute)

    @property
    def red_diff(self) -> int:
        """红牌差(主队 - 客队)。"""
        return self.red_h - self.red_a


@dataclass
class OddsSnapshot:
    """某场比赛当前的市场赔率(欧洲/小数赔率)。"""
    match_id: str
    minute: int
    # 胜平负 1X2
    home: Optional[float] = None   # 主胜赔率
    draw: Optional[float] = None   # 平局赔率
    away: Optional[float] = None   # 客胜赔率
    # 大小球 (盘口线 -> 赔率)
    over: Dict[float, float] = field(default_factory=dict)   # 如 {2.5: 2.10}
    under: Dict[float, float] = field(default_factory=dict)
    # 精确比分 (比分元组 -> 赔率)
    exact: Dict[tuple, float] = field(default_factory=dict)


@dataclass
class BetRecommendation:
    """一条投注推荐。"""
    market: str                 # 市场标识, 如 "1X2:home"、"OU:over2.5"、"CS:2-1"
    odds: float                 # 赔率
    model_prob: float           # 模型估计的中奖概率
    edge: float                 # 期望值 EV(每 1 单位投注的期望利润)
    stake_fraction: float       # 建议投注占总资金的比例
    reason: str = ""

    def __repr__(self) -> str:
        return (f"<Bet {self.market} @ {self.odds:.2f} "
                f"p={self.model_prob:.3f} edge={self.edge:+.3f} "
                f"stake={self.stake_fraction:.3%} | {self.reason}>")
