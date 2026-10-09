# -*- coding: utf-8 -*-
"""
探索：复现参考程序的《中证1000 股指期权 · 平值卖沽「当月→次月」移仓价差》月报
（2026-09-27，仅用于验证口径，不是正式功能）

他的月报口径（从截图逐条读出）：
  · 品种 MO，标的 中证1000 指数 sh000852，收盘价口径，单位指数点（1点=100元/手）
  · 横轴 = 过去 12 次月度到期（25/10 ... 26/09）
  · 「距交割 T-1 ~ T-10」= 到期日前的第 N 个**应开市交易日**（不是自然日）
  · 档位 = 「当前平值 K」（也可切 上一档 K+1 / 下一档 K-1）
  · 价差 = 次月P(K)收盘 − 当月P(K)收盘
  · 长假导致某月缺值 → 插值「补值」，图上标星号
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import migrate, store  # noqa: E402

VARIETY = "MO"
CP = "P"
IDX = "sh000852"

conn = store.connect()

# 全市场交易日（用 MO 自身的日期即可）
all_days = [r["date"] for r in conn.execute(
    "SELECT DISTINCT date FROM opt_daily WHERE variety=? ORDER BY date", (VARIETY,))]
exps = [r["expiry"] for r in conn.execute(
    "SELECT DISTINCT expiry FROM opt_daily WHERE variety=? ORDER BY expiry", (VARIETY,))]

print(f"库内交易日 {len(all_days)} 个：{all_days[0]} ~ {all_days[-1]}")
print(f"到期月 {len(exps)} 个：{exps}")
print()

# 只保留相邻的两个到期月（当月 -> 次月）
pairs = []
for i in range(len(exps) - 1):
    if int(exps[i + 1]) - int(exps[i]) == 1:
        pairs.append((exps[i], exps[i + 1]))
# 取最近 12 次
pairs = pairs[-12:]


def pick_atm(strikes, spot):
    """平值 = 最接近现货收盘的档位"""
    return min(strikes, key=lambda k: abs(k - spot))


def spread_on(exp, far, day):
    """某日：当月 exp、次月 far，取平值档，返回 (K, 价差, 现货)"""
    spot = store.load_index_close(conn, IDX, day)
    if not spot:
        return None
    near = [o for o in store.load_options(conn, VARIETY, day, CP) if o["expiry"] == exp]
    fars = [o for o in store.load_options(conn, VARIETY, day, CP) if o["expiry"] == far]
    if not near or not fars:
        return None
    far_by_k = {o["strike"]: o for o in fars}
    strikes = sorted({o["strike"] for o in near if o["strike"] in far_by_k})
    if not strikes:
        return None
    K = pick_atm(strikes, spot)
    n = next(o for o in near if o["strike"] == K)
    f = far_by_k[K]
    pn, pf = migrate._px(n), migrate._px(f)
    if pn is None or pf is None:
        return None
    return {"K": K, "net": round(pf - pn, 2), "spot": spot}


def day_for(exp, N):
    """到期日前的第 N 个应开市交易日（T-N）。T-1 = 到期日的前一个交易日。"""
    ed = migrate.expiry_date(exp).isoformat()
    seq = [d for d in all_days if d <= ed]
    if len(seq) <= N:
        return None
    return seq[-1 - N]


print("=" * 96)
print("T-N 移仓价差矩阵（当月=平值档，收盘价口径，单位：指数点）")
print("=" * 96)
hdr = f"{'到期月':>7} " + " ".join(f"{'T-'+str(n):>8}" for n in range(1, 11))
print(hdr)
print("-" * len(hdr))

grid = {}
for exp, far in pairs:
    row = []
    for N in range(1, 11):
        d = day_for(exp, N)
        r = spread_on(exp, far, d) if d else None
        row.append(r)
        grid[(exp, N)] = (d, r)
    label = f"{exp[:2]}/{exp[2:]}"
    cells = " ".join((f"{r['net']:>8.1f}" if r else f"{'--':>8}") for r in row)
    ks = [r["K"] for r in row if r]
    print(f"{label:>7} {cells}   平值档 {min(ks):.0f}~{max(ks):.0f}" if ks else f"{label:>7} {cells}")

print()
print("=" * 96)
print("按 T-N 汇总（对应他截图里的指标卡）")
print("=" * 96)
for N in range(1, 11):
    vals = [grid[(e, N)][1]["net"] for e, _ in pairs if grid[(e, N)][1]]
    sps = [grid[(e, N)][1]["spot"] for e, _ in pairs if grid[(e, N)][1]]
    if not vals:
        continue
    vals_sorted = sorted(vals)
    mean = sum(vals) / len(vals)
    med = (vals_sorted[len(vals) // 2] if len(vals) % 2
           else (vals_sorted[len(vals) // 2 - 1] + vals_sorted[len(vals) // 2]) / 2)
    ratio = sum(v / s for v, s in zip(vals, sps)) / len(sps) * 100
    print(f"  T-{N:<2}  样本 {len(vals):>2} 个月  均值 {mean:>7.2f} 点  "
          f"中位数 {med:>7.2f} 点  价差/现货 {ratio:>6.3f}%")

print()
print("=" * 96)
print("他截图上的数字（T-1，当前平值 K）：均值 211.25 / 中位 218.60 / 价差现货 2.664%")
print("=" * 96)
conn.close()
