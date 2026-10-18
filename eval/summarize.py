#!/usr/bin/env python3
"""Сводка слепой оценки: по каждому варианту правки — ранг живости у каждого судьи, пометки о фактах,
стопы и предупреждения check.py против исходника и доля изменённых слов.

    python3 summarize.py arms/ judged/ --ids 3,8,11

Ранг 1 — лучший. «Изменено слов» — доля слов исходника, которых нет на своём месте в правке:
показывает, насколько смело правил вариант, и помогает отличить вкус судьи от качества.
"""
import argparse
import collections
import difflib
import json
import os
import re
import subprocess
import tempfile

CHECK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "slovo", "check.py")


def changed_share(a, b):
    wa, wb = re.findall(r"\w+", a.lower()), re.findall(r"\w+", b.lower())
    same = sum(bl.size for bl in difflib.SequenceMatcher(None, wa, wb, autojunk=False).get_matching_blocks())
    return 1 - same / max(len(wa), 1)


def check(src, new):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/a.md", "w").write(src)
        open(f"{d}/b.md", "w").write(new)
        r = subprocess.run(["python3", CHECK, f"{d}/a.md", f"{d}/b.md", "--genre", "article"],
                           capture_output=True, text=True)
    return "stop" if r.returncode else "warn" if "внимание:" in r.stdout else "clean"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arms")
    ap.add_argument("judged")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--json", help="куда записать построчные данные")
    a = ap.parse_args()
    ranks = collections.defaultdict(list)          # (judge, variant) -> ranks
    facts = collections.defaultdict(collections.Counter)
    firsts = collections.defaultdict(collections.Counter)
    checks = collections.defaultdict(collections.Counter)
    share = collections.defaultdict(list)
    rows = []
    for i in a.ids.split(","):
        src = open(f"{a.arms}/{i}.before.md").read()
        for f in sorted(os.listdir(a.arms)):
            m = re.match(rf"{re.escape(i)}\.([\w-]+)\.md$", f)
            if not m or m.group(1) == "before":
                continue
            v = m.group(1)
            new = open(f"{a.arms}/{f}").read()
            c = check(src, new)
            checks[v][c] += 1
            share[v].append(changed_share(src, new))
            rows.append({"id": i, "variant": v, "check": c, "changed": round(share[v][-1], 3)})
        for f in sorted(os.listdir(a.judged)):
            if not f.startswith(f"{i}."):
                continue
            d = json.load(open(f"{a.judged}/{f}"))
            res, mp, j = d.get("result"), d["mapping"], d["judge"]
            if not res:
                continue
            order = [x for x in res.get("alive_rank", []) if x in mp]
            for r, letter in enumerate(order, 1):
                ranks[(j, mp[letter])].append(r)
            if order:
                firsts[j][mp[order[0]]] += 1
            for letter, verdict in (res.get("facts") or {}).items():
                if letter in mp:
                    facts[(j, mp[letter])][verdict] += 1
            rows.append({"id": i, "judge": j, "rank": [mp[x] for x in order],
                         "facts": {mp[k]: v for k, v in (res.get("facts") or {}).items() if k in mp},
                         "note": res.get("note")})
    variants = sorted(share)
    judges = sorted({j for j, _ in ranks})
    print(f"текстов: {len(a.ids.split(','))}\n")
    print(f"{'вариант':10} {'изменено слов':>14} {'check: стоп/вним./чисто':>26}")
    for v in variants:
        s = sum(share[v]) / len(share[v])
        c = checks[v]
        print(f"{v:10} {s:>13.0%} {c['stop']:>10}/{c['warn']}/{c['clean']}")
    for j in judges:
        print(f"\nсудья {j}: средний ранг живости (1 — лучший), первых мест, факты ok/lost/added/both")
        for v in variants:
            r = ranks[(j, v)]
            fc = facts[(j, v)]
            avg = sum(r) / len(r) if r else float("nan")
            print(f"  {v:10} ранг {avg:.2f}  первых {firsts[j][v]:>2}  факты {fc['ok']}/{fc['lost']}/{fc['added']}/{fc['both']}")
    if a.json:
        json.dump(rows, open(a.json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
