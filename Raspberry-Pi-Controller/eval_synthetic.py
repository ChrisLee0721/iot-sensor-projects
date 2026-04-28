#!/usr/bin/env python3
"""
eval_synthetic.py — 用仿真数据集离线验证 ML 有效性
──────────────────────────────────────────────────
生成一周（7天 × 144条/天 = 1008条）的合成温湿度数据。
数据加入了昼夜曲线 + 工作日/周末规律 + 随机噪声，
用来证明 ML 可以在边界区间学到规则不知道的时间模式。

运行：
    python3 eval_synthetic.py

输出：
  - eval_result.csv    完整运行记录
  - 控制台输出关键指标
"""

import math
import random
import csv
from datetime import datetime, timedelta
from pathlib import Path

from river import tree, preprocessing, compose, metrics

# ── 配置（与 pi_controller 保持一致）────────────────────────────────────────
TEMP_LOW  = 20.0
TEMP_HIGH = 28.0
HUMI_LOW  = 40.0
HUMI_HIGH = 70.0
BOOTSTRAP_N = 20
SCALE = 10000        # river VALUE_SCALE

# ── 仿真数据生成 ────────────────────────────────────────────────────────────
def generate_week(start: datetime, interval_minutes: int = 10):
    """
    生成一周的合成室内温湿度数据。

    规律：
    - 温度：基础值随小时变化（午后高、凌晨低），周末白天高 0.5°C（活动多）
    - 湿度：基础值随季节/时间波动 + 小噪声
    - 仿真"边界区间"：刻意让傍晚 17-19 点温度在 TEMP_HIGH ± 1.5 徘徊，
      这是规则引擎最难判断的地方，也是 ML 时间特征最有价值的区间。
    """
    samples = []
    t = start
    steps = 7 * 24 * 60 // interval_minutes
    for _ in range(steps):
        hour    = t.hour
        weekday = t.weekday()   # 0=周一 … 6=周日
        is_weekend = weekday >= 5

        # 室内温度：基础 sine 曲线（凌晨 5 点最低，14 点最高）
        phase = (hour - 5) / 24 * 2 * math.pi
        base_temp = 24.0 + 4.0 * math.sin(phase)

        # 周末下午多人在家，温度略高
        if is_weekend and 12 <= hour <= 20:
            base_temp += 0.8

        # 傍晚 17-19 刻意压到边界区间顶部，让规则引擎犹豫
        if 17 <= hour <= 19:
            base_temp = TEMP_HIGH + 1.0 + random.gauss(0, 0.5)
        else:
            base_temp += random.gauss(0, 0.6)

        # 室内湿度：基础 60%，夜间略低，白天略高
        base_humi = 55.0 + 8.0 * math.sin((hour - 8) / 24 * 2 * math.pi)
        base_humi += random.gauss(0, 3.0)
        base_humi = max(30.0, min(85.0, base_humi))

        samples.append({
            "ts":      t,
            "hour":    hour,
            "weekday": weekday,
            "in_temp": round(base_temp, 2),
            "in_humi": round(base_humi, 2),
            # 室外（简化：比室内低 2-5°C，湿度相近）
            "out_temp": round(base_temp - random.uniform(2, 5), 2),
            "out_humi": round(base_humi + random.gauss(0, 5), 2),
        })
        t += timedelta(minutes=interval_minutes)
    return samples


# ── 规则引擎（与 pi_controller 相同）────────────────────────────────────────
def rule_decision(in_t, in_h, out_t):
    if in_h > HUMI_HIGH + 10 or in_h < HUMI_LOW - 10:
        return 5
    if in_t < TEMP_LOW - 2:
        return 1
    if in_t > TEMP_HIGH + 2:
        return 2
    if TEMP_LOW <= in_t <= TEMP_HIGH and HUMI_LOW <= in_h <= HUMI_HIGH and abs(out_t - in_t) < 3:
        return 3
    return 0


def is_comfortable(in_t, in_h):
    return TEMP_LOW <= in_t <= TEMP_HIGH and HUMI_LOW <= in_h <= HUMI_HIGH


ACTION_NAMES = {0: "维持", 1: "制热", 2: "制冷", 3: "开窗", 4: "关窗", 5: "报警"}


