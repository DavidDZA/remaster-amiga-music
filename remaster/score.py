"""Du module rejoué aux partitions : chaque attaque est placée sur la grille des lignes du module.

Une ligne de pattern = une double croche, 16 lignes = une mesure à 4/4 (le cas de presque tous les modules
ProTracker, et de *Dr Mario*). Le tempo vient de la vitesse : 6 ticks à 125 BPM = noire à 125, 5 ticks = 150.

Les parties à écrire (guitares, basse, batterie…) sont décrites dans la fiche du morceau, clé `partitions` :
quels samples chaque musicien joue. Une partie `lead` ne prend, à chaque mesure, que la voie du module qui joue le
plus haut parmi ses samples : les autres lignes de lead vont à la partie suivante qui les accepte (la 2e guitare).
"""
from __future__ import annotations
import bisect
import math
from dataclasses import dataclass, field
from .modfile import Module, period_to_semitones
from .player import Song
from . import extras

ROWS_PER_BEAT = 4
ROWS_PER_BAR = 16


@dataclass
class Hit:
    """Une attaque d'un sample sur une voie du module."""
    row: int                 # indice de ligne dans song.rows
    end: int                 # ligne où la note s'arrête (exclue)
    pitches: tuple[int, ...]  # notes MIDI (accord compris) ; pour la batterie, la note GM
    sample: int
    channel: int
    bend: list[float] = field(default_factory=list)  # décalage (demi-tons) à la fin de chaque ligne de la note
    muted: bool = False      # note étouffée (palm mute)
    velocity: int = 100


@dataclass
class Event:
    """Ce que joue un musicien à une ligne : une note ou un accord, avec sa durée."""
    row: int
    end: int
    pitches: tuple[int, ...]
    muted: bool = False
    bend: list[float] = field(default_factory=list)
    samples: frozenset = frozenset()


def tick_rows(song: Song) -> list[int]:
    times = [r[2] for r in song.rows]
    return [max(0, bisect.bisect_right(times, t + 1e-9) - 1) for t in song.tick_times]


def hits(song: Song, mod: Module, cfg: dict) -> list[Hit]:
    """Toutes les attaques du module, avec les instruments de la fiche (hauteur, accord, transposition)."""
    from .render import instrument  # import tardif : render charge les outils audio
    trow = tick_rows(song)
    insts: dict = {}
    out: list[Hit] = []
    for c in range(song.channels):
        cur: Hit | None = None
        start_t = 0.0
        max_len = None
        is_drum = False
        for i, tk in enumerate(song.ticks[c]):
            r = trow[i]
            first_tick = i == 0 or trow[i - 1] != r
            if cur is not None:
                cut = max_len is not None and tk.time - start_t >= max_len - 1e-9
                if tk.trigger or tk.sample != cur.sample or tk.volume == 0 or cut:
                    cur.end = max(cur.row + 1, r if first_tick else r + 1)
                    cur = None
                elif tk.period and tk.note_period and not is_drum:
                    k = r - cur.row
                    off = 12 * math.log2(tk.note_period / tk.period)
                    while len(cur.bend) <= k:
                        cur.bend.append(cur.bend[-1] if cur.bend else 0.0)
                    cur.bend[k] = off
            if not (tk.trigger and tk.sample) or tk.volume == 0:
                continue
            key = (tk.sample, c)
            if key not in insts:
                insts[key] = instrument(cfg, mod, tk.sample, c)
            inst = insts[key]
            if inst.mute:
                continue
            if inst.drum is not None:
                pitches = (inst.drum,)
            else:
                base = round(inst.root + period_to_semitones(tk.note_period) + inst.transpose)
                pitches = tuple(base + x for x in inst.chord)
            cur = Hit(r, r + 1, pitches, tk.sample, c, bend=[0.0],
                      muted=bool(inst.max_length and inst.max_length <= 0.2),
                      velocity=max(1, min(127, round(inst.velocity * math.sqrt(tk.volume / 64)))))
            if inst.drum is not None:
                cur.bend = []
            start_t, max_len, is_drum = tk.time, inst.max_length, inst.drum is not None
            out.append(cur)
        if cur is not None:
            cur.end = len(song.rows)
    out.sort(key=lambda h: (h.row, h.channel))
    return out


