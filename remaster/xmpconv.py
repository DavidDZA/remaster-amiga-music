"""Convertit en .mod (ProTracker) les musiques Amiga d'autres formats, grâce à libxmp.

libxmp (bibliothèque libre, compilée dans tools/libxmp/bin/libxmp.dll par scripts/build_libxmp.py) lit plus de
90 formats : OctaMED, SoundFX, Game Music Creator, et beaucoup de modules « compactés » des jeux (The Player 4,
Digital Illusions…). On relit sa représentation (motifs, samples, effets) et on la réécrit en .mod, le format que
lit Remaster AMIGA Music :

- hauteurs : la note libxmp est calée sur celle du .mod d'origine (Dr Mario : C-2 ProTracker = note 61), transposition
  et finetune des samples compris ; on écrit la période exacte, même hors des 3 octaves de ProTracker ;
- motifs de longueur quelconque (OctaMED) : découpés par 64 lignes, un « D00 » termine un motif plus court ;
- volume en colonne (OctaMED, XM) : devient un effet Cxx si la case n'a pas d'autre effet ;
- samples 16 bits ramenés à 8 bits ; instruments de synthèse (non échantillonnés) : laissés vides ;
- effets propres à un format (au-delà de Fxx) : ignorés.
"""
from __future__ import annotations
import ctypes as C
import pathlib
import struct
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
DLL = ROOT / "tools" / "libxmp" / "bin" / "libxmp.dll"
NOTE_C2 = 61            # note libxmp du C-2 ProTracker (période 428) : mesuré sur Dr Mario
XMP_KEY_OFF = 0x81
SAMPLE_16BIT, SAMPLE_LOOP, SAMPLE_SYNTH = 1, 2, 1 << 15


class Event(C.Structure):
    _fields_ = [("note", C.c_ubyte), ("ins", C.c_ubyte), ("vol", C.c_ubyte), ("fxt", C.c_ubyte),
                ("fxp", C.c_ubyte), ("f2t", C.c_ubyte), ("f2p", C.c_ubyte), ("flag", C.c_ubyte)]


class Track(C.Structure):
    _fields_ = [("rows", C.c_int), ("event", Event * 1)]


class Pattern(C.Structure):
    _fields_ = [("rows", C.c_int), ("index", C.c_int * 1)]


class Envelope(C.Structure):
    _fields_ = [("flg", C.c_int), ("npt", C.c_int), ("scl", C.c_int), ("sus", C.c_int), ("sue", C.c_int),
                ("lps", C.c_int), ("lpe", C.c_int), ("data", C.c_short * 64)]


class SubInstrument(C.Structure):
    _fields_ = [(n, C.c_int) for n in ("vol", "gvl", "pan", "xpo", "fin", "vwf", "vde", "vra", "vsw", "rvv",
                                       "sid", "nna", "dct", "dca", "ifc", "ifr")]


class KeyMap(C.Structure):
    _fields_ = [("ins", C.c_ubyte), ("xpo", C.c_byte)]


class Instrument(C.Structure):
    _fields_ = [("name", C.c_char * 32), ("vol", C.c_int), ("nsm", C.c_int), ("rls", C.c_int),
                ("aei", Envelope), ("pei", Envelope), ("fei", Envelope), ("map", KeyMap * 121),
                ("sub", C.POINTER(SubInstrument)), ("extra", C.c_void_p)]


class Sample(C.Structure):
    _fields_ = [("name", C.c_char * 32), ("len", C.c_int), ("lps", C.c_int), ("lpe", C.c_int),
                ("flg", C.c_int), ("data", C.POINTER(C.c_ubyte))]


class Channel(C.Structure):
    _fields_ = [("pan", C.c_int), ("vol", C.c_int), ("flg", C.c_int)]


class Module(C.Structure):
    _fields_ = [("name", C.c_char * 64), ("type", C.c_char * 64)] + \
               [(n, C.c_int) for n in ("pat", "trk", "chn", "ins", "smp", "spd", "bpm", "len", "rst", "gvl")] + \
               [("xxp", C.POINTER(C.POINTER(Pattern))), ("xxt", C.POINTER(C.POINTER(Track))),
                ("xxi", C.POINTER(Instrument)), ("xxs", C.POINTER(Sample)),
                ("xxc", Channel * 64), ("xxo", C.c_ubyte * 256)]


class Sequence(C.Structure):
    _fields_ = [("entry_point", C.c_int), ("duration", C.c_int)]


