"""Compare a rewrite with its source: lost facts, shifted meaning markers, dashes, rhythm, length.

Usage: python3 check.py source.md rewrite.md [--glossary glossary.md]
Exit code 1 (hard stop) if a number, code, link or `fragment` was lost; if a new one appeared that is
in neither the source nor the glossary; if a number changed its unit (5 % → 5 п. п.); or if a dash
disappeared from prose that is still there (a dash that left with a wholly deleted sentence, a
heading or a table cell is a warning; so is «3» → «три» or «в 2 раза» → «вдвое»). Under 150 words the
length and rewrite thresholds are not applied; --genre article lowers the rewrite threshold from a half
to a third; --shortened (the author asked to cut) drops the thresholds and lets a number leave with a
wholly deleted sentence as a warning. Everything else is a warning: a place to reread against the source, not a verdict.
A proofread stays quiet: «Было-бы» → «было бы», «не велик» → «невелик» and a stop put back between two glued
sentences raise nothing.
"""

import argparse
import difflib
import re
import statistics
import sys
from collections import Counter

# Words that carry weight, scope, cause and certainty, with the direction in which a change is
# suspicious. Tuned on a real rewrite of 32 analytical reports: these words caught real distortions,
# and words that mostly fired on honest glosses («без фото», «только каждая десятая») were dropped.
MARKERS = {
    "оценка": (r"резк\w*|обвал\w*|рухн\w*|катастроф\w*|драматич\w*|рекорд\w*|лидер\w*|колоссальн\w*"
               r"|беспрецедентн\w*|стремительн\w*|кардинальн\w*|революционн\w*|взрывн\w*", "+"),
    "кратность": (r"вдвое|втрое|вчетверо|в\s+(?:\d+(?:[.,]\d+)?|два|три|четыре|пять|десять)\s+раза?", "+"),
    "охват": (r"всей|весь|вся|всю|целиком|полностью|никогда|всегда|ни\s+од(?:ин|на|но|ной|ного)", "+"),
    "причина": (r"из-за|поэтому|потому\s+что|вызван\w*|вызвал\w*|привел\w*|привёл\w*|привод\w*|благодаря"
                r"|следовательно|помога\w*|помогл\w*|влия\w*|повлия\w*|объясн\w*|(?<!в\s)связ\w*", "±"),
    "оговорка": (r"примерно|около|порядка|почти|вероятно|возможно|может|могут|скорее|похоже|видимо"
                 r"|предположительно|по-видимому|гипотез\w*|доказан\w*|проверял\w*|сверял\w*", "-"),
    "«бы»": (r"бы", "+"),
    # a lost «не» flips the claim: «не доказан» → «доказан», «не проверяли» → «проверяли»
    "отрицание": (r"не|ни|нет", "-"),
    # a lost «только» widens the claim; an added one is mostly an honest gloss, so only loss counts
    "сужение": (r"только|лишь", "-"),
}
MARKER_RE = {k: re.compile(rf"(?<![\w-])(?:{v})(?![\w-])", re.I) for k, (v, _) in MARKERS.items()}
SCOPED_HEDGE = re.compile(r"не\s+доказан\w*|не\s+проверял\w*|не\s+сверял\w*|предположительно"
                          r"|по-видимому|вероятно|возможно|скорее всего", re.I)

KANTS = re.compile(
    r"(?<!\w)(?:являет\w*|являют\w*|данн(?:ый|ая|ое|ые|ого|ой|ом|ых|ым)|в рамках|в целях|с целью|имеет место"
    r"|осуществля\w*|в связи с|на данный момент|в терминах|на ежедневной основе|адресовать)(?!\w)"
    r"|(?<!\w)\w{3,}(?:ние|ния|нию|нием|нии|ций|ция|цию|цией|ции)(?!\w)",
    re.I,
)
NUMBER = re.compile(r"(?<![\w.])\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?|(?<![\w.])\d+(?:[.,:]\d+)*")
# A number with the unit that changes its meaning. Dates (25.09) are not numbers with units.
UNIT = re.compile(r"(?<![\w.])(\d{1,3}(?:[  ]\d{3})+(?:,\d+)?|\d+(?:,\d+)?)(?![.\d])\s?"
                  r"(%|п\.\s?п\.|процентн\w*\s+пункт\w*|раза?\b|млн|млрд|тыс\.?|мс\b|₽|руб\w*|коп\w*|\$|€|"
                  r"долл\w*|евро\b|чел\w*|сек\w*|с\b|мин\w*|ч\b|час\w*|сут\w*|дн\w*|день|недел\w*|нед\.|"
                  r"мес\w*|год\w*|лет\b|г\.)", re.I)
