# -*- coding: utf-8 -*-
"""
期货-期权平价套利 —— 用「可成交价」重算（这才是真能拿到手的钱）

构造（全部持有到到期，现金交割，无平仓价差）：
    卖合成期货 = 卖 C + 买 P     今日收 (bid_C - ask_P)
    买实际期货 = 买 IF           今日付 0（保证金占用）
    到期合计 payoff = (K - S) + (S - F) = K - F     <- 无风险

    1 张 IF 配 3 套期权（乘数 300 vs 100）：
        净收益 = 300 × [ bid_C - ask_P + K - ask_IF ]     单位：元

★ 关键：用 bid/ask 而不是 mid。mid 是账面价，成交要付买卖价差。
"""
import math
import sys
from datetime import date, timedelta

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import quotes  # noqa: E402

R = 0.02
VAL_DATE = date(2026, 9, 25)
MULT_FUT = 300          # IF 元/点
MULT_OPT = 100          # IO 元/点


def third_friday(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def main():
    ch = quotes.fetch_option_chain('IO')
    spot = ch['spot']
    futs = {f['month']: f for f in quotes.fetch_futures('IF')}

    print('=' * 92)
    print('期货-期权平价套利  ——  可成交价测算')
    print('=' * 92)
    print(f'标的 = {spot:.2f}   估值日 = {VAL_DATE}')
    print()
    print('  逻辑：卖合成期货（卖C + 买P）+ 买 IF，持有到到期')
    print('  1 张 IF 配 3 套期权（IF 乘数 300 / IO 乘数 100）')
    print()

    results = []
    for m in ch['months']:
        f = futs.get(m)
        if not f:
            continue
        y, mo = 2000 + int(m[:2]), int(m[2:])
        expiry = third_friday(y, mo)
        days = (expiry - VAL_DATE).days
        if days <= 0:
            continue
        T = days / 365.0

        # ATM 行权价
        K = min(ch['strikes'], key=lambda k: abs(k - spot))
        c = ch['chain'].get((m, 'C', K))
        p = ch['chain'].get((m, 'P', K))
        if not (c and p and c.get('bid') and c.get('ask') and p.get('bid') and p.get('ask')):
            continue
        if not (f.get('bid') and f.get('ask')):
            continue

        # ---- 可成交价 ----
        bid_c, ask_c = c['bid'], c['ask']
        bid_p, ask_p = p['bid'], p['ask']
        ask_if = f['ask']

        # 合成空头实得（卖C按买一，买P按卖一）
        synth = bid_c - ask_p
        # 到期无风险收益（元）
        pnl = MULT_FUT * (synth + K - ask_if)

        # 理论价（mid）作对照
        mid_c = (bid_c + ask_c) / 2
        mid_p = (bid_p + ask_p) / 2
        mid_if = (f['bid'] + f['ask']) / 2
        pnl_mid = MULT_FUT * ((mid_c - mid_p) + K - mid_if)

        # 价差成本
        spread_opt = (ask_c - bid_c) + (ask_p - bid_p)      # 每套
        spread_fut = f['ask'] - f['bid']
        spread_cost = 300 * spread_opt + 300 * spread_fut   # 3套期权 + 1张IF

        # 手续费（隔日平昨口径，因为持有到交割不涉及平今）
        notional = ask_if * MULT_FUT
        fee_if = notional * 0.000023 * 2                    # 开+交割
        fee_opt = 6 * 30                                    # 6张，15元/张单边
        fee = fee_if + fee_opt

        # 保证金占用
        margin_if = notional * 0.12
        otm = max(K - spot, 0)
        marg_c = (ask_c + max(0.12 * spot - otm, 0.07 * spot)) * MULT_OPT
        margin = margin_if + 3 * marg_c
        premium_p = 3 * ask_p * MULT_OPT

        results.append(dict(
            m=m, days=days, K=K, synth=synth, pnl=pnl, pnl_mid=pnl_mid,
            spread_cost=spread_cost, fee=fee, net=pnl - spread_cost - fee,
            margin=margin + premium_p, ask_if=ask_if,
            bid_c=bid_c, ask_c=ask_c, bid_p=bid_p, ask_p=ask_p,
            spread_opt=spread_opt, spread_fut=spread_fut,
        ))

    # ---------------- 明细 ----------------
    for r in results:
        print('-' * 92)
        print(f"[{r['m']}]  到期剩 {r['days']} 天   ATM 行权价 K = {r['K']}")
        print(f"   IO 认购  bid={r['bid_c']:.1f}  ask={r['ask_c']:.1f}  (价差 {r['spread_opt']/2:.1f})")
        print(f"   IO 认沽  bid={r['bid_p']:.1f}  ask={r['ask_p']:.1f}")
        print(f"   IF 期货  ask={r['ask_if']:.1f}  (价差 {r['spread_fut']:.1f})")
        print()
        print(f"   ① 理论毛利（mid 口径）        {r['pnl_mid']:>10,.0f} 元")
        print(f"   ② 可成交毛利（bid/ask 口径）  {r['pnl']:>10,.0f} 元")
        print(f"   ③ 买卖价差成本                {-r['spread_cost']:>10,.0f} 元")
        print(f"   ④ 手续费                      {-r['fee']:>10,.0f} 元")
        print(f"   ────────────────────────────────────────")
        print(f"   ⑤ 净收益 = ②+③+④              {r['net']:>10,.0f} 元", end='')
        if r['net'] > 0:
            print('   ✅')
        else:
            print('   ❌ 亏')
        print(f"   ⑥ 占用资金（保证金+权利金）    {r['margin']:>10,.0f} 元")
        if r['net'] > 0:
            roi = r['net'] / r['margin']
            ann = roi * 365 / r['days']
            print(f"   ⑦ 期间收益率 {roi*100:.3f}%   年化 {ann*100:.2f}%")

    # ---------------- 汇总 ----------------
    print()
    print('=' * 92)
    print('汇总')
    print('=' * 92)
    print(f"  {'月份':<8}{'天数':>6}{'理论毛利':>12}{'价差成本':>12}{'手续费':>10}{'净收益':>12}{'年化':>10}")
    for r in results:
        ann = (r['net'] / r['margin'] * 365 / r['days'] * 100) if r['net'] > 0 else 0
        print(f"  {r['m']:<8}{r['days']:>6}{r['pnl_mid']:>12,.0f}{-r['spread_cost']:>12,.0f}"
              f"{-r['fee']:>10,.0f}{r['net']:>12,.0f}{ann:>9.2f}%")
    print()
    print('  注：净收益按「持有到交割」口径；若中途平仓还要再付一次买卖价差。')


if __name__ == '__main__':
    main()
