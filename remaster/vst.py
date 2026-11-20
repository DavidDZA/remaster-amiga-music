"""Les VST3 : où les trouver, lesquels marchent, jouer une piste avec un instrument VST, l'écouter en direct.

Deux dossiers : tools/vst3/ (VST libres téléchargés par scripts/setup_tools.py, ignoré par git ; plus
tools/dragonfly/) et
C:\\Program Files\\Common Files\\VST3 (VST installés par leur installeur). Un VST se désigne par son nom de fichier
sans « .vst3 » : « Surge XT », « Dexed », « MT-PowerDrumKit »…

Le son choisi (preset, réglages) est l'état du plugin (`raw_state`) : un fichier binaire rangé dans
songs/vst/<musique>/ et nommé dans la fiche :
    "vsti": {"plugin": "Surge XT", "state": "vst/Dr Mario/s05.bin", "bend_range": 2}

Certains VST font planter le programme qui les charge (MT Power Drum Kit 2 avec Pedalboard) : le catalogue
(`python -m remaster.vst`) essaie chaque VST dans un processus à part et retient ceux qui marchent.
"""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
import numpy as np
import mido

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOLS_VST = ROOT / "tools" / "vst3"
SYSTEM_VST = pathlib.Path(os.environ.get("COMMONPROGRAMFILES", r"C:\Program Files\Common Files")) / "VST3"
SONGS = ROOT / "songs"
CATALOGUE = TOOLS_VST / "catalogue.json"
DIRS = (TOOLS_VST, ROOT / "tools" / "dragonfly", SYSTEM_VST)


def _binary(p: pathlib.Path) -> pathlib.Path | None:
    """Le fichier à charger : dans un paquet (<nom>.vst3/Contents/x86_64-win/<nom>.vst3) ou un .vst3 seul."""
    if p.is_file():
        return p
    inner = p / "Contents" / "x86_64-win" / p.name
    return inner if inner.is_file() else None


def installed() -> dict[str, pathlib.Path]:
    """{nom: fichier à charger} de tous les VST3 des deux dossiers (ceux de tools/ d'abord)."""
    out: dict[str, pathlib.Path] = {}
    for d in DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.rglob("*.vst3")):
            if any(q.suffix == ".vst3" for q in p.parents):  # le fichier interne d'un paquet
                continue
            b = _binary(p)
            if b and p.stem not in out:
                out[p.stem] = b.resolve()
    return out


def find(name: str) -> pathlib.Path:
    found = installed()
    for k, v in found.items():
        if k.lower() == name.lower():
            return v
    raise SystemExit(f"VST3 absent : {name} (lancer scripts/setup_tools.py, ou l'installer) ; "
                     f"trouvés : {', '.join(sorted(found)) or 'aucun'}")


# ---------------------------------------------------------------- catalogue

