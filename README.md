# 🏡 Dona Maria – Radar de Ofertas para as Melhores Donas de Casa

Bot automático que posta **ofertas selecionadas do Mercado Livre** no Telegram, com foco exclusivo em produtos para casa, cozinha, organização, limpeza e eletrodomésticos.

Ideal para grupos e canais voltados às **melhores donas de casa**.

## Nicho

- Casa & Organização
- Eletrodomésticos & Cozinha
- Limpeza & Utilidades
- Decoração & Conforto

## Como funciona

- Roda a cada hora via GitHub Actions
- Seleciona até 4 produtos diversificados (um de cada grupo)
- Evita repetir o mesmo produto por 14 dias
- Prioriza frete grátis
- Horário (America/Sao_Paulo):
  - 07h–22h: toda hora
  - 23h, 02h e 05h: madrugada

## Configuração

1. Crie o grupo no Telegram e adicione o bot `@adona_maria_07_bot` como administrador.
2. Pegue o `CHAT_ID` do grupo (pode usar o bot `@userinfobot` ou `@getidsbot` no grupo).
3. No repositório → **Settings → Secrets and variables → Actions**, adicione:

| Secret | Descrição |
|--------|-----------|
| `TELEGRAM_TOKEN` | Token do bot (ex: o que o BotFather te deu) |
| `TELEGRAM_CHAT_ID` | ID do grupo (ex: `-100xxxxxxxxxx`) |
| `ML_CLIENT_ID` | Client ID da aplicação Mercado Livre |
| `ML_CLIENT_SECRET` | Client Secret da aplicação Mercado Livre |

4. (Opcional) `ML_AFFILIATE_ID` já está definido como `71970283` no workflow.

## Executar manualmente

Vá em **Actions → Dona Maria Radar → Run workflow**.

## Origem

Baseado no projeto [radar-ml](https://github.com/epratesti/radar-ml), adaptado para o nicho **Dona Maria**.
