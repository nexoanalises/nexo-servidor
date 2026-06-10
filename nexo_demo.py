from groq import Groq
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.lib import colors
import os
import sys

# ─── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
_GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
client = Groq(api_key=_GROQ_KEY)

WHATSAPP   = "(21) 92006-9321"
LIMITE_DEMO = 2

if getattr(sys, 'frozen', False):
    _DIR = os.path.dirname(sys.executable)
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))
USO_ARQUIVO = os.path.join(_DIR, "nexo_uso.txt")

def ler_usos():
    if os.path.exists(USO_ARQUIVO):
        try:
            with open(USO_ARQUIVO, "r") as f:
                return int(f.read().strip())
        except Exception:
            return 0
    return 0

def salvar_usos(n):
    with open(USO_ARQUIVO, "w") as f:
        f.write(str(n))

# ─── APP PRINCIPAL ───────────────────────────────────────────────────────────────

def analisar(dados, segmento):
    resposta = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": (
                f"Você é um consultor sênior especialista em {segmento} com 20 anos de experiência no mercado brasileiro.\n\n"
                f"Com base nos dados abaixo, entregue um parecer executivo completo:\n\n"
                f"1) DIAGNÓSTICO EXECUTIVO — resumo em 3 linhas no tom de um CEO\n"
                f"2) PONTO CRÍTICO POSITIVO — principal resultado positivo e seu impacto\n"
                f"3) RISCO PRINCIPAL — maior risco e consequência se não tratado\n"
                f"4) PLANO DE AÇÃO — 3 ações priorizadas por urgência e impacto, com prazo sugerido. "
                f"Para cada ação, além de dizer O QUE fazer, explique COMO fazer na prática: "
                f"passos concretos, táticas específicas e exemplos aplicáveis ao segmento "
                f"(ex: se a ação envolve marketing digital, sugira canais, tipo de campanha e se vale contratar um especialista; "
                f"se envolve estoque, sugira métodos de controle e renegociação com fornecedores; "
                f"se envolve equipe, sugira ações concretas de retenção e treinamento)\n"
                f"5) INDICADOR DE SAÚDE DO NEGÓCIO — nota de 0 a 10 com justificativa\n\n"
                f"Use linguagem executiva, direta e profissional. Responda em português do Brasil.\n\n"
                f"DADOS DO NEGÓCIO:\n{dados}"
            )
        }]
    )
    return resposta.choices[0].message.content