def probe(path: pathlib.Path) -> dict:
    """Charge le VST dans un processus à part : s'il plante, seul ce processus tombe."""
    try:
        r = subprocess.run([sys.executable, "-m", "remaster.vst", "--sonde", str(path)], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    except subprocess.TimeoutExpired:
        return {"ok": False, "erreur": "trop long à charger (plus de 3 min)"}
    for line in reversed(r.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    err = (r.stderr.strip().splitlines() or [f"code {r.returncode}"])[-1]
    return {"ok": False, "erreur": "plantage au chargement" if r.returncode in (3221225477, -1073741819, 139)
            else err[:200]}


def _probe_here(path: str) -> dict:
    import pedalboard as pb
    p = pb.load_plugin(path)
    info = {"ok": True, "nom": p.name, "instrument": bool(p.is_instrument), "parametres": len(p.parameters)}
    if p.is_instrument:
        msgs = [mido.Message("note_on", note=60, velocity=100, time=0.0),
                mido.Message("note_off", note=60, time=0.5)]
        a = p(msgs, duration=1.0, sample_rate=48000, num_channels=2)
        info["son"] = bool(np.abs(a).max() > 1e-4)
    return info


def catalogue(refresh: bool = False, log=print) -> dict[str, dict]:
    """{nom: {"ok", "instrument", "chemin", …}} ; gardé dans tools/vst3/catalogue.json (refait si un VST change)."""
    old = {}
    if CATALOGUE.exists() and not refresh:
        old = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    out = {}
    for name, path in installed().items():
        stamp = f"{path}|{path.stat().st_mtime_ns}"
        if old.get(name, {}).get("empreinte") == stamp:
            out[name] = old[name]
            continue
        log(f"  essai : {name}…")
        out[name] = {**probe(path), "chemin": str(path), "empreinte": stamp}
    TOOLS_VST.mkdir(parents=True, exist_ok=True)
    CATALOGUE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


# ---------------------------------------------------------------- chargement et état

_CACHE: dict = {}


def load(name: str):
    """Le plugin (gardé en mémoire : le recharger coûte plusieurs secondes)."""
    import pedalboard as pb
    if name not in _CACHE:
        _CACHE[name] = pb.load_plugin(str(find(name)))
    return _CACHE[name]


def state_path(rel: str) -> pathlib.Path:
    return SONGS / rel


def state_hash(spec: dict | None) -> str:
    """Empreinte de l'état enregistré (pour le cache des pistes : un autre preset = une piste à refaire)."""
    if not spec or not spec.get("state"):
        return ""
    p = state_path(spec["state"])
    return hashlib.sha1(p.read_bytes()).hexdigest() if p.exists() else "absent"


def prepare(spec: dict):
    """Le plugin d'une fiche, avec son état et ses paramètres."""
    plug = load(spec["plugin"])
    if spec.get("state"):
        p = state_path(spec["state"])
        if not p.exists():
            raise SystemExit(f"état du VST absent : {p} (le refaire avec python -m remaster.choisir)")
        plug.raw_state = p.read_bytes()
    for k, v in (spec.get("params") or {}).items():
        setattr(plug, k, v)
    # certains VST ne chargent leur preset qu'au premier passage de son (Surge XT : le premier rendu après
    # raw_state était muet) : un quart de seconde à vide avant le vrai rendu
    if plug.is_instrument:
        plug([], duration=0.25, sample_rate=48000, num_channels=2, reset=False)
    else:
        plug.process(np.zeros((2, 12000), np.float32), 48000, reset=False)
    plug.reset()
    return plug


# ---------------------------------------------------------------- jouer une piste

def to_messages(events, spec: dict, source_bend_range: float, start: float = 0.0) -> list[mido.Message]:
    """Événements (temps, message) de la fiche → messages pour le VST (temps en secondes depuis `start`).

    - Pitch bend : nos courbes sont écrites pour ±source_bend_range demi-tons ; le synthé a sa propre amplitude
      (souvent ±2) : `bend_range` dans la fiche. Au-delà, le bend est écrêté.
    - Volume du module (CC 11) : beaucoup de synthés l'ignorent ; il devient la vélocité de la note
      (`"expression": "velocity"`, par défaut), ou reste un CC 11 (`"expression": "cc11"`).
    """
    target = float(spec.get("bend_range", 2))
    mode = spec.get("expression", "velocity")
    expr = 127
    out = []
    for t, m in sorted(events, key=lambda e: (e[0], 0 if e[1].type == "note_off" else 1)):
        if t < start:
            if m.type == "control_change" and m.control == 11:
                expr = m.value
            continue
        if m.type == "pitchwheel":
            semis = m.pitch / 8192 * source_bend_range
            m = m.copy(pitch=max(-8192, min(8191, round(semis / target * 8192))))
        elif m.type == "control_change" and m.control == 11:
            expr = m.value
            if mode != "cc11":
                continue
        elif m.type == "note_on" and m.velocity > 0 and mode != "cc11":
            m = m.copy(velocity=max(1, min(127, round(m.velocity * expr / 127))))
        out.append(m.copy(time=float(t - start)))
    return out


def render(spec: dict, events, duration: float, sr: int, source_bend_range: float) -> np.ndarray:
    """Une piste jouée par un instrument VST3 : (2, n) float32."""
    plug = prepare(spec)
    msgs = to_messages(events, spec, source_bend_range)
    audio = plug(msgs, duration=duration, sample_rate=sr, num_channels=2, buffer_size=512, reset=True)
    return np.asarray(audio, np.float32)


# ---------------------------------------------------------------- écoute en direct

class Audition:
    """Pendant que la fenêtre du VST est ouverte, un extrait passe en boucle dans le VST, vers les haut-parleurs :
    chaque changement de preset s'entend tout de suite.

    instrument : `events` = [(temps, message)] joués par le VST ;
    effet      : `audio` = (2, n) passé dans le VST.
    """

    def __init__(self, plug, sr_events_audio, events=None, audio=None, source_bend_range=24.0, spec=None,
                 block=2048, volume=0.5):
        self.plug, self.events, self.audio = plug, events, audio
        self.sr = sr_events_audio
        self.bend, self.spec = source_bend_range, spec or {}
        self.block, self.volume = block, volume
        self.stop = threading.Event()
        self.error: BaseException | None = None

    def _loop(self, stream):
        sr = int(stream.sample_rate)
        block = self.block
        if self.events is not None:
            length = max((t for t, _ in self.events), default=0.0) + 1.0
            msgs = to_messages(self.events, self.spec, self.bend)
        else:  # l'extrait est déjà rendu à la fréquence de la carte son
            length = self.audio.shape[1] / sr
        n_total = int(length * sr)
        while not self.stop.is_set():
            pos = 0
            while pos < n_total and not self.stop.is_set():
                t0, t1 = pos / sr, (pos + block) / sr
                if self.events is not None:
                    chunk = [m.copy(time=m.time - t0) for m in msgs if t0 <= m.time < t1]
                    y = self.plug(chunk, duration=block / sr, sample_rate=sr, num_channels=2,
                                  buffer_size=block, reset=False)
                else:
                    x = self.audio[:, pos:pos + block]
                    if x.shape[1] < block:
                        x = np.pad(x, ((0, 0), (0, block - x.shape[1])))
                    y = self.plug.process(x, sr, buffer_size=block, reset=False)
                y = np.clip(np.asarray(y, np.float32) * self.volume, -0.9, 0.9)  # protège les oreilles
                stream.write(y, sr)
                pos += block
            if self.events is not None:  # fin de la boucle : on coupe tout ce qui sonne encore
                off = [mido.Message("control_change", channel=c, control=123, value=0, time=0.0) for c in (0, 9)]
                self.plug(off, duration=block / sr, sample_rate=sr, num_channels=2, buffer_size=block, reset=False)

    def run(self, stream):
        try:
            self._loop(stream)
        except BaseException as e:  # noqa: BLE001  (affiché par le fil principal)
            self.error = e


def output_stream():
    from pedalboard.io import AudioStream
    return AudioStream(output_device_name=AudioStream.default_output_device_name, num_output_channels=2)


def listen_while_editing(plug, **kw) -> None:
    """Ouvre la fenêtre du VST (bloque jusqu'à sa fermeture) en jouant l'extrait en boucle."""
    with output_stream() as stream:
        aud = Audition(plug, int(stream.sample_rate), **kw)
        th = threading.Thread(target=aud.run, args=(stream,), daemon=True)
        th.start()
        try:
            plug.show_editor(aud.stop)
        finally:
            aud.stop.set()
            th.join(timeout=5)
    if aud.error:
        raise aud.error


# ---------------------------------------------------------------- ligne de commande

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) == 3 and sys.argv[1] == "--sonde":
        print(json.dumps(_probe_here(sys.argv[2]), ensure_ascii=False), flush=True)
        return
    import argparse
    ap = argparse.ArgumentParser(description="Liste les VST3 trouvés et essaie chacun (catalogue).")
    ap.add_argument("--refaire", action="store_true", help="réessayer tous les VST, même ceux déjà essayés")
    a = ap.parse_args()
    print(f"VST3 cherchés dans : {TOOLS_VST} et {SYSTEM_VST}")
    cat = catalogue(refresh=a.refaire)
    for kind, label in ((True, "Instruments"), (False, "Effets")):
        rows = [(k, v) for k, v in sorted(cat.items(), key=lambda kv: kv[0].lower())
                if v.get("ok") and v.get("instrument") == kind]
        print(f"\n{label} ({len(rows)}) :")
        for k, v in rows:
            mute = "" if v.get("son", True) else "  (aucun son à l'essai : preset à choisir)"
            print(f"  {k}{mute}")
    bad = [(k, v) for k, v in sorted(cat.items()) if not v.get("ok")]
    if bad:
        print(f"\nInutilisables ({len(bad)}) :")
        for k, v in bad:
            print(f"  {k} : {v.get('erreur')}")


if __name__ == "__main__":
    main()
