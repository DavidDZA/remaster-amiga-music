"""Construit UADE (émulateur des lecteurs de musique Amiga, GPL) dans tools\\uade\\.

    .venv\\Scripts\\python scripts\\build_uade.py

Il faut MSYS2 avec sa partie POSIX : C:\\msys64, et `pacman -S gcc make pkgconf` (UADE utilise fork et des
sockets : le gcc MinGW ne suffit pas). Étapes :
1. télécharge UADE 3.05, bencodetools et libzakalwe (gitlab) ;
2. compile dans un dossier temporaire **sans espaces** (les Makefile ne supportent pas « Nos documents ») :
   les deux bibliothèques en statique, puis libuade.a et l'émulateur uadecore.exe ;
3. compile native\\uade2wav.c (notre petit programme : joue une musique et l'écrit en WAV) ;
4. installe dans tools\\uade : bin\\ (uade2wav.exe, uadecore.exe, msys-2.0.dll) et data\\ (score, uaerc,
   eagleplayer.conf, uade.conf, players\\ : les 175 lecteurs Amiga).

Les chemins passés à UADE doivent être de la forme /cygdrive/f/… (voir remaster\\paula.py).
"""
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEST = ROOT / "tools" / "uade"
MSYS = pathlib.Path(r"C:\msys64")
SOURCES = {
    "uade": "https://gitlab.com/uade-music-player/uade/-/archive/uade-3.05/uade-uade-3.05.tar.gz",
    "bencodetools": "https://gitlab.com/heikkiorsila/bencodetools/-/archive/master/bencodetools-master.tar.gz",
    "libzakalwe": "https://gitlab.com/hors/libzakalwe/-/archive/master/libzakalwe-master.tar.gz",
}
ZAKALWE = ("array base bitfield endianess file input math mem norm_inv_table_65536 random string str_array time "
           "unix-support")

BUILD = r"""set -e
export PATH=/usr/bin:$PATH
R=$(cygpath -u "$1"); P=$R/inst
mkdir -p $P/lib $P/include
cd $R/bencodetools-*/
gcc -O2 -Iinclude -c bencode.c -o bencode.o
ar rcs $P/lib/libbencodetools.a bencode.o
cp -r include/* $P/include/
cd $R/libzakalwe-*/
./configure --prefix=$P > /dev/null
for m in %s; do gcc -O2 -I include -pthread -D_DEFAULT_SOURCE -c $m.c -o $m.o; done
ar rcs $P/lib/libzakalwe.a *.o
cp -r include/zakalwe $P/include/
cd $R/uade-*/
./configure --prefix=$P --bencode-tools-prefix=$P --libzakalwe-prefix=$P --without-uade123 --without-uadesimple \
    --without-write-audio --without-uadefs > /dev/null
make -C src/frontends/libuade libuade.a > /dev/null
make uadecore > /dev/null
gcc -O2 -Isrc/frontends/include -o $R/uade2wav.exe $R/uade2wav.c src/frontends/libuade/libuade.a \
    -L$P/lib -lbencodetools -lzakalwe -lm
""" % ZAKALWE


WRITE_FN_START = "void uade_write_audio_write(struct uade_write_audio *w, const int output[4],"
WRITE_FN_END = "void uade_write_audio_write_left_right("

