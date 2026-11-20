"""Un petit lecteur SFZ (format ouvert d'instruments échantillonnés) en numpy.

Gère ce dont ont besoin les banques de sfzinstruments : #include, #define, <control>/<global>/<master>/<group>/
<region>, couches de vélocité (amp_velcurve_N), prises alternées (seq_length / seq_position, lorand / hirand),
conditions de contrôleurs (loccN / hiccN, set_ccN, set_hdccN), enveloppe (ampeg_*), groupes qui se coupent
(group / off_by), note_polyphony, one_shot, volume / amplitude / pan / tune / transpose, pitch bend et expression
(CC 11). Batteries multi-micros (format « ARIA » de kinwie : Muldjord, Naked Drums, Sonor…) : plusieurs #include
sur une ligne, amplitude_onccN / volume_onccN / pan_onccN avec leurs courbes (*_curveccN), réglés par set_hdccN.
Les échantillons sont chargés (et téléchargés au besoin, par `fetch`) seulement s'ils sont joués.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import math
import pathlib
import posixpath
import random
import re
import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

NOTE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}
_OPCODE = re.compile(r"([A-Za-z0-9_$]+)=")
_HEADER = re.compile(r"<(\w+)>")


def note_number(v: str) -> int:
    v = v.strip().lower()
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    m = re.fullmatch(r"([a-g])(#|b)?(-?\d+)", v)
    if not m:
        raise ValueError(f"note SFZ illisible : {v}")
    n = NOTE[m.group(1)] + (1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0)
    return n + (int(m.group(3)) + 1) * 12


class Region(dict):
    def num(self, key, default=0.0):
        v = self.get(key)
        if v is None:
            return default
        try:
            return float(v)
        except ValueError:
            return default

    def key_range(self):
        if "key" in self:
            k = note_number(self["key"])
            return k, k
        return note_number(self.get("lokey", "0")), note_number(self.get("hikey", "127"))

    def keycenter(self):
        if "pitch_keycenter" in self:
            return note_number(self["pitch_keycenter"])
        if "key" in self:
            return note_number(self["key"])
        return 60


class Instrument:
    """Une banque SFZ. `root` : le fichier .sfz, chemin relatif à la racine de la banque (style posix)."""

    def __init__(self, root: str, read_text, fetch, cc: dict | None = None):
        self.read_text = read_text  # chemin posix -> texte
        self.fetch = fetch          # chemin posix -> pathlib.Path local (télécharge si besoin)
        self.root_dir = posixpath.dirname(root)
        self.defines: dict[str, str] = {}
        self.control: dict[str, str] = {}
        self.regions: list[Region] = []
        self._parse_file(root)
        self.cc = {int(k[6:]): float(v) for k, v in self.control.items() if k.startswith("set_cc")}
        # set_hdccN : la même chose de 0 à 1
        self.cc.update({int(k[8:]): float(v) * 127 for k, v in self.control.items()
                        if k.startswith("set_hdcc") and k[8:].isdigit()})
        self.cc.update(cc or {})
        self.default_path = self.control.get("default_path", "")
        self._cache: dict[str, tuple[np.ndarray, int]] = {}

    # ---------- lecture du fichier
    def _parse_file(self, path: str):
        text = self.read_text(path)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        self._state = getattr(self, "_state", {"section": None, "global": {}, "master": {}, "group": {},
                                                 "region": None})
        for raw in text.splitlines():
            line = raw.split("//", 1)[0].strip()
            if not line:
                continue
            if line.startswith("#define"):  # parfois plusieurs sur une ligne : #define $a 1   #define $b 31
                for name, val in re.findall(r"#define\s+(\S+)\s+(.*?)(?=\s+#define\s|$)", line):
                    for prev in sorted(self.defines, key=len, reverse=True):  # une valeur peut en citer une autre
                        val = val.replace(prev, self.defines[prev])
                    self.defines[name] = val.strip()
                continue
            if line.startswith("#include"):  # parfois plusieurs sur une ligne : #include "a" #include "b"
                for inc in re.findall(r'#include\s+"([^"]+)"', line):
                    self._parse_file(posixpath.normpath(posixpath.join(self.root_dir, inc)))
                continue
            for name in sorted(self.defines, key=len, reverse=True):
                line = line.replace(name, self.defines[name])
            self._parse_line(line)

    def _parse_line(self, line: str):
        st = self._state
        pos = 0
        for hm in list(_HEADER.finditer(line)) + [None]:
            end = hm.start() if hm else len(line)
            self._opcodes(line[pos:end])
            if hm is None:
                break
            h = hm.group(1)
            st["section"] = h
            if h == "global":
                st["global"], st["master"], st["group"] = {}, {}, {}
            elif h == "master":
                st["master"], st["group"] = {}, {}
            elif h == "group":
                st["group"] = {}
            elif h == "region":
                r = Region({**st["global"], **st["master"], **st["group"]})
                self.regions.append(r)
                st["region"] = r
            pos = hm.end()

    def _opcodes(self, chunk: str):
        st = self._state
        ms = list(_OPCODE.finditer(chunk))
        for i, m in enumerate(ms):
            val = chunk[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(chunk)].strip()
            key = m.group(1)
            sec = st["section"]
            if sec == "control":
                self.control[key] = val
            elif sec in ("global", "master", "group"):
                st[sec][key] = val
            elif sec == "region" and st["region"] is not None:
                st["region"][key] = val

    # ---------- choix des régions
    def _active(self, r: Region, vel: int) -> bool:
        if r.get("trigger", "attack") not in ("attack", "first"):
            return False
        if "sw_last" in r or "sw_down" in r or "sw_up" in r:
            sw = self.control.get("sw_default") or r.get("sw_default")
            if sw is None or note_number(r.get("sw_last", "-1")) != note_number(sw):
                return False
        if not (r.num("lovel", 0) <= vel <= r.num("hivel", 127)):
            return False
        for k, v in r.items():
            if k.startswith("locc") and k[4:].isdigit():
                if self.cc.get(int(k[4:]), 0) < float(v):
                    return False
            elif k.startswith("hicc") and k[4:].isdigit():
                if self.cc.get(int(k[4:]), 0) > float(v):
                    return False
        return True

    def pick(self, key: int, vel: int, counters: dict, rng: random.Random):
        """Régions à jouer pour une note : [(région, demi-tons de transposition en plus)]."""
        cand = [r for r in self.regions if self._active(r, vel)]
        hit = [r for r in cand if r.key_range()[0] <= key <= r.key_range()[1]]
        shift = 0
        if not hit:  # note hors de la tessiture : la plus proche, transposée
            pitched = [r for r in cand if r.num("pitch_keytrack", 100) != 0 and r.get("sample") != "*silence"]
            if not pitched:
                return []

            def dist(r):
                lo, hi = r.key_range()
                return lo - key if key < lo else key - hi
            best = min(dist(r) for r in pitched)
            hit = [r for r in pitched if dist(r) == best]
            lo, hi = hit[0].key_range()
            near = lo if key < lo else hi
            shift = key - near
            key = near
        counters[key] = counters.get(key, 0) + 1
        rnd = rng.random()
        out = []
        for r in hit:
            n = int(r.num("seq_length", 1))
            if n > 1 and ((counters[key] - 1) % n) + 1 != int(r.num("seq_position", 1)):
                continue
            if not (r.num("lorand", 0) <= rnd < r.num("hirand", 1.0001)):
                continue
            out.append((r, shift, key))
        return out

    # ---------- échantillons
    def sample_path(self, r: Region) -> str | None:
        s = r.get("sample")
        if not s or s.startswith("*"):
            return None
        s = s.replace("\\", "/")
        return posixpath.normpath(posixpath.join(self.root_dir, self.default_path, s))

    def prefetch(self, paths):
        todo = [p for p in set(paths) if p and p not in self._cache]
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(self.fetch, todo))

    def load(self, path: str, sr: int) -> np.ndarray:
        if path not in self._cache:
            data, rate = sf.read(self.fetch(path), dtype="float32", always_2d=True)
            data = data.T
            if rate != sr:
                g = math.gcd(rate, sr)
                data = resample_poly(data, sr // g, rate // g, axis=1).astype(np.float32)
            self._cache[path] = (data, sr)
        return self._cache[path][0]


def _curve(r: Region, prefix: str, cc: int, x: float) -> float:
    """Courbe d'un contrôleur (x de 0 à 1) : <prefix>_curveccN, courbes par défaut de sfizz / ARIA."""
    c = int(r.num(f"{prefix}_curvecc{cc}", 0))
    x = max(0.0, min(1.0, x))
    return {0: x, 1: 2 * x - 1, 2: 1 - x, 3: 1 - 2 * x, 4: x * x, 5: math.sqrt(x), 6: math.sqrt(1 - x)}.get(c, x)


