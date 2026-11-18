"""Montre un module comme dans un tracker, pour comprendre qui joue quoi avant d'écrire la fiche.

    .venv\\Scripts\\python scripts\\dump_patterns.py "in\\music\\Dr Mario\\Dr Mario.mod"           # résumé : samples et voies par pattern
    .venv\\Scripts\\python scripts\\dump_patterns.py "in\\music\\Dr Mario\\Dr Mario.mod" 4 13       # le détail des patterns 4 et 13

Une case : note (C-2…), n° de sample, effet (1xx glissando vers le haut, 2xx vers le bas, Cxx volume, Fxx vitesse).
"""
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from remaster import modfile, analyze  # noqa: E402

NAMES = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]


def note_name(period: int) -> str:
    if not period:
        return "..."
    i = min(range(36), key=lambda k: abs(modfile.PERIODS[k] - period))
    return NAMES[i % 12] + str(i // 12 + 1)


def cell(n) -> str:
    if not (n.period or n.sample or n.effect or n.param):
        return "...  .. ..."
    return f"{note_name(n.period)} {n.sample:02d} {n.effect:X}{n.param:02X}"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    mod = modfile.load(pathlib.Path(sys.argv[1]))
    pats = [int(x) for x in sys.argv[2:]]
    if pats:
        for pat in pats:
            print(f"=== pattern {pat} (positions {[i for i, o in enumerate(mod.orders) if o == pat]})")
            for r, row in enumerate(mod.patterns[pat]):
                print(f"{r:02d} | " + " | ".join(cell(n) for n in row))
        return
    print(f"ordre ({len(mod.orders)} positions) : {mod.orders}")
    print("\nsamples :")
    for s in mod.samples:
        if len(s.data) >= 4:
            print(f"  {s.index:2d} {s.name!r:28} {analyze.describe(s)}")
    print("\npattern : positions dans l'ordre, {sample: voies}, effets")
    for pat in sorted(set(mod.orders)):
        by = collections.defaultdict(set)
        eff = collections.Counter()
        for row in mod.patterns[pat]:
            for c, n in enumerate(row):
                if n.sample:
                    by[n.sample].add(c + 1)
                if n.effect or n.param:
                    eff[f"{n.effect:X}"] += 1
        pos = [i for i, o in enumerate(mod.orders) if o == pat]
        print(f"  {pat:2d} {pos} {dict(sorted(by.items()))} {dict(eff)}")


if __name__ == "__main__":
    main()
