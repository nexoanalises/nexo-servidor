from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import random
import re
import string
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import json
import requests
from groq import Groq

app = Flask(__name__)

# ─── PORTEIRO DA ROTA DE ANÁLISE ────────────────────────────────────────────────
# A /analisar não exige licença no modo demo (o app publicado não manda token), então
# sem isto ela é um proxy de LLM aberto: dá pra queimar a chave da Groq em loop ou
# mandar payload de megabytes. Custo zero, sem dependência nova e sem tocar no app.
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024      # 256 KB — análise real não passa de ~10 KB
ANALISES_POR_HORA = 20                              # lojista real faz 1 ou 2 por mês
_chamadas = {}                                      # ip -> [timestamps]

def _ip_do_pedido():
    encaminhado = request.headers.get("X-Forwarded-For", "")
    return (encaminhado.split(",")[0].strip() if encaminhado else request.remote_addr) or "?"

def _passou_do_limite(ip):
    agora = datetime.now().timestamp()
    recentes = [t for t in _chamadas.get(ip, []) if agora - t < 3600]
    if len(_chamadas) > 5000:                       # não deixa o dicionário crescer sem fim
        _chamadas.clear()
    _chamadas[ip] = recentes + [agora]
    return len(recentes) >= ANALISES_POR_HORA

# ─── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL", "contato@nexosoft.com.br")
BREVO_API_KEY  = os.environ.get("BREVO_API_KEY")
SPREADSHEET_ID = "1Z-uW3AVXComh-3DGvdRiAASQL567oOf1DThJwNXt3Sc"
SHEET_NAME     = "Página1"
WHATSAPP       = "(21) 92006-9321"
DOWNLOAD_COMPLETO = "https://drive.google.com/file/d/1UNAF_QAu1otB88bGLmjhWhxnTyBd5IrH/view?usp=sharing"
FORM_AVALIACAO    = "https://docs.google.com/forms/d/e/1FAIpQLScdGr_TGwC4ith2tyRu1S7NyprrTLZm7cYlRPtOzbx7A92xXw/viewform"

# Credenciais Google — lidas do ambiente (Railway/Render) ou arquivo local
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# Chave da Groq — fica SOMENTE no servidor, nunca no app do cliente
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Segredo compartilhado entre o app e o servidor (opcional, dificulta abuso da rota /analisar)
APP_TOKEN = os.environ.get("APP_TOKEN", "")

# Modelo da análise. O app nunca manda este campo — existe para comparar modelos
# com os MESMOS dados antes de trocar o padrão, em vez de decidir por benchmark
# de terceiro. Allowlist: request não escolhe modelo caro fora desta lista.
MODELO_PADRAO = os.environ.get("GROQ_MODELO", "llama-3.3-70b-versatile")
MODELOS_PERMITIDOS = {
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
}

PLANOS = {
    "97":  ("lancamento",  0,  "forever"),
    "47":  ("mensal",      1,  "months"),
    "297": ("anual",       12, "months"),
    "697": ("definitivo",  0,  "forever"),
}

# ─── FUNÇÕES ────────────────────────────────────────────────────────────────────