class ModuleInfo(C.Structure):
    _fields_ = [("md5", C.c_ubyte * 16), ("vol_base", C.c_int), ("mod", C.POINTER(Module)),
                ("comment", C.c_char_p), ("num_sequences", C.c_int), ("seq_data", C.POINTER(Sequence))]


class FrameInfo(C.Structure):
    _fields_ = [(n, C.c_int) for n in ("pos", "pattern", "row", "num_rows", "frame", "speed", "bpm", "time",
                                       "total_time", "frame_time")] + \
               [("buffer", C.c_void_p)] + \
               [(n, C.c_int) for n in ("buffer_size", "total_size", "volume", "loop_count", "virt_channels",
                                       "virt_used", "sequence")] + \
               [("channel_info", C.c_ubyte * (64 * 64))]  # détail des voies : non utilisé, place réservée


_lib = None


def lib():
    global _lib
    if _lib is None:
        if not DLL.exists():
            raise SystemExit("libxmp absente : lancer  .venv\\Scripts\\python scripts\\build_libxmp.py")
        _lib = C.CDLL(str(DLL))
        _lib.xmp_create_context.restype = C.c_void_p
        _lib.xmp_load_module.argtypes = [C.c_void_p, C.c_char_p]
        _lib.xmp_get_module_info.argtypes = [C.c_void_p, C.POINTER(ModuleInfo)]
        _lib.xmp_release_module.argtypes = [C.c_void_p]
        _lib.xmp_free_context.argtypes = [C.c_void_p]
        _lib.xmp_start_player.argtypes = [C.c_void_p, C.c_int, C.c_int]
        _lib.xmp_play_frame.argtypes = [C.c_void_p]
        _lib.xmp_get_frame_info.argtypes = [C.c_void_p, C.POINTER(FrameInfo)]
        _lib.xmp_end_player.argtypes = [C.c_void_p]
    return _lib


class Loaded:
    """Une musique chargée par libxmp (à utiliser avec « with »)."""

    def __init__(self, path: pathlib.Path):
        self.ctx = lib().xmp_create_context()
        err = lib().xmp_load_module(self.ctx, str(path).encode("mbcs"))
        if err != 0:
            lib().xmp_free_context(self.ctx)
            raise ValueError(f"libxmp ne sait pas lire ce fichier (code {err})")
        self.info = ModuleInfo()
        lib().xmp_get_module_info(self.ctx, C.byref(self.info))
        self.mod = self.info.mod.contents

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        lib().xmp_release_module(self.ctx)
        lib().xmp_free_context(self.ctx)

    @property
    def format(self) -> str:
        return self.mod.type.decode("latin-1", "replace")

    @property
    def duration(self) -> float:
        """Durée du premier morceau du fichier, en secondes, selon libxmp."""
        return self.info.seq_data[0].duration / 1000 if self.info.num_sequences else 0.0

    def event(self, pattern: int, channel: int, row: int) -> Event:
        p = self.mod.xxp[pattern].contents
        idx = C.cast(C.addressof(p) + Pattern.index.offset, C.POINTER(C.c_int))[channel]
        t = self.mod.xxt[idx].contents
        if row >= t.rows:
            return Event()
        return C.cast(C.addressof(t) + Track.event.offset, C.POINTER(Event))[row]

    def pattern_rows(self, pattern: int) -> int:
        return self.mod.xxp[pattern].contents.rows

    def timeline(self, max_seconds: float = 1200) -> list[tuple[int, int, int, float]]:
        """Le morceau joué par libxmp : (motif, ligne, vitesse, durée d'un tick en secondes) à chaque nouvelle
        ligne, dans l'ordre d'écoute. C'est le tempo réel, quelle que soit l'unité du format (OctaMED…)."""
        L = lib()
        out = []
        if L.xmp_start_player(self.ctx, 8000, 4) != 0:  # 8 kHz mono : on ne garde pas le son
            return out
        fi = FrameInfo()
        last = None
        t = 0.0
        while L.xmp_play_frame(self.ctx) == 0:
            L.xmp_get_frame_info(self.ctx, C.byref(fi))
            if fi.loop_count > 0 or t > max_seconds:
                break
            key = (fi.pos, fi.pattern, fi.row)
            if key != last:
                out.append((fi.pattern, fi.row, fi.speed, fi.frame_time / 1e6))
                last = key
            t += fi.frame_time / 1e6
        L.xmp_end_player(self.ctx)
        return out


