"""score.py: score slovo edits against the gold the errors were injected into.
  python score.py SET_DIR OUT_DIR [--check path/to/check.py] [--accepted accepted.tsv]
accepted.tsv: id<TAB>context<TAB>was<TAB>now — real errors of the published gold; an edit gold→out matching one
(same was/now, context in the text just before it) is a fix of the gold, not an extra edit.
For each site: fixed (out == gold there), missed (out == in there), other. Extra edits: gold→out diffs away from every site.
Writes OUT_DIR/_score.txt (per text, per kind, list of extras).
"""
import argparse, difflib, json, re, subprocess, sys
from collections import Counter, defaultdict
from pathlib import Path

TOK = re.compile(r"\w+|[^\w\s]|\s+")


def toks(s):
    return ["\n" if "\n" in x else " " if x.isspace() else x for x in TOK.findall(s.strip())]


def ops(a, b):
    return [(i1, i2, j1, j2) for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if t != "equal"]


def touches(op, span, tol=1):
    i1, i2 = op[0], op[1]
    g1, g2 = span
    return i1 < g2 + tol and i2 > g1 - tol if i1 != i2 else g1 - tol <= i1 <= g2 + tol


def in_quote(t, i):
    """Is token i inside «…» or a dialogue paragraph (starting with a dash)? A stamp there sits in someone's speech."""
    j = i
    while j > 0 and t[j - 1] != "\n": j -= 1
    para = t[j:i]
    return para.count("«") > para.count("»") or (para[:1] and para[0] in "—–-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("set"); ap.add_argument("out"); ap.add_argument("--check"); ap.add_argument("--accepted")
    a = ap.parse_args()
    S, O = Path(a.set), Path(a.out)
    kinds, totals, lines, extras_all, gold_fixes = defaultdict(Counter), Counter(), [], [], []
    acc = defaultdict(list)
    if a.accepted:
        for ln in Path(a.accepted).read_text(encoding="utf-8").splitlines():
            if ln.strip() and not ln.startswith("#"):
                i, ctx, was, now = (ln.split("\t") + ["", "", ""])[:4]
                acc[i].append((ctx, was, now))
    for sj in sorted(S.glob("*.sites.json")):
        id_ = sj.name.split(".")[0]
        of = O / f"{id_}.md"
        if not of.exists(): continue
        gold, bad, out = (toks(p.read_text(encoding="utf-8")) for p in (S / f"{id_}.gold.md", S / f"{id_}.in.md", of))
        sites = json.loads(sj.read_text(encoding="utf-8"))
        go, io = ops(gold, out), ops(bad, out)
        res = Counter()
        for s in sites:
            if s["class"] == "stamp" and in_quote(gold, s["gold"][0]):
                s["status"] = "in_quote"; kinds[s["kind"]]["in_quote"] += 1; continue
            st = "fixed" if not any(touches(o, s["gold"]) for o in go) else "missed" if not any(touches(o, s["in"]) for o in io) else "other"
            s["status"] = st; kinds[s["kind"]][st] += 1
            if s["class"] == "stamp": res["stamp_" + st] += 1; continue  # a single lead-in in a column may stay (SKILL.md): reported, not scored
            res[st] += 1
        extras = [o for o in go if not any(touches(o, s["gold"]) for s in sites)]
        words = sum(1 for x in gold if re.match(r"\w", x))
        word_ex = 0
        kept = []
        for i1, i2, j1, j2 in extras:
            g, n = "".join(gold[i1:i2]), "".join(out[j1:j2])
            left = "".join(gold[max(0, i1 - 12):i1])
            if any(g == w and n == v and c in left for c, w, v in acc[id_]):
                gold_fixes.append(f"{id_}\t…{left[-30:]}[{g!r} → {n!r}]"); continue
            kept.append((i1, i2, j1, j2))
        extras = kept
        for i1, i2, j1, j2 in extras:
            g, n = "".join(gold[i1:i2]), "".join(out[j1:j2])
            w = any(re.match(r"\w", x) for x in gold[i1:i2] + out[j1:j2])
            word_ex += w
            extras_all.append(f"{id_}\t{'слово' if w else 'знак'}\t…{''.join(gold[max(0, i1 - 12):i1])}[{g!r} → {n!r}]{''.join(gold[i2:i2 + 6])}…")
        chk = ""
        if a.check:
            r = subprocess.run([sys.executable, a.check, str(S / f"{id_}.gold.md"), str(of), "--genre", "article"], capture_output=True, text=True)
            chk = (r.stdout.strip().splitlines() or [""])[-1][:80]
        for s in sites:
            if s["status"] not in ("fixed", "in_quote") and s["class"] != "stamp":
                lines.append(f"  {id_} {s['kind']} {s['status']}: {s['was']!r}→{s['now']!r}")
        totals.update(res); totals["extra"] += len(extras); totals["extra_words"] += word_ex; totals["words"] += words; totals["texts"] += 1
        print(f"{id_}\tслов {words}\tпорч {len(sites)}\tпочинено {res['fixed']}\tпропущено {res['missed']}\tиначе {res['other']}\tлишних {len(extras)} (слова {word_ex})\t{chk}")
    t = totals
    n = t["fixed"] + t["missed"] + t["other"]
    summary = [f"\nТекстов {t['texts']}, слов {t['words']}, порч {n}: починено {t['fixed']} ({100 * t['fixed'] / max(n, 1):.0f} %), пропущено {t['missed']}, иначе {t['other']}.",
               f"Вставленные подводки (не в счёт: одиночная в колонке может остаться): сняты {t['stamp_fixed']}, оставлены {t['stamp_missed']}, иначе {t['stamp_other']}.",
               f"Ошибки самого эталона, исправленные правкой: {len(gold_fixes)} (правил в списке {sum(len(v) for v in acc.values())}; не в счёт лишних).",
               f"Лишних правок {t['extra']} ({1000 * t['extra'] / max(t['words'], 1):.1f} на 1000 слов), из них со словами {t['extra_words']}.",
               "\nПо типам порчи (починено/пропущено/иначе):"] + [f"  {k}: {v['fixed']}/{v['missed']}/{v['other']}" + (f" (в чужой речи, не считаются: {v['in_quote']})" if v['in_quote'] else "") for k, v in sorted(kinds.items())]
    print("\n".join(summary))
    (O / "_score.txt").write_text("\n".join(summary + ["\nНе починено:"] + lines + ["\nЛишние правки:"] + extras_all + ["\nОшибки эталона, исправленные правкой:"] + gold_fixes) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