# Order matters: the first prefix that fits names the unit («чел» before «ч», «мс» before «м…»).
UNIT_NAME = {"п.п.": "п. п.", "проц": "п. п.", "раз": "раз", "млн": "млн", "млрд": "млрд", "тыс": "тыс.",
             "мс": "мс", "%": "%", "₽": "₽", "руб": "₽", "коп": "коп.", "$": "$", "долл": "$", "€": "€",
             "евро": "€", "чел": "чел.", "сек": "с", "с": "с", "мин": "мин", "час": "ч", "ч": "ч", "сут": "дн.",
             "дн": "дн.", "день": "дн.", "нед": "нед.", "мес": "мес.", "год": "год", "лет": "год", "г.": "год"}
CODE = re.compile(r"(?<!\w)[A-ZА-ЯЁ]{1,4}\d+[a-zа-я0-9-]*(?!\w)")
# A number written as a word: «3 месяца» → «три месяца», «в 2 раза» → «вдвое» keeps the fact.
NUMBER_WORDS = {
    "1": r"один|одна|одно|одного|одной|одному|одну|одним|одном",
    "2": r"два|две|двух|двум|двумя|вдвое|дважды",
    "3": r"три|трёх|трех|трём|трем|тремя|втрое|трижды",
    "4": r"четыре|четырёх|четырех|четырём|четырем|четырьмя|вчетверо",
    "5": r"пять|пяти|пятью|впятеро",
    "6": r"шесть|шести|шестью|вшестеро",
    "7": r"семь|семи|семью",
    "8": r"восемь|восьми|восемью",
    "9": r"девять|девяти|девятью",
    "10": r"десять|десяти|десятью|вдесятеро",
    "100": r"сто|ста",
    "1000": r"тысяча|тысячи|тысячу|тысячей|тысяч",
}
NUMBER_WORD_RE = {n: re.compile(rf"(?<![\w-])(?:{v})(?![\w-])", re.I) for n, v in NUMBER_WORDS.items()}


def strip_code(text):
    return re.sub(r"```.*?```", "", text, flags=re.S)


def norm_num(n):
    return re.sub(r"[  ]", "", n)


def facts(text):
    out = set(re.findall(r"`([^`]+)`", text))
    out |= set(re.findall(r"\]\(([^)]+)\)", text))
    out |= {norm_num(n) for n in NUMBER.findall(text)}
    out |= set(CODE.findall(text))
    return out


def unit_of(u):
    u = re.sub(r"\s", "", u.lower())
    for k, v in UNIT_NAME.items():
        if u.startswith(k):
            return v
    return u


def units(text):
    """Number → set of units it is used with."""
    out = {}
    for n, u in UNIT.findall(strip_code(text)):
        out.setdefault(norm_num(n), set()).add(unit_of(u))
    return out


def number_counts(text):
    return Counter(norm_num(n) for n in NUMBER.findall(strip_code(text)))


def spelled(src, new):
    """Numbers that only changed form: a digit lost while its word appeared, or the other way round."""
    out = set()
    for n, rx in NUMBER_WORD_RE.items():
        ws, wn = len(rx.findall(strip_code(src))), len(rx.findall(strip_code(new)))
        cs, cn = number_counts(src)[n], number_counts(new)[n]
        # the total (digits + words) must hold: «3 месяца, 3 %» → «три месяца» still lost a 3
        if cs + ws == cn + wn and cs != cn:
            out.add(n)
    return out


def multiples(text):
    """Values of «в 2 раза», «в два раза», «вдвое»: a multiplier only changed in form is not a new one."""
    out = set()
    for m in MARKER_RE["кратность"].findall(text):
        d = re.search(r"\d+(?:[.,]\d+)?", m)
        out |= {norm_num(d.group())} if d else {n for n, rx in NUMBER_WORD_RE.items() if rx.search(m)}
    return out


