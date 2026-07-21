"""基于 API-Football 明细数据（分钟级事件 + 终场统计 + 比分）的分析脚本。

做三件事：
  1) 分钟级进球分布 —— 验证"进球强度随比赛时间变化"（时变泊松假设）
  2) 描述统计 —— 主客场进球、场面统计与进球的相关性
  3) 特征权重回归 —— 用泊松回归拟合"场面特征差 → 进球数"，
     校准 models/poisson_live.py 里的 FEATURE_WEIGHTS

用法：
    python3 -m data.analyze_apifootball 2024
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import List

import numpy as np

from .api_football_loader import SEASON_DIR


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def load(season: int) -> list:
    path = SEASON_DIR / f"csl_{season}_details.json"
    if not path.exists():
        raise FileNotFoundError(f"未找到 {path}，请先运行拉取命令。")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1) 分钟级进球分布
# ---------------------------------------------------------------------------
def goal_timing(details: list) -> None:
    print("\n" + "=" * 60)
    print("【1. 分钟级进球分布】(验证进球强度随时间变化)")
    print("=" * 60)

    # 按 15 分钟一档统计进球数
    buckets = {f"{lo:02d}-{lo+15:02d}": 0 for lo in range(0, 90, 15)}
    total_goals = 0
    for m in details:
        for e in m["events"]:
            if e.get("type") == "Goal" and e.get("minute") is not None:
                mn = e["minute"]
                lo = min(int(mn) // 15 * 15, 75)
                buckets[f"{lo:02d}-{lo+15:02d}"] += 1
                total_goals += 1

    n_matches = len(details)
    print(f"共 {n_matches} 场，进球事件 {total_goals} 个，"
          f"场均 {total_goals / n_matches:.2f} 球\n")
    peak = max(buckets.values()) or 1
    for label, cnt in buckets.items():
        bar = "█" * int(cnt / peak * 30)
        share = cnt / total_goals * 100 if total_goals else 0
        print(f"  {label}'  {cnt:3d}  {share:4.1f}%  {bar}")

    # 上下半场对比
    first = sum(v for k, v in buckets.items() if int(k[:2]) < 45)
    second = total_goals - first
    print(f"\n  上半场进球 {first}（{first/total_goals*100:.1f}%），"
          f"下半场进球 {second}（{second/total_goals*100:.1f}%）")
    print("  → 若下半场明显更多，说明进球强度随时间上升，支持时变泊松建模。")


# ---------------------------------------------------------------------------
# 2) 描述统计 + 相关性
# ---------------------------------------------------------------------------
def _team_rows(details: list):
    """把每场拆成两条球队记录：(进球, 射正差, 角球差, xG差, 控球差)。"""
    rows = []
    for m in details:
        hs, as_ = m["home_stats"], m["away_stats"]
        if m["hg"] is None or m["ag"] is None:
            continue

        def diff(a, b):
            if a is None or b is None:
                return None
            return a - b

        # 主队视角
        rows.append({
            "goals": m["hg"],
            "sot": diff(hs.get("shots_on"), as_.get("shots_on")),
            "corner": diff(hs.get("corners"), as_.get("corners")),
            "xg": diff(hs.get("xg"), as_.get("xg")),
            "poss": diff(hs.get("possession"), as_.get("possession")),
            "is_home": 1,
        })
        # 客队视角（差值取反）
        rows.append({
            "goals": m["ag"],
            "sot": diff(as_.get("shots_on"), hs.get("shots_on")),
            "corner": diff(as_.get("corners"), hs.get("corners")),
            "xg": diff(as_.get("xg"), hs.get("xg")),
            "poss": diff(as_.get("possession"), hs.get("possession")),
            "is_home": 0,
        })
    return rows


def describe(details: list) -> None:
    print("\n" + "=" * 60)
    print("【2. 描述统计与相关性】")
    print("=" * 60)

    hg = np.array([m["hg"] for m in details if m["hg"] is not None])
    ag = np.array([m["ag"] for m in details if m["ag"] is not None])
    print(f"  主队场均进球 {hg.mean():.2f}，客队场均进球 {ag.mean():.2f}")
    print(f"  主场优势（主-客）：{hg.mean() - ag.mean():+.2f} 球/场")

    rows = _team_rows(details)
    goals = np.array([r["goals"] for r in rows], dtype=float)
    print("\n  各特征差值与进球数的皮尔逊相关系数：")
    for feat in ("sot", "corner", "xg", "poss"):
        vals = np.array([r[feat] if r[feat] is not None else np.nan for r in rows])
        mask = ~np.isnan(vals)
        if mask.sum() < 3:
            print(f"    {feat:8s}: 数据不足")
            continue
        r = np.corrcoef(vals[mask], goals[mask])[0, 1]
        print(f"    {feat:8s}: {r:+.3f}")
    print("  → 相关系数越大，说明该特征对进球越有预测力。")


# ---------------------------------------------------------------------------
# 3) 泊松回归校准 FEATURE_WEIGHTS
# ---------------------------------------------------------------------------
def poisson_regression(details: list) -> None:
    print("\n" + "=" * 60)
    print("【3. 泊松回归 —— 校准 FEATURE_WEIGHTS】")
    print("=" * 60)

    rows = _team_rows(details)
    # 只保留特征齐全的样本
    feats = ("sot", "corner", "xg", "poss")
    clean = [r for r in rows if all(r[f] is not None for f in feats)]
    if len(clean) < 8:
        print(f"  有效样本仅 {len(clean)} 条，太少，无法稳健回归。")
        return

    y = np.array([r["goals"] for r in clean], dtype=float)
    # 设计矩阵：截距 + is_home + 各特征差
    X = np.column_stack([
        np.ones(len(clean)),
        np.array([r["is_home"] for r in clean], dtype=float),
        np.array([r["sot"] for r in clean], dtype=float),
        np.array([r["corner"] for r in clean], dtype=float),
        np.array([r["xg"] for r in clean], dtype=float),
        np.array([r["poss"] for r in clean], dtype=float),
    ])
    names = ["截距", "主场", "sot", "corner", "xg", "possession"]

    beta = _fit_poisson(X, y)

    print(f"  有效样本 {len(clean)} 条，泊松回归（log 链接）系数：\n")
    print(f"  {'特征':12s}{'当前权重':>10s}{'回归拟合':>12s}")
    from models.poisson_live import FEATURE_WEIGHTS
    cur = {"sot": FEATURE_WEIGHTS["sot"], "corner": FEATURE_WEIGHTS["corner"],
           "xg": FEATURE_WEIGHTS["xg"], "possession": FEATURE_WEIGHTS["possession"]}
    for name, b in zip(names, beta):
        c = cur.get(name)
        cur_s = f"{c:.4f}" if c is not None else "—"
        print(f"  {name:12s}{cur_s:>10s}{b:>12.4f}")

    print("\n  解读：")
    print("  - 'xg' 系数应最大（信息量最强），若明显高于当前 0.30，可上调。")
    print("  - 'sot' 系数为正且显著，说明射正差确实推高进球。")
    print("  - 系数含义：per-90 的 log(λ) 每单位特征差的增量，")
    print("    与 poisson_live._adjust_lambda 里的 delta 计算口径一致。")
    print(f"  - 主场优势系数 {beta[1]:+.3f}（>0 印证主场进球更多）。")


def _fit_poisson(X: np.ndarray, y: np.ndarray, iters: int = 50) -> np.ndarray:
    """用 IRLS（迭代重加权最小二乘）拟合泊松回归 log(λ)=Xβ。"""
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = X @ beta
        eta = np.clip(eta, -10, 10)
        mu = np.exp(eta)
        # 加权最小二乘更新
        W = np.diag(mu)
        z = eta + (y - mu) / np.clip(mu, 1e-6, None)
        try:
            beta_new = np.linalg.solve(X.T @ W @ X + 1e-6 * np.eye(X.shape[1]),
                                       X.T @ W @ z)
        except np.linalg.LinAlgError:
            break
        if np.max(np.abs(beta_new - beta)) < 1e-6:
            beta = beta_new
            break
        beta = beta_new
    return beta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    details = load(season)
    print(f"分析赛季 {season}，共 {len(details)} 场比赛")
    goal_timing(details)
    describe(details)
    poisson_regression(details)
    print("\n完成。")
