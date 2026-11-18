"""Écrit les partitions au format LilyPond (texte), puis les grave en PDF avec LilyPond (tools/lilypond).

Les durées sont comptées en lignes du module (1 ligne = 1 double croche). Une note est découpée en valeurs
lisibles (croche, noire pointée…) qui respectent les temps de la mesure, et liée si besoin.
"""
from __future__ import annotations
import pathlib
import subprocess

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"
SHARPS = ["c", "cis", "d", "dis", "e", "f", "fis", "g", "gis", "a", "ais", "b"]
FLATS = ["c", "des", "d", "es", "e", "f", "ges", "g", "as", "a", "bes", "b"]
DURATION = {1: "16", 2: "8", 3: "8.", 4: "4", 6: "4.", 8: "2", 12: "2.", 16: "1"}


def lilypond_exe() -> pathlib.Path:
    exe = next(TOOLS.glob("lilypond/*/bin/lilypond.exe"), None)
    if not exe:
        raise SystemExit("LilyPond absent : lancer  .venv\\Scripts\\python scripts\\setup_tools.py")
    return exe


def pitch(m: int, flats: bool = False) -> str:
    name = (FLATS if flats else SHARPS)[m % 12]
    octave = m // 12 - 4
    return name + ("'" * octave if octave > 0 else "," * -octave)


def split(pos: int, length: int, bar_len: int = 16) -> list[int]:
    """Découpe une durée (en lignes) qui commence à `pos` dans la mesure en valeurs qui respectent les temps."""
    out = []
    length = min(length, bar_len - pos)  # jamais au-delà de la barre de mesure
    while length > 0:
        for v in (16, 12, 8, 6, 4, 3, 2, 1):
            if v > length or pos + v > bar_len:
                continue
            if v == 16 and pos != 0:
                continue
            if v == 12 and pos not in (0, 4):
                continue
            if v in (8, 6) and pos % 8:
                continue
            if v == 4 and pos % 4:
                continue
            if v == 3 and pos % 4 not in (0, 1):
                continue
            if v == 2 and pos % 2:
                continue
            out.append(v)
            pos += v
            length -= v
            break
    return out


def bar_music(bar_len: int, notes: list[tuple], empty: str = "R") -> str:
    """Une mesure : notes = [(position, durée, corps, ajout[, liée à la mesure suivante])] ;
    corps « <e\\5 b\\4> », ajout « -. » (staccato)…

    Les trous sont des silences. Une mesure vide : « R » (pause, regroupable) ou « s » (rien d'affiché)."""
    if not notes:
        return f"{empty}1" if bar_len == 16 else f"{empty}16*{bar_len}"
    out = []
    pos = 0
    for note in sorted(notes, key=lambda n: n[0]):
        start, length, body, extra = note[:4]
        tie_out = len(note) > 4 and note[4]
        if start > pos:
            out += [f"r{DURATION[v]}" for v in split(pos, start - pos, bar_len)]
            pos = start
        length = min(length, bar_len - start)
        if length <= 0:
            continue
        vals = split(start, length, bar_len)
        for k, v in enumerate(vals):
            dur = DURATION[v]
            tok = (body.replace("{d}", dur) if "{d}" in body else body + dur) + (extra if k == 0 else "")
            if k < len(vals) - 1 or (tie_out and start + length >= bar_len):
                tok += "~"
            out.append(tok)
        pos = start + length
    if pos < bar_len:
        out += [f"r{DURATION[v]}" for v in split(pos, bar_len - pos, bar_len)]
    return " ".join(out)


def spacer_bar(bar_len: int, marks: dict[int, list[str]], prefix: str = "") -> str:
    """Une mesure invisible qui porte les textes (P.M., b. ½…), le tempo et les repères."""
    toks = [prefix] if prefix else []
    run = 0
    for i in range(bar_len):
        if i in marks:
            if run:
                toks.append(f"s16*{run}")
                run = 0
            texts = [m for m in marks[i] if not m.startswith("\\")]
            cmds = "".join(m for m in marks[i] if m.startswith("\\"))  # \startTextSpan…
            tok = "s16"
            if texts:
                txt = " ".join(texts).replace('"', "'")
                tok += f'^\\markup \\small "{txt}"'
            toks.append(tok + cmds)
        else:
            run += 1
    if run:
        toks.append(f"s16*{run}")
    return " ".join(toks)


def bar_prefix(b: int, tempi: list[int], secs: dict) -> str:
    """Tempo (s'il change) et repère de partie (lettre + temps dans le morceau) en début de mesure."""
    out = []
    if b == 0 or tempi[b] != tempi[b - 1]:
        out.append(f"\\tempo 4 = {tempi[b]}")
    if b in secs:
        letter, t = secs[b]
        m, s = divmod(int(round(t)), 60)
        out.append(f'\\mark \\markup {{ \\box \\bold "{letter}" \\small "{m}:{s:02d}" }}')
    return " ".join(out)


def header(title: str, subtitle: str, composer: str, legend: str = "") -> str:
    leg = ""
    if legend:
        leg = f'\\markup \\small \\wordwrap {{ {legend} }}\n\\markup \\vspace #1\n'
    return f"""\\version "2.24.4"
\\paper {{
  #(set-paper-size "a4")
  top-margin = 12 bottom-margin = 12 left-margin = 14 right-margin = 12
  system-system-spacing.basic-distance = #14
  print-page-number = ##t
}}
\\header {{
  title = "{title}"
  subtitle = "{subtitle}"
  composer = "{composer}"
  tagline = "Généré par Remaster AMIGA Music (LilyPond)"
}}
{leg}"""


def compile_pdf(ly_path: pathlib.Path) -> pathlib.Path:
    """Grave le .ly en PDF dans le même dossier ; lève une erreur lisible si LilyPond échoue."""
    r = subprocess.run([str(lilypond_exe()), "-dno-point-and-click", "-o", str(ly_path.with_suffix("")), str(ly_path)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ly_path.parent)
    pdf = ly_path.with_suffix(".pdf")
    if r.returncode != 0 or not pdf.exists():
        raise RuntimeError(f"LilyPond a échoué sur {ly_path.name} :\n{r.stderr[-3000:]}")
    return pdf


def compile_png(ly_path: pathlib.Path, resolution: int = 100) -> list[pathlib.Path]:
    """Version image (pour vérifier la gravure)."""
    subprocess.run([str(lilypond_exe()), "-dno-point-and-click", "--png", f"-dresolution={resolution}",
                    "-o", str(ly_path.with_suffix("")), str(ly_path)], capture_output=True, cwd=ly_path.parent)
    return sorted(ly_path.parent.glob(ly_path.stem + "*.png"))
