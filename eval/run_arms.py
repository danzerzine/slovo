#!/usr/bin/env python3
"""Прогоняет тексты через варианты правки и складывает результат на диск.

Варианты:
  slovo     — модель с инструкцией slovo (SKILL.md, для текстов от 150 слов ещё reference.md);
  plain     — то же задание без скилла: проверка «скилл включён / выключен»;
  humanize  — «перепиши по-человечески» без скилла (по желанию, --arms slovo,plain,humanize).

Каждый запуск — `claude -p` из пустой папки, без пользовательских настроек и скиллов, без
инструментов. Готовые файлы пропускаются, так что прогон можно прерывать и продолжать.

    python3 run_arms.py pairs.jsonl --ids 3,8,11 --out arms/ --model sonnet
"""
import argparse
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..", "slovo")
ASK = {
    "slovo": "Отредактируй этот текст по правилам из инструкции. Верни только готовый текст, без пояснений.",
    "slovo2": "Отредактируй этот текст по правилам из инструкции. Верни только готовый текст, без пояснений.",
    "plain": "Отредактируй этот текст. Верни только готовый текст, без пояснений.",
    "humanize": "Перепиши этот текст по-человечески, без канцелярита и штампов, ничего не меняя по смыслу. "
                "Верни только готовый текст, без пояснений.",
}


def skill_file(words):
    parts = [os.path.join(SKILL, "SKILL.md")]
    if words >= 150:
        parts.append(os.path.join(SKILL, "reference.md"))
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    for p in parts:
        f.write(open(p).read() + "\n\n")
    f.close()
    return f.name


def run(arm, text, model, workdir):
    cmd = ["claude", "-p", "--model", model, "--no-session-persistence", "--setting-sources", "project",
           "--disable-slash-commands", "--tools", ""]
    sf = None
    if arm.startswith("slovo"):                  # slovo2 — рабочая копия скилла против прежних ответов slovo
        sf = skill_file(len(text.split()))
        cmd += ["--append-system-prompt-file", sf]
    prompt = ASK[arm] + "\n\n" + text                          # через stdin: --tools забирает позиционные слова
    try:
        r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, input=prompt, timeout=300)
        return r.stdout.strip()
    finally:
        if sf:
            os.unlink(sf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs")
    ap.add_argument("--ids", required=True, help="номера пар через запятую")
    ap.add_argument("--out", required=True)
    ap.add_argument("--arms", default="slovo,plain")
    ap.add_argument("--model", default="sonnet")
    a = ap.parse_args()
    pairs = {}
    for line in open(a.pairs):
        d = json.loads(line)
        pairs[str(d["id"])] = d
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="slovo-run-")                 # пустая папка: ни CLAUDE.md, ни файлов проекта
    for i in a.ids.split(","):
        d = pairs[i]
        open(f"{a.out}/{i}.before.md", "w").write(d["before"] + "\n")
        open(f"{a.out}/{i}.human.md", "w").write(d["after"] + "\n")
        for arm in a.arms.split(","):
            path = f"{a.out}/{i}.{arm}.md"
            if os.path.exists(path) and os.path.getsize(path):
                continue
            out = run(arm, d["before"], a.model, work)
            if not out:
                print(i, arm, "ПУСТО, файл не записан", flush=True)
                continue
            open(path, "w").write(out + "\n")
            print(i, arm, len(out.split()), flush=True)


if __name__ == "__main__":
    main()
