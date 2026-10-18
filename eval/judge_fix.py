#!/usr/bin/env python3
"""Исправлена ли названная ошибка: судья видит исходник, пометку учебника и его правку как образец.

Ранжирование «что живее» шумит; узкий вопрос «ошибка исправлена: да/нет» с эталоном перед глазами — нет.
Варианты под случайными буквами, названия судье не сообщаются. Откат к исходнику судья не решает:
его считает сводка по сходству слов.

    python3 judge_fix.py pairs.jsonl arms/ --ids r001,m010 --variants slovo,slovo_full,plain --out judged_fix/
"""
import argparse
import json
import os
import random
import tempfile

from judge_blind import ask, parse

PROMPT = """Ты проверяешь редакторскую правку русской фразы. Учебник по литературному редактированию указывает в ИСХОДНИКЕ ошибку и даёт ОБРАЗЕЦ исправления. Ниже {n} варианта правки под буквами {letters}; кто правил, неизвестно.

Для каждого варианта ответь на два вопроса.
1. fixed: названная ошибка устранена? Не обязательно так же, как в образце: любой способ, после которого этой ошибки нет. Если вариант повторяет исходник или ошибка осталась — false.
2. meaning: смысл по сравнению с ИСХОДНИКОМ цел? «ok» — всё, что утверждается, на месте (можно убрать пустые слова и повторы); «shifted» — пропало ограничение, оговорка, условие, участник, сменились время, вид действия, причинная связь или оценка, появилось то, чего не было. Кратко назови, что сдвинулось.

Ответь ТОЛЬКО одним JSON-объектом:
{{{example}}}

ОШИБКА ПО УЧЕБНИКУ: {note}

ИСХОДНИК:
{source}

ОБРАЗЕЦ ИСПРАВЛЕНИЯ:
{gold}

{blocks}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("arms")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--variants", default="slovo,slovo_full,plain")
    ap.add_argument("--judge", default="codex")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    pairs = {str(d["id"]): d for d in map(json.loads, open(a.pairs))}
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="slovo-judge-")
    for i in a.ids.split(","):
        path = f"{a.out}/{i}.{a.judge}.json"
        if os.path.exists(path):
            continue
        have = [v for v in a.variants.split(",") if os.path.exists(f"{a.arms}/{i}.{v}.md")]
        order = have[:]
        random.Random(f"{a.seed}-{i}").shuffle(order)
        letters = "ABCDEFGH"[:len(order)]
        blocks = "\n\n".join(f"ВАРИАНТ {l}:\n{open(f'{a.arms}/{i}.{v}.md').read().strip()}"
                             for l, v in zip(letters, order))
        d = pairs[i]
        prompt = PROMPT.format(n=len(order), letters=", ".join(letters), note=d.get("note", ""),
                               source=d["before"], gold=d["after"], blocks=blocks,
                               example=", ".join(f'"{l}": {{"fixed": true, "meaning": "ok", "what": ""}}'
                                                 for l in letters))
        raw = ask(a.judge, prompt, work)
        res = parse(raw)
        json.dump({"id": i, "judge": a.judge, "mapping": dict(zip(letters, order)), "result": res,
                   "raw": None if res else raw[-800:]}, open(path, "w"), ensure_ascii=False, indent=1)
        print(i, "ok" if res else "НЕ РАЗОБРАНО", flush=True)


if __name__ == "__main__":
    main()
