#!/usr/bin/env python3
"""Прогоняет тексты через варианты правки и складывает результат на диск.

Варианты:
  slovo     — модель с инструкцией slovo (SKILL.md, для текстов от 150 слов ещё reference.md);
  plain     — то же задание без скилла: проверка «скилл включён / выключен»;
  humanize  — «перепиши по-человечески» без скилла (по желанию, --arms slovo,plain,humanize);
  slovo-<раздел> — скилл без одного раздела SKILL.md (проверка правил по одному, см. DROP);
  slovo-old — SKILL.md до уточнения глубины правки (44ae39f), для сравнения на других жанрах;
  slovo-head — SKILL.md из последнего коммита: рабочая копия (slovo) против него;
  slovo-rep — полный скилл ещё раз: разброс между прогонами для сравнения с вкладом разделов;
  slovo_full — скилл с терминалом: модель сама запускает check.py и перечитывает отмеченное.

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
    "slovo_full": "Отредактируй текст из файла source.md по правилам из инструкции, включая раздел «Проверка»: "
                  "в терминале есть python3, папка скилла — {skill}. Готовую правку запиши в result.md, "
                  "только текст, без пояснений.",
    "plain": "Отредактируй этот текст. Верни только готовый текст, без пояснений.",
    "humanize": "Перепиши этот текст по-человечески, без канцелярита и штампов, ничего не меняя по смыслу. "
                "Верни только готовый текст, без пояснений.",
}

DROP = {"norewrite": "## Переписать полностью", "nocheck": "## Проверка", "nogram": "## Грамотность",
        "nodont": "## Не трогай", "noinv": "## Инварианты"}


def without(text, heading):
    out, skip = [], False
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            skip = line.startswith(heading)
        if not skip:
            out.append(line)
    return "".join(out)


def skill_file(words, drop=None):
    parts = [os.path.join(SKILL, "SKILL.md")]
    if words >= 150:
        parts.append(os.path.join(SKILL, "reference.md"))
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False)
    for i, p in enumerate(parts):
        t = open(p).read()
        if drop in ("old", "head") and i == 0:            # old — до правки глубины (44ae39f), head — последний коммит
            rev = "44ae39f" if drop == "old" else "HEAD"
            t, drop = subprocess.run(["git", "-C", SKILL, "show", f"{rev}:slovo/SKILL.md"],
                                     capture_output=True, text=True, check=True).stdout, None
        f.write((without(t, DROP[drop]) if drop and i == 0 else t) + "\n\n")
    f.close()
    return f.name


def run_full(text, model):
    """Скилл целиком: модель сама пишет файлы, запускает check.py и перечитывает отмеченные места."""
    work = tempfile.mkdtemp(prefix="slovo-full-")
    open(os.path.join(work, "source.md"), "w").write(text + "\n")
    sf = skill_file(len(text.split()))
    cmd = ["claude", "-p", "--model", model, "--no-session-persistence", "--setting-sources", "project",
           "--disable-slash-commands", "--tools", "Bash,Read,Write,Edit",
           "--allowedTools", "Bash(python3:*),Read,Write,Edit", "--append-system-prompt-file", sf]
    prompt = ASK["slovo_full"].format(skill=os.path.abspath(SKILL))
    try:
        subprocess.run(cmd, cwd=work, capture_output=True, text=True, input=prompt, timeout=600)
        out = os.path.join(work, "result.md")
        return open(out).read().strip() if os.path.exists(out) else ""
    finally:
        os.unlink(sf)


def run(arm, text, model, workdir):
    if arm == "slovo_full":
        return run_full(text, model)
    cmd = ["claude", "-p", "--model", model, "--no-session-persistence", "--setting-sources", "project",
           "--disable-slash-commands", "--tools", ""]
    sf = None
    if arm.startswith("slovo"):                  # slovo2 — рабочая копия скилла против прежних ответов slovo
        drop = arm.split("-", 1)[1] if "-" in arm else None
        sf = skill_file(len(text.split()), None if drop == "rep" else drop)
        cmd += ["--append-system-prompt-file", sf]
    prompt = ASK[arm.split("-")[0]] + "\n\n" + text                          # через stdin: --tools забирает позиционные слова
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
