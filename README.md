# Automação multicanal — Como Jesus Cristo faria?

Arquitetura inspirada no publicador `pzoadriana/ig-agendamento-github`.

## Fluxo

1. O editor local fica no disco C, mas lê e grava vídeos somente no Drive `G:`.
2. Os vídeos aprovados ficam em `Como Jesus Cristo Faria/03 - Finalizados`.
3. `preparar_fila.py` cria a fila diária, usando o nome do vídeo como título do YouTube.
4. Os vídeos são copiados temporariamente para o repositório público.
5. Às 09:00 BRT, o GitHub Actions publica no Instagram, Facebook e YouTube.
6. Quando as três plataformas confirmam, o vídeo é removido do repositório.

## Textos padrão

- Instagram e Facebook: `Siga @como_jesuscristo_faria.`
- YouTube: título sem a numeração inicial do arquivo e descrição convidando a seguir o canal.

## YouTube temporariamente desativado

A publicação no YouTube está desativada nesta etapa através da flag
`ATIVAR_YOUTUBE` (env var lida em `publicar.py`, padrão `false`). Enquanto
estiver desativada:

- o script nunca lê nem exige `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`
  ou `YOUTUBE_REFRESH_TOKEN`, e nem precisa que `google-api-python-client`
  esteja instalado — a ausência desses segredos ou do pacote não afeta a
  publicação no Instagram/Facebook;
- cada item da fila é marcado com `"youtube": {"status": "desativado"}` e
  não entra no critério que decide se o vídeo já pode ser removido do
  repositório (esse critério passa a exigir só Instagram + Facebook);
- todo o código de publicação no YouTube foi preservado em `publicar.py`
  (`publicar_youtube`, `credenciais_youtube`).

Para reativar no futuro: configure os três segredos do Google/YouTube nos
GitHub Secrets e mude `ATIVAR_YOUTUBE` para `"true"` no `env:` do workflow
(`.github/workflows/publicar.yml`).

## Segredos do GitHub

Em uso nesta etapa (Instagram + Facebook):

- `IG_ACCESS_TOKEN`
- `IG_BUSINESS_ID`
- `FB_PAGE_ACCESS_TOKEN`
- `FB_PAGE_ID`

Reservados para quando o YouTube for reativado (ver seção acima):

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Nenhuma senha ou credencial deve ser gravada no código, no Git ou no Drive.

## Trava de segurança: um vídeo por dia

`publicar.py` interrompe a execução com erro caso `fila/fila.json` tenha
mais de um item para a mesma data, evitando publicação duplicada no
mesmo dia.

