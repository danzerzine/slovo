#!/usr/bin/env python3
"""Собирает открытый корпус пар «первая версия → последняя версия» из ru.wikinews.org.

Тексты Викиновостей под CC BY 2.5 / CC BY-SA (см. страницу каждой статьи), поэтому
корпус можно хранить в репозитории. Пара годится, если правили минимум двое
участников, обе версии 150–900 слов и версии различаются, но не целиком.

    python3 build_corpus.py corpus/ --n 60 --seed 1

В папке появятся NNN.first.md, NNN.last.md и index.json (заголовок, id версий, авторы).
Только стандартная библиотека; запросы идут с User-Agent, как просит Викимедиа.
"""
import argparse
import difflib
import json
import random
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

API = "https://ru.wikinews.org/w/api.php"
UA = "slovo-eval/0.1 (https://github.com/danzerzine; corpus build)"


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


class Plain(HTMLParser):
    """Абзацы основного текста статьи; таблицы, сноски и служебные блоки пропускаются."""
    SKIP = {"table", "style", "script", "sup", "ul", "ol", "dl", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.in_p = False
        self.buf = []
        self.paras = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag == "p" and not self.depth:
            self.in_p = True
            self.buf = []

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag == "p" and self.in_p:
            self.in_p = False
            t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
            if t:
                self.paras.append(t)

    def handle_data(self, data):
        if self.in_p and not self.depth:
            self.buf.append(data)


def text_of(oldid):
    d = call(action="parse", oldid=oldid, prop="text", disablelimitreport=1)
    raw = d.get("parse", {}).get("text", {}).get("*", "")
    p = Plain()
    p.feed(raw)
    return "\n\n".join(p.paras)


def words(t):
    return len(re.findall(r"\w+", t))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    random.seed(a.seed)
    import os
    os.makedirs(a.out, exist_ok=True)
    index, seen = [], set()
    while len(index) < a.n:
        batch = call(action="query", list="random", rnnamespace=0, rnlimit=40)
        for pg in batch.get("query", {}).get("random", []):
            if len(index) >= a.n:
                break
            if pg["id"] in seen:
                continue
            seen.add(pg["id"])
            revs = call(action="query", prop="revisions", pageids=pg["id"], rvlimit=500,
                        rvprop="ids|user|size|comment", rvdir="newer")
            rv = next(iter(revs.get("query", {}).get("pages", {}).values()), {}).get("revisions", [])
            if len(rv) < 2 or len({r.get("user") for r in rv}) < 2:
                continue
            if any("redirect" in (r.get("comment") or "").lower() for r in rv):
                continue
            first, last = rv[0], rv[-1]
            if not (800 < first.get("size", 0) < 12000 and 800 < last.get("size", 0) < 12000):
                continue
            t1, t2 = text_of(first["revid"]), text_of(last["revid"])
            if not (150 <= words(t1) <= 900 and 150 <= words(t2) <= 900) or t1 == t2:
                continue
            ratio = difflib.SequenceMatcher(None, t1, t2, autojunk=False).ratio()
            if not 0.6 <= ratio <= 0.995:
                continue
            n = len(index) + 1
            open(f"{a.out}/{n:03d}.first.md", "w").write(t1 + "\n")
            open(f"{a.out}/{n:03d}.last.md", "w").write(t2 + "\n")
            index.append({"n": n, "title": pg["title"], "pageid": pg["id"],
                          "first_rev": first["revid"], "last_rev": last["revid"],
                          "users": sorted({r.get("user") for r in rv if r.get("user")}),
                          "similarity": round(ratio, 3), "words_first": words(t1)})
            print(n, pg["title"], round(ratio, 3), words(t1), flush=True)
    json.dump(index, open(f"{a.out}/index.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
