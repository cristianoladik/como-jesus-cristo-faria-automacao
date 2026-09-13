"""Valida a integridade e a acessibilidade pública das filas IG/FB.

Erro ESTRUTURAL continua derrubando tudo: cabeçalho errado, forma da fila
quebrada, ID ausente ou repetido, data, horário ou status inválido, e falha do
``gh`` ao ler a release. Nesses casos a fila inteira perdeu a confiança, e parar
é o certo.

Defeito DE UM ITEM vira AVISO e a conferência termina com código zero. Antes um
único vídeo ruim lá no fim da fila derrubava o conferidor inteiro e a publicação
do dia nem chegava a ser tentada: em 12/09/2026 cinco vídeos agendados para
novembro deixaram um canal irmão sem publicar de manhã. Quem recusa o item ruim
é o publicar.py, na hora de escolher o vídeo do horário.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any

import requests

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
HORARIOS_REELS = {"09:00", "21:00"}
HORARIO_STORIES = "09:00"
STATUS_ITEM = {"pendente", "concluido", "pulado"}
STATUS_PLATAFORMA = {"pendente", "erro", "publicado"}
PLATAFORMAS = ("instagram", "facebook")
# Limite do canal, conforme o README: cada parte de Story vai até 59 segundos.
DURACAO_MINIMA_PARTE = 3.0
DURACAO_MAXIMA_PARTE = 59.0


def carregar(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def validar_data_iso(valor: Any, contexto: str) -> str:
    texto = str(valor or "")
    try:
        date.fromisoformat(texto)
    except ValueError as erro:
        raise RuntimeError(f"Data inválida em {contexto}: {texto!r}") from erro
    return texto


def validar_origem(origem: dict, contexto: str) -> None:
    if not origem.get("arquivo"):
        raise RuntimeError(f"Arquivo de origem ausente em {contexto}.")
    if not SHA256_RE.fullmatch(str(origem.get("sha256", "")).lower()):
        raise RuntimeError(f"SHA-256 da origem inválido em {contexto}.")


def validar_midia(midia: dict, contexto: str) -> None:
    """Confere só o que está gravado na fila, sem tocar na rede.

    O publicar.py chama esta conferência dentro do runner, na hora de escolher o
    vídeo. Se ela dependesse do ``gh`` ou de um HEAD público, uma instabilidade
    de rede recusaria vídeo bom e calaria o horário à toa.
    """
    asset = str(midia.get("asset", ""))
    if not asset:
        raise RuntimeError(f"Nome de asset ausente em {contexto}.")
    if "/" in asset or "\\" in asset or not asset.lower().endswith(".mp4"):
        raise RuntimeError(f"Nome de asset inseguro em {contexto}.")
    if not str(midia.get("url_publica", "")).startswith("https://github.com/"):
        raise RuntimeError(f"URL pública inválida em {contexto}.")
    if not SHA256_RE.fullmatch(str(midia.get("sha256", "")).lower()):
        raise RuntimeError(f"SHA-256 inválido em {contexto}.")
    if int(midia.get("tamanho_bytes", 0)) <= 0:
        raise RuntimeError(f"Tamanho inválido em {contexto}.")


def validar_plataforma(dados: dict, contexto: str, exigir_legenda: bool) -> None:
    status = str(dados.get("status", ""))
    if status not in STATUS_PLATAFORMA:
        raise RuntimeError(f"Status de plataforma inválido em {contexto}: {status!r}")
    if exigir_legenda and not dados.get("legenda"):
        raise RuntimeError(f"Legenda ausente em {contexto}.")
    if status == "publicado" and not dados.get("id"):
        raise RuntimeError(f"Publicação sem ID em {contexto}.")
    if status == "erro" and not dados.get("erro"):
        raise RuntimeError(f"Estado de erro sem mensagem em {contexto}.")


def defeito_do_reel(item: dict, identificador: str) -> str | None:
    """Devolve o problema que afeta SÓ este Reel, ou None se ele está bom."""
    try:
        validar_origem(item.get("origem", {}), identificador)
        validar_midia(item.get("midia", {}), identificador)
        for plataforma in PLATAFORMAS:
            validar_plataforma(
                item.get(plataforma, {}),
                f"{identificador}/{plataforma}",
                exigir_legenda=True,
            )
        if item.get("status") == "concluido" and not all(
            item.get(p, {}).get("status") == "publicado" for p in PLATAFORMAS
        ):
            raise RuntimeError(f"Reel concluído sem as duas confirmações: {identificador}")
    except RuntimeError as erro:
        return str(erro)
    except (AttributeError, TypeError, ValueError) as erro:
        # Item fora de forma (campo com o tipo errado) é defeito dele, não motivo
        # para derrubar a fila inteira.
        return f"Item malformado em {identificador}: {erro}"
    return None


def defeito_do_story(pacote: dict, identificador: str) -> str | None:
    """Devolve o problema que afeta SÓ este pacote de Story, ou None."""
    try:
        validar_origem(pacote.get("origem", {}), identificador)
        partes = pacote.get("partes") or []
        if not partes:
            raise RuntimeError(f"Pacote de Story sem partes: {identificador}")
        ordens = [int(parte.get("ordem", 0)) for parte in partes]
        if ordens != list(range(1, len(partes) + 1)):
            raise RuntimeError(f"Ordem descontínua no pacote {identificador}.")
        for parte in partes:
            contexto = f"{identificador}/parte-{parte.get('ordem')}"
            midia = parte.get("midia", {})
            validar_midia(midia, contexto)
            segundos = float(midia.get("duracao_segundos", 0))
            if segundos < DURACAO_MINIMA_PARTE or segundos > DURACAO_MAXIMA_PARTE:
                raise RuntimeError(
                    f"Parte de Story fora do intervalo de {DURACAO_MINIMA_PARTE:g} a "
                    f"{DURACAO_MAXIMA_PARTE:g} segundos: {contexto}"
                )
            for plataforma in PLATAFORMAS:
                validar_plataforma(
                    parte.get(plataforma, {}),
                    f"{contexto}/{plataforma}",
                    exigir_legenda=False,
                )
        if pacote.get("status") == "concluido" and not all(
            parte.get(p, {}).get("status") == "publicado"
            for parte in partes
            for p in PLATAFORMAS
        ):
            raise RuntimeError(f"Story concluído sem todas as confirmações: {identificador}")
    except RuntimeError as erro:
        return str(erro)
    except (AttributeError, TypeError, ValueError) as erro:
        return f"Pacote malformado em {identificador}: {erro}"
    return None


def validar_reels(fila: dict) -> dict[str, str]:
    """Confere a fila de Reels: estrutura levanta erro, defeito de item volta na lista."""
    if fila.get("canal") != "instagram-facebook-reels":
        raise RuntimeError("Cabeçalho da fila de Reels inválido.")
    conteudos = fila.get("conteudos")
    if not isinstance(conteudos, list):
        raise RuntimeError("A fila de Reels não tem a lista de conteúdos.")
    ids: set[str] = set()
    janelas: set[tuple[str, str]] = set()
    defeitos: dict[str, str] = {}
    for item in conteudos:
        identificador = str(item.get("id", ""))
        janela = (validar_data_iso(item.get("data"), identificador), str(item.get("horario", "")))
        if not identificador or identificador in ids:
            raise RuntimeError(f"ID de Reel ausente ou repetido: {identificador!r}")
        if janela in janelas or janela[1] not in HORARIOS_REELS:
            raise RuntimeError(f"Janela de Reel inválida ou repetida: {janela}")
        ids.add(identificador)
        janelas.add(janela)
        if item.get("status") not in STATUS_ITEM:
            raise RuntimeError(f"Status de Reel inválido em {identificador}.")
        defeito = defeito_do_reel(item, identificador)
        if defeito:
            defeitos[identificador] = defeito
    return defeitos


def validar_stories(fila: dict) -> dict[str, str]:
    """Confere a fila de Stories na mesma divisão: estrutura x defeito de item."""
    if fila.get("canal") != "instagram-facebook-stories":
        raise RuntimeError("Cabeçalho da fila de Stories inválido.")
    pacotes = fila.get("pacotes")
    if not isinstance(pacotes, list):
        raise RuntimeError("A fila de Stories não tem a lista de pacotes.")
    ids: set[str] = set()
    datas: set[str] = set()
    defeitos: dict[str, str] = {}
    for pacote in pacotes:
        identificador = str(pacote.get("id", ""))
        data = validar_data_iso(pacote.get("data"), identificador)
        if not identificador or identificador in ids:
            raise RuntimeError(f"ID de Story ausente ou repetido: {identificador!r}")
        if data in datas or str(pacote.get("horario", HORARIO_STORIES)) != HORARIO_STORIES:
            raise RuntimeError(f"Data/horário de Story inválido ou repetido: {data}")
        ids.add(identificador)
        datas.add(data)
        if pacote.get("status") not in STATUS_ITEM:
            raise RuntimeError(f"Status de Story inválido em {identificador}.")
        if not isinstance(pacote.get("partes"), list):
            raise RuntimeError(f"Pacote de Story sem a lista de partes: {identificador}")
        defeito = defeito_do_story(pacote, identificador)
        if defeito:
            defeitos[identificador] = defeito
    return defeitos


def midias(reels: dict, stories: dict) -> list[tuple[str, dict]]:
    """Devolve os pares (identificador do item, mídia) que ainda precisam do asset.

    O identificador vem junto para o aviso poder dizer QUAL item está com
    defeito, e não só o nome do arquivo. Item ``pulado`` fica de fora junto com o
    ``concluido``: nenhum dos dois vai ao ar e o limpar_release.py já apagou a
    mídia deles, então cobrar o asset daria aviso eterno.
    """
    resultado = [
        (str(item.get("id", "")), item.get("midia") or {})
        for item in reels.get("conteudos", [])
        if item.get("status") not in ("concluido", "pulado")
    ]
    for pacote in stories.get("pacotes", []):
        if pacote.get("status") in ("concluido", "pulado"):
            continue
        for parte in pacote.get("partes", []):
            contexto = f"{pacote.get('id', '')}/parte-{parte.get('ordem')}"
            resultado.append((contexto, parte.get("midia") or {}))
    return resultado


def assets_da_release(repositorio: str, tag: str) -> dict[str, dict]:
    """Lista os assets da release. Falhar aqui é global, então continua fatal.

    Sem o ``gh`` nenhuma mídia pode ser conferida: não é defeito de um item, é a
    conferência inteira que não aconteceu.
    """
    try:
        resultado = subprocess.run(
            ("gh", "release", "view", tag, "--repo", repositorio, "--json", "assets"),
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as erro:
        detalhe = getattr(erro, "stderr", "") or erro
        raise SystemExit(f"Não foi possível ler a release {tag} de {repositorio}: {detalhe}") from erro
    return {asset["name"]: asset for asset in json.loads(resultado.stdout).get("assets", [])}


def validar_http(par: tuple[str, dict]) -> tuple[str, str] | None:
    identificador, midia = par
    asset = midia.get("asset", "sem asset")
    url = str(midia.get("url_publica", ""))
    if not url:
        return identificador, f"URL pública ausente: {asset}"
    try:
        resposta = requests.head(url, allow_redirects=True, timeout=(10, 20))
        tamanho = resposta.headers.get("Content-Length")
        if resposta.status_code != 200:
            return identificador, f"HTTP {resposta.status_code}: {asset}"
        if tamanho and int(tamanho) != int(midia.get("tamanho_bytes", 0)):
            return identificador, f"Tamanho HTTP divergente: {asset}"
    except Exception as erro:
        return identificador, f"Falha HTTP {asset}: {erro}"
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
    defeitos = validar_reels(reels)
    defeitos.update(validar_stories(stories))
    todas = midias(reels, stories)
    assets = assets_da_release(args.repo_github, args.release)
    for identificador, midia in todas:
        nome = str(midia.get("asset", ""))
        asset = assets.get(nome)
        if not asset:
            defeitos.setdefault(identificador, f"Asset ausente: {nome}")
            continue
        digest = str(asset.get("digest", "")).removeprefix("sha256:").lower()
        if digest != str(midia.get("sha256", "")).lower() or int(asset.get("size", -1)) != int(midia.get("tamanho_bytes", 0)):
            defeitos.setdefault(identificador, f"Asset divergente: {nome}")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for resultado in executor.map(validar_http, todas):
            if resultado:
                defeitos.setdefault(resultado[0], resultado[1])
    relatorio = {
        "reels": len(reels.get("conteudos", [])),
        "stories": len(stories.get("pacotes", [])),
        "assets": len(todas),
        "avisos": [{"item": item, "motivo": motivo} for item, motivo in sorted(defeitos.items())],
    }
    if args.relatorio:
        args.relatorio.parent.mkdir(parents=True, exist_ok=True)
        args.relatorio.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {relatorio['reels']} Reels, {relatorio['stories']} Stories e {relatorio['assets']} assets conferidos.")
    # Defeito de item é AVISO, não parada: quem recusa o vídeo ruim é o
    # publicar.py, e só o horário daquele item fica sem publicar.
    if defeitos:
        print(f"AVISO: {len(defeitos)} item(ns) com defeito; serão pulados na publicação:")
        for identificador, motivo in sorted(defeitos.items()):
            print(f"  - {identificador}: {motivo}")


if __name__ == "__main__":
    main()
