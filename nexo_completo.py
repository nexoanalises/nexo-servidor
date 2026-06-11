from groq import Groq
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.lib import colors
import json
import os
import csv
import io
import sys
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

try:
    import requests
except ImportError:
    requests = None

# ─── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────
_GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
client = Groq(api_key=_GROQ_KEY)

SHEETS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS8kLGIcqkHXBPOshW6_1742tsSsFXW-p37DPgs83kEGTPkTh-QD335wUZ2pgQWCnRj5grfghDADAJ8/pub?output=csv"
WHATSAPP = "(21) 92006-9321"

if getattr(sys, 'frozen', False):
    _DIR = os.path.dirname(sys.executable)
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))
LICENCA_ARQUIVO = os.path.join(_DIR, "nexo_licenca.json")

# ─── LICENÇA ────────────────────────────────────────────────────────────────────

def carregar_licenca():
    if os.path.exists(LICENCA_ARQUIVO):
        with open(LICENCA_ARQUIVO, "r") as f:
            return json.load(f)
    return None

def salvar_licenca(chave, plano, expiracao):
    with open(LICENCA_ARQUIVO, "w") as f:
        json.dump({
            "chave": chave,
            "plano": plano,
            "expiracao": expiracao,
            "ultima_validacao": datetime.now().isoformat()
        }, f)

def validar_chave_online(chave):
    if requests is None:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(SHEETS_CSV_URL, timeout=10, headers=headers)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        for row in reader:
            if row.get("chave", "").strip().upper() == chave.strip().upper():
                ativo = row.get("ativo", "").strip().lower()
                expiracao = row.get("expiracao", "").strip().lower()
                plano = row.get("plano", "").strip()
                if ativo != "sim":
                    return {"valido": False, "motivo": "Licença desativada."}
                if expiracao != "definitivo":
                    try:
                        data_exp = datetime.strptime(expiracao, "%Y-%m-%d")
                        if datetime.now() > data_exp:
                            return {"valido": False, "motivo": f"Licença expirada. Renove em:\nWhatsApp: {WHATSAPP}"}
                    except ValueError:
                        return {"valido": False, "motivo": "Erro na data da licença. Contate o suporte."}
                return {"valido": True, "plano": plano, "expiracao": expiracao}
        return {"valido": False, "motivo": "Chave não encontrada."}
    except Exception:
        return None

def verificar_licenca():
    licenca = carregar_licenca()
    if licenca is None:
        return False, None, "sem_licenca"
    ultima = datetime.fromisoformat(licenca["ultima_validacao"])
    if datetime.now() - ultima < timedelta(hours=24):
        return True, licenca, None
    resultado = validar_chave_online(licenca["chave"])
    if resultado is None:
        return True, licenca, None
    if resultado["valido"]:
        salvar_licenca(licenca["chave"], resultado["plano"], resultado["expiracao"])
        return True, licenca, None
    else:
        os.remove(LICENCA_ARQUIVO)
        return False, None, resultado["motivo"]

def ativar_chave(chave, janela_ativacao, callback_sucesso):
    chave = chave.strip().upper()
    if not chave:
        messagebox.showerror("Erro", "Digite uma chave de ativação.", parent=janela_ativacao)
        return
    resultado = validar_chave_online(chave)
    if resultado is None:
        messagebox.showerror("Sem conexão",
            "Não foi possível conectar ao servidor de licenças.\n"
            "Verifique sua internet e tente novamente.", parent=janela_ativacao)
        return
    if resultado["valido"]:
        salvar_licenca(chave, resultado["plano"], resultado["expiracao"])
        messagebox.showinfo("Ativado!", f"Nexo ativado com sucesso!\nPlano: {resultado['plano']}", parent=janela_ativacao)
        janela_ativacao.destroy()
        callback_sucesso()
    else:
        messagebox.showerror("Chave inválida", resultado["motivo"], parent=janela_ativacao)