def dashes(text):
    return {"—": text.count("—"), "–": text.count("–")}


def prose_lines(text):
    for line in strip_code(text).splitlines():
        s = line.strip()
        if s and not s.startswith(("|", "#", ">")):
            yield re.sub(r"^[-*\d.]+\s+", "", s)


def table_heading_lines(text):
    return "\n".join(s for s in (ln.strip() for ln in strip_code(text).splitlines()) if s.startswith(("|", "#")))


# Two sentences glued without a space («Алёша.После») are two sentences: a proofread that adds the space
# must not read as a split. Three letters before the stop keep «ул.Ленина» and «т.Е» whole.
GLUED_STOP = r"|(?<=[^\W\d_]{3}[.!?…])(?=[A-ZА-ЯЁ])"


def sentences(text):
    parts = re.split(r"(?<=[.!?…])\s+(?=[«\"(A-ZА-ЯЁ])" + GLUED_STOP, " ".join(prose_lines(text)))
    return [p for p in parts if len(p.split()) >= 2]


def nwords(text):
    """Words, not tokens: a comma or dash cut off by spaces («текст , и») is not a word."""
    return sum(1 for w in text.split() if re.search(r"\w", w))


def cv(lengths):
    if len(lengths) < 3:
        return 0.0
    return statistics.pstdev(lengths) / statistics.mean(lengths)


def paragraphs(text):
    """Blocks split by blank lines, with the line number each starts on; code blocks are skipped."""
    out, buf, start, in_code = [], [], 0, False
    for i, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.strip():
            if not buf:
                start = i
            buf.append(line.strip())
        elif buf:
            out.append((start, " ".join(buf)))
            buf = []
    if buf:
        out.append((start, " ".join(buf)))
    return out


def summary_split(text):
    """Top summary = text before the first «## » heading if it has real prose, else the first ## section."""
    parts = re.split(r"(?m)^(?=## )", text)
    if len(" ".join(prose_lines(parts[0])).split()) >= 40 or len(parts) < 2:
        return parts[0], "".join(parts[1:])
    return parts[0] + parts[1], "".join(parts[2:])


# Synonyms of one kind of link count as one word: «потому что» → «поэтому» is not a shift,
# «помогает» → «связаны» is (an effect became a correlation).
SAME = {"пото": "поэт", "из-з": "поэт", "благ": "поэт", "след": "поэт",
        "вызв": "влия", "прив": "влия", "помо": "влия", "пов": "влия", "объя": "влия"}


def stem(word):
    """Crude stem so that «доказано» and «доказаны», «связь» and «связан» count as one word."""
    w = re.sub(r"\s+", " ", word.lower().replace("ё", "е"))
    w = w if len(w) <= 4 else w[:4]
    return SAME.get(w, w)


def words_only(text):
    return re.findall(r"\w+", text.lower().replace("ё", "е"))


def proofread_only(src, new):
    """Spelling, commas, spaces and capitals only: the words are the same once glued words are split
    and split ones glued («Алёша.После», «не велик» → «невелик», «Было-бы» → «Было бы»)."""
    a, b = "".join(words_only(src)), "".join(words_only(new))
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.98


def stops_restored(src, new):
    """Rhythm fell only because missing stops were put back: same words, and no comma became a stop.
    A long sentence chopped at its commas keeps its words too, so it still warns."""
    commas = lambda s: len(re.findall(r"[,;:]", s))
    return proofread_only(src, new) and commas(new) >= commas(src)


def unglue_particles(text):
    """«Было-бы» is a misspelt «было бы», not a new «бы»; «только-только» is still two «только»."""
    text = re.sub(r"(?<![\w-])(\w+)-(\1)(?![\w-])", r"\1 \2", text, flags=re.I)
    return re.sub(r"(?<=\w)-(?=(?:бы|ли|же)(?![\w-]))", " ", text, flags=re.I)


def glued_negations(old, cur):
    """«не велик» → «невелик» joins «не» to its word; the negation is still there."""
    return sum(1 for w in re.findall(r"(?<![\w-])не\s+(\w+)", old, re.I)
               if re.search(rf"(?<![\w-])не{re.escape(w)}(?!\w)", cur, re.I))


def markers(text):
    return {k: Counter(stem(m) for m in r.findall(text)) for k, r in MARKER_RE.items()}


