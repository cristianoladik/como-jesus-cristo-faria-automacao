"""Reconcilia filas IG/FB com os nomes reais dos assets da release.

Também pode retirar uma origem que já tenha sido publicada e deslocar os itens
restantes para preservar a sequência de horários. Não envia nem apaga mídia.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


def carregar(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def salvar(caminho: Path, dados: dict) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def assets_da_release(repositorio: str, tag: str) -> list[dict]:
    resultado = subprocess.run(
        ("gh", "release", "view", tag, "--repo", repositorio, "--json", "assets"),
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    return json.loads(resultado.stdout).get("assets", [])


def url_asset(repositorio: str, tag: str, asset: str) -> str:
    return f"https://github.com/{repositorio}/releases/download/{tag}/{quote(asset, safe='')}"


def chave_midia(midia: dict) -> tuple[str, int]:
    return midia["sha256"].lower(), int(midia["tamanho_bytes"])


def reconciliar_midia(midia: dict, indice: dict[tuple[str, int], list[dict]], repositorio: str, tag: str) -> None:
    candidatos = indice.get(chave_midia(midia), [])
    if len(candidatos) != 1:
        raise RuntimeError(f"Não há um único asset compatível para {midia['asset']}: {len(candidatos)} encontrados.")
    asset = candidatos[0]["name"]
    midia["asset"] = asset
    midia["url_publica"] = url_asset(repositorio, tag, asset)


def momento_reel(item: dict) -> datetime:
    return datetime.fromisoformat(f"{item['data']}T{item['horario']}:00")


def momento_story(item: dict) -> datetime:
    return datetime.fromisoformat(f"{item['data']}T{item.get('horario', '09:00')}:00")


def reagendar_reels(itens: list[dict], horarios: list[datetime]) -> None:
    for item, agendado in zip(sorted(itens, key=momento_reel), horarios):
        digest = item["origem"]["sha256"]
        item["id"] = f"reel-{agendado:%Y%m%d-%H%M}-{digest[:10]}"
        item["data"] = agendado.date().isoformat()
        item["horario"] = agendado.strftime("%H:%M")


def reagendar_stories(itens: list[dict], horarios: list[datetime]) -> None:
    for item, agendado in zip(sorted(itens, key=momento_story), horarios):
        digest = item["origem"]["sha256"]
        item["id"] = f"story-{agendado:%Y%m%d}-{digest[:10]}"
        item["data"] = agendado.date().isoformat()
        item["horario"] = agendado.strftime("%H:%M")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repositorio", type=Path, required=True)
    parser.add_argument("--repo-github", default="cristianoladik/como-jesus-cristo-faria-automacao")
    parser.add_argument("--release", default="fila-instagram-facebook")
    parser.add_argument("--excluir-sha", required=True)
    args = parser.parse_args()

    raiz = args.repositorio.resolve()
    caminho_reels = raiz / "fila" / "fila-reels.json"
    caminho_stories = raiz / "fila" / "fila-stories.json"
    reels, stories = carregar(caminho_reels), carregar(caminho_stories)
    excluir = args.excluir_sha.lower()

    indice: dict[tuple[str, int], list[dict]] = {}
    for asset in assets_da_release(args.repo_github, args.release):
        digest = str(asset.get("digest", "")).removeprefix("sha256:").lower()
        if digest:
            indice.setdefault((digest, int(asset["size"])), []).append(asset)

    horarios_reels = sorted(momento_reel(item) for item in reels.get("conteudos", []))
    horarios_stories = sorted(momento_story(item) for item in stories.get("pacotes", []))
    antes_reels, antes_stories = len(reels["conteudos"]), len(stories["pacotes"])
    reels["conteudos"] = [item for item in reels["conteudos"] if item.get("origem", {}).get("sha256", "").lower() != excluir]
    stories["pacotes"] = [item for item in stories["pacotes"] if item.get("origem", {}).get("sha256", "").lower() != excluir]
    if len(reels["conteudos"]) != antes_reels - 1 or len(stories["pacotes"]) != antes_stories - 1:
        raise RuntimeError("A origem histórica esperada não foi encontrada exatamente uma vez em cada fila.")

    for item in reels["conteudos"]:
        reconciliar_midia(item["midia"], indice, args.repo_github, args.release)
    for pacote in stories["pacotes"]:
        for parte in pacote["partes"]:
            reconciliar_midia(parte["midia"], indice, args.repo_github, args.release)

    reagendar_reels(reels["conteudos"], horarios_reels[:len(reels["conteudos"])])
    reagendar_stories(stories["pacotes"], horarios_stories[:len(stories["pacotes"])])
    salvar(caminho_reels, reels)
    salvar(caminho_stories, stories)
    print(f"Filas reconciliadas: {len(reels['conteudos'])} Reels e {len(stories['pacotes'])} pacotes de Stories.")


if __name__ == "__main__":
    main()