def conectar_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if CREDENTIALS_JSON:
        info = json.loads(CREDENTIALS_JSON)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("nexo_credentials.json", scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

def gerar_chave():
    chars = string.ascii_uppercase + string.digits
    return "NEXO-" + "".join(random.choices(chars, k=4)) + "-" + "".join(random.choices(chars, k=4))

def calcular_expiracao(plano_valor):
    _, quantidade, unidade = PLANOS.get(plano_valor, ("mensal", 1, "months"))
    if unidade == "forever":
        return "definitivo"
    return (datetime.now() + relativedelta(months=quantidade)).strftime("%Y-%m-%d")

def registrar_chave(chave, plano_nome, expiracao, cliente, email_cliente):
    ws = conectar_sheets()
    ws.append_row([
        chave,
        plano_nome,
        expiracao,
        "sim",
        cliente,
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        email_cliente
    ], table_range="A1:G1")

def enviar_email(email_cliente, nome_cliente, chave, plano_nome, expiracao):
    expiracao_texto = "Vitalícia" if expiracao == "definitivo" else f"Válida até {expiracao}"

    corpo = f"""
Olá, {nome_cliente}!

Obrigado pela sua compra. Sua chave de ativação do NEXO Análise está pronta:

━━━━━━━━━━━━━━━━━━━━━━━━
🔑 CHAVE: {chave}
📋 Plano: {plano_nome}
📅 Validade: {expiracao_texto}
━━━━━━━━━━━━━━━━━━━━━━━━

📥 Baixe o NEXO Análise aqui: {DOWNLOAD_COMPLETO}

Como instalar e ativar:
1. Baixe e extraia o arquivo .zip
2. Execute o "Instalar_Nexo_Completo"
3. Abra o NEXO Análise pelo atalho criado na área de trabalho
4. Na tela de ativação, digite a chave acima
5. Clique em "Ativar"
6. Pronto! O NEXO Análise estará liberado.

É normal o Windows mostrar um aviso azul na primeira vez. Ele aparece com programas recém-lançados, até o Windows reconhecê-los — não é vírus nem indica problema. Quando surgir "O Windows protegeu o seu PC", clique em "Mais informações" e depois em "Executar assim mesmo". Pronto, o NEXO abre normalmente.

Qualquer dúvida, é só escrever pra contato@nexosoft.com.br — eu leio e respondo cada mensagem.

Quando você rodar suas primeiras análises, conta pra gente como foi (leva 1 minuto): {FORM_AVALIACAO}

Boas análises!
Ricardo — NEXO Análise
contato@nexosoft.com.br
"""

    resposta = requests.post(
        "https://api.brevo.com/v3/smtp/email",
        headers={
            "accept": "application/json",
            "api-key": BREVO_API_KEY,
            "content-type": "application/json",
        },
        json={
            "sender": {"name": "Ricardo — NEXO Análise", "email": SENDER_EMAIL},
            "to": [{"email": email_cliente, "name": nome_cliente}],
            "subject": "✅ Sua chave de ativação do NEXO Análise chegou!",
            "textContent": corpo,
        },
        timeout=15,
    )
    resposta.raise_for_status()

# ─── ANÁLISE (IA) ─────────────────────────────────────────────────────────────────

def validar_licenca_chave(chave):
    """Confere na planilha se a chave existe, está ativa e não expirou."""
    try:
        ws = conectar_sheets()
        for row in ws.get_all_records():
            if str(row.get("chave", "")).strip().upper() == chave.strip().upper():
                if str(row.get("ativo", "")).strip().lower() != "sim":
                    return False
                exp = str(row.get("expiracao", "")).strip().lower()
                if exp and exp != "definitivo":
                    try:
                        if datetime.now() > datetime.strptime(exp, "%Y-%m-%d"):
                            return False
                    except ValueError:
                        return False
                return True
        return False
    except Exception as e:
        print(f"ERRO ao validar licença: {e}")
        return False

# ─── MOTOR DE ESTRATÉGIA NEXO (v1) ───────────────────────────────────────────────
# O LLM não faz conta: os números-pivô (margem, atingimento de meta, variações vs
# análise anterior) são calculados AQUI, em Python, e entram no prompt como fatos.
# Campo que não dá pra interpretar com segurança vira "não calculável" — nunca chute.
# As bandeiras do Radar numérico também nascem de regra, não de opinião do modelo.

def _num_br(texto):
    """Extrai UM número de texto livre BR ('R$ 38.500', '28%', '40 mil', '-R$ 2.000').
    Retorna float, ou None se não houver número único e inequívoco."""
    if not texto:
        return None
    t = texto.strip().lower()
    achados = re.findall(r"\d[\d.,]*", t)
    if len(achados) != 1:
        return None  # nenhum número, ou mais de um (faixa, soma) = ambíguo
    s = achados[0].rstrip(".,")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")  # ponto de milhar (38.500 / 1.234.567)
    try:
        v = float(s)
    except ValueError:
        return None
    # "mil" como PALAVRA. Sem o \b, "fa-mil-iar" e "si-mil-ar" multiplicavam por 1000:
    # "R$ 900 (familiar)" virava R$ 900.000, em silêncio.
    if re.search(r"\bmil\b", t) and v < 1000:
        v *= 1000
    # Sinal negativo só quando o marcador está COLADO no número, ou quando o prejuízo
    # é afirmado. "R$ 5.000 (sem prejuízo este mês)" é lucro, não perda.
    prejuizo_negado = re.search(r"\b(sem|nenhum|zero|nada de|não teve|nao teve)\s+(preju[íi]zo)", t)
    prejuizo_afirmado = re.search(r"\bpreju[íi]zo\b", t) and not prejuizo_negado
    if re.search(r"(^|\s)-\s*r?\$?\s*\d", t) or prejuizo_afirmado:
        v = -abs(v)
    return v

# Rótulos como o lojista os vê na tela — para o aviso falar a língua dele.
ROTULOS_CAMPOS = {
    "faturamento": "Faturamento do período", "meta": "Meta de faturamento",
    "custos": "Investimento/Custos do período", "lucro": "Lucro líquido",
    "ticket_medio": "Ticket médio", "clientes": "Número de clientes atendidos",
    "conversao": "Taxa de conversão", "capacidade": "Capacidade operacional ocupada",
}
CAMPOS_CRITICOS = ("faturamento", "meta", "custos", "lucro", "ticket_medio")

def _campos_do_bloco(bloco):
    """Primeira ocorrência VENCE. Antes vencia a última, e uma linha 'lucro: 1'
    digitada dentro das Observações sobrescrevia o lucro real do formulário —
    em silêncio. Devolve também as chaves repetidas, para o aviso ao cliente."""
    campos, repetidos = {}, []
    for linha in bloco.splitlines():
        if ":" in linha:
            k, _, v = linha.partition(":")
            k = k.strip().lower()
            if not re.fullmatch(r"[a-z_]+", k):
                continue  # "Dos R$ 57.100 de custos" não é nome de campo
            if k in campos:
                if k in CAMPOS_CRITICOS and k not in repetidos:
                    repetidos.append(k)
                continue
            campos[k] = v.strip()
    return campos, repetidos

def _fmt_br(v, dec=1):
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-2] if s.endswith(",0") else s