def words_for(text, kind, stems):
    seen = {}
    for m in MARKER_RE[kind].findall(text):
        seen.setdefault(stem(m), m.lower())
    return sorted(seen.get(s, s) for s in stems)


def said_in_source(cur, kind, st, src_bigrams):
    """True if every new use of the marker stands next to the same word somewhere in the source."""
    toks = re.findall(r"[\w-]+", cur.lower().replace("ё", "е"))
    hits = [i for i, t in enumerate(toks) if MARKER_RE[kind].fullmatch(t) and stem(t) == st]
    if not hits:
        return False
    for i in hits:
        pair = {(stem(toks[i - 1]), st) if i else None, (st, stem(toks[i + 1])) if i + 1 < len(toks) else None}
        if not pair & src_bigrams:
            return False
    return True


def bigrams(text):
    toks = [stem(t) for t in re.findall(r"[\w-]+", text.lower().replace("ё", "е"))]
    return set(zip(toks, toks[1:]))


def content_words(s):
    return {w for w in re.findall(r"\w+", s.lower()) if len(w) >= 4}


def split_hedges(old_sents, new_sents):
    """A sentence whose hedge covered two claims was cut in two, and the hedge stayed with the first half."""
    out = []
    for s in old_sents:
        h = SCOPED_HEDGE.search(s)
        if not h or s in new_sents or ";" in s[h.end():]:
            continue
        ws = content_words(s)
        for i, a in enumerate(new_sents[:-1]):
            b = new_sents[i + 1]
            if not SCOPED_HEDGE.search(a) or SCOPED_HEDGE.search(b) or not ws:
                continue
            wa, wb = content_words(a), content_words(b)
            if len(ws & wa) / len(ws) >= 0.3 and wb and len(ws & wb) / len(wb) >= 0.4:
                out.append(b)
    return out


def around(text, kind, st):
    """A few words around the first use of the marker, to find the place and judge it."""
    for m in MARKER_RE[kind].finditer(text):
        if stem(m.group()) == st:
            left = text[:m.start()].split()[-5:]
            right = text[m.end():].split()[:5]
            return " ".join(left + [m.group()] + right)
    return ""


def line_of(text, sentence):
    pos = text.find(sentence[:40])
    return text.count("\n", 0, pos) + 1 if pos >= 0 else 0


def marker_shifts(src, new):
    """For every changed run of sentences: suspicious markers gained or lost, new numbers, split hedges."""
    ss, sn = sentences(src), sentences(new)
    sm = difflib.SequenceMatcher(None, ss, sn, autojunk=False)
    src_bi = bigrams(src)
    src_nums = {norm_num(n) for n in NUMBER.findall(src)}
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        old, cur = " ".join(ss[i1:i2]), " ".join(sn[j1:j2])
        line = line_of(new, sn[j1]) if j1 < j2 else 0
        mo, mn = markers(unglue_particles(old)), markers(unglue_particles(cur))
        notes = []
        for k, (_, direction) in MARKERS.items():
            plus = [st for st in (mn[k] - mo[k]) if not said_in_source(cur, k, st, src_bi)]
            if k == "кратность" and multiples(cur) <= multiples(old):
                plus = []
            minus = list((mo[k] - mn[k]).elements())
            if k in ("отрицание", "сужение") and op == "delete":
                minus = []  # the whole sentence is gone, not flipped
            if k == "отрицание":
                for _ in range(glued_negations(old, cur)):
                    if "не" in minus:
                        minus.remove("не")
            if plus and direction in "+±":
                where = around(cur, k, plus[0])
                line = line_of(new, where) or line
                notes.append(f"{k} +{'/'.join(words_for(cur, k, plus))}: «…{where}…»")
            if minus and direction in "-±":
                notes.append(f"{k} −{'/'.join(words_for(old, k, minus))}: было «…{around(old, k, minus[0])}…»")
        new_nums = {norm_num(n) for n in NUMBER.findall(cur)} - src_nums
        if new_nums:
            notes.append(f"новые числа {sorted(new_nums)}")
        uo, un = units(old), units(cur)
        for n in sorted(set(uo) & set(un)):
            if un[n] - uo[n]:  # a new unit for this number; a dropped one is a lost or respelled number
                notes.append(f"число сменило единицу: {n} {'/'.join(sorted(uo[n]))} → {n} {'/'.join(sorted(un[n]))}")
        if op != "delete" and (dashes(cur)["—"] < dashes(old)["—"] or dashes(cur)["–"] < dashes(old)["–"]):
            notes.append("в этом месте пропало тире: проверь, удалена ли фраза целиком")
        for b in split_hedges(ss[i1:i2], sn[j1:j2]):
            notes.append(f"оговорка осталась в соседней фразе, а эта читается как факт: «{b[:60]}…»")
        if notes:
            out.append((line, notes))
    return out


