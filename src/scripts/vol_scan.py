# -*- coding: utf-8 -*-
"""
IO 期权波动率快照 —— 隐含波动率(IV) 期限结构 + 偏度 + 与已实现波动率(RV) 对比

为什么做这个：
    知乎那篇《期权套利全拆解》把期权套利分四类，其中
      ① 平价套利(PCP)   —— 需要几秒级速度，散户做不了
      ② 波动率套利      —— 私募最主流，年化 6%~12%，回撤 <3%，**不需要秒级速度**
      ③ 波动率偏度套利  —— 危机 Alpha
      ④ 日历价差套利
    ★ ②③④ 才是散户（有编程能力、不拼速度）可能够得着的。
    本脚本就是「波动率套利」扫描器的雏形：把 IV 和 RV 摆在一起看。

判据：
    IV > RV  → 期权贵（卖方有优势）
    IV < RV  → 期权便宜（买方有优势）
"""
import json
import math
import re
import sys
import urllib.request
from datetime import date, timedelta

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import quotes, risk  # noqa: E402

VAL = date(2026, 9, 24)      # 最后交易日（9-25 中秋休市）
R = 0.02
SINA_KLINE = ("http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
              "CN_MarketData.getKLineData?symbol=sh000300&scale=240&ma=no&datalen={n}")


def third_friday(y, m):
    d = date(y, m, 1)
    return d + timedelta(days=(4 - d.weekday()) % 7 + 14)


def mid(o):
    b, a = o.get('bid'), o.get('ask')
    if b and a and b > 0 and a > 0:
        return (b + a) / 2.0
    return o.get('last')


def fetch_index_closes(n=80):
    url = SINA_KLINE.format(n=n)
    req = urllib.request.Request(url, headers={
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0'})
    raw = urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'replace')
    # 新浪这个口是非严格 JSON（key 无引号），先尝试标准解析再兜底
    try:
        arr = json.loads(raw)
    except Exception:
        arr = json.loads(re.sub(r'(\w+):', r'"\1":', raw))
    return [(x['day'], float(x['close'])) for x in arr]


def realized_vol(closes, win):
    """年化已实现波动率（对数收益标准差 × sqrt(252)）"""
    if len(closes) < win + 1:
        return None
    c = closes[-(win + 1):]
    rets = [math.log(c[i + 1] / c[i]) for i in range(len(c) - 1)]
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / (len(rets) - 1)
    return math.sqrt(var) * math.sqrt(252)


def main():
    ch = quotes.fetch_option_chain('IO')

    # ---------- 1. 已实现波动率 ----------
    print('=' * 84)
    print('① 沪深300 已实现波动率（RV，年化）')
    print('=' * 84)
    try:
        bars = fetch_index_closes(80)
        closes = [c for _, c in bars]
        print(f'   数据区间：{bars[0][0]} ~ {bars[-1][0]}   共 {len(bars)} 个交易日')
        print(f'   最新收盘：{closes[-1]:.2f}')
        rv20 = realized_vol(closes, 20)
        rv60 = realized_vol(closes, 60)
        print(f'   RV20 = {rv20*100:.2f}%')
        print(f'   RV60 = {rv60*100:.2f}%')
    except Exception as e:
        print(f'   抓取失败：{e}')
        rv20 = rv60 = None

    # ---------- 2. 每月：远期 + ATM IV + 偏度 ----------
    print()
    print('=' * 84)
    print('② IO 期权隐含波动率（IV）期限结构 + 偏度')
    print('=' * 84)
    print(f"   {'月份':<7}{'剩余':>5}{'远期F':>10}{'ATM K':>8}{'ATM IV':>9}"
          f"{'虚值沽IV':>10}{'偏度':>8}")

    rows = []
    for m in ch['months']:
        y, mo = 2000 + int(m[:2]), int(m[2:])
        exp = third_friday(y, mo)
        days = (exp - VAL).days
        if days <= 0:
            continue

        # 反推该月远期 F = K + (C-P)（用 mid）
        fs = []
        for (mm, cp, k), o in ch['chain'].items():
            if mm != m or cp != 'C':
                continue
            p = ch['chain'].get((mm, 'P', k))
            if not p:
                continue
            cm, pm = mid(o), mid(p)
            if cm is None or pm is None:
                continue
            fs.append(cm - pm + k)
        if not fs:
            continue
        fs.sort()
        F = fs[len(fs) // 2]

        # ATM
        K = min(ch['strikes'], key=lambda k: abs(k - F))
        c = ch['chain'].get((m, 'C', K))
        p = ch['chain'].get((m, 'P', K))
        ivs = []
        for o, cp in ((c, 'C'), (p, 'P')):
            if not o:
                continue
            px = mid(o)
            if px:
                iv = risk.implied_vol_from_price(px, F, K, cp, days, R)
                if iv:
                    ivs.append(iv)
        atm_iv = sum(ivs) / len(ivs) if ivs else None

        # 虚值认沽（低一档行权价）的 IV —— 看偏度
        below = [k for k in ch['strikes'] if k < K]
        put_iv = None
        if below:
            Kp = max(below)
            op = ch['chain'].get((m, 'P', Kp))
            if op:
                px = mid(op)
                if px:
                    put_iv = risk.implied_vol_from_price(px, F, Kp, 'P', days, R)

        skew = (put_iv - atm_iv) if (put_iv and atm_iv) else None

        def f(x):
            return f'{x*100:.2f}%' if x else '--'
        print(f"   {m:<7}{days:>5}{F:>10.1f}{K:>8}{f(atm_iv):>9}"
              f"{f(put_iv):>10}{f(skew):>8}")
        rows.append(dict(m=m, days=days, F=F, K=K, atm_iv=atm_iv,
                         put_iv=put_iv, skew=skew))

    # ---------- 3. IV vs RV ----------
    if rv20:
        print()
        print('=' * 84)
        print('③ IV vs RV —— 谁贵谁便宜（波动率套利的判据）')
        print('=' * 84)
        print(f'   RV20 = {rv20*100:.2f}%   RV60 = {rv60*100:.2f}%')
        print()
        print(f"   {'月份':<7}{'剩余':>5}{'ATM IV':>10}{'IV-RV20':>10}   判断")
        for r in rows:
            if not r['atm_iv']:
                continue
            d = r['atm_iv'] - rv20
            verdict = '期权偏贵（卖方有优势）' if d > 0.02 else (
                '期权偏便宜（买方有优势）' if d < -0.02 else '基本持平')
            print(f"   {r['m']:<7}{r['days']:>5}{r['atm_iv']*100:>9.2f}%"
                  f"{d*100:>+9.2f}pp   {verdict}")
        print()
        print('   ★ 注意：这只是"快照"。判断贵贱需要 IV 的历史分位（要攒数据）。')
        print('     这正是「每日快照积累」要做的事。')


if __name__ == '__main__':
    main()
