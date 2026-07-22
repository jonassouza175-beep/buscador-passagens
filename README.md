# Buscador de Passagens - Rio de Janeiro x Brasil / Europa

Script que roda sozinho todo dia, consulta preços de voo e te manda um
e-mail quando encontra uma boa oportunidade. Sem custo de servidor —
tudo roda no GitHub Actions.

## Como funciona

1. Todo dia, o GitHub Actions executa `buscar_passagem.py`.
2. Os destinos do dia (Brasil + Europa divididos em grupos ao longo da
   semana, pra não estourar a cota gratuita da API).
3. Pra cada destino, o script busca em **2 fases**, pra gastar API só
   quando faz sentido:
   - **Fase 1 - Sonda:** 1 única chamada, numa data de referência.
     Compara esse preço com a **média histórica** desse destino
     (guardada em `price_history.json`).
   - **Fase 2 - Busca completa:** só roda se a sonda já veio abaixo da
     média (ou abaixo do teto configurado). Aí sim o script testa todas
     as datas e origens configuradas pra achar o melhor preço de
     verdade.
   - Se a sonda mostrar preço normal, o script **não gasta mais
     chamadas** com aquele destino no dia — ele só atualiza o histórico
     com o preço da sonda mesmo.
4. Se, depois da fase que rodou, o preço final ficou abaixo da média ou
   do teto configurado, manda um e-mail com o resumo.

Na prática: num dia comum, a maioria dos destinos custa **1 chamada de
API cada**; só os que já dão sinal de queda logo na sonda é que
"ganham" a busca completa (várias chamadas). Isso reduz bastante o
consumo da cota gratuita comparado a testar todas as datas pra todos os
destinos todos os dias.

## Passo a passo para colocar no ar

### 1. Criar o repositório

Suba esses arquivos para um repositório novo no GitHub (pode ser privado).

### 2. Criar conta na Amadeus for Developers

1. Crie uma conta gratuita em `developers.amadeus.com`.
2. Crie um "app" novo — isso gera um **API Key** (client id) e um
   **API Secret** (client secret) do ambiente de teste (self-service).
3. O ambiente de teste é gratuito, mas vale ler a documentação da
   Amadeus sobre limites de chamadas da sua conta antes de aumentar a
   frequência ou o número de destinos — isso muda com o tempo, então
   não vou te dar um número fixo aqui que pode já estar desatualizado.

### 3. Criar uma senha de app no Gmail (ou outro provedor)

Se for usar Gmail como remetente:

1. Ative a verificação em duas etapas na conta Google.
2. Gere uma "senha de app" em `myaccount.google.com/apppasswords`.
3. Use essa senha (não a senha normal da conta) na secret `EMAIL_PASSWORD`.

Se preferir outro provedor de e-mail, troque `SMTP_SERVER`/`SMTP_PORT`
no workflow.

### 4. Configurar os "Secrets" no GitHub

No repositório: **Settings → Secrets and variables → Actions → New
repository secret**. Crie:

| Nome | Valor |
|---|---|
| `AMADEUS_CLIENT_ID` | API Key da Amadeus |
| `AMADEUS_CLIENT_SECRET` | API Secret da Amadeus |
| `EMAIL_FROM` | seu e-mail (remetente) |
| `EMAIL_PASSWORD` | senha de app gerada no passo 3 |
| `EMAIL_TO` | e-mail que vai receber os alertas (pode ser o mesmo) |

### 5. Ajustar `config.yaml`

Já vem preenchido com todas as capitais do Brasil e os principais hubs
europeus a partir do Rio. Você pode:

- Mudar `preco_maximo_brasil` / `preco_maximo_europa` para os tetos que
  fazem sentido pra você.
- Mudar `queda_percentual_minima` (padrão 10%).
- Ajustar `dias_a_partir_de_hoje` para as janelas de viagem que te
  interessam.
- Colocar `sempre_enviar_resumo: true` se quiser receber e-mail todo dia
  mesmo sem alerta.

### 6. Testar manualmente

Vá em **Actions → Monitorar Passagens → Run workflow** para rodar na
hora, sem esperar o horário agendado. Veja o log pra confirmar que
buscou os preços e (se configurado) mandou o e-mail.

## Limitações importantes (honestidade acima de tudo)

- O ambiente de teste da Amadeus às vezes retorna dados sintéticos ou
  incompletos para rotas domésticas menores — trate os alertas como
  "vale a pena olhar", não como preço garantido de compra.
- Passagem internacional a partir do Rio normalmente sai do Galeão
  (GIG); Santos Dumont (SDU) é praticamente só doméstico — por isso o
  script já ignora SDU nas buscas pra Europa automaticamente (a API só
  retorna resultado se a rota existir).
- Preços de passagem mudam por algoritmo de yield management o tempo
  todo — o alerta é um indicativo de queda relativa, não previsão de
  preço mínimo absoluto.

## Estrutura do projeto

```
buscador-passagens/
├── buscar_passagem.py              # script principal
├── config.yaml                     # rotas, datas e limites de alerta
├── requirements.txt                # dependências Python
├── price_history.json              # histórico (gerado automaticamente)
├── README.md
└── .github/workflows/
    └── monitorar_passagens.yml     # agenda a execução diária
```
