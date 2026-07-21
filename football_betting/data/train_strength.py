"""Train a Dixon-Coles / Poisson team-strength model on CSL history.

Model (classic Maximum Likelihood):
    goals_home ~ Poisson(mu_home)
    goals_away ~ Poisson(mu_away)
    log(mu_home) = attack[home] - defence[away] + home_adv
    log(mu_away) = attack[away] - defence[home]

with a Dixon-Coles low-score dependence correction tau(., rho).

Parameters are fit by minimizing the negative log-likelihood with
optional time-decay weighting (recent seasons matter more).

Output: a JSON file mapping each team -> attack / defence strength,
plus global home_adv & rho. This lets us derive pre-match lambdas:

    lambda_home = exp(attack[H] - defence[A] + home_adv)
    lambda_away = exp(attack[A] - defence[H])
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy.optimize import minimize

from .csl_loader import Match, load_matches

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "csl_strength.json"


def _dc_tau(hg: int, ag: int, mu_h: float, mu_a: float, rho: float) -> float:
    if hg == 0 and ag == 0:
        return 1 - mu_h * mu_a * rho
    if hg == 0 and ag == 1:
        return 1 + mu_h * rho
    if hg == 1 and ag == 0:
        return 1 + mu_a * rho
    if hg == 1 and ag == 1:
        return 1 - rho
    return 1.0


def train(matches: List[Match],
          decay: float = 0.0018,
          latest_season: int | None = None) -> Dict:
    """Fit attack/defence strengths via MLE with season time-decay."""
    teams = sorted({t for m in matches for t in (m.home, m.away)})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    if latest_season is None:
        latest_season = max(m.season for m in matches)

    # time-decay weight: older seasons down-weighted
    weights = np.array([math.exp(-decay * 365 * (latest_season - m.season))
                        for m in matches])

    hg = np.array([m.hg for m in matches])
    ag = np.array([m.ag for m in matches])
    h_idx = np.array([idx[m.home] for m in matches])
    a_idx = np.array([idx[m.away] for m in matches])

    # params: [attack(n), defence(n), home_adv, rho]
    def unpack(p):
        atk = p[:n]
        dfc = p[n:2 * n]
        home_adv = p[2 * n]
        rho = p[2 * n + 1]
        return atk, dfc, home_adv, rho

    def neg_log_likelihood(p):
        atk, dfc, home_adv, rho = unpack(p)
        mu_h = np.exp(atk[h_idx] - dfc[a_idx] + home_adv)
        mu_a = np.exp(atk[a_idx] - dfc[h_idx])
        # poisson log-pmf
        ll = (hg * np.log(mu_h) - mu_h - _gammaln(hg + 1)
              + ag * np.log(mu_a) - mu_a - _gammaln(ag + 1))
        # dixon-coles correction (vectorized-ish)
        tau = np.array([_dc_tau(int(hg[i]), int(ag[i]), mu_h[i], mu_a[i], rho)
                        for i in range(len(hg))])
        tau = np.clip(tau, 1e-6, None)
        ll += np.log(tau)
        return -np.sum(weights * ll)

    # constraint: mean attack = 0 (identifiability)
    cons = [{"type": "eq", "fun": lambda p: np.sum(p[:n])}]

    x0 = np.concatenate([
        np.zeros(n),        # attack
        np.zeros(n),        # defence
        [0.25],             # home advantage
        [-0.05],            # rho
    ])
    bounds = [(-3, 3)] * (2 * n) + [(-1, 1), (-0.3, 0.3)]

    print(f"训练中… {len(matches)} 场, {n} 支球队")
    res = minimize(neg_log_likelihood, x0, method="SLSQP",
                   bounds=bounds, constraints=cons,
                   options={"maxiter": 400, "ftol": 1e-7})

    atk, dfc, home_adv, rho = unpack(res.x)
    model = {
        "teams": {t: {"attack": float(atk[idx[t]]),
                      "defence": float(dfc[idx[t]])} for t in teams},
        "home_adv": float(home_adv),
        "rho": float(rho),
        "n_matches": len(matches),
        "latest_season": latest_season,
        "converged": bool(res.success),
        "nll": float(res.fun),
    }
    return model


def _gammaln(x):
    from scipy.special import gammaln
    return gammaln(x)


def expected_lambdas(model: Dict, home: str, away: str) -> tuple[float, float]:
    """Compute pre-match lambda_home, lambda_away from trained strengths."""
    t = model["teams"]
    if home not in t or away not in t:
        raise KeyError(f"未知球队: {home if home not in t else away}")
    ha = model["home_adv"]
    lam_h = math.exp(t[home]["attack"] - t[away]["defence"] + ha)
    lam_a = math.exp(t[away]["attack"] - t[home]["defence"])
    # clip to a sane in-league range to avoid extreme single-team blowouts
    lam_h = min(max(lam_h, 0.2), 3.0)
    lam_a = min(max(lam_a, 0.2), 3.0)
    return lam_h, lam_a


def save(model: Dict, path: Path = MODEL_PATH) -> None:
    path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")


def load(path: Path = MODEL_PATH) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import sys
    # usage:
    #   python3 -m football_betting.data.train_strength            # 默认近3季 2023-2025
    #   python3 -m football_betting.data.train_strength 2022 2025  # 指定起止年份
    #   python3 -m football_betting.data.train_strength 3          # 最近N季
    all_years = list(range(2018, 2026))
    latest = all_years[-1]

    args = sys.argv[1:]
    if len(args) == 2:
        start, end = int(args[0]), int(args[1])
        years = list(range(start, end + 1))
    elif len(args) == 1:
        n = int(args[0])
        years = all_years[-n:]
    else:
        years = [2023, 2024, 2025]   # 默认近3个赛季

    print(f"使用赛季: {years}")
    matches = load_matches(years)
    # 近几年数据时间跨度小, 用较小衰减即可
    model = train(matches, decay=0.0018, latest_season=latest)
    model["train_years"] = years
    save(model)
    print(f"\n收敛: {model['converged']}  NLL={model['nll']:.1f}  主场优势={model['home_adv']:.3f}  rho={model['rho']:.3f}")
    print(f"训练赛季: {years}  球队数: {len(model['teams'])}")
    print(f"模型已保存: {MODEL_PATH}")

    # show strongest / weakest teams by (attack - defence) net rating
    ranking = sorted(model["teams"].items(),
                     key=lambda kv: kv[1]["attack"] - kv[1]["defence"],
                     reverse=True)
    print("\n综合实力 TOP 10 (attack - defence):")
    for name, s in ranking[:10]:
        print(f"  {name:26s} 攻 {s['attack']:+.2f}  防 {s['defence']:+.2f}  "
              f"净 {s['attack'] - s['defence']:+.2f}")
