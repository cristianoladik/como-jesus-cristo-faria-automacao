"""Valida os destinos de Stories sem enviar nem publicar qualquer mídia."""
import os
import requests

base = f"https://graph.facebook.com/{os.getenv('META_GRAPH_VERSION', 'v23.0')}"

def consultar(identificador, token, campos):
    resposta = requests.get(f"{base}/{identificador}", params={"fields": campos, "access_token": token}, timeout=30)
    if not resposta.ok:
        raise RuntimeError(f"Meta HTTP {resposta.status_code}: {resposta.text}")
    return resposta.json()

def iniciar_sessao_story_facebook(page_id, token):
    resposta = requests.post(
        f"{base}/{page_id}/video_stories",
        data={"upload_phase": "start", "access_token": token},
        timeout=30,
    )
    if not resposta.ok:
        raise RuntimeError(f"Facebook Stories indisponível: HTTP {resposta.status_code}: {resposta.text}")
    dados = resposta.json()
    if not dados.get("video_id") or not dados.get("upload_url"):
        raise RuntimeError(f"Facebook Stories não retornou sessão de upload: {dados}")
    return dados

ig = consultar(os.environ["IG_BUSINESS_ID"], os.environ["IG_ACCESS_TOKEN"], "id,username")
pagina = consultar(os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_ACCESS_TOKEN"], "id,name")
print(f"Instagram acessível: @{ig.get('username')} ({ig.get('id')})")
print(f"Página Facebook acessível: {pagina.get('name')} ({pagina.get('id')})")
sessao = iniciar_sessao_story_facebook(os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_ACCESS_TOKEN"])
print(f"Facebook Stories: sessão de upload autorizada ({sessao.get('video_id')}). Nenhuma mídia foi enviada.")