def salvar_pdf(resultado, segmento, nome_negocio):
    saida = filedialog.asksaveasfilename(
        defaultextension=".pdf",
        filetypes=[("PDF", "*.pdf")],
        initialfile=f"analise_{nome_negocio}.pdf",
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
    conteudo = []
    conteudo.append(Paragraph("NEXO", estilo_titulo))
    conteudo.append(Paragraph("Análise inteligente para o seu negócio", estilo_slogan))
    conteudo.append(Spacer(1, 0.3*cm))
    conteudo.append(Paragraph(f"Negócio: {nome_negocio} | Segmento: {segmento}", estilos["Heading2"]))
    conteudo.append(Spacer(1, 0.3*cm))
    for linha in resultado.split("\n"):
        if linha.strip() == "":
            conteudo.append(Spacer(1, 0.3*cm))
        else:
            conteudo.append(Paragraph(linha.replace("**", ""), estilos["Normal"]))
    conteudo.append(Spacer(1, 1*cm))
    conteudo.append(Paragraph("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", estilo_rodape))
    conteudo.append(Paragraph("NEXO — Análise inteligente para o seu negócio", estilo_rodape))
    conteudo.append(Paragraph(f"WhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com", estilo_rodape))
    doc.build(conteudo)
    return saida

janela = tk.Tk()
janela.title("Nexo — Versão Demo")
janela.geometry("800x900")
janela.resizable(True, True)
janela.configure(bg="#1a0033")

tk.Label(janela, text="NEXO", font=("Arial", 30, "bold"), bg="#1a0033", fg="#b366ff").pack(pady=10)
tk.Label(janela, text="Análise inteligente para o seu negócio", font=("Arial", 13), bg="#1a0033", fg="#dddddd").pack()
tk.Frame(janela, bg="#6A0DAD", height=2, width=700).pack(pady=10)

tk.Label(janela, text="Selecione o tipo de negócio:", font=("Arial", 13, "bold"), bg="#1a0033", fg="white").pack()
segmentos = ["Loja / Varejo e Moda", "Restaurante / Alimentação", "Clínica / Saúde",
             "Recursos Humanos", "Imobiliária", "Escola / Educação",
             "Academia / Fitness", "Farmácia"]
var_segmento = tk.StringVar(value=segmentos[0])
combo_segmento = ttk.Combobox(janela, textvariable=var_segmento, values=segmentos,
                               font=("Arial", 13), state="readonly", width=40)
combo_segmento.pack(pady=8)

frame_container = tk.Frame(janela, bg="#1a0033")
frame_container.pack(fill="both", expand=True, padx=20)

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
    global frame_campos
    for widget in frame_campos.winfo_children():
        widget.destroy()
    campos_widgets.clear()
    canvas.delete("all")
    frame_campos = tk.Frame(canvas, bg="#1a0033")
    frame_campos.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=frame_campos, anchor="nw")

    tk.Label(frame_campos, text="── INFORMAÇÕES GERAIS ──", font=("Arial", 12, "bold"),
             bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)

    criar_campo(frame_campos, "Nome do negócio *", "nome_negocio",
                dica="Ex: Padaria do João, Clínica Bem Estar, Escola Saber")
    criar_campo(frame_campos, "Período analisado *", "periodo",
                dica="Ex: Maio/2026, Janeiro a Março/2026. Todos os valores abaixo devem se referir a este período.")
    criar_campo(frame_campos, "Faturamento do período (R$) *", "faturamento",
                dica="Total de receitas brutas recebidas no período. Ex: R$ 45.000")
    criar_campo(frame_campos, "Meta de faturamento (R$)", "meta",
                dica="Quanto você esperava faturar no período. Ex: R$ 50.000")
    criar_campo(frame_campos, "Investimento/Custos do período (R$)", "custos",
                dica="Some todos os custos do período: salários, aluguel, energia, marketing, materiais, etc.")
    criar_campo(frame_campos, "Lucro líquido (R$)", "lucro",
                dica="Faturamento menos todos os custos. Se teve prejuízo, informe com sinal negativo: -R$ 2.000")
    criar_campo(frame_campos, "Número de funcionários", "funcionarios",
                dica="Total de colaboradores ativos no período, incluindo sócios que trabalham no negócio.")
    criar_campo(frame_campos, "Capacidade operacional ocupada (%)", "capacidade",
                dica="Em quanto % o negócio está operando? Ex: 70%")
    criar_checkboxes(frame_campos, "Principais canais de aquisição de clientes", "canais", canais_opcoes,
                     dica="Selecione por onde a maioria dos seus clientes chega até você.")
    criar_campo(frame_campos, "Vendas por canal (quantidade ou %)", "vendas_canal",
                dica="Ex: Loja Física 50% | WhatsApp 35% | Site 15%")
    criar_campo(frame_campos, "Principais desafios do período", "desafios", tipo="text",
                dica="Descreva os maiores problemas ou dificuldades enfrentados.")
    criar_campo(frame_campos, "Observações adicionais", "observacoes", tipo="text",
                dica="Qualquer informação relevante que não se encaixou nos campos acima.")

    seg = var_segmento.get()

    if seg == "Loja / Varejo e Moda":
        tk.Label(frame_campos, text="── LOJA / VAREJO E MODA ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Produtos mais vendidos", "produtos_top",
                    dica="Liste os 3 produtos com maior saída.")
        criar_campo(frame_campos, "Produtos com baixo giro", "produtos_baixo",
                    dica="Produtos parados no estoque.")
        criar_campo(frame_campos, "Coleção atual", "colecao",
                    dica="Ex: Inverno 2026, Verão 2026.")
        criar_campo(frame_campos, "Peças/modelos com maior saída", "pecas_top")
        criar_campo(frame_campos, "Peças/modelos encalhados", "pecas_encalhadas")
        criar_campo(frame_campos, "Tamanhos com maior saída", "tamanhos_top")
        criar_campo(frame_campos, "Tamanhos encalhados", "tamanhos_encalhados")
        criar_campo(frame_campos, "Percentual de vendas: Roupas vs Calçados (%)", "proporcao_loja")
        criar_campo(frame_campos, "Ticket médio (R$)", "ticket_medio")
        criar_campo(frame_campos, "Número de clientes atendidos", "clientes")
        criar_campo(frame_campos, "Taxa de conversão (%)", "conversao")
        criar_campo(frame_campos, "Reclamações recebidas", "reclamacoes")
        criar_campo(frame_campos, "Trocas por defeito", "trocas")
        criar_campo(frame_campos, "Fornecedores que cumprem prazo (%)", "fornecedores")
        criar_campo(frame_campos, "Vendas realizadas via WhatsApp", "vendas_zap")
        criar_campo(frame_campos, "Situação do estoque atual", "estoque", tipo="text")

    elif seg == "Restaurante / Alimentação":
        tk.Label(frame_campos, text="── RESTAURANTE / ALIMENTAÇÃO ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Dias e horário de funcionamento", "horario")
        criar_campo(frame_campos, "Média de clientes por dia", "clientes_dia")
        criar_campo(frame_campos, "Prato mais pedido", "prato_top")
        criar_campo(frame_campos, "CMV - Custo de Mercadoria Vendida (%)", "cmv",
                    dica="Ideal: entre 25% e 35%.")
        criar_campo(frame_campos, "Desperdício de alimentos", "desperdicio")
        criar_campo(frame_campos, "Capacidade de assentos vs ocupação (%)", "ocupacao")
        criar_campo(frame_campos, "Canal majoritário", "canal",
                    dica="Salão, Delivery ou Ambos?")
        criar_campo(frame_campos, "Avaliações dos clientes (nota média)", "avaliacoes")

    elif seg == "Clínica / Saúde":
        tk.Label(frame_campos, text="── CLÍNICA / SAÚDE ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Número de consultas realizadas", "consultas")
        criar_campo(frame_campos, "Taxa de retorno de pacientes (%)", "retorno")
        criar_campo(frame_campos, "Taxa de No-Show (%)", "noshow")
        criar_campo(frame_campos, "Procedimentos mais realizados", "procedimentos")
        criar_campo(frame_campos, "Agendamentos cancelados", "cancelamentos")
        criar_campo(frame_campos, "Tempo médio de espera (minutos)", "espera")
        criar_campo(frame_campos, "Consultas por intercorrências anteriores", "intercorrencias")

    elif seg == "Recursos Humanos":
        tk.Label(frame_campos, text="── RECURSOS HUMANOS ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Contratações no período", "contratacoes")
        criar_campo(frame_campos, "Demissões no período", "demissoes")
        criar_campo(frame_campos, "Tempo médio de casa dos funcionários", "tempo_casa")
        criar_campo(frame_campos, "Absenteísmo — Nome | Dias ausente | Motivo", "absenteismo", tipo="text")
        criar_campo(frame_campos, "Nível de satisfação da equipe (1 a 5)", "satisfacao")
        criar_campo(frame_campos, "Treinamentos realizados", "treinamentos")

    elif seg == "Imobiliária":
        tk.Label(frame_campos, text="── IMOBILIÁRIA ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Imóveis disponíveis", "imoveis_disponiveis")
        criar_campo(frame_campos, "Imóveis vendidos/alugados no período", "imoveis_vendidos")
        criar_campo(frame_campos, "Imóveis sob gestão", "imoveis_gestao")
        criar_campo(frame_campos, "Imóveis em obra + prazo de entrega", "imoveis_obra", tipo="text")
        criar_campo(frame_campos, "Tempo médio do imóvel no catálogo (dias)", "tempo_catalogo")
        criar_campo(frame_campos, "Ticket médio das vendas (R$)", "ticket_imovel")
        criar_checkboxes(frame_campos, "Canal dos leads", "canais_leads",
                        ["Instagram", "Facebook", "WhatsApp", "Portal ZAP",
                         "Portal OLX", "Viva Real", "Indicação", "Tráfego Pago", "Site próprio"])

    elif seg == "Escola / Educação":
        tk.Label(frame_campos, text="── ESCOLA / EDUCAÇÃO ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Total de alunos", "total_alunos")
        criar_campo(frame_campos, "Total de professores", "total_professores")
        criar_campo(frame_campos, "Matrículas novas no período", "matriculas")
        criar_campo(frame_campos, "Cancelamentos + motivo principal", "cancelamentos", tipo="text")
        criar_campo(frame_campos, "Inadimplência (R$ ou %)", "inadimplencia")
        criar_campo(frame_campos, "Ticket médio por aluno (R$)", "ticket_aluno")

    elif seg == "Academia / Fitness":
        tk.Label(frame_campos, text="── ACADEMIA / FITNESS ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Total de alunos", "total_alunos")
        criar_campo(frame_campos, "Novos alunos no período", "novos_alunos")
        criar_campo(frame_campos, "Cancelamentos no período", "cancelamentos")
        criar_campo(frame_campos, "Taxa de renovação de planos (%)", "renovacao")
        criar_campo(frame_campos, "Plano mais vendido", "plano_top")
        criar_campo(frame_campos, "Horários de pico", "horario_pico")
        criar_campo(frame_campos, "Manutenções realizadas no período", "manutencoes")
        criar_campo(frame_campos, "Novos aparelhos adquiridos", "aparelhos_novos")
        criar_campo(frame_campos, "Aparelhos desativados/descartados", "aparelhos_fora")
        criar_campo(frame_campos, "Reclamações recebidas + motivo", "reclamacoes", tipo="text")

    elif seg == "Farmácia":
        tk.Label(frame_campos, text="── FARMÁCIA ──", font=("Arial", 12, "bold"),
                 bg="#1a0033", fg="#b366ff").pack(fill="x", pady=5)
        criar_campo(frame_campos, "Medicamentos mais vendidos", "med_top")
        criar_campo(frame_campos, "Proporção Medicamentos vs Perfumaria (%)", "proporcao")
        criar_campo(frame_campos, "Ticket médio (R$)", "ticket_medio")
        criar_campo(frame_campos, "Clientes fidelizados", "fidelizados")
        criar_campo(frame_campos, "Itens em estoque crítico", "estoque_critico", tipo="text")

    frame_campos.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))
    canvas.yview_moveto(0)