def calcular_motor(dados):
    """Retorna (indicadores, radar): listas de linhas calculadas dos dados.
    Listas vazias se nada foi parseável — o prompt então cai no modo antigo."""
    if "=== DADOS ATUAIS ===" in dados:
        atual_txt = dados.split("=== DADOS ATUAIS ===", 1)[1]
    else:
        atual_txt = dados
    ant_txt = ""
    if "DADOS DAQUELA ANÁLISE:" in dados:
        ant_txt = dados.split("DADOS DAQUELA ANÁLISE:", 1)[1]
        for corte in ("DECISÕES RECOMENDADAS", "=== ANÁLISE ANTERIOR 2", "=== DADOS ATUAIS"):
            if corte in ant_txt:
                ant_txt = ant_txt.split(corte, 1)[0]
    atual_bruto, repetidos = _campos_do_bloco(atual_txt)
    atual = {k: _num_br(v) for k, v in atual_bruto.items()}
    ant = {k: _num_br(v) for k, v in _campos_do_bloco(ant_txt)[0].items()} if ant_txt else {}

    indicadores, radar = [], []

    # AVISO EM VEZ DE CHUTE: campo crítico preenchido que o Motor não conseguiu ler
    # vira linha visível no PDF, com o que o cliente escreveu e como corrigir.
    # Silêncio aqui já custou análise errada entregue como se fosse certa.
    for chave in CAMPOS_CRITICOS:
        escrito = atual_bruto.get(chave, "").strip()
        if escrito and atual.get(chave) is None:
            rotulo = ROTULOS_CAMPOS.get(chave, chave)
            radar.append(
                f"🟡 Não consegui ler o campo \"{rotulo}\" com segurança — você escreveu "
                f"\"{escrito[:60]}\". Escreva só o número (ex.: 38500). "
                f"Esta análise saiu sem os cálculos que dependem desse campo (leitura)")
    for chave in repetidos:
        rotulo = ROTULOS_CAMPOS.get(chave, chave)
        radar.append(
            f"🟡 O campo \"{rotulo}\" apareceu mais de uma vez nos dados. Usei o valor do "
            f"formulário. Se você escreveu esse valor de novo dentro das Observações ou dos "
            f"Desafios, ele foi ignorado (leitura)")
    fat = atual.get("faturamento")
    meta = atual.get("meta")
    custos = atual.get("custos")
    lucro = atual.get("lucro")

    if fat and fat > 0 and lucro is not None:
        margem = lucro / fat * 100
        indicadores.append(f"Margem líquida: {_fmt_br(margem)}% (lucro R$ {_fmt_br(lucro)} / faturamento R$ {_fmt_br(fat)})")
        band = "🔴" if margem < 0 else ("🟡" if margem < 10 else "🟢")
        rotulo = "prejuízo" if margem < 0 else ("margem apertada" if margem < 10 else "margem saudável")
        radar.append(f"{band} Margem líquida: {_fmt_br(margem)}% ({rotulo})")
    if fat and fat > 0 and meta and meta > 0:
        ating = fat / meta * 100
        indicadores.append(f"Atingimento da meta: {_fmt_br(ating)}% (faturou R$ {_fmt_br(fat)} de uma meta de R$ {_fmt_br(meta)})")
        band = "🟢" if ating >= 95 else ("🟡" if ating >= 70 else "🔴")
        radar.append(f"{band} Meta do período: {_fmt_br(ating)}% atingida")
    if fat and fat > 0 and custos and custos > 0:
        peso = custos / fat * 100
        indicadores.append(f"Custos sobre faturamento: {_fmt_br(peso)}%")
        if lucro is not None:
            dif = (fat - custos) - lucro
            if abs(dif) > 0.15 * fat:
                radar.append(f"🟡 Números não fecham: faturamento menos custos dá R$ {_fmt_br(fat - custos)}, "
                             f"mas o lucro informado é R$ {_fmt_br(lucro)} — vale conferir os lançamentos")
    # Para onde o dinheiro foi: custo crescendo mais rápido que faturamento é a explicação
    # aritmética do "faturei mais e não sobrou". Calculado aqui, em Python, porque é a
    # informação que o dono procura — não pode depender de o modelo reparar nela.
    fat_ant, custos_ant = ant.get("faturamento"), ant.get("custos")
    if fat and fat > 0 and custos and custos > 0 and fat_ant and fat_ant > 0 and custos_ant and custos_ant > 0:
        peso_ant = custos_ant / fat_ant * 100
        peso_atual = custos / fat * 100
        d_fat = (fat - fat_ant) / fat_ant * 100
        d_cus = (custos - custos_ant) / custos_ant * 100
        # Sanidade: campo mal preenchido gera percentual absurdo, e o prompt manda
        # reproduzir a linha como fato. Fora da faixa, o Motor cala em vez de mentir.
        if max(peso_ant, peso_atual) <= 300 and max(abs(d_fat), abs(d_cus)) <= 300:
            indicadores.append(
                f"Custos sobre faturamento: eram {_fmt_br(peso_ant)}% do faturamento e agora são "
                f"{_fmt_br(peso_atual)}% (custos {'+' if d_cus >= 0 else ''}{_fmt_br(d_cus)}%, "
                f"faturamento {'+' if d_fat >= 0 else ''}{_fmt_br(d_fat)}%)")
            # O que importa não é o custo ter subido — é ele ter passado a comer uma
            # fatia MAIOR de cada real vendido. Folga de 3 pontos contra ruído.
            if peso_atual > peso_ant + 3:
                lucro_ant = ant.get("lucro")
                if lucro is not None and lucro_ant is not None:
                    if lucro < lucro_ant:
                        fecho = "e o lucro caiu"
                    elif lucro > lucro_ant:
                        fecho = "o lucro subiu, mas cada real vendido está deixando menos"
                    else:
                        fecho = "e o lucro ficou parado no mesmo lugar"
                else:
                    fecho = "cada real vendido está deixando menos no bolso"
                radar.append(
                    f"🔴 Os custos passaram a comer uma fatia maior do seu faturamento: "
                    f"de {_fmt_br(peso_ant)}% para {_fmt_br(peso_atual)}% — {fecho}")

    for chave, nome in (("faturamento", "Faturamento"), ("lucro", "Lucro"), ("ticket_medio", "Ticket médio")):
        a, b = atual.get(chave), ant.get(chave)
        if a is not None and b:
            delta = (a - b) / abs(b) * 100
            indicadores.append(f"{nome}: {'+' if delta >= 0 else ''}{_fmt_br(delta)}% vs análise anterior "
                               f"(de R$ {_fmt_br(b)} para R$ {_fmt_br(a)})")
            if chave == "faturamento":
                band = "🟢" if delta > 0 else ("🟡" if delta >= -5 else "🔴")
                radar.append(f"{band} Faturamento vs análise anterior: {'+' if delta >= 0 else ''}{_fmt_br(delta)}%")
    return indicadores, radar

