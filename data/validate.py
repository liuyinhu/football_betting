"""用 walk-forward(逐步前推)方式验证训练好的强度模型。

对测试赛季的每场比赛, 只用之前赛季的数据训练模型来预测胜平负, 然后衡量：
  - 准确率(概率最高的结果是否发生)
  - 对数损失 log-loss
  - 与朴素基线(永远猜主胜)对比

运行:
    python3 -m data.validate
"""
from __future__ import annotations
import math
from collections import Counter

from scipy.stats import poisson

from .csl_loader import load_matches
from .train_strength import train, expected_lambdas


def outcome_probs(lam_h: float, lam_a: float, max_g: int = 8):
    ph = pd = pa = 0.0
    for i in range(max_g):
        for j in range(max_g):
            p = poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    tot = ph + pd + pa
    return ph / tot, pd / tot, pa / tot


def walk_forward(train_years, test_years):
    train_matches = load_matches(train_years)
    model = train(train_matches)

    test_matches = load_matches(test_years)
    n = correct = 0
    logloss = 0.0
    naive_correct = 0
    conf = Counter()

    for m in test_matches:
        try:
            lam_h, lam_a = expected_lambdas(model, m.home, m.away)
        except KeyError:
            continue  # 该队未在训练集中出现
        ph, pd, pa = outcome_probs(lam_h, lam_a)

        actual = "H" if m.hg > m.ag else ("D" if m.hg == m.ag else "A")
        pred = max([("H", ph), ("D", pd), ("A", pa)], key=lambda x: x[1])[0]

        n += 1
        if pred == actual:
            correct += 1
        conf[(actual, pred)] += 1
        p_actual = {"H": ph, "D": pd, "A": pa}[actual]
        logloss += -math.log(max(p_actual, 1e-9))
        if actual == "H":
            naive_correct += 1

    print("\n" + "=" * 50)
    print(f"验证集: {test_years}  可评估 {n} 场")
    print(f"模型准确率 (取最高概率结果): {correct / n:.2%}")
    print(f"基线准确率 (永远猜主胜)   : {naive_correct / n:.2%}")
    print(f"平均对数损失 log-loss     : {logloss / n:.4f}  (越低越好, 随机≈1.10)")
    print("\n混淆 (真实,预测):")
    for actual in "HDA":
        row = "  ".join(f"{p}:{conf[(actual, p)]:>3}" for p in "HDA")
        print(f"  真实={actual}  {row}")


if __name__ == "__main__":
    import sys
    # 默认: 近几年训练(2023-2024) 测试(2025)
    if len(sys.argv) >= 3:
        # 例如 python -m data.validate 2023,2024 2025
        train_years = [int(x) for x in sys.argv[1].split(",")]
        test_years = [int(x) for x in sys.argv[2].split(",")]
    else:
        train_years = [2023, 2024]
        test_years = [2025]
    walk_forward(train_years, test_years)
