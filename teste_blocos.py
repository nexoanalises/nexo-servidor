# Testes das seções escritas por CÓDIGO (#083): _trocar_secao e _bloco_metas.
# Zero token: lógica pura.
import sys, types
class _Qq:
    def __init__(self, *a, **k): self.config = {}
    def __call__(self, *a, **k): return _Qq()
    def __getattr__(self, _): return _Qq()
    def __setitem__(self, k, v): pass
    def __getitem__(self, k): return _Qq()
for nome in ("flask", "gspread", "google", "google.oauth2", "google.oauth2.service_account",
             "dateutil", "dateutil.relativedelta", "requests", "groq"):
    m = types.ModuleType(nome); m.__getattr__ = lambda _n: _Qq(); sys.modules.setdefault(nome, m)
sys.modules["flask"].Flask = _Qq; sys.modules["flask"].request = _Qq(); sys.modules["flask"].jsonify = _Qq()
sys.modules["google.oauth2.service_account"].Credentials = _Qq
sys.modules["dateutil.relativedelta"].relativedelta = _Qq; sys.modules["groq"].Groq = _Qq
sys.path.insert(0, r"C:\Users\Ricardo\Desktop\Nexo arquivos antigos\nexo_servidor")
import servidor as S

ok = falhou = 0
def caso(t, obtido, esperado):
    global ok, falhou
    b = obtido == esperado
    print(f"{'  OK  ' if b else ' FALHA'} | {t}")
    if not b: print(f"         obtido={obtido!r}\n         esperado={esperado!r}")
    ok, falhou = ok + b, falhou + (not b)

# Dados reais de JUNHO/2026 — a rodada que rodou em producao as 12:15.
JUNHO = ("Segmento: Loja / Varejo e Moda\nnome_negocio: Loja da Bia\nperiodo: Junho/2026\n"
         "faturamento: 54.800\nmeta: 55.000\ncustos: 46.900\nlucro: 7.900\n"
         "estoque: Equilibrado. A colecao Outono chegou em marco e ainda esta saindo devagar.\n")

# A saida que producao devolveu as 12:15 — com as metas INVENTADAS.
SAIDA_REAL = """\U0001F4CC 1. RADAR DO NEGOCIO
\U0001F7E2 Margem liquida: 14,4% (margem saudavel)
A loja tem uma boa margem.

\U0001F9ED 2. DIAGNOSTICO CENTRAL
Voce vendeu mais e atingiu a meta.

\U0001F9ED 8. METAS ATE A PROXIMA ANALISE
De R$ 7.900 para R$ 10.000 em lucro.
De R$ 54.800 para R$ 62.500 em faturamento.
De 14,4% para 16% em margem liquida."""

print("\n=== _bloco_metas — o alvo arbitrado morre ===")
metas = S._bloco_metas(JUNHO)
txt = "\n".join(metas)
print(txt + "\n")
caso("nao inventa 62.500", "62.500" in txt, False)
caso("nao inventa 10.000", "10.000" in txt, False)
caso("usa a meta que o cliente deu (55.000)", "55.000" in txt, True)
caso("margem vira defesa ('manter em')", "manter em 14,4% ou mais" in txt, True)
# Com meta 55.000 contra faturamento 54.800, o alvo de lucro daria R$ 7.928 -- 0,4%
# acima do atual. Meta que nao move o numero nao e meta: vira defesa declarada.
caso("meta que nao move o numero vira defesa",
     "Lucro: manter em R$ 7.900 ou mais" in txt, True)
# Com meta AINDA NAO batida (55.000 > 54.800), a frase nao pode dizer que ele ja
# faturou o que precisava -- isso contradiria a linha de faturamento logo acima,
# que manda ir de 54.800 para 55.000. Saiu assim no teste real de 06/08.
caso("nao contradiz a meta de faturamento", "já faturou o que precisava" in txt, False)
caso("explica que a meta sozinha nao move o lucro", "quase não move o lucro" in txt, True)
# E quando a meta JA foi batida, a frase e a outra.
batida = "\n".join(S._bloco_metas(JUNHO.replace("meta: 55.000", "meta: 50.000")))
caso("meta batida: diz que o volume ja foi feito",
     "já faturou o que precisava" in batida, True)
# E quando a meta e de fato maior, a conta sai e diz que e sugerida.
maior = "\n".join(S._bloco_metas(JUNHO.replace("meta: 55.000", "meta: 60.000")))
caso("meta maior: conta sai rotulada",
     "meta sugerida pelo NEXO" in maior and "para R$ 8.649,64" in maior, True)
caso("fecha a redacao com a frase do fundador",
     txt.strip().endswith("cálculos realizados nesta análise."), True)
caso("sem estoque lido, nao ha meta de estoque", "Estoque parado" in txt, False)

print("\n=== _bloco_metas — cliente ja superou a propria meta ===")
sup = "\n".join(S._bloco_metas(JUNHO.replace("meta: 55.000", "meta: 50.000")))
caso("vira defesa em vez de alvo novo", "manter em R$ 54.800 ou mais" in sup, True)

print("\n=== _bloco_metas — sem meta informada ===")
sm = "\n".join(S._bloco_metas(JUNHO.replace("meta: 55.000\n", "")))
caso("declara a ausencia, nao inventa", "não informou meta" in sm, True)

print("\n=== _bloco_metas — com estoque lido ===")
ce = "\n".join(S._bloco_metas(JUNHO.replace(
    "saindo devagar.", "saindo devagar, tem R$ 13.000 a preco de custo parados.")))
caso("meta de estoque aparece rotulada",
     "R$ 13.000 para menos da metade" in ce and "sugerida pelo NEXO" in ce, True)

print("\n=== _substituir_secao com o bloco de metas ===")
sec = S._em_secoes(SAIDA_REAL)
caso("substituiu as metas", S._substituir_secao(sec, "METAS", metas), True)
final = S._texto_de_secoes(sec)
caso("alvo inventado sumiu do texto final", "62.500" in final, False)
caso("meta do cliente esta la", "R$ 55.000" in final, True)
caso("as outras secoes ficam intactas", "DIAGNOSTICO CENTRAL" in final, True)

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