def tela_ativacao(callback_sucesso):
    win = tk.Tk()
    win.title("Nexo — Ativação")
    win.geometry("480x300")
    win.configure(bg="#1a0033")
    win.resizable(False, False)
    tk.Label(win, text="NEXO", font=("Arial", 28, "bold"), bg="#1a0033", fg="#b366ff").pack(pady=(20, 0))
    tk.Label(win, text="Análise inteligente para o seu negócio", font=("Arial", 11),
             bg="#1a0033", fg="#dddddd").pack()
    tk.Frame(win, bg="#6A0DAD", height=2, width=400).pack(pady=12)
    tk.Label(win, text="Digite sua chave de ativação:", font=("Arial", 12, "bold"),
             bg="#1a0033", fg="white").pack()
    entrada = tk.Entry(win, font=("Arial", 13), bg="#2d0052", fg="white",
                       insertbackground="white", width=32, justify="center")
    entrada.pack(pady=10)
    entrada.focus()
    tk.Button(win, text="Ativar", font=("Arial", 13, "bold"), bg="#b366ff", fg="white",
              padx=20, pady=8,
              command=lambda: ativar_chave(entrada.get(), win, callback_sucesso)).pack(pady=6)
    tk.Label(win, text=f"Não tem uma chave? Adquira em:\nWhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com",
             font=("Arial", 10), bg="#1a0033", fg="#888888", justify="center").pack(pady=8)
    win.mainloop()

# ─── VERIFICAÇÃO DE LICENÇA ──────────────────────────────────────────────────────

liberado, licenca_atual, motivo = verificar_licenca()

if not liberado:
    if motivo == "sem_licenca":
        tela_ativacao(lambda: None)
        sys.exit()
    else:
        root_err = tk.Tk()
        root_err.withdraw()
        messagebox.showerror("Acesso negado", motivo)
        root_err.destroy()
        sys.exit()

# ─── APP PRINCIPAL ───────────────────────────────────────────────────────────────

def analisar(dados, segmento):
    resposta = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": (
                f"Você é o NEXO, um sistema de apoio à decisão para donos de pequenos e médios negócios do segmento {segmento} no Brasil.\n\n"
                f"OBJETIVO: ajudar o proprietário a tomar decisões práticas, realistas e executáveis dentro da realidade atual do negócio dele. "
                f"NÃO é diagnosticar, impressionar com análises ou agir como consultoria tradicional. "
                f"O dono deve identificar suas próximas prioridades em menos de 3 minutos de leitura.\n\n"
                f"PRINCÍPIOS OBRIGATÓRIOS:\n"
                f"- Decisão acima de análise: priorize ações, não explicações longas.\n"
                f"- Realidade acima da solução ideal: respeite o porte e o orçamento informado.\n"
                f"- Execução acima de teoria: toda recomendação precisa ser executável pelo próprio dono.\n"
                f"- O cliente deve agir sozinho: priorize ferramentas gratuitas, de baixo custo e métodos DIY.\n"
                f"- NUNCA recomende como ação principal: contratar consultoria estratégica, agência especializada, equipe dedicada "
                f"ou implementar sistemas complexos — exceto se o orçamento informado claramente comportar.\n"
                f"- NUNCA direcione o cliente para buscar ajuda estratégica externa como solução principal. O NEXO É o consultor dele.\n\n"
                f"LINGUAGEM: direta e imperativa. Use 'Faça', 'Implemente', 'Corrija', 'Monitore', 'Priorize'. "
                f"EVITE 'É importante considerar...', 'Recomenda-se avaliar...', 'Pode ser interessante...'. "
                f"Português do Brasil, sem jargão de IA ou de consultoria genérica.\n\n"
                f"ESTRUTURA OBRIGATÓRIA DO RELATÓRIO (use exatamente estes títulos numerados):\n\n"
                f"1) RESUMO EXECUTIVO\n"
                f"Resumo direto da situação atual. Máximo 5 linhas.\n\n"
                f"2) OPORTUNIDADE MAIS IMPORTANTE\n"
                f"Aponte o principal fator positivo identificado. Explique por que ele deve ser preservado ou ampliado.\n\n"
                f"3) ATENÇÃO IMEDIATA\n"
                f"Aponte o problema ou risco que merece atenção prioritária. Explique o impacto concreto de não agir.\n\n"
                f"4) O QUE FAZER AGORA\n"
                f"Liste de 3 a 5 ações priorizadas. Para CADA ação informe, em formato de tópicos curtos:\n"
                f"- Prioridade: (Alta / Média / Baixa)\n"
                f"- Impacto esperado: (descrição objetiva do ganho)\n"
                f"- Custo estimado: (ex.: 'Custo zero', 'até R$ 100', 'R$ 200-500')\n"
                f"- Tempo de implementação: (ex.: '1 dia', '1 semana', '15 dias')\n"
                f"- Tempo até perceber resultado: (ex.: '7 dias', '30 dias', '60-90 dias')\n\n"
                f"5) COMO EXECUTAR\n"
                f"Para CADA ação listada em 'O QUE FAZER AGORA', detalhe:\n"
                f"- O que fazer\n"
                f"- Como fazer (passo a passo simplificado e específico para o segmento)\n"
                f"- Ferramentas recomendadas (priorize gratuitas ou de baixo custo — ex.: WhatsApp Business, Google Meu Negócio, Canva grátis, Instagram orgânico, planilha Google)\n\n"
                f"6) JUSTIFICATIVA\n"
                f"Só agora apresente a análise que sustenta as decisões acima. Conecte cada recomendação a um dado concreto do negócio. Aumente a confiança do dono nas escolhas.\n\n"
                f"REGRAS DE PRIORIZAÇÃO — cada ação deve responder: Vale a pena? Quanto esforço exige? Quanto custa? Quanto impacto gera? Pode ser executada pelo próprio dono? "
                f"Se não responder claramente essas perguntas, NÃO inclua a ação.\n\n"
                f"RESTRIÇÃO DE ORÇAMENTO: respeite estritamente o campo 'Orçamento disponível para melhorias' nos dados. "
                f"Se o orçamento for baixo, nulo ou não informado, recomende apenas ações de custo zero ou muito baixo "
                f"(ajustes de processo, ações orgânicas, renegociação, organização interna, ferramentas gratuitas).\n\n"
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
    conteudo.append(Paragraph(f"Negócio: {escape(nome_negocio)} | Segmento: {escape(segmento)}", estilos["Heading2"]))
    conteudo.append(Spacer(1, 0.3*cm))
    for linha in resultado.split("\n"):
        if linha.strip() == "":
            conteudo.append(Spacer(1, 0.3*cm))
        else:
            conteudo.append(Paragraph(escape(linha.replace("**", "")), estilos["Normal"]))
    conteudo.append(Spacer(1, 1*cm))
    conteudo.append(Paragraph("NEXO — Análise inteligente para o seu negócio", estilo_rodape))
    conteudo.append(Paragraph(f"WhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com", estilo_rodape))
    doc.build(conteudo)
    return saida

