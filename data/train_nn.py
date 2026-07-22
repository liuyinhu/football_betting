"""训练并验证「神经网络版」中超胜平负预测器。

与 Dixon-Coles(data/train_strength.py + data/validate.py) 的关系：
  - **共享同一份信息**：特征全部由已训练的攻防强度模型推导得到,
    包括主客攻防强度、主场优势、以及泊松解析式给出的赛前 lambda。
    这样对比才公平——差异只在「泊松解析式」vs「神经网络拟合」。
  - **同样的 walk-forward 验证**：默认 2024+2025 训练、2026 测试,
    指标(准确率 / log-loss / 混淆矩阵)与 validate.py 完全一致, 可直接对照。

用法:
    # 训练并保存神经网络模型(默认: 按日期切分, 温和时间权重, 最优配置)
    python3 -m data.train_nn

    # walk-forward 验证 + 与 Dixon-Coles 并排对比(按赛季)
    python3 -m data.train_nn --validate
    python3 -m data.train_nn --validate 2024,2025 2026

    # ★ 按日期切分验证: 训练"最近30场之前"全部数据(温和时间权重),
    #   预测 2026 最近 30 场。可指定场数与时间权重半衰期(天)。
    python3 -m data.train_nn --recent
    python3 -m data.train_nn --recent 30
    python3 -m data.train_nn --recent 30 --half-life 450
    python3 -m data.train_nn --recent 30 --half-life 0   # 0=等权(无时间权重)

    # ★ 进球数预测(泊松回归): 训练目标=主/客队进球数, 输出更丰富的评估
    #   (进球 MAE/RMSE + 衍生胜平负准确率 + 大小球命中率), 与 DC 并排。
    python3 -m data.train_nn --goals            # 验证, 默认最近50场/等权
    python3 -m data.train_nn --goals 50 --half-life 450
    python3 -m data.train_nn --goals --save     # 训练并保存进球回归模型
"""
from __future__ import annotations
import math
from collections import Counter
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np

from .api_football_loader import load_all_matches, load_all_details, FixtureData
from .csl_loader import Match
from .train_strength import train as train_strength, expected_lambdas
from models.nn_predictor import (MLPClassifier, MLPPoissonRegressor,
                                 CLASSES, MODEL_PATH, POISSON_MODEL_PATH)


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------
def _features_for(model: Dict, home: str, away: str) -> List[float] | None:
    """基于攻防强度模型, 为一场对阵构造特征向量。返回 None 表示球队缺失。"""
    teams = model["teams"]
    if home not in teams or away not in teams:
        return None
    th, ta = teams[home], teams[away]
    ha = model["home_adv"]

    atk_h, dfc_h = th["attack"], th["defence"]
    atk_a, dfc_a = ta["attack"], ta["defence"]

    # 泊松解析式给出的赛前 lambda(与 Dixon-Coles 同源)
    lam_h, lam_a = expected_lambdas(model, home, away)

    return [
        atk_h, dfc_h,                    # 主队攻防
        atk_a, dfc_a,                    # 客队攻防
        atk_h - dfc_a,                   # 主队进攻 vs 客队防守
        atk_a - dfc_h,                   # 客队进攻 vs 主队防守
        (atk_h - dfc_h) - (atk_a - dfc_a),  # 综合实力差
        ha,                              # 主场优势
        lam_h, lam_a,                    # 赛前预期进球
        lam_h - lam_a,                   # 预期进球差
        math.log(lam_h / lam_a),         # 对数进球比
    ]


N_FEATURES = 12


def _label(m: Match) -> int:
    if m.hg > m.ag:
        return 0  # H
    if m.hg == m.ag:
        return 1  # D
    return 2      # A


def build_dataset(model: Dict, matches: List[Match]
                  ) -> Tuple[np.ndarray, np.ndarray]:
    """把比赛列表转成 (X, y)。跳过强度模型里没有的球队。"""
    X, y = [], []
    for m in matches:
        feats = _features_for(model, m.home, m.away)
        if feats is None:
            continue
        X.append(feats)
        y.append(_label(m))
    return np.array(X, dtype=float), np.array(y, dtype=int)


# ---------------------------------------------------------------------------
# 训练
# ---------------------------------------------------------------------------
def _matches_for(years):
    allm = load_all_matches()
    return [m for m in allm if m.season in years]


