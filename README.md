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

## Publicação no YouTube pelo navegador

O processo oficial do YouTube usa o recurso nativo do **YouTube Studio no
navegador**, sem depender da API para programar os vídeos. O workflow mantém
`ATIVAR_YOUTUBE=false` para impedir que o mesmo vídeo seja enviado duas vezes.

Para cada vídeo:

1. abrir o canal **Como Jesus Cristo faria?** no YouTube Studio;
2. enviar o arquivo correspondente da pasta de finalizados;
3. usar como título o nome do vídeo sem a numeração inicial;
4. usar a descrição padrão convidando a pessoa a se inscrever no canal;
5. marcar **Não é conteúdo para crianças**;
6. programar um vídeo por dia, às **09:00 de Brasília**;
7. confirmar na página de conteúdo do canal que data e horário estão corretos.

Com o YouTube desativado no robô:

- o script nunca lê nem exige `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`
  ou `YOUTUBE_REFRESH_TOKEN`, e nem precisa que `google-api-python-client`
  esteja instalado — a ausência desses segredos ou do pacote não afeta a
  publicação no Instagram/Facebook;
- cada item da fila é marcado com `"youtube": {"status": "desativado"}` e
  não entra no critério que decide se o vídeo já pode ser removido do
  repositório (esse critério passa a exigir só Instagram + Facebook);
- todo o código de publicação no YouTube foi preservado em `publicar.py`
  (`publicar_youtube`, `credenciais_youtube`).

O código da API permanece preservado apenas para uma possível retomada futura.
Para reativá-lo, será necessário confirmar as credenciais e trocar
`ATIVAR_YOUTUBE` para `"true"` no workflow.

## Segredos do GitHub

Em uso nesta etapa (Instagram + Facebook):

- `IG_ACCESS_TOKEN`
- `IG_BUSINESS_ID`
- `FB_PAGE_ACCESS_TOKEN`
- `FB_PAGE_ID`

Reservados para uma possível automação futura do YouTube:

- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

Nenhuma senha ou credencial deve ser gravada no código, no Git ou no Drive.

## Trava de segurança: um vídeo por dia

`publicar.py` interrompe a execução com erro caso `fila/fila.json` tenha
mais de um item para a mesma data, evitando publicação duplicada no
mesmo dia.