def _normalizar_saida(texto):
    """Higiene determinística da resposta do modelo: o que dá pra garantir em Python
    não fica dependendo de o modelo obedecer. Vale pra qualquer modelo."""
    if not texto:
        return ""
    t = texto.replace("**", "").replace("###", "").replace("##", "")
    t = re.sub(r"^[ \t]*[-–—]{3,}[ \t]*$", "", t, flags=re.M)   # linhas de régua markdown
    t = re.sub(r"(\d)[ \t]+%", r"\1%", t)                       # "8,5 %" -> "8,5%"
    # "R$ 18 000" e "R$ 1 234 567" -> ponto de milhar brasileiro, em todos os grupos.
    # Só dentro da mesma linha, para não colar o valor de uma linha no texto da outra.
    t = re.sub(r"(R\$[ \t]*\d{1,3}(?:[ \t]\d{3})+)",
               lambda m: re.sub(r"[ \t](\d{3})", r".\1", m.group(1)), t)
    t = re.sub(r"[ \t]+$", "", t, flags=re.M)                   # espaços no fim da linha
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def gerar_analise(dados, segmento, modelo=None):
    modos = {
        "Loja / Varejo e Moda": "🟢 MODO GIRO — foco em estoque, giro de produtos, preço, promoção e vendas rápidas.",
        "Perfumaria e Cosméticos": "🟢 MODO GIRO — foco em giro de produtos, validade, margem por categoria, preço e promoção.",
        "Pet Shop": "🟢 MODO GIRO — foco em giro de produtos, ocupação da agenda de serviços e recorrência de clientes.",
        "Celular e Acessórios": "🟢 MODO GIRO — foco em giro rápido (estoque desvaloriza), mix venda × assistência e proteção de margem.",
        "Loja Multicanal (física + online)": "🟢 MODO GIRO — foco em comparar canais: onde está o lucro real depois de taxas e frete, e onde reforçar.",
        # Segmentos legados (#040): apps antigos em campo ainda enviam estes nomes.
        "Farmácia": "🟢 MODO GIRO — foco em estoque, giro de produtos, preço, promoção e vendas rápidas.",
        "Restaurante / Alimentação": "🍽️ MODO FLUXO — foco em tempo de atendimento, ticket médio, eficiência operacional, cardápio e desperdício.",
        "Academia / Fitness": "🏋️ MODO RETENÇÃO — foco em retenção de clientes, cancelamentos, recorrência, engajamento e reativação.",
    }
    modo = modos.get(segmento, "")
    tem_historico = "=== ANÁLISE ANTERIOR" in dados
    indicadores, radar = calcular_motor(dados)

    # Formato de saída montado aqui (determinístico): Radar abre quando o Motor
    # calculou bandeiras; senão cai no Diagnóstico textual. A seção de evolução só
    # existe quando o app mandou análises anteriores junto com os dados.
    if radar:
        secoes = [
            "📌 1. RADAR DO NEGÓCIO\n"
            "Abra com as linhas do bloco RADAR CALCULADO, EXATAMENTE como fornecidas (não altere bandeiras nem números, "
            "não crie bandeiras numéricas novas). Depois, se os dados sustentarem, acrescente no máximo 2 linhas "
            "qualitativas de radar (🔴/🟡/🟢) sobre pontos NÃO numéricos, terminando cada uma com '(leitura)'. "
            "Feche com 2 linhas de síntese direta da saúde do negócio."
        ]
    else:
        secoes = [
            "📌 1. DIAGNÓSTICO GERAL\n"
            "A saúde real do negócio em 2 a 4 linhas diretas: se está saudável, em risco ou em crise, "
            "citando os números que provam (margem, faturamento vs meta). Sem suavizar e sem dramatizar."
        ]
    num = 2
    if tem_historico:
        secoes.append(
            f"🔄 {num}. EVOLUÇÃO DESDE A ÚLTIMA ANÁLISE\n"
            "Compare os números atuais com os da análise anterior: o que melhorou, o que piorou e o que ficou igual — "
            "sempre com os números lado a lado (use os INDICADORES CALCULADOS quando existirem). "
            "Se a análise anterior tiver seção de METAS, confira meta a meta: cumprida, parcial ou não cumprida — "
            "só quando os campos atuais permitirem conferir; se não permitirem, diga 'não informado desta vez'. "
            "OBRIGATÓRIO citar também O QUE MELHOROU (clientes atendidos, conversão, ticket médio, canal que cresceu) — "
            "o dono precisa saber o que está funcionando para não desmontar justamente isso. "
            "Se um problema aparecer repetido em análises seguidas, nomeie a reincidência "
            "(ex.: 'é a 2ª análise seguida com ruptura do produto campeão'). "
            "Se uma decisão recomendada aparentemente não foi executada, diga com franqueza e mostre o custo de "
            "continuar adiando. Se foi executada e deu resultado, reconheça com números."
        )
        num += 1
    secoes.append(f"🎯 {num}. DECISÃO MAIS IMPORTANTE AGORA\nUma única decisão crítica e direta."); num += 1
    secoes.append(
        f"🔧 {num}. AÇÕES IMEDIATAS\n"
        "No máximo 3 ações práticas, executáveis e simples, compatíveis com a verba e o tempo informados. "
        "Cada ação obedece à REGRA DA ALAVANCA NOMEADA: alavanca + alvo + direção, com número. "
        "Se os dados citam DEFEITO ou ATRASO de fornecedor, uma das ações é ACIONAR esse fornecedor "
        "(troca, crédito ou substituição das peças, com o nome dele e a quantidade que está nos dados) — "
        "é dinheiro de volta a custo zero, e alerta passivo não recupera nada. "
        "Se há reclamação repetida de clientes sobre um produto (numeração, tamanho, defeito), "
        "trate-a como conserto barato e concreto, não como observação. "
        "Ao final de CADA ação, acrescente uma tag curta entre parênteses com o custo e o prazo de resultado, "
        "neste formato exato: (Custo: zero | Resultado em: ~7 dias). "
        "Use valores realistas em reais (ou 'zero') e prazos aproximados. Não use notas, pontuações ou percentuais de prioridade."
    ); num += 1
    secoes.append(f"⚠️ {num}. O QUE ESTÁ TE FAZENDO PERDER DINHEIRO\nProblemas claros e acionáveis identificados nos dados."); num += 1
    secoes.append(
        f"📈 {num}. OPORTUNIDADE MAIS RÁPIDA DE GANHO\n"
        "Uma ação de retorno rápido e realista. Antes de escolher, olhe o campo de vendas por canal: se um canal já "
        "responde por fatia relevante do faturamento E os dados apontam fricção nele (demora na resposta, reclamação, "
        "ausência de atendimento em algum horário), essa costuma ser a oportunidade mais barata que existe — "
        "o cliente já está lá, só está esbarrando em algo. Não repita a mesma ação da seção de decisão."
    ); num += 1
    secoes.append(
        f"🚨 {num}. ALERTAS\n"
        "Até 3 riscos latentes que ainda não exigem ação imediata, mas merecem atenção. "
        "Antes de escrever esta seção, VARRA os campos de reclamações, trocas/defeitos, fornecedores (atrasos e "
        "defeitos recorrentes — cite o nome do fornecedor quando informado), dependência de um único canal de vendas "
        "e tendência de queda em qualquer número. Defeito ou atraso de fornecedor citado nos dados é SEMPRE alerta. "
        "Somente se realmente não houver nenhum risco nos dados, escreva apenas: Nenhum alerta crítico neste período."
    ); num += 1
    secoes.append(
        f"🧭 {num}. METAS ATÉ A PRÓXIMA ANÁLISE\n"
        "2 a 3 metas específicas, cada uma com número-alvo, VERIFICÁVEIS pelos próprios campos do formulário na "
        "próxima análise (ex.: 'Ticket médio: de R$ 85 para R$ 92', 'Zerar o estoque de casacos de inverno'). "
        "Devem derivar das ações recomendadas acima. Nada de metas impossíveis de conferir "
        "(ex.: 'melhorar o atendimento' não vale). "
        "Feche com uma frase curta convidando a rodar a próxima análise no fim do período para conferir as metas."
    )
    formato = "\n\n".join(secoes)

    instrucao_historico = ""
    if tem_historico:
        instrucao_historico = (
            "HISTÓRICO: os dados contêm blocos '=== ANÁLISE ANTERIOR ===' com dados e decisões de análises passadas "
            "DESTE MESMO negócio, geradas pelo próprio NEXO em períodos anteriores. Use esses blocos SOMENTE para "
            "avaliar a evolução (o que melhorou, o que piorou, metas cumpridas ou não, problemas reincidentes). "
            "As decisões novas devem se basear nos dados do bloco '=== DADOS ATUAIS ==='.\n\n"
        )

    bloco_motor = ""
    if indicadores or radar:
        bloco_motor = "INDICADORES CALCULADOS (cálculo exato do Motor NEXO — use estes números, NÃO recalcule):\n"
        bloco_motor += "".join(f"- {i}\n" for i in indicadores)
        if radar:
            bloco_motor += "\nRADAR CALCULADO (reproduza na seção 1 exatamente como está):\n"
            bloco_motor += "".join(f"{r}\n" for r in radar)
        bloco_motor += "\n"

    modelo_usado = modelo if isinstance(modelo, str) and modelo in MODELOS_PERMITIDOS else MODELO_PADRAO
    resposta = groq_client.chat.completions.create(
        model=modelo_usado,
        messages=[{
            "role": "user",
            "content": (
                f"Você é o NEXO Análise. Slogan: Transformando dados em decisões.\n\n"
                f"Sua função é transformar informações de negócios em decisões práticas, claras e executáveis. "
                f"Você NÃO cria relatórios. Você NÃO cria análises teóricas. Você NÃO terceiriza decisões. "
                f"Você entrega apenas decisões acionáveis de alto impacto.\n\n"
                f"REGRAS INEGOCIÁVEIS:\n"
                f"- Proibido qualquer conteúdo de Recursos Humanos (RH).\n"
                f"- Proibido sugerir consultorias, agências ou consultores externos. O NEXO É o consultor do cliente.\n"
                f"- Proibido respostas teóricas sem ação prática.\n"
                f"- Proibido ignorar a verba disponível.\n"
                f"- Proibido ignorar o tempo disponível.\n"
                f"- Proibido recomendações impossíveis de executar pelo próprio dono.\n"
                f"- Sempre priorize simplicidade e execução imediata.\n"
                f"- Sempre use linguagem direta e de ação — e TODO verbo carrega alvo e número: "
                f"'reduza o estoque de blazer em 50%', nunca 'otimize o estoque'. "
                f"Evite: 'seria interessante', 'recomenda-se avaliar', 'pode-se considerar', 'otimizar', 'melhorar', 'trabalhar melhor'.\n\n"
                f"PRINCÍPIO CENTRAL: a qualidade da decisão depende diretamente da qualidade das informações fornecidas. "
                f"Use TODOS os dados do negócio informados abaixo — cada número e detalhe ajuda a calibrar a decisão.\n\n"
                f"{instrucao_historico}"
                f"MODO DE DECISÃO DESTE NEGÓCIO: {modo}\n\n"
                f"📅 HOJE É {datetime.now().strftime('%d/%m/%Y')}. Todo prazo que você propuser tem de ser FUTURO "
                f"em relação a esta data — o período analisado já terminou, e prazo no passado invalida a ação.\n\n"

                f"⚖️ NÃO CONTRADIGA O MOTOR, E NÃO INVENTE RÓTULO CONCORRENTE: o resultado do negócio já vem "
                f"decidido nas linhas calculadas. Se a margem calculada é positiva, HOUVE LUCRO — nunca escreva "
                f"'prejuízo' nem 'lucro negativo'. Use o mesmo rótulo que o Radar usou ('margem apertada', "
                f"'margem saudável', 'prejuízo'); não crie um julgamento paralelo que brigue com ele. "
                f"Também não afirme que o lucro caiu, subiu ou ficou igual sem que os números calculados digam isso. "
                f"Contradizer o Motor invalida a resposta.\n\n"

                f"📄 FORMATAÇÃO — a saída vai direto para um PDF que não interpreta markdown:\n"
                f"- Escreva em TEXTO PURO. Proibido '**', '###', '---', '```', tabelas e qualquer marcação.\n"
                f"- Cada título de seção começa pelo emoji e pelo número, exatamente como no formato pedido, "
                f"e a linha do título não leva nenhum outro caractere de marcação.\n"
                f"- Números no padrão brasileiro: R$ 18.000 (ponto no milhar), 8,5% (vírgula decimal, "
                f"sem espaço antes do %). Nunca 'R$ 18 000' nem '8,5 %'.\n"
                f"- Escreva tudo em português do Brasil; nenhuma palavra em outro idioma.\n\n"

                f"🚫 PROIBIDO INVENTAR NÚMERO (regra que vence todas as outras):\n"
                f"Existem dois tipos de número, e eles não se misturam:\n"
                f"- NÚMERO-FATO (afirma algo sobre o negócio): só pode sair de duas fontes — um valor que aparece "
                f"literalmente nos DADOS DO NEGÓCIO, ou uma linha de INDICADORES/RADAR CALCULADO. "
                f"É PROIBIDO calcular percentuais, taxas, somas, divisões, quanto se 'recupera em caixa' ou "
                f"valores de período anterior que não estejam escritos. Se o número não existe nessas duas fontes, "
                f"escreva a frase SEM número — descrever bem vale mais que calcular errado.\n"
                f"- NÚMERO-META (o alvo que VOCÊ está propondo, ex.: 'liquidar a -40%', 'reduzir em 30%'): "
                f"esse você escolhe, e ele é bem-vindo. Nunca apresente número-meta como se fosse resultado apurado.\n"
                f"Nunca atribua a um fornecedor, canal ou produto uma taxa ou percentual que não esteja nos dados.\n"
                f"ATENÇÃO — esta regra NÃO manda omitir informação: repetir uma quantidade que já está escrita nos dados "
                f"('3 blusas com defeito do fornecedor X') é citar, não é calcular, e continua OBRIGATÓRIO. "
                f"Na dúvida, cite o fato sem transformá-lo em percentual.\n\n"

                f"🔑 REGRA DA ALAVANCA NOMEADA (a mais importante depois daquela):\n"
                f"Toda decisão e toda ação nomeia A ALAVANCA, O ALVO e A DIREÇÃO, com número-meta quando fizer sentido "
                f"(respeitando a regra acima: nunca invente número-fato para justificar a ação). "
                f"Quem lê é um lojista ocupado que vai executar o que ENTENDEU, não o que você quis dizer — "
                f"palavra que ele possa resolver de duas formas diferentes é decisão perdida.\n"
                f"- PROIBIDO: 'fazer promoções', 'ajustar os preços', 'otimizar o estoque', 'melhorar o atendimento', "
                f"'revisar os processos', ou qualquer ordem sem alvo nomeado.\n"
                f"- OBRIGATÓRIO no lugar: 'liquidar o blazer de alfaiataria e a saia longa jeans a -40% nos próximos 15 dias', "
                f"'subir o preço do vestido midi em 8%', 'responder o WhatsApp até as 20h no sábado'.\n"
                f"- Ao falar de estoque encalhado, nomeie o item E o tamanho/variação encalhada quando os dados trouxerem "
                f"(ex.: 'GG e XG'). É o tamanho que corrige a PRÓXIMA COMPRA — sem ele o dono repete o erro.\n"
                f"- PROIBIDA QUALQUER AMBIGUIDADE: se uma frase puder ser lida de duas formas, reescreva. "
                f"Comparação sempre diz explicitamente o que é comparado com o quê "
                f"(errado: 'custos subiram 21,7% e o faturamento 13,9%, 1,6x mais rápido'; "
                f"certo: 'os custos subiram 1,6x mais rápido que o faturamento').\n\n"

                f"⚖️ AS DUAS ALAVANCAS DE PREÇO SÃO OPOSTAS — NUNCA NA MESMA FRASE:\n"
                f"- LIQUIDAR o encalhado: sacrifica margem DE PROPÓSITO para recuperar CAIXA. Só vale para item parado.\n"
                f"- REPRECIFICAR o que gira: recupera MARGEM. Só vale para item de alta saída.\n"
                f"Escrever 'faça promoção para aumentar a margem' é contradição e invalida a resposta. "
                f"Diga sempre QUAL das duas, em QUAIS itens, e O QUE ela recupera — caixa ou margem.\n\n"

                f"💰 CAPITAL PARADO — cruzamento OBRIGATÓRIO, é a explicação que o dono mais procura:\n"
                f"- Se o RADAR CALCULADO trouxer a linha 'O dinheiro ficou no custo', ela é FATO e tem de ser EXPLICADA "
                f"na seção 'o que está te fazendo perder dinheiro': diga para ONDE o dinheiro foi, cruzando com o que os "
                f"dados dizem sobre compra de estoque, coleção nova e encalhe.\n"
                f"- Se os custos do período incluem COMPRA DE ESTOQUE e os dados declaram estoque encalhado, parado ou de "
                f"coleção anterior, diga explicitamente que o lucro não desapareceu, ele VIROU ESTOQUE — com os dois valores "
                f"lado a lado (quanto foi comprado × quanto está parado).\n"
                f"- Nunca trate 'margem apertada' como causa. Margem apertada é sintoma; a causa é onde o dinheiro entrou.\n\n"

                f"🔁 NÃO RECOMENDE O QUE JÁ FOI TENTADO: varre os campos de desafios e observações antes de decidir. "
                f"Se o dono declarou ter feito algo (ex.: 'dei muito desconto'), NÃO recomende a mesma coisa. "
                f"Reconheça que já foi tentado, diga por que não resolveu e proponha uma alavanca DIFERENTE.\n\n"

                f"FORMATO OBRIGATÓRIO DE SAÍDA (use exatamente estes títulos, nesta ordem):\n\n"
                f"{formato}\n\n"
                f"PRIORIZAÇÃO INTERNA (NÃO EXIBIR AO USUÁRIO): antes de responder, avalie cada ação possível por impacto no resultado, "
                f"facilidade de execução, custo em relação à verba disponível e consumo do tempo semanal disponível. "
                f"Priorize sempre alto impacto + alta facilidade + baixo custo + baixo consumo de tempo. "
                f"Apresente ao usuário apenas as ações já priorizadas — nunca mostre pontuações, notas ou cálculos.\n\n"
                f"RESTRIÇÃO DE ORÇAMENTO: respeite estritamente o campo 'Verba destinada para melhorias'. "
                f"Se a verba for baixa, nula ou não informada, recomende apenas ações de custo zero ou muito baixo "
                f"(ajustes de processo, ações orgânicas, renegociação, organização interna, ferramentas gratuitas).\n\n"
                f"RESTRIÇÃO DE TEMPO: respeite estritamente o campo 'Tempo disponível para implementação'. "
                f"Nenhuma ação pode exigir, por semana, mais tempo do que o informado pelo cliente.\n\n"
                f"REGRA FINAL DE QUALIDADE: se a resposta não terminar com uma decisão clara e executável, a resposta é inválida.\n\n"
                f"{bloco_motor}"
                f"DADOS DO NEGÓCIO:\n{dados}"
            )
        }]
    )
    return _normalizar_saida(resposta.choices[0].message.content)

