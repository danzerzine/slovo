"""Regression tests for check.py on editing accidents taken from a real rewrite of analytical reports.

Each case in cases.json: the bad rewrite must raise a signal, the good one must not. A case with no
«bad» is a false-positive guard: an honest rewrite that must stay clean.
Cases in tests/cases.local.json (git-ignored) run too, if the file exists.
Cases marked known_miss are meaning shifts check.py cannot see (left to the cold check);
they are reported, not failed, and a known miss that starts to be caught is reported too.

Usage:
  python3 tests/run_tests.py
  python3 tests/run_tests.py --pairs DIR
    also runs your own accepted rewrites: DIR holds name.orig.md and name.new.md pairs that a human
    checked as faithful. None may hard-fail, and the number of «сверить» places is printed, so a
    noisier check.py shows up as a bigger number.
  python3 tests/run_tests.py --repo REPO --commit SHA
    the same for a commit whose files are accepted rewrites of their parent versions.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import check  # noqa: E402


def signals(src, new):
    respelled = check.spelled(src, new)
    out = [f"потеряно {x}" for x in sorted(check.facts(src) - check.facts(new) - respelled)]
    out += [f"новое {x}" for x in sorted(check.facts(new) - check.facts(src) - respelled)]
    out += [f"единица {x}" for x in check.unit_changes(src, new)]
    out += [f"тире {k}" for k, v in check.dash_loss(src, new)[0].items() if v]
    out += [n for _, notes in check.marker_shifts(src, new) for n in notes]
    return out


def doc(case, text):
    return (case.get("context", "") + "\n\n" + text + "\n").lstrip()


def run_cases():
    failed = 0
    cases = json.loads((HERE / "cases.json").read_text(encoding="utf-8"))
    local = HERE / "cases.local.json"  # your own cases from work, kept out of git
    if local.exists():
        cases += json.loads(local.read_text(encoding="utf-8"))
    for c in cases:
        src = doc(c, c["source"])
        good = signals(src, doc(c, c["good"]))
        bad = signals(src, doc(c, c["bad"])) if "bad" in c else ["(нет плохой правки)"]
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


def run_share():
    """Rewritten share counts sentences rewritten in earnest, not commas or one swapped word."""
    src = "Мы сравнили три версии спада и ни одна его не объясняет. Данные взяли за май у всех клиентов. " \
          "Отчёт собрали вручную и проверили дважды. Вопросы остались только по возвратам."
    light = "Мы сравнили три версии спада, и ни одна его не объясняет. Данные взяли за май у всех клиентов. " \
            "Отчёт собрали вручную и проверили два раза. Вопросы остались только по возвратам."
    heavy = "Ни одна из трёх версий не объясняет спад. Майские данные охватывают всех клиентов. " \
            "Ручная сборка отчёта прошла двойную проверку. Открытыми остаются лишь возвраты."
    cases = [("запятая и одно слово", light, lambda x: x == 0), ("пересказ", heavy, lambda x: x == 1)]
    failed = 0
    for name, new, ok in cases:
        share = check.changed_share(src, new)
        good = ok(share)
        failed += not good
        print(f"доля: {name:<20} {100 * share:.0f} % {'ок' if good else 'ПРОВАЛ'}")
    return failed


def folder_pairs(folder):
    for orig in sorted(Path(folder).glob("*.orig.md")):
        new_path = orig.with_name(orig.name[: -len(".orig.md")] + ".new.md")
        if new_path.exists():
            yield new_path.name, orig.read_text(encoding="utf-8"), new_path.read_text(encoding="utf-8")


def commit_pairs(repo, commit):
    def git(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True).stdout
    for f in git("show", "--name-only", "--format=", commit).split():
        yield f, git("show", f"{commit}^:{f}"), git("show", f"{commit}:{f}")


def run_pairs(pairs):
    hard, places, n = 0, 0, 0
    for name, src, new in pairs:
        n += 1
        bad = (check.facts(src) - check.facts(new)) or (check.facts(new) - check.facts(src)) \
            or check.unit_changes(src, new) or any(check.dash_loss(src, new)[0].values())
        hard += bool(bad)
        places += len(check.marker_shifts(src, new))
        if bad:
            print(f"  жёсткая ошибка на принятой правке: {name}")
    print(f"принятые правки: {n} пар, жёстких ошибок {hard}, мест «сверить» {places}")
    return hard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", help="folder with name.orig.md / name.new.md pairs checked by a human")
    ap.add_argument("--repo", help="git repo whose --commit holds accepted rewrites (parent = sources)")
    ap.add_argument("--commit", help="commit with accepted rewrites, used with --repo")
    args = ap.parse_args()
    failed = run_cases() + run_share()
    if args.pairs:
        failed += run_pairs(folder_pairs(args.pairs))
    if args.repo and args.commit:
        failed += run_pairs(commit_pairs(args.repo, args.commit))
    print("всё прошло" if not failed else f"провалов: {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
