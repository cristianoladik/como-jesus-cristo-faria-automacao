"""Publicador exclusivo de Reels para Instagram e Facebook.

Não contém integrações nem credenciais de TikTok ou YouTube.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent
FILA_FILE = ROOT / "fila" / "fila-reels.json"
VIDEO_DIR = ROOT / "videos"
BRT = timezone(timedelta(hours=-3))
GRAPH_BASE = f"https://graph.facebook.com/{os.getenv('META_GRAPH_VERSION', 'v23.0')}"
PLATAFORMAS = {"instagram", "facebook"}


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


def publicar_instagram(item: dict, video_url: str) -> str:
    token, ig_id = obrigatoria("IG_ACCESS_TOKEN"), obrigatoria("IG_BUSINESS_ID")
    container = graph_post(f"{ig_id}/media", {
        "media_type": "REELS", "video_url": video_url,
        "caption": item["instagram"]["legenda"], "share_to_feed": "true", "access_token": token,
    })
    container_id = container.get("id")
    if not container_id:
        raise RuntimeError(f"Container do Instagram sem ID: {container}")
    aguardar_instagram(container_id, token)
    publicado = graph_post(f"{ig_id}/media_publish", {"creation_id": container_id, "access_token": token})
    if not publicado.get("id"):
        raise RuntimeError(f"Instagram não retornou o post: {publicado}")
    return publicado["id"]


def publicar_facebook(item: dict, caminho_video: Path) -> str:
    token_sistema, page_id = obrigatoria("FB_PAGE_ACCESS_TOKEN"), obrigatoria("FB_PAGE_ID")
    token = graph_get(page_id, {"fields": "access_token", "access_token": token_sistema}).get("access_token")
    if not token:
        raise RuntimeError("A Meta não retornou o token de acesso da Página.")
    inicio = graph_post(f"{page_id}/video_reels", {"upload_phase": "start", "access_token": token})
    video_id, upload_url = inicio.get("video_id"), inicio.get("upload_url")
    if not video_id or not upload_url:
        raise RuntimeError(f"Facebook não iniciou o upload: {inicio}")
    tamanho = caminho_video.stat().st_size
    with caminho_video.open("rb") as arquivo:
        resposta = requests.post(upload_url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tamanho)}, data=arquivo, timeout=900)
    if not resposta.ok:
        raise RuntimeError(f"Facebook falhou no upload ({resposta.status_code}): {resposta.text}")
    fim = graph_post(f"{page_id}/video_reels", {"upload_phase": "finish", "video_id": video_id, "video_state": "PUBLISHED", "description": item["facebook"]["legenda"], "access_token": token})
    if not fim.get("success"):
        raise RuntimeError(f"Facebook não confirmou a publicação: {fim}")
    return str(video_id)


def executar(item: dict, plataforma: str, funcao, *args) -> None:
    dados = item[plataforma]
    if dados.get("status") == "publicado":
        return
    try:
        dados.update({"status": "publicado", "id": funcao(item, *args), "publicado_em": datetime.now(BRT).isoformat()})
        dados.pop("erro", None)
    except Exception as erro:
        dados.update({"status": "erro", "erro": str(erro)})
        print(f"ERRO {plataforma}: {erro}")


def main() -> None:
    # O runner do GitHub usa UTC. Em 21:00 BRT já é 00:00 UTC do dia seguinte,
    # portanto a data padrão precisa ser calculada no fuso de Brasília.
    hoje = os.getenv("DATA_PUBLICACAO", "").strip() or datetime.now(BRT).date().isoformat()
    horario = os.getenv("HORARIO_PUBLICACAO", "").strip() or datetime.now(BRT).strftime("%H:%M")
    fila = json.loads(FILA_FILE.read_text(encoding="utf-8"))
    itens = [item for item in fila["conteudos"] if item["data"] == hoje and item["horario"] == horario]
    if not itens:
        print(f"Nenhum Reel previsto para {hoje} às {horario}.")
        return
    if len(itens) != 1:
        raise RuntimeError("A fila precisa ter exatamente um Reel por data e horário.")
    item = itens[0]
    caminho = VIDEO_DIR / item["video_file"]
    if not caminho.exists():
        raise FileNotFoundError(caminho)
    repo = obrigatoria("GITHUB_REPOSITORY")
    url = f"https://raw.githubusercontent.com/{repo}/main/videos/{quote(item['video_file'])}"
    executar(item, "instagram", publicar_instagram, url)
    executar(item, "facebook", publicar_facebook, caminho)
    if all(item[p].get("status") == "publicado" for p in PLATAFORMAS):
        item["status"] = "concluido"
        caminho.unlink(missing_ok=True)
    salvar_fila(fila)
    if any(item[p].get("status") == "erro" for p in PLATAFORMAS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