# ---------------------------------------------------------------------------
# 按日期切分 + 时间权重(比赛越近权重越大)
# ---------------------------------------------------------------------------
def _to_match(d: FixtureData) -> Match:
    return Match(d.season, d.home, d.away, int(d.hg), int(d.ag))


def _parse_day(date_str: str) -> datetime:
    """把 API 日期(如 2026-05-31T19:35:00+00:00)解析成无时区 datetime。"""
    return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)


def split_recent(n_test: int = 30) -> Tuple[List[FixtureData], List[FixtureData]]:
    """按比赛日期切分：测试集 = 2026 赛季最近 n_test 场, 训练集 = 其余全部。"""
    alld = [d for d in load_all_details()
            if d.hg is not None and d.ag is not None]
    alld.sort(key=lambda d: d.date)
    d26 = [d for d in alld if d.season == 2026]
    if len(d26) < n_test:
        raise SystemExit(f"2026 赛季只有 {len(d26)} 场, 不足 {n_test} 场。")
    test = d26[-n_test:]
    test_ids = {d.fixture_id for d in test}
    train = [d for d in alld if d.fixture_id not in test_ids]
    return train, test


def _time_weights(days: List[datetime], half_life_days: float | None):
    """按比赛日期算指数时间权重: exp(-ln2/半衰期 * 天数差)。
    half_life_days=None 时返回 None(等权)。基准=最新一场。"""
    if half_life_days is None:
        return None
    ref = max(days)
    decay = math.log(2) / half_life_days
    age = np.array([(ref - dd).days for dd in days], dtype=float)
    return np.exp(-decay * age)


def train_nn_recent(n_test: int = 30,
                    half_life_days: float | None = 450.0,
                    hidden_sizes=(8,),
                    epochs: int = 50,
                    verbose: bool = False
                    ) -> Tuple[MLPClassifier, Dict, List[FixtureData]]:
    """按日期切分训练神经网络：用测试集之前的全部数据 + 温和时间权重。

    返回 (分类器, 强度模型, 测试集明细)。
    默认 half_life=450 天(经 30 种子扫描最优)：近期比赛权重更高, 但不过度偏重。
    """
    train_det, test_det = split_recent(n_test)
    train_matches = [_to_match(d) for d in train_det]
    strength = train_strength(train_matches)

    X, y, days = [], [], []
    for d in train_det:
        feats = _features_for(strength, d.home, d.away)
        if feats is None:
            continue
        X.append(feats)
        y.append(_label(_to_match(d)))
        days.append(_parse_day(d.date))
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=int)

    sw = _time_weights(days, half_life_days)
    hl = f"半衰期 {half_life_days:.0f} 天" if half_life_days else "等权(无时间权重)"
    print(f"神经网络训练集: {len(X)} 场, {N_FEATURES} 维特征   时间权重: {hl}")

    clf = MLPClassifier(hidden_sizes=hidden_sizes, epochs=epochs,
                        val_frac=0.0, patience=10**9)
    clf.fit(X, y, sample_weight=sw, verbose=verbose)
    return clf, strength, test_det


