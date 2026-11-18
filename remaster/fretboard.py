"""Place les notes sur le manche : quelle corde, quelle case (accordage standard).

Pour chaque note ou accord, on cherche toutes les positions jouables (une note par corde, écart de 4 cases au plus
entre doigts) ; puis on choisit la suite de positions qui bouge le moins la main et reste basse sur le manche
(programmation dynamique, comme un guitariste qui reste « en position »).
Un accord injouable (deux voies du module qui jouent des accords différents en même temps) perd des notes :
d'abord les doublures d'octave, puis les notes du milieu.
"""
from __future__ import annotations
from itertools import permutations

GUITAR = (40, 45, 50, 55, 59, 64)   # mi grave … mi aigu (E2 A2 D3 G3 B3 E4)
BASS = (28, 33, 38, 43)             # E1 A1 D2 G2

Fingering = tuple[tuple[int, int, int], ...]  # ((note MIDI, n° de corde 1 = la plus aiguë, case), …)


def positions(pitches, tuning=GUITAR, max_fret=22, span=4) -> list[Fingering]:
    n = len(tuning)
    out = []
    ps = sorted(pitches)
    if len(ps) > n:
        return []
    for strings in permutations(range(n), len(ps)):
        frets = [p - tuning[s] for p, s in zip(ps, strings)]
        if any(f < 0 or f > max_fret for f in frets):
            continue
        used = [f for f in frets if f > 0]
        if used and max(used) - min(used) > span:
            continue
        out.append(tuple(sorted(((p, n - s, f) for p, s, f in zip(ps, strings, frets)), key=lambda x: -x[1])))
    return out


def reductions(pitches):
    """Les accords à essayer, du plus complet au plus réduit."""
    ps = tuple(sorted(set(pitches)))
    seen = {ps}
    level = [ps]
    while level:
        yield from level
        nxt = []
        for c in level:
            if len(c) <= 1:
                continue
            for drop in _drop_order(c):
                d = tuple(p for p in c if p != drop)
                if d not in seen:
                    seen.add(d)
                    nxt.append(d)
        level = nxt


def _drop_order(c):
    """Notes à enlever en priorité : doublure d'octave (la plus aiguë des deux), puis le milieu, puis le grave."""
    pcs = [p % 12 for p in c]
    dup = [p for i, p in enumerate(c) if pcs.count(p % 12) > 1 and i > pcs.index(p % 12)]
    middle = list(c[1:-1])
    return dup[::-1] + middle + [c[0]]


def _pos(f: Fingering):
    used = [fr for _p, _s, fr in f if fr > 0]
    return min(used) if used else None


def _static(f: Fingering) -> float:
    cost = sum(0.08 * fr + 0.4 * max(0, fr - 12) for _p, _s, fr in f)
    if len(f) > 1:
        strings = sorted(s for _p, s, _fr in f)
        cost += 2.5 * sum(b - a - 1 for a, b in zip(strings, strings[1:]))  # corde sautée : forme peu naturelle
        fretted = [fr for _p, _s, fr in f if fr > 0]
        if fretted and len(fretted) < len(f):
            cost += 1.5  # corde à vide mêlée à des notes appuyées
    return cost


def _move(a: Fingering, b: Fingering) -> float:
    pa, pb = _pos(a), _pos(b)
    if pa is None or pb is None:
        return 0.0
    return abs(pa - pb)


def assign(chords: list[tuple[int, ...]], tuning=GUITAR, max_fret=22, span=4) -> tuple[list[Fingering], int]:
    """Une position par accord ; renvoie aussi le nombre de notes enlevées (injouables)."""
    cands = []
    dropped = 0
    cache: dict = {}
    for ch in chords:
        key = tuple(sorted(ch))
        if key not in cache:
            found, lost = [], 0
            for red in reductions(key):
                found = positions(red, tuning, max_fret, span)
                if found:
                    lost = len(set(key)) - len(red)
                    break
            cache[key] = (found, lost)
        found, lost = cache[key]
        dropped += lost
        cands.append(found or [()])
    if not cands:
        return [], 0
    # Viterbi : coût = hauteur sur le manche + déplacements de la main
    cost = [_static(f) for f in cands[0]]
    back = []
    for k in range(1, len(cands)):
        prev = cands[k - 1]
        new_cost, ptr = [], []
        for f in cands[k]:
            best_j = min(range(len(prev)), key=lambda j: cost[j] + _move(prev[j], f))
            new_cost.append(cost[best_j] + _move(prev[best_j], f) + _static(f))
            ptr.append(best_j)
        cost = new_cost
        back.append(ptr)
    j = min(range(len(cost)), key=cost.__getitem__)
    path = [j]
    for ptr in reversed(back):
        j = ptr[j]
        path.append(j)
    path.reverse()
    return [cands[k][j] for k, j in enumerate(path)], dropped
