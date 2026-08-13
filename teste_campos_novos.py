# Os três campos novos que o servidor passou a ler: compra_mercadoria,
# recebimento_futuro e ancora_sazonal. Zero token — só Motor.
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

def payload(extra="", fat="54.800", ant=None):
    base = (f"nome_negocio: Loja da Bia\nperiodo: Junho/2026\nfaturamento: {fat}\n"
            f"meta: 55.000\ncustos: 46.900\nlucro: 7.900\n{extra}")
    if ant:
        return ("=== ANÁLISE ANTERIOR 1 ===\nDADOS DAQUELA ANÁLISE:\n" + ant +
                "\n=== DADOS ATUAIS ===\n" + base)
    return base

def linhas(d):
    i, r = S.calcular_motor(d)
    return "\n".join(i + r)

print("\n=== compra_mercadoria: para onde foi o dinheiro (D03) ===")
t = linhas(payload("compra_mercadoria: 28.500\n"))
caso("publica a composição", "Composição dos custos" in t, True)
caso("mostra a compra", "R$ 28.500" in t, True)
caso("calcula o custo fixo (46.900 − 28.500)", "R$ 18.400" in t, True)
caso("diz o peso da compra", "60,8%" in t, True)
# 🔴 A frase "o dinheiro que virou estoque não sumiu — está na prateleira" SAIU em
# 13/08, por veredito do fundador: ela trata TODA a compra como estoque remanescente,
# e no mesmo relatório o Motor calculava que R$ 34.000 tinham SAÍDO do estoque. Parte
# da compra vira venda; quanto permanece exige outra relação — que agora é publicada
# como "Compra × saída", quando há dois períodos para calculá-la.
caso("⛔ não afirma que a compra ficou na prateleira",
     "virou estoque não sumiu" in t, False)

print("\n=== e quando o número não fecha, DECLARA em vez de usar ===")
t = linhas(payload("compra_mercadoria: 99.000\n"))
caso("avisa que não fecha", "maior que os custos do período" in t, True)
caso("não publica composição errada", "Composição dos custos" in t, False)

print("\n=== recebimento_futuro: o eixo do caixa (D06) ===")
t = linhas(payload("recebimento_futuro: 16.440\n"))
caso("publica a defasagem", "ainda não entrou" in t, True)
caso("mostra o valor", "R$ 16.440" in t, True)
caso("mostra o peso", "30%" in t, True)

print("\n=== os dois juntos: entrou menos, saiu mais ===")
t = linhas(payload("compra_mercadoria: 28.500\nrecebimento_futuro: 16.440\n"))
caso("cruza a saída em mercadoria", "já saíram em mercadoria" in t, True)

print("\n=== a receber maior que o faturado: declara ===")
t = linhas(payload("recebimento_futuro: 90.000\n"))
caso("avisa", "maior que o faturamento" in t, True)
caso("não publica cifra de caixa", "ainda não entrou" in t, False)

print("\n=== campos vazios não inventam nada ===")
t = linhas(payload())
for termo in ("Composição dos custos", "ainda não entrou", "declarou que este costuma"):
    caso(f"silencia: {termo}", termo in t, False)

print("\n=== ancora_sazonal: a declaração é publicada ===")
t = linhas(payload("ancora_sazonal: Mês fraco\n"))
caso("publica a declaração", "costuma ser um mês fraco" in t, True)

print("\n=== a bandeira respeita a estação declarada ===")
# Não se compara emoji literal: ele se corrompe ao atravessar shell. Extrai-se a
# bandeira da linha que o cliente de fato vê — a da comparação rica.
VERMELHA, AMARELA, VERDE = "\U0001F534", "\U0001F7E1", "\U0001F7E2"
NOMES = {VERMELHA: "vermelha", AMARELA: "amarela", VERDE: "verde"}

def bandeira_do_faturamento(texto):
    for l in texto.split("\n"):
        if "Faturamento: R$" in l and l[:1] in NOMES:
            return NOMES[l[0]]
    return "ausente"

ANT = "faturamento: 70.000\nmeta: 70.000\ncustos: 50.000\nlucro: 12.000\n"
sem   = linhas(payload("", ant=ANT))                                # queda de ~22%
fraco = linhas(payload("ancora_sazonal: Mês fraco\n", ant=ANT))
forte = linhas(payload("ancora_sazonal: Mês forte\n", ant=ANT))

caso("sem declaração, queda de 22% é vermelha", bandeira_do_faturamento(sem), "vermelha")
caso("declarado mês fraco, vira amarela", bandeira_do_faturamento(fraco), "amarela")
caso("e explica ao cliente por que amarelou", "costuma ser um mês fraco" in fraco, True)
caso("mês forte NÃO suaviza a queda", bandeira_do_faturamento(forte), "vermelha")
caso("e não inventa nota sazonal no mês forte", "costuma ser um mês fraco" in forte, False)
caso("alta continua verde mesmo em mês fraco",
     bandeira_do_faturamento(linhas(payload("ancora_sazonal: Mês fraco\n", fat="90.000", ant=ANT))),
     "verde")

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
