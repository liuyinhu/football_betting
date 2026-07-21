"""在中超历史数据上训练 Dixon-Coles / 泊松 球队强度模型。

模型(经典最大似然估计)：
    主队进球 ~ Poisson(mu_home)
    客队进球 ~ Poisson(mu_away)
    log(mu_home) = attack[主] - defence[客] + home_adv
    log(mu_away) = attack[客] - defence[主]

并加入 Dixon-Coles 低比分相关性修正 tau(., rho)。

参数通过最小化负对数似然拟合, 可选时间衰减加权(越近的赛季权重越高)。

输出：一个 JSON 文件, 映射每支球队 -> 攻击/防守强度,
以及全局的 home_adv 与 rho。据此可推导赛前 lambda：

    lambda_home = exp(attack[主] - defence[客] + home_adv)
    lambda_away = exp(attack[客] - defence[主])
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
    """Dixon-Coles 低比分修正系数。"""
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
    """用带赛季时间衰减的最大似然估计, 拟合各队攻击/防守强度。"""
    teams = sorted({t for m in matches for t in (m.home, m.away)})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    if latest_season is None:
        latest_season = max(m.season for m in matches)

    # 时间衰减权重：越老的赛季权重越低
    weights = np.array([math.exp(-decay * 365 * (latest_season - m.season))
                        for m in matches])

    hg = np.array([m.hg for m in matches])
    ag = np.array([m.ag for m in matches])
    h_idx = np.array([idx[m.home] for m in matches])
    a_idx = np.array([idx[m.away] for m in matches])

    # 参数向量: [攻击(n), 防守(n), 主场优势, rho]
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
        # 泊松对数概率质量函数
        ll = (hg * np.log(mu_h) - mu_h - _gammaln(hg + 1)
              + ag * np.log(mu_a) - mu_a - _gammaln(ag + 1))
        # Dixon-Coles 修正
        tau = np.array([_dc_tau(int(hg[i]), int(ag[i]), mu_h[i], mu_a[i], rho)
                        for i in range(len(hg))])
        tau = np.clip(tau, 1e-6, None)
        ll += np.log(tau)
        return -np.sum(weights * ll)

    # 约束: 攻击强度均值=0 (保证参数可辨识)
    cons = [{"type": "eq", "fun": lambda p: np.sum(p[:n])}]

    x0 = np.concatenate([
        np.zeros(n),        # 攻击
        np.zeros(n),        # 防守
        [0.25],             # 主场优势
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
    """根据训练好的强度, 计算赛前的 lambda_home 与 lambda_away。"""
    t = model["teams"]
    if home not in t or away not in t:
        raise KeyError(f"未知球队: {home if home not in t else away}")
    ha = model["home_adv"]
    lam_h = math.exp(t[home]["attack"] - t[away]["defence"] + ha)
    lam_a = math.exp(t[away]["attack"] - t[home]["defence"])
    # 限制在合理区间, 避免单队数值过于极端
    lam_h = min(max(lam_h, 0.2), 3.0)
    lam_a = min(max(lam_a, 0.2), 3.0)
    return lam_h, lam_a


def save(model: Dict, path: Path = MODEL_PATH) -> None:
    path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")


def load(path: Path = MODEL_PATH) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    import sys
    # 用法:
    #   python3 -m data.train_strength            # 默认近3季 2023-2025
    #   python3 -m data.train_strength 2022 2025  # 指定起止年份
    #   python3 -m data.train_strength 3          # 最近N季
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

    # 按净实力(攻击 - 防守)展示最强的球队
    ranking = sorted(model["teams"].items(),
                     key=lambda kv: kv[1]["attack"] - kv[1]["defence"],
                     reverse=True)
    print("\n综合实力 TOP 10 (攻击 - 防守):")
    for name, s in ranking[:10]:
        print(f"  {name:26s} 攻 {s['attack']:+.2f}  防 {s['defence']:+.2f}  "
              f"净 {s['attack'] - s['defence']:+.2f}")
