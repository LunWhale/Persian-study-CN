#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate one or all content/*.jsonl writer files against spec.md.
Usage:
  python3 build/validate.py            # all files, brief
  python3 build/validate.py <file>     # one file
  python3 build/validate.py <file> --full   # one file, full report
Exit code 0 = all clean enough (only warnings), 1 = errors found.
"""
import json, re, sys, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

# ---------- Persian orthography whitelist ----------
FA_ALLOW = set()
def fa_add_range(lo, hi): FA_ALLOW.update(range(lo, hi + 1))
fa_add_range(0x0621, 0x063A)          # Arabic letters incl hamza forms
fa_add_range(0x0641, 0x0642)          # ف ق
fa_add_range(0x0644, 0x0648)          # ل م ن ه و
fa_add_range(0x0660, 0x0669)          # western digits used in Persian text
fa_add_range(0x06F0, 0x06F9)          # Persian digits
for cp in [0x067E, 0x0686, 0x0698, 0x06A9, 0x06AF, 0x06CC, 0x06C6, 0x06C7, 0x06C8,
           0x0622, 0x0621, 0x0623, 0x0624, 0x0626,          # آ ء أ ؤ ئ
           0x060C, 0x061B, 0x061F, 0x066B, 0x066C,          # ، ؛ ؟ ٫ ٬
           0x200C, 0x20, 0x09, 0x0A,
           ord('('), ord(')'), ord('['), ord(']'), ord('{'), ord('}'),
           ord('-'), ord('+'), ord('/'), ord('%'), ord('*'), ord('='),
           ord('.'), ord(','), ord(':'), ord(';'), ord('!'), ord('?'),
           ord('\u00ab'), ord('\u00bb'), ord('\u2018'), ord('\u2019'),
           ord('\u201c'), ord('\u201d'), ord('\u2026')]:
    FA_ALLOW.add(cp)

FA_FORBID = {
    0x0640,   # tatweel ـ
    0x0643,   # Arabic kaf ك
    0x0649,   # Arabic alef maksura ى
    0x064A,   # Arabic yeh ي
    0x0629,   # taa marbuta ة
    0x06D2,   # Urdu yeh ے
    0x06C1,   # Urdu heh ہ
    0x06BE,   # Urdu heh doachashmee ھ
    0x200B, 0x200D, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0xFEFF, 0x00A0,
}

ROMAN_EXTRA = set("āīūḵḡšžč")
ROMAN_RE = re.compile(r"^[a-zāīūḵḡšžč' \-]+$")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ASCII_WORD_RE = re.compile(r"[A-Za-z]{3,}")

CATEGORY_ORDER = [
    "core", "self", "numbers", "questions", "survival", "food", "shopping",
    "travel", "city", "timeweather", "home", "body", "emotions", "actions",
    "verbs2", "adverbs", "business", "religion", "culture",
]

def fa_problem(fa: str):
    """Return list of problems for fa string, else []."""
    probs = []
    if not fa or not fa.strip():
        return ["empty fa"]
    for ch in fa:
        o = ord(ch)
        if o in FA_FORBID:
            probs.append(f"forbidden char U+{o:04X} {unicodedata.name(ch,'?')}")
        elif o == 0x064B:
            probs.append("diacritic fathatan")
        elif o not in FA_ALLOW:
            probs.append(f"unexpected char U+{o:04X} {unicodedata.name(ch,'?')}")
    if "\u200b" in fa: probs.append("contains zero-width space")
    return probs

def roman_problem(rom: str):
    probs = []
    if not rom or not rom.strip(): return ["empty roman"]
    if rom != rom.strip() or rom != rom.lower(): probs.append("must be lowercase trimmed")
    if not ROMAN_RE.match(rom): probs.append("illegal characters in roman")
    return probs

def sound_problem(sound: str, rom: str):
    probs = []
    if not sound or not sound.strip(): return ["empty sound"]
    if not CJK_RE.search(sound): probs.append("sound needs Chinese characters")
    for w in ASCII_WORD_RE.findall(sound):
        if w.lower() not in (rom.lower() or ""):
            probs.append(f"English-like word '{w}' in sound")
    return probs

def validate_file(path: Path, full=False):
    errors, warnings = [], []
    rows, seen = 0, {}
    if not path.exists():
        return None, ["file missing"], []
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line: continue
        rows += 1
        try:
            obj = json.loads(line)
        except Exception as e:
            errors.append(f"line {ln}: JSON error {e}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {ln}: not an object"); continue
        missing = [k for k in ("fa", "roman", "cn", "sound", "note") if k not in obj]
        if missing:
            errors.append(f"line {ln}: missing {missing}"); continue
        for k in obj:
            if not isinstance(obj[k], str):
                errors.append(f"line {ln}: field {k} not string"); continue
            if k == "note" and not obj[k].strip():
                errors.append(f"line {ln}: empty note")
            if k in ("cn",) and not CJK_RE.search(obj[k]):
                errors.append(f"line {ln}: cn lacks Chinese")
        # --- new enhanced fields (optional, when present must be sane) ---
        if "syl" in obj:
            if not obj["syl"].strip():
                errors.append(f"line {ln}: empty syl")
            else:
                for p in roman_problem(obj["syl"].replace("·", "").replace("ˈ", "").replace("ˌ", "").replace("-", "")):
                    errors.append(f"line {ln}: syl: {p}")
        if "stress" in obj:
            if not re.fullmatch(r"\d+(-\d+)+|\d+", obj["stress"].strip()):
                errors.append(f"line {ln}: stress must be like 1 / 2-1 / 1-2")
        for p in fa_problem(obj["fa"]): errors.append(f"line {ln}: fa: {p}")
        for p in roman_problem(obj["roman"]): errors.append(f"line {ln}: roman: {p}")
        for p in sound_problem(obj["sound"], obj["roman"]): warnings.append(f"line {ln}: sound: {p}")
        norm = re.sub(r"[\u200c\s]+", "", obj["fa"])
        seen.setdefault(norm, []).append(ln)
    dups = {k: v for k, v in seen.items() if len(v) > 1}
    for k, v in dups.items():
        errors.append(f"duplicate fa (norm) lines {v}: {k[:30]}")
    if full:
        print(f"== {path.name}: {rows} rows, {len(errors)} errors, {len(warnings)} warnings")
        for e in errors[:80]: print("  E", e)
        for w in warnings[:60]: print("  W", w)
        if len(errors) > 80: print("  ...more errors truncated")
    return rows, errors, warnings

def main():
    args = sys.argv[1:]
    full = "--full" in args
    args = [a for a in args if a != "--full"]
    files = [CONTENT / a for a in args] if args else sorted(CONTENT.glob("*.jsonl"))
    total_e = 0
    for f in files:
        rows, errors, warnings = validate_file(f, full=full)
        if rows is None:
            print(f"{f.name}: MISSING"); total_e += 1; continue
        status = "OK" if not errors else f"{len(errors)} ERR"
        print(f"{f.name}: {rows} rows | {status}" + (f" | {len(warnings)} warn" if warnings else ""))
        total_e += len(errors)
    sys.exit(1 if total_e else 0)

if __name__ == "__main__":
    main()