NEW_WRITE_FN = r"""void uade_write_audio_write(struct uade_write_audio *w, const int output[4],
			    const unsigned long tdelta)
{
	/* Remaster AMIGA Music : seulement les événements (registres de Paula), pas le son de chaque voie ;
	   le temps écoulé entre deux événements est cumulé dans w->pending. */
	int ch;
	enum UADEPaulaEventType et;
	struct uade_write_audio_frame frame;
	(void) output;
	w->pending += tdelta;
	for (ch = 0; ch < 4; ch++) {
		struct channel_event *ce = &w->channel_events[ch];
		for (et = 1; et < PET_MAX_ENUM; et++) {
			if (!ce->active_events[et])
				continue;
			while (w->pending > 0x00ffffff) {
				memset(&frame, 0, sizeof(frame));
				write_be_u32(&frame.tdelta, 0x00ffffff);
				uade_atomic_fwrite(&frame, sizeof(frame), 1, w->f);
				w->pending -= 0x00ffffff;
			}
			memset(&frame, 0, sizeof(frame));
			write_be_u32(&frame.tdelta, (uint32_t) (w->pending | 0x80000000));
			w->pending = 0;
			frame.data.paula_event_frame.channel = ch;
			frame.data.paula_event_frame.event_type = et;
			write_be_u16(&frame.data.paula_event_frame.event_value, ce->event_values[et]);
			uade_atomic_fwrite(&frame, sizeof(frame), 1, w->f);
		}
	}
	memset(w->channel_events, 0, sizeof(w->channel_events));
}

int uade_write_audio_sample_known(struct uade_write_audio *w, uint32_t lc, uint32_t nbytes)
{
	int i;
	if (w->smp == NULL || w->nseen >= 4096)
		return 1;
	for (i = 0; i < w->nseen; i++)
		if (w->seen_lc[i] == lc && w->seen_len[i] == nbytes)
			return 1;
	return 0;
}

void uade_write_audio_sample(struct uade_write_audio *w, uint32_t lc, uint32_t nbytes, const uint8_t *data)
{
	uint8_t hdr[8];
	if (uade_write_audio_sample_known(w, lc, nbytes))
		return;
	w->seen_lc[w->nseen] = lc;
	w->seen_len[w->nseen] = nbytes;
	w->nseen++;
	hdr[0] = lc >> 24; hdr[1] = lc >> 16; hdr[2] = lc >> 8; hdr[3] = lc;
	hdr[4] = nbytes >> 24; hdr[5] = nbytes >> 16; hdr[6] = nbytes >> 8; hdr[7] = nbytes;
	fwrite(hdr, 1, 8, w->smp);
	fwrite(data, 1, nbytes, w->smp);
}

"""

AUDIO_OLD = """	if (write_audio_state != NULL && cdp->pt == cdp->lc)
	    uade_write_audio_set_state(write_audio_state, nr, PET_LOOP, 0);
"""
AUDIO_NEW = """	if (write_audio_state != NULL && cdp->pt == cdp->lc) {
	    /* démarrage du DMA = une note démarre : on note l'événement et on copie le sample joué (une fois) */
	    uae_u32 nbytes = (cdp->len ? cdp->len : 65536) * 2;
	    uade_write_audio_set_state(write_audio_state, nr, PET_LOOP, 0);
	    if (!uade_write_audio_sample_known(write_audio_state, cdp->lc, nbytes)) {
		static uae_u8 sbuf[131072];
		uae_u32 i;
		for (i = 0; i < nbytes; i += 2) {
		    uae_u32 v = chipmem_bank.wget(cdp->lc + i);
		    sbuf[i] = v >> 8;
		    sbuf[i + 1] = v & 0xff;
		}
		uade_write_audio_sample(write_audio_state, cdp->lc, nbytes, sbuf);
	    }
	}
"""


