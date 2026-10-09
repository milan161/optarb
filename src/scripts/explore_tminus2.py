# -*- coding: utf-8 -*-
"""
探索 v2：修正两处后复现参考程序月报
  ① 到期日遇法定假日**顺延**（第三个周五若休市，顺延到下一个交易日）
  ② 只保留「到期日落在数据范围内」的月份（否则会拿"数据末尾"当"到期日"，
     这是 future 项目踩过的坑，会系统性低估）
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
all_days = [r["date"] for r in conn.execute(
    "SELECT DISTINCT date FROM opt_daily WHERE variety=? ORDER BY date", (VARIETY,))]
day_set = set(all_days)
exps = [r["expiry"] for r in conn.execute(
    "SELECT DISTINCT expiry FROM opt_daily WHERE variety=? ORDER BY expiry", (VARIETY,))]

# 理论到期日（第三个周五）
print("到期日顺延检查：")
for e in exps:
    theo = migrate.expiry_date(e).isoformat()
    real = next((d for d in all_days if d >= theo), None)
    flag = "" if real == theo else f"   ← 顺延 {real}（{theo} 休市）"
    if flag:
        print(f"  {e}  第三个周五 {theo}{flag}")
print()


def real_expiry(exp):
    theo = migrate.expiry_date(exp).isoformat()
    return next((d for d in all_days if d >= theo), None)


def pick_atm(strikes, spot):
    return min(strikes, key=lambda k: abs(k - spot))


def spread_on(exp, far, day):
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
    ed = real_expiry(exp)
    if not ed:
        return None
    seq = [d for d in all_days if d <= ed]
    if len(seq) <= N:
        return None
    return seq[-1 - N]


# ★ 只保留：到期日在数据范围内 且 次月相邻
def ym(e):
    return (2000 + int(e[:2]), int(e[2:]))


def next_ym(e):
    y, m = ym(e)
    return (y + (1 if m == 12 else 0), 1 if m == 12 else m + 1)


pairs = []
for i in range(len(exps) - 1):
    e, f = exps[i], exps[i + 1]
    if next_ym(e) != ym(f):          # ← 修：原用 int(f)-int(e)==1，跨年（2512→2601）会误判
        continue
    if real_expiry(e) is None:
        continue
    d1 = day_for(e, 1)
    if d1 is None or spread_on(e, f, d1) is None:   # ← 修：只需"次月在 T-1 那天有数据"
        continue                                    #    原要求次月到期日也在范围内，会漏掉 26/09
    pairs.append((e, f))

print(f"可用月份 {len(pairs)} 个：{[p[0][:2]+'/'+p[0][2:] for p in pairs]}")
print()

HIS = {"2510": 239, "2511": 169, "2512": 140, "2601": 207, "2602": 219,
       "2603": 203, "2604": 200, "2605": 259, "2606": 242, "2607": 256,
       "2608": 218, "2609": 182}

print("=" * 104)
print("T-N 移仓价差矩阵（当月=平值档，收盘价口径，单位：指数点）")
print("=" * 104)
hdr = f"{'到期月':>7} {'T-1(他)':>9} " + " ".join(f"{'T-'+str(n):>8}" for n in range(1, 11))
print(hdr)
print("-" * len(hdr))

grid = {}
for exp, far in pairs:
    row = []
    for N in range(1, 11):
        d = day_for(exp, N)
        row.append(spread_on(exp, far, d) if d else None)
        grid[(exp, N)] = (d, row[-1])
    label = f"{exp[:2]}/{exp[2:]}"
    his = HIS.get(exp)
    mark = ""
    if his and row[0]:
        diff = row[0]["net"] - his
        mark = f"  {'✓' if abs(diff) <= 2 else '✗'} 差 {diff:+.1f}"
    cells = " ".join((f"{r['net']:>8.1f}" if r else f"{'--':>8}") for r in row)
    ks = [r["K"] for r in row if r]
    print(f"{label:>7} {str(his) if his else '--':>9} {cells}{mark}"
          + (f"   平值档 {min(ks):.0f}~{max(ks):.0f}" if ks else ""))

print()
print("=" * 104)
print("指标卡（对应他截图的 6 个卡片）")
print("=" * 104)
for N in range(1, 11):
    vals = [grid[(e, N)][1]["net"] for e, _ in pairs if grid[(e, N)][1]]
    sps = [grid[(e, N)][1]["spot"] for e, _ in pairs if grid[(e, N)][1]]
    if not vals:
        continue
    vs = sorted(vals)
    mean = sum(vals) / len(vals)
    med = (vs[len(vs) // 2] if len(vs) % 2
           else (vs[len(vs) // 2 - 1] + vs[len(vs) // 2]) / 2)
    ratio = sum(v / s for v, s in zip(vals, sps)) / len(sps) * 100
    print(f"  T-{N:<2}  样本 {len(vals):>2}  均值 {mean:>7.2f}  中位 {med:>7.2f}  "
          f"价差/现货 {ratio:>6.3f}%")

print()
print("他截图 T-1 的卡片：均值 211.25 / 中位 218.60 / 价差现货 2.664%")
conn.close()
