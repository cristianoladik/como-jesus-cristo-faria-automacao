"""Executa um único teste real de Reel e Story em IG e Facebook.

Este programa não toca nas filas operacionais. Cada chamada é feita no máximo
uma vez e seu resultado é gravado para auditoria, inclusive em caso de falha.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from publicar import BRT, graph_get, publicar_facebook as publicar_reel_facebook, publicar_instagram as publicar_reel_instagram
from publicar_stories import publicar_facebook as publicar_story_facebook, publicar_instagram as publicar_story_instagram

ROOT = Path(__file__).resolve().parent
RESULTADO = ROOT / "fila" / "testes-publicacao.json"


def salvar(dados: dict) -> None:
    RESULTADO.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def permalink_instagram(media_id: str) -> str | None:
    try:
        return graph_get(media_id, {"fields": "permalink", "access_token": os.environ["IG_ACCESS_TOKEN"]}).get("permalink")
    except Exception:
        return None


def executar(nome: str, funcao, dados: dict, resultado: dict, historico: dict) -> None:
    try:
        media_id = str(funcao(dados))
        item = {"status": "publicado", "id": media_id, "publicado_em": datetime.now(BRT).isoformat()}
        if nome.startswith("instagram"):
            item["permalink"] = permalink_instagram(media_id)
        resultado["resultados"][nome] = item
    except Exception as erro:
        resultado["resultados"][nome] = {"status": "erro", "erro": str(erro), "tentado_em": datetime.now(BRT).isoformat()}
    salvar(historico)


def main() -> None:
    url = os.environ["TEST_VIDEO_URL"].strip()
    asset = os.environ["TEST_ASSET"].strip()
    origem = os.environ["TEST_SOURCE_NAME"].strip()
    sha256 = os.environ["TEST_SHA256"].strip()
    tamanho_bytes = os.environ["TEST_TAMANHO_BYTES"].strip()
    if not url or not asset or not origem or not sha256 or not tamanho_bytes:
        raise RuntimeError("Variáveis TEST_* obrigatórias ausentes.")

    midia = {
        "asset": asset,
        "url_publica": url,
        "sha256": sha256,
        "tamanho_bytes": int(tamanho_bytes),
    }

    resultado = {
        "id": f"teste-real-{datetime.now(BRT):%Y%m%d-%H%M%S}",
        "origem": origem,
        "midia": midia,
        "iniciado_em": datetime.now(BRT).isoformat(),
        "objetivo": "Validar Reel e Story no Instagram e Facebook por API.",
        "resultados": {},
    }
    historico = json.loads(RESULTADO.read_text(encoding="utf-8")) if RESULTADO.exists() else {"testes": []}
    historico.setdefault("testes", []).append(resultado)
    salvar(historico)

    reel = {
        "midia": midia,
        "instagram": {"legenda": "Siga @como_jesuscristo_faria."},
        "facebook": {"legenda": "Siga @como_jesuscristo_faria."},
    }
    story = {
        "ordem": 1,
        "midia": midia,
        "instagram": {},
        "facebook": {},
    }
    executar("instagram_reel", publicar_reel_instagram, reel, resultado, historico)
    executar("facebook_reel", publicar_reel_facebook, reel, resultado, historico)
    executar("instagram_story", publicar_story_instagram, story, resultado, historico)
    executar("facebook_story", publicar_story_facebook, story, resultado, historico)
    resultado["concluido_em"] = datetime.now(BRT).isoformat()
    salvar(historico)
    if any(x.get("status") != "publicado" for x in resultado["resultados"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
