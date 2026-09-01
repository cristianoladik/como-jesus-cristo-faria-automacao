"""Gera a fila exclusiva de Reels para Instagram e Facebook."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

LEGENDA = "Siga @como_jesuscristo_faria."
HORARIOS = ("09:00", "21:00")


def titulo(nome: str) -> str:
    return re.sub(r"^\d+\s*-\s*", "", Path(nome).stem).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta", required=True, type=Path)
    parser.add_argument("--inicio", required=True, type=date.fromisoformat)
    parser.add_argument("--saida", required=True, type=Path)
    args = parser.parse_args()
    if args.pasta.resolve().drive.upper() != "G:":
        raise RuntimeError("A fila deve ser montada a partir do Drive G:.")
    conteudos = []
    for indice, video in enumerate(sorted(args.pasta.glob("*.mp4"))):
        dia, horario = divmod(indice, len(HORARIOS))
        conteudos.append({
            "data": (args.inicio + timedelta(days=dia)).isoformat(),
            "horario": HORARIOS[horario], "video_file": video.name,
            "titulo": titulo(video.name), "status": "pendente",
            "instagram": {"legenda": LEGENDA, "status": "pendente"},
            "facebook": {"legenda": LEGENDA, "status": "pendente"},
        })
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps({"canal": "instagram-facebook-reels", "timezone": "America/Sao_Paulo", "conteudos": conteudos}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