@app.route("/analisar", methods=["POST"])
def analisar():
    try:
        if groq_client is None:
            return jsonify({"status": "erro", "motivo": "Servidor sem chave de IA configurada."}), 503

        # Verificação opcional do segredo do app
        if APP_TOKEN and request.headers.get("X-App-Token", "") != APP_TOKEN:
            return jsonify({"status": "erro", "motivo": "Acesso não autorizado."}), 401

        if _passou_do_limite(_ip_do_pedido()):
            return jsonify({"status": "erro",
                            "motivo": "Muitas análises seguidas deste computador. "
                                      "Tente novamente em alguns minutos."}), 429

        body = request.json or {}
        modo     = body.get("modo", "demo")
        segmento = body.get("segmento", "")
        dados    = body.get("dados", "")
        chave    = body.get("chave", "")

        if not dados or not segmento:
            return jsonify({"status": "erro", "motivo": "Dados incompletos."}), 400

        # A versão completa exige licença válida; a demo é liberada (limitada no próprio app)
        if modo == "completo":
            if not chave or not validar_licenca_chave(chave):
                return jsonify({"status": "erro", "motivo": "Licença inválida ou expirada."}), 403

        analise = gerar_analise(dados, segmento, body.get("modelo"))
        return jsonify({"status": "ok", "analise": analise}), 200

    except Exception as e:
        # Detalhe técnico fica no log do servidor; o cliente não vê mensagem interna
        # do Python na tela (o app exibe este 'motivo' direto pro lojista).
        print(f"ERRO no /analisar: {type(e).__name__}: {e}")
        return jsonify({"status": "erro",
                        "motivo": "Não foi possível gerar a análise agora. "
                                  "Tente novamente em instantes."}), 200

