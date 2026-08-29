# Automação multicanal — Como Jesus Cristo faria?

Arquitetura inspirada no publicador `pzoadriana/ig-agendamento-github`.

## Fluxo

1. O editor local fica no disco C, mas lê e grava vídeos somente no Drive `G:`.
2. Os vídeos aprovados ficam em `Como Jesus Cristo Faria/03 - Finalizados`.
3. `preparar_fila.py` cria a fila diária, usando o nome do vídeo como título do YouTube.
4. Os vídeos são copiados temporariamente para o repositório público.
5. Às 08:00 BRT, o GitHub Actions publica no Instagram, Facebook e YouTube.
6. Quando as três plataformas confirmam, o vídeo é removido do repositório.

## Textos padrão

- Instagram e Facebook: `Siga @como_jesuscristo_faria.`
- YouTube: título sem a numeração inicial do arquivo e descrição convidando a seguir o canal.

## Segredos do GitHub

- `IG_ACCESS_TOKEN`
- `IG_BUSINESS_ID`
- `FB_PAGE_ACCESS_TOKEN`
- `FB_PAGE_ID`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Nenhuma senha ou credencial deve ser gravada no código, no Git ou no Drive.

