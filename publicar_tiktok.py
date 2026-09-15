"""Publica o próximo vídeo pendente da fila do TikTok pela Content Posting API.

Roda no GitHub Actions (PC desligado). Cada item da fila aponta para um asset
temporário da release ``fila-tiktok``; o runner baixa, confere o SHA-256 e sobe
em pedaços direto para o TikTok (FILE_UPLOAD, sem depender de domínio).

Segredos: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN.
Variável TIKTOK_ATIVO (repo variable): enquanto for diferente de "SIM" o robô
só avisa e sai, porque app sem auditoria só publica em conta privada.
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
FILA_FILE = ROOT / "fila" / "fila-tiktok.json"
BRT = timezone(timedelta(hours=-3))
API = "https://open.tiktokapis.com/v2"
MAX_TENTATIVAS = int(os.getenv("MAX_TENTATIVAS", "3"))
PEDACO = 10 * 1024 * 1024
PRIVACIDADE = os.getenv("TIKTOK_PRIVACIDADE", "PUBLIC_TO_EVERYONE").strip() or "PUBLIC_TO_EVERYONE"


def obrigatoria(nome: str) -> str:
    valor = os.getenv(nome, "").strip()
    if not valor:
        raise RuntimeError(f"Segredo obrigatório ausente: {nome}")
    return valor


def salvar_fila(fila: dict) -> None:
    FILA_FILE.write_text(json.dumps(fila, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ── TikTok ─────────────────────────────────────────────────────────────────
def token_de_acesso() -> str:
    r = requests.post(
        f"{API}/oauth/token/",
        data={
            "client_key": obrigatoria("TIKTOK_CLIENT_KEY"),
            "client_secret": obrigatoria("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": obrigatoria("TIKTOK_REFRESH_TOKEN"),
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    dados = r.json()
    if "access_token" not in dados:
        raise RuntimeError(f"Renovação do token falhou: {dados}")
    if dados.get("refresh_token") and dados["refresh_token"] != os.getenv("TIKTOK_REFRESH_TOKEN", "").strip():
        print("AVISO: o TikTok devolveu um refresh_token NOVO; atualize o segredo TIKTOK_REFRESH_TOKEN.")
    return dados["access_token"]


def checar(r: requests.Response, contexto: str) -> dict:
    dados = r.json()
    erro = dados.get("error") or {}
    if erro.get("code") not in (None, "ok"):
        raise RuntimeError(f"{contexto}: {erro.get('code')} - {erro.get('message')} (log_id {erro.get('log_id')})")
    return dados


def baixar_midia(midia: dict) -> Path:
    url, nome = midia.get("url_publica", ""), midia.get("asset", "")
    if not url or not nome:
        raise RuntimeError("A fila não tem URL pública e asset da mídia.")
    destino = Path(os.getenv("MEDIA_CACHE_DIR", ROOT / ".cache")) / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with requests.get(url, stream=True, timeout=300) as resposta:
        if resposta.status_code != 200:
            raise RuntimeError(f"Não foi possível baixar {nome}: HTTP {resposta.status_code}")
        with destino.open("wb") as f:
            for bloco in resposta.iter_content(1024 * 1024):
                f.write(bloco); digest.update(bloco)
    if midia.get("sha256") and digest.hexdigest() != midia["sha256"]:
        raise RuntimeError(f"SHA-256 diferente do esperado em {nome}.")
    return destino


def publicar_tiktok(item: dict, token: str) -> str:
    arquivo = baixar_midia(item["midia"])
    tamanho = arquivo.stat().st_size
    pedaco = min(PEDACO, tamanho)
    total = max(1, tamanho // pedaco)
    cabecalho = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    corpo = {
        "post_info": {
            "title": item["tiktok"]["legenda"][:2200],
            "privacy_level": PRIVACIDADE,
            "disable_duet": False, "disable_comment": False, "disable_stitch": False,
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {"source": "FILE_UPLOAD", "video_size": tamanho, "chunk_size": pedaco, "total_chunk_count": total},
    }
    dados = checar(requests.post(f"{API}/post/publish/video/init/", headers=cabecalho, json=corpo, timeout=60), "publish/init")["data"]
    publish_id, upload_url = dados["publish_id"], dados["upload_url"]
    with arquivo.open("rb") as f:
        inicio = 0
        for i in range(total):
            fim = tamanho - 1 if i == total - 1 else inicio + pedaco - 1
            bloco = f.read(fim - inicio + 1)
            r = requests.put(upload_url, data=bloco, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(bloco)),
                "Content-Range": f"bytes {inicio}-{fim}/{tamanho}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"Upload do pedaço {i + 1}/{total} falhou: HTTP {r.status_code} {r.text[:200]}")
            print(f"  pedaço {i + 1}/{total} ok")
            inicio = fim + 1
    for tentativa in range(60):
        st = checar(requests.post(f"{API}/post/publish/status/fetch/", headers=cabecalho, json={"publish_id": publish_id}, timeout=30), "status/fetch")["data"]
        print(f"TikTok [{tentativa + 1}/60]: {st.get('status')}")
        if st.get("status") == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or st.get("publicly_available_post_id") or []
            return str(ids[0]) if ids else publish_id
        if st.get("status") == "FAILED":
            raise RuntimeError(f"TikTok não publicou: {st.get('fail_reason')}")
        time.sleep(10)
    raise TimeoutError("TikTok demorou mais de dez minutos para processar.")


# ── Fila ───────────────────────────────────────────────────────────────────
def itens_devidos(fila: dict) -> list[dict]:
    data_forcada = os.getenv("DATA_PUBLICACAO", "").strip()
    horario_forcado = os.getenv("HORARIO_PUBLICACAO", "").strip()
    if bool(data_forcada) != bool(horario_forcado):
        raise RuntimeError("Informe data e horário juntos para executar manualmente.")
    conteudos = fila.get("conteudos", [])
    if data_forcada:
        achados = [x for x in conteudos if x["data"] == data_forcada and x["horario"] == horario_forcado and x.get("status") != "concluido"]
        if len(achados) > 1:
            raise RuntimeError("A fila tem mais de um vídeo para esta data e horário.")
        return achados[:1]
    agora = datetime.now(BRT)
    devidos = []
    for item in conteudos:
        if item.get("status") in ("concluido", "pulado"):
            continue
        if not item.get("midia", {}).get("url_publica"):
            print(f"Item sem mídia, ignorado: {item.get('id')}")
            continue
        agendado = datetime.fromisoformat(f"{item['data']}T{item['horario']}:00").replace(tzinfo=BRT)
        if agendado <= agora:
            devidos.append((agendado, item))
    return [item for _, item in sorted(devidos, key=lambda par: par[0])]


def registrar_falha(item: dict, erro: str) -> None:
    tentativas = int(item.get("tentativas", 0)) + 1
    item["tentativas"] = tentativas
    item["tiktok"].update({"status": "erro", "erro": erro, "ultima_tentativa_em": datetime.now(BRT).isoformat()})
    if tentativas >= MAX_TENTATIVAS:
        item.update({"status": "pulado", "pulado_em": datetime.now(BRT).isoformat(),
                     "motivo_pulado": f"Falhou {tentativas} vezes seguidas: {erro}"})
        print(f"PULADO em definitivo ({tentativas} tentativas): {item['data']} {item['horario']} — {item['id']}")
    else:
        print(f"Falhou (tentativa {tentativas} de {MAX_TENTATIVAS}); seguindo para o próximo da fila.")


def main() -> None:
    if os.getenv("TIKTOK_ATIVO", "").strip().upper() != "SIM":
        print("TIKTOK_ATIVO não é SIM: o app ainda não foi aprovado pelo TikTok. Nada publicado.")
        return
    fila = json.loads(FILA_FILE.read_text(encoding="utf-8"))
    devidos = itens_devidos(fila)
    if not devidos:
        print("Nenhum vídeo pendente e devido para o TikTok.")
        return
    print(f"{len(devidos)} vídeo(s) vencido(s) na fila do TikTok.")
    token = token_de_acesso()
    publicado = None
    for item in devidos:
        print(f"Tentando {item['data']} {item['horario']} — {item['id']}")
        try:
            post_id = publicar_tiktok(item, token)
        except Exception as erro:
            print(f"ERRO tiktok: {erro}")
            registrar_falha(item, str(erro))
            continue
        item["tiktok"].update({"status": "publicado", "id": post_id, "publicado_em": datetime.now(BRT).isoformat()})
        item["tiktok"].pop("erro", None)
        item.update({"status": "concluido", "concluido_em": datetime.now(BRT).isoformat()})
        item.pop("tentativas", None)
        publicado = item
        break
    salvar_fila(fila)
    if publicado is None:
        raise SystemExit("Nenhum vídeo da fila conseguiu ser publicado no TikTok nesta rodada.")
    print(f"Publicado no TikTok: {publicado['data']} {publicado['horario']} — {publicado['id']}")


if __name__ == "__main__":
    main()
