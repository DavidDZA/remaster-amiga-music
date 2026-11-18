"""Tablatures (guitares, basse) et partition de batterie, en PDF.

    python -m remaster.partitions "in\\music\\Dr Mario\\Dr Mario.mod"

Les parties sont décrites dans la fiche du morceau (`songs/<nom>.json`, clé `partitions`) :

    "partitions": {
      "Guitare 1 (lead)":      {"instrument": "guitare", "samples": [5], "lead": true},
      "Guitare 2 (rythmique)": {"instrument": "guitare", "samples": [5, 11, 12]},
      "Basse":                 {"instrument": "basse", "samples": [3]},
      "Batterie (version enrichie)": {"instrument": "batterie", "samples": [1, 2], "extras": true}
    }

Pour la guitare et la basse : portée (notes) + tablature (cases), accordage standard. Les notes sont celles du
remaster (accords de la fiche compris : power chords, quintes étouffées).
"""
from __future__ import annotations
import argparse
import pathlib
from . import modfile, player, score, fretboard, lily

INSTRUMENTS = {
    # tuning, case max, écart des doigts, clé, accordage LilyPond, nom court
    "guitare": dict(tuning=fretboard.GUITAR, max_fret=22, span=4, clef='"treble_8"', lily="guitar-tuning",
                    short="Guit."),
    "basse": dict(tuning=fretboard.BASS, max_fret=20, span=4, clef='"bass_8"', lily="bass-tuning", short="B."),
}

DRUM_NAMES = {35: "bd", 36: "bd", 38: "sn", 40: "sn", 37: "ss", 42: "hh", 44: "hhp", 46: "hho",
              49: "cymc", 57: "cymc", 51: "cymr", 41: "tomfl", 43: "tomfh", 45: "toml", 47: "tommh", 48: "tomh"}
FEET = {35, 36, 44}

LEGEND_FRETTED = ("Chiffres : case à jouer sur chaque corde (0 : corde à vide). Accordage standard. "
                  "Lettres encadrées : début d'une partie, avec le temps dans le MP3.")
LEGEND_MARKS = {  # expliqués seulement s'ils sont dans la partie
    "P.M.": "P.M. - - - : étouffer avec la paume (les accords marqués > sont joués ouverts).",
    "b.": "b. ½, b. 1 : tirer la corde d'un demi-ton, d'un ton.",
    "lâcher": "lâcher : revenir à la note.",
    "gliss.": "gliss. : glisser vers la note suivante, ou laisser tomber la note.",
    "vibr.": "vibr. : vibrato.",
}
LEGEND_DRUMS = ("Hampes en bas : grosse caisse. Hampes en haut : caisse claire (3e interligne), "
                "charleston fermé (× au-dessus), crash (× entouré). "
                "Version enrichie : le charleston et les crashs sont ajoutés au module. "
                "Lettres encadrées : début d'une partie, avec le temps dans le MP3.")


