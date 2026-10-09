#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
中金所历史日行情抓取（探测/验证脚本）

用途：验证「股指期权日行情」能否稳定获取，以及字段覆盖度。
不写库、不落盘结构化数据，只做抓取 + 解析 + 统计，供决策用。

★ 路径（2026-09-27 实测可用）
    http://www.cffex.com.cn/sj/hqsj/rtj/{YYYYMM}/{DD}/{YYYYMMDD}_1.csv
    - 编码 GBK（不是 UTF-8！）
    - _1.csv 含股指期货 + 股指期权 + 国债期货
    - 需要 UA；Referer 带上更稳
    - 无成交合约的「今收盘」为 null，但「今结算」有值  ← 对应「零成交用结算价」口径
    - 回溯：实测 2015-12 起有数据；IO 期权自 2019-12-23 上市
    - ⚠️ 404 时返回 302 跳 error_404.html，HTTP 状态不是 404，要判内容

★ 字段
    合约代码,今开盘,最高价,最低价,成交量,成交金额,持仓量,持仓变化,
    今收盘,今结算,前结算,涨跌1,涨跌2,Delta
    → 有收盘/结算/Delta；**没有 IV**（IV 需自行用 BS 反推）

用法：
    python scripts/fetch_cffex_daily.py 20260924
    python scripts/fetch_cffex_daily.py 20260924 --csv out.csv
"""
import sys, os, csv, io, argparse, collections, urllib.request

BASE = "http://www.cffex.com.cn/sj/hqsj/rtj/{ym}/{dd}/{date}_1.csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
HEADERS = {"User-Agent": UA, "Referer": "http://www.cffex.com.cn/"}

# 品种前缀 → 名称
VARIETY = {
    "IF": "沪深300股指期货", "IH": "上证50股指期货",
    "IC": "中证500股指期货", "IM": "中证1000股指期货",
    "IO": "沪深300股指期权", "HO": "上证50股指期权", "MO": "中证1000股指期权",
    "TS": "2年期国债", "TF": "5年期国债", "T2": "10年期国债", "TL": "30年期国债",
}


def fetch(date: str, timeout: int = 20) -> bytes:
    """按日期抓原始字节（GBK）"""
    url = BASE.format(ym=date[:6], dd=date[6:8], date=date)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if b"\xef\xbb\xbf" in data[:8] or b"instrument" in data[:200]:
        raise RuntimeError("返回的不是日交易数据（可能被重定向到错误页）")
    if "合约代码" not in data.decode("gbk", errors="replace")[:200]:
        raise RuntimeError("内容首行不是表头，疑似 404 页")
    return data


def parse(raw: bytes):
    """GBK 解码 + 解析为 dict 列表"""
    text = raw.decode("gbk", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def summarize(rows):
    """按品种统计 + 字段覆盖度"""
    stat = collections.defaultdict(lambda: {"n": 0, "close": 0, "settle": 0, "delta": 0})
    for r in rows:
        code = (list(r.values())[0] or "").strip()
        if len(code) < 2 or code in ("合计", "小计") or "小计" in code or "合计" in code:
            continue
        v = code[:2]
        if v not in VARIETY:
            continue
        s = stat[v]
        s["n"] += 1
        for key, col in (("close", "今收盘"), ("settle", "今结算"), ("delta", "Delta")):
            if r.get(col) not in (None, "", "null"):
                s[key] += 1
    return stat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", help="交易日，如 20260924")
    ap.add_argument("--csv", help="把原始解析结果另存为该 CSV")
    args = ap.parse_args()

    raw = fetch(args.date)
    rows = parse(raw)
    print(f"日期 {args.date}  原始 {len(raw):,} 字节  数据行 {len(rows)}")

    stat = summarize(rows)
    print(f"\n{'品种':<6}{'名称':<20}{'合约数':>7}{'有收盘':>8}{'有结算':>8}{'有Delta':>9}")
    for v in ("IF", "IH", "IC", "IM", "IO", "HO", "MO"):
        if v in stat:
            s = stat[v]
            print(f"{v:<6}{VARIETY[v]:<20}{s['n']:>7}{s['close']:>8}{s['settle']:>8}{s['delta']:>9}")

    # 抽一行 IO 看真实字段
    for r in rows:
        code = (list(r.values())[0] or "").strip()
        if code.startswith("IO") and r.get("今收盘") not in (None, "", "null"):
            print("\n样例：")
            for k, v in r.items():
                if v not in (None, "", "null"):
                    print(f"  {k} = {v}")
            break

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\n已写出 {args.csv}")


if __name__ == "__main__":
    main()
