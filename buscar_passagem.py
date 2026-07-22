"""
Buscador de passagens - Rio de Janeiro x Brasil / Europa
Consulta preços via API da Amadeus, compara com o histórico salvo
e envia um e-mail quando encontra uma boa oportunidade.

Estratégia de economia de API (2 fases):
  1) "Sonda": 1 única chamada por destino, numa data de referência.
     Compara o preço com a MÉDIA histórica desse destino.
  2) Só se a sonda já vier abaixo da média (ou do teto configurado),
     o script faz a busca completa (várias datas/origens) pra achar
     o melhor preço de verdade e decidir o alerta.
  Destinos com preço "normal" na sonda não geram chamadas extras.

Rodado diariamente via GitHub Actions (ver .github/workflows/monitorar_passagens.yml).
"""

import os
import json
import statistics
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import yaml

AMADEUS_BASE = "https://test.api.amadeus.com"  # ambiente sandbox (gratuito)
HISTORICO_PATH = "price_history.json"
CONFIG_PATH = "config.yaml"


# ----------------------------------------------------------------------
# Configuração e histórico
# ----------------------------------------------------------------------

def carregar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_historico():
    if os.path.exists(HISTORICO_PATH):
        with open(HISTORICO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def salvar_historico(historico):
    with open(HISTORICO_PATH, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def media_historica(historico, chave):
    registro = historico.get(chave, {})
    precos = registro.get("precos_recentes", [])
    return statistics.mean(precos) if precos else None


def atualizar_historico(chave, preco_atual, historico, tamanho_max):
    registro = historico.get(chave, {"precos_recentes": [], "menor_preco": None})
    precos = registro.get("precos_recentes", [])
    precos.append(preco_atual)
    if len(precos) > tamanho_max:
        precos = precos[-tamanho_max:]
    registro["precos_recentes"] = precos

    menor_atual = registro.get("menor_preco")
    if menor_atual is None or preco_atual < menor_atual:
        registro["menor_preco"] = preco_atual

    registro["ultimo_preco"] = preco_atual
    registro["ultima_atualizacao"] = datetime.date.today().isoformat()
    historico[chave] = registro


# ----------------------------------------------------------------------
# API da Amadeus
# ----------------------------------------------------------------------

def obter_token():
    resp = requests.post(
        f"{AMADEUS_BASE}/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["AMADEUS_CLIENT_ID"],
            "client_secret": os.environ["AMADEUS_CLIENT_SECRET"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def buscar_menor_preco(token, origem, destino, data_ida, data_volta, adultos, moeda):
    """Retorna o menor preço encontrado para a data testada, ou None se não achar nada."""
    params = {
        "originLocationCode": origem,
        "destinationLocationCode": destino,
        "departureDate": data_ida,
        "adults": adultos,
        "currencyCode": moeda,
        "max": 5,
    }
    if data_volta:
        params["returnDate"] = data_volta

    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(
            f"{AMADEUS_BASE}/v2/shopping/flight-offers",
            headers=headers,
            params=params,
            timeout=30,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    ofertas = resp.json().get("data", [])
    if not ofertas:
        return None

    precos = [float(o["price"]["total"]) for o in ofertas]
    return min(precos)


# ----------------------------------------------------------------------
# Lógica principal
# ----------------------------------------------------------------------

def montar_destinos_do_dia(config):
    """Combina Brasil + Europa e seleciona apenas o grupo do dia da semana,
    para espalhar as chamadas de API ao longo da semana."""
    todos = {}
    for uf, codigo in config["destinos_brasil"].items():
        todos[f"BR-{uf}"] = {"codigo": codigo, "tipo": "brasil", "nome": f"{uf} ({codigo})"}
    for nome, codigo in config["destinos_europa"].items():
        todos[f"EU-{nome}"] = {"codigo": codigo, "tipo": "europa", "nome": f"{nome} ({codigo})"}

    grupos = config["busca"]["grupos_por_semana"]
    dia_semana = datetime.datetime.utcnow().weekday()  # 0 = segunda

    itens = list(todos.items())
    do_dia = itens[dia_semana::grupos] if grupos > 0 else itens
    return dict(do_dia)


def data_para_dias(dias, tipo, duracao, config):
    data_ida = (datetime.date.today() + datetime.timedelta(days=dias)).isoformat()
    data_volta = None
    if tipo == "europa":
        data_volta = (datetime.date.today() + datetime.timedelta(days=dias + duracao)).isoformat()
    return data_ida, data_volta


def sondar_preco(token, origem_lista, destino_info, config):
    """Fase 1: UMA chamada, na primeira data configurada, com a primeira origem.
    É barato de propósito - serve só pra decidir se vale investir mais chamadas."""
    tipo = destino_info["tipo"]
    dias_teste = config["busca"]["dias_a_partir_de_hoje"]
    duracao = config["busca"]["duracao_viagem_dias"]
    adultos = config["busca"]["adultos"]
    moeda = config["busca"]["moeda"]

    origem = origem_lista[0]
    data_ida, data_volta = data_para_dias(dias_teste[0], tipo, duracao, config)
    return buscar_menor_preco(token, origem, destino_info["codigo"], data_ida, data_volta, adultos, moeda)


def buscar_completo(token, origem_lista, destino_info, config):
    """Fase 2: só roda quando a sonda já indicou preço abaixo da média.
    Testa todas as datas/origens configuradas pra achar o melhor preço real."""
    tipo = destino_info["tipo"]
    dias_teste = config["busca"]["dias_a_partir_de_hoje"]
    duracao = config["busca"]["duracao_viagem_dias"]
    adultos = config["busca"]["adultos"]
    moeda = config["busca"]["moeda"]

    melhor_preco = None
    for dias in dias_teste:
        data_ida, data_volta = data_para_dias(dias, tipo, duracao, config)
        for origem in origem_lista:
            preco = buscar_menor_preco(token, origem, destino_info["codigo"], data_ida, data_volta, adultos, moeda)
            if preco is not None and (melhor_preco is None or preco < melhor_preco):
                melhor_preco = preco
    return melhor_preco


def vale_a_pena_investigar(preco_sonda, media, teto_absoluto, queda_percentual_minima):
    """Decide se a sonda já justifica gastar mais chamadas de API."""
    if preco_sonda is None:
        return False
    if preco_sonda <= teto_absoluto:
        return True
    if media is not None:
        limite = media * (1 - queda_percentual_minima / 100)
        if preco_sonda <= limite:
            return True
    return False


def avaliar_alerta(preco_final, historico_registro, media, teto_absoluto, queda_percentual_minima):
    """Decide o alerta final, já com o preço da busca completa (mais confiável que a sonda)."""
    if preco_final is None:
        return False, None

    motivos = []
    if media is not None:
        queda_pct = 100 * (media - preco_final) / media
        if queda_pct >= queda_percentual_minima:
            motivos.append(f"{queda_pct:.0f}% abaixo da média histórica (R$ {media:.0f})")

    if preco_final <= teto_absoluto:
        motivos.append(f"abaixo do teto configurado (R$ {teto_absoluto:.0f})")

    return (len(motivos) > 0), " e ".join(motivos)


# ----------------------------------------------------------------------
# E-mail
# ----------------------------------------------------------------------

def enviar_email(assunto, corpo_html):
    remetente = os.environ["EMAIL_FROM"]
    senha = os.environ["EMAIL_PASSWORD"]
    destinatario = os.environ["EMAIL_TO"]
    servidor = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    porta = int(os.environ.get("SMTP_PORT", "587"))

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = remetente
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))

    with smtplib.SMTP(servidor, porta) as smtp:
        smtp.starttls()
        smtp.login(remetente, senha)
        smtp.sendmail(remetente, destinatario, msg.as_string())


def montar_html(resultados, alertas):
    linhas = []
    for r in resultados:
        destaque = ' style="color:#0a7d2c;font-weight:bold;"' if r["alerta"] else ""
        preco_fmt = f"R$ {r['preco']:.0f}" if r["preco"] is not None else "sem dados"
        investigado = "sim" if r["investigado"] else "não (preço normal na sonda)"
        linhas.append(
            f"<tr><td>{r['nome']}</td><td{destaque}>{preco_fmt}</td>"
            f"<td>{r['motivo'] or '-'}</td><td>{investigado}</td></tr>"
        )

    tabela = "\n".join(linhas)
    resumo_alerta = (
        f"<p><strong>{len(alertas)} oportunidade(s) encontrada(s) hoje.</strong></p>"
        if alertas
        else "<p>Nenhuma queda relevante hoje, segue o resumo do dia.</p>"
    )

    return f"""
    <html><body>
    <h2>Buscador de passagens - resumo do dia</h2>
    {resumo_alerta}
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Destino</th><th>Menor preço encontrado</th><th>Motivo do alerta</th><th>Busca completa?</th></tr>
      {tabela}
    </table>
    <p style="color:#888;font-size:12px;">
      Preços via Amadeus (ambiente de teste) - confirme sempre no site da companhia antes de comprar.<br>
      "Busca completa" = destinos onde a sonda inicial já indicou preço abaixo da média,
      por isso o script investiu mais chamadas de API pra achar o melhor preço.
    </p>
    </body></html>
    """


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    config = carregar_config()
    historico = carregar_historico()
    origem_lista = config["origem"]["aeroportos"]
    tamanho_max_media = config["busca"].get("tamanho_historico_media", 20)
    queda_percentual_minima = config["alertas"]["queda_percentual_minima"]

    token = obter_token()
    destinos_hoje = montar_destinos_do_dia(config)

    resultados = []
    alertas = []
    chamadas_sonda = 0
    chamadas_completas = 0

    for chave, info in destinos_hoje.items():
        teto_absoluto = (
            config["alertas"]["preco_maximo_brasil"]
            if info["tipo"] == "brasil"
            else config["alertas"]["preco_maximo_europa"]
        )
        media = media_historica(historico, chave)

        preco_sonda = sondar_preco(token, origem_lista, info, config)
        chamadas_sonda += 1

        investigar = vale_a_pena_investigar(preco_sonda, media, teto_absoluto, queda_percentual_minima)
        # Sempre investiga na primeira vez (sem histórico ainda) pra criar a base de comparação.
        primeira_vez = media is None
        investigar_final = investigar or primeira_vez

        if investigar_final:
            preco_final = buscar_completo(token, origem_lista, info, config)
            chamadas_completas += 1
        else:
            preco_final = preco_sonda  # não vale gastar mais API, fica com o preço da sonda

        eh_alerta, motivo = (False, None)
        if not primeira_vez:
            eh_alerta, motivo = avaliar_alerta(preco_final, historico.get(chave), media, teto_absoluto, queda_percentual_minima)

        resultados.append({
            "nome": info["nome"],
            "preco": preco_final,
            "alerta": eh_alerta,
            "motivo": motivo,
            "investigado": investigar_final,
        })
        if eh_alerta:
            alertas.append(chave)

        if preco_final is not None:
            atualizar_historico(chave, preco_final, historico, tamanho_max_media)

    salvar_historico(historico)

    print(f"Sondas: {chamadas_sonda} | Buscas completas: {chamadas_completas} | Alertas: {len(alertas)}")

    deve_enviar = bool(alertas) or config["alertas"]["sempre_enviar_resumo"]
    if deve_enviar:
        assunto = (
            f"✈️ {len(alertas)} oportunidade(s) de passagem hoje!"
            if alertas
            else "Resumo diário do buscador de passagens"
        )
        html = montar_html(resultados, alertas)
        enviar_email(assunto, html)
        print("E-mail enviado.")
    else:
        print("Nenhum alerta e resumo diário desativado - e-mail não enviado.")


if __name__ == "__main__":
    main()
