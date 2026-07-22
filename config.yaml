# Buscador de Passagens - Rio de Janeiro x Brasil / Europa

Script que roda sozinho todo dia, consulta preços de voo e te manda um
e-mail quando encontra uma boa oportunidade. Sem custo de servidor —
tudo roda no GitHub Actions.

> **Nota sobre a fonte de dados:** a ideia original era usar a API da
> Amadeus, mas ela encerrou o cadastro aberto para novos
> desenvolvedores — agora só libera acesso mediante aprovação de
> empresa, o que não serve pra um projeto pessoal. Por isso o projeto
> usa a **Travelpayouts** (dados da Aviasales), que permite cadastro
> individual, sem aprovação, com token liberado na hora.

## Como funciona

1. Todo dia, o GitHub Actions executa `buscar_passagem.py`.
2. O script consulta, pra cada destino (Brasil + Europa), o menor preço
   já visto em cache pela Travelpayouts — **1 chamada de API por
   destino**, sem precisar testar várias datas.
3. Compara esse preço com a **média histórica** desse destino (guardada
   em `price_history.json`, versionado no próprio repositório).
4. Se caiu o suficiente (ou ficou abaixo de um teto que você define),
   manda um e-mail com o resumo.

## Passo a passo para colocar no ar

### 1. Criar o repositório

Suba esses arquivos para um repositório novo no GitHub (pode ser privado).

### 2. Criar conta na Travelpayouts (fonte dos preços)

1. Acesse `travelpayouts.com` e clique em **cadastro/registro** —
   cadastro individual, gratuito, sem precisar de empresa ou aprovação.
2. Confirme seu e-mail.
3. Depois de logado, vá em **Perfil → API token** (Profile → API
   token). O token já aparece pronto pra copiar.

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
| `TRAVELPAYOUTS_TOKEN` | token copiado no passo 2 |
| `EMAIL_FROM` | seu e-mail (remetente) |
| `EMAIL_PASSWORD` | senha de app gerada no passo 3 |
| `EMAIL_TO` | e-mail que vai receber os alertas (pode ser o mesmo) |

### 5. Ajustar `config.yaml`

Já vem preenchido com todas as capitais do Brasil e os principais hubs
europeus a partir do Rio. Você pode:

- Mudar `preco_maximo_brasil` / `preco_maximo_europa` para os tetos que
  fazem sentido pra você.
- Mudar `queda_percentual_minima` (padrão 10%).
- Colocar `sempre_enviar_resumo: true` se quiser receber e-mail todo dia
  mesmo sem alerta.
- Se os preços em `BRL` vierem estranhos (zerados ou muito baixos),
  troque `moeda: "BRL"` para `moeda: "USD"` no `config.yaml` — a
  conversão pode não estar disponível pra todas as moedas o tempo todo.

### 6. Testar manualmente

Vá em **Actions → Monitorar Passagens → Run workflow** para rodar na
hora, sem esperar o horário agendado. Veja o log pra confirmar que
buscou os preços e (se configurado) mandou o e-mail.

## Limitações importantes (honestidade acima de tudo)

- A base de dados da Aviasales/Travelpayouts é mais forte em **rotas
  internacionais**. Pra rotas 100% domésticas do Brasil (só
  LATAM/GOL/Azul, sem conexão internacional) a cobertura pode ser mais
  fraca — alguns destinos podem aparecer sempre como "sem dados". Trate
  os alertas como "vale a pena olhar", não como garantia de ter
  encontrado todas as opções.
- Os preços vêm de um **cache** de buscas feitas por outros usuários
  (não é uma cotação ao vivo) — sempre confirme no site da companhia
  antes de comprar.
- Passagem internacional a partir do Rio normalmente sai do Galeão
  (GIG); Santos Dumont (SDU) é praticamente só doméstico.
- Preços de passagem mudam por algoritmo de yield management o tempo
  todo — o alerta é um indicativo de queda relativa, não previsão de
  preço mínimo absoluto.

## Estrutura do projeto

```
buscador-passagens/
├── buscar_passagem.py              # script principal
├── config.yaml                     # rotas e limites de alerta
├── requirements.txt                # dependências Python
├── price_history.json              # histórico (gerado automaticamente)
├── README.md
└── .github/workflows/
    └── monitorar_passagens.yml     # agenda a execução diária
```
