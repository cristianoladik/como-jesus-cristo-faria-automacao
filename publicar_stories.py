"""Publica um pacote de Stories, em ordem, no Instagram e Facebook."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from publicar import BRT, MAX_TENTATIVAS, PLATAFORMAS, aguardar_instagram, baixar_midia, graph_get, graph_post, obrigatoria

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


def pacotes_devidos(fila: dict) -> list[dict]:
    """Devolve os pacotes já vencidos, do mais antigo para o mais novo.

    Pacotes ``concluido`` e ``pulado`` ficam de fora, para que um vídeo recusado
    pelo Instagram não segure os dias seguintes.
    """
    data_forcada = os.getenv("DATA_PUBLICACAO", "").strip()
    if data_forcada:
        encontrados = [x for x in fila.get("pacotes", []) if x["data"] == data_forcada and x.get("status") != "concluido"]
        if len(encontrados) > 1:
            raise RuntimeError("A fila tem mais de um pacote de Stories para esta data.")
        return encontrados[:1]
    agora = datetime.now(BRT)
    devidos = []
    for pacote in fila.get("pacotes", []):
        if pacote.get("status") in ("concluido", "pulado"):
            continue
        agendado = datetime.fromisoformat(f"{pacote['data']}T{pacote.get('horario', '09:00')}:00").replace(tzinfo=BRT)
        if agendado <= agora:
            devidos.append((agendado, pacote))
    return [pacote for _, pacote in sorted(devidos, key=lambda par: par[0])]


def publicar_pacote(pacote: dict) -> bool:
    """Publica as partes na ordem. Devolve False assim que uma parte falha.

    A ordem das partes é o próprio conteúdo do Story, então uma parte que falha
    interrompe o pacote inteiro. Quem pula é o pacote, nunca uma parte do meio.
    """
    for parte in sorted(pacote["partes"], key=lambda x: x["ordem"]):
        executar(parte, "instagram", publicar_instagram)
        executar(parte, "facebook", publicar_facebook)
        if any(parte[p].get("status") == "erro" for p in PLATAFORMAS):
            return False
    return True


def registrar_falha(pacote: dict) -> None:
    """Conta a tentativa do pacote e o aposenta quando esgota o limite."""
    tentativas = int(pacote.get("tentativas", 0)) + 1
    pacote["tentativas"] = tentativas
    motivos = [
        parte[p].get("erro")
        for parte in pacote["partes"] for p in PLATAFORMAS
        if parte[p].get("status") == "erro"
    ]
    if tentativas >= MAX_TENTATIVAS:
        pacote.update({
            "status": "pulado",
            "pulado_em": datetime.now(BRT).isoformat(),
            "motivo_pulado": f"Falhou {tentativas} vezes seguidas: {motivos[0] if motivos else 'erro desconhecido'}",
        })
        print(f"PULADO em definitivo ({tentativas} tentativas): pacote de {pacote['data']}")
    else:
        print(f"Falhou (tentativa {tentativas} de {MAX_TENTATIVAS}); seguindo para o próximo pacote.")


def main() -> None:
    fila = json.loads(FILA_FILE.read_text(encoding="utf-8"))
    devidos = pacotes_devidos(fila)
    if not devidos:
        print("Nenhum pacote de Stories pendente e devido para publicação.")
        return
    print(f"{len(devidos)} pacote(s) de Stories vencido(s) na fila.")
    publicado = None
    falhados = []
    for pacote in devidos:
        print(f"Tentando pacote de {pacote['data']} ({len(pacote['partes'])} parte(s))")
        if publicar_pacote(pacote):
            pacote.update({"status": "concluido", "concluido_em": datetime.now(BRT).isoformat()})
            pacote.pop("tentativas", None)
            publicado = pacote
            break
        registrar_falha(pacote)
        falhados.append(pacote)
    salvar_fila(fila)
    if publicado:
        print(f"PUBLICADO: pacote de {publicado['data']}")
        if falhados:
            print(f"{len(falhados)} pacote(s) foram pulados antes de chegar nele.")
        return
    print(f"Nenhum dos {len(devidos)} pacote(s) vencido(s) pôde ser publicado nesta execução.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
