"""纯 NumPy 实现的足球预测神经网络(零新增依赖, 不引入 torch/tf)。

包含两个模型, 共享同一份特征(来自 Dixon-Coles 攻防强度), 与 DC 公平对比:

  1. MLPClassifier       —— 胜平负三分类(H/D/A), softmax + 交叉熵。
  2. MLPPoissonRegressor —— 预测主客队进球数 λ, 泊松回归(输出 logλ, NLL 损失)。
     由 λ 可反推胜平负/大小球/精确比分等所有盘口, 评估维度更丰富。

两者均用: 特征标准化 + 小批量 Adam + L2 正则 + 内部验证集 early stopping。
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "nn_strength.json"

# 类别顺序固定为 主胜 H / 平 D / 客胜 A
CLASSES = ["H", "D", "A"]


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


class MLPClassifier:
    """纯 NumPy 的两隐藏层 MLP + Adam 优化。"""

    def __init__(self,
                 hidden_sizes: Tuple[int, ...] = (8,),
                 lr: float = 0.01,
                 l2: float = 3e-3,
                 epochs: int = 300,
                 batch_size: int = 64,
                 seed: int = 42,
                 val_frac: float = 0.2,
                 patience: int = 30):
        self.hidden_sizes = tuple(hidden_sizes)
        self.lr = lr
        self.l2 = l2
        self.epochs = epochs
        self.batch_size = batch_size
        self.seed = seed
        self.val_frac = val_frac
        self.patience = patience
        # 参数在 fit 时初始化
        self.weights: List[np.ndarray] = []
        self.biases: List[np.ndarray] = []
        # 标准化用的均值/方差
        self.mu: np.ndarray | None = None
        self.sigma: np.ndarray | None = None

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def _init_params(self, n_in: int, n_out: int) -> None:
        rng = np.random.default_rng(self.seed)
        sizes = [n_in, *self.hidden_sizes, n_out]
        self.weights = []
        self.biases = []
        for a, b in zip(sizes[:-1], sizes[1:]):
            # He 初始化(适配 ReLU)
            self.weights.append(rng.normal(0, math.sqrt(2.0 / a), size=(a, b)))
            self.biases.append(np.zeros(b))

    # ------------------------------------------------------------------
    # 前向传播
    # ------------------------------------------------------------------
    def _forward(self, x: np.ndarray):
        """返回 (各层激活值列表, 各层线性输出列表)。最后一层是 softmax。"""
        acts = [x]
        zs = []
        h = x
        n_layers = len(self.weights)
        for i in range(n_layers):
            z = h @ self.weights[i] + self.biases[i]
            zs.append(z)
            if i < n_layers - 1:
                h = _relu(z)
            else:
                h = _softmax(z)
            acts.append(h)
        return acts, zs

    # ------------------------------------------------------------------
    # 训练
    # ------------------------------------------------------------------
    def fit(self, X: np.ndarray, y: np.ndarray,
            sample_weight: np.ndarray | None = None,
            verbose: bool = False) -> "MLPClassifier":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        n, n_in = X.shape
        n_out = len(CLASSES)

        # 特征标准化
        self.mu = X.mean(axis=0)
        self.sigma = X.std(axis=0) + 1e-8
        Xs = (X - self.mu) / self.sigma

        # one-hot 标签
        Y = np.zeros((n, n_out))
        Y[np.arange(n), y] = 1.0

        if sample_weight is None:
            sw = np.ones(n)
        else:
            sw = np.asarray(sample_weight, dtype=float)
        sw = sw / sw.mean()  # 归一化到均值 1

        self._init_params(n_in, n_out)

        # 划分内部验证集用于 early stopping(小数据必需, 防过拟合)
        rng = np.random.default_rng(self.seed)
        val_mask = np.zeros(n, dtype=bool)
        n_val = int(round(n * self.val_frac))
        if 0 < n_val < n:
            val_idx = rng.choice(n, size=n_val, replace=False)
            val_mask[val_idx] = True
        tr_idx = np.where(~val_mask)[0]
        va_idx = np.where(val_mask)[0]

        # Adam 状态
        mW = [np.zeros_like(w) for w in self.weights]
        vW = [np.zeros_like(w) for w in self.weights]
        mB = [np.zeros_like(b) for b in self.biases]
        vB = [np.zeros_like(b) for b in self.biases]
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        t = 0

        best_val = math.inf
        best_params = None
        wait = 0

        for epoch in range(self.epochs):
            perm = rng.permutation(tr_idx)
            for start in range(0, len(perm), self.batch_size):
                idx = perm[start:start + self.batch_size]
                xb, yb, wb = Xs[idx], Y[idx], sw[idx]
                t += 1
                gW, gB = self._backward(xb, yb, wb)
                # Adam 更新
                for i in range(len(self.weights)):
                    mW[i] = beta1 * mW[i] + (1 - beta1) * gW[i]
                    vW[i] = beta2 * vW[i] + (1 - beta2) * (gW[i] ** 2)
                    mB[i] = beta1 * mB[i] + (1 - beta1) * gB[i]
                    vB[i] = beta2 * vB[i] + (1 - beta2) * (gB[i] ** 2)
                    mW_hat = mW[i] / (1 - beta1 ** t)
                    vW_hat = vW[i] / (1 - beta2 ** t)
                    mB_hat = mB[i] / (1 - beta1 ** t)
                    vB_hat = vB[i] / (1 - beta2 ** t)
                    self.weights[i] -= self.lr * mW_hat / (np.sqrt(vW_hat) + eps)
                    self.biases[i] -= self.lr * mB_hat / (np.sqrt(vB_hat) + eps)

            # early stopping: 用内部验证集 log-loss 监控
            if len(va_idx) > 0:
                val_loss = self._loss(Xs[va_idx], Y[va_idx], sw[va_idx])
                if val_loss < best_val - 1e-5:
                    best_val = val_loss
                    best_params = ([w.copy() for w in self.weights],
                                   [b.copy() for b in self.biases])
                    wait = 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        if verbose:
                            print(f"  early stop @ epoch {epoch + 1}, "
                                  f"best val loss={best_val:.4f}")
                        break

            if verbose and (epoch + 1) % 50 == 0:
                loss = self._loss(Xs[tr_idx], Y[tr_idx], sw[tr_idx])
                print(f"  epoch {epoch + 1:4d}/{self.epochs}  "
                      f"train={loss:.4f}  val={best_val:.4f}")

        # 回滚到验证集最优参数
        if best_params is not None:
            self.weights, self.biases = best_params
        return self

    def _backward(self, xb, yb, wb):
        """一个 mini-batch 的反向传播, 返回各层梯度。"""
        acts, zs = self._forward(xb)
        m = xb.shape[0]
        wcol = wb.reshape(-1, 1)

        gW = [None] * len(self.weights)
        gB = [None] * len(self.biases)

        # 输出层: softmax + 交叉熵 -> delta = (p - y) * 样本权重
        delta = (acts[-1] - yb) * wcol / m
        for i in reversed(range(len(self.weights))):
            gW[i] = acts[i].T @ delta + self.l2 * self.weights[i]
            gB[i] = delta.sum(axis=0)
            if i > 0:
                # 反传到上一层, 经过 ReLU 导数
                dh = delta @ self.weights[i].T
                dh[zs[i - 1] <= 0] = 0.0
                delta = dh
        return gW, gB

    def _loss(self, Xs, Y, sw) -> float:
        acts, _ = self._forward(Xs)
        p = np.clip(acts[-1], 1e-9, 1.0)
        ce = -(Y * np.log(p)).sum(axis=1)
        reg = self.l2 / 2 * sum((w ** 2).sum() for w in self.weights)
        return float((sw * ce).mean() + reg / len(Xs))

    # ------------------------------------------------------------------
    # 预测
    # ------------------------------------------------------------------
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        Xs = (X - self.mu) / self.sigma
        acts, _ = self._forward(Xs)
        return acts[-1]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.predict_proba(X).argmax(axis=1)

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "hidden_sizes": list(self.hidden_sizes),
            "lr": self.lr,
            "l2": self.l2,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "seed": self.seed,
            "val_frac": self.val_frac,
            "patience": self.patience,
            "weights": [w.tolist() for w in self.weights],
            "biases": [b.tolist() for b in self.biases],
            "mu": self.mu.tolist() if self.mu is not None else None,
            "sigma": self.sigma.tolist() if self.sigma is not None else None,
            "classes": CLASSES,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MLPClassifier":
        obj = cls(hidden_sizes=tuple(d["hidden_sizes"]), lr=d["lr"],
                  l2=d["l2"], epochs=d["epochs"],
                  batch_size=d["batch_size"], seed=d["seed"],
                  val_frac=d.get("val_frac", 0.2),
                  patience=d.get("patience", 30))
        obj.weights = [np.array(w) for w in d["weights"]]
        obj.biases = [np.array(b) for b in d["biases"]]
        obj.mu = np.array(d["mu"]) if d["mu"] is not None else None
        obj.sigma = np.array(d["sigma"]) if d["sigma"] is not None else None
        return obj

    def save(self, path: Path = MODEL_PATH) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False),
                        encoding="utf-8")

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "MLPClassifier":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


# ===========================================================================
# 进球数回归器: 预测主/客队预期进球 λ (泊松回归)
# ===========================================================================
POISSON_MODEL_PATH = (Path(__file__).resolve().parent.parent
                      / "data" / "nn_goals.json")


class MLPPoissonRegressor:
    """纯 NumPy 的 MLP 泊松回归, 预测主客队进球数。

    - 输出层 2 个神经元, 经 exp() 得到非负的 λ_home, λ_away。
    - 损失 = 泊松负对数似然 NLL: λ - k·log(λ) (对每个进球数分别求和)。
    - 与 Dixon-Coles 一致: 进球服从泊松分布, 由 λ 可反推胜平负/大小球等所有盘口。
    - 复用与 MLPClassifier 相同的骨架(标准化 + Adam + L2 + early stopping)。
    """

    N_OUT = 2  # [log λ_home, log λ_away]

    def __init__(self,
                 hidden_sizes: Tuple[int, ...] = (8,),
                 lr: float = 0.01,
                 l2: float = 3e-3,
                 epochs: int = 300,
                 batch_size: int = 64,
                 seed: int = 42,
                 val_frac: float = 0.2,
                 patience: int = 30):
        self.hidden_sizes = tuple(hidden_sizes)
        self.lr = lr
        self.l2 = l2
        self.epochs = epochs
        self.batch_size = batch_size
        self.seed = seed
        self.val_frac = val_frac
        self.patience = patience
        self.weights: List[np.ndarray] = []
        self.biases: List[np.ndarray] = []
        self.mu: np.ndarray | None = None
        self.sigma: np.ndarray | None = None

    def _init_params(self, n_in: int) -> None:
        rng = np.random.default_rng(self.seed)
        sizes = [n_in, *self.hidden_sizes, self.N_OUT]
        self.weights, self.biases = [], []
        for a, b in zip(sizes[:-1], sizes[1:]):
            self.weights.append(rng.normal(0, math.sqrt(2.0 / a), size=(a, b)))
            self.biases.append(np.zeros(b))

    def _forward(self, x: np.ndarray):
        """返回 (激活列表, 线性输出列表)。最后一层线性输出 = log λ。"""
        acts = [x]
        zs = []
        h = x
        n_layers = len(self.weights)
        for i in range(n_layers):
            z = h @ self.weights[i] + self.biases[i]
            zs.append(z)
            if i < n_layers - 1:
                h = _relu(z)
            else:
                h = z  # 输出层保持线性 = log λ
            acts.append(h)
        return acts, zs

    def fit(self, X: np.ndarray, Y: np.ndarray,
            sample_weight: np.ndarray | None = None,
            verbose: bool = False) -> "MLPPoissonRegressor":
        """X: (n, n_features);  Y: (n, 2) = [主队进球, 客队进球]。"""
        X = np.asarray(X, dtype=float)
        Y = np.asarray(Y, dtype=float)
        n, n_in = X.shape

        self.mu = X.mean(axis=0)
        self.sigma = X.std(axis=0) + 1e-8
        Xs = (X - self.mu) / self.sigma

        if sample_weight is None:
            sw = np.ones(n)
        else:
            sw = np.asarray(sample_weight, dtype=float)
        sw = sw / sw.mean()

        self._init_params(n_in)

        rng = np.random.default_rng(self.seed)
        val_mask = np.zeros(n, dtype=bool)
        n_val = int(round(n * self.val_frac))
        if 0 < n_val < n:
            val_idx = rng.choice(n, size=n_val, replace=False)
            val_mask[val_idx] = True
        tr_idx = np.where(~val_mask)[0]
        va_idx = np.where(val_mask)[0]

        mW = [np.zeros_like(w) for w in self.weights]
        vW = [np.zeros_like(w) for w in self.weights]
        mB = [np.zeros_like(b) for b in self.biases]
        vB = [np.zeros_like(b) for b in self.biases]
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        t = 0

        best_val = math.inf
        best_params = None
        wait = 0

        for epoch in range(self.epochs):
            perm = rng.permutation(tr_idx)
            for start in range(0, len(perm), self.batch_size):
                idx = perm[start:start + self.batch_size]
                xb, yb, wb = Xs[idx], Y[idx], sw[idx]
                t += 1
                gW, gB = self._backward(xb, yb, wb)
                for i in range(len(self.weights)):
                    mW[i] = beta1 * mW[i] + (1 - beta1) * gW[i]
                    vW[i] = beta2 * vW[i] + (1 - beta2) * (gW[i] ** 2)
                    mB[i] = beta1 * mB[i] + (1 - beta1) * gB[i]
                    vB[i] = beta2 * vB[i] + (1 - beta2) * (gB[i] ** 2)
                    mW_hat = mW[i] / (1 - beta1 ** t)
                    vW_hat = vW[i] / (1 - beta2 ** t)
                    mB_hat = mB[i] / (1 - beta1 ** t)
                    vB_hat = vB[i] / (1 - beta2 ** t)
                    self.weights[i] -= self.lr * mW_hat / (np.sqrt(vW_hat) + eps)
                    self.biases[i] -= self.lr * mB_hat / (np.sqrt(vB_hat) + eps)

            if len(va_idx) > 0:
                val_loss = self._loss(Xs[va_idx], Y[va_idx], sw[va_idx])
                if val_loss < best_val - 1e-5:
                    best_val = val_loss
                    best_params = ([w.copy() for w in self.weights],
                                   [b.copy() for b in self.biases])
                    wait = 0
                else:
                    wait += 1
                    if wait >= self.patience:
                        if verbose:
                            print(f"  early stop @ epoch {epoch + 1}, "
                                  f"best val NLL={best_val:.4f}")
                        break

            if verbose and (epoch + 1) % 50 == 0:
                loss = self._loss(Xs[tr_idx], Y[tr_idx], sw[tr_idx])
                print(f"  epoch {epoch + 1:4d}/{self.epochs}  "
                      f"train={loss:.4f}  val={best_val:.4f}")

        if best_params is not None:
            self.weights, self.biases = best_params
        return self

    def _backward(self, xb, yb, wb):
        """泊松 NLL 反向传播。输出层 delta = (λ - k) (对 log λ 求导)。"""
        acts, zs = self._forward(xb)
        m = xb.shape[0]
        wcol = wb.reshape(-1, 1)

        gW = [None] * len(self.weights)
        gB = [None] * len(self.biases)

        lam = np.exp(np.clip(acts[-1], -20, 20))  # (m, 2)
        # d NLL / d(logλ) = λ - k
        delta = (lam - yb) * wcol / m
        for i in reversed(range(len(self.weights))):
            gW[i] = acts[i].T @ delta + self.l2 * self.weights[i]
            gB[i] = delta.sum(axis=0)
            if i > 0:
                dh = delta @ self.weights[i].T
                dh[zs[i - 1] <= 0] = 0.0
                delta = dh
        return gW, gB

    def _loss(self, Xs, Y, sw) -> float:
        acts, _ = self._forward(Xs)
        loglam = np.clip(acts[-1], -20, 20)
        lam = np.exp(loglam)
        # 泊松 NLL(去掉与参数无关的 log(k!) 常数项): sum(λ - k·logλ)
        nll = (lam - Y * loglam).sum(axis=1)
        reg = self.l2 / 2 * sum((w ** 2).sum() for w in self.weights)
        return float((sw * nll).mean() + reg / len(Xs))

    def predict_lambda(self, X: np.ndarray) -> np.ndarray:
        """返回 (n, 2) = [预期主队进球 λ_home, 预期客队进球 λ_away]。"""
        X = np.asarray(X, dtype=float)
        Xs = (X - self.mu) / self.sigma
        acts, _ = self._forward(Xs)
        return np.exp(np.clip(acts[-1], -20, 20))

    def to_dict(self) -> Dict:
        return {
            "kind": "poisson",
            "hidden_sizes": list(self.hidden_sizes),
            "lr": self.lr, "l2": self.l2, "epochs": self.epochs,
            "batch_size": self.batch_size, "seed": self.seed,
            "val_frac": self.val_frac, "patience": self.patience,
            "weights": [w.tolist() for w in self.weights],
            "biases": [b.tolist() for b in self.biases],
            "mu": self.mu.tolist() if self.mu is not None else None,
            "sigma": self.sigma.tolist() if self.sigma is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "MLPPoissonRegressor":
        obj = cls(hidden_sizes=tuple(d["hidden_sizes"]), lr=d["lr"],
                  l2=d["l2"], epochs=d["epochs"],
                  batch_size=d["batch_size"], seed=d["seed"],
                  val_frac=d.get("val_frac", 0.2),
                  patience=d.get("patience", 30))
        obj.weights = [np.array(w) for w in d["weights"]]
        obj.biases = [np.array(b) for b in d["biases"]]
        obj.mu = np.array(d["mu"]) if d["mu"] is not None else None
        obj.sigma = np.array(d["sigma"]) if d["sigma"] is not None else None
        return obj

    def save(self, path: Path = POISSON_MODEL_PATH) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False),
                        encoding="utf-8")

    @classmethod
    def load(cls, path: Path = POISSON_MODEL_PATH) -> "MLPPoissonRegressor":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
