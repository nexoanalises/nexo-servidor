# O VALIDADOR PRECISA ENXERGAR AS AÇÕES — em QUALQUER forma de enumeração.
#
# Existe por causa do defeito 1 da rodada dos cinco ambientes (10/08): a seção
# "7. AÇÕES IMEDIATAS" chegava VAZIA ao validador, porque o parser dele aceitava
# qualquer linha `^\d+\.\s` como título — e a primeira ação, "1. Revisar a formação de
# preço…", fechava a seção que acabara de abrir.
#
# Duas checagens morriam junto: a 4 (ação sem prazo · ação ACIMA DA VERBA que o cliente
# informou) e a 5 (decisão principal sem ação correspondente). Efeito medido em
# produção: verba de "Até R$ 500" e o produto recomendando "(Custo: R$ 1.000)".
#
# 🔒 A EXIGÊNCIA DO FUNDADOR, e é ela que este arquivo guarda: *"o validador precisa
# encontrar as ações independentemente da forma de enumeração usada pelo Motor. Não
# quero outro remendo específico para '1.'"*. Por isso o teste varre oito formatos, e
# não o que quebrou.
import sys, types
# O console do Windows abre em cp1252 e derruba o teste no primeiro "→".
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
class _Qq:
    def __init__(self,*a,**k): self.config={}
    def __call__(self,*a,**k): return _Qq()
    def __getattr__(self,_): return _Qq()
    def __setitem__(self,k,v): pass
    def __getitem__(self,k): return _Qq()
for n in ("flask","gspread","google","google.oauth2","google.oauth2.service_account",
          "dateutil","dateutil.relativedelta","requests","groq"):
    m=types.ModuleType(n); m.__getattr__=lambda _x:_Qq(); sys.modules.setdefault(n,m)
sys.modules["flask"].Flask=_Qq; sys.modules["flask"].request=_Qq(); sys.modules["flask"].jsonify=_Qq()
sys.modules["google.oauth2.service_account"].Credentials=_Qq
sys.modules["dateutil.relativedelta"].relativedelta=_Qq; sys.modules["groq"].Groq=_Qq
sys.path.insert(0,r"C:\Users\Ricardo\Desktop\Nexo arquivos antigos\nexo_servidor")
import servidor as S

ok = falhou = 0
def caso(t, obtido, esperado):
    global ok, falhou
    b = obtido == esperado
    print(f"{'  OK  ' if b else ' FALHA'} | {t}")
    if not b: print(f"         obtido={obtido!r}\n         esperado={esperado!r}")
    ok, falhou = ok+b, falhou+(not b)

TAG = "(Custo: zero | Resultado em: ~7 dias)"
def analise(corpo_acoes, decisao="Reprecificar o vestido midi para proteger a margem."):
    """Uma análise inteira, com a seção seguinte logo depois das ações — o caso que
    fechava a extração cedo demais."""
    return ("1. RADAR DO NEGÓCIO\n🟢 Faturamento: R$ 60.000 → R$ 68.000 (+13,3%)\n\n"
            f"6. DECISÃO MAIS IMPORTANTE AGORA\n{decisao}\n\n"
            f"7. AÇÕES IMEDIATAS\n{corpo_acoes}\n\n"
            "8. METAS ATÉ A PRÓXIMA ANÁLISE\n"
            "• Faturamento: de R$ 68.000 para R$ 70.000 — a meta que você definiu.\n")

print("=== 1. A SEÇÃO É ENCONTRADA EM QUALQUER FORMA DE ENUMERAÇÃO ===")
FORMATOS = {
    "numerada '1.'":      f"1. Reprecificar o vestido midi {TAG}.\n2. Girar o blazer {TAG}.",
    "numerada '1)'":      f"1) Reprecificar o vestido midi {TAG}.\n2) Girar o blazer {TAG}.",
    "bullet '•'":         f"• Reprecificar o vestido midi {TAG}.\n• Girar o blazer {TAG}.",
    "traço '-'":          f"- Reprecificar o vestido midi {TAG}.\n- Girar o blazer {TAG}.",
    "asterisco '*'":      f"* Reprecificar o vestido midi {TAG}.\n* Girar o blazer {TAG}.",
    "letra 'a)'":         f"a) Reprecificar o vestido midi {TAG}.\nb) Girar o blazer {TAG}.",
    "romano 'I.'":        f"I. Reprecificar o vestido midi {TAG}.\nII. Girar o blazer {TAG}.",
    "sem marcador":       f"Reprecificar o vestido midi {TAG}.\nGirar o blazer {TAG}.",
}
for nome, corpo in FORMATOS.items():
    linhas = S._secao_da_saida(analise(corpo), "AÇÕES IMEDIATAS")
    caso(f"{nome:18} → 2 ações extraídas", len(linhas), 2)

print("\n=== 2. a seção seguinte encerra a extração — e não entra nela ===")
linhas = S._secao_da_saida(analise(FORMATOS["numerada '1.'"]), "AÇÕES IMEDIATAS")
caso("nenhuma linha de METAS vazou para as ações",
     any("meta que você definiu" in l for l in linhas), False)
caso("nenhuma linha do RADAR vazou", any("Faturamento" in l for l in linhas), False)

