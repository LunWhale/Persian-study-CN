#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Force re-synthesize ALL audio files with slow rate (-15%)."""
import asyncio, hashlib, json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "audio" / "fa"
EDGE = ROOT / ".venv" / "bin" / "edge-tts"
RATE = "-15%"

def h(fa): return hashlib.sha1(fa.encode("utf-8")).hexdigest()[:16]

# 收集所有需要音频的 fa 文本：content + phonetics + note_extra + grammar 宏
# 只合成含波斯字母(U+0600-06FF)的文本；grammar 宏里纯拉丁示范词(ketāb/dūstā)跳过
import unicodedata
def has_fa(t):
    return any('\u0600' <= c <= '\u06FF' for c in t)

texts = {}
def reg(fa):
    if fa and has_fa(fa): texts.setdefault(fa, True)

for p in (ROOT / "content").glob("*.jsonl"):
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        o = json.loads(line)
        reg(o.get("fa"))
for line in (ROOT / "build" / "phonetics.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip(): continue
    o = json.loads(line)
    reg(o.get("name_fa")); reg(o.get("ex_fa")); reg(o.get("sound_fa"))
for line in (ROOT / "build" / "note_extra.jsonl").read_text(encoding="utf-8").splitlines():
    if not line.strip(): continue
    reg(json.loads(line).get("fa"))
for line in (ROOT / "build" / "grammar_cn.md").read_text(encoding="utf-8").splitlines():
    for m in re.findall(r"⟨([^⟩]+)⟩", line):
        reg(m.split("‖")[0].strip())

all_texts = sorted(texts)
print("total texts:", len(all_texts), flush=True)

async def synth_all():
    sem = asyncio.Semaphore(4)
    ok, fail = 0, []
    async def one(fa):
        nonlocal ok
        async with sem:
            mp3 = AUDIO / f"{h(fa)}.mp3"
            try:
                mp3.unlink(missing_ok=True)
            except Exception:
                pass
            proc = await asyncio.create_subprocess_exec(
                str(EDGE), "--voice", "fa-IR-DilaraNeural", f"--rate={RATE}",
                "--text", fa, "--write-media", str(mp3),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate()
            if proc.returncode == 0 and mp3.exists() and mp3.stat().st_size > 500:
                ok += 1
            else:
                fail.append((fa, err.decode(errors="ignore")[:100]))
    await asyncio.gather(*(one(f) for f in all_texts))
    print("done ok:", ok, "fail:", len(fail), flush=True)
    for fa, err in fail[:20]:
        print("FAIL:", fa, err, flush=True)

asyncio.run(synth_all())
