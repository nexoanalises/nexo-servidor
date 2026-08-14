from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import random
import re
import string
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import os
import sys
import hmac
import uuid
import tempfile
import collections
import json
import unicodedata
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

# Segredo da rota /laboratorio. Sem esta variável a rota responde 404 e o laboratório
# é como se não existisse — nasce DESLIGADO de propósito: ele gasta a mesma cota
# diária que o cliente pagante usa, e ninguém deve poder ligá-lo sem querer.
LAB_TOKEN = os.environ.get("LAB_TOKEN", "")

# 🔭 SHADOW MODE do mecanismo decisório (#095). A espinha determinística fica LIGADA
# — custa zero token e responde relações, abstinências, limites e recall. A fase do
# MODELO nasce DESLIGADA porque consome a mesma cota diária do cliente pagante:
# `SHADOW_REDACAO=1` liga, `SHADOW_AMOSTRA` limita a fração das análises.
# 🪟 JANELA DE OBSERVAÇÃO — as últimas N observações do shadow, saneadas, em memória.
#
# ⚠️ É JANELA, NÃO REGISTRO OFICIAL. Some em restart e em deploy; se o Railway rodar
# mais de uma instância, ela vê só o que passou por este processo. Para a fase de
# shadow isso basta — banco ou Redis agora seria infraestrutura demais antes de
# sabermos se o shadow produz informação útil.
_JANELA_SHADOW = collections.deque(maxlen=60)

SHADOW_MOTOR   = os.environ.get("SHADOW_MOTOR", "1") != "0"
SHADOW_REDACAO = os.environ.get("SHADOW_REDACAO", "") == "1"

# 🔬 CAPTURA CANÔNICA — instrumento TEMPORÁRIO e BOUNDED (14/08). Desligado por padrão.
# Quando `NEXO_CAPTURA=1`, o servidor imprime no log, para CADA análise: o `usage` real
# de tokens de cada chamada à Groq e a resposta 1 completa do modelo (entre marcadores).
# É como capturamos as §6+§7 reais dos payloads canônicos Agosto/Setembro para desenhar
# a retentativa seletiva — provando, não dimensionando de cabeça.
# ⛔ NÃO muda prompt, Motor nem fluxo decisório: só imprime. E NÃO deve ficar ligado em
# produção com clientes reais — liga-se para os canônicos fictícios e desliga-se depois.
CAPTURA_CANONICA = os.environ.get("NEXO_CAPTURA", "") == "1"
# Grava em ARQUIVO, não em memória: o gunicorn roda com --workers 2 e memória é
# por-worker (a GET pegaria o worker errado). Um arquivo em /tmp é compartilhado pelos
# workers do mesmo container. Efêmero — some no redeploy, que é o que queremos.
CAPTURA_ARQUIVO = os.path.join(tempfile.gettempdir(), "nexo_captura.txt")

def _cap_arquivo(texto):
    """Append à captura em arquivo. Guardada pela env var e NUNCA derruba a análise."""
    if not CAPTURA_CANONICA:
        return
    try:
        with open(CAPTURA_ARQUIVO, "a", encoding="utf-8") as f:
            f.write(texto)
    except Exception:                                            # noqa: BLE001
        pass
try:
    SHADOW_AMOSTRA = float(os.environ.get("SHADOW_AMOSTRA", "0.25"))
except ValueError:
    SHADOW_AMOSTRA = 0.25

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
    # O "7" é o primeiro ciclo da oferta de entrada. Sem ele a venda de R$7 caía no
    # padrão do webhook e era registrada como "mensal" — chave válida, mas a planilha
    # deixava de distinguir quem entrou por R$7 de quem entrou por R$47, que é
    # exatamente a medição que a oferta existe para produzir.
    "7":   ("ativacao",    1,  "months"),
    "97":  ("lancamento",  0,  "forever"),
    "47":  ("mensal",      1,  "months"),
    "297": ("anual",       12, "months"),
    "697": ("definitivo",  0,  "forever"),
}

# Cobrança que atrasa não pode derrubar quem está em dia: a validade gravada leva
# alguns dias a mais que o ciclo pago. A folga é descontada antes de cada renovação
# (ver `validade_renovada`), senão ela se acumularia mês a mês.
FOLGA_RENOVACAO_DIAS = 5

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

def _com_folga(base, meses):
    return (base + relativedelta(months=meses) + timedelta(days=FOLGA_RENOVACAO_DIAS)).strftime("%Y-%m-%d")

def calcular_expiracao(plano_valor):
    _, quantidade, unidade = PLANOS.get(plano_valor, ("mensal", 1, "months"))
    if unidade == "forever":
        return "definitivo"
    return _com_folga(datetime.now(), quantidade)

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

# ─── RENOVAÇÃO ──────────────────────────────────────────────────────────────────
# A recorrência da Eduzz cobra o cliente todo mês e cai NESTE MESMO webhook. Sem o
# que vem abaixo, cada cobrança gerava uma chave NOVA numa linha NOVA — e a linha do
# cliente ficava parada na validade do primeiro ciclo. No dia seguinte ao vencimento
# o app apagava a licença local e mandava comprar de novo: cliente em dia, cobrança
# em dia, deslogado. Nunca apareceu porque nunca houve um pagante.
#
# O conserto é só de servidor: o app revalida contra a planilha a cada 24h e regrava
# a validade que encontrar (`nexo_analise.py:266-288`). Movendo a data da linha que
# já existe, a licença se estende sozinha e o cliente não vê nada acontecer.

def achar_linha_renovavel(valores, email_cliente):
    """(índice 1-based, linha) do registro que uma renovação deve estender.

    Renovável = mesmo e-mail · ativo · com data de validade. Varre de baixo para cima
    porque o registro que vale é o último. Vitalícia devolve "não achei" de propósito:
    não se estende o que não vence, e ninguém com vitalícia vira mensal por engano.
    """
    alvo = (email_cliente or "").strip().lower()
    if not alvo:
        return None, None
    for i in range(len(valores), 1, -1):        # para em 2: a linha 1 é o cabeçalho
        linha = valores[i - 1]
        if len(linha) < 7 or linha[6].strip().lower() != alvo:
            continue
        if linha[3].strip().lower() != "sim":
            continue
        if linha[2].strip().lower() == "definitivo":
            return None, None
        return i, linha
    return None, None

def validade_renovada(validade_atual, meses, hoje=None):
    """A data que a renovação grava na linha do cliente.

    Conta do FIM DO CICLO PAGO, não da data que está na planilha: a folga é descontada
    antes e somada de novo depois, senão ela cresceria a cada mês (5, 10, 15 dias...)
    e o dia do vencimento fugiria do dia da cobrança.

    Validade vencida — ou ilegível — renova a partir de hoje: quem pagou com atraso
    recebe o ciclo inteiro contado do pagamento, nunca menos do que comprou.
    """
    base = hoje or datetime.now()
    try:
        fim_do_ciclo = datetime.strptime(str(validade_atual).strip(), "%Y-%m-%d") - timedelta(days=FOLGA_RENOVACAO_DIAS)
        if fim_do_ciclo > base:
            base = fim_do_ciclo
    except ValueError:
        pass                                    # data que a planilha não explica: vale hoje
    return _com_folga(base, meses)

def renovar_validade(ws, indice, validade_nova):
    """Move a validade da linha existente. A CHAVE não muda — é a mesma que já está
    instalada na máquina do cliente. O PLANO também não: ele registra por onde o
    cliente ENTROU (`ativacao` = R$7), e sobrescrever apagaria a única medição que
    diz quantos R$7 viraram R$47. Quantos ciclos ele já pagou está na distância
    entre a data de registro (coluna F) e esta validade."""
    ws.update_cell(indice, 3, validade_nova)    # coluna C = expiracao

