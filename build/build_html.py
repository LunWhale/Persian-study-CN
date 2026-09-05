#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the final single-file HTML from content/*.jsonl + build/template.html.

Audio embedding: every card needs an mp3 at audio/fa/<sha1(fa)>.mp3. If the file
is missing it is *synthesized on the fly* via edge-tts (free Microsoft Persian
neural voice), so running this script once produces audio AND the HTML.
"""
import asyncio, base64, hashlib, html, json, re, subprocess, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
AUDIO = ROOT / "audio" / "fa"
OUT = ROOT / "波斯语入门学习.html"
TEMPLATE = Path(__file__).resolve().parent / "template.html"
PHONETICS = Path(__file__).resolve().parent / "phonetics.jsonl"
EDGE = ROOT / ".venv" / "bin" / "edge-tts"
VOICE_F = "fa-IR-DilaraNeural"
VOICE_M = "fa-IR-FaridNeural"
MAX_TEXT = 450  # hard cap for a single clip (chars)

CATEGORY_META = {
    "core": ("见面问候 · 礼貌口语", "第1组", "打招呼、道别、感谢、道歉——最常用，先背熟。"),
    "self": ("自我介绍 · 人物家庭", "第2组", "介绍自己、聊国家职业、说家人。"),
    "numbers": ("数字 · 时间 · 日期", "第3组", "数数、时间、星期与月份（含伊朗历）。"),
    "questions": ("提问 · 疑问词", "第4组", "会用问句，聊天就能继续。"),
    "survival": ("应急 · 求助 · 就医", "第5组", "旅行出状况时救命的一节。"),
    "food": ("饮食 · 点餐", "第6组", "点菜、买单、评价味道，伊朗美食必备。"),
    "shopping": ("购物 · 砍价 · 颜色", "第7组", "市场血拼与讨价还价。"),
    "travel": ("旅行 · 交通 · 住宿", "第8组", "机场、打车、酒店、问方向。"),
    "city": ("城市 · 地点", "第9组", "银行、邮局、换钱和公共场所。"),
    "timeweather": ("天气 · 自然", "第10组", "聊聊天气和季节。"),
    "home": ("居家 · 生活用品", "第11组", "房子、家具、日用品与家务。"),
    "body": ("身体 · 健康", "第12组", "身体部位、症状描述、就医句子。"),
    "emotions": ("情感 · 性格 · 评价", "第13组", "表达感受，夸人或委婉批评。"),
    "actions": ("常用动词 · 现在时", "第14组", "最常用的动作动词（带“我…”的说法）。"),
    "verbs2": ("动词 · 过去时", "第15组", "过去时怎么变，讲故事必备。"),
    "adverbs": ("副词 · 介词 · 虚词", "第16组", "把句子串起来的小词。"),
    "business": ("工作 · 办公 · 网络", "第17组", "上班开会、邮件电话、电脑手机。"),
    "religion": ("宗教 · 信仰用语", "第18组", "伊朗日常会听到的伊斯兰用语，中性了解。"),
    "culture": ("波斯文化 · 习俗 · 谚语", "第19组", "诗歌、诺鲁孜节、茶文化与吉祥话。"),
}
CAT_ORDER = list(CATEGORY_META)

def esc(s): return html.escape(s, quote=True)
def norm_key(fa): return re.sub(r"[\u200c\s]+", "", fa)

# ---------------- audio ----------------
def fa_hash(fa):
    return hashlib.sha1(fa.encode("utf-8")).hexdigest()[:16]

def synthesize_many(texts, out_root=AUDIO, voice=VOICE_F, concurrency=3):
    """Return {fa: mp3_path} for successfully synthesized texts."""
    out_root.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    results = {}
    async def one(fa):
        h = fa_hash(fa)
        mp3 = out_root / f"{h}.mp3"
        if mp3.exists() and mp3.stat().st_size > 500:
            results[fa] = mp3; return
        proc = await asyncio.create_subprocess_exec(
            str(EDGE), "--voice", voice, "--text", fa, "--write-media", str(mp3),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        if proc.returncode == 0 and mp3.exists() and mp3.stat().st_size > 500:
            results[fa] = mp3
        else:
            print("[synth-fail]", fa[:40], err.decode(errors="ignore")[:120])
    async def run():
        sem = asyncio.Semaphore(concurrency)
        async def guarded(fa):
            async with sem:
                await one(fa)
        await asyncio.gather(*(guarded(f) for f in texts))
    asyncio.run(run())
    return results

def b64_of(fa):
    mp3 = AUDIO / f"{fa_hash(fa)}.mp3"
    if mp3.exists() and mp3.stat().st_size > 500:
        return base64.b64encode(mp3.read_bytes()).decode("ascii")
    return ""

def playbtn(fa, label="▶"):
    b = b64_of(fa)
    if not b: return ""
    return f'<button class="play" data-src="{b}" aria-label="播放">{label}</button>'

# ---------------- phonetics classroom rows ----------------
def load_phonetics():
    rows = []
    if not PHONETICS.exists(): return rows
    for line in PHONETICS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line: continue
        try: o = json.loads(line)
        except Exception: continue
        rows.append(o)
    return rows

def phone_row_html(r, kind):
    """kind: vowel / letter / tricky → one <tr> or one .lett div."""
    def _b64(fa):
        return b64_of(fa)
    btn = lambda fa, extra="": (f'<button class="play mini" data-src="{_b64(fa)}">{extra}▶</button>' if _b64(fa) else "")
    if kind == "vowel":
        head = f'<span class="sym">{esc(r["sym"])}</span>'
        sf = r.get("sound_fa", "")
        b0 = f'<button class="play mini" data-src="{b64_of(sf)}" title="听音素">▶</button>' if sf and b64_of(sf) else ""
        name = f'{esc(r["name"])} · <span class="roman">{esc(r["name_cn"])}</span>'
        ex = (f'<span class="fa-eg">{esc(r["ex_fa"])}</span> '
              f'<span class="roman">{esc(r["ex_roman"])}</span> '
              f'<span class="snd">　谐音：{esc(r["ex_snd"])}</span>')
        return (f'<tr><td>{head} {b0}</td><td>{name}<div class="how">{esc(r["how"])}</div></td>'
                f'<td>{ex}</td><td style="text-align:right">{btn(r["ex_fa"])}</td></tr>')
    elif kind == "letter":
        b1 = btn(r["name_fa"], "名")
        b2 = btn(r["ex_fa"])
        return (f'<div class="lett"><div class="g">{esc(r["glyph"])}</div>'
                f'<div class="nm"><span class="nr">{esc(r["name_roman"])}</span> · <span class="nc">{esc(r["name_cn"])}</span>'
                f'<div class="how">{esc(r["how"])}</div>'
                f'<div><span class="fa-eg">{esc(r["ex_fa"])}</span> <span class="roman">{esc(r["ex_roman"])}</span> <span class="snd">{esc(r["ex_snd"])}</span></div>'
                f'<span class="minibtnwrap">{b1}{b2}</span></div></div>')
    elif kind == "tricky":
        head = f'<span class="sym">{esc(r["sym"])}</span>'
        name = f'{esc(r["glyph"])} · <span class="roman">{esc(r["name_cn"])}</span>'
        ex = (f'<span class="fa-eg">{esc(r["ex_fa"])}</span> '
              f'<span class="roman">{esc(r["ex_roman"])}</span> '
              f'<span class="snd">　谐音：{esc(r["ex_snd"])}</span>')
        return (f'<tr><td>{head}</td><td>{name}<div class="how">{esc(r["how"])}</div></td>'
                f'<td>{ex}</td><td style="text-align:right">{btn(r["ex_fa"])}</td></tr>')
    return ""

def phonetics_blocks():
    rows = load_phonetics()
    vowel_rows, lett_grid, tricky_rows = [], [], []
    for r in rows:
        k = r.get("kind")
        if k == "vowel": vowel_rows.append(phone_row_html(r, "vowel"))
        elif k == "letter": lett_grid.append(phone_row_html(r, "letter"))
        elif k == "tricky": tricky_rows.append(phone_row_html(r, "tricky"))
    # 纯 JS 内容（不带 <script> 标签），由模板内 <!--__PHONETICS__--> 注入
    return ("window.VOWELROWS=" + json.dumps("".join(vowel_rows), ensure_ascii=False) +
            ";window.LETTGRID=" + json.dumps("".join(lett_grid), ensure_ascii=False) +
            ";window.TRICKYROWS=" + json.dumps("".join(tricky_rows), ensure_ascii=False) + ";")

def demo_rows():
    return phonetics_blocks()  # backward compatibility no-op

# ---------------- cards ----------------
def syllable_html(syl):
    """syl e.g. 'sobh·be-ḵeyr' → spans with · and hyphen preserved, stress digits stripped."""
    if not syl: return ""
    out = []
    for chunk in re.split(r"([·\-])", syl):
        if chunk == "·": out.append('<span class="sdot">·</span>')
        elif chunk == "-": out.append('<span class="shyph">-</span>')
        elif chunk: out.append(f'<span class="syl">{esc(chunk)}</span>')
    return "".join(out)

def load_rows():
    rows, dup = [], set()
    for cat in CAT_ORDER:
        p = CONTENT / f"{cat}.jsonl"
        if not p.exists(): continue
        for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line: continue
            try: o = json.loads(line)
            except Exception as e:
                print(f"[skip] {cat}:{ln} JSON {e}"); continue
            if not all(k in o for k in ("fa", "roman", "cn", "sound", "note")): continue
            o["cat"] = cat
            rows.append(o)
    return rows

def render_cards(rows):
    """Group cards by category, return (accordions_html, cat_counts)."""
    by_cat = {c: [] for c in CAT_ORDER}
    for r in rows:
        by_cat[r["cat"]].append(r)
    cat_counts = {c: len(v) for c, v in by_cat.items()}

    # lookup: fa(原文) -> (roman, sound) 用于 note 行内注音
    fa_lookup = {}
    for rs in by_cat.values():
        for r in rs:
            fa_lookup.setdefault(norm_key(r["fa"]), (r["roman"], r["sound"]))
    # note_extra.jsonl 里额外为行内片段注音（无完整词条卡，只有音译）
    xp = Path(__file__).resolve().parent / "note_extra.jsonl"
    if xp.exists():
        for line in xp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try: o = json.loads(line)
            except Exception: continue
            fa_lookup.setdefault(norm_key(o.get("fa", "")), (o.get("roman", ""), o.get("snd", "")))
    def note_enhance(note_txt):
        """把 note 里出现的已知波斯语短语包成 ⟨inline⟩ 可点读+注音。"""
        # 按 fa 原文(规范化后) 最长优先匹配
        keys = sorted(fa_lookup, key=len, reverse=True)
        out = note_txt
        for k in keys:
            if k not in out: continue
            # 找到原始 fa 文本（从 lookup 的另一边不好取回，用 k 匹配原note中的无ZWNJ文本可能失败）
        # 简化：直接扫描 note 里形如 [\u0600-\u06FF]{2,} 的片段，若片段规范化后命中词库则包宏
        import re as _re
        def repl(m):
            frag = m.group(0)
            nk = norm_key(frag)
            if nk in fa_lookup:
                rom, snd = fa_lookup[nk]
                b = b64_of(frag)
                if not b: return frag
                return (f'<span class="nfa"><span class="nfa-txt">{esc(frag)}</span>'
                        f'<span class="nfa-rom">{esc(rom)}</span>'
                        f'<span class="nfa-snd">{esc(snd)}</span>'
                        f'<button class="play mini" data-src="{b}">▶</button></span>')
            return frag
        out = _re.sub(r'[\u0600-\u06FF\u200c][\u0600-\u06FF\u200c .\-]*', repl, out)
        return out

    accs = []
    for cat in CAT_ORDER:
        rs = by_cat[cat]
        if not rs: continue
        title, sub, _ = CATEGORY_META[cat]
        cards_html = []
        for r in rs:
            b = b64_of(r["fa"])
            audio = f'<button class="play" data-src="{b}" aria-label="播放">▶</button>' if b else ""
            syl, stress = r.get("syl", ""), r.get("stress", "")
            pron_parts = []
            if syl:
                pron_parts.append(f'<span class="pronsyl">逐音节 {syllable_html(syl)}</span>')
            if stress:
                pron_parts.append(f'<span class="prstress">重音<span class="st">{esc(stress)}</span></span>')
            pron_html = f'<div class="row-pron">{"".join(pron_parts)}</div>' if pron_parts else ""
            note = note_enhance(r["note"])
            cards_html.append(
                f'<div class="card" data-cat="{cat}">'
                f'<div class="row1"><div class="fa">{esc(r["fa"])}</div>{audio}</div>'
                f'<div class="row2"><span class="zh">{esc(r["cn"])}</span>'
                f'<span class="rlc">转写 <span class="roman">{esc(r["roman"])}</span></span>'
                f'<span class="snd">谐音 <span class="hb">{esc(r["sound"])}</span></span></div>'
                f'{pron_html}'
                f'<div class="note">{note}</div>'
                f'</div>')
        accs.append(
            f'<details class="acc" data-total="{len(rs)}">'
            f'<summary><span>📁 {esc(title)}</span><span class="cnt">{len(rs)}</span>'
            f'<span class="subx">{esc(sub)}</span><span class="chev">▼</span></summary>'
            f'<div class="accbody"><div class="grid">{"".join(cards_html)}</div></div>'
            f'</details>')
    return "\n".join(accs), cat_counts

def md_to_html(md):
    out, para = [], []
    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>"); para.clear()
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            flush(); out.append(f'<h3>{esc(line[2:])}</h3>')
        elif line.startswith("## "):
            flush(); out.append(f'<h4>{esc(line[3:])}</h4>')
        elif line.startswith("### "):
            flush(); out.append(f'<h5>{esc(line[4:])}</h5>')
        elif line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
        elif re.match(r"^\s*[-*]\s+", line):
            flush()
            out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif re.match(r"^\s*\d+\.\s+", line):
            flush()
            out.append("<li>" + inline(re.sub(r"^\s*\d+\.\s+", "", line)) + "</li>")
        elif not line.strip():
            flush()
        else:
            para.append(inline(line))
    flush()
    out2, i = [], 0
    while i < len(out):
        if out[i].startswith("<li>"):
            j = i
            while j < len(out) and out[j].startswith("<li>"): j += 1
            out2.append("<ul>" + "".join(out[i:j]) + "</ul>"); i = j
        elif out[i].startswith("<tr>"):
            j = i
            while j < len(out) and out[j].startswith("<tr>"): j += 1
            out2.append('<div style="overflow-x:auto"><table>' + "".join(out[i:j]) + "</table></div>"); i = j
        else:
            out2.append(out[i]); i += 1
    return "\n".join(out2)

def inline(t):
    """Grammar md inline: 「pron」→ span.pron; **bold**; ⟨fa|rom|谐音|?⟩ macro → inline playable Persian."""
    def fa_macro(m):
        inner = m.group(1)
        parts = [p.strip() for p in inner.split("‖")]
        fa_txt, rom, snd = parts[0], (parts[1] if len(parts) > 1 else ""), (parts[2] if len(parts) > 2 else "")
        b = b64_of(fa_txt)
        btn = f'<button class="play mini" data-src="{b}" aria-label="播放">▶</button>' if b else ""
        s = f'<span class="gfa">{esc(fa_txt)}</span>'
        if rom: s += f' <span class="grom">{esc(rom)}</span>'
        if snd: s += f' <span class="gsnd">{esc(snd)}</span>'
        return f'<span class="gmac">{s}{btn}</span>'
    t = re.sub(r"「([^」]+)」", lambda m: f'<span class="pron">{esc(m.group(1))}</span>', t)
    t = re.sub(r"⟨([^⟩]+)⟩", fa_macro, t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    return t

def build(force_tts=True):
    rows = load_rows()
    seen, keep = set(), []
    for r in rows:
        k = (r["cat"], norm_key(r["fa"]))
        if k in seen: print("[drop dup]", r["cat"], r["fa"]); continue
        seen.add(k); keep.append(r)
    rows = keep

    need = []
    for r in rows:
        r["h"] = fa_hash(r["fa"])
        mp3 = AUDIO / f"{r['h']}.mp3"
        if not (mp3.exists() and mp3.stat().st_size > 500):
            need.append(r["fa"])
    # phonetics extras
    extra_texts = set()
    for p in load_phonetics():
        if p.get("ex_fa"): extra_texts.add(p["ex_fa"])
        if p.get("name_fa"): extra_texts.add(p["name_fa"])
    # note_extra extras
    xp = Path(__file__).resolve().parent / "note_extra.jsonl"
    if xp.exists():
        for line in xp.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try: o = json.loads(line)
            except Exception: continue
            if o.get("fa"): extra_texts.add(o["fa"])
    for t in extra_texts:
        mp3 = AUDIO / f"{fa_hash(t)}.mp3"
        if not (mp3.exists() and mp3.stat().st_size > 500):
            need.append(t)
    need = list(dict.fromkeys(need))

    if force_tts and need:
        print(f"synthesizing {len(need)} clips (edge-tts, {VOICE_F})…")
        ok = synthesize_many(need)
        missing = [f for f in need if f not in ok]
        print("done:", len(ok), "ok,", len(missing), "failed")
    else:
        missing = [t for t in need if not (AUDIO / f"{fa_hash(t)}.mp3").exists()]
        print("no synth run; audio missing:", len(missing))

    cards, cat_counts = render_cards(rows)
    print("total rows:", len(rows), "| audio embedded:", cards.count('data-src="'))

    cat_buttons = "".join(
        f'<button class="catbtn" data-cat="{c}" onclick="filterCat(\'{c}\')">{esc(m[0])}'
        f'<span class="cnt">{cat_counts.get(c, 0)}</span></button>'
        for c, m in CATEGORY_META.items())
    stats = json.dumps({c: {"title": CATEGORY_META[c][0], "count": cat_counts.get(c, 0),
                            "sub": CATEGORY_META[c][1]} for c in CAT_ORDER}, ensure_ascii=False)

    tpl = TEMPLATE.read_text(encoding="utf-8")
    gpath = ROOT / "build" / "grammar_cn.md"
    grammar_html = md_to_html(gpath.read_text(encoding="utf-8")) if gpath.exists() else \
        "<h3>语法指南文件缺失（build/grammar_cn.md）</h3>"
    ph = phonetics_blocks()
    doc = (tpl.replace("<!--__ACCORDIONS__-->", cards)
               .replace("<!--__CARDS__-->", "")
               .replace("<!--__GRAMMAR__-->", grammar_html)
               .replace("<!--__PHONETICS__-->", ph)
               .replace("const STATS = {};", "const STATS = " + stats + ";"))
    OUT.write_text(doc, encoding="utf-8")
    print("wrote:", OUT, OUT.stat().st_size, "bytes")

if __name__ == "__main__":
    build(force_tts=("--no-tts" not in sys.argv))