print("\n=== 3. ação em MÚLTIPLAS LINHAS não é perdida ===")
multi = (f"1. Reprecificar o vestido midi, campeão de vendas,\n"
         f"   para proteger a margem sem perder competitividade {TAG}.\n"
         f"2. Girar o blazer de alfaiataria {TAG}.")
linhas = S._secao_da_saida(analise(multi), "AÇÕES IMEDIATAS")
caso("as três linhas do corpo são extraídas", len(linhas), 3)
caso("a continuação da 1ª ação está lá",
     any("para proteger a margem" in l for l in linhas), True)

print("\n=== 4. AÇÃO ACIMA DA VERBA BLOQUEIA — o caso que passou em produção ===")
d500 = "=== DADOS ATUAIS ===\nverba_melhorias: Até R$ 500\n"
def regras(saida, dados=d500):
    return [v["regra"] for v in S.validar_saida(saida, dados, [], [])]

for nome, corpo in FORMATOS.items():
    cara = corpo.replace("(Custo: zero", "(Custo: R$ 1.000")
    caso(f"{nome:18} → barra ação de R$ 1.000 com verba de R$ 500",
         "ação acima da verba informada" in regras(analise(cara)), True)

print("\n=== 5. AÇÃO SEM PRAZO BLOQUEIA ===")
for nome, corpo in FORMATOS.items():
    sem = corpo.replace(f" {TAG}", "")
    caso(f"{nome:18} → acusa ação sem prazo",
         "ação sem prazo" in regras(analise(sem)), True)

print("\n=== 6. DECISÃO SEM AÇÃO CORRESPONDENTE BLOQUEIA ===")
descolada = analise(f"1. Contratar um estagiário para o estoque {TAG}.\n"
                    f"2. Reorganizar a vitrine da loja {TAG}.",
                    decisao="Renegociar o contrato de aluguel do galpão logístico.")
caso("acusa decisão que nenhuma ação executa",
     "decisão sem ação correspondente" in regras(descolada), True)
casada = analise(f"1. Reprecificar o vestido midi conforme a margem {TAG}.",
                 decisao="Reprecificar o vestido midi para proteger a margem.")
caso("e NÃO acusa quando a ação executa a decisão",
     "decisão sem ação correspondente" in regras(casada), False)

print("\n=== 7. ação DENTRO da verba não é barrada (sem falso positivo) ===")
dentro = FORMATOS["numerada '1.'"].replace("(Custo: zero", "(Custo: R$ 300")
caso("R$ 300 com verba de R$ 500 passa",
     "ação acima da verba informada" in regras(analise(dentro)), False)

print("\n=== 8. a checagem das METAS não regrediu com o parser novo ===")
# A checagem 1 compara a linha da meta com a linha bruta da saída: se o marcador
# se perdesse na extração, as metas voltariam a ser varridas como número sem fonte.
metas = S._secao_da_saida(analise(FORMATOS["numerada '1.'"]), "METAS")
caso("a meta sai COM o marcador original", metas[0].startswith("•"), True)
# A pergunta certa é se a LINHA DA META foi acusada — não se existe alguma acusação na
# análise inteira. Com `radar=[]`, as cifras do Radar ficam legitimamente sem fonte, e
# medir o total confundiria o alvo da checagem com o ruído do cenário de teste.
viols = S.validar_saida(analise(FORMATOS["numerada '1.'"]), d500 + "faturamento: 68000\n", [], [])
caso("a linha da meta NÃO é acusada de número sem fonte",
     [v for v in viols if v["regra"] == "número sem fonte"
      and "meta que você definiu" in v["trecho"]], [])

print("\n=== 9. título ausente ou seção vazia não quebra ===")
caso("seção que não existe devolve lista vazia",
     S._secao_da_saida(analise(FORMATOS["bullet '•'"]), "SEÇÃO QUE NÃO EXISTE"), [])
caso("saída vazia devolve lista vazia", S._secao_da_saida("", "AÇÕES IMEDIATAS"), [])
caso("saída None devolve lista vazia", S._secao_da_saida(None, "AÇÕES IMEDIATAS"), [])

print("\n=== 10. o defeito original, reproduzido literalmente ===")
# O texto exato que saiu da Perfumaria em produção, 10/08.
producao = ("7. AÇÕES IMEDIATAS\n"
            "1. Revisar a formação de preço dos itens de maior saída nos próximos 30 dias "
            "(Custo: zero | Resultado em: ~7 dias).\n"
            "2. Criar um combo de skincare parado (Custo: zero | Resultado em: ~14 dias).\n"
            "3. Verificar a possibilidade de compra de perfume importado "
            "(Custo: R$ 1.000 | Resultado em: ~30 dias).\n")
linhas = S._secao_da_saida(producao, "AÇÕES IMEDIATAS")
caso("as 3 ações da rodada real são extraídas", len(linhas), 3)
caso("e a de R$ 1.000 contra verba de R$ 500 é barrada",
     "ação acima da verba informada" in regras(producao), True)

print(f"\n{'='*58}\n  {ok} passaram · {falhou} falharam\n{'='*58}")
sys.exit(1 if falhou else 0)