class Context:
    """Ce qui est commun à toutes les parties d'un morceau."""

    def __init__(self, mod_path: pathlib.Path, cfg: dict, mod=None, song=None, title: str | None = None):
        """mod, song : une musique déjà chargée (lue par UADE et posée sur une grille : paula.on_grid)."""
        self.mod = mod if mod is not None else modfile.load(mod_path)
        self.song = song if song is not None else player.play(self.mod)
        self.cfg = cfg
        self.title = title or mod_path.stem
        self.repeat_bars = 0   # > 0 : ces mesures-là, à partir de repeat_from, sont à jouer deux fois (reprise)
        self.repeat_from = 0   # mesures avant la reprise : la levée, écrite une fois
        self.fade = 0.0        # fondu de fin du MP3 (secondes), comme l'original enregistré par UADE
        self.composer = cfg.get("artist", "")
        self.bars = score.bars(self.song)
        self.tempi = score.bar_tempi(self.song, self.bars)
        self.sections = score.sections(self.song, self.mod, self.bars)
        self.hits = score.hits(self.song, self.mod, cfg)
        self.extras = score.extra_hits(self.song, self.mod, cfg, self.hits)
        tonal = [h for h in self.hits if not score._is_drum(cfg, h.sample)]
        self.key = score.estimate_key(score.pitch_classes(tonal))
        self.flats = score.uses_flats(self.key)

    def key_command(self) -> str:
        t, minor = self.key
        return f"\\key {lily.pitch(t + 48, self.flats)} \\{'minor' if minor else 'major'}"

    def split_bars(self, evs: list[score.Event]):
        """Chaque événement découpé par mesure : {mesure: [(position, durée, événement, continue après)]}."""
        out: dict[int, list] = {}
        bar_of = score._bar_index(self.bars)
        for e in evs:
            r = e.row
            while r < min(e.end, len(bar_of)):
                b = bar_of[r]
                start, n = self.bars[b]
                stop = min(e.end, start + n)
                out.setdefault(b, []).append((r - start, stop - r, e, r == e.row, stop < e.end))
                r = stop
        return out

    def join_bars(self, bars_txt: list[str], first: int = 0) -> str:
        """Regroupe les mesures vides qui se suivent (R1*12 : une seule pause chiffrée ; s1*12 pour une voix
        invisible), sans passer un repère ni un changement de tempo. LilyPond ne regroupe les pauses que si
        aucune autre voix de la portée ne coupe la suite de mesures."""
        out = []
        run, kind = 0, None
        for b, txt in enumerate(bars_txt, start=first):
            txt = "s1" if txt == "s16*16" else txt
            breaks = b in self.sections or (b > 0 and self.tempi[b] != self.tempi[b - 1])
            if run and (txt != kind or breaks):
                out.append(f"{kind}*{run}" if run > 1 else kind)
                run, kind = 0, None
            if txt in ("R1", "s1", "s16*16"):
                kind = "s1" if txt.startswith("s") else txt
                run += 1
            else:
                out.append(txt)
        if run:
            out.append(f"{kind}*{run}" if run > 1 else kind)
        return "\n  ".join(out)

    def marks_voice(self, marks: dict[int, list[str]], first: int = 0, upto: int | None = None) -> str:
        """marks : {ligne globale: [textes]} ; first, upto : seulement ces mesures (partition avec reprise)."""
        out = []
        for b, (start, n) in list(enumerate(self.bars))[first:upto]:
            local = {r - start: t for r, t in marks.items() if start <= r < start + n}
            out.append(lily.spacer_bar(n, local, lily.bar_prefix(b, self.tempi, self.sections)))
        return self.join_bars(out, first)


def fretted_part(ctx: Context, name: str, hs: list[score.Hit], kind: str) -> tuple[str, dict]:
    spec = INSTRUMENTS[kind]
    evs = score.events(hs)
    moved = score.fit_range(evs, spec["tuning"][0])
    fings, dropped = fretboard.assign([e.pitches for e in evs], spec["tuning"], spec["max_fret"], spec["span"])
    body_of = {}
    for e, f in zip(evs, fings):
        notes = [f"{lily.pitch(p, ctx.flats)}\\{s}" for p, s, _fr in sorted(f)]
        body_of[id(e)] = (notes[0].replace("\\", "{d}\\", 1) if len(notes) == 1
                          else ("<" + " ".join(notes) + ">" if notes else ""))
    # P.M. - - - au-dessus de chaque suite de notes étouffées ; les accords ouverts au milieu sont accentués (>)
    marks: dict[int, list[str]] = {}
    accented = set()
    for run in pm_runs(evs):
        first, last = run[0], run[-1]
        if first.row == last.row:
            marks.setdefault(first.row, []).append("P.M.")
        else:
            marks.setdefault(first.row, []).append("\\startTextSpan")
            marks.setdefault(last.row, []).append("\\stopTextSpan")
        accented |= {id(e) for e in evs if first.row < e.row < last.row and not e.muted}
    for e in evs:
        for r, t in score.bend_marks(e):
            marks.setdefault(r, []).append(t)
    per_bar = ctx.split_bars(evs)
    bars_txt = []
    for b, (_start, n) in enumerate(ctx.bars):
        notes = [(pos, ln, body_of[id(e)], "->" if first and id(e) in accented else "", tie)
                 for pos, ln, e, first, tie in per_bar.get(b, []) if body_of[id(e)]]
        bars_txt.append(lily.bar_music(n, notes))
    music = ctx.join_bars(bars_txt)
    short = spec["short"]
    used = {t.split()[0] for ts in marks.values() for t in ts if not t.startswith("\\")}
    if any(t.startswith("\\") for ts in marks.values() for t in ts):
        used.add("P.M.")
    text = f"""music = {{
  \\compressEmptyMeasures
  {music}
}}
marks = {{
  \\override TextSpanner.bound-details.left.text = \\markup \\small "P.M."
  {ctx.marks_voice(marks)}
}}
\\score {{
  \\new StaffGroup <<
    \\new Staff \\with {{ instrumentName = "{short}" \\omit StringNumber }} <<
      \\new Voice {{ \\clef {spec['clef']} {ctx.key_command()} \\music }}
      \\new Voice {{ \\marks }}
    >>
    \\new TabStaff \\with {{ stringTunings = #{spec['lily']} }} {{ \\music }}
  >>
  \\layout {{ indent = 0 }}
}}
"""
    stats = {"notes": len(evs), "remontées d'une octave": moved, "notes enlevées (injouables)": dropped}
    return text, stats, used


