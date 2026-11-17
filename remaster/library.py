"""Les instruments, amplis et baffles gratuits, téléchargés à la demande dans tools/library (ignoré par git).

Seuls les fichiers réellement joués sont téléchargés : une banque de 1 Go n'en coûte que quelques dizaines de Mo.
"""
from __future__ import annotations
import pathlib
import posixpath
import shutil
import urllib.parse
import urllib.request
from . import sfz

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIB = ROOT / "tools" / "library"

# Banques SFZ (licence CC0 sauf mention) : https://sfzinstruments.github.io
BANKS = {
    "black-and-green-guitars": "sfzinstruments/karoryfer.black-and-green-guitars",  # guitares électriques DI
    "black-and-blue-basses": "sfzinstruments/karoryfer.black-and-blue-basses",      # basses électriques
    "virtuosity-drums": "sfzinstruments/virtuosity_drums",                          # batterie
    "big-rusty-drums": "sfzinstruments/karoryfer.big-rusty-drums",                  # autre batterie
    "shinyguitar": "sfzinstruments/karoryfer.shinyguitar",                          # guitare acoustique / électrique
    "emilyguitar": "sfzinstruments/karoryfer.emilyguitar",
    "meatbass": "sfzinstruments/karoryfer.meatbass",                                # contrebasse
}

# Banques placées plus haut que le son réel (mesuré) : la touche 35 de Black and Blue Basses sonne si 0 (30,9 Hz),
# soit la touche 23. On ajoute ce décalage aux notes jouées.
KEY_OFFSET = {
    "black-and-blue-basses": 12,
}

# Amplis : captures NAM de la communauté (GPL-3.0), https://github.com/pelennor2170/NAM_models
NAM_REPO = "pelennor2170/NAM_models"
# Baffles : réponses impulsionnelles « Jesters Brutal / Emerald Pack » (CC0), copiées dans le projet OrbitCab
IR_REPO = "darwinscat/orbitcab"
IR_DIR = "resources/ir"


def _download(url: str, dest: pathlib.Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "remaster-amiga-music"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def _raw(repo: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/HEAD/{urllib.parse.quote(path)}"


def _safe(base: pathlib.Path, rel: str) -> pathlib.Path:
    rel = posixpath.normpath(rel.replace("\\", "/"))
    parts = rel.split("/")
    if rel.startswith("/") or ".." in parts or any(":" in x for x in parts):
        raise ValueError(f"chemin hors de la banque : {rel}")
    return base.joinpath(*parts)


def bank_file(bank: str, rel: str) -> pathlib.Path:
    repo = BANKS[bank]
    base = LIB / bank
    p = _safe(base, rel)
    if not p.exists():
        _download(_raw(repo, rel), p)
    return p


def load_sfz(bank: str, program: str, cc: dict | None = None) -> sfz.Instrument:
    def read_text(rel):
        b = bank_file(bank, rel).read_bytes()
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return b.decode("latin-1")
    return sfz.Instrument(program, read_text, lambda rel: bank_file(bank, rel), {int(k): float(v) for k, v in (cc or {}).items()})


def nam_model(name: str) -> pathlib.Path:
    """Un ampli par son nom de fichier dans NAM_models (sans .nam)."""
    p = LIB / "amps" / f"{name}.nam"
    if not p.exists():
        _download(_raw(NAM_REPO, f"{name}.nam"), p)
    return p


def cab_ir(name: str) -> pathlib.Path:
    """Un baffle par son nom de fichier dans le dossier des IR (sans .wav), ex. « 03-kitten-slayer »."""
    p = LIB / "cabs" / f"{name}.wav"
    if not p.exists():
        _download(_raw(IR_REPO, f"{IR_DIR}/{name}.wav"), p)
    return p
