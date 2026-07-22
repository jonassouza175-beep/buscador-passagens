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
import xml.etree.ElementTree as ET
import email.utils
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import yaml

MELHORESDESTINOS_FEED = "https://www.melhoresdestinos.com.br/feed"

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
    barata encontrada, já com o aeroporto de origem e o destino anexados."""
    melhor = None
    for origem in origem_lista:
        oferta = buscar_oferta_mais_barata(token, origem, destino, moeda)
        if oferta is not None and (melhor is None or oferta["price"] < melhor["price"]):
            melhor = {**oferta, "origem": origem, "destino": destino}
    return melhor


# ----------------------------------------------------------------------
# Melhores Destinos (RSS público - forma legítima de acompanhar, sem raspagem)
# ----------------------------------------------------------------------

def buscar_promocoes_melhoresdestinos(palavras_chave, horas_recentes=48):
    """Lê o feed RSS público do Melhores Destinos (feito pra consumo automatizado,
    diferente de raspar a página de busca deles) e retorna só os posts recentes
    que mencionam algum dos destinos monitorados."""
    try:
        resp = requests.get(MELHORESDESTINOS_FEED, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []

    agora = datetime.datetime.now(datetime.timezone.utc)
    limite = agora - datetime.timedelta(hours=horas_recentes)

    encontrados = []
    for item in root.findall(".//item"):
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        descricao = (item.findtext("description") or "").strip()
        pub_date_str = item.findtext("pubDate")

        pub_date = None
        if pub_date_str:
            try:
                pub_date = email.utils.parsedate_to_datetime(pub_date_str)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
            except (TypeError, ValueError):
                pub_date = None

        if pub_date is not None and pub_date < limite:
            continue

        texto_busca = f"{titulo} {descricao}".lower()
        if any(palavra.lower() in texto_busca for palavra in palavras_chave if palavra):
            encontrados.append({"titulo": titulo, "link": link, "data": pub_date})

    return encontrados


def montar_palavras_chave(config):
    """Monta a lista de nomes usados pra filtrar o RSS: nomes dos estados/capitais
    brasileiros + nomes dos países/cidades da Europa (extraídos das chaves do config)."""
    nomes_uf = {
        "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
        "BA": "Bahia", "CE": "Ceará", "DF": "Brasília", "ES": "Espírito Santo",
        "GO": "Goiânia", "MA": "Maranhão", "MT": "Cuiabá", "MS": "Campo Grande",
        "MG": "Belo Horizonte", "PA": "Belém", "PB": "João Pessoa", "PR": "Curitiba",
        "PE": "Recife", "PI": "Teresina", "RN": "Natal", "RS": "Porto Alegre",
        "RO": "Porto Velho", "RR": "Boa Vista", "SC": "Florianópolis",
        "SP": "São Paulo", "SE": "Aracaju", "TO": "Palmas",
    }
    palavras = [nomes_uf.get(uf, "") for uf in config["destinos_brasil"]]
    for chave_destino in config["destinos_europa"]:
        partes = chave_destino.split("_")
        palavras.extend(partes)  # inclui país e cidade (ex: "Portugal" e "Lisboa")
    return [p for p in palavras if p]


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


def montar_link_oferta(oferta):
    """Monta o link de busca no Aviasales. Prioriza o campo 'link' se a API
    devolver (mais curto/direto), senão monta manualmente com o formato
    oficial de busca pré-preenchida, usando origem/destino/data que já temos."""
    if oferta is None:
        return None

    if oferta.get("link"):
        return f"https://www.aviasales.com/search/{oferta['link']}"

    origem = oferta.get("origem")
    destino = oferta.get("destino")
    data_ida = oferta.get("departure_at")
    if not origem or not destino or not data_ida:
        return None

    data_ida_fmt = data_ida[:10]
    params = f"origin_iata={origem}&destination_iata={destino}&depart_date={data_ida_fmt}"

    data_volta = oferta.get("return_at")
    if data_volta:
        params += f"&return_date={data_volta[:10]}&one_way=false"
    else:
        params += "&one_way=true"

    params += "&adults=1&children=0&infants=0&trip_class=0&locale=pt"
    return f"https://search.aviasales.com/flights/?{params}"


def montar_html(resultados, alertas, promocoes):
    linhas = []
    for r in resultados:
        destaque = ' style="color:#0a7d2c;font-weight:bold;"' if r["alerta"] else ""
        preco_fmt = f"R$ {r['preco']:.0f}" if r["preco"] is not None else "sem dados"
        data_viagem = formatar_data_viagem(r.get("oferta"))
        origem_fmt = r["oferta"]["origem"] if r.get("oferta") else "-"
        link = montar_link_oferta(r.get("oferta"))
        link_fmt = f'<a href="{link}">ver oferta</a>' if link else "-"
        linhas.append(
            f"<tr><td>{r['nome']}</td><td{destaque}>{preco_fmt}</td>"
            f"<td>{origem_fmt}</td><td>{data_viagem}</td><td>{link_fmt}</td><td>{r['motivo'] or '-'}</td></tr>"
        )

    tabela = "\n".join(linhas)
    resumo_alerta = (
        f"<p><strong>{len(alertas)} oportunidade(s) encontrada(s) hoje.</strong></p>"
        if alertas
        else "<p>Nenhuma queda relevante hoje, segue o resumo do dia.</p>"
    )

    secao_promocoes = ""
    if promocoes:
        itens_promo = "\n".join(
            f'<li><a href="{p["link"]}">{p["titulo"]}</a></li>' for p in promocoes
        )
        secao_promocoes = f"""
        <h3>Promoções recentes do Melhores Destinos pros seus destinos</h3>
        <ul>{itens_promo}</ul>
        """

    return f"""
    <html><body>
    <h2>Buscador de passagens - resumo do dia</h2>
    {resumo_alerta}
    <table border="1" cellpadding="6" cellspacing="0">
      <tr><th>Destino</th><th>Menor preço encontrado</th><th>Saindo de</th><th>Data da viagem</th><th>Link</th><th>Motivo do alerta</th></tr>
      {tabela}
    </table>
    {secao_promocoes}
    <p style="color:#888;font-size:12px;">
      Preços via Travelpayouts/Aviasales (dados em cache de buscas recentes de usuários,
      podem ter até alguns dias) - confirme sempre no site da companhia antes de comprar.
      A data mostrada é a que estava disponível na oferta mais barata encontrada, não
      necessariamente a data mais barata possível para a rota. Promoções do Melhores
      Destinos vêm do feed RSS público deles, não da nossa busca de preços.
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

    palavras_chave = montar_palavras_chave(config)
    horas_recentes = config.get("melhoresdestinos", {}).get("horas_recentes", 48)
    promocoes = (
        buscar_promocoes_melhoresdestinos(palavras_chave, horas_recentes)
        if config.get("melhoresdestinos", {}).get("ativado", True)
        else []
    )

    print(
        f"Destinos checados hoje: {len(destinos_hoje)} | Alertas: {len(alertas)} | "
        f"Promoções encontradas no RSS: {len(promocoes)}"
    )

    deve_enviar = bool(alertas) or bool(promocoes) or config["alertas"]["sempre_enviar_resumo"]
    if deve_enviar:
        total_novidades = len(alertas) + len(promocoes)
        assunto = (
            f"✈️ {total_novidades} oportunidade(s) de passagem hoje!"
            if total_novidades
            else "Resumo diário do buscador de passagens"
        )
        html = montar_html(resultados, alertas, promocoes)
        enviar_email(assunto, html)
        print("E-mail enviado.")
    else:
        print("Nenhum alerta e resumo diário desativado - e-mail não enviado.")


if __name__ == "__main__":
    main()
