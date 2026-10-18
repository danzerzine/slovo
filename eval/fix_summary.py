#!/usr/bin/env python3
"""Сводка по учебным парам: исправил ошибку, откатил к исходнику, сдвинул смысл; совпадение правки с учебником.

Откат — правка почти не отличается от исходника (сходство слов ≥ 0.95) и ошибка не исправлена.
Совпадение — какие слова исходника тронуты: точность (тронутое вариантом тронуто и учебником) и полнота
(тронутое учебником тронуто вариантом). Интервалы — бутстреп по парам, 95 %.

    python3 fix_summary.py pairs.jsonl arms/ judged_fix/ --ids r001,m010 [--variants slovo,slovo_full,plain]
"""
import argparse
import difflib
import json
import random


def words(t):
    return t.split()


def touched(src, new):
    s = set()
    for op, i1, i2, _, _ in difflib.SequenceMatcher(None, src, new, autojunk=False).get_opcodes():
        if op != "equal":
            s.update(range(i1, i2) if i2 > i1 else [i1 - 0.5])          # вставка — между словами
    return s


def ci(xs, n=2000):
    rng = random.Random(0)
    m = [sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(n)]
    m.sort()
    return sum(xs) / len(xs), m[int(n * .025)], m[int(n * .975)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("arms")
    ap.add_argument("judged")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--variants", default="slovo,slovo_full,plain")
    ap.add_argument("--judge", default="codex")
    a = ap.parse_args()
    pairs = {str(d["id"]): d for d in map(json.loads, open(a.pairs))}
    ids = a.ids.split(",")
    rows = {v: [] for v in a.variants.split(",")}
    for i in ids:
        j = json.load(open(f"{a.judged}/{i}.{a.judge}.json"))
        if not j["result"]:
            continue
        inv = {v: k for k, v in j["mapping"].items()}
        src, gold = words(pairs[i]["before"]), words(pairs[i]["after"])
        tg = touched(src, gold)
        for v in rows:
            r = j["result"].get(inv.get(v, "?"))
            if not r:
                continue
            new = words(open(f"{a.arms}/{i}.{v}.md").read())
            tv = touched(src, new)
            fixed = bool(r.get("fixed"))
            rows[v].append({"id": i, "fixed": fixed, "shift": r.get("meaning") != "ok", "what": r.get("what", ""),
                            "revert": not fixed and difflib.SequenceMatcher(None, src, new).ratio() >= .95,
                            "prec": len(tv & tg) / len(tv) if tv else 1.0,
                            "rec": len(tv & tg) / len(tg) if tg else 1.0,
                            "rec_": bool(pairs[i].get("reconstructed")), "book": i[0]})
    print(f"пар: {len(ids)}; интервалы 95 % (бутстреп)\n")
    print(f"{'вариант':<11}{'исправил':>18}{'откатил':>18}{'смысл сдвинут':>18}{'точность':>10}{'полнота':>9}")
    for v, rs in rows.items():
        cells = []
        for k in ("fixed", "revert", "shift"):
            m, lo, hi = ci([float(r[k]) for r in rs])
            cells.append(f"{m:5.0%} [{lo:.0%}–{hi:.0%}]")
        p, rc = (sum(r[k] for r in rs) / len(rs) for k in ("prec", "rec"))
        print(f"{v:<11}" + "".join(f"{c:>18}" for c in cells) + f"{p:>10.0%}{rc:>9.0%}")
    print("\nисправил, по срезам:")
    for name, f in [("Розенталь", lambda r: r["book"] == "r"), ("Мильчин", lambda r: r["book"] == "m"),
                    ("фраза дана целиком", lambda r: not r["rec_"]), ("достроена по обрывку", lambda r: r["rec_"])]:
        print(f"  {name:<22}" + "  ".join(f"{v} {sum(r['fixed'] for r in rs if f(r)) / max(1, sum(map(f, rs))):.0%}"
                                          for v, rs in rows.items()) + f"  (n={sum(map(f, next(iter(rows.values()))))})")
    json.dump(rows, open(f"{a.judged}/rows.local.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