# ─── WEBHOOK ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        dados = request.get_json(silent=True) or request.form.to_dict()

        # Campos que a Eduzz envia
        event_data    = dados.get("data", {}) or {}
        buyer         = event_data.get("buyer", {}) or {}
        nome_cliente  = buyer.get("name", "Cliente")
        email_cliente = buyer.get("email", "")
        valor         = str(int(float((event_data.get("price") or {}).get("value", 0))))
        status        = event_data.get("status", "")

        # Só processa vendas aprovadas
        if status not in ("paid", "approved", "3", "3.0"):
            return jsonify({"status": "ignorado", "motivo": "status não aprovado"}), 200

        if not email_cliente:
            return jsonify({"status": "erro", "motivo": "email não encontrado"}), 400

        plano_info = PLANOS.get(valor)
        if not plano_info:
            plano_info = ("mensal", 1, "months")
        plano_nome = plano_info[0]

        chave      = gerar_chave()
        expiracao  = calcular_expiracao(valor)

        registrar_chave(chave, plano_nome, expiracao, nome_cliente, email_cliente)
        enviar_email(email_cliente, nome_cliente, chave, plano_nome, expiracao)

        return jsonify({"status": "ok", "chave": chave}), 200

    except Exception as e:
        print(f"ERRO no webhook: {e}")
        return jsonify({"status": "erro", "detalhe": str(e)}), 200

