"""Regression tests for check.py on editing accidents taken from a real rewrite of analytical reports.

Each case in cases.json: the bad rewrite must raise a signal, the good one must not.
Cases marked known_miss are meaning shifts check.py cannot see (left to the cold check);
they are reported, not failed, and a known miss that starts to be caught is reported too.

Usage:
  python3 tests/run_tests.py
  python3 tests/run_tests.py --pairs DIR
    also runs your own accepted rewrites: DIR holds name.orig.md and name.new.md pairs that a human
    checked as faithful. None may hard-fail, and the number of «сверить» places is printed, so a
    noisier check.py shows up as a bigger number.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import check  # noqa: E402


def signals(src, new):
    out = [f"потеряно {x}" for x in sorted(check.facts(src) - check.facts(new))]
    out += [f"новое {x}" for x in sorted(check.facts(new) - check.facts(src))]
    out += [f"единица {x}" for x in check.unit_changes(src, new)]
    out += [n for _, notes in check.marker_shifts(src, new) for n in notes]
    return out


def doc(case, text):
    return (case.get("context", "") + "\n\n" + text + "\n").lstrip()


def run_cases():
    failed = 0
    for c in json.loads((HERE / "cases.json").read_text(encoding="utf-8")):
        src = doc(c, c["source"])
        bad, good = signals(src, doc(c, c["bad"])), signals(src, doc(c, c["good"]))
        miss = c.get("known_miss", False)
        if good:
            status, failed = "ПРОВАЛ: хорошая правка помечена", failed + 1
        elif not bad and not miss:
            status, failed = "ПРОВАЛ: плохая правка не помечена", failed + 1
        elif not bad:
            status = "не видит (оставлено сверке)"
        elif miss:
            status = "ловит, хотя помечен known_miss: сними пометку"
        else:
            status = "ок"
        print(f"{c['id']:<20} {status}")
        for s in good:
            print(f"    хорошая: {s}")
        if bad and status != "ок":
            print(f"    плохая: {bad[0]}")
    return failed


def run_pairs(folder):
    hard, places, n = 0, 0, 0
    for orig in sorted(Path(folder).glob("*.orig.md")):
        new_path = orig.with_name(orig.name[: -len(".orig.md")] + ".new.md")
        if not new_path.exists():
            continue
        src, new = orig.read_text(encoding="utf-8"), new_path.read_text(encoding="utf-8")
        n += 1
        bad = (check.facts(src) - check.facts(new)) or (check.facts(new) - check.facts(src)) \
            or check.unit_changes(src, new)
        hard += bool(bad)
        places += len(check.marker_shifts(src, new))
        if bad:
            print(f"  жёсткая ошибка на принятой правке: {new_path.name}")
    print(f"принятые правки: {n} пар, жёстких ошибок {hard}, мест «сверить» {places}")
    return hard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", help="folder with name.orig.md / name.new.md pairs checked by a human")
    args = ap.parse_args()
    failed = run_cases()
    if args.pairs:
        failed += run_pairs(args.pairs)
    print("всё прошло" if not failed else f"провалов: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