def ao_trocar_segmento(event):
    carregar_campos()
    janela.update_idletasks()

combo_segmento.bind("<<ComboboxSelected>>", ao_trocar_segmento)
carregar_campos()

def executar_analise():
    usos = ler_usos()
    if usos >= LIMITE_DEMO:
        messagebox.showwarning("Demo encerrada",
            f"Você já usou suas {LIMITE_DEMO} análises gratuitas!\n\n"
            "Adquira uma licença para continuar:\n"
            f"WhatsApp: {WHATSAPP}\nnexo.analises@gmail.com")
        return

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

    resultado = analisar(dados, seg)

    caixa_resultado.config(state="normal")
    caixa_resultado.delete("1.0", tk.END)
    caixa_resultado.insert(tk.END, resultado)
    caixa_resultado.config(state="disabled")

    pdf = salvar_pdf(resultado, seg, nome)

    novo_uso = usos + 1
    salvar_usos(novo_uso)
    restantes = LIMITE_DEMO - novo_uso
    label_contador.config(text=f"Análises gratuitas restantes: {restantes}/{LIMITE_DEMO}")

    botao_analisar.config(state="normal", text="Analisar Negócio")

    msg_pdf = f"\nPDF salvo em:\n{pdf}\n\n" if pdf else "\n\n"
    if restantes > 0:
        messagebox.showinfo("Análise concluída",
            f"Análise concluída!{msg_pdf}"
            f"Você ainda tem {restantes} análise(s) gratuita(s).\n"
            "Para análises ilimitadas, adquira uma licença:\n"
            f"WhatsApp: {WHATSAPP}")
    else:
        messagebox.showinfo("Análise concluída",
            f"Análise concluída!{msg_pdf}"
            "⚠️ Esta foi sua última análise gratuita.\n"
            "Adquira uma licença para continuar:\n"
            f"WhatsApp: {WHATSAPP}\nnexo.analises@gmail.com")

botao_analisar = tk.Button(janela, text="Analisar Negócio",
                           font=("Arial", 15, "bold"), bg="#b366ff", fg="white",
                           padx=20, pady=10, command=executar_analise)
botao_analisar.pack(pady=10)

tk.Label(janela, text="Resultado:", font=("Arial", 13, "bold"), bg="#1a0033", fg="white").pack()
caixa_resultado = tk.Text(janela, width=85, height=10, font=("Arial", 12),
                          state="disabled", bg="#2d0052", fg="white", insertbackground="white")
caixa_resultado.pack(padx=10, pady=5)

usos_atuais = ler_usos()
restantes_inicial = LIMITE_DEMO - usos_atuais

tk.Label(janela, text=f"Versão Demo  |  WhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com",
         font=("Arial", 11), bg="#1a0033", fg="#888888").pack(pady=(5, 0))
label_contador = tk.Label(janela,
                          text=f"Análises gratuitas restantes: {restantes_inicial}/{LIMITE_DEMO}",
                          font=("Arial", 11, "bold"), bg="#1a0033", fg="#b366ff")
label_contador.pack(pady=(0, 8))

janela.mainloop()