def validate_recent(n_test: int = 30,
                    half_life_days: float | None = 450.0,
                    n_seed: int = 10) -> None:
    """按日期切分验证：训练测试集之前的全部数据, 预测 2026 最近 n_test 场。

    多种子平均以消除随机初始化噪声, 并与 Dixon-Coles 并排对比。
    """
    train_det, test_det = split_recent(n_test)
    train_matches = [_to_match(d) for d in train_det]
    strength = train_strength(train_matches)

    # 构造训练数据(含日期用于时间权重)
    X, y, days = [], [], []
    for d in train_det:
        feats = _features_for(strength, d.home, d.away)
        if feats is None:
            continue
        X.append(feats)
        y.append(_label(_to_match(d)))
        days.append(_parse_day(d.date))
    X = np.array(X, dtype=float)
    y = np.array(y, dtype=int)
    sw = _time_weights(days, half_life_days)

    # 多种子训练 NN
    nn_accs, nn_lls = [], []
    nn_conf = Counter()
    for s in range(n_seed):
        clf = MLPClassifier(hidden_sizes=(8,), epochs=50,
                            val_frac=0.0, patience=10**9, seed=s)
        clf.fit(X, y, sample_weight=sw)
        n = c = 0
        ll = 0.0
        for d in test_det:
            f = _features_for(strength, d.home, d.away)
            if f is None:
                continue
            a = _label(_to_match(d))
            p = clf.predict_proba(np.array([f], dtype=float))[0]
            n += 1
            c += (int(p.argmax()) == a)
            ll += -math.log(max(p[a], 1e-9))
            if s == 0:
                nn_conf[(CLASSES[a], CLASSES[int(p.argmax())])] += 1
        nn_accs.append(c / n)
        nn_lls.append(ll / n)

    # Dixon-Coles 并排(无随机性, 单次即可)
    dc_c = dc_ll = naive_c = dc_n = 0
    dc_ll = 0.0
    for d in test_det:
        f = _features_for(strength, d.home, d.away)
        if f is None:
            continue
        a = _label(_to_match(d))
        ph, pd, pa = _dixon_coles_probs(strength, d.home, d.away)
        probs = [ph, pd, pa]
        dc_n += 1
        dc_c += (int(np.argmax(probs)) == a)
        dc_ll += -math.log(max(probs[a], 1e-9))
        naive_c += (a == 0)

    hl = f"半衰期 {half_life_days:.0f} 天" if half_life_days else "等权"
    print("\n" + "=" * 60)
    print(f"按日期切分  训练 {len(X)} 场  →  测试 2026 最近 {n_test} 场")
    print(f"测试区间: {test_det[0].date[:10]} ~ {test_det[-1].date[:10]}   "
          f"时间权重: {hl}")
    print("=" * 60)
    print(f"{'指标':18s}{'神经网络(MLP)':>16s}{'Dixon-Coles':>16s}")
    print(f"{'准确率':18s}{np.mean(nn_accs):>15.2%} {dc_c / dc_n:>15.2%}")
    print(f"{'log-loss':18s}{np.mean(nn_lls):>16.4f}{dc_ll / dc_n:>16.4f}")
    print(f"{'基线(永远主胜)':18s}{naive_c / dc_n:>15.2%}{'—':>16s}")
    print(f"  (NN 为 {n_seed} 种子平均; log-loss 越低越好, 随机≈1.10)")

    print("\n神经网络混淆矩阵 (真实,预测, 首个种子):")
    for a in CLASSES:
        row = "  ".join(f"{p}:{nn_conf[(a, p)]:>3}" for p in CLASSES)
        print(f"  真实={a}  {row}")


def train_nn(train_years: List[int],
             hidden_sizes=(16, 8),
             epochs: int = 400,
             verbose: bool = False
             ) -> Tuple[MLPClassifier, Dict]:
    """先用 train_strength 拟合攻防强度(作为特征来源), 再训练 MLP。"""
    train_matches = _matches_for(train_years)
    # 复用现有 Dixon-Coles 强度作为特征提取器
    strength = train_strength(train_matches)

    X, y = build_dataset(strength, train_matches)
    print(f"神经网络训练集: {len(X)} 场, {N_FEATURES} 维特征")

    clf = MLPClassifier(hidden_sizes=hidden_sizes, epochs=epochs)
    clf.fit(X, y, verbose=verbose)
    return clf, strength


# ===========================================================================
# 进球数预测(泊松回归): 训练目标 = 主/客队实际进球数
# ===========================================================================
def _probs_from_lambda(lam_h: float, lam_a: float, max_goals: int = 8):
    """由 λ_home, λ_away 用泊松分布反推 (胜平负概率, 总进球期望)。"""
    from scipy.stats import poisson
    ph = pd = pa = 0.0
    for i in range(max_goals):
        pi = poisson.pmf(i, lam_h)
        for j in range(max_goals):
            p = pi * poisson.pmf(j, lam_a)
            if i > j:
                ph += p
            elif i == j:
                pd += p
            else:
                pa += p
    tot = ph + pd + pa
    return ph / tot, pd / tot, pa / tot


def build_dataset_goals(strength: Dict, details: List[FixtureData]):
    """把比赛明细转成 (X, Y, days)。Y[:,0]=主队进球, Y[:,1]=客队进球。"""
    X, Y, days = [], [], []
    for d in details:
        feats = _features_for(strength, d.home, d.away)
        if feats is None:
            continue
        X.append(feats)
        Y.append([int(d.hg), int(d.ag)])
        days.append(_parse_day(d.date))
    return (np.array(X, dtype=float), np.array(Y, dtype=float), days)


