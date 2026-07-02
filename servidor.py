from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import json
from groq import Groq

app = Flask(__name__)

# ─── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
GMAIL_EMAIL    = os.environ.get("GMAIL_EMAIL", "nexo.analises@gmail.com")
GMAIL_SENHA    = os.environ.get("GMAIL_SENHA")  # senha de app, definida nas variáveis de ambiente
SPREADSHEET_ID = "1Z-uW3AVXComh-3DGvdRiAASQL567oOf1DThJwNXt3Sc"
SHEET_NAME     = "Página1"
WHATSAPP       = "(21) 92006-9321"
DOWNLOAD_COMPLETO = "https://drive.google.com/file/d/1UNAF_QAu1otB88bGLmjhWhxnTyBd5IrH/view?usp=sharing"

# Credenciais Google — lidas do ambiente (Railway/Render) ou arquivo local
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# Chave da Groq — fica SOMENTE no servidor, nunca no app do cliente
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Segredo compartilhado entre o app e o servidor (opcional, dificulta abuso da rota /analisar)
APP_TOKEN = os.environ.get("APP_TOKEN", "")

PLANOS = {
    "97":  ("lancamento",  1,  "months"),
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
    ])

def enviar_email(email_cliente, nome_cliente, chave, plano_nome, expiracao):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "✅ Sua chave de ativação do NEXO Análise chegou!"
    msg["From"]    = GMAIL_EMAIL
    msg["To"]      = email_cliente

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

Qualquer dúvida, fale comigo pelo WhatsApp: {WHATSAPP}

Boas análises!
Equipe NEXO
nexo.analises@gmail.com
"""
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_EMAIL, GMAIL_SENHA)
        server.sendmail(GMAIL_EMAIL, email_cliente, msg.as_string())

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

def gerar_analise(dados, segmento):
    modos = {
        "Loja / Varejo e Moda": "🟢 MODO GIRO — foco em estoque, giro de produtos, preço, promoção e vendas rápidas.",
        "Farmácia": "🟢 MODO GIRO — foco em estoque, giro de produtos, preço, promoção e vendas rápidas.",
        "Restaurante / Alimentação": "🍽️ MODO FLUXO — foco em tempo de atendimento, ticket médio, eficiência operacional, cardápio e desperdício.",
        "Academia / Fitness": "🏋️ MODO RETENÇÃO — foco em retenção de clientes, cancelamentos, recorrência, engajamento e reativação.",
    }
    modo = modos.get(segmento, "")
    resposta = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
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
                f"- Sempre use linguagem direta e de ação: implemente, ajuste, corrija, organize, reduza, aumente, reative, otimize, divulgue. "
                f"Evite: 'seria interessante', 'recomenda-se avaliar', 'pode-se considerar'.\n\n"
                f"PRINCÍPIO CENTRAL: a qualidade da decisão depende diretamente da qualidade das informações fornecidas. "
                f"Use TODOS os dados do negócio informados abaixo — cada número e detalhe ajuda a calibrar a decisão.\n\n"
                f"MODO DE DECISÃO DESTE NEGÓCIO: {modo}\n\n"
                f"FORMATO OBRIGATÓRIO DE SAÍDA (use exatamente estes títulos, nesta ordem):\n\n"
                f"🎯 1. DECISÃO MAIS IMPORTANTE AGORA\n"
                f"Uma única decisão crítica e direta.\n\n"
                f"🔧 2. AÇÕES IMEDIATAS\n"
                f"No máximo 3 ações práticas, executáveis e simples, compatíveis com a verba e o tempo informados. "
                f"Ao final de CADA ação, acrescente uma tag curta entre parênteses com o custo e o prazo de resultado, "
                f"neste formato exato: (Custo: zero | Resultado em: ~7 dias). "
                f"Use valores realistas em reais (ou 'zero') e prazos aproximados. Não use notas, pontuações ou percentuais de prioridade.\n\n"
                f"⚠️ 3. O QUE ESTÁ TE FAZENDO PERDER DINHEIRO\n"
                f"Problemas claros e acionáveis identificados nos dados.\n\n"
                f"📈 4. OPORTUNIDADE MAIS RÁPIDA DE GANHO\n"
                f"Uma ação de retorno rápido e realista.\n\n"
                f"🧭 5. PRÓXIMO PASSO\n"
                f"Uma instrução final clara de continuidade.\n\n"
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
                f"DADOS DO NEGÓCIO:\n{dados}"
            )
        }]
    )
    return resposta.choices[0].message.content

@app.route("/analisar", methods=["POST"])
def analisar():
    try:
        if groq_client is None:
            return jsonify({"status": "erro", "motivo": "Servidor sem chave de IA configurada."}), 503

        # Verificação opcional do segredo do app
        if APP_TOKEN and request.headers.get("X-App-Token", "") != APP_TOKEN:
            return jsonify({"status": "erro", "motivo": "Acesso não autorizado."}), 401

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

        analise = gerar_analise(dados, segmento)
        return jsonify({"status": "ok", "analise": analise}), 200

    except Exception as e:
        print(f"ERRO no /analisar: {e}")
        return jsonify({"status": "erro", "motivo": f"Falha ao gerar a análise: {e}"}), 200

# ─── WEBHOOK ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        dados = request.json or request.form.to_dict()

        # Campos que a Eduzz envia
        nome_cliente  = dados.get("cus_name", "Cliente")
        email_cliente = dados.get("cus_email", "")
        valor         = str(int(float(dados.get("trans_value", "0"))))
        status        = dados.get("trans_status", "")

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

@app.route("/", methods=["GET"])
def home():
    return "Nexo Servidor ativo.", 200

# ─── INÍCIO ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
