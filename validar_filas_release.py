"""Valida a integridade e a acessibilidade pública das filas IG/FB."""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests


def carregar(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def midias(reels: dict, stories: dict) -> list[dict]:
    resultado = [item["midia"] for item in reels.get("conteudos", []) if item.get("status") != "concluido"]
    for pacote in stories.get("pacotes", []):
        if pacote.get("status") != "concluido":
            resultado.extend(parte["midia"] for parte in pacote["partes"])
    return resultado


def assets_da_release(repositorio: str, tag: str) -> dict[str, dict]:
    resultado = subprocess.run(
        ("gh", "release", "view", tag, "--repo", repositorio, "--json", "assets"),
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=True,
    )
    return {asset["name"]: asset for asset in json.loads(resultado.stdout).get("assets", [])}


def validar_http(midia: dict) -> str | None:
    try:
        resposta = requests.head(midia["url_publica"], allow_redirects=True, timeout=(10, 20))
        tamanho = resposta.headers.get("Content-Length")
        if resposta.status_code != 200:
            return f"HTTP {resposta.status_code}: {midia['asset']}"
        if tamanho and int(tamanho) != int(midia["tamanho_bytes"]):
            return f"Tamanho HTTP divergente: {midia['asset']}"
    except Exception as erro:
        return f"Falha HTTP {midia['asset']}: {erro}"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repositorio", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--repo-github", default="cristianoladik/como-jesus-cristo-faria-automacao")
    parser.add_argument("--release", default="fila-instagram-facebook")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--relatorio", type=Path)
    args = parser.parse_args()

    raiz = args.repositorio.resolve()
    reels = carregar(raiz / "fila" / "fila-reels.json")
    stories = carregar(raiz / "fila" / "fila-stories.json")
    todas = midias(reels, stories)
    assets = assets_da_release(args.repo_github, args.release)
    erros: list[str] = []
    for midia in todas:
        asset = assets.get(midia["asset"])
        if not asset:
            erros.append(f"Asset ausente: {midia['asset']}")
            continue
        digest = str(asset.get("digest", "")).removeprefix("sha256:").lower()
        if digest != midia["sha256"].lower() or int(asset.get("size", -1)) != int(midia["tamanho_bytes"]):
            erros.append(f"Asset divergente: {midia['asset']}")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        erros.extend(erro for erro in executor.map(validar_http, todas) if erro)
    relatorio = {
        "reels": len(reels.get("conteudos", [])),
        "stories": len(stories.get("pacotes", [])),
        "assets": len(todas),
        "erros": erros,
    }
    if args.relatorio:
        args.relatorio.parent.mkdir(parents=True, exist_ok=True)
        args.relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if erros:
        raise SystemExit("\n".join(erros))
    print(f"OK: {len(reels.get('conteudos', []))} Reels, {len(stories.get('pacotes', []))} Stories e {len(todas)} assets acessíveis.")


if __name__ == "__main__":
    main()