def train_goals_recent(n_test: int = 50,
                       half_life_days: float | None = None,
                       hidden_sizes=(8,),
                       epochs: int = 300,
                       verbose: bool = False
                       ) -> Tuple[MLPPoissonRegressor, Dict, List[FixtureData]]:
    """按日期切分训练进球数泊松回归。默认等权(经实验最优)。"""
    train_det, test_det = split_recent(n_test)
    strength = train_strength([_to_match(d) for d in train_det])
    X, Y, days = build_dataset_goals(strength, train_det)
    sw = _time_weights(days, half_life_days)
    hl = f"半衰期 {half_life_days:.0f} 天" if half_life_days else "等权"
    print(f"进球回归训练集: {len(X)} 场, {N_FEATURES} 维特征   时间权重: {hl}")
    reg = MLPPoissonRegressor(hidden_sizes=hidden_sizes, epochs=epochs,
                              val_frac=0.0, patience=10**9)
    reg.fit(X, Y, sample_weight=sw, verbose=verbose)
    return reg, strength, test_det


def train_goals_all(half_life_days: float | None = None,
                    hidden_sizes=(8,),
                    epochs: int = 300,
                    verbose: bool = False
                    ) -> Tuple[MLPPoissonRegressor, Dict]:
    """用【全部已有数据】训练进球数泊松回归(不留测试集), 用于正式预测未来比赛。

    同时保存进球回归模型(nn_goals.json)和攻防强度模型(train_strength 的
    MODEL_PATH), 保证预测时特征提取器与训练时一致。
    """
    alld = [d for d in load_all_details()
            if d.hg is not None and d.ag is not None]
    alld.sort(key=lambda d: d.date)
    strength = train_strength([_to_match(d) for d in alld])
    X, Y, days = build_dataset_goals(strength, alld)
    sw = _time_weights(days, half_life_days)
    hl = f"半衰期 {half_life_days:.0f} 天" if half_life_days else "等权"
    seasons = sorted({d.season for d in alld})
    print(f"进球回归训练集(全量): {len(X)} 场, 赛季 {seasons}, "
          f"{N_FEATURES} 维特征   时间权重: {hl}")
    reg = MLPPoissonRegressor(hidden_sizes=hidden_sizes, epochs=epochs,
                              val_frac=0.0, patience=10**9)
    reg.fit(X, Y, sample_weight=sw, verbose=verbose)
    return reg, strength


