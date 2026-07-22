"""按「比赛日期」切分 + 逐场时间权重 的神经网络实验。

任务设定:
  - 测试集: 2026 赛季最近 30 场(按日期)
  - 训练集: 其余全部比赛(2023 全年 + 2024 全年 + 2025 全年 + 2026 剩余场次)
  - 时间权重: 比赛越接近"当下"权重越大, 指数衰减 exp(-decay * 天数差)
             基准 = 训练集里最新一场比赛的日期

用法:
    python3 -m data.experiment_time_weight
"""
from __future__ import annotations
import math
from collections import Counter
from datetime import datetime
from typing import List

import numpy as np

from .api_football_loader import load_all_details, FixtureData
from .csl_loader import Match
from .train_strength import train as train_strength, expected_lambdas
from .train_nn import _features_for, _label
from models.nn_predictor import MLPClassifier, CLASSES

N_TEST = 30


def _to_match(d: FixtureData) -> Match:
    return Match(d.season, d.home, d.away, int(d.hg), int(d.ag))


def _parse_day(date_str: str) -> datetime:
    # date 形如 "2026-05-31T19:35:00+00:00"
    return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)


def build_split():
    """返回 (train_details, test_details), 都带日期, 已按日期升序。"""
    alld = [d for d in load_all_details() if d.hg is not None and d.ag is not None]
    alld.sort(key=lambda d: d.date)
    d26 = [d for d in alld if d.season == 2026]
    test = d26[-N_TEST:]
    test_ids = {d.fixture_id for d in test}
    train = [d for d in alld if d.fixture_id not in test_ids]
    return train, test


def build_dataset_with_dates(strength, details: List[FixtureData]):
    """构造 (X, y, days) —— days 为每场比赛的 datetime, 用于算时间权重。"""
    X, y, days = [], [], []
    for d in details:
        feats = _features_for(strength, d.home, d.away)
        if feats is None:
            continue
        X.append(feats)
        y.append(_label(_to_match(d)))
        days.append(_parse_day(d.date))
    return np.array(X, dtype=float), np.array(y, dtype=int), days


def run_config(name, X, y, days, strength, test, decay=None, n_seed=10):
    """decay=None 表示等权; 否则按天数指数衰减。多种子平均。"""
    sw = None
    if decay is not None:
        ref = max(days)  # 训练集最新一场为基准
        age_days = np.array([(ref - dd).days for dd in days], dtype=float)
        sw = np.exp(-decay * age_days)

    accs, lls = [], []
    conf_sum = Counter()
    for s in range(n_seed):
        clf = MLPClassifier(hidden_sizes=(8,), epochs=50,
                            val_frac=0.0, patience=10**9, seed=s)
        clf.fit(X, y, sample_weight=sw)
        n = c = 0
        ll = 0.0
        for d in test:
            f = _features_for(strength, d.home, d.away)
            if f is None:
                continue
            a = _label(_to_match(d))
            p = clf.predict_proba(np.array([f], dtype=float))[0]
            n += 1
            c += (int(p.argmax()) == a)
            ll += -math.log(max(p[a], 1e-9))
            if s == 0:
                conf_sum[(CLASSES[a], CLASSES[int(p.argmax())])] += 1
        accs.append(c / n)
        lls.append(ll / n)
    print(f"{name:32s} {np.mean(accs)*100:6.2f}%  {np.mean(lls):.4f}")
    return conf_sum


if __name__ == "__main__":
    train_det, test_det = build_split()
    print(f"训练集 {len(train_det)} 场 (2023/2024/2025 全年 + 2026 早期)")
    print(f"测试集 {len(test_det)} 场 (2026 最近 {N_TEST} 场, "
          f"{test_det[0].date[:10]} ~ {test_det[-1].date[:10]})\n")

    # 强度模型(特征来源)用训练集拟合
    train_matches = [_to_match(d) for d in train_det]
    strength = train_strength(train_matches)

    X, y, days = build_dataset_with_dates(strength, train_det)
    print(f"有效训练样本 {len(X)} 场, {X.shape[1]} 维特征\n")

    print(f"{'方案 (10 种子平均)':32s} {'准确率':>6s}  {'log-loss':>8s}")
    print("-" * 52)
    run_config("无时间权重(等权基线)", X, y, days, strength, test_det, decay=None)
    # 半衰期换算: decay = ln2 / 半衰期(天)
    for half in [365, 180, 90, 45]:
        dcy = math.log(2) / half
        run_config(f"时间衰减 半衰期{half}天", X, y, days, strength,
                   test_det, decay=dcy)

    print("\n注: 半衰期=N天 表示 N 天前的比赛权重减半; 越小越偏重近期。")