def extra_hits(song: Song, mod: Module, cfg: dict, all_hits: list[Hit]) -> list[Hit]:
    """Charleston et crashs de la version enrichie (mêmes règles que extras.py), en attaques sur la grille."""
    ex = cfg.get("extras") or {}
    drum_samples = {h.sample for h in all_hits if _is_drum(cfg, h.sample)}
    drows = extras.drum_rows(song, drum_samples)
    out = []
    if "hihat" in ex:
        note = ex["hihat"].get("note", 42)
        out += [Hit(i, i + 1, (note,), -1, -1, velocity=v) for i, v in extras.hihat_rows(song, mod, drows, ex["hihat"])]
    if "crash" in ex:
        note = ex["crash"].get("note", 49)
        out += [Hit(i, i + 1, (note,), -2, -1, velocity=ex["crash"].get("velocity", 110))
                for i in extras.crash_rows(song, mod, drows)]
    return out


def _is_drum(cfg: dict, sample: int) -> bool:
    return cfg.get("samples", {}).get(str(sample), {}).get("drum") is not None


def bars(song: Song) -> list[tuple[int, int]]:
    """(première ligne, nombre de lignes) de chaque mesure : 16 lignes, ou moins si un pattern est coupé."""
    starts = [i for i, (order, row, _t) in enumerate(song.rows)
              if row % ROWS_PER_BAR == 0 or i == 0 or song.rows[i - 1][0] != order]
    ends = starts[1:] + [len(song.rows)]
    return [(s, e - s) for s, e in zip(starts, ends)]


def row_seconds(song: Song) -> list[float]:
    """Début de chaque ligne, plus la fin du morceau."""
    return [r[2] for r in song.rows] + [song.duration]


def bar_tempi(song: Song, bar_list) -> list[int]:
    """Tempo (noires par minute) de chaque mesure : celui de la majorité de ses lignes."""
    t = row_seconds(song)
    out = []
    for s, n in bar_list:
        bpms = [round(60 / ((t[i + 1] - t[i]) * ROWS_PER_BEAT)) for i in range(s, s + n)]
        out.append(max(set(bpms), key=bpms.count))
    return out


def sections(song: Song, mod: Module, bar_list) -> dict[int, tuple[str, float]]:
    """Repères : une lettre au début de chaque nouvelle partie (le pattern change), avec le temps en secondes."""
    out = {}
    letters = 0
    for b, (s, _n) in enumerate(bar_list):
        order, row, t = song.rows[s]
        if row != 0:
            continue
        if order == 0 or mod.orders[order] != mod.orders[order - 1]:
            q, r = divmod(letters, 26)
            out[b] = ((chr(65 + q - 1) if q else "") + chr(65 + r), t)
            letters += 1
    return out


# --- répartition des attaques entre les musiciens -------------------------------------------------------------

def assign(all_hits: list[Hit], parts: dict, bar_list) -> dict[str, list[Hit]]:
    """parts : {nom: {"samples": [...], "lead": bool, "extras": bool}} dans l'ordre de priorité."""
    bar_of = _bar_index(bar_list)
    out: dict[str, list[Hit]] = {name: [] for name in parts}
    taken: set[int] = set()
    for name, p in parts.items():
        samples = set(p.get("samples", []))
        if p.get("extras"):
            samples |= {-1, -2}
        mine = [h for h in all_hits if h.sample in samples and id(h) not in taken]
        if p.get("lead"):
            top = _top_channel(mine, bar_of)
            mine = [h for h in mine if top.get(bar_of[h.row]) == h.channel]
        for h in mine:
            taken.add(id(h))
        out[name] = mine
    return out


def _bar_index(bar_list) -> list[int]:
    idx = []
    for b, (_s, n) in enumerate(bar_list):
        idx += [b] * n
    return idx


def _top_channel(hs: list[Hit], bar_of) -> dict[int, int]:
    """Pour chaque mesure, la voie qui joue le plus haut (moyenne des notes) parmi ces attaques."""
    acc: dict[tuple[int, int], list[int]] = {}
    for h in hs:
        acc.setdefault((bar_of[h.row], h.channel), []).append(max(h.pitches))
    best: dict[int, tuple[float, int]] = {}
    for (b, c), ps in acc.items():
        m = sum(ps) / len(ps)
        if b not in best or m > best[b][0]:
            best[b] = (m, c)
    return {b: c for b, (_m, c) in best.items()}


