"""density.py: how much an edit touched texts that had no reference edit (a strong author without an editor).
  python density.py SRC_DIR OUT_DIR
For each SRC_DIR/NAME.md with OUT_DIR/NAME.md: word-level diff hunks, split into punctuation-only and word edits,
per 1000 words. Prints a table and the total; writes OUT_DIR/_edits.txt with every hunk in context for reading.
"""
import difflib, re, sys
from pathlib import Path

TOK = re.compile(r"\w+|[^\w\s]")
src, out = Path(sys.argv[1]), Path(sys.argv[2])
tot, lines = [0, 0, 0], []
print("text\twords\tedits\tpunct\twords_changed\tper1000")
for s in sorted(src.glob("*.md")):
    o = out / s.name
    if not o.exists(): continue
    a, b = TOK.findall(s.read_text(encoding="utf-8")), TOK.findall(o.read_text(encoding="utf-8"))
    words = sum(1 for x in a if re.match(r"\w", x))
    hunks = [op for op in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if op[0] != "equal"]
    punct = sum(1 for _, i1, i2, j1, j2 in hunks if not any(re.match(r"\w", x) for x in a[i1:i2] + b[j1:j2]))
    print(f"{s.stem}\t{words}\t{len(hunks)}\t{punct}\t{len(hunks) - punct}\t{1000 * len(hunks) / max(words, 1):.1f}")
    tot = [tot[0] + words, tot[1] + len(hunks), tot[2] + punct]
    for _, i1, i2, j1, j2 in hunks:
        lines.append(f"{s.stem}\t…{' '.join(a[max(0, i1 - 5):i1])} [{' '.join(a[i1:i2])} → {' '.join(b[j1:j2])}]")
print(f"ALL\t{tot[0]}\t{tot[1]}\t{tot[2]}\t{tot[1] - tot[2]}\t{1000 * tot[1] / max(tot[0], 1):.1f}")
(out / "_edits.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
