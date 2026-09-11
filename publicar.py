"""Publica a próxima peça pendente de Reels no Instagram e Facebook.

As mídias não entram no histórico Git. Cada item aponta para um asset temporário
da release ``fila-instagram-facebook``; o runner o baixa somente para o upload
resumível da Página do Facebook.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
FILA_FILE = ROOT / "fila" / "fila-reels.json"
BRT = timezone(timedelta(hours=-3))
GRAPH_BASE = f"https://graph.facebook.com/{os.getenv('META_GRAPH_VERSION', 'v23.0')}"
PLATAFORMAS = ("instagram", "facebook")
MAX_TENTATIVAS = int(os.getenv("MAX_TENTATIVAS", "3"))


def obrigatoria(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise RuntimeError(f"Segredo obrigatório ausente: {nome}")
    return valor


def salvar_fila(fila: dict) -> None:
    FILA_FILE.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def graph_post(caminho: str, dados: dict, timeout: int = 60) -> dict:
    resposta = requests.post(f"{GRAPH_BASE}/{caminho}", data=dados, timeout=timeout)
    if not resposta.ok:
        raise RuntimeError(f"Meta HTTP {resposta.status_code}: {resposta.text}")
    return resposta.json()


def graph_get(caminho: str, parametros: dict, timeout: int = 30) -> dict:
    resposta = requests.get(f"{GRAPH_BASE}/{caminho}", params=parametros, timeout=timeout)
    if not resposta.ok:
        raise RuntimeError(f"Meta HTTP {resposta.status_code}: {resposta.text}")
    return resposta.json()


def aguardar_instagram(container_id: str, token: str) -> None:
    for tentativa in range(36):
        status = graph_get(container_id, {"fields": "status_code,status", "access_token": token})
        codigo = status.get("status_code", "")
        print(f"Instagram [{tentativa + 1}/36]: {codigo}")
        if codigo == "FINISHED":
            return
        if codigo in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram não processou o Reel: {status}")
        time.sleep(10)
    raise TimeoutError("Instagram demorou mais de seis minutos para processar.")


def baixar_midia(midia: dict) -> Path:
    """Baixa e confere o asset transitório antes do upload ao Facebook."""
    url = midia.get("url_publica", "")
    nome = midia.get("asset", "")
    if not url or not nome:
        raise RuntimeError("A fila não tem URL pública e asset da mídia.")
    destino = Path(os.getenv("MEDIA_CACHE_DIR", ROOT / ".cache")) / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    tamanho = 0
    with requests.get(url, stream=True, timeout=(30, 900)) as resposta:
        if not resposta.ok:
            raise RuntimeError(f"Não foi possível baixar {nome}: HTTP {resposta.status_code}")
        with destino.open("wb") as arquivo:
            for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                if bloco:
                    arquivo.write(bloco)
                    digest.update(bloco)
                    tamanho += len(bloco)
    if midia.get("sha256") and digest.hexdigest().lower() != midia["sha256"].lower():
        destino.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 divergente para {nome}.")
    if midia.get("tamanho_bytes") and tamanho != int(midia["tamanho_bytes"]):
        destino.unlink(missing_ok=True)
        raise RuntimeError(f"Tamanho divergente para {nome}.")
    return destino


def publicar_instagram(item: dict) -> str:
    token, ig_id = obrigatoria("IG_ACCESS_TOKEN"), obrigatoria("IG_BUSINESS_ID")
    midia = item["midia"]
    container = graph_post(f"{ig_id}/media", {
        "media_type": "REELS", "video_url": midia["url_publica"],
        "caption": item["instagram"]["legenda"], "share_to_feed": "true", "access_token": token,
    })
    container_id = container.get("id")
    if not container_id:
        raise RuntimeError(f"Container do Instagram sem ID: {container}")
    aguardar_instagram(container_id, token)
    publicado = graph_post(f"{ig_id}/media_publish", {"creation_id": container_id, "access_token": token})
    if not publicado.get("id"):
        raise RuntimeError(f"Instagram não retornou o post: {publicado}")
    return str(publicado["id"])


def publicar_facebook(item: dict) -> str:
    token_sistema, page_id = obrigatoria("FB_PAGE_ACCESS_TOKEN"), obrigatoria("FB_PAGE_ID")
    token = graph_get(page_id, {"fields": "access_token", "access_token": token_sistema}).get("access_token")
    if not token:
        raise RuntimeError("A Meta não retornou o token de acesso da Página.")
    caminho_video = baixar_midia(item["midia"])
    try:
        inicio = graph_post(f"{page_id}/video_reels", {"upload_phase": "start", "access_token": token})
        video_id, upload_url = inicio.get("video_id"), inicio.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError(f"Facebook não iniciou o upload: {inicio}")
        tamanho = caminho_video.stat().st_size
        with caminho_video.open("rb") as arquivo:
            resposta = requests.post(upload_url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tamanho)}, data=arquivo, timeout=900)
        if not resposta.ok:
            raise RuntimeError(f"Facebook falhou no upload ({resposta.status_code}): {resposta.text}")
        fim = graph_post(f"{page_id}/video_reels", {
            "upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED",
            "description": item["facebook"]["legenda"], "access_token": token,
        })
        if not fim.get("success"):
            raise RuntimeError(f"Facebook não confirmou a publicação: {fim}")
        return str(video_id)
    finally:
        caminho_video.unlink(missing_ok=True)


def executar(item: dict, plataforma: str, funcao) -> None:
    dados = item[plataforma]
    if dados.get("status") == "publicado":
        return
    try:
        dados.update({"status": "publicado", "id": funcao(item), "publicado_em": datetime.now(BRT).isoformat()})
        dados.pop("erro", None)
    except Exception as erro:
        dados.update({"status": "erro", "erro": str(erro), "ultima_tentativa_em": datetime.now(BRT).isoformat()})
        print(f"ERRO {plataforma}: {erro}")


def itens_devidos(fila: dict) -> list[dict]:
    """Devolve os Reels já vencidos, do mais antigo para o mais novo.

    Itens ``concluido`` e ``pulado`` ficam de fora: o primeiro já saiu, o segundo
    esgotou as tentativas e não pode travar a fila de quem vem depois.
    """
    data_forcada = os.getenv("DATA_PUBLICACAO", "").strip()
    horario_forcado = os.getenv("HORARIO_PUBLICACAO", "").strip()
    if bool(data_forcada) != bool(horario_forcado):
        raise RuntimeError("Informe data e horário juntos para executar manualmente.")
    conteudos = fila.get("conteudos", [])
    if data_forcada:
        encontrados = [x for x in conteudos if x["data"] == data_forcada and x["horario"] == horario_forcado and x.get("status") != "concluido"]
        if len(encontrados) > 1:
            raise RuntimeError("A fila tem mais de um Reel para esta data e horário.")
        return encontrados[:1]
    agora = datetime.now(BRT)
    devidos = []
    for item in conteudos:
        if item.get("status") in ("concluido", "pulado"):
            continue
        agendado = datetime.fromisoformat(f"{item['data']}T{item['horario']}:00").replace(tzinfo=BRT)
        if agendado <= agora:
            devidos.append((agendado, item))
    return [item for _, item in sorted(devidos, key=lambda par: par[0])]


def registrar_falha(item: dict) -> None:
    """Conta a tentativa e aposenta o item quando ele esgota o limite."""
    tentativas = int(item.get("tentativas", 0)) + 1
    item["tentativas"] = tentativas
    motivos = [item[p].get("erro") for p in PLATAFORMAS if item[p].get("status") == "erro"]
    if tentativas >= MAX_TENTATIVAS:
        item.update({
            "status": "pulado",
            "pulado_em": datetime.now(BRT).isoformat(),
            "motivo_pulado": f"Falhou {tentativas} vezes seguidas: {motivos[0] if motivos else 'erro desconhecido'}",
        })
        print(f"PULADO em definitivo ({tentativas} tentativas): {item['data']} {item['horario']} — {item.get('titulo', item['id'])}")
    else:
        print(f"Falhou (tentativa {tentativas} de {MAX_TENTATIVAS}); seguindo para o próximo da fila.")


def main() -> None:
    fila = json.loads(FILA_FILE.read_text(encoding="utf-8"))
    devidos = itens_devidos(fila)
    if not devidos:
        print("Nenhum Reel pendente e devido para publicação.")
        return
    print(f"{len(devidos)} Reel(s) vencido(s) na fila.")
    publicado = None
    falhados = []
    for item in devidos:
        print(f"Tentando {item['data']} {item['horario']} — {item.get('titulo', item['id'])}")
        executar(item, "instagram", publicar_instagram)
        executar(item, "facebook", publicar_facebook)
        if all(item[p].get("status") == "publicado" for p in PLATAFORMAS):
            item.update({"status": "concluido", "concluido_em": datetime.now(BRT).isoformat()})
            item.pop("tentativas", None)
            publicado = item
            break
        registrar_falha(item)
        falhados.append(item)
    salvar_fila(fila)
    if publicado:
        print(f"PUBLICADO: {publicado['data']} {publicado['horario']} — {publicado.get('titulo', publicado['id'])}")
        if falhados:
            print(f"{len(falhados)} item(ns) foram pulados antes de chegar nele.")
        return
    print(f"Nenhum dos {len(devidos)} Reel(s) vencido(s) pôde ser publicado nesta execução.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