def events(hs: list[Hit], max_rows: int | None = None, until_next: bool = False) -> list[Event]:
    """Les attaques d'un musicien, regroupées par ligne (accords) ; chaque note s'arrête à la suivante.

    until_next : la note dure jusqu'à l'attaque suivante (batterie : on écrit l'espacement des coups)."""
    by_row: dict[int, list[Hit]] = {}
    for h in hs:
        by_row.setdefault(h.row, []).append(h)
    rows = sorted(by_row)
    out = []
    for k, r in enumerate(rows):
        group = by_row[r]
        end = max(h.end for h in group)
        if until_next:
            end = rows[k + 1] if k + 1 < len(rows) else r + (max_rows or 4)
        if k + 1 < len(rows):
            end = min(end, rows[k + 1])
        if max_rows:
            end = min(end, r + max_rows)
        top = max(group, key=lambda h: max(h.pitches))
        out.append(Event(r, max(r + 1, end), tuple(sorted({p for h in group for p in h.pitches})),
                         muted=all(h.muted for h in group), bend=list(top.bend[: end - r]),
                         samples=frozenset(h.sample for h in group)))
    return out


def fit_range(evs: list[Event], low: int) -> int:
    """Remonte d'une octave les notes trop graves pour l'instrument. Renvoie le nombre de notes déplacées."""
    moved = 0
    for e in evs:
        if min(e.pitches) < low:
            ps = []
            for p in e.pitches:
                while p < low:
                    p += 12
                    moved += 1
                ps.append(p)
            e.pitches = tuple(sorted(set(ps)))
    return moved


# --- bends et glissandos : textes au-dessus de la portée ------------------------------------------------------

def bend_marks(e: Event) -> list[tuple[int, str]]:
    """(ligne, texte) pour une note dont la hauteur bouge : b. ½ / b. 1 (tirer la corde), lâcher, gliss., vibr."""
    b = [round(x * 2) / 2 for x in e.bend]
    if not b or max(abs(x) for x in b) < 0.75:
        return []
    marks = []
    chord = len(e.pitches) > 1
    lo, hi = min(b), max(b)
    if lo <= -0.75 and hi < 0.75:
        returns = any(b[k] <= -0.75 and b[k + 1] > b[k] for k in range(len(b) - 1))
        first = next(k for k, x in enumerate(b) if x <= -0.75)
        k0 = max(0, first - 1)
        marks.append((e.row + k0, "vibr." if returns else "gliss."))
        return marks
    if chord or hi >= 3 or (hi >= 2.75 and b[-1] >= hi - 0.5):
        k0 = next(k for k, x in enumerate(b) if x >= 0.75)
        marks.append((e.row + max(0, k0 - 1), "gliss."))
        return marks
    state = 0.0
    for k, x in enumerate(b):
        if x >= 0.75 and abs(x - state) >= 0.75:
            marks.append((e.row + k, f"b. {_tones(x)}"))
            state = x
        elif state >= 0.75 and x < 0.5:
            marks.append((e.row + k, "lâcher"))
            state = 0.0
    return marks


def _tones(semis: float) -> str:
    t = round(semis) / 2
    whole, half = int(t), t - int(t) >= 0.5
    if whole == 0:
        return "½"
    return f"{whole}½" if half else str(whole)


# --- tonalité ----------------------------------------------------------------------------------------------------

MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
FLAT_KEYS = {(5, False), (10, False), (3, False), (8, False), (1, False), (6, False),
             (2, True), (7, True), (0, True), (5, True), (10, True), (3, True)}


def pitch_classes(hs: list[Hit]) -> list[float]:
    """Poids de chaque classe de hauteur (do … si) : durée des notes, accords compris."""
    w = [0.0] * 12
    for h in hs:
        for p in h.pitches:
            w[p % 12] += h.end - h.row
    return w


def estimate_key(weights: list[float]) -> tuple[int, bool]:
    """(tonique 0-11, mineur ?) : corrélation avec les profils de Krumhansl-Kessler."""
    def corr(a, b):
        ma, mb = sum(a) / 12, sum(b) / 12
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) or 1.0
        return num / den
    best = max(((corr(weights, prof[-t:] + prof[:-t]), t, minor)
                for t in range(12) for minor, prof in ((False, MAJOR_PROFILE), (True, MINOR_PROFILE))))
    return best[1], best[2]


def uses_flats(key: tuple[int, bool]) -> bool:
    return key in FLAT_KEYS


def scale(key: tuple[int, bool]) -> set[int]:
    t, minor = key
    steps = [0, 2, 3, 5, 7, 8, 10] if minor else [0, 2, 4, 5, 7, 9, 11]
    return {(t + s) % 12 for s in steps}
