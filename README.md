# Automação Instagram e Facebook — Como Jesus Cristo faria?

Este repositório executa somente estes fluxos, mesmo com o computador desligado:

- Reels: 09:00 e 21:00, horário de Brasília;
- Stories: um pacote diário às 09:00, com partes sequenciais de no máximo 59 segundos;
- publicação independente no Instagram e na Página do Facebook;
- confirmação separada por rede, sem repetir a rede que já confirmou.

As filas são `fila/fila-reels.json` e `fila/fila-stories.json`. Cada item aponta
para um asset temporário da release `fila-instagram-facebook`; ele não entra no
histórico Git. O asset só é removido depois da confirmação das duas redes.

O Drive continua sendo o acervo permanente e o computador apenas repõe o estoque
mínimo de 30 dias quando voltar a ficar ligado. TikTok e YouTube não têm acesso a
este repositório ou a essas filas.