# ─── OPT-IN DA LANDING (ponte → Systeme.io, API oficial) ────────────────────────
# A landing envia pra cá e o servidor cadastra o lead pela API pública do
# Systeme.io (api.systeme.io): cria/acha o contato e aplica a tag de lead.
# O fluxo de e-mails usa o gatilho "Tag adicionada" — nada de form/endpoint
# não-documentado (o opt-in interno deles quebrou sem aviso em 07/07/2026).

SYSTEME_API_URL  = "https://api.systeme.io/api"
SYSTEME_API_KEY  = os.environ.get("SYSTEME_API_KEY", "")
SYSTEME_TAG_LEAD = "biblioteca-lead"   # gatilho do fluxo "NEXO — Sequência PDF 1"
_systeme_tag_id  = None                # cache do id da tag (estável na conta)

OPTIN_ORIGENS = {
    "https://nexosoft.com.br",
    "https://www.nexosoft.com.br",
    "https://nexo-analise.netlify.app",
}


def _systeme_req(metodo, caminho, **kwargs):
    return requests.request(
        metodo, SYSTEME_API_URL + caminho,
        headers={"x-api-key": SYSTEME_API_KEY, "content-type": "application/json"},
        timeout=15, **kwargs,
    )


def _systeme_tag_lead_id():
    global _systeme_tag_id
    if _systeme_tag_id:
        return _systeme_tag_id
    r = _systeme_req("GET", "/tags", params={"limit": 100})
    r.raise_for_status()
    for tag in r.json().get("items", []):
        if tag.get("name") == SYSTEME_TAG_LEAD:
            _systeme_tag_id = tag["id"]
            return _systeme_tag_id
    r = _systeme_req("POST", "/tags", json={"name": SYSTEME_TAG_LEAD})
    r.raise_for_status()
    _systeme_tag_id = r.json()["id"]
    return _systeme_tag_id


