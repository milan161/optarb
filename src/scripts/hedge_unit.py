# -*- coding: utf-8 -*-
"""
对冲单元测算 —— 做 1 个「delta 中性」单元到底要多少资金？

背景：
    「波动率套利」= 卖期权 + 用期货对冲掉方向风险（delta 归零），只赚 IV→RV 回归。
    这是私募最主流的期权套利（文章说年化 6%~12%、回撤<3%）。
    但对散户，第一道门槛不是技术，是**资金粒度**：
      IO 期权乘数 100，IF 期货乘数 300 —— 要配平 delta，1 张 IF 要配好几张 IO。
      配不平就做不成中性，做不成中性就还是"赌方向"。

本脚本回答：50 万资金够不够做一个中性单元？
"""
import math
import os
import sys
from datetime import date, timedelta

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import quotes, risk  # noqa: E402

VAL = date(2026, 9, 24)
R = 0.02
# 可用资金：默认 50 万；东哥说「策略风险低时可投入 100 万」→ OPTARB_CAPITAL=1000000
CAPITAL = int(os.environ.get('OPTARB_CAPITAL', '500000'))


def N(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def third_friday(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def mid(o):
    b, a = o.get('bid'), o.get('ask')
    if b and a and b > 0 and a > 0:
        return (b + a) / 2.0
    return o.get('last')


def main():
    ch = quotes.fetch_option_chain('IO')
    futs = {f['month']: f for f in quotes.fetch_futures('IF')}

    print('=' * 104)
    print('做 1 个 delta 中性单元需要多少资金？')
    print('=' * 104)
    print(f'  设定资金 = {CAPITAL:,} 元')
    print(f'  构造：卖 N 张 IO 平值认购 + 买 1 张 IF 对冲（使组合 delta ≈ 0）')
    print()
    print(f"  {'月份':<7}{'剩余':>5}{'远期F':>9}{'K':>7}{'权利金':>8}{'IV':>8}"
          f"{'delta':>8}{'需IO张数':>9}{'IO保证金':>11}{'IF保证金':>11}{'合计':>11}{'够吗':>6}")

    for m in ch['months']:
        f = futs.get(m)
        if not f:
            continue
        y, mo = 2000 + int(m[:2]), int(m[2:])
        exp = third_friday(y, mo)
        days = (exp - VAL).days
        if days <= 0:
            continue

        fs = []
        for (mm, cp, k), o in ch['chain'].items():
            if mm != m or cp != 'C':
                continue
            p = ch['chain'].get((mm, 'P', k))
            if not p:
                continue
            cm, pm = mid(o), mid(p)
            if cm and pm:
                fs.append(cm - pm + k)
        if not fs:
            continue
        fs.sort()
        F = fs[len(fs) // 2]

        # ★ 从「该月自己有的行权价」里挑 ATM，不要用全品种的 strikes
        #   （远月缺档，用全量 strikes 会挑到该月不存在的 K → None）
        month_strikes = sorted({k for (mm, cp, k) in ch['chain'] if mm == m})
        if not month_strikes:
            continue
        K = min(month_strikes, key=lambda k: abs(k - F))
        c = ch['chain'].get((m, 'C', K))
        if not c:
            continue
        px = mid(c)
        if not px:
            continue
        iv = risk.implied_vol_from_price(px, F, K, 'C', days, R)
        if not iv:
            continue

        T = days / 365.0
        d1 = (math.log(F / K) + (R + iv * iv / 2) * T) / (iv * math.sqrt(T))
        delta = N(d1)                      # 认购 delta ∈ (0,1)

        # 1 张 IO 的方向敞口（元/点 × 点）
        io_notional = delta * 100 * F
        # 1 张 IF 的方向敞口
        Ff = (f['bid'] + f['ask']) / 2
        if_notional = 300 * Ff

        n = max(1, round(if_notional / io_notional))   # 需要几张 IO 才能配平 1 张 IF

        # 保证金：卖方按中金所公式；买方 IF 按 12%
        io_marg = n * (px + max(0.12 * F, 0.07 * F)) * 100
        if_marg = if_notional * 0.12
        total = io_marg + if_marg

        ok = 'OK' if total <= CAPITAL else '不够'
        print(f"  {m:<7}{days:>5}{F:>9.1f}{K:>7}{px:>8.1f}{iv*100:>7.2f}%"
              f"{delta:>8.3f}{n:>9}{io_marg:>11,.0f}{if_marg:>11,.0f}"
              f"{total:>11,.0f}{ok:>6}")

    print()
    print('  ★ 关键：IO 乘数 100、IF 乘数 300，且认购 delta < 1 ——')
    print('     1 张 IF 的方向敞口，要 6 张左右的 IO 才配得平。')
    print('     资金不够就配不平 → 配不平就还是"赌方向"，不是套利。')


if __name__ == '__main__':
    main()
