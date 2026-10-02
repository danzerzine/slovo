"""corrupt.py: build the eval set from edited texts.

Takes ~400-word excerpts of publication-edited texts (gold), injects known errors and records where.
  python corrupt.py SRC_DIR ID [ID ...] --out set/ [--words 400] [--seed 1]
Writes set/ID.gold.md, set/ID.in.md, set/ID.sites.json (sites in token coordinates of gold and in).
"""
import argparse, json, random, re
from pathlib import Path

TOK = re.compile(r"\w+|[^\w\s]|\s+")


def toks(s):
    return TOK.findall(s)


def excerpt(text, words):
    paras, out, n = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()], [], 0
    for p in paras:
        out.append(p.strip()); n += len(p.split())
        if n >= words: break
    return "\n\n".join(out) + "\n"


def is_w(t):
    return bool(re.match(r"\w", t))


# Each corruptor: (kind, class, fn(tokens, i) -> (span_len, replacement) or None). Applied at token i of gold.
def drop_comma(t, i):  # ", что" → " что"
    if t[i] == "," and i + 2 < len(t) and t[i + 1] == " " and re.fullmatch(r"(что|чтобы|котор\w+)", t[i + 2], re.I):
        return 1, []


def hyphen_space(t, i):  # из-за → из за, кто-то → кто то
    if i + 2 < len(t) and t[i + 1] == "-" and (
        (t[i].lower() == "из" and t[i + 2] in ("за", "под"))
        or re.fullmatch(r"(то|либо|нибудь)", t[i + 2])
    ):
        return 3, [t[i], " ", t[i + 2]]


def glue(t, i):  # ". Слово" → ".Слово"
    if t[i] in ".!?" and i + 2 < len(t) and t[i + 1] == " " and re.match(r"[А-ЯЁ]", t[i + 2]):
        return 2, [t[i]]


def space_comma(t, i):  # "слово," → "слово ,"
    if t[i] == "," and i > 0 and is_w(t[i - 1]):
        return 1, [" ", ","]


def lower_after_dot(t, i):  # ". Однако" → ". однако" (common words only, not names)
    if t[i] in ".!?" and i + 2 < len(t) and t[i + 1] == " " and re.fullmatch(
        r"(Но|И|А|Однако|Это|Он|Она|Они|Мы|Я|В|На|Как|Что|Когда|Если|Так|Потом|Теперь|Там|Тут|Здесь|Все|Всё|При|После|Да|Нет)", t[i + 2]
    ):
        return 3, [t[i], " ", t[i + 2].lower()]


def tsya(t, i):  # -тся ↔ -ться
    w = t[i]
    if re.search(r"[а-яё]ться$", w) and len(w) > 6:
        return 1, [w[:-4] + "тся"]
    if re.search(r"[аеиоуяюэ]тся$", w) and len(w) > 6:
        return 1, [w[:-3] + "ться"]


def typo(t, i):  # swap two inner letters of a long lowercase word
    w = t[i]
    if re.fullmatch(r"[а-яё]{8,}", w):
        k = len(w) // 2
        if w[k] != w[k + 1]:
            return 1, [w[:k] + w[k + 1] + w[k] + w[k + 2:]]


STAMPS = ["Стоит отметить, что", "Важно подчеркнуть, что", "Необходимо отметить, что", "Следует сказать, что"]


def stamp(t, i):  # insert a lead-in stamp at a sentence start: ". Он" → ". Стоит отметить, что он"
    if t[i] in ".!?" and i + 2 < len(t) and t[i + 1] == " " and re.fullmatch(r"(Он|Она|Они|Это|Мы|Я|В|На|Все|Всё)", t[i + 2]):
        return 3, [t[i], " "] + toks(STAMPS[i % len(STAMPS)]) + [" ", t[i + 2].lower()]


GRAMMAR = [drop_comma, hyphen_space, glue, space_comma, lower_after_dot, tsya, typo]


def corrupt(gold, rnd, per_words=40, stamps=1):
    t = toks(gold)
    nwords = sum(1 for x in t if is_w(x))
    cand = []
    for i in range(len(t)):
        for f in GRAMMAR + [stamp]:
            r = f(t, i)
            if r: cand.append((i, f, r))
    rnd.shuffle(cand)
    want_g, want_s, taken, used = max(3, nwords // per_words), stamps, [], set()
    per_kind = {}
    for i, f, (n, rep) in cand:
        is_stamp = f is stamp
        if is_stamp and want_s <= 0: continue
        if not is_stamp and want_g <= 0: continue
        if per_kind.get(f.__name__, 0) >= max(2, want_g // 3 + 1) and not is_stamp: continue
        span = set(range(i - 3, i + n + 3))
        if span & used: continue
        used |= span; taken.append((i, n, rep, f.__name__, "stamp" if is_stamp else "grammar"))
        per_kind[f.__name__] = per_kind.get(f.__name__, 0) + 1
        if is_stamp: want_s -= 1
        else: want_g -= 1
    taken.sort()
    out, sites, pos = [], [], 0
    for i, n, rep, kind, cls in taken:
        out += t[pos:i]
        sites.append({"kind": kind, "class": cls, "gold": [i, i + n], "in": [len(out), len(out) + len(rep)],
                      "was": "".join(t[i:i + n]), "now": "".join(rep)})
        out += rep; pos = i + n
    out += t[pos:]
    return "".join(out), sites


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("ids", nargs="+"); ap.add_argument("--out", required=True)
    ap.add_argument("--words", type=int, default=400); ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    od = Path(a.out); od.mkdir(parents=True, exist_ok=True)
    for id_ in a.ids:
        gold = excerpt(Path(a.src, f"{id_}.md").read_text(encoding="utf-8"), a.words)
        bad, sites = corrupt(gold, random.Random(f"{a.seed}-{id_}"))
        (od / f"{id_}.gold.md").write_text(gold, encoding="utf-8")
        (od / f"{id_}.in.md").write_text(bad, encoding="utf-8")
        (od / f"{id_}.sites.json").write_text(json.dumps(sites, ensure_ascii=False, indent=1), encoding="utf-8")
        print(id_, len(gold.split()), "слов", len(sites), "порч:", ", ".join(s["kind"] for s in sites))
