"""Met dans la fiche d'une musique les sons choisis à l'écoute des extraits (scripts/extraits.py).

    .venv\\Scripts\\python scripts\\appliquer_choix.py "in\\music\\Dr Mario\\Dr Mario.mod" Batterie=7 "Guitare rythmique=7" Lead=7 Chœur=1

Chaque « partie=n° » prend le candidat n° n de songs\\extraits\\<musique>.json et remplace dans songs\\<musique>.json
les réglages des samples de la partie (et ceux du charleston / des crashs ajoutés pour une batterie). Le n° 0 (son
actuel) ne change rien. Chaque sample garde une trace du choix dans « comment ». Relancer ensuite le remaster.
"""
from __future__ import annotations
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from remaster import render  # noqa: E402
from remaster.__main__ import open_music  # noqa: E402
from extraits import candidate_cfg  # noqa: E402


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    music = pathlib.Path(sys.argv[1])
    m = open_music(music)
    plan = json.loads((ROOT / "songs" / "extraits" / f"{m.name}.json").read_text(encoding="utf-8"))
    parts = {p["titre"]: p for p in plan["parties"]}
    cfg = render.load_config(m.cfg_path)
    today = datetime.date.today().strftime("%d/%m/%Y")
    for arg in sys.argv[2:]:
        title, _, num = arg.rpartition("=")
        if title not in parts:
            raise SystemExit(f"partie inconnue : {title} (parties : {', '.join(parts)})")
        part, k = parts[title], int(num)
        cand = part["candidats"][k]
        if k == 0:
            print(f"{title} : son actuel gardé")
            continue
        cfg = candidate_cfg(cfg, [str(s) for s in part["samples"]], cand, m.name, f"choix-{k}")
        for s in part["samples"]:
            cfg["samples"][str(s)]["comment"] = f"choisi à l'écoute le {today} : {title} n° {k}, {cand['nom']}"
        print(f"{title} : n° {k}, {cand['nom']}")
    m.cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"→ {m.cfg_path}")


if __name__ == "__main__":
    main()