def enviar_email_renovacao(email_cliente, nome_cliente, chave, validade):
    corpo = f"""
Olá, {nome_cliente}!

Sua assinatura do NEXO Análise foi renovada.

━━━━━━━━━━━━━━━━━━━━━━━━
🔑 CHAVE: {chave} (a mesma de sempre)
📅 Válida até: {validade}
━━━━━━━━━━━━━━━━━━━━━━━━

Você não precisa fazer nada: o NEXO reconhece a renovação sozinho na próxima vez que
você abrir o app. A chave continua a mesma — não é preciso ativar de novo.

Qualquer dúvida, é só escrever pra contato@nexosoft.com.br — eu leio e respondo cada mensagem.

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
            "subject": "✅ Sua assinatura do NEXO Análise foi renovada",
            "textContent": corpo,
        },
        timeout=15,
    )
    resposta.raise_for_status()

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
    prejuizo_negado = re.search(
        r"\b(sem|nenhum|zero|nada de)\s+(nenhum\s+)?preju[íi]zo"
        r"|\b(não|nao|nunca|jamais)\s+\w*\s*(tive|teve|tivemos|houve|deu)\s*(nenhum\s+)?preju[íi]zo"
        r"|preju[íi]zo\s+(zero|nenhum|algum)", t)
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
    "proporcao_loja": "Percentual de vendas: Roupas vs Calçados", "vendas_canal": "Vendas por canal",
    "proporcao_pet": "Produtos vs Serviços", "proporcao_assistencia": "Vendas vs Assistência técnica",
    "agenda_ocupacao": "Ocupação da agenda de serviços", "funcionarios": "Número de funcionários",
    "estoque_valor": "Valor do estoque hoje",
    "preocupacao": "O que mais está te preocupando",
}
CAMPOS_CRITICOS = ("faturamento", "meta", "custos", "lucro", "ticket_medio", "estoque_valor")

# Todo campo numérico que o formulário pede é comparável entre períodos. O tipo
# manda na conta: percentual varia em PONTOS, dinheiro e quantidade variam em %.
CAMPOS_COMPARAVEIS = (
    ("faturamento",  "Faturamento",              "dinheiro"),
    ("lucro",        "Lucro",                    "dinheiro"),
    ("custos",       "Custos",                   "dinheiro"),
    ("ticket_medio", "Ticket médio",             "dinheiro"),
    ("clientes",     "Clientes atendidos",       "quantidade"),
    ("funcionarios", "Funcionários",             "quantidade"),
    ("conversao",    "Taxa de conversão",        "percentual"),
    ("capacidade",   "Capacidade ocupada",       "percentual"),
    ("fornecedores", "Fornecedores no prazo",    "percentual"),
    ("agenda_ocupacao", "Ocupação da agenda",    "percentual"),
    ("recorrentes",  "Clientes recorrentes",     "quantidade"),
    ("estoque_valor", "Valor do estoque",        "dinheiro"),
)

# SÓ estes campos são RATEIO — a soma deles tem de fechar 100%. Rodar a conferência
# em campo de texto livre acusa o cliente de erro que ele não cometeu: "dei 30% de
# desconto e girei 20% da coleção" somaria 50%. Pior, a dica do próprio app para a
# capacidade do Pet Shop ("agenda 80% ocupada, loja em 60%") nunca soma 100.
CAMPOS_RATEIO = ("proporcao_loja", "proporcao_pet", "proporcao_assistencia")

# A PREOCUPAÇÃO DECLARADA (#088) → a grandeza que o Motor já apura para ela.
# Serve para publicar o FATO ao lado da declaração — nunca para julgar se o lojista
# escolheu "certo". "Outro" não entra: sem grandeza definida, não há comparação honesta
# a fazer, e inventar uma seria arbitrar.
#
# ⚠️ O terceiro item da tupla é HERANÇA MORTA e fica documentado como tal para ninguém
# reanimá-lo: ele é desempacotado e nunca usado — a linha publica só o movimento
# ("subiu 20%"), sem palavra de valência. E depois do #102 ele estaria ERRADO para o
# estoque, que passou a significar TOTAL: queda deixou de ser melhora automática.
PREOCUPACOES = {
    "vendas":   ("faturamento",   "o faturamento",         +1),
    "lucro":    ("lucro",         "o lucro",               +1),
    "estoque":  ("estoque_valor", "o valor do estoque",    -1),
    "clientes": ("clientes",      "o número de clientes",  +1),
    # "o custo total" e não "os custos": o verbo da frase é sempre singular
    # ("subiu"/"caiu"), e "os custos subiu" ia sair no Radar do cliente.
    "custos":   ("custos",        "o custo total",         -1),
}

def _pct_do_texto(p):
    """'70,5' -> 70.5 · '1.250' -> 1250.0. Ponto só é milhar com 3 casas depois."""
    p = p.rstrip(".,")
    if "," in p:
        return float(p.replace(".", "").replace(",", "."))
    if p.count(".") == 1 and len(p.split(".")[1]) != 3:
        return float(p)            # 70.5 é decimal, não milhar
    return float(p.replace(".", ""))

# Rótulos que o lojista usa para custo que NÃO varia com a venda. O que sobra do
# custo total depois deles é mercadoria e taxa — a parte sobre a qual ele decide.
ROTULOS_CUSTO_FIXO = (
    ("aluguel", r"aluguel"), ("folha", r"folha|sal[áa]rio|funcion[áa]rio"),
    ("energia e internet", r"energia|luz|internet|[áa]gua"),
    ("contador", r"contador|contabilidade"), ("software", r"sistema|software|assinatura"),
)

def _custos_fixos(brutos):
    """Soma os custos fixos que o cliente NOMEOU COM VALOR EM REAIS no texto livre.
    Exige o marcador R$ (ou a palavra 'mil'): sem isso, 'o aluguel vai subir 10%'
    virava R$ 10 e ia para o PDF sob o selo de cálculo exato. O campo `custos` fica
    fora da varredura — é o total, e colado no fim contaminava o último rótulo."""
    texto = " ".join((brutos.get(c) or "") for c in ("observacoes", "desafios")).lower()
    total, achados = 0.0, []
    for rotulo, padrao in ROTULOS_CUSTO_FIXO:
        melhor = 0.0
        for m in re.finditer(r"(?:" + padrao + r")[^\d%]{0,20}?"
                             r"(?:r\$\s*(\d[\d.,]*)|\b(\d[\d.,]*)\s*mil\b)(\s*mil\b)?", texto):
            bruto, em_mil, sufixo_mil = m.group(1), m.group(2), m.group(3)
            try:
                if em_mil:
                    valor = _pct_do_texto(em_mil) * 1000
                else:
                    valor = _pct_do_texto(bruto) * (1000 if sufixo_mil else 1)
            except ValueError:
                continue
            melhor = max(melhor, valor)      # 'de 300 para 150' → fica o maior declarado
        if melhor > 0:
            total += melhor
            achados.append(rotulo)
    return total, achados

def _canais(texto):
    """'Loja física 60% | WhatsApp 28%' -> {'loja fisica': ('Loja física', 60.0), …}
    A barra NÃO é separador: as dicas do próprio app trazem 'WhatsApp/tele-entrega' e
    'Instagram/WhatsApp' dentro do nome. O nome é ancorado no início do pedaço, senão
    'vendo 70% na loja' vira um canal chamado 'vendo'. A chave é normalizada para o
    lojista poder escrever 'WhatsApp' num mês e 'whatsapp' no outro."""
    canais = {}
    for pedaco in re.split(r"[|;]", texto or ""):
        m = re.match(r"\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ /.&-]{1,34}?)\s*:?\s*(\d[\d.,]*)\s*%", pedaco)
        if not m:
            continue
        nome = m.group(1).strip().rstrip(":")
        chave = re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", nome.lower())
                       .encode("ascii", "ignore").decode())
        if not chave:
            continue
        try:
            canais[chave] = (nome, _pct_do_texto(m.group(2)))
        except ValueError:
            pass
    # Só é rateio de canal se houver pelo menos dois e a soma fechar perto de 100.
    # 'vendo 70% na loja e 30% online' não é lista de canais — é frase.
    soma = sum(v[1] for v in canais.values())
    return canais if len(canais) >= 2 and 90 <= soma <= 110 else {}

def _limpar_eco(texto, limite=45):
    """O aviso repete o que o cliente escreveu. Texto dele vai para dentro de um bloco
    que o prompt manda reproduzir exatamente — sem limpar, dá para injetar instrução
    no miolo do produto por um campo do formulário."""
    limpo = re.sub(r"[^0-9A-Za-zÀ-ÿ .,%$/()-]", " ", texto)
    limpo = re.sub(r"\s{2,}", " ", limpo).strip()
    return (limpo[:limite] + "…") if len(limpo) > limite else limpo

def _conferir_somas_percentuais(brutos):
    """Campo de rateio ('Roupas 85% | Calçados 20%') que não fecha 100% é erro de
    preenchimento — e o produto tem de avisar em vez de analisar em cima dele."""
    avisos = []
    for chave in CAMPOS_RATEIO:
        texto = (brutos.get(chave) or "").strip()
        if not texto or "%" not in texto:
            continue
        partes = re.findall(r"(\d[\d.,]*)\s*%", texto)
        if len(partes) < 2:
            continue
        try:
            soma = sum(_pct_do_texto(p) for p in partes)
        except ValueError:
            continue
        if not 97 <= soma <= 103:
            rotulo = ROTULOS_CAMPOS.get(chave, chave.replace("_", " "))
            avisos.append(
                f"🟡 As informações de \"{rotulo}\" NÃO PUDERAM SER AVALIADAS: os percentuais que "
                f"você escreveu ({_limpar_eco(texto)}) somam {_fmt_br(soma)}%, e precisam somar 100%. "
                f"Volte ao campo \"{rotulo}\" no formulário, corrija e gere a análise de novo. "
                f"O restante desta análise não foi afetado")
    return avisos

# O app escreve os campos gerais SEMPRE nesta ordem, um por linha, e escreve todos
# — inclusive os vazios. É isso que permite distinguir o campo de verdade de uma
# linha "lucro: 20.000" que o lojista digitou DENTRO do Objetivo (que é o 3º campo,
# antes de faturamento/meta/custos/lucro) e que antes vencia o valor real.
ORDEM_CAMPOS_GERAIS = (
    "nome_negocio", "periodo", "objetivo_principal", "faturamento", "meta",
    "custos", "lucro", "verba_melhorias", "funcionarios",
    # `canais` saiu do formulário em 06/08 (o `vendas_canal` já nomeia os canais).
    # `tempo_disponivel` saiu em 10/08 (#087): o prompt prometia respeitá-lo e nenhum
    # código conferia — e o fiscal exigiria precificar cada ação em horas, conta que
    # ninguém sabe fazer. As quatro instruções que o citavam saíram no mesmo ato.
    # Ficam fora daqui também: chave morta nesta lista faz ela mentir sobre o
    # formulário. A 1.0.2.0 instalada ainda manda os campos — e eles continuam sendo
    # aceitos, só que pelo caminho livre, sem exigência de ordem.
    "capacidade", "vendas_canal", "desafios", "observacoes",
)
_POSICAO = {k: i for i, k in enumerate(ORDEM_CAMPOS_GERAIS)}

def _campos_do_bloco(bloco):
    """Um campo geral só é aceito se o campo ANTERIOR na ordem do formulário já
    apareceu. Uma linha 'lucro: X' escrita dentro do Objetivo chega antes de
    'custos' e é descartada — sem isso, texto livre sequestrava número crítico e
    o Motor publicava o valor errado como 'cálculo exato'.
    Devolve (campos, sequestrados) — o aviso ao cliente precisa dizer a verdade."""
    linhas = [l for l in bloco.splitlines() if ":" in l]
    # Quais campos gerais existem NESTE bloco — a exigência é sobre o anterior que
    # de fato está presente. Sem isso, um bloco parcial rejeita tudo em cascata.
    presentes = [k for k in ORDEM_CAMPOS_GERAIS
                 if any(re.fullmatch(r"[a-z_]+", l.partition(":")[0].strip().lower())
                        and l.partition(":")[0].strip().lower() == k for l in linhas)]
    anterior_de = {k: (presentes[i - 1] if i > 0 else None) for i, k in enumerate(presentes)}

    campos, sequestrados, vistos, descartados = {}, [], set(), {}
    for linha in linhas:
        k, _, v = linha.partition(":")
        k = k.strip().lower()
        if not re.fullmatch(r"[a-z_]+", k):
            continue  # "Dos R$ 57.100 de custos" não é nome de campo
        if k in _POSICAO:
            anterior = anterior_de.get(k)
            fora_de_ordem = anterior is not None and anterior not in vistos
            if fora_de_ordem or k in campos:
                if k in CAMPOS_CRITICOS and k not in sequestrados:
                    sequestrados.append(k)
                    descartados.setdefault(k, v.strip())
                continue
            vistos.add(k)
        elif k in campos:
            continue
        campos[k] = v.strip()
    # Rede de segurança: se a ordem do app mudar, um campo pode ser descartado e nunca
    # reaparecer. Valor descartado é melhor que campo vazio — mas o aviso cai, porque
    # aí não houve sequestro nenhum, foi a minha regra que errou.
    for chave, valor in descartados.items():
        if chave not in campos:
            campos[chave] = valor
            sequestrados.remove(chave)

    # O BLOCO CONTÍGUO decide os quatro números que importam. O app escreve
    # faturamento/meta/custos/lucro em quatro linhas SEGUIDAS, uma por campo. Uma
    # linha 'lucro: X' digitada dentro de um campo de texto nunca vem seguida de
    # 'verba_melhorias:'. É a posição no bloco que distingue, não a ordem relativa —
    # e o Objetivo é vizinho imediato do faturamento, então ordem não basta.
    seq = ("faturamento", "meta", "custos", "lucro")
    chaves_por_linha = []
    for linha in linhas:
        k = linha.partition(":")[0].strip().lower()
        chaves_por_linha.append(k if re.fullmatch(r"[a-z_]+", k) else None)
    # O bloco verdadeiro é o que vem SEGUIDO do campo seguinte do formulário
    # (verba_melhorias). Um bloco injetado dentro de um texto não tem esse vizinho.
    candidatos = [i for i in range(len(chaves_por_linha) - 3)
                  if tuple(chaves_por_linha[i:i + 4]) == seq]
    real = next((i for i in candidatos
                 if i + 4 < len(chaves_por_linha) and chaves_por_linha[i + 4] == "verba_melhorias"),
                candidatos[-1] if candidatos else None)
    if real is not None:
        for j, chave in enumerate(seq):
            valor = linhas[real + j].partition(":")[2].strip()
            if campos.get(chave) != valor:
                campos[chave] = valor
                if chave not in sequestrados:
                    sequestrados.append(chave)
    return campos, sequestrados

_RE_CANAL_REAIS = re.compile(r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \-\./]{1,28}?)\s*R?\$\s*([\d.]+(?:,\d+)?)")

def _canais_reais(texto):
    """'Loja R$ 25.000 | Mercado Livre R$ 18.000' -> {'Loja': 25000.0, ...}.

    Irmão do `_canais()`, que lê percentual. Existe porque o `custo_canal` foi
    convertido de prosa para reais por canal justamente para dar margem de
    contribuição por canal — a dor nº 1 do Multicanal — e a conversão tinha sido
    feita só no app."""
    fora = {}
    for bruto, valor in _RE_CANAL_REAIS.findall(texto or ""):
        nome = bruto.strip(" |-–—.").strip()
        if len(nome) < 3:
            continue
        v = _num_br(valor)
        if v is not None and v > 0:
            fora[nome] = v
    return fora

def _pct_sao(*valores, limite=300):
    """Percentual fora desta faixa quase sempre é campo mal preenchido, não negócio.
    O Motor cala em vez de imprimir '+5.900%' sob o selo de 'cálculo exato'."""
    return all(v is not None and abs(v) <= limite for v in valores)

# ─── O ESTOQUE PARADO — a cifra mais carregada da análise, e ela vem de PROSA ───
# "Situação do estoque atual" é tipo="text" (nexo_analise.py:692): o cliente escreve
# à vontade e escreve o valor sem ninguém pedir — "ainda tem cerca de R$ 18.000 a
# preço de custo parada" (teste real de 01/08). Esse número sustenta QUATRO seções:
# a perda, a decisão, o gatilho da ação e a meta de estoque. E até aqui quem o lia da
# prosa era o modelo.
#
# REGRA DO FUNDADOR (05/08), e é a espinha desta função:
#     "Se o sistema tem certeza, usa. Se o sistema tem dúvida, cala."
# Calar não é omitir — o produto DECLARA que não conseguiu determinar. É melhor
# admitir uma limitação do que apresentar um número sem fundamento: a primeira o
# lojista perdoa, a segunda destrói a confiança quando ele descobre.
_RE_CIFRA_ESTOQUE = re.compile(r"R\$\s*(\d[\d.]*(?:,\d+)?)\s*(%?)")

def _texto_do_campo(dados, chave):
    """Valor de um campo do payload, com as linhas de continuação juntas.
    O app envia 'chave: valor' (nexo_analise.py:851) e um widget Text quebra linha —
    sem juntar a continuação, metade da frase do cliente se perde. Uma linha nova que
    pareça 'outro_campo:' encerra: na dúvida colhe-se MENOS texto, que erra para o
    lado de calar."""
    # 🔴 SÓ O BLOCO ATUAL. Esta função varria o payload INTEIRO e pegava a PRIMEIRA
    # linha com a chave — que está na análise anterior, porque o app manda o mês
    # passado antes do marcador. Medido: o lojista informava R$ 4.000 hoje e o
    # produto publicava R$ 18.000 do mês passado, com o selo "apurado"; e com o
    # campo de hoje VAZIO ele publicava o valor antigo como "o estoque que você
    # informou". Irmão gêmeo do bug do `_teto_da_verba`, e a contradição estava
    # dentro do próprio `_bloco_metas`: ele cortava certo para faturamento e lucro
    # e errado para o estoque, na mesma função.
    dados = (dados or "").split("=== DADOS ATUAIS ===", 1)[-1]
    achado, corpo = False, []
    for linha in (dados or "").splitlines():
        m = re.match(r"^([a-z_]+):\s?(.*)$", linha)
        if m:
            if achado:
                break
            if m.group(1) == chave:
                achado, corpo = True, [m.group(2)]
            continue
        if achado:
            corpo.append(linha)
    return "\n".join(corpo).strip() if achado else ""

def _valor_do_estoque(dados):
    """Devolve (valor, motivo). valor=None é o DEGRAU 3 do #081 — declarar a ausência,
    nunca estimar. Exige marcador de moeda: 'cerca de 30% parado' NÃO é R$ 30."""
    texto = _texto_do_campo(dados, "estoque")
    if not texto:
        return None, "o campo de estoque não foi preenchido"
    achados = _RE_CIFRA_ESTOQUE.findall(texto)
    if not achados:
        return None, "o cliente descreveu o estoque sem informar valor em reais"
    if len(achados) > 1:
        return None, "o campo traz mais de um valor em reais e não se sabe qual é o parado"
    bruto, pct = achados[0]
    if pct:
        return None, "o número informado é percentual, não valor em reais"
    v = _num_br(bruto)
    if v is None or v <= 0:
        return None, "o valor informado não pôde ser lido"
    return v, "ok"

def _valor_estoque(dados):
    """Devolve (valor, motivo) — a cifra do estoque que o resto do produto usa para
    NARRAR (meta, prompt, validador). DECLARAÇÃO GANHA DE INFERÊNCIA (#085 M4):
    primeiro tenta `estoque_valor` (#088) — campo numérico próprio, sem ambiguidade
    de parsing. Só cai para `_valor_do_estoque` — regex sobre o texto livre de
    `estoque` — quando o campo novo não veio: é o caminho que a 1.0.2.0 instalada
    ainda percorre, porque ela não manda `estoque_valor`.
    ⚠️ NÃO é a função que o GIRO usa (`calcular_motor`, bloco GIRO) — o giro exige
    o valor DECLARADO nas DUAS pontas (hoje e a análise anterior); aceitar inferência
    aqui bastaria para narrar "o estoque parado é X", mas não para fechar uma
    identidade contábil entre dois períodos."""
    texto = _texto_do_campo(dados, "estoque_valor")
    if texto:
        v = _num_br(texto)
        if v is not None and v > 0:
            return v, "ok"
        return None, "o valor do estoque não pôde ser lido"
    return _valor_do_estoque(dados)

# Frase do degrau 3, definida pelo fundador em 05/08. Sai daqui, literal, para o
# prompt e para o validador — uma redação só, num lugar só.
FRASE_ESTOQUE_SEM_VALOR = ("Foi identificado estoque parado, mas não foi possível determinar "
                           "seu valor com segurança a partir dos dados informados.")

def _fmt_br(v, dec=1):
    s = f"{v:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-2] if s.endswith(",0") else s

def _fmt_rs(v):
    """Dinheiro: centavos só quando existem. Uma regra de arredondamento, num lugar
    só — é o que impede a mesma grandeza de sair '16,77' numa seção e '16,8' na
    outra, que foi o defeito do PDF de agosto."""
    s = _fmt_br(v, 2)
    return s[:-3] if s.endswith(",00") else s

def _lucro_incoerente(fat, custos, lucro):
    """O lucro informado não fecha com faturamento − custos?

    🔴 O DEFEITO QUE ESTA FUNÇÃO EXISTE PARA MATAR, achado em análise real (13/08):
    o Radar dizia, na mesma tela, *"Números não fecham: faturamento menos custos dá
    R$ 20.000, mas o lucro informado é R$ 45.000"* — e logo acima **"Margem líquida:
    75% (margem saudável)"**. Depois o §2 amplificava: *"o lucro de R$ 45.000 é um
    ponto positivo, considerando a margem saudável"*.

    ### O produto avisava que o número estava errado e concluía a partir dele.

    Entrada incoerente precisa CONTAMINAR tudo que depende dela. Não basta avisar:
    aviso ao lado de conclusão é conclusão, porque ninguém lê o rodapé antes de
    acreditar no título.

    ⚠️ A tolerância de 15% é a mesma que já existia no aviso — não é régua nova.
    """
    if not (fat and fat > 0 and custos is not None and lucro is not None):
        return False
    return abs((fat - custos) - lucro) > 0.15 * fat


def _atuais(dados):
    """Números do período ATUAL, com a mesma leitura que o Motor usa. Existe para as
    seções escritas por código não dependerem de reparsear nada por conta própria."""
    txt = dados.split("=== DADOS ATUAIS ===", 1)[1] if "=== DADOS ATUAIS ===" in dados else dados
    return {k: _num_br(v) for k, v in _campos_do_bloco(txt)[0].items()}

# ─── A ANÁLISE VIRA ESTRUTURA — e para de ser re-interpretada em cada estágio ───
# Até 05/08 a análise viajava como TEXTO e era lida por regex em três lugares
# independentes: o validador aqui, a injeção dos blocos de código aqui, e o
# `salvar_pdf` do app (nexo_analise.py:360). Três parsers sobre prosa de LLM, e
# qualquer um podia discordar dos outros — cada conserto num abria folga em outro.
# Agora a prosa vira estrutura UMA VEZ, aqui, e todo mundo depois lê estrutura.
_RE_TITULO_SECAO = re.compile(r"^\s*[^\w\d]*(\d+)\.\s+(.+)$")
_BANDEIRAS = {"\U0001F534": "risco", "\U0001F7E1": "atencao", "\U0001F7E2": "ok"}
_SIMBOLOS = {v: k for k, v in _BANDEIRAS.items()}

def _linha_estruturada(t):
    """A bandeira vira DADO, não emoji no meio da frase. É o que dispensa o app de
    fazer strip de emoji e remapear para bolinha colorida porque a fonte do PDF não
    renderiza — em HTML a cor sai do campo `bandeira`."""
    t = (t or "").strip()
    band = next((b for b in _BANDEIRAS if t.startswith(b)), None)
    if band:
        return {"texto": t[len(band):].strip(), "bandeira": _BANDEIRAS[band], "tipo": "bandeira"}
    if t.startswith("•"):
        return {"texto": t.lstrip("• ").strip(), "bandeira": None, "tipo": "bullet"}
    return {"texto": t, "bandeira": None, "tipo": "corrida"}

def _parece_titulo(t):
    """Título de seção é MAIORITARIAMENTE maiúsculo — não integralmente.

    Exigir o título inteiro em maiúsculas derrubava a seção por um parêntese:
    'METAS ATÉ A PRÓXIMA ANÁLISE (2 a 3 metas)' não era reconhecida, a
    substituição falhava e a meta INVENTADA pelo modelo ia ao cliente.
    E olhar só a primeira palavra derrubava '5. O QUE ESTÁ TE FAZENDO PERDER
    DINHEIRO', que abre com uma letra só — defeito medido antes de subir.
    A proporção resolve os dois e continua recusando linha de ação numerada
    ('1. Definir o preço de saída', 1 maiúscula em 28 letras)."""
    letras = [c for c in (t or "") if c.isalpha()]
    if len(letras) < 3:
        return False
    maiusculas = sum(1 for c in letras if c.isupper())
    return maiusculas >= 3 and maiusculas / len(letras) >= 0.6

def _garantir_secao(secoes, chave, titulo, linhas):
    """Substitui a seção pelo texto do código — e se o cabeçalho do modelo não
    permitiu encontrá-la, ACRESCENTA em vez de desistir.

    🔴 Por que a segunda metade existe: sem ela, a garantia de que o Radar e as
    Metas saem do código dependia de o modelo ter escrito o cabeçalho do jeito
    esperado naquele dia. Falhou o casamento, publicava-se a versão do modelo —
    exatamente o defeito que a estrutura veio matar, e em silêncio."""
    if not linhas:
        return "sem-dado"
    if _substituir_secao(secoes, chave, linhas):
        return "codigo"
    n = max([s["n"] for s in secoes if s.get("n")] or [0]) + 1
    secoes.append({"n": n, "titulo": titulo, "origem": "codigo",
                   "linhas": [_linha_estruturada(l) for l in linhas]})
    return "acrescentada"

def _em_secoes(texto):
    """O ÚNICO ponto em que prosa vira estrutura.
    Título de seção é MAIÚSCULO — sem isso, uma ação numerada ('1. Definir o preço
    de saída…') seria lida como início de seção e partiria a análise ao meio."""
    secoes, atual, preambulo = [], None, []
    for linha in (texto or "").split("\n"):
        m = _RE_TITULO_SECAO.match(linha)
        # A PRIMEIRA PALAVRA em maiúsculas basta. Exigir o título INTEIRO maiúsculo
        # derrubava a seção por um parêntese: "8. METAS ATÉ A PRÓXIMA ANÁLISE
        # (2 a 3 metas)" não era reconhecida, a substituição falhava, e a meta
        # INVENTADA pelo modelo ia ao cliente. Medido em 05/08: 3 de 4 variações
        # de cabeçalho quebravam. E "1. Definir o preço de saída" continua sendo
        # recusada, que é o falso positivo que o teste de maiúsculas existia para
        # evitar.
        if m and _parece_titulo(m.group(2)):
            atual = {"n": int(m.group(1)), "titulo": m.group(2).strip(),
                     "origem": "modelo", "linhas": []}
            secoes.append(atual)
            continue
        if not linha.strip():
            continue
        (atual["linhas"] if atual is not None else preambulo).append(_linha_estruturada(linha))
    if preambulo:
        secoes.insert(0, {"n": None, "titulo": None, "origem": "modelo", "linhas": preambulo})
    return secoes

def _substituir_secao(secoes, chave, linhas):
    """O miolo que o modelo escreveu é DESCARTADO e o do código entra no lugar.
    `origem` fica no payload para o app poder mostrar o que é apurado."""
    if not linhas:
        return False
    for s in secoes:
        if s["titulo"] and chave.upper() in s["titulo"].upper():
            s["linhas"] = [_linha_estruturada(l) for l in linhas]
            s["origem"] = "codigo"
            return True
    return False

def _texto_de_secoes(secoes):
    """Achata a estrutura de volta em texto. Isto NÃO é legado descartável: é o campo
    `analise` que a 1.0.2.0 instalada na máquina dos clientes espera. Acrescenta-se
    `secoes`; nunca se remove `analise`, senão todo cliente instalado quebra junto."""
    partes = []
    for s in secoes:
        if s["titulo"]:
            partes.append(f"{s['n']}. {s['titulo']}")
        for l in s["linhas"]:
            pref = _SIMBOLOS.get(l["bandeira"], "") + " " if l["bandeira"] else (
                   "• " if l["tipo"] == "bullet" else "")
            partes.append(f"{pref}{l['texto']}")
        partes.append("")
    return "\n".join(partes).strip()

def _bloco_metas(dados):
    """§8 ESCRITA POR CÓDIGO — mata o alvo arbitrado.
    Em produção, 05/08, o modelo inventou 'de R$ 54.800 para R$ 62.500' e ignorou a
    meta de R$ 55.000 que o cliente havia informado. Números redondos escolhidos por
    quem não tem de onde tirá-los.
    A regra passa a ser: alvo ou VEM DO CLIENTE, ou é CONTA declarada, ou a meta é
    DEFENDER o que já foi conquistado. Meta que nasce de conta diz que nasceu."""
    a = _atuais(dados)
    fat, meta, lucro = a.get("faturamento"), a.get("meta"), a.get("lucro")
    linhas = []
    # 🔴 A mesma invalidade do Radar: sem isto o §8 mandava "manter a margem em 75%"
    # sobre uma margem que o próprio Radar tinha acabado de invalidar — e o alvo de
    # lucro, que nasce dela, herdava o erro multiplicado.
    if _lucro_incoerente(fat, a.get("custos"), lucro):
        margem = None
    else:
        margem = (lucro / fat * 100) if (fat and fat > 0 and lucro is not None) else None
        if margem is not None and not _pct_sao(margem):
            margem = None

    if fat and fat > 0:
        if meta and meta > fat:
            linhas.append(f"• Faturamento: de R$ {_fmt_rs(fat)} para R$ {_fmt_rs(meta)} "
                          f"— a meta que você definiu.")
        elif meta and meta > 0:
            linhas.append(f"• Faturamento: manter em R$ {_fmt_rs(fat)} ou mais — você já "
                          f"superou a meta de R$ {_fmt_rs(meta)} que definiu para o período.")
        else:
            linhas.append(f"• Faturamento: manter em R$ {_fmt_rs(fat)} ou mais. "
                          f"Você não informou meta de faturamento nesta análise.")
    if margem is not None:
        linhas.append(f"• Margem líquida: manter em {_fmt_br(margem)}% ou mais.")

    # Lucro NÃO é alvo novo: é o que o faturamento-alvo dá com a margem de hoje.
    alvo_fat = meta if (meta and fat and meta > fat) else fat
    if alvo_fat and margem is not None and lucro is not None:
        alvo_lucro = alvo_fat * margem / 100
        # Quando a meta de faturamento já foi batida, o alvo vira o próprio
        # faturamento e a conta reproduz o lucro atual: saía "de R$ 7.900 para
        # R$ 7.900" sob selo de apurado. Meta que repete o ponto de partida não é
        # meta — é defesa, e se escreve como defesa.
        if abs(alvo_lucro - lucro) < max(0.005 * abs(lucro or 1), 1):
            if meta and fat and meta > fat:
                linhas.append(f"• Lucro: manter em R$ {_fmt_rs(lucro)} ou mais — bater a "
                              f"meta de faturamento acima, sozinha, quase não move o lucro. "
                              f"Quem move é a margem.")
            else:
                linhas.append(f"• Lucro: manter em R$ {_fmt_rs(lucro)} ou mais — você já "
                              f"faturou o que precisava; o que muda o lucro daqui em diante "
                              f"é a margem, não o volume.")
        else:
            linhas.append(f"• Lucro: de R$ {_fmt_rs(lucro)} para R$ {_fmt_rs(alvo_lucro)} "
                          f"— meta sugerida pelo NEXO, calculada com o faturamento acima e a "
                          f"margem de hoje.")

    # 🔴 O ALVO É NUMÉRICO, e isso não é preciosismo de redação: a régua do próprio
    # validador (checagem 2) exige "de [atual] para [alvo]" com os DOIS números. Esta
    # linha dizia "para menos da metade" — alvo em texto — e reprovava. Como ela é
    # escrita por CÓDIGO e reposta por `_entregar` a cada tentativa, o modelo não tinha
    # como consertar: reprovava na 1ª, reprovava na 2ª, e a análise caía no fallback.
    # 🟢 Medido em produção 10/08 19:30 (VALIDADOR|saida-2a-tentativa|ativa|meta sem
    # ponto de partida). Ficou latente enquanto a cifra do estoque dependia de o
    # cliente escrevê-la no texto livre; com `estoque_valor` estruturado (#088) passou
    # a valer para TODA análise com estoque preenchido.
    # 🔴 A META DE METADE DO ESTOQUE SAIU EM 14/08. "De R$ 20.000 para R$ 10.000 — metade
    # do estoque que você informou" tem matemática correta e decisão nenhuma: não existe
    # régua calibrada que autorize reduzir 50% do estoque num ciclo. Dividir por dois não
    # é análise, é a única conta que dava para fazer com um número só.
    #
    # ⚖️ É a lei da trava ⓑ no outro eixo — indicador sem benchmark não vira juízo; ALVO
    # SEM RÉGUA NÃO VIRA META. E aqui era PIOR que o modelo escrevendo: sai por código,
    # dentro da seção que leva o selo "apurado".
    #
    # 🚪 O que destrava: uma régua de cobertura declarada (quantos meses de venda um
    # estoque deve cobrir naquele ramo). Com ela, o alvo nasce do dado. Sem ela, o
    # produto informa o valor e cala sobre o tamanho certo — que é o que ele sabe.

    if not linhas:
        return []
    # Redação escolhida pelo fundador em 05/08: o produto afirma o que faz, não se
    # defende do que não faz.
    # Sem a string vazia: ela virava um <li> vazio no HTML do app.
    linhas.append("As metas foram definidas apenas a partir dos dados informados e dos "
                  "cálculos realizados nesta análise.")
    return linhas

# 🔴 CAUSA A (14/08) — REVISÃO DO MESMO PERÍODO NÃO É CICLO, defesa no Motor.
# A correção nasce na seleção do histórico (app), mas o cliente 1.0.2.0 já instalado
# não filtra na origem: se ele rodar o mesmo mês de novo, manda "ANÁLISE ANTERIOR 1"
# com o período atual, e o Motor compararia Agosto × Agosto. Esta defesa neutraliza
# isso na leitura, antes de qualquer cálculo — protege TODOS os clientes.
def _norm_periodo(p):
    p = unicodedata.normalize("NFD", (p or ""))
    p = "".join(c for c in p if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", p.lower())

def _mesmo_periodo(p1, p2):
    a, b = _norm_periodo(p1), _norm_periodo(p2)
    return bool(a) and a == b

def _revisao_do_mesmo_periodo(dados):
    """A ANÁLISE ANTERIOR 1 tem o mesmo período que os DADOS ATUAIS?"""
    m_ant = re.search(r"ANÁLISE ANTERIOR 1 \(período:\s*(.*?)[,)]", dados or "")
    if not m_ant:
        return False
    atual = (dados or "").split("=== DADOS ATUAIS ===", 1)[-1]
    m_at = re.search(r"^periodo:\s*(.*)$", atual, re.M | re.I)
    return bool(m_at) and _mesmo_periodo(m_ant.group(1), m_at.group(1))

def _neutralizar_revisao(dados):
    """Se o predecessor for do mesmo período, remove o bloco anterior — downstream vê
    'primeira análise' (sem giro, sem §2 de ciclo, sem comparação). É a leitura honesta:
    duas fotos do mesmo mês não formam evolução."""
    if _revisao_do_mesmo_periodo(dados):
        return "=== DADOS ATUAIS ===\n" + (dados or "").split("=== DADOS ATUAIS ===", 1)[-1].lstrip("\n")
    return dados

def _anteriores(dados):
    """Números da análise ANTERIOR, com a mesma leitura do Motor."""
    if "DADOS DAQUELA ANÁLISE:" not in dados:
        return {}
    txt = dados.split("DADOS DAQUELA ANÁLISE:", 1)[1]
    for corte in ("DECISÕES RECOMENDADAS", "=== ANÁLISE ANTERIOR 2", "=== DADOS ATUAIS"):
        if corte in txt:
            txt = txt.split(corte, 1)[0]
    return {k: _num_br(v) for k, v in _campos_do_bloco(txt)[0].items()}

# ─────────────────────────────────────────────────────────────────────────────
# 🔴 A CHAVE NÃO É NOME — e o cliente leu a chave.
#
# Relatório da Aromática, 14/08: *"A VALIDADE RISCO do Perfume é um alerta de que
# R$ 250,00 podem ser perdidos nos próximos 30 dias."* `validade_risco` é o nome da
# chave; ela viajava crua dentro de DADOS DO NEGÓCIO e o modelo a costurou na frase.
#
# ⚠️ SEGUNDA VEZ DA MESMA CAUSA. A primeira foi o `baixa_*`, que o modelo leu como
# FALTA e inverteu a decisão do Motorola G17. Consertamos RENOMEANDO — o que fez a
# chave ser lida certo, mas não parou de ser lida. Renomear tratava o sintoma.
#
# Agora o payload continua idêntico para todo parser (o `dados` não é tocado): o que
# muda é a CÓPIA que entra no prompt, onde cada chave estruturada vira o rótulo que o
# lojista viu na tela. Um nome que o modelo pode escrever sem estragar a frase.
ROTULOS_ESTRUTURADOS = {
    "falta_ocorreu":     "Faltou algum item no período",
    "falta_categoria":   "Tipo de item que faltou",
    "falta_canal":       "Canal em que faltou",
    "falta_item":        "Item que faltou",
    "margem_melhor":     "Categoria de MELHOR margem (declarada pelo lojista)",
    "margem_pior":       "Categoria de PIOR margem (declarada pelo lojista)",
    "encalhe_ocorreu":   "Há produto parado/encalhado",
    "encalhe_categoria": "Tipo de produto parado",
    "encalhe_item":      "Item parado",
    "validade_risco":    "Há produto próximo do vencimento",
    "validade_item":     "Produto próximo do vencimento",
    "validade_valor":    "Valor em risco por vencimento (R$)",
    "validade_prazo":    "Prazo do vencimento mais próximo",
}
# ⛔ `estoque_base` é contrato entre app e Motor, não dado de negócio. O modelo não tem
# o que fazer com ele, e uma linha "estoque base: total" no meio dos dados é
# exatamente o tipo de coisa que ele acaba narrando.
CAMPOS_INTERNOS = ("estoque_base",)

def _dados_legiveis(dados):
    """A cópia do payload que vai ao modelo, com chave trocada por rótulo.

    ⚠️ NÃO altera `dados`. Todo parser — Motor, validador, shadow, `_atuais` — continua
    lendo a chave original. Trocar o payload de verdade quebraria a precedência do
    #097, que existe justamente para distinguir chave estruturada de campo legado."""
    saida = []
    for linha in (dados or "").split("\n"):
        chave = linha.split(":", 1)[0].strip()
        if chave in CAMPOS_INTERNOS:
            continue
        rotulo = ROTULOS_ESTRUTURADOS.get(chave)
        saida.append(f"{rotulo}:{linha.split(':', 1)[1]}" if rotulo else linha)
    return "\n".join(saida)

def _bloco_atual(dados):
    return dados.split("=== DADOS ATUAIS ===", 1)[1] if "=== DADOS ATUAIS ===" in dados else dados

def _bloco_anterior(dados):
    if "DADOS DAQUELA ANÁLISE:" not in dados:
        return ""
    txt = dados.split("DADOS DAQUELA ANÁLISE:", 1)[1]
    for corte in ("DECISÕES RECOMENDADAS", "=== ANÁLISE ANTERIOR 2", "=== DADOS ATUAIS"):
        if corte in txt:
            txt = txt.split(corte, 1)[0]
    return txt

def _base_estoque(bloco):
    """`estoque_valor` daquele bloco é ESTOQUE TOTAL, declarado pela versão que coletou?

    Não é campo do formulário — é o app dizendo sob QUAL contrato pediu o número. Até
    14/08 a dica pedia o que está PARADO e a identidade do giro exige o TOTAL; quem
    obedeceu a dica mandou encalhe. Sem a declaração, a natureza é desconhecida, e
    desconhecida não alimenta identidade contábil.

    ⛔ Ausência NUNCA vira "provavelmente total". É o mesmo princípio do #099: o que
    não está garantido não sustenta o que depende dele."""
    return _texto_do_campo(bloco, "estoque_base").strip().lower() == "total"

def _sem_tag_de_prazo(texto):
    """Tira a etiqueta (Custo: … | Resultado em: …) e a numeração da ação antiga.
    Ela é do MÊS PASSADO — o app a renderiza como chip e o lojista lê como prazo
    de agora."""
    # O `[\s.·]*$` do fim importa: a frase costuma terminar em ")." e sem ele o
    # ancoramento falhava por causa do ponto final.
    t = re.sub(r"\s*\(?\s*Custo:[^)]*\)?[\s.·]*$", "", texto, flags=re.I)
    return re.sub(r"^\s*\d+[\.\)]\s*", "", t).strip(" .·") + "."

def _acoes_recomendadas(dados):
    """As ações que a análise ANTERIOR recomendou. O app manda o relatório inteiro
    daquele mês sob 'DECISÕES RECOMENDADAS'; aqui se pega só a seção de ações."""
    if "DECISÕES RECOMENDADAS" not in dados:
        return []
    txt = dados.split("DECISÕES RECOMENDADAS", 1)[1].split("=== DADOS ATUAIS", 1)[0]
    for s in _em_secoes(txt):
        titulo = (s["titulo"] or "").upper()
        if any(p in titulo for p in ("AÇÕES", "AÇÃO", "ACOES", "PLANO", "O QUE FAZER")):
            return [_sem_tag_de_prazo(l["texto"]) for l in s["linhas"]
                    if len(l["texto"]) > 20][:3]
    return []

# As quatro leituras do ciclo. Sem a coluna "executou", as linhas 2 e 4 recebem o
# MESMO conselho — e elas pedem conselhos opostos. O PDF de agosto escreveu "ainda
# é importante", que é certo para a 4 e errado para a 2: acertou por sorte.
_LEITURA_CICLO = {
    ("sim", True):      "Você executou e o resultado veio. Repetir é a aposta mais segura do próximo ciclo.",
    ("sim", False):     "Você executou e o resultado não veio. O caminho não é insistir — é mudar a abordagem.",
    ("parcial", True):  "Você executou em parte e o resultado veio. Vale terminar o que ficou pela metade antes de tentar coisa nova.",
    ("parcial", False): "Você executou em parte e o resultado não veio. Antes de trocar de estratégia, veja se o que faltou executar era justamente o que sustentava a recomendação.",
    ("nao", True):      "O resultado melhorou sem que a recomendação fosse executada. Vale descobrir o que puxou — porque não foi isso.",
    ("nao", False):     "A recomendação não chegou a ser testada. Ela continua de pé.",
}

# 🔴 O TERCEIRO ESTADO, que faltava — e a falta dele produziu a pior frase já publicada.
#
# Análise real de 13/08, segundo ciclo do "Celular Legal": faturamento +10%, ticket
# +13,3%, clientes +36,8%, conversão +15 pontos — e lucro −6,7%, margem −3,8 pontos,
# estoque +50%. O produto escreveu:
#
#     "Você executou e o resultado NÃO VEIO. O caminho não é insistir."
#
# Porque `melhorou` era decidido por UMA linha: `lucro >= lucro_ant`. Quatro medidas
# avançaram e uma caiu, e o veredito olhou só a que caiu.
#
# 🔴 E o mais grave: a recomendação era LIQUIDAR ENCALHE — que o próprio prompt define
# como "sacrificar margem DE PROPÓSITO para recuperar caixa". O produto mandou
# sacrificar margem e depois reprovou o lojista porque a margem caiu.
#
# ⛔ RESULTADO MISTO NÃO É RESULTADO QUE NÃO VEIO.

# Direção de cada comparável: para onde ele precisa ir para ser "melhor".
#
# ⚠️ SÓ ENTRA AQUI O QUE TEM VALÊNCIA DEFINIDA NO CONTRATO. Faturamento maior é melhor
# porque a definição do indicador diz isso, não porque parece. Custo maior é pior pela
# mesma razão. Onde a valência depende de evidência que o NEXO não tem, o campo fica
# FORA e é apenas descrito.
_DIRECAO_COMPARAVEL = {
    "faturamento": +1, "lucro": +1, "ticket_medio": +1, "clientes": +1,
    "conversao": +1,
    # Custo subindo é PIOR: mais dinheiro saindo para produzir a mesma venda.
    "custos": -1,
}

# 🔴 O ESTOQUE PERDEU A VALÊNCIA EM 14/08 — consequência direta do #102.
#
# Enquanto `estoque_valor` significava ESTOQUE PARADO, `-1` era honesto: encalhe
# caindo é bom, sem discussão. Agora o campo significa ESTOQUE TOTAL, e a direção
# deixou de decidir sozinha:
#
#   · estoque menor pode ser GIRO SAUDÁVEL — ou RISCO DE RUPTURA;
#   · estoque maior pode ser EXCESSO — ou preparação legítima para um mês forte.
#
# ⚖️ Direção pode ser publicada; VALÊNCIA EXIGE EVIDÊNCIA ADICIONAL. O Motor continua
# dizendo "Valor do estoque: R$ 24.000 → R$ 22.000 (−8,3%)" pela linha comparativa —
# o que ele não faz mais é usar essa queda para pôr o estoque no lado bom do estado
# misto. E o MISTO não perde nada com isso: ele se forma com os comparáveis cuja
# valência ESTÁ definida, sem precisar fabricar valência para existir.
_SEM_VALENCIA = ("estoque_valor",)

_ROTULO_COMPARAVEL = {
    "faturamento": "faturamento", "lucro": "lucro", "ticket_medio": "ticket",
    "clientes": "clientes", "conversao": "conversão", "custos": "custos",
    "estoque_valor": "estoque",
}


# Rótulos que são PLURAIS mesmo sozinhos na frase. Sem isto o verbo concordava com o
# tamanho da lista e saía "enquanto custos subiu".
_ROTULO_PLURAL = {"custos", "clientes"}


def _lista_pt(itens):
    itens = [_ROTULO_COMPARAVEL[k] for k in itens]
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


# 🔴 O ESTADO É DO RESULTADO; A DECLARAÇÃO É DO LOJISTA. Eram duas coisas grudadas
# nas seis frases acima — cada uma abre julgando o resultado ("o resultado veio") e
# fecha aconselhando a execução ("termine o que ficou pela metade"). Enquanto o MISTO
# só valia para quem executou tudo, as outras duas ramificações continuavam decidindo
# se o resultado veio por UMA linha, `lucro >= lucro_ant` — a falha original, intacta
# em dois terços do bloco. Com faturamento caindo 22% e custos melhorando, "Em parte"
# ainda publicava "o resultado veio", e "Não executei" ainda publicava "o resultado
# melhorou". Agora a oração de resultado vem da classificação e a de execução vem da
# declaração, que é o que cada uma sempre significou.
_ABERTURA_MISTA = {
    "sim":     "Você executou as ações do ciclo anterior.",
    "parcial": "Você executou em parte as ações do ciclo anterior.",
    "nao":     "Você não executou as ações do ciclo anterior.",
}
_FECHO_MISTO = {
    "sim":     "Com os dados disponíveis, o NEXO não atribui essas variações às ações "
               "executadas.",
    # O conselho do "em parte" NÃO depende da direção do resultado — o que ficou pela
    # metade continua por testar tanto no ciclo bom quanto no ruim. Ele sobrevive.
    "parcial": "Com os dados disponíveis, o NEXO não atribui essas variações ao que foi "
               "executado. Vale terminar o que ficou pela metade antes de concluir "
               "sobre a recomendação.",
    "nao":     "Com os dados disponíveis, o NEXO não atribui essas variações à "
               "recomendação: ela não chegou a ser testada e continua de pé.",
}


def _leitura_mista(avancaram, recuaram, chave="sim"):
    """A frase do resultado MISTO — observa, compara e PRESERVA CAUSALIDADE.

    A última oração não é cortesia: sem ela, listar o que subiu logo depois de dizer
    "você executou" ATRIBUI o movimento às ações. O NEXO comparou; não mediu causa.
    E ela muda com a declaração: para quem NÃO executou, "não atribui às ações
    executadas" seria absurdo — não houve ação a que atribuir.

    ⚠️ E o verbo segue o MOVIMENTO, não a avaliação: custo e estoque que pioraram
    SUBIRAM, não recuaram. Dizer "os custos recuaram" quando eles subiram inverteria
    o fato para poder usar uma palavra só.

    🔴 E ISSO VALE NOS DOIS LADOS — a mesma lição de 13/08, de novo. A regra estava
    aplicada só ao lado ruim, e o lado bom herdou o defeito espelhado: custo e estoque
    que MELHORAM caem, e a frase dizia que eles "avançaram". Pego no teste dirigido da
    Aromática, antes de gastar análise: *"faturamento, lucro e estoque avançaram"* com
    o estoque indo de R$ 24.000 para R$ 22.000.

    ⚠️ E o verbo também concorda com o NÚMERO GRAMATICAL do rótulo, não com o tamanho
    da lista. "custos" e "clientes" são plurais mesmo sozinhos — a frase saía "enquanto
    custos subiu". Mesma família da nota do `PREOCUPACOES`, que já registrava que "os
    custos subiu" ia sair no Radar.
    """
    def _frase(chaves, verbo_s, verbo_p):
        if not chaves:
            return ""
        plural = len(chaves) > 1 or _ROTULO_COMPARAVEL[chaves[0]] in _ROTULO_PLURAL
        return f"{_lista_pt(chaves)} {verbo_p if plural else verbo_s}"

    # Lado BOM: o que subiu subiu; o que melhorou caindo, caiu.
    melhorou = " e ".join(p for p in (
        _frase([k for k in avancaram if _DIRECAO_COMPARAVEL[k] > 0], "avançou", "avançaram"),
        _frase([k for k in avancaram if _DIRECAO_COMPARAVEL[k] < 0], "caiu", "caíram"),
    ) if p)
    # Lado RUIM: idem, na direção oposta.
    piorou = " e ".join(p for p in (
        _frase([k for k in recuaram if _DIRECAO_COMPARAVEL[k] > 0], "recuou", "recuaram"),
        _frase([k for k in recuaram if _DIRECAO_COMPARAVEL[k] < 0], "subiu", "subiram"),
    ) if p)
    return (f"{_ABERTURA_MISTA[chave]} Os resultados foram MISTOS: "
            f"{melhorou}, enquanto {piorou}. "
            f"{_FECHO_MISTO[chave]}")


def _classificar_ciclo(a, ant):
    """Devolve (avancaram, recuaram) entre os comparáveis que existem nos dois períodos.

    ⛔ Percorre só o `_DIRECAO_COMPARAVEL` — quem está no `_SEM_VALENCIA` nunca entra
    em nenhum dos dois lados. Não é omissão: é a recusa de transformar direção em
    juízo onde a evidência não existe."""
    avancaram, recuaram = [], []
    for campo, direcao in _DIRECAO_COMPARAVEL.items():
        atual, anterior = a.get(campo), ant.get(campo)
        if atual is None or anterior is None or atual == anterior:
            continue
        (avancaram if (atual > anterior) == (direcao > 0) else recuaram).append(campo)
    return avancaram, recuaram

def _bloco_ciclo(dados, indicadores=()):
    """§2 CICLO ANTERIOR — escrita por CÓDIGO.

    Quatro fatos lado a lado e uma leitura escolhida por tabela, não por opinião:
    o que foi recomendado · o que o lojista executou · o que aconteceu com os
    números · o que ele mudou por conta própria. É o que transforma "como foi meu
    mês?" em "o que eu fiz funcionou?".

    Nada aqui é inferido: sem análise anterior a seção não existe, e sem declaração
    de execução o produto NÃO atribui o resultado à recomendação."""
    recomendadas = _acoes_recomendadas(dados)
    if not recomendadas:
        return []                      # primeira análise: não há ciclo a comparar

    a, ant = _atuais(dados), _anteriores(dados)
    bruto = _campos_do_bloco(dados.split("=== DADOS ATUAIS ===", 1)[-1])[0]

    linhas = ["O que o NEXO recomendou no ciclo anterior:"]
    linhas += [f"• {r}" for r in recomendadas]

    resp = (bruto.get("acoes_executadas") or "").strip().lower()
    quais = (bruto.get("acoes_quais") or "").strip()
    if "todas" in resp or resp.startswith("sim"):
        chave, rotulo = "sim", "Executei todas"
    elif "parte" in resp:
        chave, rotulo = "parcial", "Executei em parte"
    elif "não executei" in resp or "nao executei" in resp:
        chave, rotulo = "nao", "Não executei"
    elif "primeira" in resp:
        # A opção existe no formulário e não casava com nada: o lojista marcava
        # "esta é minha primeira análise" e lia "Não informado" no relatório.
        chave, rotulo = None, "Você marcou que esta seria sua primeira análise"
    else:
        chave, rotulo = None, "Não informado"
    linhas.append(f"O que você executou: {rotulo}" + (f" — {quais}" if quais else ""))

    # TODAS as comparações apuradas, não uma amostra. A seção antiga PEDIA ao modelo
    # que percorresse as linhas calculadas — e pedir nunca garantiu que ele
    # percorresse. Inclusive as que MELHORARAM: o dono precisa saber o que está
    # funcionando para não desmontar justamente isso.
    comparacoes = [i for i in indicadores if "→" in i or "vs análise anterior" in i]
    if comparacoes:
        linhas.append("O que aconteceu com os números:")
        linhas += [f"• {c}" for c in comparacoes]

    lucro, lucro_ant = a.get("lucro"), ant.get("lucro")
    melhorou = None
    if lucro is not None and lucro_ant is not None:
        melhorou = lucro >= lucro_ant
        if not comparacoes:
            linhas.append(f"O que aconteceu com o lucro: R$ {_fmt_rs(lucro_ant)} → "
                          f"R$ {_fmt_rs(lucro)}")

    mudou = (bruto.get("mudancas") or "").strip()
    if mudou:
        linhas.append(f"O que mudou por sua conta: {mudou}")

    # 🔴 O resultado MISTO tem leitura própria e vem ANTES da tabela binária: quatro
    # medidas avançando e uma caindo não é "o resultado não veio". Vale nas TRÊS
    # declarações — o estado é do resultado, não de quem o declarou.
    avancaram, recuaram = _classificar_ciclo(a, ant)
    if chave and avancaram and recuaram:
        linhas.append(_leitura_mista(avancaram, recuaram, chave))
    elif chave and melhorou is not None:
        linhas.append(_LEITURA_CICLO[(chave, melhorou)])
    else:
        # 🔴 A fronteira de execução: sem declaração, o produto NÃO escolhe entre as
        # histórias possíveis — ele diz que não escolhe.
        linhas.append("Você não informou o que executou, então esta análise observa o "
                      "resultado sem atribuí-lo às recomendações anteriores.")
    return linhas

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
    atual_bruto, sequestrados = _campos_do_bloco(atual_txt)
    atual = {k: _num_br(v) for k, v in atual_bruto.items()}
    ant_bruto = _campos_do_bloco(ant_txt)[0] if ant_txt else {}
    ant = {k: _num_br(v) for k, v in ant_bruto.items()}

    # Lida cedo: a bandeira do faturamento precisa dela.
    sazonal = (atual_bruto.get("ancora_sazonal") or "").strip()
    mes_fraco = "fraco" in sazonal.lower()

    indicadores, radar = [], []

    # AVISO EM VEZ DE CHUTE: campo crítico preenchido que o Motor não conseguiu ler
    # vira linha visível no PDF, com o que o cliente escreveu e como corrigir.
    # Silêncio aqui já custou análise errada entregue como se fosse certa.
    # Ficam numa lista PRÓPRIA: são recado de preenchimento, não diagnóstico, e entram
    # DEPOIS da história do negócio — o cliente abria o PDF pago sendo corrigido.
    avisos = []
    for chave in CAMPOS_CRITICOS:
        escrito = (atual_bruto.get(chave) or "").strip()
        if escrito and atual.get(chave) is None:
            rotulo = ROTULOS_CAMPOS.get(chave, chave)
            avisos.append(
                f"🟡 Os cálculos que dependem de \"{rotulo}\" NÃO PUDERAM SER FEITOS: não consegui "
                f"ler o valor com segurança, você escreveu \"{_limpar_eco(escrito)}\". "
                f"Volte ao campo \"{rotulo}\" e escreva só o número (ex.: 38500), sem texto junto. "
                f"O restante desta análise não foi afetado")
    avisos.extend(_conferir_somas_percentuais(atual_bruto))
    for chave in sequestrados:
        rotulo = ROTULOS_CAMPOS.get(chave, chave)
        avisos.append(
            f"🟡 Encontrei \"{rotulo}\" escrito também dentro de um campo de texto (Objetivo, "
            f"Desafios ou Observações). Para o cálculo usei o valor do campo próprio do "
            f"formulário e ignorei o que estava no texto. Se o valor certo é o outro, volte ao "
            f"campo \"{rotulo}\" e corrija. O restante desta análise não foi afetado")
    fat = atual.get("faturamento")
    meta = atual.get("meta")
    custos = atual.get("custos")
    lucro = atual.get("lucro")

    # O Radar tem de contar UMA história que fecha sozinha, na ordem em que o dono
    # pensa: vendi quanto → gastei quanto → sobrou quanto → sobra quanto de cada 100.
    # Antes cada linha estava certa e o conjunto não explicava nada: "meta 104%
    # atingida" colava em "o lucro caiu" sem a ponte, e o aumento dos custos — que é
    # a ponte — não aparecia em lugar nenhum.
    fat_ant, custos_ant, lucro_ant = ant.get("faturamento"), ant.get("custos"), ant.get("lucro")
    conta_historia = bool(fat and fat > 0 and fat_ant and fat_ant > 0
                          and custos and custos > 0 and custos_ant and custos_ant > 0
                          and lucro is not None and lucro_ant is not None)

    # 🔑 A INVALIDADE SE PROPAGA CORTANDO NA RAIZ, não consumidor a consumidor.
    # `margem = None` desliga de uma vez o indicador, o rótulo, a linha do Radar, a
    # comparação com a análise anterior e o alvo do §8 — porque todos eles JÁ têm
    # guarda para None. Policiar seis lugares deixaria o sétimo passar.
    incoerente = _lucro_incoerente(fat, custos, lucro)
    margem = None if incoerente else (
        lucro / fat * 100 if (fat and fat > 0 and lucro is not None) else None)
    if margem is not None:
        indicadores.append(f"Margem líquida: {_fmt_br(margem)}% (lucro R$ {_fmt_br(lucro)} / faturamento R$ {_fmt_br(fat)})")
    ating = fat / meta * 100 if (fat and fat > 0 and meta and meta > 0) else None
    if ating is not None:
        indicadores.append(f"Atingimento da meta: {_fmt_br(ating)}% (faturou R$ {_fmt_br(fat)} de uma meta de R$ {_fmt_br(meta)})")
    rotulo_margem = None
    if margem is not None:
        rotulo_margem = "prejuízo" if margem < 0 else ("margem apertada" if margem < 10 else "margem saudável")

    if conta_historia:
        d_fat = (fat - fat_ant) / fat_ant * 100
        d_cus = (custos - custos_ant) / custos_ant * 100
        # 🔴 Só o que DEPENDE do lucro morre quando ele não fecha. Faturamento e
        # custos continuam: eles não têm nada a ver com o número que não bateu, e
        # apagá-los seria invalidar o que está por perto, não o que depende.
        d_luc = (None if incoerente else
                 ((lucro - lucro_ant) / abs(lucro_ant) * 100 if lucro_ant else None))
        m_ant = None if incoerente else lucro_ant / fat_ant * 100
        if _pct_sao(d_fat, d_cus) and (margem is None or _pct_sao(margem, m_ant))                 and (d_luc is None or _pct_sao(d_luc)):
            # 1. vendi quanto
            sinal = "+" if d_fat >= 0 else ""
            texto_meta = ""
            if ating is not None:
                # 🔴 "Bateu" a partir de 95% dizia que o lojista atingiu a meta
                # quando ele ficou abaixo dela. No teste real de 06/08 saiu
                # "bateu a meta de R$ 55.000 (99,6%)" — e o modelo escalou para
                # "vendeu mais do que o previsto" na seção seguinte. Bater é
                # chegar a 100%; 95–99,9% é quase, e quase se diz como quase.
                if ating >= 100:
                    texto_meta = f" — e bateu a meta de R$ {_fmt_br(meta)} ({_fmt_br(ating)}%)"
                elif ating >= 95:
                    texto_meta = (f" — e chegou perto da meta de R$ {_fmt_br(meta)}, "
                                  f"faltando {_fmt_br(100 - ating)}% para bater")
                else:
                    texto_meta = f" — mas ficou em {_fmt_br(ating)}% da meta de R$ {_fmt_br(meta)}"
            # A ÂNCORA SAZONAL entra AQUI, na bandeira que o cliente de fato vê.
            # Queda em mês que o LOJISTA declarou fraco não é 🔴: é o esperado.
            # Sem isto, uma loja de roupas comparando janeiro com dezembro levava
            # bandeira vermelha todo ano — número certo, leitura falsa.
            band_fat = "🟢" if d_fat > 0 else ("🟡" if mes_fraco else "🔴")
            nota_sazonal = " — e você declarou que este costuma ser um mês fraco" if (
                mes_fraco and d_fat <= 0) else ""
            radar.append(f"{band_fat} Faturamento: R$ {_fmt_br(fat_ant)} → R$ {_fmt_br(fat)} "
                         f"({sinal}{_fmt_br(d_fat)}%){texto_meta}{nota_sazonal}")
            # 2. gastei quanto — a ponte que faltava
            # "caíram" com +0% saiu no teste real de 06/08: variação exatamente
            # zero caía no `else`. Ficar igual não é cair.
            comparativo = ("ficaram iguais" if abs(d_cus) < 0.05
                           else "subiram MAIS que o faturamento" if d_cus > d_fat
                           else "subiram menos que o faturamento" if d_cus > 0
                           else "caíram")
            radar.append(f"{'🔴' if d_cus > d_fat else '🟢'} Custos: R$ {_fmt_br(custos_ant)} → R$ {_fmt_br(custos)} "
                         f"({'+' if d_cus >= 0 else ''}{_fmt_br(d_cus)}%) — {comparativo}")
            # 3. sobrou quanto
            if d_luc is not None:
                radar.append(f"{'🟢' if d_luc >= 0 else '🔴'} Lucro: R$ {_fmt_br(lucro_ant)} → R$ {_fmt_br(lucro)} "
                             f"({'+' if d_luc >= 0 else ''}{_fmt_br(d_luc)}%)")
            # 4. sobra quanto de cada R$ 100 — a régua que o dono entende sem conta.
            # ⛔ Some quando o lucro não fecha: ela é margem pura.
            if margem is not None and m_ant is not None:
                band = "🟢" if margem >= m_ant else ("🔴" if (m_ant - margem >= 3 and margem < 10) else "🟡")
                radar.append(f"{band} De cada R$ 100 vendidos sobravam R$ {_fmt_br(m_ant, 2)} e agora sobram "
                             f"R$ {_fmt_br(margem, 2)} ({rotulo_margem})")
        else:
            conta_historia = False

    if not conta_historia:
        if margem is not None:
            band = "🔴" if margem < 0 else ("🟡" if margem < 10 else "🟢")
            radar.append(f"{band} Margem líquida: {_fmt_br(margem)}% ({rotulo_margem})")
        if ating is not None:
            band = "🟢" if ating >= 95 else ("🟡" if ating >= 70 else "🔴")
            radar.append(f"{band} Meta do período: {_fmt_br(ating)}% atingida")
    if fat and fat > 0 and custos and custos > 0:
        peso = custos / fat * 100
        indicadores.append(f"Custos sobre faturamento: {_fmt_br(peso)}%")
        if lucro is not None:
            if _lucro_incoerente(fat, custos, lucro):
                # Declara o LIMITE, não um "vale conferir" ao lado da conclusão: diz
                # o que ficou de fora e por quê. O limite é do dado informado, e a
                # frase nunca acusa o lojista de nada — ele pode ter errado de campo.
                radar.append(f"🔴 Números não fecham: faturamento menos custos dá R$ {_fmt_br(fat - custos)}, "
                             f"mas o lucro informado é R$ {_fmt_br(lucro)}. Margem e lucro ficaram "
                             f"FORA desta leitura — confira os lançamentos e rode de novo")
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
        if _pct_sao(peso_ant, peso_atual, d_fat, d_cus):
            indicadores.append(
                f"Custos sobre faturamento: eram {_fmt_br(peso_ant)}% do faturamento e agora são "
                f"{_fmt_br(peso_atual)}% (custos {'+' if d_cus >= 0 else ''}{_fmt_br(d_cus)}%, "
                f"faturamento {'+' if d_fat >= 0 else ''}{_fmt_br(d_fat)}%)")

    # A MARGEM ENTRE PERÍODOS — é a resposta direta a "para onde foi o dinheiro", e
    # faltava: o Motor comparava faturamento, lucro e ticket, e deixava de fora
    # justamente a linha que mede se o negócio ficou mais ou menos lucrativo.
    fat_ant2, lucro_ant2 = ant.get("faturamento"), ant.get("lucro")
    if fat and fat > 0 and lucro is not None and fat_ant2 and fat_ant2 > 0 and lucro_ant2 is not None:
        m_atual, m_ant = lucro / fat * 100, lucro_ant2 / fat_ant2 * 100
        if _pct_sao(m_atual, m_ant):
            pontos = m_atual - m_ant
            indicadores.append(
                f"Margem líquida vs análise anterior: era {_fmt_br(m_ant)}% e agora é {_fmt_br(m_atual)}% "
                f"({'+' if pontos >= 0 else ''}{_fmt_br(pontos)} pontos)")

    # COMPARAÇÃO DE TODOS OS CAMPOS NUMÉRICOS, não só de três. O Motor comparava
    # faturamento, lucro e ticket; os outros sete o modelo comparava de cabeça — e
    # errava (declarou "a capacidade ficou igual" com 65% → 70% nos dados).
    # Campo percentual se compara em PONTOS, não em porcentagem: 33% → 35% é
    # +2 pontos, não "+2". A conta é diferente e a leitura também.
    # 🔴 A CONTRADIÇÃO DETERMINÍSTICA DA RODADA 2 (14/08). O Radar declarava, com todas
    # as letras, que o estoque de julho NÃO tem natureza garantida — "antes o campo
    # pedia só o que estava parado; misturar daria um número errado" — e três linhas
    # abaixo o §2 publicava "Valor do estoque: R$ 20.000 → R$ 24.000 (+20%)".
    #
    # ⛔ SE JULHO NÃO SERVE PARA O GIRO, NÃO SERVE PARA A VARIAÇÃO. É o mesmo número,
    # com a mesma natureza desconhecida, no mesmo par de períodos. Publicar a segunda
    # é contradizer o que o próprio produto acabou de invalidar.
    #
    # ⚖️ Por isso NÃO é observação: é a exceção do #099 — falha determinística,
    # dependência explícita, e a saída contradiz um fato que o NEXO já declarou.
    base_par_ok = _base_estoque(_bloco_atual(dados)) and _base_estoque(_bloco_anterior(dados))
    for chave, nome, tipo in CAMPOS_COMPARAVEIS:
        a, b = atual.get(chave), ant.get(chave)
        if a is None or not b:
            continue
        if chave == "estoque_valor" and not base_par_ok:
            continue
        if tipo == "percentual":
            pontos = a - b
            if not _pct_sao(a, b) or abs(pontos) < 0.1:
                continue
            indicadores.append(f"{nome}: {_fmt_br(b)}% → {_fmt_br(a)}% "
                               f"({'+' if pontos >= 0 else ''}{_fmt_br(pontos)} pontos)")
            continue
        delta = (a - b) / abs(b) * 100
        if not _pct_sao(delta):
            continue  # campo mal preenchido: cala em vez de imprimir '+5.900%' como fato
        if delta == 0 and chave not in CAMPOS_CRITICOS:
            continue  # "Funcionários: 2 → 2" é ruído; "Lucro: igual" não é
        moeda = "R$ " if tipo == "dinheiro" else ""
        indicadores.append(f"{nome}: {moeda}{_fmt_br(b)} → {moeda}{_fmt_br(a)} "
                           f"({'+' if delta >= 0 else ''}{_fmt_br(delta)}%)")
        if chave == "faturamento" and not conta_historia:
            # Mesma regra da comparação rica: queda em mês declarado fraco não é 🔴.
            band = "🟢" if delta > 0 else ("🟡" if (delta >= -5 or mes_fraco) else "🔴")
            radar.append(f"{band} Faturamento vs análise anterior: {'+' if delta >= 0 else ''}{_fmt_br(delta)}%")
    # A EVOLUÇÃO DOS CANAIS — "Loja física 65% | WhatsApp 25%" é texto, então nenhum
    # campo numérico a captura, e o canal que mais cresce ficava invisível. É a única
    # boa notícia estrutural que os dados da loja traziam e o PDF não citava.
    canais_a, canais_b = _canais(atual_bruto.get("vendas_canal")), _canais(ant_bruto.get("vendas_canal"))
    for chave, (nome_canal, pct_a) in canais_a.items():
        if chave not in canais_b:
            continue
        pct_b = canais_b[chave][1]
        if abs(pct_a - pct_b) < 0.5 or not _pct_sao(pct_a, pct_b):
            continue
        pontos = pct_a - pct_b
        indicadores.append(f"Canal {nome_canal}: {_fmt_br(pct_b)}% → {_fmt_br(pct_a)}% das vendas "
                           f"({'+' if pontos >= 0 else ''}{_fmt_br(pontos)} pontos)")

    # CUSTOS CONTROLÁVEIS — o formulário tem um campo `custos` agregado, mas o lojista
    # costuma detalhar aluguel/folha/energia nas observações. Somando o que ele nomeou
    # como fixo, o resto é mercadoria e taxa: é ali que a redução é possível. Sem isto
    # a única saída do produto era mandar o dono "mapear os custos", que é tarefa, não
    # decisão — e o Cânone veta entregar tarefa no lugar de decisão.
    #
    # ⚠️ A HIERARQUIA ENTRE AS DUAS FONTES. Esta varredura é INFERÊNCIA sobre texto
    # livre; `compra_mercadoria` é NÚMERO DECLARADO pelo lojista. As duas publicavam
    # "custo fixo" na MESMA análise, com valores diferentes e sob rótulos quase
    # idênticos ("Composição do custo" × "Composição dos custos") — o cliente lia dois
    # números para a mesma coisa e não tinha como saber qual valia. Declaração ganha de
    # inferência: havendo o número, a varredura desce a NOMEADORA — entrega os rótulos
    # que a cifra declarada não tem, e cala a própria cifra.
    if custos and custos > 0:
        fixos, achados = _custos_fixos(atual_bruto)
        declarado = atual.get("compra_mercadoria")
        if declarado is not None and 0 < declarado <= custos:
            # E mesmo nomeando, só fala se as duas leituras couberem uma na outra: se o
            # fixo que ele detalhou já estoura o fixo declarado (custos − compra), as
            # fontes se contradizem, e o produto cala em vez de escolher uma delas.
            if achados and 0 < fixos <= custos - declarado:
                indicadores.append("Composição do custo fixo (pelo que você detalhou): "
                                   + ", ".join(achados))
        elif len(achados) >= 3 and 0 < fixos < custos:
            controlaveis = custos - fixos
            indicadores.append(
                f"Composição do custo (pelo que você detalhou): fixos R$ {_fmt_br(fixos)} "
                f"({', '.join(achados)}) e R$ {_fmt_br(controlaveis)} em mercadoria e taxas, "
                f"que é a parte onde a redução é possível — {_fmt_br(controlaveis / custos * 100)}% do custo total")

    # Recado de preenchimento entra no fim, e limitado: o Radar é do negócio.
    if avisos:
        radar.extend(avisos[:3])
        if len(avisos) > 3:
            radar.append(f"🟡 …e mais {len(avisos) - 3} campo(s) a conferir no preenchimento")

    # ── PARA ONDE FOI O DINHEIRO — compra de mercadoria × custo fixo ────────────
    # A dor D03 é "o dinheiro some no fim do mês e eu não sei por quê". O produto
    # sabia o total dos custos e não sabia DO QUÊ. No teste real de 01/08 a resposta
    # existiu — mas dentro de `observacoes`, porque o cliente teve a boa vontade de
    # decompor sozinho. Dependia da generosidade de quem preenche.
    compra = atual.get("compra_mercadoria")
    if compra is not None and compra > 0 and custos and custos > 0:
        if compra > custos:
            radar.append("🟡 A compra de mercadoria informada é maior que os custos do "
                         "período. Confira os dois campos — o NEXO não usou este número.")
        else:
            fixo = custos - compra
            pct = compra / custos * 100
            radar.append(
                f"💰 Composição dos custos: R$ {_fmt_rs(compra)} foi compra de mercadoria "
                f"({_fmt_br(pct)}% dos custos) e R$ {_fmt_rs(fixo)} é custo fixo e "
                f"despesa.")

        # 🔴 A FRASE QUE SAIU DAQUI: "o dinheiro que virou estoque não sumiu — está na
        # prateleira". Ela trata TODA a compra como estoque remanescente, e no mesmo
        # relatório de 13/08 o Motor calculou que R$ 34.000 SAÍRAM do estoque. A compra
        # não fica na prateleira: parte dela vira venda.
        #
        # ✅ E no lugar entra a relação que o produto JÁ TINHA e não usava: compras
        # menos saída é EXATAMENTE a variação do estoque. Isso é apuração, não juízo —
        # e diz ao lojista se ele comprou acima ou abaixo do que vendeu, que é a
        # pergunta que o campo existe para responder.

    # ── O GIRO — a identidade do estoque, calculada em código (#088 · dados.md M6) ──
    # "O que devo comprar menos, comprar mais ou parar de comprar?" (veredito do
    # fundador) se responde pela identidade contábil: saída do período = estoque
    # INICIAL + compra de mercadoria − estoque FINAL. O inicial é o estoque final da
    # análise ANTERIOR — já vive no histórico local; dado que já está na casa não se
    # pergunta de novo (M6). O "do quê" já tem dono (`produtos_baixo` nomeia o que
    # não gira); faltava só a cifra, e agora ela é DECLARADA (`estoque_valor`), não
    # inferida de prosa — as duas pontas do tempo usam a MESMA fonte.
    #
    # ⚠️ Exige o valor DECLARADO nas duas pontas — não usa `_valor_estoque` (que aceita
    # inferência da prosa livre): a identidade fecha ou não fecha, não "quase fecha".
    # Cliente que veio da 1.0.2.0 sem `estoque_valor` na análise anterior cai no ramo
    # da primeira vez, e o giro chega assim que houver duas análises com o campo novo.
    # 🔴 A LINHA VAI PARA O `radar`, NÃO PARA OS `indicadores` — e a distinção é a
    # regra M3/#082, não preferência de layout. `indicadores` são CONTEXTO que o
    # modelo narra se quiser; `radar` é publicado LITERALMENTE por código
    # (`_garantir_secao`). Medido na validação ponta a ponta de 10/08: o giro foi
    # calculado certo, entrou como indicador, a rodada caiu no fallback e o cliente
    # não viu o número em lugar nenhum. Cifra que responde "o que parar de comprar"
    # não pode depender de o modelo lembrar dela. Mesma família de "Composição dos
    # custos" e "Caixa", que já são radar pelo mesmo motivo.
    # 🔒 A NATUREZA TEM DE ESTAR DECLARADA NAS DUAS PONTAS. Até 14/08 a dica do campo
    # pedia "quanto vale o que está PARADO hoje" enquanto a identidade abaixo exige o
    # estoque TOTAL — e a dica, por ser mais específica que o rótulo, é a que o lojista
    # obedece. Número coletado assim NÃO pode alimentar giro: seria o Motor atribuindo
    # ao dado uma natureza diferente da que a interface induziu.
    #
    # ⛔ E a trava é retroativa por construção: análise gravada antes desta versão não
    # traz `estoque_base`, então o giro se abstém até haver DUAS coletadas sob o
    # contrato novo. Não se conserta dado velho adivinhando o que ele queria dizer.
    base_ok = _base_estoque(_bloco_atual(dados)) and _base_estoque(_bloco_anterior(dados))
    est_final = atual.get("estoque_valor")
    est_inicial = ant.get("estoque_valor") if base_ok else None
    if est_final is not None and est_final > 0:
        if est_inicial is None:
            # REGRA DA PRIMEIRA VEZ (M6): sem período anterior com o dado, o Motor
            # declara a ausência — e diz quando o número aparece — em vez de calcular
            # com o que não tem. Publicada também, porque declarar a ausência É
            # entrega (E6) e porque diz ao lojista o que ele ganha voltando.
            # ⚠️ E o MOTIVO é dito, porque os dois são diferentes para o lojista: um se
            # resolve voltando no próximo mês; o outro é o produto declarando que NÃO
            # VAI USAR um número que ele tem — e por quê.
            #
            # ⛔ A redação vale para as DUAS pontas. Pode faltar critério no período
            # anterior (coletado sob a dica antiga) ou no atual (app não atualizado), e
            # afirmar qual dos dois seria adivinhar.
            if not base_ok and ant.get("estoque_valor") is not None:
                radar.append(
                    "📦 Giro do estoque: ainda não calculável — o NEXO passou a pedir o "
                    "valor TOTAL do estoque, e antes o campo pedia só o que estava parado. "
                    "Os dois períodos precisam ter sido informados pelo mesmo critério; "
                    "misturar daria um número errado. A partir da próxima análise ele "
                    "aparece sozinho.")
            else:
                radar.append(
                    "📦 Giro do estoque: ainda não calculável — o NEXO precisa do valor do "
                    "estoque em duas análises seguidas para medir o que saiu no período. "
                    "A partir da próxima, ele aparece sozinho.")
        elif compra is not None and compra >= 0:
            saida = est_inicial + compra - est_final
            estoque_medio = (est_inicial + est_final) / 2
            # Números não fecham: o estoque final maior do que inicial+compra
            # explicariam não produz giro negativo — cala, mesma família da checagem
            # de faturamento/custos/lucro acima. E é a COBERTURA que explode quando a
            # saída é quase zero (divisão por um número pequeno) — o teto de sanidade
            # é nela, não no giro, que não tem essa fragilidade.
            if saida > 0 and estoque_medio > 0:
                cobertura = est_final / saida
                if _pct_sao(cobertura, limite=60):
                    giro = saida / estoque_medio
                    radar.append(
                        f"📦 Giro do estoque: R$ {_fmt_rs(saida)} saiu de estoque no período "
                        f"(giro de {_fmt_br(giro, 2)}x sobre o estoque médio) — no ritmo "
                        f"atual, o estoque de hoje (R$ {_fmt_rs(est_final)}) equivale a "
                        f"{_fmt_br(cobertura, 1)} meses de venda.")
                    # ✅ COMPRA × SAÍDA — a relação que o produto já tinha e não dizia.
                    # É subtração pura, e responde direto a pergunta do campo: comprei
                    # mais ou menos do que vendi? ⛔ Sem adjetivo: o Motor informa a
                    # direção, quem decide se está certo é o dono.
                    delta = compra - saida
                    if abs(delta) >= 1:
                        sentido = ("acima" if delta > 0 else "abaixo")
                        radar.append(
                            f"🛒 Compra × saída: você comprou R$ {_fmt_rs(compra)} e saiu "
                            f"R$ {_fmt_rs(saida)} — comprou R$ {_fmt_rs(abs(delta))} "
                            f"{sentido} do que vendeu, e essa diferença é exatamente a "
                            f"variação do estoque no período.")
            # saída <= 0 ou cobertura fora da faixa de sanidade: campo mal preenchido
            # produziria giro sem sentido — cala em vez de publicar.
        # compra ausente: a identidade não fecha sem as três pernas — cala em
        # silêncio, mesmo padrão de qualquer outra conta condicional do Motor.

    # ── O EIXO DO CAIXA ─────────────────────────────────────────────────────────
    # D06: "meu faturamento cresce e o caixa continua apertado". Faturamento, custos
    # e lucro são COMPETÊNCIA; caixa é quando o dinheiro entra. Quem vende em 12x
    # tem lucro e não tem caixa — e o NEXO dizia a ele que a margem estava saudável.
    # Pergunta-se o VALOR que só entra depois, não o percentual: 30% em 2x e 30% em
    # 12x produzem defasagens opostas e o percentual devolvia o mesmo número.
    depois = atual.get("recebimento_futuro")
    if depois is not None and depois > 0 and fat and fat > 0:
        if depois > fat:
            radar.append("🟡 O valor a receber informado é maior que o faturamento do "
                         "período. Confira os dois campos — o NEXO não usou este número.")
        else:
            pct = depois / fat * 100
            linha = (f"💵 Caixa: R$ {_fmt_rs(depois)} do que você faturou ainda não entrou "
                     f"({_fmt_br(pct)}% do faturamento)")
            if compra is not None and 0 < compra <= (custos or 0):
                linha += f", enquanto R$ {_fmt_rs(compra)} já saíram em mercadoria"
            radar.append(linha + ".")

    # ── A PREOCUPAÇÃO DECLARADA — LENTE DE COLETA, JAMAIS DIAGNÓSTICO ───────────
    # Trava 3 do veredito (#088), e ela é escrita em CÓDIGO de propósito: pedir ao
    # modelo que "não conclua pela preocupação do cliente" é instrução, e instrução
    # sobre enquadramento falha do mesmo jeito que falhava sobre número (#083). O que
    # se garante aqui é o FATO publicado ao lado da declaração — se o lojista aponta
    # estoque e o estoque caiu 26,7%, isso sai no Radar por código, mesmo que o modelo
    # escreva um diagnóstico de estoque logo abaixo. O produto deixa de ser espelho da
    # opinião do cliente sem depender da boa vontade do Intérprete.
    declarada = (atual_bruto.get("preocupacao") or "").strip()
    if declarada:
        linha = f"🎯 Sua maior preocupação declarada: {declarada.upper()}."
        alvo = next((v for k, v in PREOCUPACOES.items() if k in declarada.lower()), None)
        if alvo:
            campo, rotulo, sentido = alvo
            a, b = atual.get(campo), ant.get(campo)
            # ⛔ MESMO PAR, MESMA NATUREZA DESCONHECIDA. Nesta rodada a preocupação era
            # LUCRO e a linha não apareceu — mas com "estoque" declarado ela faria
            # exatamente a variação que o Radar acabou de declarar impossível.
            if campo == "estoque_valor" and not base_par_ok:
                a = None
            if a is not None and b:
                delta = (a - b) / abs(b) * 100
                if _pct_sao(delta) and abs(delta) >= 0.1:
                    direcao = "subiu" if delta > 0 else "caiu"
                    linha += (f" Nos números apurados, {rotulo} {direcao} "
                              f"{_fmt_br(abs(delta))}% desde a análise anterior.")
        linha += (" O diagnóstico abaixo segue os números apurados, não a preocupação "
                  "declarada.")
        radar.append(linha)

    # ── A ÂNCORA SAZONAL ────────────────────────────────────────────────────────
    # Sem ela o NEXO compara mês contra mês anterior e nada mais: uma loja de roupas
    # comparando janeiro com dezembro parece catástrofe todo ano. Não é imprecisão —
    # é conclusão errada com número certo, e por isso passa por todas as checagens.
    # O lojista DECLARA (comparar com o mesmo mês do ano passado exigiria 12 análises
    # no histórico, e nenhum cliente tem).
    if sazonal:
        radar.append(f"📅 Você declarou que este costuma ser um {sazonal.lower()} "
                     f"para o seu negócio.")

    # ── OS CAMPOS QUE ERAM PEDIDOS E NÃO ERAM LIDOS ─────────────────────────────
    # Uma auditoria de 06/08 achou OITO campos com zero ocorrências aqui: o lojista
    # preenchia e o produto não usava. Pedir trabalho em troca de nada é pior que
    # não ter o campo. Cada um vira linha apurada, e cala quando vem vazio.

    # DESCONTO — a dor nº 3 do Varejo. Dois números declarados lado a lado, sem
    # derivação: nada de "cada peça saiu no prejuízo", que foi o defeito de ontem.
    desc = atual.get("desconto_valor")
    if desc is not None and desc > 0:
        linha = f"Descontos concedidos no período: R$ {_fmt_rs(desc)}"
        if lucro is not None:
            linha += f", contra um lucro de R$ {_fmt_rs(lucro)} no mesmo período"
        indicadores.append(linha + ".")

    # TEMPO DE PRATELEIRA — no Celular o estoque perde valor a cada lançamento.
    semanas = atual.get("tempo_prateleira")
    if semanas is not None and 0 < semanas <= 520:
        indicadores.append(f"Item mais antigo parado há {_fmt_br(semanas)} semanas.")

    # AGENDA OCIOSA — conta trivial sobre campo que já chega numérico, e é a única
    # cifra que o desenho aprovou para o Pet. Em PERCENTUAL: valorizar em reais
    # exigiria a capacidade teórica, que o lojista não tem e chutaria.
    ocup = atual.get("agenda_ocupacao")
    if ocup is not None and 0 <= ocup <= 100 and ocup < 100:
        indicadores.append(f"Agenda de serviços: {_fmt_br(100 - ocup)}% ociosa "
                           f"({_fmt_br(ocup)}% da capacidade foi preenchida).")

    # MARGEM POR CANAL — a dor nº 1 do Multicanal. `custo_canal` foi convertido para
    # reais no app exatamente para isto, e a conversão não tinha nada do outro lado.
    fat_canal = _canais_reais(atual_bruto.get("faturamento_canal"))
    cus_canal = _canais_reais(atual_bruto.get("custo_canal"))
    for nome, valor in fat_canal.items():
        custo = cus_canal.get(nome)
        if custo is None or valor <= 0:
            continue
        sobra = valor - custo
        indicadores.append(
            f"Canal {nome}: faturou R$ {_fmt_rs(valor)} e, depois dos custos do canal "
            f"(R$ {_fmt_rs(custo)}), sobraram R$ {_fmt_rs(sobra)} "
            f"({_fmt_br(sobra / valor * 100)}% do que vendeu ali).")

    # CONFIANÇA DECLARADA — o campo é obrigatório no app e a dica PROMETE ao lojista
    # que a análise sai com a ressalva certa. Era a única promessa feita na cara dele
    # que o produto não cumpria.
    conf = (atual_bruto.get("confianca_declarada") or "").strip().lower()
    if conf and not conf.startswith("sim"):
        radar.append("🟡 Você indicou que os números informados não representam "
                     "totalmente a realidade — leia as conclusões com essa ressalva.")
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
    t = _corrigir_vocabulario(t)                                # grafia do que é nosso
    t = re.sub(r"[ \t]+$", "", t, flags=re.M)                   # espaços no fim da linha
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

# ─── VALIDADOR — a camada entre a IA e o PDF ────────────────────────────────────
# Fronteira adotada em 04/08: a IA interpreta e recomenda; o CÓDIGO calcula, valida
# e controla. Estas funções não analisam nada — só conferem a resposta da IA contra
# os fatos que o Motor calculou e contra o que o cliente escreveu.
#
# FASE 1 = OBSERVAÇÃO: registra o que bloquearia e deixa passar. Camada nova não
# recusa a entrega de um lojista real antes de a taxa de falso positivo ser medida.
# FASE 2 (04/08, veredito do fundador): CORRIGIR. A observação mediu o que precisava
# — dois falsos positivos achados e consertados, e a última rodada apontou três
# defeitos, os três reais. Em observação eles chegavam ao cliente do mesmo jeito.
# ⚠️ 04/08, fim da manhã: de volta a OBSERVAÇÃO por precaução, com a hipótese de que
# a falha de ~1s em toda análise era cota da conta Groq — e o modo corrigir DOBRA as
# chamadas.
# ✅ 04/08, tarde: CORRIGIR de novo, e a precaução caiu por fato. O serviço voltou
# sozinho, no mesmo dia, sem ninguém tocar em chave ou plano — cota diária não reseta
# no meio do dia, limite de taxa reenche. E a precaução atacava a variável errada: o
# que estourou foi a RAJADA de dezenas de análises por script, não o fator 2. Contra
# rajada, dividir por dois não é defesa; uso real é 1 ou 2 análises por mês.
# O que a precaução custava era alto: em observação a violação é detectada e entregue
# ao cliente assim mesmo — a saída de produção das 15h trazia metas que não fechavam
# entre si (faturamento 12.000 × margem 35% dá 4.200, e a meta de lucro dizia 3.600),
# e o validador tinha apontado. Reativar é trocar esta palavra.
MODO_VALIDADOR = os.environ.get("NEXO_VALIDADOR", "corrigir")      # observacao|corrigir|bloquear

FALLBACK_SEGURO = ("Não foi possível gerar esta recomendação com segurança a partir dos dados "
                   "informados. Confira os campos do período e rode a análise novamente.")

_RE_NUM = re.compile(r"\d[\d.]*(?:,\d+)?")

def _numeros_de(texto):
    return {m.group().replace(".", "") for m in _RE_NUM.finditer(texto or "")}

def _secao_da_saida(saida, titulo):
    """Corpo de uma seção da resposta, pelo MESMO teste de título que estrutura a
    análise — `_parece_titulo`, que exige MAIÚSCULAS.

    🔴 O QUE ESTAVA ERRADO, e por que passou despercebido. Esta função tinha um parser
    PRÓPRIO, e ele era ingênuo: qualquer linha `^\\d+\\.\\s` virava título de seção. Ele
    achava "7. AÇÕES IMEDIATAS", entrava — e a linha seguinte, "1. Revisar a formação
    de preço…", casava com o mesmo padrão e a FECHAVA na hora. A seção de ações chegava
    sempre VAZIA ao validador, e com ela morriam duas checagens:
      · a 4 — ação sem prazo, e ação acima da verba que o cliente informou;
      · a 5 — decisão principal sem ação correspondente.
    Medido em produção 10/08, nos três ambientes da rodada: `acoes=0` em todos. Efeito
    real: verba declarada de "Até R$ 500" e o produto recomendando "(Custo: R$ 1.000)"
    sem ninguém barrar. E o pior de tudo é que a trava aparecia como instalada — testes
    verdes, documentação citando "a verba barra" — que é a definição do #085: trava que
    não roda ocupa o lugar da vigilância sem exercê-la.

    ⚠️ E a correção não é tratar o caso "1." — é PARAR DE TER DOIS PARSERS. O
    `_em_secoes` já resolvia isto desde 05/08, com o teste de maiúsculas, e o comentário
    dele diz exatamente que "1. Definir o preço de saída" tem de ser recusado. Duas
    implementações da mesma leitura, uma certa e outra errada, é a doença que o #083
    nomeia para número — aqui ela apareceu para estrutura.

    Devolve as linhas BRUTAS (com o marcador que o modelo escreveu), porque a checagem 1
    compara o texto da meta com a linha original da saída — sem o marcador, a comparação
    falharia e as metas voltariam a ser varridas como número sem fonte."""
    alvo = (titulo or "").lower()
    linhas = (saida or "").split("\n")
    # Onde estão os títulos DE VERDADE, pelo mesmo critério da estruturação.
    inicios = []
    for i, linha in enumerate(linhas):
        m = _RE_TITULO_SECAO.match(linha)
        if m and _parece_titulo(m.group(2)):
            inicios.append((i, m.group(2)))
    for pos, (i, nome) in enumerate(inicios):
        if alvo not in nome.lower():
            continue
        fim = inicios[pos + 1][0] if pos + 1 < len(inicios) else len(linhas)
        return [l.strip() for l in linhas[i + 1:fim] if l.strip()]
    return []

def _teto_da_verba(dados):
    """Maior valor que o cliente declarou ter para melhorias. 'entre R$ 1.000 e
    R$ 2.000' -> 2000. 'não tenho no momento' -> 0. Sem informação -> None."""
    # 🔴 SÓ O BLOCO ATUAL. Esta função varria o payload INTEIRO, e o app manda a
    # análise anterior ANTES do marcador — então o teto vinha da verba do mês
    # passado. Medido: anterior "não tenho" + atual "acima de R$ 2.000" devolvia 0,
    # e a checagem 4 barrava toda ação por falso positivo. Atingia exatamente o
    # cliente recorrente, que é o eixo do produto.
    atual = (dados or "").split("=== DADOS ATUAIS ===", 1)[-1]
    m = re.search(r"verba_melhorias\s*:\s*(.+)", atual, re.I)
    if not m:
        return None
    texto = m.group(1).strip().lower()
    if not texto:
        return None
    if re.search(r"n[ãa]o tenho|nenhum|zero|sem verba", texto):
        return 0.0
    # "Acima de X" declara PISO, não teto. Devolver X dava ao cliente que tem MAIS
    # dinheiro o mesmo limite do que tem menos, e barrava a ação boa. Sem teto, a
    # checagem fica declaradamente desligada — que é o que o contrato do campo diz.
    if re.search(r"acima de|mais de|acima d[oe]", texto):
        return None
    valores = []
    for bruto in re.findall(r"\d[\d.,]*", texto):
        try:
            v = _pct_do_texto(bruto)
        except ValueError:
            continue
        valores.append(v * 1000 if re.search(re.escape(bruto) + r"\s*mil\b", texto) else v)
    return max(valores) if valores else None

# O produto tem vocabulário próprio e curto. O modelo deforma palavra longa em
# português — saíram 'Reprepecificar', 'Repreprecificar' e 'investedo' em PDFs
# finais. Conferir a grafia do que é NOSSO é determinístico; o resto não é.
VOCABULARIO_NEXO = (
    # 'repre' + qualquer coisa + 'fica' só existe em português como reprecificar.
    # Pega Reprepecificar, Repreprecificar e o que mais o modelo inventar da família.
    (r"\b([Rr])epre[a-zà-ÿ]{0,6}fica", r"\1eprecifica"),
    (r"\binvestedo\b", "investido"),
    (r"\bliquidiar\b", "liquidar"),
)

def _corrigir_vocabulario(texto):
    t = texto or ""
    for padrao, certo in VOCABULARIO_NEXO:
        t = re.sub(padrao, certo, t)
    return t

def _viol(regra, detalhe, trecho="", bloqueia=False, campo="", observa=False):
    """observa=True: a checagem REGISTRA mas não manda a análise de volta ao modelo.
    Checagem nova estreia assim. O motivo é custo medido, não cerimônia: retentativa
    dobra o consumo (6.299 → ~13.400 tokens) de um teto DIÁRIO compartilhado com
    cliente pagante — um falso positivo novo tira análise da mão de quem pagou.
    Mede-se a taxa de disparo no log e só então se promove a checagem.

    ⚖️ A EXCEÇÃO, congelada no #099 para que a convenção não vire dogma:

        Validação nova pode ESTREAR BLOQUEANDO quando a falha é DETERMINÍSTICA, a
        dependência é EXPLÍCITA, e permitir a saída produziria CONTRADIÇÃO com um
        fato que o próprio NEXO Análise já invalidou.

    A convenção protege contra falso positivo de checagem discutível. Quando não há
    o que discutir — `faturamento − custos ≠ lucro`, e o Radar já publicou isso —
    deixar passar não é prudência: é publicar contradição. Única checagem hoje sob
    a exceção: `conclusão sobre número inválido`."""
    return {"regra": regra, "detalhe": detalhe, "trecho": trecho[:90],
            "bloqueia": bloqueia, "campo": campo, "observa": observa}

def validar_entrada(atual, brutos):
    """🔴 BLOQUEIO DE ENTRADA — erro do cliente, detectado ANTES de chamar a IA.
    Bloqueia só o IMPOSSÍVEL; o meramente suspeito vira aviso no Radar e a análise
    segue. Lojista que separa custo de mercadoria de despesa não pode ser barrado."""
    v, fat = [], atual.get("faturamento")
    custos, lucro = atual.get("custos"), atual.get("lucro")
    if fat and fat > 0 and lucro is not None and lucro > fat:
        v.append(_viol("lucro maior que faturamento",
                       f"o lucro informado (R$ {_fmt_br(lucro)}) é maior que o faturamento do "
                       f"período (R$ {_fmt_br(fat)}). Não é possível sobrar mais do que entrou",
                       bloqueia=True, campo="Lucro líquido"))
    if custos and custos > 0 and fat and fat > 0 and custos > 5 * fat:
        v.append(_viol("custos desproporcionais",
                       f"os custos informados (R$ {_fmt_br(custos)}) são mais de cinco vezes o "
                       f"faturamento (R$ {_fmt_br(fat)}). Confira se digitou o valor certo",
                       bloqueia=True, campo="Investimento/Custos do período"))
    # Suspeito, não impossível: a divergência já vira aviso 🟡 no Radar (Motor).
    if fat and fat > 0 and custos and custos > 0 and lucro is not None:
        esperado = fat - custos
        if abs(esperado - lucro) > 0.25 * fat:
            v.append(_viol("lucro diverge de faturamento menos custos",
                           f"faturamento menos custos dá R$ {_fmt_br(esperado)}, mas o lucro "
                           f"informado é R$ {_fmt_br(lucro)}", bloqueia=False, campo="Lucro líquido"))
    return v

# ─────────────────────────────────────────────────────────────────────────────
# 🔴 O QUE UM FATO DECLARADO AUTORIZA DIZER — e onde o produto extrapolou.
#
# Análise real de 13/08. Três frases saíram afirmando o que os dados NÃO sustentam:
#
#   "a compra de R$ 38.000 indica que o investimento em estoque pode não ter sido
#    totalmente eficaz"        → compra ser 84,4% dos custos NÃO prova ineficiência
#   "a falta de capa pode ter IMPACTADO as vendas"
#                              → a falta comprova RUPTURA, não impacto consumado
#   "a diminuição do fluxo pode ser sinal de mudança no comportamento"
#                              → o NEXO sabe que caiu; não sabe POR QUÊ
#
# São a mesma família: FATO DECLARADO → CONSEQUÊNCIA OU CAUSA QUE ELE NÃO ESTABELECE.
# É a causalidade que o mecanismo novo torna inexpressável — aqui ela ainda entra pela
# linguagem, então a trava é nominal e determinística onde dá, e observação onde não dá.
# ─────────────────────────────────────────────────────────────────────────────

# Variação dos APURADOS. Sem análise anterior não existe "cresceu" nem "caiu": não há
# de quê. ⚠️ Nominal nos campos que o Motor compara — o lojista pode declarar variação
# dele ("o fluxo caiu 10%") e isso continua sendo fato dele.
# ─────────────────────────────────────────────────────────────────────────────
# 🔴 "NA MESMA FRASE", EM PORTUGUÊS DE VERDADE — e por que TODAS as travas abaixo
# estavam parcialmente cegas.
#
# `[^.]{0,80}` parece dizer "sem sair da frase". Na prática para no PRIMEIRO ponto —
# e em português o ponto também é separador de milhar. Toda trava escrita assim fica
# cega justamente nas frases que têm DINHEIRO, que são as que este produto escreve.
#
# Medido contra a frase real do relatório da Aromática (14/08):
#     "o estoque parado de R$ 20.000 também é um dinheiro que já foi gasto e não voltou"
# A janela morria dentro de "20.000" e o `re.search` devolvia None.
#
# ⚠️ É a MESMA classe do `\b` que virou byte 0x08 em 13/08: trava instalada,
# documentada, com teste passando — e morta na frase que importava. A diferença é que
# aquela nascia morta e esta morria só quando havia cifra. Pior de encontrar.
#
# Aqui o ponto atravessa quando é ponto de número, e só então.
_MESMA_FRASE = r"(?:[^.]|\.(?=\d))"

_APURADO_VARIA = re.compile(
    r"\b(faturamento|custos?|lucro|margem|ticket m[ée]dio)\b" + _MESMA_FRASE + r"{0,60}?"
    r"\b(cresceu|caiu|subiu|aumentou|diminuiu|reduziu|melhorou|piorou|"
    r"cresceram|caíram|subiram|aumentaram|diminuíram|reduziram)\b|"
    r"\b(cresceu|caiu|subiu|aumentou|diminuiu|reduziu|"
    r"cresceram|caíram|subiram|aumentaram|diminuíram)\b" + _MESMA_FRASE + r"{0,40}?"
    r"\b(faturamento|custos?|lucro|margem|ticket m[ée]dio)\b", re.I)

# Impacto CONSUMADO atribuído à falta. Ruptura autoriza RISCO, nunca efeito medido.
_FALTA_IMPACTO = re.compile(
    r"\b(falta|faltou|ruptura|em falta)\b" + _MESMA_FRASE + r"{0,80}?"
    r"\b(impact\w+|reduz\w+|derrub\w+|prejudic\w+|diminu\w+|fez perder|"
    r"custou|comeu|tirou)\b", re.I)

# Juízo sobre a QUALIDADE da compra. Nenhum campo mede se a compra foi acertada.
# ─────────────────────────────────────────────────────────────────────────────
# 🔑 O MOTOR CONCEDE O DIREITO DE CONCLUIR — o detector só reconhece a conclusão.
#
# Veredito do fundador, 14/08, depois da Rodada 2 provar os dois lados:
#
#   · bloqueio LEXICAL puro é errado — "a compra foi excessiva" pode ser VERDADE
#     quando existe evidência, e travar a palavra calaria o produto;
#   · `observa=True` é errado também — deixou frases economicamente falsas chegarem
#     ao relatório real.
#
# ⚖️ A saída não é escolher entre os dois: é BLOQUEIO CONDICIONADO À AUTORIZAÇÃO.
#     *"O modelo não ganha direito de concluir porque encontrou palavras plausíveis;
#      o Motor concede o direito de concluir porque existe evidência."*
#
# E o autorizador não é régua nova: é O QUE O MOTOR JÁ PUBLICOU nesta análise.

def _excesso_de_compra_declarado(radar, indicadores):
    """O Motor declarou que se comprou ACIMA do que se vendeu?

    Duas formas, ambas já existentes: a relação `compra × saída` (que só nasce quando
    a identidade do giro fecha) e o estoque subindo entre períodos — que, por
    construção, só é publicado quando as duas pontas têm natureza declarada.

    ⛔ Composição NÃO entra: 64% dos custos serem compra é o normal do comércio."""
    for l in radar or ():
        if "Compra × saída" in l and "acima do que vendeu" in l:
            return True
    for l in indicadores or ():
        if l.startswith("Valor do estoque:") and "(+" in l:
            return True
    return False


# "Nenhuma", "não houve", "-", "0": campo preenchido para dizer que NÃO houve. Tratar
# isso como evento seria pior que não ter o campo.
_NEGATIVO = re.compile(r"^\s*(n[ãa]o|nenhum\w*|nada|sem\b|n/?a|-+|0)\s*[.!]?\s*$", re.I)

def _evento_de_perda_declarado(dados):
    """Existe PERDA REALIZADA declarada — o que de fato não volta?

    Validade vencendo, troca por defeito, avaria. É o contraste que o produto precisa
    saber fazer: mercadoria parada é capital imobilizado e volta quando vender;
    mercadoria vencida não volta."""
    at = _bloco_atual(dados)
    if _texto_do_campo(at, "validade_risco").strip().lower().startswith("sim"):
        return True
    for chave in ("perdas_validade", "trocas"):
        t = _texto_do_campo(at, chave).strip()
        if t and not _NEGATIVO.match(t):
            return True
    return False


# Variação de estoque ENTRE PERÍODOS: "de R$ 20.000 para R$ 24.000", "subiu 20%",
# "aumentou R$ 4.000". ⚠️ Só o que compara duas pontas — dizer o valor de hoje ("o
# estoque é de R$ 24.000") continua livre, porque esse número é do período atual e tem
# natureza declarada.
_VARIACAO_ESTOQUE = re.compile(
    r"\bestoque\b" + _MESMA_FRASE + r"{0,90}?"
    r"(de R\$ ?[\d.,]+ (para|a) R\$ ?[\d.,]+|"
    r"(subiu|aumentou|cresceu|caiu|diminuiu|reduziu|recuou)" + _MESMA_FRASE + r"{0,20}?"
    r"(\d[\d.,]*\s*%|R\$ ?[\d.,]+)|→)|"
    r"(varia[çc][ãa]o|aumento|queda|crescimento|redu[çc][ãa]o)( d[eo])? estoque",
    re.I)

# 🔴 ESTOQUE VIRANDO PERDA — o que o prompt ensinava até 14/08 e o modelo repetiu
# VERBATIM: "o estoque parado de R$ 20.000 também é um dinheiro que já foi gasto e não
# voltou". ⛔ Exige a vizinhança das duas ideias na MESMA frase, e deixa passar a perda
# que é real (validade, avaria, furto) — que é justamente o contraste que o produto
# precisa saber fazer.
_ESTOQUE_COMO_PERDA = re.compile(
    r"\b(estoque|mercadoria parada|encalhe|encalhad\w+)\b" + _MESMA_FRASE + r"{0,90}?"
    r"(dinheiro (que )?(j[áa] )?(foi )?(gasto|perdido)" + _MESMA_FRASE + r"{0,20}(n[ãa]o volt\w+|sumiu)|"
    r"\bperd(a|as|ido|idos|eu)\b|preju[íi]zo|dinheiro jogado)|"
    r"(dinheiro (que )?(j[áa] )?foi gasto" + _MESMA_FRASE + r"{0,20}n[ãa]o volt\w+)" + _MESMA_FRASE + r"{0,60}?\b(estoque|mercadoria)\b",
    re.I)
# ⛔ E o percentual de composição virando causa de perda: "a compra de mercadoria, que
# representou 75% dos custos" sob o título "o que está te fazendo perder dinheiro".
_COMPOSICAO_COMO_PERDA = re.compile(
    r"\b(compra|aquisi[çc][ãa]o)\b" + _MESMA_FRASE + r"{0,60}?\b\d[\d.,]*\s*%" + _MESMA_FRASE + r"{0,30}?\b(dos )?custos?\b|"
    r"\b(representou|representa|corresponde\w*|equivale\w*)\b" + _MESMA_FRASE + r"{0,20}?\d[\d.,]*\s*%"
    r"" + _MESMA_FRASE + r"{0,30}?\bcustos?\b", re.I)

# ⚠️ E A NEGAÇÃO ANALÍTICA CONTA IGUAL. O léxico cobria `desnecessárias` e deixava
# passar "que NÃO SÃO MAIS NECESSÁRIAS" — mesmo juízo, negação solta em vez de
# prefixada. Medido contra a frase real do relatório da Aromática (14/08): "Revisar a
# estratégia de compras para evitar aquisição de mercadorias que não são mais
# necessárias" — o `re.search` devolvia None. Uma trava que só pega uma das duas
# formas do português não é uma trava.
_COMPRA_JULGADA = re.compile(
    r"\b(compra|compras|aquisi[çc][ãa]o|mercadorias?|investimento em estoque)\b" + _MESMA_FRASE + r"{0,80}?"
    r"\b(efica[zc]|ineficaz|ineficiente|acertad\w+|errad\w+|equivocad\w+|"
    r"mal (feita|dimensionada)|desnecess[áa]ri\w+|excessiv\w+|"
    r"n[ãa]o (s[ãa]o|era\w*|foram|s[ãa]o mais|eram mais)? ?(mais )?necess[áa]ri\w+)\b|"
    r"\b(efica[zc]|ineficaz|ineficiente)\b" + _MESMA_FRASE + r"{0,60}?\b(compra|estoque)\b", re.I)

# Intensidade que ninguém apurou. ⚠️ ESTREIA OBSERVANDO — aqui há julgamento de grau,
# e a convenção do `_viol` vale: mede-se a taxa antes de promover.
_INTENSIDADE = re.compile(
    r"\b(significativ\w+|expressiv\w+|consider[áa]v\w+|substancial\w*|"
    r"drasticamente|fortemente|enormemente)\b", re.I)


# Julgamentos que ficam PROIBIDOS quando o lucro informado não fecha. Não é blacklist
# de estilo: é a lista das formas de dizer "este número é bom/ruim" — e o número em
# questão foi retirado da leitura por não fechar.
_JULGA_MARGEM = re.compile(
    r"margem\s+(saud[áa]vel|apertada|boa|ruim|alta|baixa|confort[áa]vel|positiva|"
    r"negativa|forte|fraca|excelente|[óo]tima)", re.I)
_JULGA_LUCRO = re.compile(
    r"lucro" + _MESMA_FRASE + r"{0,40}\b(significativ|positiv|expressiv|s[óo]lid|saud[áa]vel|"
    r"confort[áa]vel|excelente|[óo]tim|bom\b|boa\b|ruim\b|baix|fraco|alto)", re.I)


# Indicadores que o Motor APURA e para os quais NÃO existe régua declarada. Informar
# o número é entrega; dizer se ele é bom ou ruim é juízo sem fonte.
# ⚠️ `margem` fora: ela tem rótulo próprio publicado pelo Motor, e o prompt manda usar.
_INDICADOR_JULGADO = re.compile(
    r"\b(giro|ticket m[ée]dio|convers[ãa]o|capacidade|cobertura|meses de venda)\b"
    r"" + _MESMA_FRASE + r"{0,90}?\b(inadequad\w+|adequad\w+|ruim|p[ée]ssim\w+|bom\b|boa\b|"
    r"saud[áa]vel|preocupante|ideal|excelente|[óo]tim\w+|insuficiente|baix\w+|alt\w+|"
    r"mal (gerenciad|administrad|dimensionad)\w*|gerenciad\w+ de forma)\b", re.I)

_STOPWORDS_ACAO = frozenset("""
a o as os um uma de do da dos das em no na nos nas por para com sem sobre e ou que
se ao aos à às como mais menos até ser está estão foi ser custo resultado dias zero
próximos próximas r$ ~ • - –
""".split())


def _palavras_acao(texto):
    """Palavras de conteúdo de uma ação — o que sobra depois de tirar a moldura."""
    return {p for p in re.findall(r"[a-zA-ZÀ-ÿ]{4,}", (texto or "").lower())
            if p not in _STOPWORDS_ACAO}


def _mesma_acao(a, b):
    """Duas ações dizem a mesma coisa? Sobreposição de palavras de conteúdo ≥ 70%.

    Não é semântica — é medida de repetição literal, que é exatamente o defeito:
    o relatório devolveu as MESMAS frases do ciclo anterior.
    """
    pa, pb = _palavras_acao(a), _palavras_acao(b)
    if len(pa) < 4 or len(pb) < 4:
        return False
    return len(pa & pb) / min(len(pa), len(pb)) >= 0.7


def _acoes_anteriores(dados):
    """As ações que o ciclo anterior recomendou, vindas do bloco do histórico."""
    marca = "DECISÕES RECOMENDADAS NAQUELA ANÁLISE:"
    if marca not in (dados or ""):
        return []
    bloco = dados.split(marca, 1)[1].split("=== DADOS ATUAIS ===")[0]
    return [l.strip() for l in bloco.split("\n") if len(l.strip()) >= 20]


def validar_saida(saida, dados, indicadores, radar):
    """🟠 BLOQUEIO DE SAÍDA — os dados estavam certos e a IA produziu algo inválido."""
    v = []
    permitidos = _numeros_de(dados) | _numeros_de("\n".join(indicadores)) | _numeros_de("\n".join(radar))
    permitidos |= {str(n) for n in range(0, 101)}          # prazo, quantidade de item, %
    metas = set(_secao_da_saida(saida, "METAS"))

    # 0 · 🔴 INVALIDADE PROPAGADA — a checagem que nasce do caso real de 13/08.
    #
    # Quando o Radar publica "Números não fecham", margem e lucro ficaram FORA da
    # leitura. Instrução no prompt não bastou: o modelo escreveu "margem saudável" e
    # "lucro significativo" numa análise em que o próprio Radar dizia que o lucro não
    # fechava. Aqui a saída é REPROVADA e volta para o modelo.
    #
    # ⚠️ As linhas do Radar são puladas: elas são do CÓDIGO e entram na saída
    # literalmente (M3). Sem pular, a própria linha do aviso se autoacusaria.
    if any("Números não fecham" in l for l in (radar or [])):
        linhas_radar = {l.strip() for l in (radar or [])}
        for linha in (saida or "").split("\n"):
            if linha.strip() in linhas_radar:
                continue
            if _JULGA_MARGEM.search(linha) or _JULGA_LUCRO.search(linha):
                v.append(_viol("conclusão sobre número inválido",
                               "o lucro informado não fecha com faturamento menos custos, "
                               "então margem e lucro ficaram fora da leitura — nenhuma "
                               "seção pode julgá-los", linha))

    # 0b · 🔴 ENCALHE LIDO COMO RUPTURA — a troca que INVERTE a decisão.
    #
    # Análise real de 13/08: o lojista declarou o Motorola G17 como item PARADO, e o
    # relatório escreveu *"a baixa do Motorola G17 sugere risco de perda de vendas se
    # não houver estoque adequado"*. Encalhe pede liquidar; ruptura pede repor. São
    # decisões opostas, e o produto recomendou a errada sobre o item certo.
    #
    # ⚠️ A checagem é NOMINAL de propósito: só dispara quando o ITEM que o lojista
    # declarou encalhado aparece na mesma frase que vocabulário de falta. Não julga
    # o raciocínio — confere se um fato declarado foi invertido.
    _item_encalhe = re.search(r"^\s*encalhe_item\s*:\s*(.+)$", dados or "", re.M | re.I)
    if _item_encalhe:
        alvo = _item_encalhe.group(1).strip()
        if len(alvo) >= 3:
            _RUPTURA = re.compile(r"faltar|falta d|em falta|ruptura|repor|reposi[çc]|"
                                  r"sem estoque|estoque adequado|acabar o estoque", re.I)
            for linha in (saida or "").split("\n"):
                if alvo.lower() in linha.lower() and _RUPTURA.search(linha):
                    v.append(_viol("encalhe tratado como falta",
                                   f"'{alvo}' foi declarado como item PARADO/baixa saída; "
                                   f"dizer que ele pode faltar ou precisa de reposição "
                                   f"inverte a decisão", linha))

    # 0j · 🔴 VARIAÇÃO DE ESTOQUE ENTRE NATUREZAS INCOMPATÍVEIS — e esta BLOQUEIA.
    #
    # O Motor parou de publicar a comparação, mas os DOIS valores crus continuam no
    # payload (um em cada bloco de período) e o modelo sabe subtrair. Tirar a linha do
    # Radar não impede a frase de nascer na prosa.
    #
    # ⚖️ Exceção do #099, e ela se aplica inteira: a falha é DETERMINÍSTICA (ou o
    # `estoque_base` está declarado nas duas pontas, ou não está), a dependência é
    # EXPLÍCITA (a variação depende das duas pontas terem a mesma natureza), e a saída
    # CONTRADIZ um fato que o próprio NEXO já publicou no Radar — "misturar daria um
    # número errado". Não há o que discutir, então não se observa: bloqueia.
    if not _base_estoque(_bloco_atual(dados)) or not _base_estoque(_bloco_anterior(dados)):
        for linha in (saida or "").split("\n"):
            if linha.strip() in {l.strip() for l in (radar or [])}:
                continue
            if _VARIACAO_ESTOQUE.search(linha):
                v.append(_viol("variação de estoque entre naturezas incompatíveis",
                               "o Radar já declarou que os dois períodos não foram "
                               "informados pelo mesmo critério — a mesma razão que "
                               "impede o giro impede a variação", linha))

    # 0i · 🟡 FATO REQUALIFICADO EM PERDA — a retaguarda das duas correções de 14/08.
    #
    # A causa primária das duas era o PRÓPRIO PRODUTO, e foi consertada onde nasceu: a
    # frase "dinheiro que já foi gasto e não voltou" saiu do bloco de estoque, e a
    # proibição de tratar composição como sangria entrou. Isto aqui é o que sobra
    # depois — o modelo chegando ao mesmo lugar por conta própria.
    #
    # ⚠️ ESTREIA OBSERVANDO, as duas. A convenção do `_viol` vale integralmente: a
    # exceção do #099 não alcança nenhuma delas, porque aqui não há fato que o NEXO
    # já tenha invalidado — há uma qualificação econômica discutível, e "a compra subiu
    # 40% enquanto a venda subiu 5%" é evidência LEGÍTIMA de excesso que não pode ser
    # bloqueada por parecer com o que não é. Mede-se a taxa antes de promover.
    _suspeitas = (_secao_da_saida(saida, "PERDER DINHEIRO")
                  + _secao_da_saida(saida, "ALERTAS")
                  + _secao_da_saida(saida, "DECISÃO MAIS IMPORTANTE"))
    # 🔑 E O GATE É A AUTORIZAÇÃO DO MOTOR, não a palavra. Havendo evento de perda
    # declarado, "perda" está autorizada e a frase passa; havendo excesso de compra
    # declarado, o juízo sobre a compra passa. Sem eles, BLOQUEIA — porque aí não é
    # uma frase discutível, é uma conclusão sem nada que a sustente.
    perda_ok = _evento_de_perda_declarado(dados)
    compra_ok = _excesso_de_compra_declarado(radar, indicadores)
    for linha in _suspeitas:
        if not perda_ok and _ESTOQUE_COMO_PERDA.search(linha):
            v.append(_viol("estoque tratado como perda sem evento de perda",
                           "mercadoria parada é capital IMOBILIZADO — volta quando ela "
                           "vender. Perda é o que venceu, estragou ou foi devolvido sem "
                           "retorno, e nada disso foi declarado nesta análise", linha))
        if not compra_ok and _COMPOSICAO_COMO_PERDA.search(linha):
            v.append(_viol("composição de custo tratada como perda",
                           "percentual de composição diz PARA ONDE o dinheiro foi, não "
                           "que foi mal gasto — e o Motor não apurou compra acima da "
                           "saída nem estoque subindo que sustentem a conclusão", linha))

    # 0c · 🔴 VARIAÇÃO SEM PERÍODO ANTERIOR — conclusão sem origem, sem cifra.
    #
    # Análise real de 13/08, PRIMEIRA do negócio: *"O faturamento cresceu, mas os
    # custos também subiram"*. Não havia com o que comparar. Nenhum número foi
    # inventado — por isso a checagem 1 não pegou — mas a AFIRMAÇÃO de variação foi.
    #
    # ⚠️ Nominal nos apurados: o lojista pode declarar variação dele ("o fluxo caiu
    # 10%") e isso continua sendo fato dele, não invenção do produto.
    if "=== ANÁLISE ANTERIOR" not in (dados or ""):
        for linha in (saida or "").split("\n"):
            if linha.strip() in {l.strip() for l in (radar or [])}:
                continue
            if _APURADO_VARIA.search(linha):
                v.append(_viol("variação sem período anterior",
                               "esta é a primeira análise do negócio — não há com o que "
                               "comparar, então nada cresceu, caiu ou subiu", linha))

    # 0d · 🔴 FALTA VIRANDO IMPACTO CONSUMADO.
    # *"A falta de capa pode ter IMPACTADO as vendas"* — a falta comprova RUPTURA.
    # Não comprova que venda alguma deixou de acontecer: ninguém mediu isso.
    # ✅ O permitido é RISCO: "a falta da capa cria risco de perda de vendas".
    for linha in (saida or "").split("\n"):
        if linha.strip() in {l.strip() for l in (radar or [])}:
            continue
        if _FALTA_IMPACTO.search(linha) and not re.search(r"\brisco\b", linha, re.I):
            v.append(_viol("falta tratada como impacto medido",
                           "a ruptura comprova que faltou, não que a venda caiu por "
                           "causa dela — o permitido é falar em RISCO", linha))

    # 0e · 🔴 JUÍZO SOBRE A QUALIDADE DA COMPRA.
    # *"a compra de R$ 38.000 indica que o investimento em estoque pode não ter sido
    # totalmente eficaz"* — compra ser 84,4% dos custos é COMPOSIÇÃO, não veredito.
    # Nenhum campo do formulário mede se a compra foi acertada.
    # 🔑 MESMO GATE DA 0i: o juízo sobre a compra passa a ser permitido QUANDO o Motor
    # apurou excesso — comprou acima do que vendeu, ou o estoque subiu entre períodos
    # comparáveis. Antes de 14/08 esta trava era cega nos dois sentidos: bloqueava a
    # conclusão verdadeira e não tinha como distinguir.
    if not _excesso_de_compra_declarado(radar, indicadores):
        for linha in (saida or "").split("\n"):
            if linha.strip() in {l.strip() for l in (radar or [])}:
                continue
            if _COMPRA_JULGADA.search(linha):
                v.append(_viol("juízo sobre a compra sem dado que o sustente",
                               "a composição do custo diz QUANTO foi comprado, não se a "
                               "compra foi acertada — e o Motor não apurou compra acima "
                               "da saída nem estoque subindo nesta análise", linha))

    # 0f · 🟡 INTENSIDADE NÃO APURADA — *"impactaram SIGNIFICATIVAMENTE o lucro"*.
    # ⚠️ ESTREIA OBSERVANDO, e de propósito: aqui há julgamento de grau, e a convenção
    # do `_viol` vale integralmente. A exceção do #099 não alcança este caso — ele não
    # é determinístico. Mede-se a taxa de disparo antes de promover.
    for linha in (saida or "").split("\n"):
        if linha.strip() in {l.strip() for l in (radar or [])}:
            continue
        if _INTENSIDADE.search(linha):
            v.append(_viol("intensidade não apurada",
                           "grau ('significativo', 'expressivo') não sai de nenhum "
                           "número calculado", linha, observa=True))

    # 0g · 🔴 "MUDE A ABORDAGEM" SEGUIDO DA MESMA ABORDAGEM.
    #
    # Análise real de 13/08: o §2 disse *"o caminho não é insistir — é mudar a
    # abordagem"* e o §7 devolveu **as três ações do ciclo anterior**, que o próprio
    # §2 registrava como executadas. O relatório se contradiz dentro de si mesmo e
    # manda o lojista repetir o que ele acabou de cumprir.
    if re.search(r"não é insistir|mudar a abordagem|trocar de estrat", saida or "", re.I):
        anteriores = _acoes_anteriores(dados)
        if anteriores:
            for linha in _secao_da_saida(saida, "AÇÕES"):
                if len(linha.strip()) < 20:
                    continue
                if any(_mesma_acao(linha, ant) for ant in anteriores):
                    v.append(_viol("manda mudar e repete a mesma ação",
                                   "o ciclo disse que não é para insistir, e esta ação "
                                   "repete o que já foi recomendado e executado", linha))

    # 0h · 🔴 INDICADOR SEM BENCHMARK VIRANDO JUÍZO DE QUALIDADE.
    #
    # *"giro de 2,27x [...] pode ser um sinal de que o estoque está sendo gerenciado
    # de forma INADEQUADA"*. O número sozinho não demonstra nada: não existe
    # benchmark declarado que autorize a qualificação. O Motor pode INFORMAR o giro;
    # não pode julgá-lo.
    #
    # ⚠️ `margem` fica de fora: para ela o Motor PUBLICA um rótulo próprio, e o prompt
    # manda usar exatamente aquele. Onde há régua declarada, há juízo autorizado.
    for linha in (saida or "").split("\n"):
        if linha.strip() in {l.strip() for l in (radar or [])}:
            continue
        if _INDICADOR_JULGADO.search(linha):
            v.append(_viol("indicador sem benchmark virando juízo",
                           "não há régua declarada que diga se este número é bom ou "
                           "ruim — o Motor informa o indicador, não o qualifica", linha))

    # 1 · número sem fonte (a seção de METAS é alvo proposto, tratada abaixo)
    for linha in (saida or "").split("\n"):
        if re.match(r"^[^\w\d]*\d+\.\s", linha) or linha.strip() in metas:
            continue
        for n in _numeros_de(linha):
            if n not in permitidos and len(n.replace(",", "")) >= 3:
                v.append(_viol("número sem fonte", f"o valor {n} não está nos dados nem nas "
                               f"linhas calculadas", linha))

    # 2 · meta sem ponto de partida escrito
    for linha in metas:
        # Linha sem número não é meta — é o convite de fechamento da seção ou a linha
        # do fallback. Falso positivo medido na fase de observação, em 04/08.
        if len(linha) < 12 or not re.search(r"\d", linha):
            continue
        # 'de X para Y' e também 'manter em X ou mais', que é meta de defesa legítima
        # e traz o ponto de partida escrito. Falso positivo medido em 04/08.
        tem_partida = (re.search(r"\bde\s+R?\$?\s*[\d.,]+\s*%?\s+para\s+R?\$?\s*[\d.,]+", linha, re.I)
                       or re.search(r"\bmanter\b" + _MESMA_FRASE + r"{0,40}?R?\$?\s*[\d.,]+\s*%?", linha, re.I))
        if not tem_partida:
            v.append(_viol("meta sem ponto de partida",
                           "toda meta escreve o valor atual: 'de [atual] para [alvo]' "
                           "ou 'manter em [atual] ou mais'", linha))
        # meta sobre variável que o formulário não mede
        proibida = re.search(r"\b(estoque|encalh\w+|desconto|custos?)\b", linha, re.I)
        if proibida and re.search(r"\d+\s*%|\bem\s+\d", linha, re.I):
            v.append(_viol("meta sobre variável não autorizada",
                           f"meta sobre '{proibida.group(1).lower()}' não tem ponto de partida no "
                           f"formulário — use margem, lucro, faturamento ou ticket médio", linha))

    # 3 · as metas têm de fechar entre si
    alvo = {}
    for linha in metas:
        m = re.search(r"para\s+R?\$?\s*([\d.,]+)\s*(%?)", linha, re.I)
        if not m:
            continue
        try:
            valor = float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            continue
        chave = ("margem" if m.group(2) == "%" else
                 "faturamento" if "fatura" in linha.lower() else
                 "lucro" if "lucro" in linha.lower() else None)
        if chave:
            alvo[chave] = valor
    if {"faturamento", "margem", "lucro"} <= set(alvo):
        esperado = alvo["faturamento"] * alvo["margem"] / 100
        if abs(esperado - alvo["lucro"]) > max(0.02 * alvo["lucro"], 50):
            v.append(_viol("metas não fecham entre si",
                           f"faturamento {_fmt_br(alvo['faturamento'])} × margem "
                           f"{_fmt_br(alvo['margem'])}% dá {_fmt_br(esperado)}, mas a meta de "
                           f"lucro é {_fmt_br(alvo['lucro'])}"))

    # 4 · ação sem prazo/custo declarado, e custo fora da verba que o cliente informou
    teto = _teto_da_verba(dados)
    for linha in _secao_da_saida(saida, "AÇÕES IMEDIATAS"):
        if len(linha) >= 25 and "Resultado em" not in linha:
            v.append(_viol("ação sem prazo", "toda ação termina com (Custo: … | Resultado em: …)",
                           linha))
        m = re.search(r"Custo:\s*R?\$?\s*([\d.,]+)", linha, re.I)
        if m and teto is not None:
            try:
                custo = _pct_do_texto(m.group(1))
            except ValueError:
                custo = None
            if custo is not None and custo > teto:
                v.append(_viol("ação acima da verba informada",
                               f"a ação custa R$ {_fmt_br(custo)} e o cliente informou até "
                               f"R$ {_fmt_br(teto)} para melhorias", linha))

    # 5 · decisão sem ação que a execute
    decisao = " ".join(_secao_da_saida(saida, "DECISÃO MAIS IMPORTANTE"))
    acoes = " ".join(_secao_da_saida(saida, "AÇÕES IMEDIATAS")).lower()
    if decisao and acoes:
        genericas = {"produtos", "estoque", "porque", "dessas", "depois", "aumentar", "custos",
                     "margem", "vendas", "proximos", "próximos", "analise", "análise", "periodo",
                     "período", "importante", "decisao", "decisão", "agora", "nesta", "sobre"}
        chaves = {p for p in re.findall(r"[a-zà-ÿ]{5,}", decisao.lower()) if p not in genericas}
        if chaves and sum(1 for p in chaves if p in acoes) / len(chaves) < 0.25:
            v.append(_viol("decisão sem ação correspondente",
                           "nenhuma das ações imediatas executa a decisão principal", decisao))

    # 6 · comparação inconsistente ('de X para Y (+Z%)' com Z que não bate)
    for m in re.finditer(r"R?\$?\s*([\d.]+(?:,\d+)?)\s*(?:→|para)\s*R?\$?\s*([\d.]+(?:,\d+)?)"
                         r"[^()\n]{0,25}\(\s*([+-]?[\d,]+)\s*%", saida or ""):
        try:
            a = float(m.group(1).replace(".", "").replace(",", "."))
            b = float(m.group(2).replace(".", "").replace(",", "."))
            z = float(m.group(3).replace(",", "."))
        except ValueError:
            continue
        if a and abs((b - a) / abs(a) * 100 - z) > 0.6:
            v.append(_viol("comparação inconsistente",
                           f"{m.group(1)} → {m.group(2)} dá {(b - a) / abs(a) * 100:.1f}%, "
                           f"não {m.group(3)}%", m.group(0)))

    # 7 · cifra de estoque parado que o código não autorizou (#083)
    # Pega onde a checagem 1 é cega — linha de ação numerada e seção de METAS, que
    # é justamente onde a cifra do estoque reaparece — e pega o que ela não vê:
    # número que ESTÁ nos dados mas está no lugar errado (o R$ 21.000 da compra da
    # coleção citado como se fosse o valor parado).
    valor_estoque = _valor_estoque(dados)[0]
    # 🔴 O VALIDADOR JULGA O QUE O MODELO ESCREVEU — NUNCA O QUE O CÓDIGO PUBLICOU.
    # Linha do Radar entra no texto final literalmente (`_garantir_secao`), então
    # varrê-la é auditar a própria apuração. E dava falso positivo real: o `📦 Giro do
    # estoque: R$ 28.000 saiu...` era acusado de "cifra de estoque diferente da
    # informada" porque 28.000 (a SAÍDA do período) está perto da palavra estoque e
    # difere dos 22.000 parados. Medido em produção 10/08 19:30. Marcado `observa`, não
    # bloqueava — mas poluía o log e bloquearia no dia em que a checagem 7 fosse
    # promovida, que é justamente o que a fase de observação existe para decidir.
    # Radar E Metas: as duas seções que `_entregar` repõe por código. Buscar as metas
    # aqui, em vez de recebê-las por parâmetro, é de propósito — assim a isenção não
    # depende de quem chama lembrar de passá-las, e não há como o defeito voltar por
    # esquecimento numa chamada nova.
    def _sem_marca(l):
        return l.strip().lstrip("•").strip()
    publicadas = {_sem_marca(l) for l in radar} | {_sem_marca(l) for l in _bloco_metas(dados)}
    for linha in (saida or "").split("\n"):
        if _sem_marca(linha) in publicadas:
            continue
        for m in _RE_CIFRA_ESTOQUE.finditer(linha):
            if m.group(2):                                  # percentual: outra regra
                continue
            # Só conta se a cifra estiver PERTO da fala de estoque parado…
            ini, fim = max(0, m.start() - 60), min(len(linha), m.end() + 60)
            if not re.search(r"estoque|encalh|parad[oa]|coleç", linha[ini:fim], re.I):
                continue
            # …e se ela não pertencer, visivelmente, a OUTRA grandeza. O §4 compara o
            # estoque com o lucro na mesma frase ("é mais do que o lucro do mês, R$ X")
            # e sem isto o lucro era acusado de ser estoque errado. Falso positivo
            # medido no teste de 05/08, na estrutura que a própria maquete usa.
            antes = linha[max(0, m.start() - 30):m.start()]
            if re.search(r"lucro|faturamento|custos?|meta|ticket|margem|verba", antes, re.I):
                continue
            achado = _num_br(m.group(1))
            if achado is None:
                continue
            if valor_estoque is None:
                v.append(_viol("cifra de estoque sem fundamento",
                               f"o produto afirmou R$ {m.group(1)} de estoque, e o campo de "
                               f"estoque não permite determinar valor nenhum com segurança. "
                               f"Escreva: \"{FRASE_ESTOQUE_SEM_VALOR}\"",
                               linha, observa=True))
            elif abs(achado - valor_estoque) > 0.01:
                v.append(_viol("cifra de estoque diferente da informada",
                               f"o produto afirmou R$ {m.group(1)} de estoque, e o cliente "
                               f"escreveu R$ {_fmt_br(valor_estoque)}", linha, observa=True))
    return v

def _registrar(fase, segmento, violacoes, extra=""):
    """Log estruturado da fase de observação — é o dado que decide quando ativar o
    bloqueio, e qual regra ainda dá falso positivo."""
    if not violacoes:
        print(f"VALIDADOR|{fase}|{segmento}|ok|0|{extra}")
        return
    for x in violacoes:
        # O marcador obs/ativa é o dado que decide quando promover uma checagem nova:
        # sem ele não se sabe a taxa de disparo nem quantos eram falso positivo.
        marca = "obs" if x.get("observa") else "ativa"
        print(f"VALIDADOR|{fase}|{segmento}|{marca}|{x['regra']}|{x['detalhe']}|{x['trecho']}|{extra}")

def _texto_das_violacoes(violacoes):
    linhas = [f"- {x['regra'].upper()}: {x['detalhe']}" +
              (f"  (na linha: «{x['trecho']}»)" if x["trecho"] else "") for x in violacoes]
    return "\n".join(linhas)

def _fallback_apurado(bruto, dados, indicadores, radar, segmento):
    """FALLBACK CONTROLADO — e ele NÃO joga fora o que o código garantiu.

    O Radar, o §2 e as Metas são escritos por CÓDIGO e estão certos
    independentemente do que o modelo fez: quem falhou foi a interpretação, não a
    apuração. Medido em produção 05/08 12:43 — uma rodada caiu aqui e o cliente
    recebeu UMA FRASE no lugar da análise, com o Motor tendo calculado tudo.

    ⚠️ `bruto` pode ser "" — é o caso em que a retentativa nem chegou a existir
    (exceção). Aí só há as seções apuradas, que é exatamente o que se quer."""
    secoes = _em_secoes(bruto)
    _garantir_secao(secoes, "RADAR", "RADAR DO NEGÓCIO", list(radar))
    _garantir_secao(secoes, "CICLO", "O CICLO ANTERIOR", _bloco_ciclo(dados, indicadores))
    _garantir_secao(secoes, "METAS", "METAS ATÉ A PRÓXIMA ANÁLISE", _bloco_metas(dados))
    apuradas = [s for s in secoes if s["origem"] == "codigo"]
    if not apuradas:
        return FALLBACK_SEGURO, []
    apuradas.append({"n": None, "titulo": None, "origem": "codigo", "linhas": [
        _linha_estruturada("Os números acima foram apurados e conferidos. A leitura e as "
                           "recomendações desta análise não puderam ser produzidas com "
                           "segurança desta vez — rode a análise novamente.")]})
    print(f"PUBLICACAO|{segmento}|fallback-parcial|secoes-apuradas={len(apuradas) - 1}")
    return _texto_de_secoes(apuradas), apuradas

def gerar_analise(dados, segmento, modelo=None):
    # 🔴 CAUSA A: revisão do mesmo período não é ciclo — a defesa vem ANTES de tudo,
    # para que Motor, giro, §2 e comparações vejam a mesma leitura já saneada.
    dados = _neutralizar_revisao(dados)
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
            "curtas (🔴/🟡/🟢) sobre pontos NÃO numéricos — estoque, fornecedor, reclamação. Nada de rótulo, marcador "
            "ou sufixo entre parênteses no fim delas. E nada de fechamento aqui: a leitura dos números é a seção 2."
        ]
    else:
        secoes = [
            "📌 1. DIAGNÓSTICO GERAL\n"
            "O que os números mostram, em 2 a 4 linhas diretas — o que está indo bem e o que está apertando, "
            "citando os números que provam (margem, faturamento vs meta). Sem suavizar e sem dramatizar."
        ]
    num = 2
    # §2 CICLO ANTERIOR — o miolo é escrito por CÓDIGO (_bloco_ciclo). O prompt
    # reserva a POSIÇÃO: sem ela declarada aqui, a seção seria acrescentada no fim
    # e o relatório sairia fora da ordem do mapa. O que o modelo escreve aqui é
    # descartado quando há histórico; serve de rede se a substituição falhar.
    if tem_historico:
        secoes.append(
            f"🔄 {num}. O CICLO ANTERIOR\n"
            "Compare os números atuais com os da análise anterior, com os valores lado a lado. "
            "Fale sempre do RESULTADO, nunca da conduta do dono: diga o que os números mostram, "
            "jamais se ele executou ou deixou de executar — isso só o próprio lojista declara."
        )
        num += 1
    # Oito números viram uma frase que o dono entende sem fazer conta. Vem depois do
    # Radar e do Ciclo porque é a leitura deles, não uma seção nova de conteúdo.
    secoes.append(
        f"🧭 {num}. DIAGNÓSTICO CENTRAL\n"
        "Duas partes, nesta ordem e nada além disso:\n"
        "• UMA FRASE CURTA, em linguagem de dono de loja, dizendo o que aconteceu no período "
        "(ex.: 'Você vendeu mais, mas ganhou menos.' · 'Você vendeu menos e ainda gastou mais.' · "
        "'Você vendeu mais e ganhou mais.'). Sem jargão, sem número nessa frase.\n"
        "• UM PARÁGRAFO curto com os números que sustentam a frase, tirados das linhas calculadas "
        "(EXEMPLO GENÉRICO — NÃO REUTILIZAR: 'O faturamento cresceu X%, enquanto os custos cresceram Y%. Como "
        "resultado, o lucro variou Z% e a margem líquida passou de A% para B%.' X, Y, Z, A e B são marcadores de "
        "ESTRUTURA. Nunca reproduzi-los literalmente; substituir só pelos valores calculados deste negócio).\n"
        "O Diagnóstico Central sai SEMPRE dos dados do negócio atual. Nunca copiar números, nomes, produtos, "
        "fornecedores, metas ou conclusões de exemplo algum deste prompt.\n"
        "Não repita isto nas outras seções e não emende recomendação aqui — diagnóstico é o que É, "
        "não o que fazer."
    ); num += 1
    # A antiga seção EVOLUÇÃO DESDE A ÚLTIMA ANÁLISE foi REMOVIDA daqui: ela e o
    # §2 CICLO ANTERIOR falavam da mesma coisa, e duas seções sobre o mesmo
    # assunto é a doença que o mapa das 8 veio curar. O que ela tinha de valor
    # migrou para o CÓDIGO: as quatro linhas do APRENDIZADO viraram a tabela de
    # leitura do _bloco_ciclo, e a ordem de 'reportar TODAS as comparações' virou
    # publicação garantida — pedir ao modelo que percorresse as linhas nunca
    # garantiu que ele percorresse.
    # ⬇️ A ORDEM DO MAPA APROVADO: primeiro o que está sangrando e o que ameaça,
    # depois a escolha e a execução. Decidir antes de mostrar a perda punha a
    # decisão sem lastro na página — o dono lia a conclusão antes da evidência.
    secoes.append(
        f"⚠️ {num}. O QUE ESTÁ TE FAZENDO PERDER DINHEIRO\n"
        "Onde o dinheiro está saindo AGORA e onde ele está parado podendo voltar — "
        "as duas coisas nesta seção, porque para o dono é o mesmo bolso.\n"
        "Até 4 linhas, cada uma com o número que a prova quando ele existir nos dados:\n"
        "• O QUE SANGRA — custo que subiu mais que a venda, desconto que comeu a margem, "
        "perda por validade ou defeito. Se o cliente informou ONDE está a melhor e a pior "
        "margem, use as palavras dele para dizer o que está drenando — e continua PROIBIDO "
        "afirmar qual é a margem de um item que ele só nomeou.\n"
        # 🔴 A FRASE SAIU EM 14/08, e ela era do PRODUTO, não do modelo. O relatório da
        # Aromática publicou "o estoque parado de R$ 20.000 também é um dinheiro que já
        # foi gasto e não voltou" — VERBATIM daqui. Fiscal nenhum pegaria: o modelo
        # estava obedecendo.
        #
        # ⛔ E ela é FALSA para estoque. Mercadoria parada é capital IMOBILIZADO — o
        # dinheiro está lá e volta quando ela vender. O que não volta é o que venceu ou
        # estragou, e para isso existe campo próprio. A mesma sentença é verdadeira na
        # dica de validade do app (`nexo_analise.py`), e foi de lá que ela veio parar
        # aqui, aplicada ao lugar errado.
        "• O QUE ESTÁ PARADO — capital imobilizado: dinheiro que já saiu e só volta quando a "
        "mercadoria vender. Estoque encalhado, crédito com fornecedor, devolução pendente. "
        "NÃO é perda: perda é o que venceu, estragou ou foi devolvido sem retorno. Diga o "
        "valor SÓ quando ele estiver nos dados.\n"
        "• O QUE ESTÁ ESBARRANDO — cliente que já está chegando e não fecha: fricção declarada, "
        "demora de resposta, reclamação, horário sem atendimento.\n"
        "Se algum desses não tiver base nos dados, simplesmente não escreva a linha. "
        "Não invente para preencher, e não repita aqui o que a seção de decisão vai dizer.\n"
        # 🔴 O TÍTULO DA SEÇÃO NÃO É EVIDÊNCIA. Posto sob "o que está te fazendo perder
        # dinheiro", todo número vira sangria — foi assim que "a compra de mercadoria
        # representou 75% dos custos" virou causa de perda no relatório da Aromática.
        # 75% é COMPOSIÇÃO: diz para onde o dinheiro foi, não que foi mal gasto.
        "⛔ COMPOSIÇÃO NÃO É PERDA. Que a compra de mercadoria seja a maior fatia do custo é "
        "o NORMAL do comércio — é assim que a loja tem o que vender. Só escreva a compra "
        "nesta seção se houver EVIDÊNCIA de excesso nos dados: comprou mais do que vendeu no "
        "período, estoque subindo ciclo após ciclo, ou o próprio lojista declarando sobra. "
        "Percentual de composição, sozinho, NUNCA sustenta essa linha."
    ); num += 1
    secoes.append(
        f"🚨 {num}. ALERTAS\n"
        "Até 3 riscos latentes que ainda NÃO estão custando dinheiro — se já está custando, "
        "é a seção anterior. Aqui é o que ameaça o próximo ciclo.\n"
        "Antes de escrever, VARRA os campos de PRODUTOS VENCENDO (cite o valor e a DATA quando o "
        "cliente informou — validade sem prazo é descrição, com prazo é alerta), O QUE FALTOU "
        "(item que o cliente procurou e não havia: quem não encontra compra em outro lugar e "
        "muitas vezes não volta), reclamações, trocas/defeitos, fornecedores (atrasos e "
        "defeitos recorrentes — cite o nome do fornecedor quando informado, e NUNCA atribua a um fornecedor o defeito "
        "que os dados atribuem a outro) e tendência de queda em qualquer número. "
        "Defeito ou atraso de fornecedor citado nos dados é SEMPRE alerta — mas descreva o FATO ('3 blusas com "
        "desfiado na costura'), nunca um veredito sobre a empresa ('problemas de qualidade', 'reavaliar a parceria'). "
        "DEPENDÊNCIA DE CANAL — REGRA: só classificar um canal como 'dependência' ou 'risco de dependência' quando "
        "esse canal representar MAIS DE 50% das vendas do período. Igual ou abaixo de 50%, não usar os termos "
        "'dependência', 'dependência alta' nem 'risco de dependência'. Canal que cresceu e permanece em 50% ou menos "
        "é OPORTUNIDADE DE CRESCIMENTO, nunca dependência. "
        "Somente se realmente não houver nenhum risco nos dados, escreva apenas: Nenhum alerta crítico neste período."
        # NOTA FIXA, não alerta condicional: nenhum campo carrega perfil de compra
        # de acessório, então fingir gatilho seria fabricar precisão. A fonte é
        # primária (Anatel/gov.br) e o número foi conferido em 05/08.
        + ("\nNOTA FIXA DESTE SEGMENTO — escreva SEMPRE, como última linha da seção, "
           "exatamente assim: 'Homologação Anatel: entre janeiro de 2025 e janeiro de "
           "2026 foram retirados de circulação 1,39 milhão de produtos irregulares, em "
           "maioria carregadores e roteadores. Confira a homologação do que você "
           "compra.' Não a transforme em alerta condicional nem altere o número: ela "
           "não depende dos dados deste cliente."
           if segmento == "Celular e Acessórios" else "")
    ); num += 1
    secoes.append(f"🎯 {num}. DECISÃO MAIS IMPORTANTE AGORA\nUma única decisão crítica e direta, "
                  f"e ela responde à MAIOR perda apurada na seção anterior."); num += 1
    secoes.append(
        f"🔧 {num}. AÇÕES IMEDIATAS\n"
        "No máximo 3 ações práticas, executáveis e simples, compatíveis com a verba informada. "
        "Cada ação obedece à REGRA DA ALAVANCA NOMEADA: alavanca + alvo + direção, com número. "
        "Se os dados citam DEFEITO ou ATRASO de fornecedor, uma das ações é ACIONAR esse fornecedor "
        "(troca, crédito ou substituição das peças, com o nome dele e a quantidade que está nos dados) — "
        "é dinheiro de volta a custo zero, e alerta passivo não recupera nada. "
        "Se há reclamação repetida de clientes sobre um produto (numeração, tamanho, defeito), "
        "trate-a como conserto barato e concreto, não como observação. "
        "Ao final de CADA ação, acrescente uma tag curta entre parênteses com o custo e o prazo de resultado, "
        "neste formato exato: (Custo: zero | Resultado em: ~7 dias). "
        "Use valores realistas em reais (ou 'zero') e prazos aproximados. Não use notas, pontuações ou percentuais de prioridade.\n"
        # 🔴 A AÇÃO NÃO PODE EMPOBRECER O QUE O FORMULÁRIO CONQUISTOU. Relatório da
        # Aromática (14/08): o lojista declarou item=Perfume, valor=R$ 250 e prazo=30
        # dias — e a ação saiu "verificar a validade dos perfumes". O produto pediu que
        # ele conferisse o que ele acabou de informar.
        #
        # ⛔ NUNCA mandar VERIFICAR, LEVANTAR, CHECAR ou MAPEAR um dado que já está nos
        # dados. Se o cliente informou item, valor e prazo, a ação AGE sobre eles.
        "⛔ NÃO peça ao lojista para VERIFICAR, CONFERIR, LEVANTAR ou MAPEAR aquilo que ele "
        "JÁ INFORMOU. Se um campo traz o item, o valor e o prazo, a ação usa os TRÊS e diz o "
        "que FAZER com eles. Errado: 'verificar a validade dos perfumes'. Certo: 'priorizar o "
        "Perfume com R$ 250 em risco de validade nos próximos 30 dias e definir a ação de giro "
        "antes desse prazo'. Ação que devolve a pergunta ao cliente não é ação."
    ); num += 1
    secoes.append(
        f"🧭 {num}. METAS ATÉ A PRÓXIMA ANÁLISE\n"
        "RELAÇÃO ENTRE AÇÕES E METAS: as metas derivam DIRETAMENTE das ações recomendadas acima. Para cada meta, "
        "tem de ser possível apontar qual ação contribui para alcançá-la. Não criar meta independente nem "
        "desconectada. Priorizar as metas ligadas à Decisão Mais Importante e às Ações Imediatas. "
        "Se uma ação não sustentar uma meta numérica autorizada, NÃO invente meta só para preencher a seção.\n"
        "2 a 3 metas, todas com PRAZO 'até a próxima análise' — nunca 60 ou 90 dias, porque a próxima análise é a "
        "que confere. Cada meta sai de um CAMPO NUMÉRICO do formulário e ESCREVE O VALOR ATUAL como partida: "
        "'de [valor calculado] para [alvo]'. Meta sem o valor de partida na frase é inválida. "
        "🚫 PROIBIDO meta sobre quantidade de estoque, percentual de encalhe vendido, percentual de desconto ou "
        "corte de custo — o formulário não tem esses números. Se a decisão do período for sobre estoque, a meta "
        "correspondente é o que o estoque DEVE MOVER: margem, lucro, faturamento ou ticket. "
        "Nada de 'melhorar o atendimento'.\n"
        "Se este período não trouxer campo numérico suficiente para duas metas, escreva as que der e uma linha: "
        "'as demais metas dependem de preencher [campo] na próxima análise'. Nunca invente o valor de partida.\n"
        "EXCEÇÃO PARA MULTICANAL: quando o segmento for Multicanal e não existir campo numérico específico para "
        "calcular a meta de uma variável, NÃO invente o valor de partida — use uma das variáveis autorizadas que "
        "estiver disponível (faturamento, lucro, margem, ticket médio). Se nenhuma estiver, não crie meta numérica "
        "para essa categoria e escreva: 'as demais metas dependem de preencher [campo] na próxima análise'.\n"
        "ORDEM DE PRIORIDADE do relatório: 1) decisão mais importante agora · 2) ações imediatas · 3) metas "
        "derivadas dessas ações · 4) próxima análise para verificar o resultado. "
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

    # O ESTOQUE PARADO — quem lê a cifra é o código, não o modelo (#083).
    # Certeza usa, dúvida cala. A instrução abaixo é o pedido; a garantia é a
    # checagem 7 do validador, porque instrução de prompt sobre número já provou
    # não bastar (o PDF de agosto saiu com 16,8% tendo "reproduza exatamente" escrito).
    # 🔴 E O RÓTULO SEGUE A NATUREZA DECLARADA. Enquanto este bloco entregava o número
    # como "ESTOQUE PARADO", o modelo obedecia — e o relatório da Aromática (14/08)
    # chamou de parado o estoque inteiro do lojista, em quatro lugares, com a decisão
    # mais importante da análise construída em cima disso.
    valor_estoque, motivo_estoque = _valor_estoque(dados)
    total = _base_estoque(_bloco_atual(dados))
    rotulo = "VALOR TOTAL DO ESTOQUE" if total else "VALOR DO ESTOQUE INFORMADO"
    como_falar = ("o valor total do estoque" if total else
                  "o valor do estoque que o cliente informou")
    if valor_estoque is not None:
        bloco_motor += (f"{rotulo} — LIDO DO QUE O CLIENTE ESCREVEU: "
                        f"R$ {_fmt_br(valor_estoque)}.\n"
                        f"Use EXATAMENTE este valor ao falar do estoque. É PROIBIDO "
                        f"escrever qualquer outro valor em reais para o estoque.\n")
        if total:
            # ⛔ A distinção que faltava: total ≠ encalhado. Sem esta linha o modelo
            # tratava o estoque inteiro como mercadoria parada — que é o que ele fez.
            bloco_motor += ("Este é o estoque TOTAL, não o encalhado: é PROIBIDO chamá-lo de "
                            "'estoque parado', 'encalhado' ou 'sem giro'. O que está parado, "
                            "se existir, está descrito nos campos próprios — e não tem este "
                            "valor.\n")
        bloco_motor += "\n"
    else:
        bloco_motor += (f"{rotulo} — NÃO DETERMINADO ({motivo_estoque}).\n"
                        f"É PROIBIDO afirmar, estimar ou arredondar QUALQUER valor em reais para o "
                        f"estoque — inclusive 'cerca de', 'aproximadamente' ou 'em torno de'.\n"
                        f"Se precisar mencionar {como_falar} com cifra, escreva exatamente: "
                        f"\"{FRASE_ESTOQUE_SEM_VALOR}\"\n"
                        f"A decisão e as ações continuam valendo sem a cifra — o estoque perde o "
                        f"tamanho, não o rumo.\n\n")

    modelo_usado = modelo if isinstance(modelo, str) and modelo in MODELOS_PERMITIDOS else MODELO_PADRAO
    prompt = (
                f"Você é o NEXO Análise. Slogan: Transformando dados em decisões.\n\n"

                f"⚖️ HIERARQUIA DE REGRAS — leia antes de tudo.\n"
                f"As regras deste prompt são cumulativas e não podem se contradizer. Uma regra específica não pode "
                f"autorizar aquilo que outra regra proíbe. Havendo conflito entre uma regra, exemplo ou instrução "
                f"anterior e uma regra posterior mais específica, PREVALECE A REGRA MAIS ESPECÍFICA.\n"
                f"EXEMPLOS SÃO ILUSTRATIVOS. Não são dados reais e não podem ser reutilizados como fatos, números, "
                f"metas, nomes, produtos, fornecedores ou recomendações de outro negócio. "
                f"NUNCA siga um exemplo quando ele contradisser uma regra explícita.\n\n"
                f"Sua função é transformar informações de negócios em decisões práticas, claras e executáveis. "
                f"Você NÃO cria relatórios. Você NÃO cria análises teóricas. Você NÃO terceiriza decisões. "
                f"Você entrega apenas decisões acionáveis de alto impacto.\n\n"
                f"REGRAS INEGOCIÁVEIS:\n"
                f"- Proibido qualquer conteúdo de Recursos Humanos (RH).\n"
                f"- Proibido sugerir consultorias, agências ou consultores externos. O NEXO É o consultor do cliente.\n"
                f"- Proibido respostas teóricas sem ação prática.\n"
                f"- Proibido ignorar a verba disponível.\n"
                f"- Proibido recomendações impossíveis de executar pelo próprio dono.\n"
                f"- Sempre priorize simplicidade e execução imediata.\n"
                f"- Sempre use linguagem direta e de ação — e TODO verbo carrega ALVO NOMEADO.\n"
                f"  EXEMPLO DE AÇÃO CORRETA: 'Criar uma ação de giro para o blazer de alfaiataria nos próximos 30 dias, "
                f"definindo o desconto somente após verificar custo, preço atual, margem e quantidade disponível.'\n"
                f"  EXEMPLO DE AÇÃO CORRETA: 'Reprecificar o vestido midi, campeão de vendas, para proteger "
                f"sua margem sem comprometer a competitividade do preço.'\n"
                f"  Repare no exemplo: 'campeão de vendas' está NOS DADOS; a margem daquela peça NÃO está, "
                f"então a ação fala em PROTEGER a margem e nunca afirma qual ela é.\n"
                f"  NUNCA usar como exemplo nem como ação: 'reduzir o estoque em 50%', 'dar 30% de desconto', "
                f"'subir o preço em 8%', 'otimize o estoque' — nem qualquer percentual de estoque, desconto ou preço "
                f"quando esses dados não estiverem disponíveis. "
                f"Evite: 'seria interessante', 'recomenda-se avaliar', 'pode-se considerar', 'otimizar', 'melhorar', 'trabalhar melhor'.\n\n"
                f"PRINCÍPIO CENTRAL: a qualidade da decisão depende diretamente da qualidade das informações fornecidas. "
                f"Use TODOS os dados do negócio informados abaixo — cada número e detalhe ajuda a calibrar a decisão.\n\n"
                f"{instrucao_historico}"
                f"MODO DE DECISÃO DESTE NEGÓCIO: {modo}\n\n"
                f"📅 HOJE É {datetime.now().strftime('%d/%m/%Y')}. Todo prazo que você propuser tem de ser FUTURO "
                f"em relação a esta data — o período analisado já terminou, e prazo no passado invalida a ação.\n\n"

                f"🎯 FIRME NA DECISÃO, CONSERVADOR NA CONCLUSÃO:\n"
                f"- A decisão é sua e vai direta. O DIAGNÓSTICO fica do tamanho do dado.\n"
                f"- PROIBIDO veredito global sobre a empresa ('a saúde do negócio está comprometida', 'a empresa está "
                f"em risco') quando os números não sustentam. Se a loja vendeu mais, bateu a meta e ainda teve lucro, "
                f"o que piorou foi a RENTABILIDADE — diga isso, e só isso.\n"
                f"- PROIBIDO afirmar CAUSA que os dados não isolam. Nunca escreva que algo aconteceu 'por causa' de "
                f"outra coisa sem prova nos números. Escreva 'pode ter contribuído' e diga o que faltaria para saber.\n"
                f"- PROIBIDO afirmar que uma decisão anterior não foi executada. Você não sabe. Se os dados mostram o "
                f"contrário do esperado, diga o RESULTADO ('a meta X não foi atingida'), nunca a conduta do dono.\n"
                f"- PROIBIDO apontar UMA saída como se fosse a única. Margem apertada não significa 'cortar custos': "
                f"pode ser compra, preço, desconto ou giro. Escreva a prioridade e as frentes juntas — 'a prioridade é "
                f"recuperar margem, avaliando ao mesmo tempo custos, descontos e giro do estoque' — e só aponte uma "
                f"frente isolada quando os números disserem qual é.\n\n"

                f"⚖️ RISCO NÃO É O MESMO QUE OPORTUNIDADE, e canal que CRESCE não é risco:\n"
                f"- Canal que ganhou participação, ou cresceu em reais, entra como OPORTUNIDADE, com o número do "
                f"crescimento. Não o chame de 'dependência' nem de 'risco'.\n"
                f"- Só existe dependência quando um canal responde por MAIS DA METADE das vendas — e aí o canal a "
                f"nomear é esse, não o que cresceu. Concentração de 28% não é dependência.\n"
                f"- Canal que PERDEU participação, aí sim, é o que merece atenção de risco.\n\n"

                f"⚖️ NÃO CONTRADIGA O MOTOR, E NÃO INVENTE RÓTULO CONCORRENTE: o resultado do negócio já vem "
                f"decidido nas linhas calculadas. Se a margem calculada é positiva, HOUVE LUCRO — nunca escreva "
                f"'prejuízo' nem 'lucro negativo'. Use o mesmo rótulo que o Radar usou ('margem apertada', "
                f"'margem saudável', 'prejuízo'); não crie um julgamento paralelo que brigue com ele. "
                f"Também não afirme que o lucro caiu, subiu ou ficou igual sem que os números calculados digam isso. "
                f"Contradizer o Motor invalida a resposta.\n\n"

                f"🔴 SE O RADAR TRAZ 'Números não fecham': o lucro informado NÃO fecha com faturamento menos "
                f"custos, e por isso margem e lucro ficaram FORA da leitura. Nesse caso é PROIBIDO, em qualquer "
                f"seção: chamar a margem de saudável, apertada ou de qualquer outra coisa; dizer que o lucro foi "
                f"bom, positivo, significativo ou ruim; usar o valor do lucro como prova de conclusão; e construir "
                f"diagnóstico sobre ele. Diga o que os OUTROS números sustentam e trate a correção dos lançamentos "
                f"como o próximo passo. Aviso ao lado de conclusão é conclusão.\n\n"

                f"📄 FORMATAÇÃO — a saída vai direto para um PDF que não interpreta markdown:\n"
                f"- Escreva em TEXTO PURO. Proibido '**', '###', '---', '```', tabelas e qualquer marcação.\n"
                f"- NUNCA numere os itens DENTRO de uma seção ('1.', '2.', '3.'). Só os TÍTULOS das seções levam "
                f"número. Item de lista começa direto pela palavra. Numerar item quebra o PDF: ele vira título.\n"
                f"- Cada título de seção começa pelo emoji e pelo número, exatamente como no formato pedido, "
                f"e a linha do título não leva nenhum outro caractere de marcação.\n"
                f"- Números no padrão brasileiro: R$ 12.345 (ponto no milhar), 9,7% (vírgula decimal, "
                f"sem espaço antes do %). Nunca 'R$ 18 000' nem '8,5 %'.\n"
                f"- Escreva tudo em português do Brasil. NENHUMA palavra em outro idioma, em hipótese alguma — "
                f"se faltar a palavra certa, reescreva a frase. Antes de entregar, releia procurando palavra "
                f"estrangeira e frase interrompida no meio.\n"
                f"- NUNCA nomeie a ferramenta nem as seções dentro do texto. Proibido 'o radar mostra', 'o radar de "
                f"vendas indica', 'esta análise conclui', 'o NEXO recomenda'. Fale do NEGÓCIO, não do relatório: "
                f"'o estoque está cheio', não 'o radar de estoque indica que o estoque está cheio'.\n"
                f"- Proibido marcador, rótulo ou sigla de sistema no texto do cliente — nada de '(leitura)', "
                f"'(calculado)', '(fato)'. O cliente não sabe o que significam.\n\n"

                f"🚫 PROIBIDO INVENTAR NÚMERO (regra que vence todas as outras):\n"
                f"Existem dois tipos de número, e eles não se misturam:\n"
                f"- NÚMERO-FATO (afirma algo sobre o negócio): só pode sair de duas fontes — um valor que aparece "
                f"literalmente nos DADOS DO NEGÓCIO, ou uma linha de INDICADORES/RADAR CALCULADO. "
                f"É PROIBIDO calcular percentuais, taxas, somas, divisões, quanto se 'recupera em caixa' ou "
                f"valores de período anterior que não estejam escritos. Se o número não existe nessas duas fontes, "
                f"escreva a frase SEM número — descrever bem vale mais que calcular errado.\n"
                f"- NÚMERO-META (o alvo que VOCÊ propõe, e SÓ sobre margem, lucro, faturamento ou ticket, sempre "
                f"escrevendo o valor de partida calculado — 'de [atual] para [alvo]'): esse você escolhe, e ele é "
                f"bem-vindo. Nunca apresente número-meta como se fosse resultado apurado.\n"
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
                f"- OBRIGATÓRIO no lugar: 'criar uma ação de giro para o blazer de alfaiataria e a saia longa jeans "
                f"nos próximos 30 dias, definindo o desconto somente após verificar custo, preço atual, margem e "
                f"quantidade disponível' · 'reprecificar o vestido midi, campeão de vendas, para proteger sua margem "
                f"sem comprometer a competitividade do preço' · 'responder o WhatsApp até as 20h no sábado'.\n"
                f"- Ao falar de estoque encalhado, nomeie o item E o tamanho/variação encalhada quando os dados trouxerem "
                f"(ex.: 'GG e XG'). É o tamanho que corrige a PRÓXIMA COMPRA — sem ele o dono repete o erro.\n"
                f"- PROIBIDA QUALQUER AMBIGUIDADE: se uma frase puder ser lida de duas formas, reescreva. "
                f"Comparação sempre diz explicitamente o que é comparado com o quê "
                f"(errado: 'custos subiram X% e o faturamento Y%, N vezes mais rápido' — não se sabe o que é N vezes "
                f"mais rápido que o quê; certo: 'os custos subiram N vezes mais rápido que o faturamento').\n\n"

                f"💸 REGRA DE PERCENTUAIS\n"
                f"Todo percentual apresentado como dado ou variação deve ter PONTO DE PARTIDA calculado a partir dos "
                f"dados fornecidos.\n"
                f"Percentual pode aparecer como META PROPOSTA somente nestas categorias: faturamento · lucro · "
                f"margem · ticket médio. Nessas quatro, a meta pode ser proposta por você, mas TEM DE APRESENTAR O "
                f"VALOR ATUAL COMO PONTO DE PARTIDA, sempre, sem exceção — 'de [valor calculado] para [alvo]'. "
                f"Meta sem o valor de partida escrito na própria frase é inválida.\n"
                f"NUNCA propor nem inventar percentual para: estoque · estoque encalhado · desconto · redução de "
                f"custos · quantidade de produtos · quantidade de clientes · participação de produtos · nem qualquer "
                f"outra variável fora das quatro autorizadas acima.\n"
                f"Exemplos PROIBIDOS: 'reduzir estoque em 30%' · 'dar 40% de desconto' · 'reduzir custos em 15%' · "
                f"'vender 20% mais unidades' · 'alcançar R$ [valor]' sem escrever de quanto se está partindo.\n"
                f"Quando não houver dado para calcular ou justificar um percentual, use orientação QUALITATIVA e não "
                f"invente número — 'criar uma ação de giro para o blazer e a saia longa nos próximos 30 dias, "
                f"definindo o desconto depois de olhar a margem e o custo dessas peças'.\n"
                f"EXCEÇÃO ÚNICA: percentual que já está escrito nos dados do cliente pode ser citado como está.\n\n"

                f"🔴 O QUE UM FATO DECLARADO AUTORIZA DIZER — e onde ele PARA:\n"
                f"- FALTA declarada prova que faltou. NÃO prova que alguma venda deixou de acontecer: "
                f"ninguém mediu isso. Escreva 'cria RISCO de perda de vendas', nunca 'impactou', "
                f"'reduziu' ou 'fez perder' vendas.\n"
                f"- COMPOSIÇÃO DE CUSTO diz QUANTO foi comprado e que fatia isso representa. NÃO diz se a "
                f"compra foi acertada. É PROIBIDO chamar a compra de eficaz, ineficaz, errada, excessiva ou "
                f"desnecessária — nenhum campo mede isso.\n"
                f"- QUEDA DECLARADA pelo cliente (fluxo, clientes, vendas) é fato dele e pode ser citada. "
                f"O motivo NÃO é: não escreva que ela 'sinaliza', 'indica' ou 'sugere' mudança de "
                f"comportamento, de mercado ou de concorrência. O NEXO sabe QUE caiu, não POR QUÊ.\n"
                f"- SEM ANÁLISE ANTERIOR nada cresceu, caiu ou subiu. Se este for o primeiro período do "
                f"negócio, é PROIBIDO afirmar variação de faturamento, custo, lucro, margem ou ticket.\n"
                f"- GRAU não sai de número: 'significativo', 'expressivo', 'considerável' e 'drasticamente' "
                f"acrescentam intensidade que nenhum cálculo produziu.\n\n"

                f"🔴 ENCALHE E RUPTURA SÃO OPOSTOS — NÃO TROQUE UM PELO OUTRO:\n"
                f"- ITEM ENCALHADO (encalhe_item, 'baixa saída', 'parado', 'sem giro'): há estoque DEMAIS. "
                f"A decisão é girar, liquidar, parar de comprar. NUNCA escreva que ele pode faltar, que há "
                f"risco de ruptura ou que é preciso repor.\n"
                f"- ITEM EM FALTA (falta_item, 'faltou', 'ruptura'): há estoque DE MENOS. A decisão é repor e "
                f"não deixar faltar de novo. NUNCA escreva que ele está parado ou encalhado.\n"
                f"Trocar um pelo outro INVERTE a decisão e invalida a resposta.\n\n"

                f"⚖️ AS DUAS ALAVANCAS DE PREÇO SÃO OPOSTAS — NUNCA NA MESMA FRASE:\n"
                f"- LIQUIDAR o encalhado: sacrifica margem DE PROPÓSITO para recuperar CAIXA. Só vale para item parado.\n"
                f"- REPRECIFICAR o que gira: recupera MARGEM. Só vale para item de alta saída.\n"
                f"Escrever 'faça promoção para aumentar a margem' é contradição e invalida a resposta. "
                f"Diga sempre QUAL das duas, em QUAIS itens, e O QUE ela recupera — caixa ou margem.\n\n"

                f"💰 CAPITAL PARADO — cruzamento OBRIGATÓRIO, é a explicação que o dono mais procura:\n"
                f"- Se o RADAR CALCULADO trouxer a linha 'Os custos passaram a comer uma fatia maior' ou a linha "
                f"'De cada R$ 100 vendidos', ela é FATO e tem de ser EXPLICADA "
                f"na seção 'o que está te fazendo perder dinheiro': diga para ONDE o dinheiro foi, cruzando com o que os "
                f"dados dizem sobre compra de estoque, coleção nova e encalhe.\n"
                f"- Se os custos do período incluem COMPRA DE ESTOQUE e os dados declaram estoque encalhado, parado ou de "
                f"coleção anterior, diga explicitamente que o lucro não desapareceu, ele VIROU ESTOQUE — com os dois valores "
                f"lado a lado (quanto foi comprado × quanto está parado).\n"
                f"- Nunca trate 'margem apertada' como causa. Margem apertada é sintoma; a causa é onde o dinheiro entrou.\n\n"

                f"🎯 A PREOCUPAÇÃO DECLARADA É LENTE DE COLETA, NÃO DIAGNÓSTICO. O campo 'preocupacao' diz o que "
                f"o dono TEME, não o que os dados MOSTRAM. Ele serve para você entender o que aflige o lojista — "
                f"nunca como conclusão pronta. Se os números apontarem outra causa, o diagnóstico segue os NÚMEROS "
                f"e explica a diferença em uma frase. Ex.: o dono aponta ESTOQUE, e o estoque caiu enquanto a margem "
                f"encolheu — então o diagnóstico é da margem, e você diz que o estoque melhorou. "
                f"É PROIBIDO abrir o diagnóstico repetindo a preocupação declarada como se fosse achado seu.\n\n"

                f"🔁 NÃO RECOMENDE O QUE JÁ FOI TENTADO: varre os campos de desafios e observações antes de decidir. "
                f"Se o dono declarou ter feito algo (ex.: 'dei muito desconto'), NÃO recomende a mesma coisa. "
                f"Reconheça que já foi tentado, diga por que não resolveu e proponha uma alavanca DIFERENTE.\n\n"

                f"FORMATO OBRIGATÓRIO DE SAÍDA (use exatamente estes títulos, nesta ordem):\n\n"
                f"{formato}\n\n"
                f"PRIORIZAÇÃO INTERNA (NÃO EXIBIR AO USUÁRIO): antes de responder, avalie cada ação possível por impacto no resultado, "
                f"facilidade de execução e custo em relação à verba disponível. "
                f"Priorize sempre alto impacto + alta facilidade + baixo custo. "
                f"Apresente ao usuário apenas as ações já priorizadas — nunca mostre pontuações, notas ou cálculos.\n\n"
                f"RESTRIÇÃO DE ORÇAMENTO: respeite estritamente o campo 'Verba destinada para melhorias'. "
                f"Se a verba for baixa, nula ou não informada, recomende apenas ações de custo zero ou muito baixo "
                f"(ajustes de processo, ações orgânicas, renegociação, organização interna, ferramentas gratuitas).\n\n"
                f"✅ VERIFICAÇÃO FINAL OBRIGATÓRIA — releia a resposta inteira antes de entregar e confirme:\n"
                f"- Nenhuma palavra em outro idioma, nenhuma frase interrompida no meio.\n"
                f"- Nenhum marcador de sistema no texto ('(leitura)', '(calculado)', '(fato)').\n"
                f"- Nenhuma frase do tipo 'o radar de vendas mostra' — fale do negócio, não do relatório.\n"
                f"- Nenhum fornecedor, produto, quantidade ou ocorrência atribuído a entidade diferente da que está "
                f"nos dados.\n"
                f"- Nenhum número, percentual, meta ou valor que não esteja nos dados, nas linhas calculadas ou "
                f"autorizado pela REGRA DE PERCENTUAIS. Toda meta traz o valor de partida escrito. "
                f"A tag (Custo: … | Resultado em: …) das Ações Imediatas é estimativa declarada, não afirmação "
                f"sobre o negócio, e continua OBRIGATÓRIA em todas as ações.\n"
                f"- Nenhuma afirmação de que uma recomendação anterior foi EXECUTADA, se os dados não confirmam. "
                f"DIFERENCIE SEMPRE: recomendação feita ≠ ação executada ≠ resultado observado. Escrever 'a estratégia "
                f"de giro não foi suficiente' já pressupõe que ela foi executada — e você não sabe disso. "
                f"O que se afirma é o RESULTADO: 'a meta de margem não foi atingida'.\n"
                f"- Nenhum veredito sobre uma empresa terceira ('problemas de qualidade', 'reavaliar a parceria'): "
                f"descreva o fato registrado nos dados.\n\n"

                f"REGRA FINAL DE QUALIDADE: se a resposta não terminar com uma decisão clara e executável, a resposta é inválida.\n\n"
                f"{bloco_motor}"
                f"DADOS DO NEGÓCIO:\n{_dados_legiveis(dados)}"
    )

    def _pedir(mensagens):
        r = groq_client.chat.completions.create(model=modelo_usado, messages=mensagens)
        # 🔬 usage REAL da chamada — o número que substitui a estimativa chars/4 no
        # cálculo do orçamento de janela. Só imprime com a captura ligada.
        if CAPTURA_CANONICA:
            u = getattr(r, "usage", None)
            if u is not None:
                linha = (f"CAPTURA|usage|prompt_tokens={getattr(u, 'prompt_tokens', '?')}|"
                         f"completion_tokens={getattr(u, 'completion_tokens', '?')}|"
                         f"total_tokens={getattr(u, 'total_tokens', '?')}")
                print(linha)
                _cap_arquivo(linha + "\n")
        return _normalizar_saida(r.choices[0].message.content)

    def _entregar(s):
        """O QUE O CÓDIGO CALCULA, O CÓDIGO PUBLICA (#083). Radar e Metas saem daqui,
        não da caneta do modelo — o miolo que ele escreveu nessas duas seções é
        descartado. Instrução de prompt já não bastava: 'reproduza exatamente como
        está' estava escrito e o PDF de agosto saiu com 16,8% onde o Motor calculou
        16,77%. Aqui não há o que obedecer.
        Devolve (texto, secoes): o texto para a 1.0.2.0 instalada, a estrutura para o
        app novo renderizar em HTML sem re-parsear nada."""
        secoes = _em_secoes(s)
        ok_radar = _garantir_secao(secoes, "RADAR", "RADAR DO NEGÓCIO", list(radar))
        ok_ciclo = _garantir_secao(secoes, "CICLO", "O CICLO ANTERIOR", _bloco_ciclo(dados, indicadores))
        ok_metas = _garantir_secao(secoes, "METAS", "METAS ATÉ A PRÓXIMA ANÁLISE",
                                   _bloco_metas(dados))

        # O degrau 3 não pode depender de o modelo acertar a seção: em 05/08 ele pôs
        # a frase no Radar, e a substituição do Radar a levou junto. Agora ela é
        # colocada por código, onde a perda é discutida.
        if _valor_estoque(dados)[0] is None:
            for sec in secoes:
                titulo = (sec["titulo"] or "").upper()
                if "PERDER DINHEIRO" in titulo or "CUSTANDO DINHEIRO" in titulo:
                    if any("estoque" in l["texto"].lower() for l in sec["linhas"]):
                        sec["linhas"].append(_linha_estruturada(FRASE_ESTOQUE_SEM_VALOR))
                    break

        print(f"PUBLICACAO|{segmento}|radar={ok_radar}|ciclo={ok_ciclo}|"
              f"metas={ok_metas}|secoes={len(secoes)}")
        return _texto_de_secoes(secoes), secoes

    saida = _pedir([{"role": "user", "content": prompt}])
    # Monta ANTES de validar: as seções escritas por código já entram no lugar, e o
    # validador passa a julgar o que o cliente vai ler. As violações que sobram são,
    # por construção, as que o modelo PODE consertar.
    texto1, secoes1 = _entregar(saida)
    violacoes = validar_saida(texto1, dados, indicadores, radar)
    _registrar("saida-1a-tentativa", segmento, violacoes, f"modo={MODO_VALIDADOR}")

    # 🔬 CAPTURA CANÔNICA — a resposta 1 INTEIRA do modelo (o log de `_registrar` traz
    # só o trecho, e a UI do Railway ainda o corta). Entre marcadores, para o fundador
    # copiar o bloco fechado. Também repete fiscal|seção|trecho completo, já que agora
    # temos o texto todo para localizar a seção. Guardado pela env var: em produção
    # normal, nada disto imprime.
    if CAPTURA_CANONICA:
        print("CAPTURA-INICIO-RESPOSTA1")
        print(saida)
        print("CAPTURA-FIM-RESPOSTA1")
        bloco = [f"\n{'='*64}\nSEGMENTO: {segmento}\n{'='*64}\n",
                 "--- RESPOSTA 1 (texto do modelo, antes de qualquer correção) ---\n",
                 saida, "\n\n--- FISCAIS QUE DISPARARAM ---\n"]
        for x in violacoes:
            marca = "obs" if x.get("observa") else "ATIVA"
            print(f"CAPTURA|fiscal|{marca}|{x['regra']}|{x['trecho']}")
            bloco.append(f"[{marca}] {x['regra']} :: {x['trecho']}\n")
        _cap_arquivo("".join(bloco))

    # Checagem marcada observa=True entra no log e NÃO puxa retentativa — ver _viol.
    ativas = [x for x in violacoes if not x.get("observa")]

    # FASE 1 — OBSERVAÇÃO: registra o que bloquearia e entrega a análise assim mesmo.
    if MODO_VALIDADOR == "observacao" or not ativas:
        return texto1, secoes1

    # CAMINHO 2 — devolver os erros específicos à IA e pedir a correção.
    correcao = (
        "A resposta que você acabou de gerar foi reprovada pela validação automática do NEXO. "
        "Os problemas abaixo são objetivos — foram apurados em cálculo, não em opinião:\n\n"
        f"{_texto_das_violacoes(ativas)}\n\n"
        "Reescreva a análise INTEIRA corrigindo exatamente esses pontos, mantendo tudo o que "
        "estava certo e obedecendo às mesmas regras do pedido original. Não comente a correção: "
        "devolva só a análise."
    )
    # 🔴 FALHA DE CORREÇÃO NUNCA REABILITA UMA SAÍDA JÁ REPROVADA.
    #
    # Este `except` devolvia `texto1` — a 1ª tentativa, com a violação intacta. A razão
    # escrita era "vale a análise da 1ª tentativa, que é real e completa", e ela parecia
    # generosa: melhor entregar algo do que nada.
    #
    # ⛔ MEDIDO NA RODADA 2 DA AROMÁTICA (14/08). O relatório chegou ao lojista com
    # "evitar aquisição de mercadorias que não são mais necessárias" — exatamente a
    # frase que o `_COMPRA_JULGADA` bloqueia. A trava disparou, a retentativa levantou
    # exceção, e o caminho de cima republicou a saída reprovada.
    #
    # ⚖️ Isso anula o significado de trava bloqueante: com pressão de cota, TODA
    # checagem ativa degradava silenciosamente para consultiva. Depois que o NEXO sabe
    # que a 1ª saída viola uma regra bloqueante, ela não pode voltar a ser candidata —
    # não importa se foi timeout, erro do modelo ou exceção interna.
    #
    # O que sobra é o fallback, que NÃO é entregar nada: o Radar, o §2 e as Metas são
    # escritos por código e continuam certos. Quem falhou foi a interpretação.
    try:
        saida2 = _pedir([{"role": "user", "content": prompt},
                         {"role": "assistant", "content": saida},
                         {"role": "user", "content": correcao}])
    except Exception as e:
        print(f"VALIDADOR|correcao-falhou|{segmento}|{type(e).__name__}|{e}")
        _registrar("fallback-sem-correcao", segmento, ativas, f"modo={MODO_VALIDADOR}")
        return _fallback_apurado("", dados, indicadores, radar, segmento)
    texto2, secoes2 = _entregar(saida2)
    violacoes2 = validar_saida(texto2, dados, indicadores, radar)
    _registrar("saida-2a-tentativa", segmento, violacoes2, f"modo={MODO_VALIDADOR}")
    if not [x for x in violacoes2 if not x.get("observa")]:
        return texto2, secoes2

    _registrar("fallback", segmento, violacoes2, f"modo={MODO_VALIDADOR}")
    return _fallback_apurado(saida2, dados, indicadores, radar, segmento)

def _observar_em_shadow(segmento, brutos, analise):
    """🔭 O mecanismo decisório novo observa a análise real e REGISTRA. Só isso.

    O empresário continua recebendo exatamente o produto atual; o mecanismo novo vê
    o mesmo caso e anota o que TERIA feito. É o que o laboratório não consegue
    fabricar: texto de lojista de verdade, combinações inesperadas, campos vazios,
    erros de digitação naturais, freios reais, tamanho real de uma análise.

    ⛔ ESTA FUNÇÃO NÃO PODE FALHAR PARA FORA. Ela roda dentro da rota que atende
    cliente pagante; qualquer exceção morre aqui e vira uma linha de log.

    💸 A fase do MODELO gasta a mesma cota diária do cliente. Por isso ela nasce
    DESLIGADA (`SHADOW_REDACAO=1` liga) e é amostrada (`SHADOW_AMOSTRA=0.25` roda em
    um quarto das análises). A espinha determinística — Fiscal 0, relações, estados,
    limites, recall — custa ZERO token e responde a maior parte das perguntas.
    """
    if not SHADOW_MOTOR:
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "lab_prototipo"))
        from shadow import detalhe, observar, resumo

        chamar = None
        if SHADOW_REDACAO and groq_client is not None and random.random() < SHADOW_AMOSTRA:
            def chamar(prompt):
                r = groq_client.chat.completions.create(
                    model=MODELO_PADRAO,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3)
                return r.choices[0].message.content

        reg = observar(segmento, brutos, analise, chamar=chamar,
                       preocupacao=(brutos.get("preocupacao") or "").strip().lower())
        print(resumo(reg), flush=True)
        for linha in detalhe(reg):
            print(linha, flush=True)

        # Janela de observação — bounded, efêmera, saneada. Ver `sanear()`.
        from shadow import sanear
        _JANELA_SHADOW.append({
            "quando": datetime.now().isoformat(timespec="seconds"),
            "id": uuid.uuid4().hex[:8],
            **sanear(reg),
        })
    except Exception as e:                              # noqa: BLE001
        # Falha do shadow NUNCA é falha da análise. O cliente não fica sabendo.
        print("SHADOW|erro-interno|%s: %s" % (type(e).__name__, e), flush=True)


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

        # 🔴 BLOQUEIO DE ENTRADA — erro do cliente se resolve antes de gastar a IA.
        # Só barra o aritmeticamente impossível; o suspeito segue e vira aviso no Radar.
        bloco_atual = dados.split("=== DADOS ATUAIS ===", 1)[-1]
        brutos_atual = _campos_do_bloco(bloco_atual)[0]
        numeros_atual = {k: _num_br(v) for k, v in brutos_atual.items()}
        entrada = validar_entrada(numeros_atual, brutos_atual)
        _registrar("entrada", segmento, entrada, f"modo={MODO_VALIDADOR}")
        impedem = [x for x in entrada if x["bloqueia"]]
        if impedem:
            campos = " · ".join(sorted({x["campo"] for x in impedem if x["campo"]}))
            return jsonify({
                "status": "erro",
                "motivo": ("DADO INCONSISTENTE — a análise não foi gerada.\n\n"
                           + "\n".join(f"• {x['detalhe']}." for x in impedem)
                           + f"\n\nCorrija {campos or 'os campos indicados'} e gere a análise "
                             "novamente."),
                "campos": [x["campo"] for x in impedem if x["campo"]],
            }), 400

        # A versão completa exige licença válida; a demo é liberada (limitada no próprio app)
        if modo == "completo":
            if not chave or not validar_licenca_chave(chave):
                return jsonify({"status": "erro", "motivo": "Licença inválida ou expirada."}), 403

        analise, secoes = gerar_analise(dados, segmento, body.get("modelo"))

        # 🔭 SHADOW MODE (#095) — o mecanismo novo observa a MESMA análise e não a
        # toca. Vem DEPOIS da resposta estar pronta, dentro do seu próprio try, e
        # nada aqui pode alterar `analise`, `secoes` ou o código de retorno.
        _observar_em_shadow(segmento, brutos_atual, analise)

        # `analise` é o contrato da 1.0.2.0 que já está instalada — ACRESCENTA-SE
        # `secoes`, nunca se troca o formato, senão todo cliente instalado quebra.
        return jsonify({"status": "ok", "analise": analise, "secoes": secoes}), 200

    except Exception as e:
        # Detalhe técnico fica no log do servidor; o cliente não vê mensagem interna
        # do Python na tela (o app exibe este 'motivo' direto pro lojista).
        print(f"ERRO no /analisar: {type(e).__name__}: {e}")
        # Falha do serviço de IA ≠ falha da análise. Dizer qual é ajuda o lojista a
        # saber que não é problema no que ele preencheu — e ajuda a diagnosticar.
        texto = f"{type(e).__name__}: {e}".lower()
        if any(x in texto for x in ("rate", "quota", "limit", "429", "insufficient",
                                    "unauthor", "401", "api key", "connection", "timeout")):
            motivo = ("O serviço de análise está temporariamente indisponível. "
                      "Seus dados estão certos — tente novamente em alguns minutos.")
        else:
            motivo = ("Não foi possível gerar a análise agora. "
                      "Tente novamente em instantes.")
        return jsonify({"status": "erro", "motivo": motivo}), 200

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
        plano_nome, quantidade, unidade = plano_info

        # RENOVAÇÃO ANTES DE EMISSÃO: quem já tem chave viva não ganha chave nova —
        # a validade DELE é que anda. Vale para qualquer cobrança recorrente, e não
        # depende de o valor da renovação chegar 7 ou 47: os dois dão um mês.
        if unidade != "forever":
            ws = conectar_sheets()
            indice, linha = achar_linha_renovavel(ws.get_all_values(), email_cliente)
            if indice:
                validade_nova = validade_renovada(linha[2], quantidade)
                renovar_validade(ws, indice, validade_nova)
                print(f"RENOVACAO: {linha[0]} -> {validade_nova} ({email_cliente})")
                enviar_email_renovacao(email_cliente, nome_cliente, linha[0], validade_nova)
                return jsonify({"status": "ok", "renovada": linha[0], "validade": validade_nova}), 200

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

@app.route("/captura", methods=["GET"])
def captura_ver():
    """🔬 A captura canônica em TEXTO PURO, para copiar do navegador — em vez de caçar
    linha a linha no log do Railway. Mesma proteção do laboratório: 404 sem o token.

    Aceita o token no header X-Lab-Token OU em ?token= (o navegador não manda header
    fácil). `?limpar=1` zera o arquivo para começar uma coleta nova, isolada.
    ⛔ Só LÊ o que a captura já gravou; não roda análise, não toca estado nenhum."""
    tok = request.headers.get("X-Lab-Token", "") or request.args.get("token", "")
    if not LAB_TOKEN or not hmac.compare_digest(tok, LAB_TOKEN):
        return jsonify({"status": "erro", "motivo": "rota inativa"}), 404
    plain = {"Content-Type": "text/plain; charset=utf-8"}
    if request.args.get("limpar") == "1":
        try:
            os.remove(CAPTURA_ARQUIVO)
        except FileNotFoundError:
            pass
        except Exception as e:                                   # noqa: BLE001
            return f"erro ao limpar: {e}", 500, plain
        return "captura zerada — rode os canônicos e recarregue esta URL sem ?limpar", 200, plain
    if not CAPTURA_CANONICA:
        return ("captura DESLIGADA. Defina NEXO_CAPTURA=1 nas Variables, faça Deploy, "
                "rode as análises e recarregue."), 200, plain
    try:
        with open(CAPTURA_ARQUIVO, encoding="utf-8") as f:
            return (f.read() or "arquivo vazio — nenhuma análise capturada ainda"), 200, plain
    except FileNotFoundError:
        return "nada capturado ainda — rode uma análise com a captura ligada", 200, plain


@app.route("/laboratorio", methods=["GET"])
def laboratorio_janela():
    """🪟 SOMENTE LEITURA — a janela de observação do shadow, saneada.

    Existe porque um shadow que ninguém consegue observar regularmente vira
    instrumentação decorativa, e depender de copiar log à mão durante dias faria a
    amostra ficar pequena e irregular.

    ⛔ NÃO é uma API de observabilidade genérica: nenhum argumento aqui altera
    shadow, prompt, caso ou qualquer estado. Só devolve o que já foi decidido que
    pode sair — e a rota continua 404 sem o token certo.
    """
    if not LAB_TOKEN or not hmac.compare_digest(
            request.headers.get("X-Lab-Token", ""), LAB_TOKEN):
        return jsonify({"status": "erro", "motivo": "rota inativa"}), 404
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "lab_prototipo"))
        from shadow import agregar
        janela = list(_JANELA_SHADOW)
        return jsonify({
            "aviso": "janela de observação — efêmera, some em restart/deploy e pode "
                     "não cobrir todas as instâncias. Não é registro oficial.",
            "build": (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "desconhecido")[:7],
            "redacao_ligada": SHADOW_REDACAO,
            "totais": agregar(janela),
            "observacoes": janela,
        }), 200
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"status": "erro", "motivo": "%s: %s" % (type(e).__name__, e)}), 500


