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
    msg["Subject"] = "✅ Sua chave de ativação do NEXO chegou!"
    msg["From"]    = GMAIL_EMAIL
    msg["To"]      = email_cliente

    expiracao_texto = "Vitalícia" if expiracao == "definitivo" else f"Válida até {expiracao}"

    corpo = f"""
Olá, {nome_cliente}!

Obrigado pela sua compra. Sua chave de ativação do NEXO está pronta:

━━━━━━━━━━━━━━━━━━━━━━━━
🔑 CHAVE: {chave}
📋 Plano: {plano_nome}
📅 Validade: {expiracao_texto}
━━━━━━━━━━━━━━━━━━━━━━━━

📥 Baixe o NEXO aqui: {DOWNLOAD_COMPLETO}

Como instalar e ativar:
1. Baixe e extraia o arquivo .zip
2. Execute o "Instalar_Nexo_Completo"
3. Abra o NEXO pelo atalho criado na área de trabalho
4. Na tela de ativação, digite a chave acima
5. Clique em "Ativar"
6. Pronto! O NEXO estará liberado.

Qualquer dúvida, fale comigo pelo WhatsApp: {WHATSAPP}

Boas análises!
Equipe NEXO
nexo.analises@gmail.com
"""
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_EMAIL, GMAIL_SENHA)
        server.sendmail(GMAIL_EMAIL, email_cliente, msg.as_string())

# ─── WEBHOOK ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        dados = request.json or request.form.to_dict()

        # Campos que a Eduzz envia
        nome_cliente  = dados.get("client_name", "Cliente")
        email_cliente = dados.get("client_email", "")
        valor         = str(int(float(dados.get("transaction_value", "0"))))
        status        = dados.get("transaction_status", "")

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