def cc_mods(r: Region, cc: dict) -> tuple[float, float]:
    """(gain, pan en %) apportés par les contrôleurs : amplitude_onccN (en %, se multiplient), volume_onccN (dB),
    pan_onccN (%)."""
    gain, pan = 1.0, 0.0
    for k, val in r.items():
        for prefix in ("amplitude_oncc", "volume_oncc", "pan_oncc"):
            if k.startswith(prefix) and k[len(prefix):].isdigit():
                n = int(k[len(prefix):])
                x = _curve(r, prefix.split("_")[0], n, cc.get(n, 0) / 127)
                v = float(val)
                if prefix == "amplitude_oncc":
                    gain *= x * v / 100
                elif prefix == "volume_oncc":
                    gain *= 10 ** (x * v / 20)
                else:
                    pan += x * v
    return gain, pan


def _vel_gain(r: Region, vel: int) -> float:
    track = r.num("amp_veltrack", 100) / 100
    pts = {0: 0.0, 127: 1.0}
    for k, v in r.items():
        if k.startswith("amp_velcurve_"):
            pts[int(k[13:])] = float(v)
    if len(pts) > 2:
        xs = sorted(pts)
        curve = float(np.interp(vel, xs, [pts[x] for x in xs]))
    else:
        curve = (vel / 127) ** 2
    return 1 - track * (1 - curve)


