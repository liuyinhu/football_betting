"""Interactive real-match predictor.

You input the CURRENT live match state (score, minute, shots, corners, etc.)
and the CURRENT market odds. The program outputs:
  - final score probability distribution (top scores)
  - 1X2 / Over-Under / BTTS probabilities
  - value bet recommendations (EV + Kelly stake)

Two ways to use:

1) Interactive (prompts you step by step):
       python3 -m football_betting.predict

2) Edit a JSON file and pass it (repeatable, no re-typing):
       python3 -m football_betting.predict match.json
   (a template is written to match.example.json on first run)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

from .core.state import MatchState, OddsSnapshot
from .models.poisson_live import outcome_probabilities, final_score_distribution
from .strategy.decision import evaluate


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ask(prompt: str, cast, default):
    raw = input(f"{prompt} [{default}]: ").strip()
    if raw == "":
        return default
    try:
        return cast(raw)
    except ValueError:
        print(f"  ! invalid, using default {default}")
        return default


def build_from_prompts() -> tuple[MatchState, OddsSnapshot]:
    print("\n=== 输入比赛当前场面 (直接回车用默认值) ===")
    minute  = _ask("当前比赛分钟数 (0-90)", int, 45)
    score_h = _ask("主队进球", int, 0)
    score_a = _ask("客队进球", int, 0)

    print("\n--- 场面统计 (可留空) ---")
    sot_h   = _ask("主队射正", int, 0)
    sot_a   = _ask("客队射正", int, 0)
    shots_h = _ask("主队总射门", int, sot_h)
    shots_a = _ask("客队总射门", int, sot_a)
    cor_h   = _ask("主队角球", int, 0)
    cor_a   = _ask("客队角球", int, 0)
    da_h    = _ask("主队危险进攻", int, 0)
    da_a    = _ask("客队危险进攻", int, 0)
    poss_h  = _ask("主队控球率 %", float, 50.0)
    red_h   = _ask("主队红牌", int, 0)
    red_a   = _ask("客队红牌", int, 0)
    xg_h    = _ask("主队 xG (没有填0)", float, 0.0)
    xg_a    = _ask("客队 xG (没有填0)", float, 0.0)

    print("\n--- 赛前预期进球 (可用赛前大小球/让球估计, 默认 1.4 / 1.1) ---")
    prior_h = _ask("主队赛前预期进球 λ", float, 1.4)
    prior_a = _ask("客队赛前预期进球 λ", float, 1.1)

    state = MatchState(
        match_id="LIVE", minute=minute, score_h=score_h, score_a=score_a,
        shots_h=shots_h, shots_a=shots_a, sot_h=sot_h, sot_a=sot_a,
        corners_h=cor_h, corners_a=cor_a,
        dangerous_attacks_h=da_h, dangerous_attacks_a=da_a,
        possession_h=poss_h, red_h=red_h, red_a=red_a,
        xg_h=xg_h, xg_a=xg_a,
        prior_lambda_h=prior_h, prior_lambda_a=prior_a,
    )

    print("\n=== 输入当前投注赔率 (欧洲/小数赔率, 没有填 0 跳过) ===")
    odds = OddsSnapshot(match_id="LIVE", minute=minute)
    odds.home = _ask("主胜赔率", float, 0.0) or None
    odds.draw = _ask("平局赔率", float, 0.0) or None
    odds.away = _ask("客胜赔率", float, 0.0) or None
    for line in (1.5, 2.5, 3.5):
        o = _ask(f"大 {line} 赔率", float, 0.0)
        if o: odds.over[line] = o
        u = _ask(f"小 {line} 赔率", float, 0.0)
        if u: odds.under[line] = u
    return state, odds


def _strip_json_comments(text: str) -> str:
    """Remove // line comments and /* */ block comments so a commented
    JSON template can still be parsed by the standard json module."""
    import re
    # remove /* ... */ block comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # remove // line comments (but keep :// inside strings like http://)
    out_lines = []
    for line in text.splitlines():
        in_str = False
        esc = False
        cut = None
        for i, ch in enumerate(line):
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str and ch == "/" and i + 1 < len(line) and line[i + 1] == "/":
                cut = i
                break
        out_lines.append(line[:cut] if cut is not None else line)
    # remove trailing commas before } or ]
    joined = "\n".join(out_lines)
    joined = re.sub(r",(\s*[}\]])", r"\1", joined)
    return joined


def _fuzzy_find_team(name: str, teams: dict) -> str | None:
    """Case-insensitive substring / difflib match of a team name."""
    if name in teams:
        return name
    low = name.lower().strip()
    for t in teams:
        if t.lower() == low:
            return t
    # substring match
    cands = [t for t in teams if low in t.lower() or t.lower() in low]
    if len(cands) == 1:
        return cands[0]
    # difflib closest
    import difflib
    close = difflib.get_close_matches(name, list(teams), n=1, cutoff=0.6)
    return close[0] if close else (cands[0] if cands else None)


def _apply_trained_lambdas(s: dict) -> None:
    """If s has home_team/away_team and a trained model exists, fill
    prior_lambda_h/a automatically (unless user already provided them)."""
    home_team = s.get("home_team")
    away_team = s.get("away_team")
    if not home_team or not away_team:
        return
    try:
        from .data.train_strength import load as load_model, expected_lambdas, MODEL_PATH
        if not MODEL_PATH.exists():
            print("⚠️ 未找到训练模型，跳过自动 λ。先运行: "
                  "python3 -m football_betting.data.train_strength")
            return
        model = load_model()
        teams = model["teams"]
        h = _fuzzy_find_team(home_team, teams)
        a = _fuzzy_find_team(away_team, teams)
        if not h or not a:
            miss = home_team if not h else away_team
            print(f"⚠️ 球队 '{miss}' 未在训练数据中找到，使用默认/手填 λ。")
            return
        lam_h, lam_a = expected_lambdas(model, h, a)
        s.setdefault("prior_lambda_h", round(lam_h, 3))
        s.setdefault("prior_lambda_a", round(lam_a, 3))
        print(f"✓ 已从训练模型载入赛前 λ:  {h} {lam_h:.2f}  vs  {a} {lam_a:.2f}")
    except Exception as e:
        print(f"⚠️ 自动 λ 失败: {e}")


def build_from_json(path: str) -> tuple[MatchState, OddsSnapshot]:
    raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(_strip_json_comments(raw))
    s = data.get("state", {})
    o = data.get("odds", {})

    # If home_team/away_team are given, auto-fill prior lambdas from trained model
    _apply_trained_lambdas(s)

    state = MatchState(match_id=s.get("match_id", "LIVE"), minute=s.get("minute", 45),
                       **{k: v for k, v in s.items()
                          if k not in ("match_id", "minute", "home_team", "away_team")})
    odds = OddsSnapshot(match_id="LIVE", minute=state.minute)
    odds.home = o.get("home")
    odds.draw = o.get("draw")
    odds.away = o.get("away")
    odds.over = {float(k): v for k, v in o.get("over", {}).items()}
    odds.under = {float(k): v for k, v in o.get("under", {}).items()}
    odds.exact = {tuple(map(int, k.split("-"))): v for k, v in o.get("exact", {}).items()}
    return state, odds


def write_template(path: str = "match.example.json") -> None:
    template = '''{
  // ============================================================
  //  足球实时预测输入文件  (支持 // 注释，运行时会自动忽略)
  //  运行:  python3 -m football_betting.predict match.example.json
  // ============================================================

  "state": {                       // —— 比赛当前场面 ——
    "minute": 60,                  // 当前比赛分钟数 (0~90)
    "score_h": 1,                  // 主队当前进球数
    "score_a": 0,                  // 客队当前进球数

    "sot_h": 4,                    // 主队射正 (影响进球率最大之一)
    "sot_a": 2,                    // 客队射正
    "shots_h": 9,                  // 主队总射门
    "shots_a": 5,                  // 客队总射门

    "corners_h": 5,                // 主队角球
    "corners_a": 3,                // 客队角球
    "dangerous_attacks_h": 40,     // 主队危险进攻
    "dangerous_attacks_a": 25,     // 客队危险进攻

    "possession_h": 58,            // 主队控球率 % (客队=100-此值)
    "red_h": 0,                    // 主队红牌 (每张λ乘0.65)
    "red_a": 0,                    // 客队红牌

    "xg_h": 1.3,                   // 主队实时 xG，没有填0 (权重高)
    "xg_a": 0.6,                   // 客队实时 xG

    "prior_lambda_h": 1.5,         // ★主队赛前预期进球λ (最关键基准)
    "prior_lambda_a": 1.1          // ★客队赛前预期进球λ
    //  可从赛前大小球反推: 大小球2.5≈主1.4/客1.1
  },

  "odds": {                        // —— 当前投注赔率 (小数赔率) ——
    "home": 1.55,                  // 主胜赔率
    "draw": 3.80,                  // 平局赔率
    "away": 7.50,                  // 客胜赔率

    "over":  { "2.5": 2.40 },      // 大球，可加 "1.5"/"3.5"
    "under": { "2.5": 1.60 },      // 小球

    "exact": {                     // 精确比分赔率(可选)，键 "主-客"
      "2-0": 5.5,
      "1-0": 4.2,
      "2-1": 8.0
    }
  }
}
'''
    Path(path).write_text(template, encoding="utf-8")
    print(f"已生成模板文件: {path}  (编辑后运行: python3 -m football_betting.predict {path})")


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------
def report(state: MatchState, odds: OddsSnapshot) -> None:
    probs = outcome_probabilities(state)
    dist = final_score_distribution(state)
    top = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:8]

    print("\n" + "=" * 60)
    print(f"当前 {state.minute}'  比分 {state.score_h}-{state.score_a}  "
          f"(剩余 {state.remaining} 分钟)")
    print("=" * 60)

    print("\n【最终比分概率 TOP 8】")
    for (h, a), p in top:
        bar = "█" * int(p * 40)
        print(f"  {h}-{a}   {p:6.2%}  {bar}")

    print("\n【胜平负 / 大小球 / 双方进球】")
    print(f"  主胜 {probs['home']:.2%}   平局 {probs['draw']:.2%}   客胜 {probs['away']:.2%}")
    print(f"  大2.5 {probs['over_2.5']:.2%}   小2.5 {probs['under_2.5']:.2%}")
    print(f"  大1.5 {probs['over_1.5']:.2%}   大3.5 {probs['over_3.5']:.2%}")
    print(f"  双方进球 是 {probs['btts_yes']:.2%}   否 {probs['btts_no']:.2%}")

    recs = evaluate(state, odds)
    print("\n【投注建议 (仅列出正期望值 EV≥3% 的)】")
    if not recs:
        print("  无。当前赔率下没有发现有价值的投注 (或你没输入赔率)。")
    else:
        for r in recs:
            print(f"  ✅ {r.market:14s} 赔率 {r.odds:5.2f}  "
                  f"模型概率 {r.model_prob:.2%}  "
                  f"EV {r.edge:+.1%}  建议仓位 {r.stake_fraction:.2%}")
        print("\n  仓位 = 占总资金比例 (已用 1/4 凯利并封顶 2%)。")
    print("\n⚠️ 仅供学习研究，模型不保证盈利，请勿用于真实赌博。")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] in ("-t", "--template"):
        write_template()
        return
    if args:
        state, odds = build_from_json(args[0])
    else:
        state, odds = build_from_prompts()
    report(state, odds)


if __name__ == "__main__":
    main()
