# -*- coding: utf-8 -*-
"""
抓取某论坛长帖《2022年股指期权卖方实战总结及2023-2024年交易思路和实战》
分页参数：?page=N（默认页 = 最新一页）
输出：log/jsl_main/page_NN.txt + 汇总 index
"""
import html
import os
import re
import time
import urllib.request

BASE = "https://www.jisilu.cn/question/469809"
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.basename(_SRC) == "src":
    _ROOT = os.path.dirname(_SRC)   # 本地: Optarb/
else:
    _ROOT = _SRC                    # ARM 扁平: optarb/
OUT = os.path.join(_ROOT, "log", "jsl_main")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

os.makedirs(OUT, exist_ok=True)


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': BASE})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8', 'replace')


def to_text(h):
    b = re.sub(r'<script.*?</script>', '', h, flags=re.S)
    b = re.sub(r'<style.*?</style>', '', b, flags=re.S)
    b = re.sub(r'<(br|/p|/div|/li|/tr|/h\d)[^>]*>', '\n', b)
    x = html.unescape(re.sub(r'<[^>]+>', '', b))
    x = re.sub(r'[ \t\xa0]+', ' ', x)
    x = re.sub(r'\n\s*\n+', '\n', x)
    return x.strip()


def main():
    index = []
    seen_sig = set()
    for p in range(1, 60):
        url = BASE if p == 1 else f"{BASE}?page={p}"
        try:
            h = fetch(url)
        except Exception as e:
            print(f"  page {p}: 抓取失败 {e}")
            break
        txt = to_text(h)
        ts = re.findall(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*来自(\S+)', txt)
        imgs = sorted(set(re.findall(r'(https://www\.jisilu\.cn/uploads/[^"\'>\s]+)', h)))
        if not ts:
            print(f"  page {p}: 无内容，停止")
            break
        sig = (ts[0][0], ts[-1][0], len(ts))
        if sig in seen_sig:
            print(f"  page {p}: 与前面重复，停止")
            break
        seen_sig.add(sig)
        fn = os.path.join(OUT, f"page_{p:02d}.txt")
        with open(fn, 'w', encoding='utf-8') as f:
            f.write(txt)
        with open(os.path.join(OUT, f"imgs_{p:02d}.txt"), 'w', encoding='utf-8') as f:
            f.write('\n'.join(imgs))
        index.append((p, len(ts), ts[0][0], ts[-1][0], len(txt), len(imgs)))
        print(f"  page {p:>2}: 条目{len(ts):>3}  {ts[0][0]} ~ {ts[-1][0]}  "
              f"文本{len(txt):>6}字  图{len(imgs)}")
        time.sleep(0.8)

    print()
    print(f"共抓取 {len(index)} 页")
    with open(os.path.join(OUT, 'index.txt'), 'w', encoding='utf-8') as f:
        for row in index:
            f.write('\t'.join(str(x) for x in row) + '\n')


if __name__ == '__main__':
    main()
