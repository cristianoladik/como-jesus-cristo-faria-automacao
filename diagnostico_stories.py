"""Valida acesso de leitura aos destinos de Stories sem publicar mídia."""
import os
import requests

base = f"https://graph.facebook.com/{os.getenv('META_GRAPH_VERSION', 'v23.0')}"

def consultar(identificador, token, campos):
    resposta = requests.get(f"{base}/{identificador}", params={"fields": campos, "access_token": token}, timeout=30)
    if not resposta.ok:
        raise RuntimeError(f"Meta HTTP {resposta.status_code}: {resposta.text}")
    return resposta.json()

ig = consultar(os.environ["IG_BUSINESS_ID"], os.environ["IG_ACCESS_TOKEN"], "id,username")
pagina = consultar(os.environ["FB_PAGE_ID"], os.environ["FB_PAGE_ACCESS_TOKEN"], "id,name")
print(f"Instagram acessível: @{ig.get('username')} ({ig.get('id')})")
print(f"Página Facebook acessível: {pagina.get('name')} ({pagina.get('id')})")
