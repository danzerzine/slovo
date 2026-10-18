#!/usr/bin/env python3
"""Добывает из истории правок русской Википедии пары «абзац до → абзац после»,
которые участник пометил как стилистическую правку.

Тексты Википедии под CC BY-SA 4.0; в index.jsonl сохраняются название статьи и номера
версий, чтобы указать авторство. Пара годится, если в одной правке заменён абзац
(было и стало по 40–250 слов, похожи на 45–97 %), без шаблонов и ссылок-сносок.

    python3 mine_style_edits.py pairs.jsonl --windows 300 --seed 1

Окна выбираются случайно по времени (2010–2025), в каждом 500 подряд идущих правок
основного пространства; боты отбрасываются. Только стандартная библиотека.
"""
import argparse
import difflib
import html
import json
import random
import re
import time
import urllib.parse
import urllib.request

API = "https://ru.wikipedia.org/w/api.php"
UA = "slovo-eval/0.1 (research; https://github.com/danzerzine)"
# «Литературная деятельность» в названии раздела не считается: убираем /* … */ до проверки
STYLE = re.compile(r"стилист|(?<!\w)стил[ьею]|канцеляр|вычитк|редактур|причесал|разговорн|энциклопедичн|"
                   r"литературн\w* (?:правк|вид|язык)", re.I)
BOT = re.compile(r"bot\b|бот\b", re.I)


def call(**params):
    params["format"] = "json"
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (attempt + 1))
    return {}


def clean(t):
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", t)      # [[ссылка|текст]] -> текст
    t = re.sub(r"'{2,}", "", t)
    return re.sub(r"\s+", " ", t).strip()


def words(t):
    return len(re.findall(r"\w+", t))


def paragraph_pairs(frm, to):
    d = call(action="compare", fromrev=frm, torev=to, prop="diff").get("compare", {}).get("*", "")
    out = []
    for row in re.findall(r"<tr>(.*?)</tr>", d, re.S):
        dl = re.search(r'<td class="diff-deletedline[^>]*>(.*?)</td>', row, re.S)
        al = re.search(r'<td class="diff-addedline[^>]*>(.*?)</td>', row, re.S)
        if not (dl and al):
            continue
        a, b = clean(dl.group(1)), clean(al.group(1))
        if re.search(r"\{\{|\}\}|&lt;|\||^[=*#:;]|ref|File:|Файл:|http", a + b):
            continue
        if not (40 <= words(a) <= 250 and 40 <= words(b) <= 250) or a == b:
            continue
        r = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
        if 0.45 <= r <= 0.97:
            out.append((a, b, round(r, 3)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--windows", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    random.seed(a.seed)
    seen, n = set(), 0
    with open(a.out, "a") as f:
        for w in range(a.windows):
            ts = f"{random.randint(2010, 2025)}-{random.randint(1, 12):02d}-{random.randint(1, 27):02d}T{random.randint(0, 23):02d}:00:00Z"
            j = call(action="query", list="allrevisions", arvnamespace=0, arvlimit=500,
                     arvprop="ids|comment|user", arvstart=ts, arvdir="newer")
            for pg in j.get("query", {}).get("allrevisions", []):
                for r in pg["revisions"]:
                    c = re.sub(r"/\*.*?\*/", "", r.get("comment", ""))
                    if not (r.get("parentid") and STYLE.search(c)) or BOT.search(r.get("user", "")):
                        continue
                    if r["revid"] in seen:
                        continue
                    seen.add(r["revid"])
                    for before, after, ratio in paragraph_pairs(r["parentid"], r["revid"]):
                        n += 1
                        f.write(json.dumps({"id": n, "title": pg["title"], "revid": r["revid"],
                                            "parentid": r["parentid"], "user": r.get("user"),
                                            "comment": r.get("comment", "")[:200], "ratio": ratio,
                                            "before": before, "after": after}, ensure_ascii=False) + "\n")
                        f.flush()
                    time.sleep(0.3)
            print(f"окно {w + 1}/{a.windows}: пар {n}", flush=True)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
