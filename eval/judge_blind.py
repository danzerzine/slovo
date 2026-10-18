#!/usr/bin/env python3
"""Слепая оценка вариантов правки судьями из других семейств моделей (codex, qwen на ПК; gemini CLI закрыт Google).

Судья видит исходник и варианты под случайными буквами (порядок свой для каждого судьи) и
отвечает JSON: ранжирование по живости и пометки о потерянных или добавленных фактах.
Названия вариантов (человек, slovo, plain…) судье не сообщаются.

    python3 judge_blind.py arms/ --ids 3,8 --judges codex,qwen --out judged/

В arms/ ожидаются файлы ID.before.md, ID.human.md, ID.slovo.md, ID.plain.md ([ID.humanize.md]).
Готовые результаты пропускаются.
"""
import argparse
import json
import os
import random
import re
import subprocess
import tempfile
import urllib.request

QWEN = os.environ.get("QWEN_URL", "http://localhost:11435/api/generate")
VARIANTS = ["human", "slovo", "slovo2", "plain", "humanize"]
PROMPT = """Ты оцениваешь редакторскую правку русского текста. Ниже ИСХОДНИК и {n} варианта правки под буквами {letters}. Кто и как правил, неизвестно.

Оцени каждый вариант по двум осям.
1. Живость: насколько текст читается как написанный человеком, без канцелярита, штампов и неуклюжих оборотов. Ранжируй от лучшего к худшему (без ничьих).
2. Факты: сравни с исходником. «ok» — все факты, числа, имена, причинные связи и оговорки на месте; «lost» — что-то пропало или ослаблено; «added» — появилось то, чего в исходнике нет; «both» — и то и другое. Правка, которая просто не тронула текст, тоже «ok».

Ответь ТОЛЬКО одним JSON-объектом без пояснений вокруг:
{{"alive_rank": [буквы от лучшего к худшему], "facts": {{{facts_example}}}, "note": "до 20 слов о главном различии"}}

ИСХОДНИК:
{source}

{blocks}"""


def ask(judge, prompt, workdir):
    if judge == "codex":
        cmd = ["codex", "exec", "-s", "read-only", "--skip-git-repo-check", prompt]
    elif judge == "gemini":
        cmd = ["gemini", "-p", prompt]
    elif judge == "qwen":
        # qwen3:14b на ПК через туннель: ssh -N -L 11435:localhost:11434 pc; консольный ollama run ломает JSON
        body = json.dumps({"model": "qwen3:14b", "prompt": prompt, "stream": False, "format": "json",
                           "think": False, "options": {"temperature": 0}}).encode()
        req = urllib.request.Request(QWEN, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.load(r).get("response", "")
    else:
        raise SystemExit(f"неизвестный судья {judge}")
    r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=600)
    return r.stdout


def parse(out):
    for m in reversed(re.findall(r"\{.*\}", out, re.S)):
        try:
            return json.loads(m)
        except ValueError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arms")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--judges", default="codex,gemini")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="slovo-judge-")
    for i in a.ids.split(","):
        src = open(f"{a.arms}/{i}.before.md").read().strip()
        have = [v for v in VARIANTS if os.path.exists(f"{a.arms}/{i}.{v}.md")]
        for judge in a.judges.split(","):
            path = f"{a.out}/{i}.{judge}.json"
            if os.path.exists(path):
                continue
            rng = random.Random(f"{a.seed}-{i}-{judge}")
            order = have[:]
            rng.shuffle(order)
            letters = "ABCDE"[:len(order)]
            blocks = "\n\n".join(f"ВАРИАНТ {l}:\n{open(f'{a.arms}/{i}.{v}.md').read().strip()}"
                                 for l, v in zip(letters, order))
            prompt = PROMPT.format(n=len(order), letters=", ".join(letters), source=src, blocks=blocks,
                                   facts_example=", ".join(f'"{l}": "ok"' for l in letters))
            raw = ask(judge, prompt, work)
            res = parse(raw)
            json.dump({"id": i, "judge": judge, "mapping": dict(zip(letters, order)), "result": res,
                       "raw": None if res else raw[-800:]}, open(path, "w"), ensure_ascii=False, indent=1)
            print(i, judge, "ok" if res else "НЕ РАЗОБРАНО", flush=True)


if __name__ == "__main__":
    main()
