# TikTok pelo navegador

Este projeto usa o TikTok Studio pela sessão autenticada do perfil do Chrome
**SUPORTE MENTORIA**. A conta esperada é `@como_jesuscristo_faria`.

O executor deve ler `tiktok_browser.json`, abrir a URL de upload, consultar
`fila/fila.json` e processar somente itens cujo `tiktok.status` ainda não seja
`programado` ou `publicado`.

Para cada item:

1. conferir se o arquivo e o horário ainda não aparecem em **Publicações**;
2. enviar `videos/<video_file>`;
3. substituir a descrição por `Siga @como_jesuscristo_faria.`;
4. selecionar **Programar**, a data do item e seu horário de Brasília;
5. manter a visibilidade **Todos**;
6. clicar em **Agendar** e confirmar o aviso de alcance, quando houver;
7. só então registrar `status: programado_navegador`, data, horário e aviso na fila.

O identificador interno da conexão do Chrome é temporário e nunca deve ser
salvo. O perfil deve ser localizado pelo nome visível **SUPORTE MENTORIA**.

Enquanto o aplicativo TikTok não tiver auditoria para publicação pública, o
TikTok não deve ser disparado pela API no GitHub Actions. O navegador é a rota
operacional deste projeto.