# ── 离线仿真运行 ─────────────────────────────────────────────────────────────
def run():
    random.seed(42)
    start = datetime(2026, 4, 22, 0, 0, 0)   # 周二开始
    # 生成 4 周数据：模拟系统持续运行一个月
    samples = []
    for w in range(4):
        samples += generate_week(start + timedelta(weeks=w), interval_minutes=10)

    model = compose.Pipeline(
        preprocessing.StandardScaler(),
        tree.HoeffdingTreeClassifier(grace_period=30, delta=1e-5, leaf_prediction="mc"),
    )
    ml_acc = metrics.Accuracy()

    rows = []
    for i, s in enumerate(samples):
        feat = {
            "in_temp":    s["in_temp"],
            "in_humi":    s["in_humi"],
            "out_temp":   s["out_temp"],
            "out_humi":   s["out_humi"],
            "feels_like": s["out_temp"] - 2,   # 简化体感
            "hour":       s["hour"],
            "weekday":    s["weekday"],
            "temp_diff":  s["in_temp"] - s["out_temp"],
            "humi_diff":  s["in_humi"] - s["out_humi"],
        }
        rule_label = rule_decision(s["in_temp"], s["in_humi"], s["out_temp"])

        sample_n = i + 1
        if sample_n <= BOOTSTRAP_N:
            ml_pred  = None
            decision = rule_label
            phase    = "bootstrap"
            model.learn_one(feat, rule_label)
        else:
            ml_pred  = model.predict_one(feat)
            decision = ml_pred if ml_pred is not None else rule_label
            ml_acc.update(rule_label, decision)
            model.learn_one(feat, rule_label)
            phase = "ML"

        diverged = int(phase == "ML" and ml_pred is not None and ml_pred != rule_label)

        # comfortable_next: 看下一条样本
        next_s = samples[i + 1] if i + 1 < len(samples) else None
        comfortable_next = int(is_comfortable(next_s["in_temp"], next_s["in_humi"])) if next_s else ""

        rows.append({
            "timestamp":         s["ts"].isoformat(timespec="seconds"),
            "hour":              s["hour"],
            "weekday":           s["weekday"],
            "in_temp":           s["in_temp"],
            "in_humi":           s["in_humi"],
            "out_temp":          s["out_temp"],
            "rule_label":        rule_label,
            "ml_pred":           ml_pred,
            "decision":          decision,
            "phase":             phase,
            "diverged":          diverged,
            "comfortable_next":  comfortable_next,
            "ml_acc_pct":        round(ml_acc.get() * 100, 1) if sample_n > BOOTSTRAP_N else "",
        })

    # ── 写 CSV ───────────────────────────────────────────────────────────────
    out_path = Path("eval_result.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        fields = list(rows[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # ── 统计分析 ──────────────────────────────────────────────────────────────
    ml_rows   = [r for r in rows if r["phase"] == "ML"]
    div_rows  = [r for r in ml_rows if r["diverged"] == 1]
    nodiv_rows = [r for r in ml_rows if r["diverged"] == 0]

    div_rate  = len(div_rows) / len(ml_rows) * 100 if ml_rows else 0

    def comfort_rate(subset):
        valid = [r for r in subset if r["comfortable_next"] != ""]
        if not valid:
            return float("nan")
        return sum(r["comfortable_next"] for r in valid) / len(valid) * 100

    cr_div   = comfort_rate(div_rows)
    cr_nodiv = comfort_rate(nodiv_rows)

    # 按小时统计发散集中在哪些时段
    div_by_hour = {}
    for r in div_rows:
        h = r["hour"]
        div_by_hour[h] = div_by_hour.get(h, 0) + 1

    print("=" * 55)
    print("  仿真数据集离线验证结果")
    print("=" * 55)
    print(f"  总样本数:           {len(rows)}")
    print(f"  ML 阶段样本:        {len(ml_rows)}")
    print(f"  ML 最终精度*:       {round(ml_acc.get() * 100, 1)}%")
    print(f"    *(对比规则标签，仅证明学到了规则，不证明有用)")
    print()
    print(f"  ML 发散率:          {div_rate:.1f}%")
    print(f"    发散时下轮舒适率:  {cr_div:.1f}%")
    print(f"    不发散时下轮舒适率:{cr_nodiv:.1f}%")
    if cr_div > cr_nodiv:
        delta = cr_div - cr_nodiv
        print(f"  → ML 发散决策比规则多带来 {delta:.1f}% 的舒适概率 ✓")
    elif cr_div < cr_nodiv:
        print(f"  → ML 发散决策比规则差，需要更多训练数据或调参 ✗")
    else:
        print(f"  → 发散与否结果相同，ML 无显著额外价值 ~")
    print()
    print(f"  发散集中时段（小时 → 发散次数）:")
    for h in sorted(div_by_hour, key=lambda x: -div_by_hour[x])[:5]:
        print(f"    {h:02d}:00  →  {div_by_hour[h]} 次")
    print()
    print(f"  结果已写入: {out_path.resolve()}")
    print("=" * 55)


if __name__ == "__main__":
    run()