def _systeme_contato_id(email, nome):
    r = _systeme_req("POST", "/contacts", json={
        "email": email,
        "fields": [{"slug": "first_name", "value": nome}],
    })
    if r.status_code == 422:
        # contato já existe → busca o id pelo e-mail
        r2 = _systeme_req("GET", "/contacts", params={"email": email})
        r2.raise_for_status()
        itens = r2.json().get("items", [])
        if itens:
            return itens[0]["id"]
    r.raise_for_status()
    return r.json()["id"]

def _optin_cors(resp):
    origem = request.headers.get("Origin", "")
    if origem in OPTIN_ORIGENS:
        resp.headers["Access-Control-Allow-Origin"] = origem
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

@app.route("/optin", methods=["POST", "OPTIONS"])
def optin():
    if request.method == "OPTIONS":
        return _optin_cors(app.make_response(("", 204)))
    try:
        body  = request.get_json(silent=True) or {}
        email = (body.get("email") or "").strip()
        # O form do Systeme.io exige first_name; a landing não coleta nome,
        # então cai em "Visitante" (nenhum e-mail da sequência usa o nome).
        nome  = (body.get("nome") or "").strip() or "Visitante"

        if "@" not in email or "." not in email.split("@")[-1]:
            resp = jsonify({"status": "erro", "motivo": "email inválido"})
            resp.status_code = 400
            return _optin_cors(resp)

        contato_id = _systeme_contato_id(email, nome[:80])
        r = _systeme_req("POST", f"/contacts/{contato_id}/tags",
                         json={"tagId": _systeme_tag_lead_id()})
        # tag repetida no mesmo contato não é erro (re-cadastro do mesmo lead)
        if r.status_code not in (200, 201, 204, 422):
            r.raise_for_status()
        return _optin_cors(jsonify({"status": "ok"}))

    except Exception as e:
        detalhe = ""
        resp_upstream = getattr(e, "response", None)
        if resp_upstream is not None:
            detalhe = f" [{resp_upstream.status_code}] {resp_upstream.text[:300]}"
        print(f"ERRO no /optin: {e}{detalhe}")
        resp = jsonify({"status": "erro", "motivo": "falha no cadastro"})
        resp.status_code = 502
        return _optin_cors(resp)

@app.route("/", methods=["GET"])
def home():
    return "Nexo Servidor ativo.", 200

# ─── INÍCIO ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
