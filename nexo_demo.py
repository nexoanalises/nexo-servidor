import requests
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.lib import colors
import os
import sys
import re
import json
from xml.sax.saxutils import escape
from datetime import datetime, date

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "️"
    "]+",
    flags=re.UNICODE
)

# ─── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
SERVIDOR_URL = "https://nexo-servidor-production.up.railway.app"
WHATSAPP = "(21) 92006-9321"
DIAS_TRIAL = 7

if getattr(sys, 'frozen', False):
    _DIR = os.path.dirname(sys.executable)
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))
TRIAL_ARQUIVO = os.path.join(_DIR, "nexo_trial.json")

# ─── TRIAL (7 DIAS GRÁTIS) ──────────────────────────────────────────────────────

def carregar_trial():
    if os.path.exists(TRIAL_ARQUIVO):
        try:
            with open(TRIAL_ARQUIVO, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def salvar_trial_inicio():
    with open(TRIAL_ARQUIVO, "w") as f:
        json.dump({"inicio": datetime.now().isoformat()}, f)

def status_trial():
    """Retorna (iniciado, ativo, dias_restantes)."""
    dados = carregar_trial()
    if dados is None:
        return False, True, DIAS_TRIAL  # não iniciado ainda → libera
    inicio = datetime.fromisoformat(dados["inicio"])
    dias_passados = (datetime.now() - inicio).days
    restantes = max(0, DIAS_TRIAL - dias_passados)
    return True, restantes > 0, restantes

# ─── VERIFICAÇÃO INICIAL ─────────────────────────────────────────────────────────

iniciado, trial_ativo, dias_restantes = status_trial()

if iniciado and not trial_ativo:
    root_err = tk.Tk()
    root_err.withdraw()
    messagebox.showinfo(
        "Período gratuito encerrado",
        f"Seu período de teste gratuito de {DIAS_TRIAL} dias chegou ao fim.\n\n"
        f"Para continuar usando o NEXO Análise, adquira sua licença:\n"
        f"WhatsApp: {WHATSAPP}\nnexo.analises@gmail.com"
    )
    root_err.destroy()
    sys.exit()

# ─── APP PRINCIPAL ───────────────────────────────────────────────────────────────

def analisar(dados, segmento):
    try:
        resposta = requests.post(
            f"{SERVIDOR_URL}/analisar",
            json={"modo": "demo", "segmento": segmento, "dados": dados},
            timeout=90
        )
        dados_resp = resposta.json()
        if resposta.status_code == 200 and dados_resp.get("status") == "ok":
            return True, dados_resp["analise"]
        return False, ("Não foi possível gerar a análise no momento.\n"
                f"Motivo: {dados_resp.get('motivo', 'erro desconhecido')}\n"
                "Tente novamente em instantes.")
    except requests.exceptions.RequestException:
        return False, ("Não foi possível conectar ao servidor de análise.\n"
                "Verifique sua conexão com a internet e tente novamente.")


def salvar_pdf(resultado, segmento, nome_negocio):
    nome_arquivo = re.sub(r'[\\/:*?"<>|]', '_', nome_negocio)
    saida = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        initialfile=f"analise_{nome_arquivo}.pdf",
        title="Salvar análise em PDF"
    )
    if not saida:
        return None
    doc = SimpleDocTemplate(saida, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("titulo", fontSize=20, textColor=colors.HexColor("#6A0DAD"),
                                   spaceAfter=10, fontName="Helvetica-Bold", alignment=1)
    estilo_slogan = ParagraphStyle("slogan", fontSize=11, textColor=colors.HexColor("#888888"),
                                   spaceAfter=20, fontName="Helvetica", alignment=1)
    estilo_rodape = ParagraphStyle("rodape", fontSize=9, textColor=colors.HexColor("#6A0DAD"),
                                   spaceBefore=20, fontName="Helvetica", alignment=1)
    estilo_secao = ParagraphStyle("secao", fontSize=13, textColor=colors.HexColor("#6A0DAD"),
                                  spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold")
    estilo_manifesto = ParagraphStyle("manifesto", fontSize=11, textColor=colors.HexColor("#6A0DAD"),
                                      spaceBefore=20, fontName="Helvetica-Oblique", alignment=1)
    conteudo = []
    conteudo.append(Paragraph("NEXO Análise", estilo_titulo))
    conteudo.append(Paragraph("Transformando dados em decisões", estilo_slogan))
    conteudo.append(Spacer(1, 0.3*cm))
    data_hoje = date.today().strftime("%d/%m/%Y")
    conteudo.append(Paragraph(f"Negócio: {escape(nome_negocio)} | Segmento: {escape(segmento)}", estilos["Heading2"]))
    conteudo.append(Paragraph(f"Data: {data_hoje}", estilos["Normal"]))
    conteudo.append(Spacer(1, 0.3*cm))
    titulo_secao_re = re.compile(r"^\d\.\s")
    for linha in resultado.split("\n"):
        linha_limpa = EMOJI_RE.sub("", linha).strip()
        if linha_limpa == "":
            conteudo.append(Spacer(1, 0.3*cm))
        elif titulo_secao_re.match(linha_limpa):
            conteudo.append(Paragraph(escape(linha_limpa.replace("**", "")), estilo_secao))
        else:
            conteudo.append(Paragraph(escape(linha_limpa.replace("**", "")), estilos["Normal"]))
    conteudo.append(Spacer(1, 1*cm))
    conteudo.append(Paragraph("Este é um relatório de decisão, não um relatório de dados. Cada linha foi selecionada para gerar resultado.", estilo_manifesto))
    conteudo.append(Paragraph("NEXO Análise — Transformando dados em decisões", estilo_rodape))
    conteudo.append(Paragraph(f"WhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com", estilo_rodape))
    doc.build(conteudo)
    return saida

# ─── TELA DE BOAS-VINDAS ─────────────────────────────────────────────────────────

def mostrar_boas_vindas(callback_iniciar):
    splash = tk.Tk()
    splash.title("NEXO Análise")
    splash.geometry("520x420")
    splash.resizable(False, False)
    splash.configure(bg="#1a0033")
    splash.eval('tk::PlaceWindow . center')

    # Título
    tk.Label(splash, text="Bem-vindo ao NEXO Análise",
             font=("Arial", 20, "bold"), bg="#1a0033", fg="white").pack(pady=(32, 8))

    # Subtítulo
    tk.Label(splash,
             text="Nos próximos minutos você receberá recomendações\nbaseadas nos dados do seu negócio.",
             font=("Arial", 12), bg="#1a0033", fg="#dddddd", justify="center").pack(pady=(0, 20))

    # Caixa de aviso (borda coral)
    frame_aviso = tk.Frame(splash, bg="#1a0033", highlightbackground="#ff751f",
                           highlightthickness=2, padx=16, pady=12)
    frame_aviso.pack(padx=30, fill="x")
    tk.Label(frame_aviso,
             text="📈  Quanto mais precisos forem os dados informados,\n"
                  "mais úteis e direcionadas serão as recomendações.",
             font=("Arial", 11), bg="#1a0033", fg="#ff751f", justify="center").pack()

    # Checkbox de aceite
    var_aceite = tk.BooleanVar(value=False)

    def ao_marcar():
        if var_aceite.get():
            btn_iniciar.config(state="normal", bg="#ff751f", fg="white", cursor="hand2")
        else:
            btn_iniciar.config(state="disabled", bg="#4a3a3a", fg="#888888", cursor="")

    frame_check = tk.Frame(splash, bg="#1a0033")
    frame_check.pack(pady=(20, 0), padx=30, fill="x")
    tk.Checkbutton(frame_check,
                   text="Entendi e utilizarei dados reais ou próximos\nda realidade do meu negócio.",
                   variable=var_aceite, command=ao_marcar,
                   bg="#1a0033", fg="white", selectcolor="#6A0DAD",
                   activebackground="#1a0033", activeforeground="white",
                   font=("Arial", 11), anchor="w", justify="left").pack(anchor="w")

    # Botão Iniciar (começa desativado)
    btn_iniciar = tk.Button(splash, text="Iniciar Análise",
                            font=("Arial", 14, "bold"),
                            bg="#4a3a3a", fg="#888888",
                            padx=24, pady=10,
                            state="disabled", relief="flat",
                            command=lambda: [splash.destroy(), callback_iniciar()])
    btn_iniciar.pack(pady=(20, 8))

    # Rodapé
    tk.Label(splash, text="Bons negócios! 🚀",
             font=("Arial", 11, "italic"), bg="#1a0033", fg="#b366ff").pack(pady=(4, 0))

    # Fechar no X encerra o app
    splash.protocol("WM_DELETE_WINDOW", lambda: sys.exit())
    splash.mainloop()

# ─── JANELA PRINCIPAL ────────────────────────────────────────────────────────────

def iniciar_app():
    janela = tk.Tk()
    janela.title("Nexo — Versão Demo (7 dias grátis)")
    janela.geometry("800x980")
    janela.resizable(True, True)
    janela.configure(bg="#1a0033")

    tk.Label(janela, text="NEXO Análise", font=("Arial", 30, "bold"), bg="#1a0033", fg="#b366ff").pack(pady=10)
    tk.Label(janela, text="Transformando dados em decisões", font=("Arial", 13), bg="#1a0033", fg="#dddddd").pack()
    tk.Frame(janela, bg="#6A0DAD", height=2, width=700).pack(pady=10)

    tk.Label(janela, text="Selecione o tipo de negócio:", font=("Arial", 13, "bold"), bg="#1a0033", fg="white").pack()
    segmentos = ["Loja / Varejo e Moda", "Restaurante / Alimentação",
                 "Academia / Fitness", "Farmácia"]
    var_segmento = tk.StringVar(value=segmentos[0])
    combo_segmento = ttk.Combobox(janela, textvariable=var_segmento, values=segmentos,
                                   font=("Arial", 13), state="readonly", width=40)
    combo_segmento.pack(pady=8)

    tk.Label(janela,
             text="Quanto mais informações relevantes você fornecer, mais precisa será a análise e maior\n"
                  "será a qualidade da tomada de decisão. Os campos aceitam informações resumidas ou detalhadas.",
             font=("Arial", 9), bg="#1a0033", fg="#b366ff", justify="center").pack(pady=(0, 8))

    frame_inferior = tk.Frame(janela, bg="#1a0033")
    frame_inferior.pack(side="bottom", fill="x")

    frame_container = tk.Frame(janela, bg="#1a0033")
    frame_container.pack(side="top", fill="both", expand=True, padx=20)

    canvas = tk.Canvas(frame_container, bg="#1a0033", highlightthickness=0)
    scrollbar = ttk.Scrollbar(frame_container, orient="vertical", command=canvas.yview)
    frame_campos = tk.Frame(canvas, bg="#1a0033")

    frame_campos.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=frame_campos, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def scroll_mouse(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind_all("<MouseWheel>", scroll_mouse)

    campos_widgets = {}

    def criar_campo(frame, label, key, tipo="entry", dica=""):
        tk.Label(frame, text=label, font=("Arial", 12, "bold"), bg="#1a0033", fg="#dddddd", anchor="w").pack(fill="x", pady=(6,0))
        if dica:
            tk.Label(frame, text=dica, font=("Arial", 10), bg="#1a0033", fg="#888888", anchor="w", wraplength=700).pack(fill="x")
        if tipo == "text":
            widget = tk.Text(frame, height=3, font=("Arial", 12), bg="#2d0052", fg="white", insertbackground="white")
        else:
            widget = tk.Entry(frame, font=("Arial", 12), bg="#2d0052", fg="white", insertbackground="white")
        widget.pack(fill="x", pady=2)
        campos_widgets[key] = widget

    def criar_checkboxes(frame, label, key, opcoes, dica=""):
        tk.Label(frame, text=label, font=("Arial", 12, "bold"), bg="#1a0033", fg="#dddddd", anchor="w").pack(fill="x", pady=(6,0))
        if dica:
            tk.Label(frame, text=dica, font=("Arial", 10), bg="#1a0033", fg="#888888", anchor="w", wraplength=700).pack(fill="x")
        vars_check = []
        frame_checks = tk.Frame(frame, bg="#1a0033")
        frame_checks.pack(fill="x")
        for opcao in opcoes:
            var = tk.BooleanVar()
            tk.Checkbutton(frame_checks, text=opcao, variable=var, bg="#1a0033", fg="white",
                          selectcolor="#6A0DAD", activebackground="#1a0033", activeforeground="white",
                          font=("Arial", 11)).pack(anchor="w")
            vars_check.append((opcao, var))
        campos_widgets[key] = vars_check

    def get_valor(key):
        widget = campos_widgets.get(key)
        if widget is None:
            return ""
        if isinstance(widget, list):
            selecionados = [op for op, var in widget if var.get()]
            return ", ".join(selecionados) if selecionados else "Não informado"
        if isinstance(widget, tk.Text):
            return widget.get("1.0", tk.END).strip()
        return widget.get().strip()

    canais_opcoes = ["Instagram", "Facebook", "WhatsApp", "Tráfego Pago (Google/Meta Ads)",
                     "Indicação", "Site próprio", "Outros"]

    def carregar_campos(segmento=None):
        nonlocal frame_campos
        for widget in frame_campos.winfo_children():
            widget.destroy()
        campos_widgets.clear()
        canvas.delete("all")
        frame_campos = tk.Frame(canvas, bg="#1a0033")
        frame_campos.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=frame_campos, anchor="nw")

        tk.Label(frame_campos, text="── INFORMAÇÕES GERAIS ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)

        seg = var_segmento.get()

        dicas_nome = {
            "Loja / Varejo e Moda": "Ex: Loja Vitória, Materiais de Construção São José, Armarinho da Ana, Calçados Show, Mercadinho Bom Preço",
            "Restaurante / Alimentação": "Ex: Cantina do José, Restaurante Sabor & Cia, Pizzaria Forno a Lenha",
            "Academia / Fitness": "Ex: Power Fitness, Academia Corpo em Forma, Studio Pilates Vida",
            "Farmácia": "Ex: Drogaria Saúde, Farmácia Popular do Bairro, Drogamais",
        }
        dicas_objetivo = {
            "Loja / Varejo e Moda": "Informe o principal resultado que deseja alcançar agora. Ex: 'Aumentar as vendas em 20% nos próximos 60 dias' ou 'Reduzir o estoque parado' ou outros.",
            "Restaurante / Alimentação": "Informe o principal resultado que deseja alcançar agora. Ex: 'Aumentar o ticket médio em 15%' ou 'Reduzir o desperdício de alimentos em 30%' ou outros.",
            "Academia / Fitness": "Informe o principal resultado que deseja alcançar agora. Ex: 'Reduzir cancelamentos em 50%' ou 'Captar 30 novos alunos em 60 dias' ou outros.",
            "Farmácia": "Informe o principal resultado que deseja alcançar agora. Ex: 'Aumentar vendas de perfumaria em 25%' ou 'Reduzir a falta de produtos em estoque' ou outros.",
        }
        dicas_faturamento = {
            "Loja / Varejo e Moda": "Total de receitas brutas no período. Some vendas da loja física, WhatsApp, redes sociais e site. Ex: R$ 45.000",
            "Restaurante / Alimentação": "Total de receitas brutas no período. Some salão, delivery e eventos. Ex: R$ 60.000",
            "Academia / Fitness": "Total de receitas brutas no período. Some mensalidades, planos, day-use e aulas avulsas. Ex: R$ 35.000",
            "Farmácia": "Total de receitas brutas no período. Some medicamentos, perfumaria, conveniência e manipulados. Ex: R$ 80.000",
        }
        dicas_meta = {
            "Loja / Varejo e Moda": "Quanto você esperava faturar no período. Ex: R$ 50.000",
            "Restaurante / Alimentação": "Quanto você esperava faturar no período. Ex: R$ 70.000",
            "Academia / Fitness": "Quanto você esperava faturar no período. Ex: R$ 40.000",
            "Farmácia": "Quanto você esperava faturar no período. Ex: R$ 95.000",
        }
        dicas_custos = {
            "Loja / Varejo e Moda": "Some todos os custos do período: aluguel, salários, energia, mercadoria reposta, marketing, embalagens, taxas de cartão.",
            "Restaurante / Alimentação": "Some todos os custos do período: aluguel, salários, insumos/alimentos, gás, energia, embalagens delivery, marketing, taxas de cartão e apps.",
            "Academia / Fitness": "Some todos os custos do período: aluguel, salários de instrutores e recepção, energia, manutenção de aparelhos, sistema de gestão, marketing.",
            "Farmácia": "Some todos os custos do período: aluguel, salários, reposição de medicamentos e perfumaria, energia, sistema de gestão, marketing, taxas de cartão.",
        }
        dicas_funcionarios = {
            "Loja / Varejo e Moda": "Total de colaboradores ativos no período, incluindo sócios que atendem na loja. Ex: 3 vendedoras + 1 caixa + 1 sócio = 5",
            "Restaurante / Alimentação": "Total de colaboradores ativos no período, incluindo sócios. Ex: 2 cozinheiros + 3 garçons + 1 caixa + 1 motoboy + 1 sócio = 8",
            "Academia / Fitness": "Total de colaboradores ativos no período, incluindo sócios. Ex: 3 instrutores + 2 recepcionistas + 1 sócio = 6",
            "Farmácia": "Total de colaboradores ativos no período, incluindo sócios. Ex: 2 farmacêuticos + 2 atendentes + 1 caixa + 1 sócio = 6",
        }
        dicas_capacidade = {
            "Loja / Varejo e Moda": "Em quanto % a loja está operando em relação ao seu potencial de vendas? Considere movimento, atendimentos e dias parados. Ex: 70%",
            "Restaurante / Alimentação": "Em quanto % das mesas/lugares você consegue ocupar nos horários de pico? Ex: 80% no almoço, 50% no jantar",
            "Academia / Fitness": "Em quanto % da sua capacidade total de alunos a academia opera hoje? Ex: 60% (300 alunos ativos numa estrutura para 500)",
            "Farmácia": "Em quanto % do potencial de atendimento sua farmácia opera? Considere o fluxo de clientes nos horários comerciais. Ex: 75%",
        }
        dicas_vendas_canal = {
            "Loja / Varejo e Moda": "Distribua suas vendas entre os canais. Ex: Loja Física 50% | WhatsApp 35% | Instagram 15%",
            "Restaurante / Alimentação": "Distribua suas vendas entre os canais. Ex: Salão 40% | iFood 35% | WhatsApp 20% | Delivery próprio 5%",
            "Academia / Fitness": "Distribua a origem das matrículas. Ex: Indicação 50% | Instagram 30% | Google 15% | Panfletagem 5%",
            "Farmácia": "Distribua suas vendas entre os canais. Ex: Balcão 70% | WhatsApp 20% | Tele-entrega 10%",
        }
        dicas_desafios = {
            "Loja / Varejo e Moda": "Descreva os maiores problemas enfrentados. Ex: estoque parado, queda de clientes, ticket médio baixo, concorrência forte.",
            "Restaurante / Alimentação": "Descreva os maiores problemas enfrentados. Ex: alta no preço dos insumos, mesas vazias no jantar, problemas com delivery, desperdício.",
            "Academia / Fitness": "Descreva os maiores problemas enfrentados. Ex: muitos cancelamentos, baixa frequência dos alunos, aparelhos quebrando, falta de instrutores.",
            "Farmácia": "Descreva os maiores problemas enfrentados. Ex: falta de produtos em estoque, queda na venda de perfumaria, concorrência de redes grandes, baixa fidelização.",
        }

        criar_campo(frame_campos, "Nome do negócio *", "nome_negocio", dica=dicas_nome[seg])
        criar_campo(frame_campos, "Período analisado *", "periodo",
                    dica="Ex: Maio/2026, Janeiro a Março/2026. Todos os valores abaixo devem se referir a este período.")
        criar_campo(frame_campos, "Objetivo principal", "objetivo_principal", tipo="text", dica=dicas_objetivo[seg])
        criar_campo(frame_campos, "Faturamento do período (R$) *", "faturamento", dica=dicas_faturamento[seg])
        criar_campo(frame_campos, "Meta de faturamento (R$)", "meta", dica=dicas_meta[seg])
        criar_campo(frame_campos, "Investimento/Custos do período (R$)", "custos", dica=dicas_custos[seg])
        criar_campo(frame_campos, "Lucro líquido (R$)", "lucro",
                    dica="Faturamento menos todos os custos. Se teve prejuízo, informe com sinal negativo: -R$ 2.000")
        criar_campo(frame_campos, "Verba destinada para melhorias", "verba_melhorias", tipo="text",
                    dica="Informe um valor aproximado ou uma faixa. Ex: 'R$ 500', 'entre R$ 2.000 e R$ 5.000', 'acima de R$ 10.000' ou 'não tenho no momento'.")
        criar_campo(frame_campos, "Tempo disponível para implementação", "tempo_disponivel", tipo="text",
                    dica="Informe quantas horas por semana você consegue dedicar à implementação das melhorias sugeridas. Ex: '3 horas por semana', 'até 8 horas/semana'.")
        criar_campo(frame_campos, "Número de funcionários", "funcionarios", dica=dicas_funcionarios[seg])
        criar_campo(frame_campos, "Capacidade operacional ocupada (%)", "capacidade", dica=dicas_capacidade[seg])
        criar_checkboxes(frame_campos, "Principais canais de aquisição de clientes", "canais", canais_opcoes,
                         dica="Selecione por onde a maioria dos seus clientes chega até você.")
        criar_campo(frame_campos, "Vendas por canal (quantidade ou %)", "vendas_canal", dica=dicas_vendas_canal[seg])
        criar_campo(frame_campos, "Principais desafios do período", "desafios", tipo="text", dica=dicas_desafios[seg])
        criar_campo(frame_campos, "Observações adicionais", "observacoes", tipo="text",
                    dica="Qualquer informação relevante que não se encaixou nos campos acima.")

        if seg == "Loja / Varejo e Moda":
            tk.Label(frame_campos, text="── LOJA / VAREJO E MODA ──", font=("Arial", 12, "bold"),
                     bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
            criar_campo(frame_campos, "Produtos mais vendidos", "produtos_top",
                        dica="Liste os 3 a 5 produtos com maior saída no período.")
            criar_campo(frame_campos, "Produtos com baixo giro", "produtos_baixo",
                        dica="Produtos que estão há mais tempo parados no estoque, sem vender.")
            criar_campo(frame_campos, "Coleção atual", "colecao",
                        dica="Ex: Inverno 2026, Verão 2026. Se não trabalha com coleções, escreva 'não se aplica'.")
            criar_campo(frame_campos, "Peças/modelos com maior saída", "pecas_top",
                        dica="Liste as peças ou modelos que mais venderam no período.")
            criar_campo(frame_campos, "Peças/modelos encalhados", "pecas_encalhadas",
                        dica="Liste as peças ou modelos que praticamente não venderam.")
            criar_campo(frame_campos, "Tamanhos com maior saída", "tamanhos_top",
                        dica="Ex: P e M são os que mais vendem.")
            criar_campo(frame_campos, "Tamanhos encalhados", "tamanhos_encalhados",
                        dica="Ex: GG e XG ficam parados no estoque.")
            criar_campo(frame_campos, "Percentual de vendas: Roupas vs Calçados (%)", "proporcao_loja",
                        dica="Ex: Roupas 70% | Calçados 30%. Se não vender calçados, escreva 'não se aplica'.")
            criar_campo(frame_campos, "Ticket médio (R$)", "ticket_medio",
                        dica="Valor médio gasto por cliente em cada compra. Ex: R$ 80")
            criar_campo(frame_campos, "Número de clientes atendidos", "clientes",
                        dica="Quantidade aproximada de clientes atendidos no período.")
            criar_campo(frame_campos, "Taxa de conversão (%)", "conversao",
                        dica="De cada 10 pessoas que entram na loja ou conversam com você, quantas compram? Ex: 30%")
            criar_campo(frame_campos, "Reclamações recebidas", "reclamacoes",
                        dica="Descreva as principais reclamações dos clientes no período, se houver.")
            criar_campo(frame_campos, "Trocas por defeito", "trocas",
                        dica="Informe o material trocado, o motivo da troca, a quantidade e o fornecedor responsável.")
            criar_campo(frame_campos, "Fornecedores que cumprem prazo (%)", "fornecedores",
                        dica="De todos os fornecedores, quantos % entregam no prazo combinado? Ex: 80%")
            criar_campo(frame_campos, "Vendas realizadas via WhatsApp", "vendas_zap",
                        dica="Quantidade ou valor aproximado de vendas feitas pelo WhatsApp no período.")
            criar_campo(frame_campos, "Situação do estoque atual", "estoque", tipo="text",
                        dica="Descreva como está o estoque hoje: excesso, falta de itens, produtos vencidos/avariados, etc.")

        elif seg == "Restaurante / Alimentação":
            tk.Label(frame_campos, text="── RESTAURANTE / ALIMENTAÇÃO ──", font=("Arial", 12, "bold"),
                     bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
            criar_campo(frame_campos, "Dias e horário de funcionamento", "horario",
                        dica="Ex: Terça a domingo, das 11h às 23h.")
            criar_campo(frame_campos, "Média de clientes por dia", "clientes_dia",
                        dica="Quantidade média de clientes atendidos por dia (salão + delivery).")
            criar_campo(frame_campos, "Prato mais pedido", "prato_top",
                        dica="O item do cardápio com maior saída no período.")
            criar_campo(frame_campos, "CMV - Custo de Mercadoria Vendida (%)", "cmv",
                        dica="Custo dos ingredientes dividido pelo faturamento, em %. Ideal: entre 25% e 35%. Se não souber calcular, descreva o gasto com insumos.")
            criar_campo(frame_campos, "Desperdício de alimentos", "desperdicio",
                        dica="Descreva o quanto e o que costuma ser desperdiçado. Ex: '2kg de carne por semana', 'sobras de massa no fim do dia'.")
            criar_campo(frame_campos, "Capacidade de assentos vs ocupação (%)", "ocupacao",
                        dica="Quantos lugares o salão tem e qual % fica ocupado nos horários de pico? Ex: '40 lugares, 80% no almoço'.")
            criar_campo(frame_campos, "Canal majoritário", "canal",
                        dica="Salão, Delivery ou Ambos?")
            criar_campo(frame_campos, "Avaliações dos clientes (nota média)", "avaliacoes",
                        dica="Nota média recebida em apps como Google, iFood, etc. Ex: 4.3")

        elif seg == "Academia / Fitness":
            tk.Label(frame_campos, text="── ACADEMIA / FITNESS ──", font=("Arial", 12, "bold"),
                     bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
            criar_campo(frame_campos, "Total de alunos", "total_alunos",
                        dica="Quantidade de alunos com plano ativo ao final do período.")
            criar_campo(frame_campos, "Novos alunos no período", "novos_alunos",
                        dica="Quantidade de matrículas novas realizadas no período.")
            criar_campo(frame_campos, "Cancelamentos no período", "cancelamentos",
                        dica="Quantidade de alunos que cancelaram ou não renovaram no período.")
            criar_campo(frame_campos, "Taxa de renovação de planos (%)", "renovacao",
                        dica="De todos os planos que venceram no período, quantos % foram renovados? Ex: 65%")
            criar_campo(frame_campos, "Plano mais vendido", "plano_top",
                        dica="O plano ou modalidade com maior número de matrículas. Ex: 'Mensal musculação', 'Trimestral'.")
            criar_campo(frame_campos, "Horários de pico", "horario_pico",
                        dica="Os horários com maior movimento de alunos. Ex: '6h-8h e 18h-21h'.")
            criar_campo(frame_campos, "Manutenções realizadas no período", "manutencoes",
                        dica="Quantidade e tipo de manutenções feitas nos equipamentos.")
            criar_campo(frame_campos, "Novos aparelhos adquiridos", "aparelhos_novos",
                        dica="Liste os equipamentos novos adquiridos no período, se houver.")
            criar_campo(frame_campos, "Aparelhos desativados/descartados", "aparelhos_fora",
                        dica="Liste os equipamentos quebrados, desativados ou descartados no período.")
            criar_campo(frame_campos, "Reclamações recebidas + motivo", "reclamacoes", tipo="text",
                        dica="Descreva as principais reclamações dos alunos e o motivo. Ex: 'aparelho quebrado', 'falta de instrutor', 'ar-condicionado'.")

        elif seg == "Farmácia":
            tk.Label(frame_campos, text="── FARMÁCIA ──", font=("Arial", 12, "bold"),
                     bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
            criar_campo(frame_campos, "Medicamentos mais vendidos", "med_top",
                        dica="Liste os 3 a 5 medicamentos ou categorias com maior saída no período.")
            criar_campo(frame_campos, "Proporção Medicamentos vs Perfumaria (%)", "proporcao",
                        dica="Ex: Medicamentos 60% | Perfumaria e conveniência 40%.")
            criar_campo(frame_campos, "Ticket médio (R$)", "ticket_medio",
                        dica="Valor médio gasto por cliente em cada compra. Ex: R$ 55")
            criar_campo(frame_campos, "Clientes fidelizados", "fidelizados",
                        dica="Quantidade aproximada de clientes recorrentes, que compram com frequência.")
            criar_campo(frame_campos, "Itens em estoque crítico", "estoque_critico", tipo="text",
                        dica="Liste os produtos que costumam faltar ou que estão perto do vencimento.")

        frame_campos.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.yview_moveto(0)

    def ao_trocar_segmento(event):
        carregar_campos()
        janela.update_idletasks()

    combo_segmento.bind("<<ComboboxSelected>>", ao_trocar_segmento)
    carregar_campos()

    def executar_analise():
        nome = get_valor("nome_negocio")
        if not nome:
            messagebox.showerror("Erro", "Preencha o nome do negócio!")
            return

        seg = var_segmento.get()
        dados = f"Segmento: {seg}\n"
        for key in campos_widgets:
            dados += f"{key}: {get_valor(key)}\n"

        botao_analisar.config(state="disabled", text="Analisando...")
        janela.update()

        sucesso, resultado = analisar(dados, seg)

        caixa_resultado.config(state="normal")
        caixa_resultado.delete("1.0", tk.END)
        caixa_resultado.insert(tk.END, resultado)
        caixa_resultado.config(state="disabled")

        botao_analisar.config(state="normal", text="Analisar Negócio")

        if not sucesso:
            messagebox.showwarning("Análise não concluída",
                f"{resultado}\n\nSeu período de teste NÃO foi afetado.")
            return

        # Inicia o trial na primeira análise bem-sucedida
        if not iniciado:
            salvar_trial_inicio()

        # Recalcula dias restantes
        _, _, dias = status_trial()
        label_contador.config(text=f"Teste gratuito: {dias} de {DIAS_TRIAL} dias restantes")

        pdf = salvar_pdf(resultado, seg, nome)
        msg_pdf = f"\nPDF salvo em:\n{pdf}\n\n" if pdf else "\n\n"

        if dias > 1:
            messagebox.showinfo("Análise concluída",
                f"Análise concluída!{msg_pdf}"
                f"Seu período de teste: {dias} dias restantes.\n"
                "Para uso ilimitado após o teste, adquira uma licença:\n"
                f"WhatsApp: {WHATSAPP}")
        else:
            messagebox.showinfo("Análise concluída",
                f"Análise concluída!{msg_pdf}"
                f"⚠️ Último dia do seu período gratuito.\n"
                "Adquira uma licença para continuar:\n"
                f"WhatsApp: {WHATSAPP}\nnexo.analises@gmail.com")

    botao_analisar = tk.Button(frame_inferior, text="Analisar Negócio",
                               font=("Arial", 15, "bold"), bg="#b366ff", fg="white",
                               padx=20, pady=10, command=executar_analise)
    botao_analisar.pack(pady=(10, 2))

    tk.Label(frame_inferior, text="Você receberá decisões priorizadas, não um relatório longo. Aqui, menos é mais.",
             font=("Arial", 9), bg="#1a0033", fg="#b366ff").pack(pady=(0, 10))

    tk.Label(frame_inferior, text="Resultado:", font=("Arial", 13, "bold"), bg="#1a0033", fg="white").pack()
    caixa_resultado = tk.Text(frame_inferior, width=85, height=8, font=("Arial", 12),
                              state="disabled", bg="#2d0052", fg="white", insertbackground="white")
    caixa_resultado.pack(padx=10, pady=5)

    _, _, dias_ini = status_trial()
    tk.Label(frame_inferior, text=f"Versão Demo  |  WhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com",
             font=("Arial", 11), bg="#1a0033", fg="#888888").pack(pady=(5, 0))
    label_contador = tk.Label(frame_inferior,
                              text=f"Teste gratuito: {dias_ini} de {DIAS_TRIAL} dias restantes",
                              font=("Arial", 11, "bold"), bg="#1a0033", fg="#b366ff")
    label_contador.pack(pady=(0, 8))

    janela.mainloop()


# ─── PONTO DE ENTRADA ────────────────────────────────────────────────────────────

mostrar_boas_vindas(iniciar_app)
