"""Publica um pacote de Stories, em ordem, no Instagram e Facebook."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from publicar import BRT, PLATAFORMAS, aguardar_instagram, baixar_midia, graph_get, graph_post, obrigatoria

ROOT = Path(__file__).resolve().parent
FILA_FILE = ROOT / "fila" / "fila-stories.json"


def salvar_fila(fila: dict) -> None:
    FILA_FILE.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def publicar_instagram(parte: dict) -> str:
    token, ig_id = obrigatoria("IG_ACCESS_TOKEN"), obrigatoria("IG_BUSINESS_ID")
    container = graph_post(f"{ig_id}/media", {
        "media_type": "STORIES", "video_url": parte["midia"]["url_publica"], "access_token": token,
    })
    container_id = container.get("id")
    if not container_id:
        raise RuntimeError(f"Container do Story Instagram sem ID: {container}")
    aguardar_instagram(container_id, token)
    publicado = graph_post(f"{ig_id}/media_publish", {"creation_id": container_id, "access_token": token})
    if not publicado.get("id"):
        raise RuntimeError(f"Instagram não retornou o Story: {publicado}")
    return str(publicado["id"])


def publicar_facebook(parte: dict) -> str:
    token_sistema, page_id = obrigatoria("FB_PAGE_ACCESS_TOKEN"), obrigatoria("FB_PAGE_ID")
    token = graph_get(page_id, {"fields": "access_token", "access_token": token_sistema}).get("access_token")
    if not token:
        raise RuntimeError("A Meta não retornou o token de acesso da Página.")
    caminho_video = baixar_midia(parte["midia"])
    try:
        inicio = graph_post(f"{page_id}/video_stories", {"upload_phase": "start", "access_token": token})
        video_id, upload_url = inicio.get("video_id"), inicio.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError(f"Facebook não iniciou o upload do Story: {inicio}")
        tamanho = caminho_video.stat().st_size
        with caminho_video.open("rb") as arquivo:
            resposta = requests.post(upload_url, headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(tamanho)}, data=arquivo, timeout=900)
        if not resposta.ok:
            raise RuntimeError(f"Facebook falhou no upload do Story ({resposta.status_code}): {resposta.text}")
        fim = graph_post(f"{page_id}/video_stories", {"upload_phase": "finish", "video_id": video_id, "access_token": token})
        if not fim.get("success") or not fim.get("post_id"):
            raise RuntimeError(f"Facebook não confirmou o Story: {fim}")
        return str(fim["post_id"])
    finally:
        caminho_video.unlink(missing_ok=True)


def executar(parte: dict, plataforma: str, funcao) -> None:
    dados = parte[plataforma]
    if dados.get("status") == "publicado":
        return
    try:
        dados.update({"status": "publicado", "id": funcao(parte), "publicado_em": datetime.now(BRT).isoformat()})
        dados.pop("erro", None)
    except Exception as erro:
        dados.update({"status": "erro", "erro": str(erro), "ultima_tentativa_em": datetime.now(BRT).isoformat()})
        print(f"ERRO {plataforma}, parte {parte['ordem']}: {erro}")


def proximo_pacote(fila: dict) -> dict | None:
    data_forcada = os.getenv("DATA_PUBLICACAO", "").strip()
    if data_forcada:
        encontrados = [x for x in fila.get("pacotes", []) if x["data"] == data_forcada and x.get("status") != "concluido"]
        if len(encontrados) > 1:
            raise RuntimeError("A fila tem mais de um pacote de Stories para esta data.")
        return encontrados[0] if encontrados else None
    agora = datetime.now(BRT)
    devidos = []
    for pacote in fila.get("pacotes", []):
        if pacote.get("status") == "concluido":
            continue
        agendado = datetime.fromisoformat(f"{pacote['data']}T{pacote.get('horario', '09:00')}:00").replace(tzinfo=BRT)
        if agendado <= agora:
            devidos.append((agendado, pacote))
    return min(devidos, key=lambda par: par[0])[1] if devidos else None


def main() -> None:
    fila = json.loads(FILA_FILE.read_text(encoding="utf-8"))
    pacote = proximo_pacote(fila)
    if not pacote:
        print("Nenhum pacote de Stories pendente e devido para publicação.")
        return
    for parte in sorted(pacote["partes"], key=lambda x: x["ordem"]):
        executar(parte, "instagram", publicar_instagram)
        executar(parte, "facebook", publicar_facebook)
        if any(parte[p].get("status") == "erro" for p in PLATAFORMAS):
            salvar_fila(fila)
            raise SystemExit(1)
    pacote.update({"status": "concluido", "concluido_em": datetime.now(BRT).isoformat()})
    salvar_fila(fila)


if __name__ == "__main__":
    main()
