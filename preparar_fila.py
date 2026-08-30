"""Monta a fila de publicação a partir dos vídeos finalizados no Drive G:."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path


LEGENDA_IG = "Siga @como_jesuscristo_faria."
LEGENDA_TIKTOK = "Siga @como_jesuscristo_faria."
DESCRICAO_YT = (
    "Inscreva-se no canal Como Jesus Cristo faria? e acompanhe uma nova "
    "reflexão todos os dias."
)


def titulo_do_arquivo(nome: str) -> str:
    return re.sub(r"^\d+\s*-\s*", "", Path(nome).stem).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pasta", required=True, type=Path)
    parser.add_argument("--inicio", required=True, type=date.fromisoformat)
    parser.add_argument("--saida", required=True, type=Path)
    args = parser.parse_args()

    if args.pasta.resolve().drive.upper() != "G:":
        raise RuntimeError("Os vídeos finalizados precisam estar no Drive G:.")
    videos = sorted(args.pasta.glob("*.mp4"))
    conteudos = []
    for indice, video in enumerate(videos):
        titulo = titulo_do_arquivo(video.name)
        conteudos.append(
            {
                "data": (args.inicio + timedelta(days=indice)).isoformat(),
                "video_file": video.name,
                "titulo": titulo,
                "status": "pendente",
                "instagram": {"legenda": LEGENDA_IG, "status": "pendente"},
                "facebook": {"legenda": LEGENDA_IG, "status": "pendente"},
                "tiktok": {
                    "legenda": LEGENDA_TIKTOK,
                    "privacidade": "PUBLIC_TO_EVERYONE",
                    "status": "pendente",
                },
                "youtube": {
                    "titulo": titulo,
                    "descricao": DESCRICAO_YT,
                    "status": "pendente",
                },
            }
        )
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps({"conteudos": conteudos}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