def validate_goals(n_test: int = 50,
                   half_life_days: float | None = None,
                   n_seed: int = 10) -> None:
    """按日期切分验证进球数回归, 多维度评估并与 Dixon-Coles 并排对比。

    评估指标:
      - 进球数 MAE / RMSE (回归精度, 越低越好)
      - 衍生胜平负准确率 (由 λ 反推 argmax)
      - 大小球 2.5 命中率 (由 λ_h+λ_a 判大小)
      - 胜平负 log-loss
    """
    train_det, test_det = split_recent(n_test)
    strength = train_strength([_to_match(d) for d in train_det])
    X, Y, days = build_dataset_goals(strength, train_det)
    sw = _time_weights(days, half_life_days)

    # 真实值
    test_rows = [(d, _features_for(strength, d.home, d.away)) for d in test_det]
    test_rows = [(d, f) for d, f in test_rows if f is not None]
    yh = np.array([int(d.hg) for d, _ in test_rows], dtype=float)
    ya = np.array([int(d.ag) for d, _ in test_rows], dtype=float)
    Xt = np.array([f for _, f in test_rows], dtype=float)
    n_test_eff = len(test_rows)

    # --- 多种子训练 NN 泊松回归, 累加指标 ---
    nn_mae = nn_rmse = nn_acc = nn_ou = nn_ll = 0.0
    for s in range(n_seed):
        reg = MLPPoissonRegressor(hidden_sizes=(8,), epochs=300,
                                  val_frac=0.0, patience=10**9, seed=s)
        reg.fit(X, Y, sample_weight=sw)
        lam = reg.predict_lambda(Xt)  # (n, 2)
        lh, la = lam[:, 0], lam[:, 1]
        # 进球数误差(主+客各算一次)
        nn_mae += (np.abs(lh - yh).sum() + np.abs(la - ya).sum()) / (2 * n_test_eff)
        nn_rmse += math.sqrt(((lh - yh) ** 2 + (la - ya) ** 2).sum() / (2 * n_test_eff))
        # 衍生盘口
        for k in range(n_test_eff):
            ph, pd, pa = _probs_from_lambda(lh[k], la[k])
            probs = [ph, pd, pa]
            actual = 0 if yh[k] > ya[k] else (1 if yh[k] == ya[k] else 2)
            nn_acc += (int(np.argmax(probs)) == actual)
            nn_ll += -math.log(max(probs[actual], 1e-9))
            pred_over = (lh[k] + la[k]) > 2.5
            actual_over = (yh[k] + ya[k]) > 2.5
            nn_ou += (pred_over == actual_over)
    nn_mae /= n_seed; nn_rmse /= n_seed
    nn_acc /= (n_seed * n_test_eff); nn_ll /= (n_seed * n_test_eff)
    nn_ou /= (n_seed * n_test_eff)

    # --- Dixon-Coles 并排(无随机性) ---
    dc_mae = dc_rmse = dc_acc = dc_ou = dc_ll = 0.0
    for k, (d, _) in enumerate(test_rows):
        lh, la = expected_lambdas(strength, d.home, d.away)
        dc_mae += (abs(lh - yh[k]) + abs(la - ya[k])) / (2 * n_test_eff)
        dc_rmse += ((lh - yh[k]) ** 2 + (la - ya[k]) ** 2) / (2 * n_test_eff)
        ph, pd, pa = _probs_from_lambda(lh, la)
        probs = [ph, pd, pa]
        actual = 0 if yh[k] > ya[k] else (1 if yh[k] == ya[k] else 2)
        dc_acc += (int(np.argmax(probs)) == actual)
        dc_ll += -math.log(max(probs[actual], 1e-9))
        dc_ou += (((lh + la) > 2.5) == ((yh[k] + ya[k]) > 2.5))
    dc_rmse = math.sqrt(dc_rmse)
    dc_acc /= n_test_eff; dc_ll /= n_test_eff; dc_ou /= n_test_eff

    # 基线: 用训练集平均进球数预测所有比赛
    base_h, base_a = Y[:, 0].mean(), Y[:, 1].mean()
    base_mae = (np.abs(base_h - yh).sum() + np.abs(base_a - ya).sum()) / (2 * n_test_eff)

    hl = f"半衰期 {half_life_days:.0f} 天" if half_life_days else "等权"
    print("\n" + "=" * 62)
    print(f"进球数预测(泊松回归)   训练 {len(X)} 场  →  测试最近 {n_test} 场")
    print(f"测试区间: {test_det[0].date[:10]} ~ {test_det[-1].date[:10]}   "
          f"时间权重: {hl}")
    print("=" * 62)
    print(f"{'指标':22s}{'神经网络(泊松)':>16s}{'Dixon-Coles':>16s}")
    print(f"{'进球 MAE(↓)':22s}{nn_mae:>16.4f}{dc_mae:>16.4f}")
    print(f"{'进球 RMSE(↓)':22s}{nn_rmse:>16.4f}{dc_rmse:>16.4f}")
    print(f"{'胜平负准确率(↑)':20s}{nn_acc:>15.2%} {dc_acc:>15.2%}")
    print(f"{'大小球2.5准确率(↑)':19s}{nn_ou:>15.2%} {dc_ou:>15.2%}")
    print(f"{'胜平负log-loss(↓)':20s}{nn_ll:>16.4f}{dc_ll:>16.4f}")
    print(f"  (NN 为 {n_seed} 种子平均; 基线[均值预测]MAE={base_mae:.4f})")
    print(f"  训练集场均进球: 主 {base_h:.2f} / 客 {base_a:.2f}")


# ---------------------------------------------------------------------------
# 验证(与 validate.py 指标一致)
# ---------------------------------------------------------------------------
def _dixon_coles_probs(strength: Dict, home: str, away: str):
    """Dixon-Coles 泊松解析式的胜平负概率, 用于并排对比。"""
    from scipy.stats import poisson
    lam_h, lam_a = expected_lambdas(strength, home, away)
    ph = pd = pa = 0.0
    for i in range(8):
        for j in range(8):
            p = poisson.pmf(i, lam_h) * poisson.pmf(j, lam_a)
            if i > j: ph += p
            elif i == j: pd += p
            else: pa += p
    tot = ph + pd + pa
    return ph / tot, pd / tot, pa / tot


