#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""增量抓取中金所历史日行情 + 指数日线 → data/optarb.db

用法：
    python scripts/update_market.py --date 20260924      # 指定单日
    python scripts/update_market.py --days 10            # 最近 10 个自然日
    python scripts/update_market.py --from 20260901 --to 20260924
    python scripts/update_market.py --days 10 --force    # 强制重抓

说明：
    · 自动跳过周末；非交易日（无数据）静默跳过
    · 已入库的日期默认跳过（真增量）
    · 指数默认一起更新（判断实值/虚值、价差/现货要用）
"""
import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import cffex, config, sina, store  # noqa: E402
from core import etf_sse  # noqa: E402  (上交所 ETF 期权官方日行情直爬：E300/E500/E880)
from core import etf_szse  # noqa: E402  (深交所 ETF 期权官方日行情直爬：E915)
from core import etf_iv  # noqa: E402  (ETF 期权 IV 序列：官方 IV + 自算，全历史可回溯)


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="单日，如 20260924")
    ap.add_argument("--from", dest="frm", help="起始日 YYYYMMDD")
    ap.add_argument("--to", dest="to", help="结束日 YYYYMMDD")
    ap.add_argument("--days", type=int, help="最近 N 个自然日")
    ap.add_argument("--force", action="store_true", help="忽略已入库标记")
    ap.add_argument("--no-index", action="store_true", help="不更新指数")
    args = ap.parse_args()

    if args.date:
        days = [args.date]
    elif args.frm:
        s = datetime.strptime(args.frm, "%Y%m%d").date()
        e = datetime.strptime(args.to or args.frm, "%Y%m%d").date()
        days = [d.strftime("%Y%m%d") for d in daterange(s, e)]
    else:
        n = args.days or 1
        today = date.today()
        days = [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]

    conn = store.connect()
    store.init_db(conn)

    added = skipped = 0
    for ds in days:
        iso = f"{ds[:4]}-{ds[4:6]}-{ds[6:]}"
        if datetime.strptime(ds, "%Y%m%d").weekday() >= 5:
            continue
        if not args.force and store.has_day(conn, iso):
            skipped += 1
            continue
        try:
            raw = cffex.fetch_raw(ds)
        except Exception as e:  # noqa: BLE001
            print(f"  {iso}  抓取失败：{e}")
            continue
        if not raw:
            continue                       # 非交易日
        opts, futs = cffex.classify(cffex.parse(raw))
        store.save_day(conn, iso, opts, futs)
        store.log_fetch(conn, iso, True, len(opts), len(futs))
        print(f"  {iso}  期权 {len(opts):4d}  期货 {len(futs):2d}")
        added += 1
        time.sleep(0.4)

    if not args.no_index:
        for _, meta in config.VARIETIES.items():
            # ★ ETF 期权的标的现货由 etf_sse 直接从官方端点取（UNDERLYING_CLOSEPX），
            #   不再走 sina；这里只更新股指期权的指数日线。
            if meta.get("exchange") != "CFFEX":
                continue
            sym = meta["index"]
            try:
                rs = sina.fetch_index_daily(sym, n=1200)
                store.save_index(conn, sym, rs)
                print(f"  指数 {sym:<10} {len(rs):4d} 条  "
                      f"({rs[0]['day']} ~ {rs[-1]['day']})" if rs else f"  指数 {sym} 空")
            except Exception as e:  # noqa: BLE001
                print(f"  指数 {sym} 失败：{e}")

    # ---------------- ETF 期权（上交所官方日行情）----------------
    # ★ 该端点只返回「最新交易日」，不支持历史回溯。
    #   所以 ETF 抓的是"今天"的快照（多个到期月同框，足以算跨月移仓价差），
    #   历史深度靠每天收盘后增量累积。与中金所按 --date 抓历史是两套逻辑。
    #   注意：若 ETF 当天已入库则跳过（除非 --force），避免重复打官网。
    #   标的 510300/510500/588080 → E300/E500/E880（588080 科创50ETF 是上交所）。
    try:
        etf_today = date.today().isoformat()
        if args.force or not store.has_day(conn, etf_today):
            ed = etf_sse.fetch_day()
            if ed and ed["options"]:
                store.save_day(conn, ed["trade_date"], ed["options"], [])
                store.log_fetch(conn, ed["trade_date"], True, len(ed["options"]), 0)
                # ETF 现货（UNDERLYING_CLOSEPX）入 index_daily，供 migrate 取 spot
                for sym, px in ed["spots"].items():
                    store.save_index(conn, sym, [{"day": ed["trade_date"], "close": px}])
                print(f"  ETF期权(沪) {ed['trade_date']}  "
                      f"{len(ed['options'])} 个合约 · 现货 {ed['spots']}")
                added += 1
            elif ed is None:
                print("  ETF期权(沪)：官方端点无数据（非交易日？）")
            else:
                print("  ETF期权(沪)：返回为空，跳过")
        else:
            print(f"  ETF期权(沪) {etf_today} 已入库，跳过")
    except Exception as e:  # noqa: BLE001
        print(f"  ETF期权(沪)抓取失败（不影响中金所数据）：{e}")

    # ---------------- ETF 期权（深交所官方日行情：E915 创业板）----------------
    # ★ szse.cn 的 option_drhy 只给「前结算价」(qjsjg)，无当日收盘/结算，也无现货；
    #   现货由 etf_szse 从新浪 sz159915 取。详见 docs/008 §四。
    try:
        sz_today = date.today().isoformat()
        if args.force or not store.has_day(conn, sz_today):
            sd = etf_szse.fetch_day()
            if sd and sd["options"] and sd["trade_date"] > sz_today:
                # ★ 长假期间该报告会把「下一个交易日」当 subname 返回，但价格还是上个交易日的。
                #   若照存，会在 fetch_log 里占掉未来那天，导致真交易日被 has_day 跳过。
                print(f"  ETF期权(深)：官方返回日期 {sd['trade_date']} 在未来（长假占位），跳过")
            elif sd and sd["options"]:
                store.save_day(conn, sd["trade_date"], sd["options"], [])
                store.log_fetch(conn, sd["trade_date"], True, len(sd["options"]), 0)
                for sym, px in sd["spots"].items():
                    store.save_index(conn, sym, [{"day": sd["trade_date"], "close": px}])
                print(f"  ETF期权(深) {sd['trade_date']}  "
                      f"{len(sd['options'])} 个合约 · 现货 {sd['spots']}")
                added += 1
            elif sd is None:
                print("  ETF期权(深)：官方端点无数据（非交易日？）")
            else:
                print("  ETF期权(深)：返回为空，跳过")
        else:
            print(f"  ETF期权(深) {sz_today} 已入库，跳过")
    except Exception as e:  # noqa: BLE001
        print(f"  ETF期权(深)抓取失败（不影响中金所数据）：{e}")

    # ---------------- ETF 期权 IV 序列（官方 IV，全历史可回溯）----------------
    # ★ 见 core/etf_iv.py / docs/009：
    #   上交所「期权风险指标」接口认 trade_date，从 2015-02-09 起有逐合约官方 IV；
    #   深交所官方无 IV，由本地合约链自算（平价远期 + Black-76）。
    #   必须放在 SSE/SZSE 日行情之后 —— 深交所自算要读当天的 opt_daily。
    #   入库口径固定为 atm_iv = (认购 + 认沽)/2（官方 IV 无视分红，取平均抵消偏差）。
    try:
        iv_date, n_iv, iv_rows = etf_iv.update_latest(conn)
        if iv_date:
            print(f"  ETF期权IV {iv_date}  {n_iv} 个标的")
            for r in iv_rows:
                print(f"      {r['underlying']} {etf_iv.UNDERLYING_NAME.get(r['underlying'],''):<14}"
                      f" ATM IV {r['atm_iv']*100:6.2f}%  ({r['src']}, {r['expiry']}, dte={r['dte']})")
        else:
            print("  ETF期权IV：最近 10 天无数据（长假？）")
    except Exception as e:  # noqa: BLE001
        print(f"  ETF期权IV 抓取失败（不影响其他数据）：{e}")

    print(f"\n完成：新增 {added} 天，跳过 {skipped} 天")
    print("库统计：", store.stats(conn))
    conn.close()


if __name__ == "__main__":
    main()