janela = tk.Tk()
janela.title("Nexo — Versão Completa")
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
    criar_campo(frame_campos, "Orçamento disponível para melhorias", "orcamento_melhorias", tipo="text",
                dica="Quanto você tem disponível para investir em melhorias agora? Ex: 'R$ 500', 'até R$ 2.000', 'não tenho no momento'. Essa informação é essencial para sugerirmos ações compatíveis com sua realidade.")
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
    botao_analisar.config(state="normal", text="Analisar Negócio")

    if pdf:
        messagebox.showinfo("Concluído", f"Análise concluída!\nPDF salvo em:\n{pdf}")
    else:
        messagebox.showinfo("Concluído", "Análise concluída!")

botao_analisar = tk.Button(janela, text="Analisar Negócio",
                           font=("Arial", 15, "bold"), bg="#b366ff", fg="white",
                           padx=20, pady=10, command=executar_analise)
botao_analisar.pack(pady=10)

tk.Label(janela, text="Resultado:", font=("Arial", 13, "bold"), bg="#1a0033", fg="white").pack()
caixa_resultado = tk.Text(janela, width=85, height=10, font=("Arial", 12),
                          state="disabled", bg="#2d0052", fg="white", insertbackground="white")
caixa_resultado.pack(padx=10, pady=5)

plano_nome = licenca_atual.get("plano", "Completo").capitalize() if licenca_atual else "Completo"
exp = licenca_atual.get("expiracao", "") if licenca_atual else ""
validade_txt = "Vitalícia" if exp == "definitivo" else (f"Válida até {exp}" if exp else "")
rodape_txt = f"Versão Completa  |  Plano: {plano_nome}"
if validade_txt:
    rodape_txt += f"  |  {validade_txt}"
rodape_txt += f"  |  WhatsApp: {WHATSAPP}  |  nexo.analises@gmail.com"

tk.Label(janela, text=rodape_txt, font=("Arial", 10), bg="#1a0033", fg="#888888").pack(pady=8)

janela.mainloop()
