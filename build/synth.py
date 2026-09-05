#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Batch-synthesize Persian mp3s for content/*.jsonl with Microsoft edge-tts.

Resumable: existing valid mp3 files are skipped. Chunked run example:
  .venv/bin/python build/synth.py core self numbers        # only these cats
  .venv/bin/python build/synth.py --all                    # everything missing
  .venv/bin/python build/synth.py --list                   # pending counts
Voices: fa-IR-DilaraNeural (default, female); fa-IR-FaridNeural (male, --male).
Run inside the project directory.
"""
import asyncio, hashlib, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
AUDIO = ROOT / "audio" / "fa"
EDGE = ROOT / ".venv" / "bin" / "edge-tts"
CATS = ["core", "self", "numbers", "questions", "survival", "food", "shopping",
        "travel", "city", "timeweather", "home", "body", "emotions", "actions",
        "verbs2", "adverbs", "business", "religion", "culture"]
VOICE = "fa-IR-DilaraNeural"

def fa_hash(fa): return hashlib.sha1(fa.encode("utf-8")).hexdigest()[:16]

def collect_texts(cats):
    texts = set()
    for c in cats:
        p = CONTENT / f"{c}.jsonl"
        if not p.exists(): continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line: continue
            try: o = json.loads(line)
            except Exception: continue
            if isinstance(o, dict) and isinstance(o.get("fa"), str) and o["fa"].strip():
                texts.add(o["fa"].strip())
    return sorted(texts)

def pending(fas):
    out = []
    for fa in fas:
        mp3 = AUDIO / f"{fa_hash(fa)}.mp3"
        if not (mp3.exists() and mp3.stat().st_size > 500):
            out.append(fa)
    return out

async def synth(fas, voice=VOICE, concurrency=3):
    AUDIO.mkdir(parents=True, exist_ok=True)
    ok, fail = 0, []
    sem = asyncio.Semaphore(concurrency)
    async def one(fa):
        nonlocal ok
        async with sem:
            h = fa_hash(fa)
            mp3 = AUDIO / f"{h}.mp3"
            if mp3.exists() and mp3.stat().st_size > 500:
                ok += 1; return True
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(EDGE), "--voice", voice, "--text", fa, "--write-media", str(mp3),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                _, err = await proc.communicate()
                if proc.returncode == 0 and mp3.exists() and mp3.stat().st_size > 500:
                    ok += 1; return True
                fail.append((fa, err.decode(errors="ignore")[:100]))
                return False
            except Exception as e:
                fail.append((fa, str(e)[:100]))
                return False
    await asyncio.gather(*(one(f) for f in fas))
    return ok, fail

async def main():
    args = sys.argv[1:]
    if "--list" in args:
        todo = pending(collect_texts(CATS))
        print(f"pending mp3: {len(todo)} (existing cached: {len(collect_texts(CATS)) - len(todo)})")
        return
    cats = []
    if "--all" in args: cats = CATS
    else: cats = [a for a in args if a in CATS]
    if not cats:
        print(__doc__); return
    if "--male" in args: voice = "fa-IR-FaridNeural"
    else: voice = VOICE
    todo = pending(collect_texts(cats))
    print(f"synth {len(todo)} clips for {cats} voice={voice}")
    ok, fail = await synth(todo, voice=voice)
    print(f"ok={ok} fail={len(fail)}")
    for fa, e in fail[:20]:
        print("  FAIL:", fa[:60], "|", e)

if __name__ == "__main__":
    asyncio.run(main())