def _env(r: Region, n_on: int, n_total: int, sr: int, release_from: int | None, fast: bool) -> np.ndarray:
    """Enveloppe d'amplitude : délai, attaque, maintien, déclin vers le palier, puis relâchement."""
    a = r.num("ampeg_attack", 0) * sr
    h = r.num("ampeg_hold", 0) * sr
    d = r.num("ampeg_decay", 0) * sr
    s = r.num("ampeg_sustain", 100) / 100
    dl = r.num("ampeg_delay", 0) * sr
    t = np.arange(n_total, dtype=np.float32)
    env = np.ones(n_total, np.float32)
    if dl:
        env[t < dl] = 0
    tt = t - dl
    if a > 1:
        m = (tt >= 0) & (tt < a)
        env[m] = tt[m] / a
    if d > 1:
        m = tt >= a + h
        env[m] = s + (1 - s) * np.exp(-5 * (tt[m] - a - h) / d)
    elif s < 1:
        env[tt >= a + h] = s
    if release_from is not None and release_from < n_total:
        rel = 0.015 if fast else max(r.num("ampeg_release", 0.001), 0.001)
        k = np.arange(n_total - release_from, dtype=np.float32) / (rel * sr)
        env[release_from:] *= np.where(k < 1, np.exp(-6 * k), 0)
    return env


