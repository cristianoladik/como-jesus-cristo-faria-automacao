"""Publicador diário de Instagram, Facebook e YouTube.

Os vídeos ficam temporariamente no repositório público para a Meta conseguir
baixá-los. Depois que todas as plataformas confirmam a publicação, o workflow
remove o arquivo do repositório.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


ROOT = Path(__file__).resolve().parent
FILA_FILE = ROOT / "fila" / "fila.json"
VIDEO_DIR = ROOT / "videos"
BRT = timezone(timedelta(hours=-3))
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v23.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def obrigatoria(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise RuntimeError(f"Segredo obrigatório ausente: {nome}")
    return valor


def salvar_fila(fila: dict) -> None:
    FILA_FILE.write_text(
        json.dumps(fila, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def graph_post(caminho: str, dados: dict, timeout: int = 60) -> dict:
    resposta = requests.post(f"{GRAPH_BASE}/{caminho}", data=dados, timeout=timeout)
    if not resposta.ok:
        raise RuntimeError(f"Meta HTTP {resposta.status_code}: {resposta.text}")
    return resposta.json()


def graph_get(caminho: str, parametros: dict, timeout: int = 30) -> dict:
    resposta = requests.get(
        f"{GRAPH_BASE}/{caminho}", params=parametros, timeout=timeout
    )
    if not resposta.ok:
        raise RuntimeError(f"Meta HTTP {resposta.status_code}: {resposta.text}")
    return resposta.json()


def aguardar_instagram(container_id: str, token: str) -> None:
    for tentativa in range(36):
        status = graph_get(
            container_id,
            {"fields": "status_code,status", "access_token": token},
        )
        codigo = status.get("status_code", "")
        print(f"Instagram [{tentativa + 1}/36]: {codigo}")
        if codigo == "FINISHED":
            return
        if codigo in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Instagram não processou o Reel: {status}")
        time.sleep(10)
    raise TimeoutError("Instagram demorou mais de seis minutos para processar.")


def publicar_instagram(item: dict, video_url: str) -> str:
    token = obrigatoria("IG_ACCESS_TOKEN")
    ig_id = obrigatoria("IG_BUSINESS_ID")
    container = graph_post(
        f"{ig_id}/media",
        {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": item["instagram"]["legenda"],
            "share_to_feed": "true",
            "access_token": token,
        },
    )
    container_id = container.get("id")
    if not container_id:
        raise RuntimeError(f"Container do Instagram sem ID: {container}")
    aguardar_instagram(container_id, token)
    publicado = graph_post(
        f"{ig_id}/media_publish",
        {"creation_id": container_id, "access_token": token},
    )
    if not publicado.get("id"):
        raise RuntimeError(f"Instagram não retornou o post: {publicado}")
    return publicado["id"]


def publicar_facebook(item: dict, caminho_video: Path) -> str:
    """Publica um Reel na Página usando o protocolo de upload da Meta."""
    token = obrigatoria("FB_PAGE_ACCESS_TOKEN")
    page_id = obrigatoria("FB_PAGE_ID")
    inicio = graph_post(
        f"{page_id}/video_reels",
        {"upload_phase": "start", "access_token": token},
    )
    video_id = inicio.get("video_id")
    upload_url = inicio.get("upload_url")
    if not video_id or not upload_url:
        raise RuntimeError(f"Facebook não iniciou o upload: {inicio}")

    tamanho = caminho_video.stat().st_size
    with caminho_video.open("rb") as arquivo:
        resposta = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(tamanho),
            },
            data=arquivo,
            timeout=900,
        )
    if not resposta.ok:
        raise RuntimeError(
            f"Facebook falhou no upload ({resposta.status_code}): {resposta.text}"
        )

    fim = graph_post(
        f"{page_id}/video_reels",
        {
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": item["facebook"]["legenda"],
            "access_token": token,
        },
    )
    if not fim.get("success"):
        raise RuntimeError(f"Facebook não confirmou a publicação: {fim}")
    return str(video_id)


def credenciais_youtube() -> Credentials:
    return Credentials(
        token=None,
        refresh_token=obrigatoria("YOUTUBE_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=obrigatoria("YOUTUBE_CLIENT_ID"),
        client_secret=obrigatoria("YOUTUBE_CLIENT_SECRET"),
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )


def publicar_youtube(item: dict, caminho_video: Path) -> str:
    youtube = build("youtube", "v3", credentials=credenciais_youtube())
    corpo = {
        "snippet": {
            "title": item["youtube"]["titulo"],
            "description": item["youtube"]["descricao"],
            "categoryId": "22",
            "defaultLanguage": "pt",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }
    requisicao = youtube.videos().insert(
        part="snippet,status",
        body=corpo,
        media_body=MediaFileUpload(
            str(caminho_video), mimetype="video/mp4", resumable=True
        ),
        notifySubscribers=True,
    )
    resposta = None
    while resposta is None:
        progresso, resposta = requisicao.next_chunk()
        if progresso:
            print(f"YouTube: {int(progresso.progress() * 100)}%")
    if not resposta.get("id"):
        raise RuntimeError(f"YouTube não retornou o vídeo: {resposta}")
    return resposta["id"]


def executar_plataforma(item: dict, plataforma: str, funcao, *args) -> None:
    dados = item[plataforma]
    if dados.get("status") == "publicado":
        return
    try:
        identificador = funcao(item, *args)
        dados.update(
            {
                "status": "publicado",
                "id": identificador,
                "publicado_em": datetime.now(BRT).isoformat(),
            }
        )
        dados.pop("erro", None)
    except Exception as erro:  # mantém as outras plataformas independentes
        dados["status"] = "erro"
        dados["erro"] = str(erro)
        print(f"ERRO {plataforma}: {erro}")


def main() -> None:
    hoje = date.today().isoformat()
    fila = json.loads(FILA_FILE.read_text(encoding="utf-8"))
    itens = [item for item in fila["conteudos"] if item["data"] == hoje]
    if not itens:
        print(f"Nenhum conteúdo previsto para {hoje}.")
        return

    repo = obrigatoria("GITHUB_REPOSITORY")
    for item in itens:
        caminho = VIDEO_DIR / item["video_file"]
        if not caminho.exists():
            raise FileNotFoundError(caminho)
        video_url = (
            f"https://raw.githubusercontent.com/{repo}/main/videos/"
            f"{quote(item['video_file'])}"
        )
        executar_plataforma(item, "instagram", publicar_instagram, video_url)
        executar_plataforma(item, "facebook", publicar_facebook, caminho)
        executar_plataforma(item, "youtube", publicar_youtube, caminho)
        salvar_fila(fila)

        concluiu = all(
            item[p].get("status") == "publicado"
            for p in ("instagram", "facebook", "youtube")
        )
        if concluiu:
            caminho.unlink(missing_ok=True)
            item["status"] = "concluido"
            salvar_fila(fila)

    if any(
        item[p].get("status") == "erro"
        for item in itens
        for p in ("instagram", "facebook", "youtube")
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