def similar(a, b):
    wa, wb = re.findall(r"\w+", a.lower()), re.findall(r"\w+", b.lower())
    return difflib.SequenceMatcher(None, wa, wb, autojunk=False).ratio()


def changed_share(src, new, keep=0.75):
    """Share of source sentences rewritten in earnest: deleted, or whose closest
    counterpart in the rewrite shares less than `keep` of its words. A comma or one
    swapped word leaves a sentence counted as kept."""
    ss, sn = sentences(src), sentences(new)
    if not ss:
        return 0.0
    sm = difflib.SequenceMatcher(None, ss, sn, autojunk=False)
    changed = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        for s in ss[i1:i2]:
            if max((similar(s, t) for t in sn[j1:j2]), default=0) < keep:
                changed += 1
    return changed / len(ss)


def dash_loss(src, new):
    """Dashes lost overall, minus those that left with wholly deleted sentences or from headings and
    tables (a rewritten heading or cell is a place to reread, not a hard stop)."""
    ds, dn = dashes(src), dashes(new)
    ss, sn = sentences(src), sentences(new)
    ts, tn = dashes(table_heading_lines(src)), dashes(table_heading_lines(new))
    gone = {k: max(ts[k] - tn[k], 0) for k in ts}
    for op, i1, i2, _, _ in difflib.SequenceMatcher(None, ss, sn, autojunk=False).get_opcodes():
        if op == "delete":
            for k, v in dashes(" ".join(ss[i1:i2])).items():
                gone[k] += v
    total = {k: max(ds[k] - dn[k], 0) for k in ds}
    return {k: max(total[k] - gone[k], 0) for k in ds}, {k: min(total[k], gone[k]) for k in ds}


def deleted_text(src, new):
    """Sentences of the source that the rewrite dropped whole (not rewritten, not merged)."""
    ss, sn = sentences(src), sentences(new)
    ops = difflib.SequenceMatcher(None, ss, sn, autojunk=False).get_opcodes()
    return " ".join(" ".join(ss[i1:i2]) for op, i1, i2, _, _ in ops if op == "delete")


