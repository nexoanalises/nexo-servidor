# Teste de lógica do extrator de estoque (#083) e da checagem 7 do validador.
# Não chama a Groq: zero token do teto diário.
import sys, os, types
# As dependências de produção (flask, gspread, groq…) não estão nesta máquina e não
# são necessárias: o que se testa é lógica pura de texto. Stub mínimo para importar.
class _Qq:
    def __init__(self, *a, **k): self.config = {}
    def __call__(self, *a, **k): return _Qq()
    def __getattr__(self, _): return _Qq()
    def __setitem__(self, k, v): pass
    def __getitem__(self, k): return _Qq()
for nome in ("flask", "gspread", "google", "google.oauth2",
             "google.oauth2.service_account", "dateutil",
             "dateutil.relativedelta", "requests", "groq"):
    mod = types.ModuleType(nome)
    mod.__getattr__ = lambda _n: _Qq()
    sys.modules.setdefault(nome, mod)
sys.modules["flask"].Flask = _Qq
sys.modules["flask"].request = _Qq()
sys.modules["flask"].jsonify = _Qq()
sys.modules["google.oauth2.service_account"].Credentials = _Qq
sys.modules["dateutil.relativedelta"].relativedelta = _Qq
sys.modules["groq"].Groq = _Qq

sys.path.insert(0, r"C:\Users\Ricardo\Desktop\Nexo arquivos antigos\nexo_servidor")
import servidor as S

ok = falhou = 0
def caso(titulo, obtido, esperado):
    global ok, falhou
    bateu = obtido == esperado
    print(f"{'  OK  ' if bateu else ' FALHA'} | {titulo}\n         obtido={obtido!r}")
    if not bateu:
        print(f"         esperado={esperado!r}")
    ok, falhou = ok + bateu, falhou + (not bateu)

# ── Dados REAIS do TESTE_analise_real_01-08.md ────────────────────────────────
JULHO = ("Cheio. A coleção Outono comprada em março ainda tem cerca de R$ 18.000 a preço "
         "de custo parada. A coleção Primavera acabou de chegar e não tem onde guardar. "
         "Não faltou nada dos produtos que mais vendem.")
JUNHO = ("Equilibrado. A coleção Outono chegou em março e ainda está saindo devagar, mas "
         "não faltou nada dos produtos que mais vendem.")

def payload(texto_estoque, extra=""):
    return ("Segmento: Loja / Varejo e Moda\n"
            "nome_negocio: Loja da Bia\n"
            "faturamento: R$ 56.350\n"
            "custos: R$ 46.900\n"
            "lucro: R$ 9.450\n"
            f"estoque: {texto_estoque}\n"
            f"encalhados: Blazer de alfaiataria, saia longa jeans\n{extra}")

print("\n=== _valor_do_estoque — CERTEZA USA / DÚVIDA CALA ===")
caso("julho real: uma cifra em R$ -> usa",
     S._valor_do_estoque(payload(JULHO))[0], 18000.0)
caso("junho real: descreve sem cifra -> cala",
     S._valor_do_estoque(payload(JUNHO))[0], None)
caso("duas cifras: qual e a parada? -> cala",
     S._valor_do_estoque(payload("R$ 18.000 da Outono e R$ 5.000 da Verao paradas"))[0], None)
caso("percentual sem moeda -> cala",
     S._valor_do_estoque(payload("cerca de 30% do estoque esta parado"))[0], None)
caso("percentual COM cifrao (R$ 30%) -> cala",
     S._valor_do_estoque(payload("tem R$ 30% parado, acho"))[0], None)
caso("campo ausente -> cala",
     S._valor_do_estoque("Segmento: X\nfaturamento: R$ 10\n")[0], None)
caso("campo vazio -> cala",
     S._valor_do_estoque(payload(""))[0], None)
caso("centavos: R$ 18.000,50 -> usa",
     S._valor_do_estoque(payload("tem R$ 18.000,50 a preco de custo parado"))[0], 18000.50)

print("\n=== _texto_do_campo — multilinha e fronteira de campo ===")
multi = ("estoque: Cheio.\nA colecao Outono tem R$ 18.000 parados.\n"
         "encalhados: Blazer\n")
caso("junta continuacao do widget Text",
     S._valor_do_estoque("Segmento: X\n" + multi)[0], 18000.0)
caso("NAO atravessa para o campo seguinte",
     S._texto_do_campo("Segmento: X\nestoque: Cheio.\nencalhados: R$ 99.999\n",
                       "estoque"), "Cheio.")

print("\n=== validar_saida — checagem 7 ===")
def viols(saida, dados):
    return [x["regra"] for x in S.validar_saida(saida, dados, [], [])]

# a) cala e o modelo inventa cifra -> tem de acusar
d_sem = payload(JUNHO)
s_inventa = "4. O QUE ESTA CUSTANDO DINHEIRO\nColecao de outono: cerca de R$ 13.000 parados na arara."
caso("degrau 3 violado: cifra de estoque sem fundamento",
     "cifra de estoque sem fundamento" in viols(s_inventa, d_sem), True)

# b) cala e o modelo escreve a frase honesta -> tem de passar limpo
s_honesto = "4. O QUE ESTA CUSTANDO DINHEIRO\n" + S.FRASE_ESTOQUE_SEM_VALOR
caso("degrau 3 respeitado: nenhuma violacao de estoque",
     any("estoque" in r for r in viols(s_honesto, d_sem)), False)

# c) valor lido e o modelo repete o certo -> passa
d_com = payload(JULHO)
s_certo = "4. O QUE ESTA CUSTANDO DINHEIRO\nColecao de outono: R$ 18.000 a preco de custo, parados."
caso("cifra correta do estoque nao e acusada",
     any("estoque" in r for r in viols(s_certo, d_com)), False)

# d) valor lido e o modelo usa OUTRO numero que esta nos dados -> tem de acusar
#    (e o furo que a checagem 1 nao pega: 46.900 existe no payload)
s_errado = "4. O QUE ESTA CUSTANDO DINHEIRO\nColecao de outono: R$ 46.900 parados no estoque."
caso("numero certo no lugar errado e acusado",
     "cifra de estoque diferente da informada" in viols(s_errado, d_com), True)

# e) lucro citado na mesma linha do estoque NAO pode virar falso positivo
s_lucro = ("4. O QUE ESTA CUSTANDO DINHEIRO\nColecao de outono: R$ 18.000 parados. "
           "E mais do que o lucro do mes inteiro (R$ 9.450).")
caso("lucro na mesma frase nao vira falso positivo",
     any("estoque" in r for r in viols(s_lucro, d_com)), False)

print("\n=== a checagem 7 nasce em OBSERVACAO (nao puxa retentativa) ===")
todas = S.validar_saida(s_inventa, d_sem, [], [])
so7 = [x for x in todas if "estoque" in x["regra"]]
caso("checagem 7 marcada observa=True", all(x["observa"] for x in so7) and len(so7) > 0, True)
caso("checagens antigas seguem ativas",
     all(not x["observa"] for x in todas if "estoque" not in x["regra"]), True)

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