def walk_forward(train_years: List[int], test_years: List[int]) -> None:
    clf, strength = train_nn(train_years)

    test_matches = _matches_for(test_years)

    # 神经网络指标
    nn_n = nn_correct = 0
    nn_logloss = 0.0
    nn_conf = Counter()
    # Dixon-Coles 指标(并排)
    dc_correct = 0
    dc_logloss = 0.0
    naive_correct = 0

    for m in test_matches:
        feats = _features_for(strength, m.home, m.away)
        if feats is None:
            continue
        actual = _label(m)
        actual_c = CLASSES[actual]

        # --- 神经网络 ---
        proba = clf.predict_proba(np.array([feats], dtype=float))[0]
        pred = int(proba.argmax())
        nn_n += 1
        if pred == actual:
            nn_correct += 1
        nn_conf[(actual_c, CLASSES[pred])] += 1
        nn_logloss += -math.log(max(proba[actual], 1e-9))

        # --- Dixon-Coles(同一强度) ---
        ph, pd, pa = _dixon_coles_probs(strength, m.home, m.away)
        dc_probs = [ph, pd, pa]
        if int(np.argmax(dc_probs)) == actual:
            dc_correct += 1
        dc_logloss += -math.log(max(dc_probs[actual], 1e-9))

        if actual_c == "H":
            naive_correct += 1

    if nn_n == 0:
        print("无可评估的比赛(测试赛季球队不在训练集中?)")
        return

    print("\n" + "=" * 56)
    print(f"验证集: {test_years}   可评估 {nn_n} 场")
    print("=" * 56)
    print(f"{'指标':16s}{'神经网络(MLP)':>16s}{'Dixon-Coles':>16s}")
    print(f"{'准确率':16s}{nn_correct / nn_n:>15.2%} {dc_correct / nn_n:>15.2%}")
    print(f"{'log-loss':16s}{nn_logloss / nn_n:>16.4f}{dc_logloss / nn_n:>16.4f}")
    print(f"{'基线(永远主胜)':16s}{naive_correct / nn_n:>15.2%}{'—':>16s}")
    print("  (log-loss 越低越好, 随机≈1.10)")

    print("\n神经网络混淆矩阵 (真实,预测):")
    for a in CLASSES:
        row = "  ".join(f"{p}:{nn_conf[(a, p)]:>3}" for p in CLASSES)
        print(f"  真实={a}  {row}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    if "--goals" in args:
        # 进球数预测(泊松回归): 默认按最近 50 场切分, 等权
        i = args.index("--goals")
        n_test = 50
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            n_test = int(args[i + 1])
        hl_raw = 0.0  # 默认等权
        if "--half-life" in args:
            j = args.index("--half-life")
            if j + 1 < len(args):
                hl_raw = float(args[j + 1])
        half_life = None if hl_raw <= 0 else hl_raw
        if "--save" in args:
            # 用全部已有数据训练(不留测试集), 用于正式预测未来比赛
            reg, strength = train_goals_all(half_life_days=half_life,
                                            verbose=True)
            reg.save()
            # 同时保存攻防强度模型, 保证预测时特征提取器与训练时完全一致
            from .train_strength import save as save_strength
            save_strength(strength)
            print(f"\n进球回归模型已保存: {POISSON_MODEL_PATH}")
            print(f"攻防强度模型已保存(供特征提取)")
            print(f"→ 现在可预测未来比赛比分:  python3 predict_score.py 主队 客队")
        else:
            validate_goals(n_test=n_test, half_life_days=half_life)
    elif "--recent" in args:
        # 按日期切分: 训练"最近 N 场之前"的全部数据 + 温和时间权重
        i = args.index("--recent")
        n_test = 30
        if i + 1 < len(args) and not args[i + 1].startswith("--"):
            n_test = int(args[i + 1])
        # --half-life 天数; 0 或负数表示等权(无时间权重)
        hl_raw = 450.0
        if "--half-life" in args:
            j = args.index("--half-life")
            if j + 1 < len(args):
                hl_raw = float(args[j + 1])
        half_life = None if hl_raw <= 0 else hl_raw
        validate_recent(n_test=n_test, half_life_days=half_life)
    elif "--validate" in args:
        rest = [a for a in args if a != "--validate"]
        if len(rest) >= 2:
            train_years = [int(x) for x in rest[0].split(",")]
            test_years = [int(x) for x in rest[1].split(",")]
        else:
            train_years = [2024, 2025]
            test_years = [2026]
        walk_forward(train_years, test_years)
    else:
        # 默认: 按日期切分(最近30场之前)+温和时间权重训练并保存 —— 最优配置
        clf, _, test_det = train_nn_recent(n_test=30, half_life_days=450.0,
                                           verbose=True)
        clf.save()
        print(f"\n神经网络模型已保存: {MODEL_PATH}")
        print(f"(训练用 2026 最近 30 场之前的全部数据 + 半衰期450天时间权重)")