def period_of(note: int) -> int:
    """Période Amiga d'une note libxmp : la table de ProTracker (C-1 … B-3), prolongée d'octave en octave."""
    from .modfile import PERIODS
    k = note - (NOTE_C2 - 12)          # 0 = C-1
    if 0 <= k < 36:
        return PERIODS[k]
    octave, i = divmod(k, 12)          # hors table : la même note de l'octave 1, divisée ou multipliée par 2
    return max(28, min(4095, round(PERIODS[i] / 2 ** octave)))


def to_mod(src: pathlib.Path, title: str | None = None) -> tuple[bytes, dict]:
    """Le fichier converti en .mod, et un compte rendu (format, voies, pertes)."""
    with Loaded(src) as m:
        mod = m.mod
        report = {"format": m.format, "voies": mod.chn, "durée_libxmp": round(m.duration, 1), "pertes": []}
        if mod.chn > 32:
            raise ValueError(f"{mod.chn} voies : trop pour un .mod")
        # instruments → samples du .mod (31 au plus)
        nins = min(mod.ins, 31)
        if mod.ins > 31:
            report["pertes"].append(f"{mod.ins - 31} instruments au-delà de 31")
        samples, tune = [], []
        for i in range(nins):
            ins = mod.xxi[i]
            if ins.nsm < 1 or not ins.sub:
                samples.append((ins.name, b"", 0, 0, 0, 0))
                tune.append((0, 0))
                continue
            sub = ins.sub[0]
            sid = sub.sid
            if not (0 <= sid < mod.smp):
                samples.append((ins.name, b"", 0, 0, 0, 0))
                tune.append((0, 0))
                continue
            s = mod.xxs[sid]
            if s.flg & SAMPLE_SYNTH or not s.data or s.len <= 0:
                if s.flg & SAMPLE_SYNTH:
                    report["pertes"].append(f"instrument {i + 1} : synthèse")
                samples.append((ins.name, b"", 0, 0, 0, 0))
                tune.append((0, 0))
                continue
            if s.flg & SAMPLE_16BIT:
                raw = np.ctypeslib.as_array(C.cast(s.data, C.POINTER(C.c_int16)), (s.len,))
                data = (raw.astype(np.int32) >> 8).astype(np.int8).tobytes()
            else:
                data = bytes(np.ctypeslib.as_array(s.data, (s.len,)))
            data = data[: 131070 & ~1]
            if len(data) % 2:
                data += b"\0"
            lps, lpe = (s.lps, s.lpe) if s.flg & SAMPLE_LOOP else (0, 0)
            lps, lpe = min(lps, len(data)) & ~1, min(lpe, len(data)) & ~1
            vol = max(0, min(64, round(sub.vol * 64 / max(1, m.info.vol_base))))
            # finetune libxmp : 1/128 de demi-ton → crans ProTracker de 1/8 de demi-ton (-8 … 7) ;
            # ce qui dépasse passe dans la transposition (en demi-tons)
            semis, rest = divmod(sub.fin, 128)
            ft = round(rest / 16)
            if ft > 7:
                semis, ft = semis + 1, ft - 16
            samples.append((ins.name, data, vol, lps, lpe - lps if lpe > lps + 2 else 0, ft & 0x0F))
            tune.append((sub.xpo + semis, 0))
        while len(samples) < 31:
            samples.append((b"", b"", 0, 0, 0, 0))
            tune.append((0, 0))

        # motifs : découpés par 64 lignes
        out_patterns: list[list[list[bytes]]] = []
        chunks_of: dict[int, list[int]] = {}
        for p in range(mod.pat):
            rows = m.pattern_rows(p)
            ids = []
            for start in range(0, max(rows, 1), 64):
                n = min(64, rows - start)
                cells = []
                for r in range(64):
                    line = []
                    for c in range(mod.chn):
                        if r < n:
                            line.append(_cell(m.event(p, c, start + r), tune, report))
                        else:
                            line.append(bytes(4))
                    cells.append(line)
                if n < 64:
                    _put_break(cells, n - 1)
                ids.append(len(out_patterns))
                out_patterns.append(cells)
            chunks_of[p] = ids
        orders = []
        for k in range(mod.len):
            orders += chunks_of.get(mod.xxo[k], [])
        if len(orders) > 128:
            report["pertes"].append(f"ordre tronqué ({len(orders)} positions → 128)")
            orders = orders[:128]
        if len(out_patterns) > 128:
            raise ValueError(f"{len(out_patterns)} motifs : trop pour un .mod")
        # tempo : celui que joue vraiment libxmp, réécrit en commandes Fxx de ProTracker (les Fxx d'origine,
        # dans l'unité de leur format, sont enlevés)
        for pat in out_patterns:
            for line in pat:
                for c, cell in enumerate(line):
                    if cell[2] & 0x0F == 0x0F:
                        line[c] = cell[:2] + bytes([cell[2] & 0xF0, 0])
        state = (6, 125)
        done = set()
        for p, r, speed, tick in m.timeline():
            if p not in chunks_of or tick <= 0 or (p, r) in done:
                continue
            done.add((p, r))
            want = _pt_tempo(speed, tick)
            ids = chunks_of[p]
            cells = out_patterns[ids[min(r // 64, len(ids) - 1)]]
            if want[0] != state[0]:
                _put_effect(cells, r % 64, 0x0F, want[0], force=True)
            if want[1] != state[1]:
                _put_effect(cells, r % 64, 0x0F, want[1], force=True)
            state = want

        name = (title or mod.name.decode("latin-1", "replace") or src.stem)[:20]
        head = name.encode("latin-1", "replace").ljust(20, b"\0")
        for nm, data, vol, lps, lpl, ft in samples:
            nm = (nm if isinstance(nm, bytes) else bytes(nm))[:22].ljust(22, b"\0")
            head += nm + struct.pack(">HBBHH", len(data) // 2, ft, vol, lps // 2, max(1, lpl // 2))
        tag = {4: b"M.K.", 6: b"6CHN", 8: b"8CHN"}.get(mod.chn, f"{mod.chn:02d}CH".encode())
        head += bytes([len(orders), 127]) + bytes(orders).ljust(128, b"\0") + tag
        body = b"".join(b"".join(b"".join(line) for line in pat) for pat in out_patterns)
        return head + body + b"".join(s[1] for s in samples), report


def _cell(e: Event, tune, report) -> bytes:
    period, ins, fx, fp = 0, e.ins, 0, 0
    if e.note and e.note < XMP_KEY_OFF:
        xpo, fin = tune[ins - 1] if 0 < ins <= len(tune) else (0, 0)
        period = period_of(e.note + xpo)
        period = max(28, min(4095, period))
    elif e.note == XMP_KEY_OFF or e.note == XMP_KEY_OFF + 1:  # note coupée : volume 0
        fx, fp = 0x0C, 0
    for t, p in ((e.fxt, e.fxp), (e.f2t, e.f2p)):
        if (t or p) and t <= 0x0F and not (fx or fp):
            fx, fp = t, p
    if e.vol and not (fx or fp):
        fx, fp = 0x0C, min(64, e.vol - 1)
    if ins > 31:
        ins = 0
    return bytes([(ins & 0xF0) | (period >> 8), period & 0xFF, ((ins & 0x0F) << 4) | (fx & 0x0F), fp & 0xFF])


def _pt_tempo(speed: int, tick: float) -> tuple[int, int]:
    """(vitesse, BPM) ProTracker qui donnent la même durée de ligne : un tick ProTracker dure 2,5 / BPM s."""
    bpm = 2.5 / tick
    if 32 <= bpm <= 255 and 1 <= speed <= 31:
        return speed, round(bpm)
    row = speed * tick
    best = min(((abs(s * 2.5 / b - row), s, b) for s in range(1, 32) for b in range(32, 256)))
    return best[1], best[2]


def _put_effect(cells, row: int, fx: int, param: int, force: bool = False) -> bool:
    """Met un effet sur une ligne, dans la première voie libre ; faux s'il n'y a pas de place.
    force : sans voie libre, remplace l'effet d'une voie (sauf un saut Bxx / Dxx ou un autre Fxx)."""
    for c, cell in enumerate(cells[row]):
        if not (cell[2] & 0x0F) and not cell[3]:
            cells[row][c] = cell[:2] + bytes([(cell[2] & 0xF0) | fx, param])
            return True
    if force:
        for c in range(len(cells[row]) - 1, -1, -1):
            cell = cells[row][c]
            if cell[2] & 0x0F not in (0x0B, 0x0D, 0x0F):
                cells[row][c] = cell[:2] + bytes([(cell[2] & 0xF0) | fx, param])
                return True
    return False


def _put_break(cells, row: int):
    if not _put_effect(cells, row, 0x0D, 0):
        c = len(cells[row]) - 1  # pas de voie libre : le saut passe avant l'effet de la dernière voie
        cell = cells[row][c]
        cells[row][c] = cell[:2] + bytes([(cell[2] & 0xF0) | 0x0D, 0])
