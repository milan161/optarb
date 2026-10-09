# -*- coding: utf-8 -*-
"""
ETF 期权 IV 序列的抓取 / 灌库 / 分位报表（见 core/etf_iv.py、docs/009）

用法：
  python scripts/fetch_etf_iv.py --import .tmp/iv_full2.json   # 从缓存快速灌全历史（推荐首次）
  python scripts/fetch_etf_iv.py --backfill                    # 从接口全量回补（慢，约 5~7 分钟）
  python scripts/fetch_etf_iv.py --backfill --start 2026-01-01 # 指定区间回补
  python scripts/fetch_etf_iv.py --today                       # 抓最新交易日（每日增量用）
  python scripts/fetch_etf_iv.py --date 2026-09-30             # 抓指定日
  python scripts/fetch_etf_iv.py --report                      # 打印分位报表
  python scripts/fetch_etf_iv.py --init                        # 只建表
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import etf_iv, store  # noqa: E402


def _report(conn):
    print("=" * 96)
    print("ETF 期权 IV 分位（口径：ATM IV = (官方认购 + 官方认沽)/2）")
    print("=" * 96)
    print(f"{'标的':<22}{'ATM IV':>9}{'全历史分位':>11}{'近1年':>9}{'近3年':>9}"
          f"{'样本':>8}  {'区间':<24}")
    print("-" * 96)
    for und in list(etf_iv.SSE_UNDERLYINGS) + list(etf_iv.SZSE_UNDERLYINGS):
        full = etf_iv.percentile(conn, und)
        if not full:
            print(f"{etf_iv.UNDERLYING_NAME.get(und, und) + ' (' + und + ')':<22}"
                  f"{'—':>9}{'无数据':>11}")
            continue
        y1 = etf_iv.percentile(conn, und, window=242)
        y3 = etf_iv.percentile(conn, und, window=726)
        nm = f"{etf_iv.UNDERLYING_NAME.get(und, und)} ({und})"
        print(f"{nm:<22}{full['value']*100:>8.2f}%{full['pct']:>10.1f}%"
              f"{y1['pct']:>8.1f}%{y3['pct']:>8.1f}%{full['n']:>8}  "
              f"{full['from']} ~ {full['to']}")
    print()
    print("分布细节（全历史）：")
    for und in list(etf_iv.SSE_UNDERLYINGS) + list(etf_iv.SZSE_UNDERLYINGS):
        p = etf_iv.percentile(conn, und)
        if not p:
            continue
        nm = f"{etf_iv.UNDERLYING_NAME.get(und, und)} ({und})"
        print(f"  {nm:<22} P10 {p['p10']*100:5.2f}  P25 {p['p25']*100:5.2f}  "
              f"中位 {p['p50']*100:5.2f}  P75 {p['p75']*100:5.2f}  "
              f"P90 {p['p90']*100:5.2f}  最高 {p['vmax']*100:6.2f}")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true", help="只建表")
    ap.add_argument("--import", dest="imp", metavar="JSON", help="从 iv_full*.json 灌库")
    ap.add_argument("--backfill", action="store_true", help="从接口全量回补")
    ap.add_argument("--start", default=None, help="回补起始日 YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="回补结束日 YYYY-MM-DD")
    ap.add_argument("--today", action="store_true", help="抓最新交易日")
    ap.add_argument("--date", default=None, help="抓指定日 YYYY-MM-DD")
    ap.add_argument("--report", action="store_true", help="打印分位报表")
    args = ap.parse_args()

    conn = store.connect()
    store.init_db(conn)
    print("库状态:", etf_iv.stats(conn))

    did = False

    if args.imp:
        n = etf_iv.import_json(conn, args.imp)
        print(f"从 {args.imp} 导入 {n} 行")
        did = True

    if args.backfill:
        start = args.start or "2015-01-01"
        end = args.end or date.today().isoformat()
        print(f"回补 {start} ~ {end} ...")
        n = etf_iv.backfill(conn, start, end,
                            progress=lambda a, b: print(f"  {a}/{b}", flush=True))
        print(f"回补写入 {n} 行")
        did = True

    if args.today:
        d, n, rows = etf_iv.update_latest(conn)
        if d:
            print(f"最新交易日 {d} 写入 {n} 行")
            for r in rows:
                print(f"  {r['underlying']} {etf_iv.UNDERLYING_NAME.get(r['underlying'],''):<14}"
                      f" ATM IV {r['atm_iv']*100:6.2f}%  ({r['src']}, {r['expiry']}, dte={r['dte']})")
        else:
            print("最近 10 天内没有拿到数据")
        did = True

    if args.date:
        n = etf_iv.fetch_and_save_day(conn, args.date)
        print(f"{args.date} 写入 {n} 行")
        did = True

    if args.report or not did:
        _report(conn)

    print("库状态:", etf_iv.stats(conn))
    conn.close()


if __name__ == "__main__":
    main()
