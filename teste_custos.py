# A HIERARQUIA DAS DUAS FONTES DE CUSTO FIXO. Zero token — só Motor.
#
# Existe por causa do achado 1.12 das auditorias de 05–06/08: dois blocos publicavam
# "custo fixo" na MESMA análise, por caminhos independentes e com valores diferentes —
# `_custos_fixos` (inferência sobre o texto livre) e `compra_mercadoria` (número que o
# lojista declarou). Os rótulos eram quase idênticos: "Composição do custo" contra
# "Composição dos custos". O cliente lia dois números para a mesma coisa.
#
# A regra que este teste trava: DECLARAÇÃO GANHA DE INFERÊNCIA. Havendo o número
# declarado, a varredura vira nomeadora — diz DO QUÊ é o custo fixo e cala a cifra.
# E se as duas leituras não couberem uma na outra, cala as duas.
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

# custos 46.900. Detalhado no texto livre: 6.000 + 9.000 + 1.200 = 16.200 de fixo.
DETALHE = "observacoes: aluguel R$ 6.000, folha R$ 9.000, energia R$ 1.200\n"
# O mesmo detalhamento, mas estourando o fixo que a declaração deixa (46.900 − 28.500).
ESTOURA = "observacoes: aluguel R$ 12.000, folha R$ 9.000, energia R$ 1.200\n"

def payload(extra=""):
    return ("nome_negocio: Loja da Bia\nperiodo: Junho/2026\nfaturamento: 54.800\n"
            "meta: 55.000\ncustos: 46.900\nlucro: 7.900\n" + extra)

def linhas(d):
    i, r = S.calcular_motor(d)
    return "\n".join(i + r)

print("\n=== SEM declaração: a inferência é a única fonte, e publica a cifra ===")
t = linhas(payload(DETALHE))
caso("publica a composição inferida", "Composição do custo (pelo que você detalhou)" in t, True)
caso("com o fixo somado do texto", "fixos R$ 16.200" in t, True)
caso("e nomeia o que somou", "aluguel, folha, energia e internet" in t, True)
caso("aponta onde a redução é possível", "em mercadoria e taxas" in t, True)

print("\n=== COM declaração: a varredura cala a cifra e vira nomeadora ===")
t = linhas(payload(DETALHE + "compra_mercadoria: 28.500\n"))
caso("nomeia sem cifra própria", "Composição do custo fixo (pelo que você detalhou)" in t, True)
caso("diz DO QUÊ é o fixo", "aluguel, folha, energia e internet" in t, True)
caso("a cifra inferida SAIU", "fixos R$ 16.200" in t, False)
caso("a declarada continua", "Composição dos custos" in t, True)
caso("com o fixo declarado (46.900 − 28.500)", "R$ 18.400" in t, True)

print("\n=== e nunca dois valores de custo fixo no mesmo relatório ===")
# O defeito original: 16.200 (inferido) e 18.400 (declarado) lado a lado, ambos
# rotulados como custo fixo. Só um número de custo fixo pode sobrar.
caso("16.200 e 18.400 não convivem", ("16.200" in t) and ("18.400" in t), False)

print("\n=== fontes que se contradizem: cala as duas ===")
# Detalhado 22.200 de fixo, mas a declaração só deixa 18.400. Não cabe: nem nomeia.
t = linhas(payload(ESTOURA + "compra_mercadoria: 28.500\n"))
caso("não nomeia", "pelo que você detalhou" in t, False)
caso("mas a declaração, que é o dado do lojista, fica", "Composição dos custos" in t, True)

print("\n=== declaração inválida não vale como declaração ===")
# compra maior que os custos: o Motor já a recusa. Recusada, a inferência volta a ser
# a única fonte — e publicar a cifra dela é correto, porque não há outra concorrendo.
t = linhas(payload(DETALHE + "compra_mercadoria: 99.000\n"))
caso("avisa que a declaração não fecha", "maior que os custos do período" in t, True)
caso("e a inferência reassume com cifra", "fixos R$ 16.200" in t, True)

print("\n=== sem detalhamento nenhum, silêncio ===")
t = linhas(payload("compra_mercadoria: 28.500\n"))
caso("não inventa composição de fixo", "pelo que você detalhou" in t, False)
caso("a declarada continua sozinha", "Composição dos custos" in t, True)

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
