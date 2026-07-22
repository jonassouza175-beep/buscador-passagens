# Passo a passo - do zero até o buscador funcionando

Este guia parte do princípio de que você nunca usou GitHub. Vai levar
uns 30-40 minutos na primeira vez. Depois disso, o buscador roda
sozinho, sem você precisar fazer mais nada.

---

## Parte 1 - Criar sua conta no GitHub (onde o robô vai morar)

1. Acesse **github.com** e clique em "Sign up".
2. Crie a conta com seu e-mail, uma senha e um nome de usuário.
3. Confirme o e-mail que o GitHub te mandar.

## Parte 2 - Criar o repositório (a "pasta" do projeto)

1. Já logado, clique no **+** no canto superior direito → **New repository**.
2. Em "Repository name", coloque `buscador-passagens`.
3. Marque como **Private** (só você vê).
4. Clique em **Create repository**.

## Parte 3 - Subir os arquivos que eu já criei

Você tem 5 arquivos/pastas prontos: `buscar_passagem.py`,
`config.yaml`, `requirements.txt`, `README.md` e a pasta
`.github/workflows/monitorar_passagens.yml`.

1. Baixe todos esses arquivos pro seu computador (o painel de arquivos
   aqui do Claude tem o botão de download em cada um).
2. Na página do seu repositório recém-criado no GitHub, clique em
   **"uploading an existing file"** (ou "Add file" → "Upload files").
3. Arraste os arquivos `buscar_passagem.py`, `config.yaml`,
   `requirements.txt` e `README.md` pra essa tela.
4. Para o arquivo dentro de `.github/workflows/`, é importante manter
   essa estrutura de pastas. O jeito mais fácil: ao arrastar o arquivo
   `monitorar_passagens.yml`, renomeie o caminho pra
   `.github/workflows/monitorar_passagens.yml` direto na caixa de
   upload do GitHub (ele aceita caminho com pastas no nome do arquivo).
5. Clique em **Commit changes** no final da página.

> Se tiver dificuldade nessa parte de subir a pasta `.github`, me
> avise que eu te mostro um jeito alternativo (dá pra criar o arquivo
> direto pela interface do GitHub, clicando em "Add file" → "Create
> new file" e colando o conteúdo).

## Parte 4 - Criar sua conta na Travelpayouts (fonte dos preços de voo)

> A ideia original era usar a Amadeus, mas ela fechou o cadastro aberto
> pra novos desenvolvedores (agora exige aprovação de empresa). Por
> isso trocamos pra Travelpayouts, que tem cadastro individual e
> instantâneo.

1. Acesse **travelpayouts.com** e clique em cadastro/registro (é grátis
   e não pede aprovação de ninguém).
2. Confirme seu e-mail.
3. Depois de logado, vá em **Perfil** (Profile) → **API token**.
4. Copie o token que já aparece pronto na tela.
5. Guarde esse token num lugar seguro por enquanto (vamos usar na
   Parte 6).

## Parte 5 - Criar uma senha especial no Gmail (pra enviar o e-mail)

O robô não pode usar sua senha normal do Gmail, ele precisa de uma
"senha de app" separada, mais segura.

1. Acesse **myaccount.google.com**.
2. No menu da esquerda, clique em **Segurança**.
3. Ative a **Verificação em duas etapas** se ainda não estiver ativa
   (o Google vai te pedir pra confirmar com o celular).
4. Depois de ativada, volte em Segurança e procure por
   **"Senhas de app"** (ou acesse diretamente
   myaccount.google.com/apppasswords).
5. Crie uma senha de app nova, dê o nome "buscador-passagens".
6. O Google vai mostrar uma senha de 16 letras — copie e guarde
   também. É essa que vamos usar, não a senha normal da sua conta.

## Parte 6 - Guardar as chaves com segurança dentro do GitHub

Essas informações (token da Travelpayouts + senha do Gmail) não ficam
escritas em nenhum arquivo — elas ficam guardadas de forma
criptografada dentro do próprio GitHub, num lugar chamado "Secrets".

1. No seu repositório, clique em **Settings** (a aba lá em cima).
2. No menu da esquerda, clique em **Secrets and variables** → **Actions**.
3. Clique em **New repository secret** e crie, um de cada vez, estes 5:

   | Nome exato (copie certinho) | O que colocar |
   |---|---|
   | `TRAVELPAYOUTS_TOKEN` | o token da Travelpayouts (Parte 4) |
   | `EMAIL_FROM` | seu e-mail do Gmail |
   | `EMAIL_PASSWORD` | a senha de app de 16 letras (Parte 5) |
   | `EMAIL_TO` | o e-mail que vai receber os alertas (pode ser o mesmo) |

   Pra cada uma: cole o **nome** exatamente como na tabela, cole o
   **valor**, e clique em **Add secret**.

## Parte 7 - Testar se está tudo funcionando

1. No seu repositório, clique na aba **Actions** (lá em cima).
2. Você vai ver "Monitorar Passagens" na lista à esquerda — clique nele.
3. Clique no botão **Run workflow** (do lado direito) → **Run workflow**
   de novo pra confirmar.
4. Espere uns 1-2 minutos e atualize a página. Vai aparecer uma
   execução com uma bolinha (amarela rodando, verde se deu certo,
   vermelha se deu erro).
5. Clique nela pra ver o passo a passo do que rodou. Se der erro, me
   manda um print da mensagem que eu te ajudo a resolver.

## Parte 8 - E agora?

- Se tudo deu certo, o robô vai rodar **sozinho, todo dia às 8h**
  (horário de Brasília), sem você precisar fazer nada.
- Na **primeira semana**, ele ainda está "aprendendo" o preço médio de
  cada destino (por isso não vai mandar alerta de queda logo de cara —
  ele precisa de um histórico mínimo pra comparar).
- Você só recebe e-mail quando encontrar uma queda de preço de verdade
  (ou puder mudar isso no `config.yaml`, olha o README pra mais
  detalhes).

---

Qualquer erro que aparecer na aba Actions, me manda o texto ou um print
que eu te ajudo a resolver.