def unit_changes(src, new):
    """Numbers whose unit changed anywhere: 5 % in the source, only 5 п. п. in the rewrite."""
    us, un = units(src), units(new)
    return [f"{n} {'/'.join(sorted(us[n]))} → {'/'.join(sorted(un[n]))}"
            for n in sorted(set(us) & set(un)) if not us[n] & un[n]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source")
    ap.add_argument("rewrite")
    ap.add_argument("--glossary", action="append", default=[],
                    help="glossary or other project file a gloss may quote numbers from")
    ap.add_argument("--genre", choices=["report", "article"], default="report",
                    help="report: up to half of the sentences outside the summary may be rewritten; "
                         "article (also column, newsletter, interview, post): up to a third")
    ap.add_argument("--shortened", action="store_true",
                    help="the author asked to cut or restructure: no length or share thresholds, and a number "
                         "that left with a wholly deleted sentence is a warning, not a stop")
    args = ap.parse_args()
    src, new = (open(p, encoding="utf-8").read() for p in (args.source, args.rewrite))
    allowed = facts(src)
    for g in args.glossary:
        allowed |= facts(open(g, encoding="utf-8").read())
    respelled = spelled(src, new)
    lost = sorted(facts(src) - facts(new) - respelled)
    cut = sorted(set(lost) & facts(deleted_text(src, new))) if args.shortened else []
    lost = [x for x in lost if x not in cut]
    added = sorted(facts(new) - allowed - respelled)
    fewer = sorted((number_counts(src) - number_counts(new)).items())
    fewer = [(n, c) for n, c in fewer if n not in respelled]
    unit_swaps = unit_changes(src, new)
    ds, dn = dashes(src), dashes(new)
    dash_lost, dash_gone = dash_loss(src, new)
    ls, ln = ([nwords(s) for s in sentences(t)] for t in (src, new))
    ws, wn = nwords(src), nwords(new)
    (sum_s, body_s), (sum_n, body_n) = summary_split(src), summary_split(new)
    share = changed_share(body_s, body_n)
    long_s, long_n = sum(n > 30 for n in ls), sum(n > 30 for n in ln)
    ks, kn = len(KANTS.findall(strip_code(src))), len(KANTS.findall(strip_code(new)))

    print(f"потеряно: {len(lost)} {lost[:40]}")
    if args.shortened:
        print(f"ушло вместе с удалёнными фразами: {len(cut)} {cut[:40]}")
    print(f"новое (нет ни в исходнике, ни в глоссарии): {len(added)} {added[:40]}")
    print(f"число сменило единицу: {len(unit_swaps)} {unit_swaps[:20]}")
    print(f"тире: было {ds}, стало {dn}")
    print(f"длина: {ws} → {wn} слов ({100 * (wn - ws) / max(ws, 1):+.0f} %); "
          f"сводка {nwords(sum_s)} → {nwords(sum_n)}")
    print(f"переписано фраз вне сводки (сходство слов < 75 %): {100 * share:.0f} %")
    print(f"датчики (не цель): разброс длин фраз {cv(ls):.2f} → {cv(ln):.2f}; "
          f"фраз длиннее 30 слов {long_s} → {long_n}; номинализаций-кандидатов {ks} → {kn}")

    shifts = marker_shifts(src, new)
    if shifts:
        print(f"\nсверить с исходником ({len(shifts)} мест; строка в правке):")
        for line, notes in shifts:
            print(f"  стр. {line}: " + "; ".join(notes))

    warn = []
    short = ws < 150
    free = short or args.shortened
    limit, limit_name = (1 / 3, "трети") if args.genre == "article" else (0.5, "половины")
    if respelled:
        warn.append(f"число сменило запись (цифра ↔ слово): {sorted(respelled, key=int)} — проверь, что значение то же")
    if fewer:
        warn.append(f"число встречается реже, чем в исходнике: {fewer[:10]} — убран повтор или факт?")
    sws, swn = nwords(sum_s), nwords(sum_n)
    if short:
        warn.append("короткий текст (меньше 150 слов): пороги длины и доли не считаются; сверь каждое число, "
                    "имя и оговорку сам")
    if cut:
        warn.append(f"числа ушли вместе с удалёнными фразами: {cut[:20]} — проверь, что мысль ушла целиком, "
                    "а не потеряла цифру")
    if not free and ws and abs(wn - ws) / ws > 0.15:
        warn.append("длина изменилась больше чем на 15 %: пересказ или дописывание? объясни или откати")
    if not free and sws and abs(swn - sws) / sws > 0.25:
        warn.append("сводка изменилась больше чем на 25 %: объясни или откати")
    if not free and share > limit:
        warn.append(f"переписано больше {limit_name} фраз вне сводки: это пересказ, а не правка; объясни или откати")
    if ln and cv(ln) < cv(ls) - 0.05 and not stops_restored(src, new):
        warn.append("разброс длин фраз упал: перечитай, не выровнялся ли текст (не чини короткими фразами)")
    if long_n > long_s:
        warn.append("длинных фраз стало больше: перечитай их, разбивай только непрозрачные")
    if any(dash_gone.values()):
        warn.append(f"тире ушли вместе с удалёнными фразами, из заголовков или таблиц: {dash_gone} — "
                    "проверь, что их убрали по делу")
    for w in warn:
        print(f"внимание: {w}")

    bad = lost or added or unit_swaps or any(dash_lost.values())
    if bad:
        print("\nитог: СТОП (код 1) — потеря или подмена из строк выше, чини и запусти снова")
    elif warn or shifts:
        print("\nитог: стопа нет (код 0). «внимание» и «сверить» — места перечитать, а не приказ откатить: "
              "правку, сделанную по делу, оставь")
    else:
        print("\nитог: стопа нет (код 0)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
