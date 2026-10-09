#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把本机 data/optarb.db 的 etf_iv_daily **单表**导出成一个独立小库。

用途：`deploy/deploy.sh iv` 推 ARM 时用。

为什么只推这一张表，不整库覆盖：
  ARM 上的 opt_daily / index_daily / fut_daily 由每日 cron（工作日 16:45）更新，
  往往**比本机新**（2026-10-01 实测：ARM 的 opt_daily 已到 2026-10-08，本机只到 09-30）。
  整库覆盖会把 ARM 上更新的数据冲掉。IV 表只有本机在算，所以单独推。
  —— 与 future 项目「推单文件 future.db」不同：那个项目的库只有本机在写。

用法：
  python scripts/export_iv_table.py [输出路径]     默认 .tmp/etf_iv_daily.db
"""
import os
import sqlite3
import sys

# [AI-2026-10-07] 原 ROOT=dirname(dirname(__file__)) 在本地会落到 Optarb/src，
#   拼出 Optarb/src/data/optarb.db（不存在）⇒ 脚本直接报"找不到"。
#   改为 README §2 的双端兼容写法：本地 src/ 的父目录 = 程序根；ARM 扁平布局直接用。
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_HERE)
if os.path.basename(_PROJ) == "src":
    SRC_ROOT = _PROJ
    PROJ_ROOT = os.path.dirname(_PROJ)       # 本地: Optarb/
else:
    SRC_ROOT = _PROJ
    PROJ_ROOT = _PROJ                         # ARM 扁平: /home/ubuntu/optarb
SRC = os.path.join(PROJ_ROOT, "data", "optarb.db")
TABLE = "etf_iv_daily"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJ_ROOT, ".tmp", TABLE + ".db")
    if not os.path.exists(SRC):
        print("✗ 找不到 %s" % SRC)
        return 1
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        os.remove(out)

    src = sqlite3.connect(SRC)
    ddl = src.execute(
        "SELECT sql FROM sqlite_master WHERE name=?", (TABLE,)).fetchone()
    if not ddl:
        print("✗ 本机库里没有表 %s —— 先跑 scripts/fetch_etf_iv.py --backfill" % TABLE)
        return 1

    dst = sqlite3.connect(out)
    dst.execute(ddl[0])
    cols = [c[1] for c in src.execute("PRAGMA table_info(%s)" % TABLE)]
    rows = src.execute("SELECT * FROM %s" % TABLE).fetchall()
    dst.executemany("INSERT INTO %s VALUES (%s)" % (TABLE, ",".join("?" * len(cols))), rows)
    dst.commit()

    n = dst.execute("SELECT COUNT(*) FROM %s" % TABLE).fetchone()[0]
    print("    导出 %d 行 → %s（%.1f KB）" % (n, os.path.relpath(out, PROJ_ROOT),
                                          os.path.getsize(out) / 1024.0))
    for u, c, lo, hi in dst.execute(
            "SELECT underlying, COUNT(*), MIN(date), MAX(date) FROM %s GROUP BY underlying" % TABLE):
        print("      %-8s %5d 行  %s ~ %s" % (u, c, lo, hi))
    dst.close()
    src.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
