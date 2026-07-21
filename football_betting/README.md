# Football Live Betting Predictor

A Python framework that consumes **live match state** (score, minute, shots, corners, fouls, red cards, xG …) plus **live market odds**, and produces:

1. Real-time score / outcome probabilities (time-varying Poisson + Dixon-Coles correction)
2. Positive-EV bet recommendations
3. Fractional-Kelly stake sizing with risk caps

> ⚠️ This is an **educational / research** framework. Gambling is illegal in mainland China and long-term profitability against efficient bookmakers is very hard. Use for simulation only.

## Structure

```
football_betting/
├── core/state.py           # dataclasses: MatchState, OddsSnapshot, BetRecommendation
├── models/poisson_live.py  # time-varying Poisson + DC score/outcome distribution
├── strategy/decision.py    # EV filter + fractional-Kelly stake sizing
├── feeds/simulated.py      # synthetic in-play feed (for demo & backtest)
├── backtest/paper_trader.py# simple paper-trading engine
└── main.py                 # end-to-end runnable demo
```

## Install

```bash
pip install -r football_betting/requirements.txt
```

## Run demo (single simulated match)

```bash
python -m football_betting.main
```

## Monte-Carlo over 500 matches

```bash
python -m football_betting.main mc 500
```

## Wiring a real data source

Implement a class exposing the same interface as `SimulatedFeed`:

```python
class MyLiveFeed:
    def step(self) -> tuple[MatchState, OddsSnapshot]: ...
```

then feed it into the same evaluation pipeline:

```python
from football_betting.strategy.decision import evaluate
state, odds = feed.step()
for rec in evaluate(state, odds):
    print(rec)
```

Recommended real sources:
- **Match stats**: API-Football, SportMonks, Understat
- **Odds**: Betfair Exchange API (best), Pinnacle, OddsPortal

## Tuning knobs

`strategy/decision.py`:
- `MIN_EDGE`     – minimum EV required to place a bet (default 3%)
- `KELLY_FRACTION` – fraction of full Kelly (default 1/4)
- `MAX_STAKE_PER_BET` – hard cap per bet (default 2%)
- `MIN_ODDS`, `MAX_ODDS` – filter extreme odds

`models/poisson_live.py`:
- `FEATURE_WEIGHTS`  – how each in-play stat pushes λ up/down
- `RED_CARD_PENALTY` – multiplier when a team goes down to 10 men

## Next steps

- Replace `SimulatedFeed` with a real websocket / REST feed
- Learn `FEATURE_WEIGHTS` from historical minute-by-minute data (LightGBM)
- Add walk-forward backtesting on a full season
- Add persistence (SQLite) + a Telegram/企业微信 notifier
