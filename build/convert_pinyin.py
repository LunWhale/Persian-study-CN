#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert all romanization to pinyin-friendly scheme + correct syllable splitting.

Mapping (for Chinese beginners who only know pinyin):
  š -> sh   č -> ch   ž -> zh   ḵ -> h   ḡ -> g   q -> k
  ā/ī/ū stay (pinyin tone marks, learners know them)
Long vowels in 谐音: 拖长一倍 (already present in most sounds).
Also recompute syl (syllable split) and stress (stress = index of stressed
syllable in the dot-split syl string, 1-based; phrase stress = last word's
last syllable, stored as that index).
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

# ---- letter-unit tokenizer: sh/ch/zh are single consonant units ----
CONS2 = {"sh", "ch", "zh"}
VOWELS = set("aeiouāīū")

def tokenize(w):
    """split roman word into phoneme units (sh/ch/zh single)."""
    w = w.replace("'", "")
    out = []
    i = 0
    while i < len(w):
        two = w[i:i+2]
        if two in CONS2 or two == "kh":  # kh legacy fallback
            out.append(two); i += 2
        else:
            out.append(w[i]); i += 1
    return out

def syllabify_word(w):
    """Return list of syllable strings for one word (pinyin letters)."""
    units = tokenize(w)
    if not units:
        return []
    # vowel positions
    vpos = [i for i, u in enumerate(units) if u in VOWELS]
    if not vpos:
        return [w]
    if len(vpos) == 1:
        return [w]
    # multiple vowels: greedy left-to-right
    # onset: consonants before first vowel, keep only last as onset unless none
    # coda: consonants between vowels, 0..1 (allow 2 only at word end)
    syls = []
    cur = []
    for i, u in enumerate(units):
        cur.append(u)
        if u in VOWELS and i != vpos[-1]:
            # look ahead: next unit after this vowel
            nxt = units[i+1] if i+1 < len(units) else ""
            nxt2 = units[i+2] if i+2 < len(units) else ""
            if nxt and nxt not in VOWELS and nxt2 and nxt2 in VOWELS:
                # consonant between two vowels -> onset of next syllable
                syls.append("".join(cur)); cur = []
            elif nxt and nxt not in VOWELS and (not nxt2 or nxt2 not in VOWELS):
                # one trailing consonant (word end or CC coda)
                syls.append("".join(cur)); cur = []
            else:
                syls.append("".join(cur)); cur = []
    if cur:
        syls.append("".join(cur))
    return syls

def convert_roman(rom):
    rom = rom.strip()
    rom = rom.replace("š", "sh").replace("č", "ch").replace("ž", "zh")
    rom = rom.replace("ḵ", "h").replace("ḡ", "g")
    rom = rom.replace("q", "k")
    # collapse repeated spaces
    rom = re.sub(r"\s+", " ", rom)
    return rom

def recompute_syl_stress(rom):
    """rom: pinyin-style roman. Return (syl_str, stress_str)."""
    rom = convert_roman(rom)
    words = [w for w in re.split(r"[ \-]+", rom) if w]
    all_syls = []
    for w in words:
        syls = syllabify_word(w)
        all_syls.append(syls)
    # syl: join word syllables with ·, words with space? For UI clarity use
    # words joined by ' ' and syllables by '·'? Existing code splits on · and -.
    # Use single dot-list across whole phrase: word boundary = space is lost.
    # Better: words joined by ' / '? Keep it simple: all syllables joined by '·',
    # phrase-level word boundaries shown separately in UI via words list.
    flat = [s for ws in all_syls for s in ws]
    syl = "·".join(flat) if flat else rom
    # stress: last syllable of last word (primary); also mark each word's last
    # syllable as secondary? Keep primary only for simplicity: index of last flat syllable
    n = len(flat)
    stress = str(n) if n else "1"
    return syl, stress, [syls for syls in all_syls]

def process_file(p: Path, out: Path):
    lines = p.read_text(encoding="utf-8").splitlines()
    changed = 0
    for i, line in enumerate(lines):
        if not line.strip(): continue
        o = json.loads(line)
        if "roman" in o:
            nr = convert_roman(o["roman"])
            if nr != o["roman"]:
                o["roman"] = nr
            syl, stress, _ = recompute_syl_stress(nr)
            # only update syl/stress if they were auto or missing; keep handcrafted core? 
            # We recompute always for consistency.
            o["syl"] = syl
            o["stress"] = stress
            lines[i] = json.dumps(o, ensure_ascii=False)
            changed += 1
    if changed:
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed

def main():
    total = 0
    for p in sorted(CONTENT.glob("*.jsonl")):
        c = process_file(p, p)
        total += c
        print(p.name, c)
    # phonetics.jsonl: name_roman/ex_roman convert; add pinyin name
    ph = ROOT / "build" / "phonetics.jsonl"
    if ph.exists():
        lines = ph.read_text(encoding="utf-8").splitlines()
        c = 0
        for i, line in enumerate(lines):
            o = json.loads(line)
            for k in ("name_roman", "ex_roman", "sym"):
                if k in o:
                    nr = convert_roman(o[k])
                    if nr != o[k]:
                        o[k] = nr
            # how text mentions š etc? leave; add pinyin alias
            lines[i] = json.dumps(o, ensure_ascii=False)
            c += 1
        ph.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("phonetics.jsonl", c)
    # note_extra.jsonl
    ne = ROOT / "build" / "note_extra.jsonl"
    if ne.exists():
        lines = ne.read_text(encoding="utf-8").splitlines()
        c = 0
        for i, line in enumerate(lines):
            o = json.loads(line)
            if "roman" in o:
                nr = convert_roman(o["roman"])
                if nr != o["roman"]:
                    o["roman"] = nr
                lines[i] = json.dumps(o, ensure_ascii=False)
                c += 1
        ne.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("note_extra.jsonl", c)
    print("done", total)

if __name__ == "__main__":
    main()