def drum_part(ctx: Context, hs: list[score.Hit]) -> tuple[str, dict]:
    hands = [h for h in hs if h.pitches[0] not in FEET]
    feet = [h for h in hs if h.pitches[0] in FEET]
    per_bar = [ctx.split_bars(score.events(g, max_rows=4, until_next=True)) for g in (hands, feet)]
    voices = []
    for k in (0, 1):
        bars_txt = []
        for b, (_start, n) in enumerate(ctx.bars):
            notes = []
            for pos, ln, e, _first, _tie in per_bar[k].get(b, []):
                names = [DRUM_NAMES.get(p, "sn") for p in e.pitches]
                body = names[0] if len(names) == 1 else "<" + " ".join(names) + ">"
                notes.append((pos, lily.split(pos, ln, n)[0], body, ""))  # pas de liaison en batterie
            # mesure vide : une pause pour la batterie entière (voix du haut), rien d'affiché pour l'autre voix
            silent = not per_bar[0].get(b) and not per_bar[1].get(b)
            bars_txt.append(lily.bar_music(n, notes, "R" if (silent and k == 0) else "s"))
        voices.append(ctx.join_bars(bars_txt))
    text = f"""up = \\drummode {{
    {voices[0]}
}}
down = \\drummode {{
    {voices[1]}
}}
marks = {{
  {ctx.marks_voice({})}
}}
\\score {{
  \\new DrumStaff \\with {{ instrumentName = "Batt." }} <<
    \\new DrumVoice {{ \\voiceOne \\up }}
    \\new DrumVoice {{ \\voiceTwo \\down }}
    \\new DrumVoice {{ \\marks }}
  >>
  \\layout {{ indent = 0 }}
}}
"""
    return text, {"coups": len(hs)}


def pm_runs(evs: list[score.Event], gap: int = 8) -> list[list[score.Event]]:
    """Suites de notes étouffées (moins de `gap` lignes entre deux), accords ouverts éventuels au milieu."""
    runs: list[list[score.Event]] = []
    for e in evs:
        if not e.muted:
            continue
        if runs and e.row - runs[-1][-1].end <= gap:
            runs[-1].append(e)
        else:
            runs.append([e])
    return runs


def make(mod_path: pathlib.Path, cfg: dict, out_dir: pathlib.Path, log=print) -> list[pathlib.Path]:
    parts = cfg.get("partitions")
    if not parts:
        raise SystemExit("La fiche du morceau n'a pas de section « partitions » (voir remaster/partitions.py).")
    ctx = Context(mod_path, cfg)
    out_dir.mkdir(parents=True, exist_ok=True)
    assigned = score.assign(ctx.hits + ctx.extras, parts, ctx.bars)
    made = []
    for name, p in parts.items():
        kind = p.get("instrument", "guitare")
        hs = assigned[name]
        if kind == "batterie":
            body, stats = drum_part(ctx, hs)
            legend = LEGEND_DRUMS
        else:
            body, stats, used = fretted_part(ctx, name, hs, kind)
            legend = " ".join([LEGEND_FRETTED] + [t for k, t in LEGEND_MARKS.items() if k in used])
        ly = out_dir / f"{ctx.title} - {name}.ly"
        ly.write_text(lily.header(ctx.title, name, ctx.composer, legend) + body, encoding="utf-8")
        pdf = lily.compile_pdf(ly)
        made.append(pdf)
        log(f"  {name} : " + ", ".join(f"{k} {v}" for k, v in stats.items()))
    for m in made:
        log(f"→ {m}")
    return made


def main():
    import sys
    from .render import load_config, ROOT
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Tablatures et partition de batterie d'un module Amiga, en PDF.")
    ap.add_argument("mod", type=pathlib.Path)
    ap.add_argument("--config", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()
    cfg = load_config(a.config or ROOT / "songs" / f"{a.mod.stem}.json")
    from .paths import work_dir
    make(a.mod, cfg, a.out or work_dir(a.mod) / "partitions")


if __name__ == "__main__":
    main()
