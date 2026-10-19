#!/usr/bin/env python3
"""Пары из собственных сообщений автора: какой вариант ближе к тому, что он в итоге отправил.

Судья видит исходник, итоговый текст автора как образец и варианты под случайными буквами. Он ранжирует
варианты по близости к образцу в голосе (слова, интонация, манера от первого лица) и длине, и для каждого
отмечает, цел ли смысл исходника. Без судьи сводка считает сходство слов с образцом и отношение длин.

    python3 judge_own.py pairs.jsonl arms/ --ids u01,u03 --variants slovo,slovo-head,plain --out judged_own/
    python3 judge_own.py pairs.jsonl arms/ --ids u01,u03 --variants slovo,slovo-head,plain --out judged_own/ --summary
"""
import argparse
import difflib
import json
import os
import random
import tempfile

from judge_blind import ask, parse

PROMPT = """Автор отдал свой черновик на редактуру, а потом отправил свою версию: она ниже как ОБРАЗЕЦ. Ниже {n} варианта правки под буквами {letters}; кто правил, неизвестно.

1. rank: упорядочь буквы от самого близкого к ОБРАЗЦУ до самого далёкого. Близость — это голос автора (его слова, интонация, разговорная манера от первого лица, без казённой гладкости и рубленых лозунгов) и длина (насколько вариант сократил или раздул текст по сравнению с образцом). Совпадение отдельных слов само по себе не важно.
2. meaning: для каждой буквы — цел ли смысл по сравнению с ИСХОДНИКОМ: «ok» или «shifted» (пропал или появился факт, оговорка, условие, участник, оценка). Кратко назови, что сдвинулось.

Ответь ТОЛЬКО одним JSON-объектом:
{{"rank": [{letters_q}], {example}}}

ИСХОДНИК:
{source}

ОБРАЗЕЦ (что автор отправил):
{gold}

{blocks}"""


def words(t):
    return t.split()


def summary(a, pairs, ids):
    vs = a.variants.split(",")
    st = {v: {"rank": [], "sim": [], "len": [], "shift": 0, "n": 0} for v in vs}
    first = {v: 0 for v in vs}
    for i in ids:
        gold = words(pairs[i]["after"])
        for v in vs:
            new = words(open(f"{a.arms}/{i}.{v}.md").read())
            st[v]["sim"].append(difflib.SequenceMatcher(None, new, gold, autojunk=False).ratio())
            st[v]["len"].append(len(new) / max(1, len(gold)))
        p = f"{a.out}/{i}.{a.judge}.json"
        j = json.load(open(p)) if os.path.exists(p) else {}
        if not j.get("result"):
            continue
        m, r = j["mapping"], j["result"]
        for pos, l in enumerate(r.get("rank", [])):
            v = m.get(l)
            if v in st:
                st[v]["rank"].append(pos + 1)
                first[v] += pos == 0
        for l, v in m.items():
            if v in st and isinstance(r.get(l), dict):
                st[v]["n"] += 1
                st[v]["shift"] += r[l].get("meaning") != "ok"
    print(f"пар: {len(ids)}\n{'вариант':<12}{'ср. место':>10}{'первый':>8}{'сходство':>10}{'длина/обр.':>12}{'сдвиг':>8}")
    for v, s in st.items():
        mr = sum(s["rank"]) / len(s["rank"]) if s["rank"] else float("nan")
        print(f"{v:<12}{mr:>10.2f}{first[v]:>8}{sum(s['sim']) / len(s['sim']):>10.0%}"
              f"{sorted(s['len'])[len(s['len']) // 2]:>12.2f}{s['shift']:>5}/{s['n']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("arms")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--variants", default="slovo,slovo-head,plain")
    ap.add_argument("--judge", default="codex")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    pairs = {str(d["id"]): d for d in map(json.loads, open(a.pairs))}
    ids = a.ids.split(",")
    os.makedirs(a.out, exist_ok=True)
    if a.summary:
        return summary(a, pairs, ids)
    work = tempfile.mkdtemp(prefix="slovo-judge-")
    for i in ids:
        path = f"{a.out}/{i}.{a.judge}.json"
        if os.path.exists(path):
            continue
        order = a.variants.split(",")
        random.Random(f"{a.seed}-{i}").shuffle(order)
        letters = "ABCDEFGH"[:len(order)]
        blocks = "\n\n".join(f"ВАРИАНТ {l}:\n{open(f'{a.arms}/{i}.{v}.md').read().strip()}"
                             for l, v in zip(letters, order))
        d = pairs[i]
        prompt = PROMPT.format(n=len(order), letters=", ".join(letters), source=d["before"], gold=d["after"],
                               blocks=blocks, letters_q=", ".join(f'"{l}"' for l in letters),
                               example=", ".join(f'"{l}": {{"meaning": "ok", "what": ""}}' for l in letters))
        res = parse(ask(a.judge, prompt, work))
        json.dump({"id": i, "judge": a.judge, "mapping": dict(zip(letters, order)), "result": res},
                  open(path, "w"), ensure_ascii=False, indent=1)
        print(i, "ok" if res else "НЕ РАЗОБРАНО", flush=True)


if __name__ == "__main__":
    main()