@app.route("/laboratorio", methods=["POST"])
def laboratorio():
    """🧪 ROTA DE LABORATÓRIO — o protótipo do mecanismo (#094) contra o modelo REAL.

    Existe por um motivo só: a chave da Groq vive aqui e em nenhum outro lugar (#043),
    então este é o único lugar onde a arquitetura pode encontrar linguagem livre. Até
    agora ela só provou barrar os erros que nós conseguimos NOMEAR.

    ⛔ NÃO toca o produto: não gera PDF, não grava histórico, não escreve na planilha,
    não altera o app e não passa perto da /analisar. Entra requisição, sai REGISTRO.

    🔒 TRÊS TRAVAS, e a primeira é a que importa:
      ① INERTE sem LAB_TOKEN nas Variables — enquanto o fundador não criar a variável,
        esta rota responde 404 e é como se não existisse;
      ② os casos vêm do ARQUIVO, nunca do corpo da requisição: ninguém injeta prompt
        aqui, o pior que um portador do token faz é queimar cota;
      ③ o modelo sai da mesma allowlist da /analisar.

    Custo: 14 unidades × ~1 frase curta ≈ metade de UMA análise de cliente.
    """
    # 🔴 As duas negativas respondem 404, e isso é correção da condição ② do fundador:
    # *"token errado → continua oculta"*. Um 401 confirmaria a QUEM ERROU que a rota
    # existe — e a diferença entre 404 e 401 é justamente o que um varredor procura.
    # Aqui as duas portas fechadas são indistinguíveis de uma parede.
    if not LAB_TOKEN or not hmac.compare_digest(
            request.headers.get("X-Lab-Token", ""), LAB_TOKEN):
        return jsonify({"status": "erro", "motivo": "rota inativa"}), 404
    if groq_client is None:
        return jsonify({"status": "erro", "motivo": "Servidor sem chave de IA configurada."}), 503

    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "lab_prototipo"))
        from laboratorio import imprimir, rodar_laboratorio
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"status": "erro",
                        "motivo": "protótipo indisponível: %s" % e}), 500

    corpo = request.get_json(silent=True) or {}
    modelo = corpo.get("modelo")
    modelo = modelo if modelo in MODELOS_PERMITIDOS else MODELO_PADRAO

    def chamar(prompt):
        r = groq_client.chat.completions.create(
            model=modelo,
            messages=[{"role": "user", "content": prompt}],
            temperature=corpo.get("temperatura", 0.3),
        )
        return r.choices[0].message.content

    registro = rodar_laboratorio(chamar)
    registro["modelo"] = modelo
    registro["build"] = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "desconhecido")[:7]

    # O registro inteiro vai para o log do Railway também: se a resposta se perder no
    # caminho, a rodada não se perde junto — e cota gasta não se repõe.
    print(imprimir(registro), flush=True)

    if corpo.get("formato") == "texto":
        return imprimir(registro), 200, {"Content-Type": "text/plain; charset=utf-8"}
    return jsonify(registro), 200


@app.route("/", methods=["GET"])
def home():
    # O commit no ar. Sem isto, conferir se um deploy fechou custava UMA ANÁLISE
    # (~6.299 tokens de um teto diário compartilhado com cliente pagante), porque a
    # única prova de que o código novo subiu era o comportamento novo aparecer.
    # Agora custa zero. O Railway injeta esta variável em cada build.
    sha = (os.environ.get("RAILWAY_GIT_COMMIT_SHA") or "desconhecido")[:7]
    return f"Nexo Servidor ativo. build={sha}", 200

# ─── INÍCIO ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
