"""End-to-end demo: run a simulated match, print predictions & bet recommendations,
then settle and show P&L.

Run:
    python -m football_betting.main
"""
from __future__ import annotations

from .feeds.simulated import SimulatedFeed
from .models.poisson_live import outcome_probabilities
from .strategy.decision import evaluate
from .backtest.paper_trader import PaperTrader


def pretty_probs(p: dict) -> str:
    return (f"H={p['home']:.2f} D={p['draw']:.2f} A={p['away']:.2f} | "
            f"O2.5={p['over_2.5']:.2f} BTTS={p['btts_yes']:.2f}")


def run_one_match(verbose: bool = True) -> dict:
    feed = SimulatedFeed(prior_lambda_h=1.5, prior_lambda_a=1.2, seed=7)
    trader = PaperTrader(bankroll=1.0)

    last_state = None
    for state, odds in feed.run(minutes=90):
        last_state = state
        probs = outcome_probabilities(state)
        recs = evaluate(state, odds)

        if verbose and (state.minute % 15 == 0 or recs):
            print(f"\n[{state.minute:>2}'] score {state.score_h}-{state.score_a}  "
                  f"SoT {state.sot_h}-{state.sot_a}  "
                  f"Corners {state.corners_h}-{state.corners_a}  "
                  f"Red {state.red_h}-{state.red_a}")
            print(f"       model probs: {pretty_probs(probs)}")
            if odds.home and odds.draw and odds.away:
                print(f"       market 1X2 : {odds.home:.2f}/{odds.draw:.2f}/{odds.away:.2f}")
            for r in recs[:3]:
                print(f"       >>> BET {r}")

        trader.on_tick(state, odds)

    summary = trader.settle(last_state)
    print("\n" + "=" * 60)
    print(f"FINAL SCORE: {summary['final_score'][0]}-{summary['final_score'][1]}")
    print(f"BETS PLACED: {summary['bets']}  WINS: {summary['wins']}  "
          f"P&L: {summary['pnl']:+.4f}  BANKROLL: {summary['final_bankroll']:.4f}")
    return summary


def run_many(n: int = 200) -> None:
    """Quick Monte-Carlo of the strategy over many simulated matches."""
    total_pnl = 0.0
    total_bets = 0
    total_wins = 0
    bankroll = 100.0
    for i in range(n):
        feed = SimulatedFeed(prior_lambda_h=1.5, prior_lambda_a=1.2, seed=i)
        trader = PaperTrader(bankroll=bankroll)
        last = None
        for state, odds in feed.run(90):
            last = state
            trader.on_tick(state, odds)
        s = trader.settle(last)
        bankroll = s["final_bankroll"]
        total_pnl += s["pnl"]
        total_bets += s["bets"]
        total_wins += s["wins"]
    print("\n=== MONTE-CARLO SUMMARY ===")
    print(f"matches: {n}  bets: {total_bets}  wins: {total_wins}  "
          f"hit-rate: {(total_wins / max(total_bets,1)):.2%}")
    print(f"total P&L: {total_pnl:+.3f} units  final bankroll: {bankroll:.3f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "mc":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        run_many(n)
    else:
        run_one_match(verbose=True)
