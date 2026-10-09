# -*- coding: utf-8 -*-
"""
IO 期权  vs  IF 期货 —— 期货-期权平价（Put-Call Parity on Futures）偏离实测

平价关系（Black 模型；欧式、同到期日、同标的）：
        C - P = e^{-rT} (F - K)
  =>    F_implied = K + (C - P) * e^{rT}

若 F_implied 与真实 F 的偏离，系统性超过交易成本，则存在可执行的套利。

★ 乘数差异（容易搞错）：
    IF 股指期货 = 300 元 / 点
    IO 股指期权 = 100 元 / 点
  => 1 张 IF 的名义敞口 = 3 张 IO 期权

★ 为什么这条对散户可行（与"现货-期权平价"的区别）：
    - 现货-期权平价需要融券或持有现货 → A 股散户基本没戏
    - 期货-期权平价全程现金结算，不需要备货、不需要融券
    - IF 与 IO 同标的（沪深300）、同到期日（交割月第三个周五）
"""
import math
import sys
from datetime import date, timedelta

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import quotes  # noqa: E402

R = 0.02                       # 无风险利率假设
VAL_DATE = date(2026, 9, 25)   # 估值日（数据为周五收盘）


def third_friday(y, m):
    """交割月第三个周五（中金所最后交易日）"""
    d = date(y, m, 1)
    off = (4 - d.weekday()) % 7        # 4 = Friday
    return d + timedelta(days=off + 14)


def mid(o):
    """优先用买卖中间价，没有则退回首笔成交价"""
    b, a = o.get('bid'), o.get('ask')
    if b and a and b > 0 and a > 0:
        return (b + a) / 2.0
    return o.get('last')


def main():
    ch = quotes.fetch_option_chain('IO')
    spot = ch['spot']
    months = ch['months']

    print('=' * 78)
    print('IO 期权  vs  IF 期货   ——   期货-期权平价偏离实测')
    print('=' * 78)
    print(f'标的（平价反推 沪深300） = {spot:.2f}')
    print(f'IO 到期月 = {months}')
    print(f'估值日 = {VAL_DATE}   无风险利率 r = {R:.1%}')

    futs = quotes.fetch_futures('IF')
    fmap = {f['month']: f for f in futs}
    print()
    print('IF 期货：')
    for f in futs:
        print(f"  {f['instrument']:<9} last={f['last']:<10} "
              f"bid={f['bid']:<10} ask={f['ask']:<10} 持仓={f['position']:.0f}")

    print()
    print('=' * 78)
    print('逐月检验（ATM 附近 5 档行权价）')
    print('=' * 78)

    for m in months:
        f = fmap.get(m)
        if not f:
            print(f'\n[{m}]  IF 无此月份，跳过')
            continue
        y, mo = 2000 + int(m[:2]), int(m[2:])
        expiry = third_friday(y, mo)
        days = (expiry - VAL_DATE).days
        if days <= 0:
            print(f'\n[{m}]  已到期，跳过')
            continue
        T = days / 365.0
        F = mid(f) or f['last']

        print(f'\n[{m}]  到期 {expiry}   剩余 {days} 天  (T={T:.4f}年)')
        print(f'       IF 期货 mid = {F}')
        print(f"       {'K':>6} {'C':>8} {'P':>8} | {'F_imp(r=2%)':>12} "
              f"{'偏离':>8} {'偏离%':>8} | {'F_imp(r=0)':>11}")

        ks = sorted(sorted(ch['strikes'], key=lambda k: abs(k - spot))[:5])
        devs = []
        for K in ks:
            c = ch['chain'].get((m, 'C', K))
            p = ch['chain'].get((m, 'P', K))
            if not c or not p:
                continue
            cm, pm = mid(c), mid(p)
            if cm is None or pm is None:
                continue
            Fi = K + (cm - pm) * math.exp(R * T)
            Fi0 = K + (cm - pm)
            d = Fi - F
            devs.append(d)
            print(f"       {K:>6} {cm:>8.1f} {pm:>8.1f} | {Fi:>12.1f} "
                  f"{d:>8.1f} {d / F * 100:>7.3f}% | {Fi0:>11.1f}")

        if devs:
            s = sorted(devs)
            md = s[len(s) // 2]
            print(f"       -> 中位偏离 {md:+.1f} 点 ({md / F * 100:+.3f}%)   "
                  f"极差 {max(devs) - min(devs):.1f} 点")

    # ---------------------------------------------------------------- 成本
    print()
    print('=' * 78)
    print('交易成本量级（1 张 IF 名义 ≈ 3 张 IO 期权）')
    print('=' * 78)
    F0 = 4400.0
    notional = F0 * 300
    if_open = notional * 0.000023      # 中金所 IF 开仓 万0.23
    if_close_today = notional * 0.000345   # 平今 万3.45
    if_close_prev = notional * 0.000023    # 平昨 万0.23
    io_rt = 6 * 30                     # 6 张 IO（3套×C+P）开+平，按 30 元/张往返
    print(f'  1 张 IF 名义 = {F0:.0f} × 300 = {notional:,.0f} 元')
    print(f'  IF 开仓        ≈ {if_open:,.1f} 元  (万0.23)')
    print(f'  IF 平今        ≈ {if_close_today:,.1f} 元  (万3.45 —— 惩罚性)')
    print(f'  IF 平昨        ≈ {if_close_prev:,.1f} 元  (万0.23)')
    print(f'  6 张 IO 往返   ≈ {io_rt:,.0f} 元  (按 15 元/张单边估)')
    print()
    for label, if_close in (('当日平今', if_close_today), ('隔日平昨', if_close_prev)):
        tot = if_open + if_close + io_rt
        print(f'  【{label}】总成本 ≈ {tot:,.0f} 元  '
              f'= 名义的 {tot / notional * 100:.3f}%  '
              f'= 指数 {tot / 300:.2f} 点')
    print()
    print('  ★ 判据：偏离必须 > 上述"指数点数"，扣掉滑点才算真机会。')


if __name__ == '__main__':
    main()
