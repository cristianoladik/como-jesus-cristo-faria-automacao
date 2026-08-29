"""Executa a fila de edição mantendo entradas e saídas no Google Drive G:."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def resolver(caminho: str, base: Path) -> Path:
    valor = Path(caminho)
    return valor if valor.is_absolute() else (base / valor).resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "config.local.json")
    parser.add_argument("--fila", type=Path)
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    drive_base = Path(config["drive_base"])
    if drive_base.drive.upper() != "G:":
        raise RuntimeError("A pasta de trabalho precisa estar no Google Drive G:.")

    fila_path = args.fila or drive_base / config["metadados"] / "fila-edicao.json"
    fila = json.loads(fila_path.read_text(encoding="utf-8"))
    robo = resolver(config["robo_editor"], config_path.parent)
    avatar = resolver(config["avatar"], config_path.parent)
    finalizados = drive_base / config["finalizados"]
    finalizados.mkdir(parents=True, exist_ok=True)

    for item in fila.get("conteudos", []):
        if item.get("status") == "finalizado":
            continue
        origem = drive_base / config["originais"] / item["arquivo_origem"]
        saida = finalizados / item["arquivo_final"]
        comando = [
            sys.executable,
            str(robo),
            "--video",
            str(origem),
            "--texto",
            item["texto_tela"],
            "--avatar",
            str(avatar),
            "--foco-vertical",
            str(item.get("foco_vertical", 0.30)),
            "--saida",
            str(saida),
        ]
        subprocess.run(comando, check=True)
        item["status"] = "finalizado"
        fila_path.write_text(
            json.dumps(fila, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()

