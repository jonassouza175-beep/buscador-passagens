"""
Buscador de passagens - Rio de Janeiro x Brasil / Europa
Consulta preços via Travelpayouts Data API (dados em cache da Aviasales),
compara com o histórico salvo e envia um e-mail quando encontra uma boa
oportunidade.

Por que Travelpayouts e não Amadeus?
A Amadeus fechou o portal self-service para novos desenvolvedores em
17/07/2026. A Travelpayouts Data API é gratuita, sem exigir volume mínimo
de usuários, e já retorna o menor preço em cache por rota em 1 única
chamada - o que também resolve naturalmente a preocupação de gastar API
à toa: cada destino custa só 1 chamada por execução.

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

TRAVELPAYOUTS_BASE = "https://api.travelpayouts.com"
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


def atualizar_historico(chave, oferta, historico, tamanho_max):
    preco_atual = oferta["price"]
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
    registro["ultima_oferta"] = {
        "origem": oferta.get("origem"),
        "data_ida": oferta.get("departure_at"),
        "data_volta": oferta.get("return_at"),
        "companhia": oferta.get("airline"),
        "numero_voo": oferta.get("flight_number"),
    }
    historico[chave] = registro


# ----------------------------------------------------------------------
# Travelpayouts Data API
# ----------------------------------------------------------------------

def buscar_oferta_mais_barata(token, origem, destino, moeda):
    """Consulta a oferta mais barata em cache (achada por buscas reais de usuários
    da Aviasales nos últimos dias) para a rota. Retorna o dicionário completo da
    oferta (preco, datas, companhia) ou None se não achar nada."""
    params = {
        "origin": origem,
        "destination": destino,
        "currency": moeda,
        "token": token,
    }
    try:
        resp = requests.get(
            f"{TRAVELPAYOUTS_BASE}/v1/prices/cheap",
            params=params,
            timeout=30,
        )
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    corpo = resp.json()
    if not corpo.get("success"):
        return None

    dados_destino = corpo.get("data", {}).get(destino)
    if not dados_destino:
        return None

    ofertas = [oferta for oferta in dados_destino.values() if "price" in oferta]
    if not ofertas:
        return None

    return min(ofertas, key=lambda o: o["price"])


def melhor_oferta_entre_origens(token, origem_lista, destino, moeda):
    """Testa cada aeroporto de origem configurado e fica com a oferta mais
    barata encontrada, já com o aeroporto de origem anexado."""
    melhor = None
    for origem in origem_lista:
        oferta = buscar_oferta_mais_barata(token, origem, destino, moeda)
        if oferta is not None and (melhor is None or oferta["price"] < melhor["price"]):
            melhor = {**oferta, "origem": origem}
    return melhor


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


def avaliar_alerta(preco_atual, media, teto_absoluto, queda_percentual_minima):
    """Decide se o preço encontrado merece um alerta por e-mail."""
    if preco_atual is None:
        return False, None

    motivos = []
    if media is not None:
        queda_pct = 100 * (media - preco_atual) / media
        if queda_pct >= queda_percentual_minima:
            motivos.append(f"{queda_pct:.0f}% abaixo da média histórica (R$ {media:.0f})")

    if preco_atual <= teto_absoluto:
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


def formatar_data_viagem(oferta):
    if oferta is None:
        return "-"
    data_ida = oferta.get("departure_at")
    data_volta = oferta.get("return_at")
    if not data_ida:
        return "-"
    ida_fmt = data_ida[:10]  # YYYY-MM-DD, sem hora
    if data_volta:
        return f"{ida_fmt} → {data_volta[:10]}"
    return ida_fmt


def montar_html(resultados, alertas):
    linhas = []
    for r in resultados:
        destaque = ' style="color:#0a7d2c;font-weight:bold;"' if r["alerta"] else ""
        preco_fmt = f"R$ {r['preco']:.0f}" if r["preco"] is not None else "sem dados"
        data_viagem = formatar_data_viagem(r.get("oferta"))
        origem_fmt = r["oferta"]["origem"] if r.get("oferta") else "-"
        linhas.append(
            f"<tr><td>{r['nome']}</td><td{destaque}>{preco_fmt}</td>"
            f"<td>{origem_fmt}</td><td>{data_viagem}</td><td>{r['motivo'] or '-'}</td></tr>"
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
      <tr><th>Destino</th><th>Menor preço encontrado</th><th>Saindo de</th><th>Data da viagem</th><th>Motivo do alerta</th></tr>
      {tabela}
    </table>
    <p style="color:#888;font-size:12px;">
      Preços via Travelpayouts/Aviasales (dados em cache de buscas recentes de usuários,
      podem ter até alguns dias) - confirme sempre no site da companhia antes de comprar.
      A data mostrada é a que estava disponível na oferta mais barata encontrada, não
      necessariamente a data mais barata possível para a rota.
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
    moeda = config["busca"]["moeda"]
    tamanho_max_media = config["busca"].get("tamanho_historico_media", 20)
    queda_percentual_minima = config["alertas"]["queda_percentual_minima"]
    token = os.environ["TRAVELPAYOUTS_TOKEN"]

    destinos_hoje = montar_destinos_do_dia(config)

    resultados = []
    alertas = []

    for chave, info in destinos_hoje.items():
        teto_absoluto = (
            config["alertas"]["preco_maximo_brasil"]
            if info["tipo"] == "brasil"
            else config["alertas"]["preco_maximo_europa"]
        )
        media = media_historica(historico, chave)

        oferta = melhor_oferta_entre_origens(token, origem_lista, info["codigo"], moeda)
        preco = oferta["price"] if oferta is not None else None

        primeira_vez = media is None
        eh_alerta, motivo = (False, None)
        if not primeira_vez:
            eh_alerta, motivo = avaliar_alerta(preco, media, teto_absoluto, queda_percentual_minima)

        resultados.append({
            "nome": info["nome"],
            "preco": preco,
            "oferta": oferta,
            "alerta": eh_alerta,
            "motivo": motivo,
        })
        if eh_alerta:
            alertas.append(chave)

        if oferta is not None:
            atualizar_historico(chave, oferta, historico, tamanho_max_media)

    salvar_historico(historico)

    print(f"Destinos checados hoje: {len(destinos_hoje)} | Alertas: {len(alertas)}")

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