def render(inst: Instrument, events, duration: float, sr: int, bend_range: float = 24.0,
           seed: int = 0, smooth_ms: float = 8.0, choke: bool = False) -> np.ndarray:
    """events : [(temps en s, message mido)] d'un seul canal. Renvoie (2, n) en float32.

    choke : chaque nouvelle attaque coupe les notes précédentes (en 15 ms), comme un nouveau coup de médiator
    étouffe les cordes qui sonnaient ; les notes d'un même accord (même instant) sonnent ensemble.
    """
    n = int((duration + 4) * sr)
    out = np.zeros((2, n), np.float32)
    # courbes de pitch bend (demi-tons) et d'expression, échantillon par échantillon
    bend = np.zeros(n, np.float32)
    expr = np.ones(n, np.float32)
    evs = sorted(events, key=lambda e: e[0])
    for t, m in evs:
        i = min(n, int(t * sr))
        if m.type == "pitchwheel":
            bend[i:] = m.pitch / 8192 * bend_range
        elif m.type == "control_change" and m.control == 11:
            expr[i:] = (m.value / 127) ** 2
    if smooth_ms:
        w = max(1, int(sr * smooth_ms / 1000))
        k = np.ones(w, np.float32) / w
        bend = np.convolve(bend, k, mode="full")[:n].astype(np.float32)
        expr = np.convolve(expr, k, mode="full")[:n].astype(np.float32)
    rng = random.Random(seed)
    counters: dict = {}
    # notes : début, fin, régions
    notes = []
    pending: dict[int, list] = {}
    for t, m in evs:
        if m.type == "note_on" and m.velocity > 0:
            regs = inst.pick(m.note, m.velocity, counters, rng)
            note = {"key": m.note, "vel": m.velocity, "start": int(t * sr), "end": None, "regions": regs}
            notes.append(note)
            pending.setdefault(m.note, []).append(note)
        elif m.type in ("note_off", "note_on"):
            if pending.get(m.note):
                pending[m.note].pop(0)["end"] = int(t * sr)
    inst.prefetch(inst.sample_path(r) for nt in notes for r, _, _ in nt["regions"])
    # coupures : off_by (groupes) et note_polyphony
    voices = []  # (note, région, shift, clé jouée)
    for nt in notes:
        if choke:
            for v in voices:
                if v["start"] < nt["start"] and (v["cut"] is None or v["cut"] > nt["start"]):
                    v["cut"] = nt["start"]
                    v["fast"] = True
        for r, shift, k in nt["regions"]:
            g = r.get("group")
            if g is not None:
                for v in voices:
                    if v["r"].get("off_by") == g and v["start"] < nt["start"] and \
                            (v["cut"] is None or v["cut"] > nt["start"]):
                        v["cut"] = nt["start"]
                        v["fast"] = v["r"].get("off_mode", "fast") == "fast"
            if r.get("sample", "").startswith("*") or r.num("end", 0) == -1:
                continue  # région muette : ne sert qu'à couper les autres
            poly = r.get("note_polyphony")
            if poly is not None:
                same = [v for v in voices if v["key"] == nt["key"] and v["r"].get("group") == g and
                        (v["cut"] is None or v["cut"] > nt["start"])]
                excess = len(same) - int(float(poly)) + 1
                for v in same[:max(0, excess)]:
                    v["cut"] = nt["start"]
                    v["fast"] = False
            voices.append({"r": r, "shift": shift, "key": nt["key"], "keyc": k, "vel": nt["vel"],
                           "start": nt["start"], "end": nt["end"], "cut": None, "fast": False})
    for v in voices:
        r = v["r"]
        data = inst.load(inst.sample_path(r), sr)
        length = data.shape[1]
        off = int(r.num("offset", 0))
        end_s = int(r.num("end", length)) if r.num("end", length) > 0 else length
        end_s = min(end_s, length)
        if off >= end_s:
            continue
        semis = (v["keyc"] - r.keycenter()) * r.num("pitch_keytrack", 100) / 100 + v["shift"] \
            + r.num("transpose", 0) + r.num("tune", 0) / 100
        ratio = 2 ** (semis / 12)
        one_shot = r.get("loop_mode") == "one_shot"
        start = v["start"]
        release_at = None if one_shot else v["end"]
        if v["cut"] is not None and (release_at is None or v["cut"] < release_at):
            release_at = v["cut"]
        rel_len = int((0.015 if v["fast"] else max(r.num("ampeg_release", 0.001), 0.001)) * sr)
        max_len = int((end_s - off) / (ratio * 2 ** (-bend_range / 12))) + 1
        stop = start + max_len
        if release_at is not None:
            stop = min(stop, release_at + rel_len)
        stop = min(stop, n)
        if stop <= start:
            continue
        follows_bend = not (r.num("bend_up", 200) == 0 and r.num("bend_down", -200) == 0)
        inc = ratio * (np.exp2(bend[start:stop] / 12) if follows_bend else np.ones(stop - start, np.float32))
        pos = off + np.concatenate([[0.0], np.cumsum(inc[:-1], dtype=np.float64)])
        ok = pos < end_s - 1
        if not ok.all():
            last = int(np.argmin(ok))
            pos = pos[:last]
        m = len(pos)
        if m == 0:
            continue
        i0 = pos.astype(np.int64)
        frac = (pos - i0).astype(np.float32)
        seg = data[:, i0] * (1 - frac) + data[:, i0 + 1] * frac
        rel_rel = None if release_at is None else release_at - start
        env = _env(r, 0, m, sr, rel_rel, v["fast"])
        gain = 10 ** (r.num("volume", 0) / 20) * r.num("amplitude", 100) / 100 * _vel_gain(r, v["vel"])
        cc_gain, cc_pan = cc_mods(r, inst.cc)
        gain *= cc_gain
        sig = seg * env * gain * expr[start:start + m]
        pan = max(-1.0, min(1.0, (r.num("pan", 0) + cc_pan) / 100))
        ang = (pan + 1) * math.pi / 4
        if sig.shape[0] == 1:
            out[0, start:start + m] += sig[0] * math.cos(ang) * math.sqrt(2) * 0.7071
            out[1, start:start + m] += sig[0] * math.sin(ang) * math.sqrt(2) * 0.7071
        else:
            out[0, start:start + m] += sig[0] * math.cos(ang) * math.sqrt(2)
            out[1, start:start + m] += sig[1] * math.sin(ang) * math.sqrt(2)
    return out