def patch_uade(src: pathlib.Path):
    """Modifie UADE pour extraire les notes (voir remaster/paula.py) :
    - le journal Paula (option « write audio ») ne garde que les événements : quelques Mo au lieu de 70 Mo / 30 s ;
    - au démarrage de chaque note, le sample joué est copié depuis la mémoire Amiga dans <journal>.smp."""
    wa = src / "src" / "write_audio.c"
    s = wa.read_text(encoding="latin-1")
    if "uade_write_audio_sample_known" in s:
        return
    s = s.replace("\tstruct channel_event channel_events[4];\n};",
                  "\tstruct channel_event channel_events[4];\n\tuint64_t pending;\n\tFILE *smp;\n"
                  "\tuint32_t seen_lc[4096];\n\tuint32_t seen_len[4096];\n\tint nseen;\n};")
    a, b = s.index(WRITE_FN_START), s.index(WRITE_FN_END)
    s = s[:a] + NEW_WRITE_FN + s[b:]
    # pas d'événements « sortie gauche / droite » (des millions par minute)
    s = s.replace("\tstruct uade_paula_event_frame *pef = &frame.data.paula_event_frame;\n\n\tif (!w->started)\n"
                  "\t\treturn;", "\tstruct uade_paula_event_frame *pef = &frame.data.paula_event_frame;\n\n"
                  "\treturn;\n\tif (!w->started)\n\t\treturn;")
    # fichier des samples à côté du journal
    s = s.replace('\t\tw->f = fopen(fname, "wb");',
                  '\t\tw->f = fopen(fname, "wb");\n\t\t{\n\t\t\tchar sname[4096];\n'
                  '\t\t\tsnprintf(sname, sizeof sname, "%s.smp", fname);\n\t\t\tw->smp = fopen(sname, "wb");\n\t\t}')
    s = s.replace("void uade_write_audio_close(struct uade_write_audio *w)\n{\n\tif (w == NULL)\n\t\treturn;",
                  "void uade_write_audio_close(struct uade_write_audio *w)\n{\n\tif (w == NULL)\n\t\treturn;\n"
                  "\tif (w->smp != NULL)\n\t\tfclose(w->smp);")
    wa.write_text(s, encoding="latin-1")
    h = src / "src" / "include" / "write_audio.h"
    t = h.read_text(encoding="latin-1")
    t = t.replace("void uade_write_audio_close(struct uade_write_audio *w);",
                  "void uade_write_audio_close(struct uade_write_audio *w);\n"
                  "int uade_write_audio_sample_known(struct uade_write_audio *w, uint32_t lc, uint32_t nbytes);\n"
                  "void uade_write_audio_sample(struct uade_write_audio *w, uint32_t lc, uint32_t nbytes,\n"
                  "\t\t\t     const uint8_t *data);")
    h.write_text(t, encoding="latin-1")
    au = src / "src" / "audio.c"
    u = au.read_text(encoding="latin-1")
    if AUDIO_OLD not in u:
        sys.exit("UADE : code de audio.c inattendu, la modification ne s'applique pas")
    au.write_text(u.replace(AUDIO_OLD, AUDIO_NEW), encoding="latin-1")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if (DEST / "bin" / "uade2wav.exe").exists():
        print("déjà là :", DEST)
        return
    bash = MSYS / "usr" / "bin" / "bash.exe"
    if not (MSYS / "usr" / "bin" / "gcc.exe").exists():
        sys.exit("Il faut MSYS2 (C:\\msys64) avec gcc POSIX :  C:\\msys64\\usr\\bin\\bash -lc \"pacman -S gcc make pkgconf\"")
    with tempfile.TemporaryDirectory(prefix="uade") as tmp:
        tmp = pathlib.Path(tmp)
        if " " in str(tmp):
            sys.exit(f"le dossier temporaire contient un espace : {tmp}")
        for name, url in SOURCES.items():
            print("téléchargement :", url)
            arch = tmp / f"{name}.tar.gz"
            with urllib.request.urlopen(url) as r, open(arch, "wb") as f:
                shutil.copyfileobj(r, f)
            with tarfile.open(arch) as t:
                t.extractall(tmp, filter="data")
        shutil.copy(ROOT / "native" / "uade2wav.c", tmp / "uade2wav.c")
        patch_uade(next(tmp.glob("uade-*/")))  # journal Paula « événements seulement » + copie des samples
        script = tmp / "build.sh"
        script.write_text(BUILD, encoding="utf-8", newline="\n")
        print("compilation (quelques minutes)…")
        r = subprocess.run([str(bash), "-lc", f'bash "$(cygpath -u "{script}")" "{tmp}"'],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            sys.exit("échec de la compilation :\n" + r.stderr[-3000:])
        src = next(tmp.glob("uade-*/"))
        (DEST / "bin").mkdir(parents=True, exist_ok=True)
        (DEST / "data").mkdir(parents=True, exist_ok=True)
        for f in (tmp / "uade2wav.exe", src / "src" / "uadecore.exe", MSYS / "usr" / "bin" / "msys-2.0.dll"):
            shutil.copy(f, DEST / "bin")
        for f in (src / "amigasrc" / "score" / "score", src / "uaerc", src / "eagleplayer.conf", src / "uade.conf"):
            shutil.copy(f, DEST / "data")
        shutil.copytree(src / "players", DEST / "data" / "players", dirs_exist_ok=True)
    print("→", DEST)


if __name__ == "__main__":
    main()
