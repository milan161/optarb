# -*- coding: utf-8 -*-
"""
解析某论坛长帖的全部回复，按「作者 + 时间 + 正文」结构化。

HTML 结构：
    <div class="aw-item" id="answer_list_4658914">
        <a class="aw-user-img" href=".../people/<楼主昵称>" data-id="6767">
        <div class="aw-mod-body">
            <em class="aw-vote-count">11</em>
            <p class="publisher"><a class="aw-user-name"><楼主昵称></a></p>
            <p class="aw-agree-by">赞同来自: ...</p>     <- 投票名单，剥掉
            <div>[正文]</div>
            <div class="...footer...">2026-09-26 10:15 来自云南</div>
        </div>
    </div>

输出：
    log/jsl_main/posts.jsonl        全部帖子（去重）
    log/jsl_main/author_posts.txt   只看楼主
"""
import html
import json
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
# ★ 2026-09-28：楼主昵称不再硬编码（隐私）。重跑时用环境变量传入：
#     JSL_AUTHOR="<昵称>" python scripts/parse_jsl_main.py
AUTHOR = os.environ.get("JSL_AUTHOR", "")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(url, cache=None):
    """带本地缓存的抓取（HTML 存下来，避免重复请求）"""
    if cache and os.path.exists(cache):
        with open(cache, encoding='utf-8') as f:
            return f.read()
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Accept-Language': 'zh-CN,zh;q=0.9', 'Referer': BASE})
    with urllib.request.urlopen(req, timeout=30) as r:
        h = r.read().decode('utf-8', 'replace')
    if cache:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, 'w', encoding='utf-8') as f:
            f.write(h)
    return h


def clean_text(s):
    s = re.sub(r'<script.*?</script>', '', s, flags=re.S)
    s = re.sub(r'<style.*?</style>', '', s, flags=re.S)
    s = re.sub(r'<img[^>]*>', ' [图] ', s)
    s = re.sub(r'<(br|/p|/div|/li|/tr|/h\d)[^>]*>', '\n', s)
    s = html.unescape(re.sub(r'<[^>]+>', '', s))
    s = re.sub(r'[ \t\xa0]+', ' ', s)
    s = re.sub(r'\n\s*\n+', '\n', s)
    return s.strip()


def parse_page(h):
    """返回 [(aid, author, time, loc, votes, content)]

    真实结构（2026-09 实测）：
        <div class="aw-item" ... id="answer_list_5549493">
          <a class="aw-user-img" ...><img .../></a>          <- 头像，丢弃
          <div class="aw-mod-body">
            <em class="...aw-vote-count...">0</em>            <- 赞数
            <p class="publisher"><a class="aw-user-name">AUTHOR</a></p>
            <p class="aw-agree-by ...">赞同来自: ...</p>       <- 投票名单，丢弃
            <div class="markitup-box" > [正文] </div>          <- ★ 唯一正文来源
          </div>
          <div class="aw-dynamic-topic-meta">
            <span class="pull-left aw-text-color-999">2026-09-26 10:15 来自江苏</span>
          </div>
        </div>
    """
    out = []
    # ★ 用前瞻切分：标签本身留在块内（否则 id="answer_list_XXX" 会被一起吞掉）
    parts = re.split(r'(?=<div class="aw-item"[^>]*id="answer_list_)', h)
    for b in parts[1:]:
        m_id = re.search(r'id="answer_list_(\d+)"', b)
        aid = m_id.group(1) if m_id else None
        # 作者：只认 publisher 里的那个（避免正文 @某人 的 aw-user-name 干扰）
        m_a = re.search(r'<p class="publisher">\s*<a class="aw-user-name"[^>]*>([^<]+)</a>', b)
        author = html.unescape(m_a.group(1)).strip() if m_a else None
        # 赞数
        m_v = re.search(r'class="[^"]*aw-vote-count[^"]*"[^>]*>(\d+)<', b)
        votes = int(m_v.group(1)) if m_v else None
        # 时间 + 地点（兜底：只有时间没有地点，或格式微变）
        m_t = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*来自(\S+?)\s*<', b)
        if not m_t:
            m_t = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*来自\s*(\S+?)\s*[<\n]', b)
        if not m_t:
            m_t = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})', b)
        ts = m_t.group(1) if m_t else None
        loc = m_t.group(2) if (m_t and m_t.lastindex and m_t.lastindex >= 2) else None
        # ★ 正文：markitup-box 起，到「end 评论内容」止
        m_c = re.search(r'<div class="markitup-box"\s*>(.*?)<!-- end 评论内容 -->',
                        b, flags=re.S)
        raw = m_c.group(1) if m_c else ''
        content = clean_text(raw)
        out.append(dict(aid=aid, author=author, time=ts, loc=loc,
                        votes=votes, content=content))
    return out


def main():
    seen = {}
    for p in range(1, 60):
        url = BASE if p == 1 else f"{BASE}?page={p}"
        cache = os.path.join(OUT, 'html', f'page_{p:02d}.html')
        try:
            h = fetch(url, cache)
        except Exception as e:
            print(f"  page {p}: 失败 {e}")
            break
        posts = parse_page(h)
        new = 0
        for x in posts:
            if not x['aid']:
                continue
            if x['aid'] not in seen:
                seen[x['aid']] = x
                new += 1
        print(f"  page {p:>2}: 解析 {len(posts):>3} 条, 新增 {new:>3}, 累计 {len(seen)}")
        if new == 0 and p > 3:
            print("  无新增，停止")
            break
        time.sleep(0.7)

    posts = sorted(seen.values(), key=lambda x: (x['time'] or ''))
    with open(os.path.join(OUT, 'posts.jsonl'), 'w', encoding='utf-8') as f:
        for x in posts:
            f.write(json.dumps(x, ensure_ascii=False) + '\n')

    mine = [x for x in posts if x['author'] == AUTHOR]
    with open(os.path.join(OUT, 'author_posts.txt'), 'w', encoding='utf-8') as f:
        for x in mine:
            f.write(f"===== {x['time']} | {x['loc']} | 赞{x['votes']} | #{x['aid']} =====\n")
            f.write((x['content'] or '') + '\n\n')

    print()
    print(f"总帖子数: {len(posts)}")
    print(f"楼主「{AUTHOR}」发言: {len(mine)} 条")
    if posts:
        print(f"时间跨度: {posts[0]['time']} ~ {posts[-1]['time']}")
    from collections import Counter
    print("发言最多的作者 top10:")
    for k, v in Counter(x['author'] for x in posts).most_common(10):
        print(f"   {v:>4}  {k}")


if __name__ == '__main__':
    main()
