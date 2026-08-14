# §2 CICLO ANTERIOR — a seção que responde "o que eu fiz funcionou?".
# É ela que justifica o campo `acoes_quais`: sem a seção citar o que foi executado,
# o campo não teria por que existir. Zero token — só lógica.
import sys, types, os
# O console do Windows abre em cp1252 e derruba o teste no primeiro "→".
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
class _Qq:
    def __init__(self, *a, **k): self.config = {}
    def __call__(self, *a, **k): return _Qq()
    def __getattr__(self, _): return _Qq()
    def __setitem__(self, k, v): pass
    def __getitem__(self, k): return _Qq()
for n in ("flask", "gspread", "google", "google.oauth2", "google.oauth2.service_account",
          "dateutil", "dateutil.relativedelta", "requests", "groq"):
    m = types.ModuleType(n); m.__getattr__ = lambda _x: _Qq(); sys.modules.setdefault(n, m)
sys.modules["flask"].Flask = _Qq; sys.modules["flask"].request = _Qq(); sys.modules["flask"].jsonify = _Qq()
sys.modules["google.oauth2.service_account"].Credentials = _Qq
sys.modules["dateutil.relativedelta"].relativedelta = _Qq; sys.modules["groq"].Groq = _Qq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import servidor as S

ok = falhou = 0
def caso(t, obtido, esperado):
    global ok, falhou
    b = obtido == esperado
    print(f"{'  OK  ' if b else ' FALHA'} | {t}")
    if not b: print(f"         obtido={obtido!r}\n         esperado={esperado!r}")
    ok, falhou = ok + b, falhou + (not b)

RELATORIO_ANTERIOR = """1. RADAR DO NEGÓCIO
Margem líquida: 17,1%

7. AÇÕES IMEDIATAS
Criar uma ação de giro para o blazer de alfaiataria e a saia longa jeans nos próximos 30 dias.
Renegociar com o fornecedor Malharia Vale as trocas por defeito.

8. METAS ATÉ A PRÓXIMA ANÁLISE
De R$ 12.000 para R$ 13.000 em lucro."""

def payload(executou="", quais="", mudou="", lucro="7.900", com_anterior=True):
    atual = (f"nome_negocio: Loja da Bia\nperiodo: Agosto/2026\nfaturamento: 54.800\n"
             f"meta: 55.000\ncustos: 46.900\nlucro: {lucro}\n")
    if executou: atual += f"acoes_executadas: {executou}\n"
    if quais:    atual += f"acoes_quais: {quais}\n"
    if mudou:    atual += f"mudancas: {mudou}\n"
    if not com_anterior:
        return atual
    return ("=== ANÁLISE ANTERIOR 1 (período: Julho/2026) ===\n"
            "DADOS DAQUELA ANÁLISE:\nfaturamento: 70.000\nmeta: 70.000\n"
            "custos: 50.000\nlucro: 12.000\n"
            f"DECISÕES RECOMENDADAS NAQUELA ANÁLISE:\n{RELATORIO_ANTERIOR}\n"
            "=== DADOS ATUAIS ===\n" + atual)

print("\n=== primeira análise: a seção NÃO existe ===")
caso("sem análise anterior, bloco vazio", S._bloco_ciclo(payload(com_anterior=False)), [])

print("\n=== as ações recomendadas voltam nomeadas ===")
b = "\n".join(S._bloco_ciclo(payload("Sim, todas")))
caso("cita a ação do blazer", "blazer de alfaiataria" in b, True)
caso("cita a do fornecedor", "Malharia Vale" in b, True)
caso("não traz a meta como se fosse ação", "13.000" in b, False)

print("\n=== as leituras ===")
# lucro caiu (12.000 -> 7.900) = não melhorou · lucro subiu (12.000 -> 15.000) = melhorou
#
# 🔴 MUDOU EM 13/08, e a mudança vale nas DUAS direções. Este payload tem faturamento
# 70.000 → 54.800 (−22%), custos 50.000 → 46.900 (melhor) e lucro que sobe ou desce.
# É RESULTADO MISTO — e o veredito saía de UMA linha só, `lucro >= lucro_ant`.
#
# Com o lucro subindo, o produto dizia "repetir é a aposta mais segura" enquanto o
# faturamento caía 22%: parabenizava por uma queda de um quinto da receita. Com o
# lucro caindo, dizia "o resultado não veio" ignorando que os custos melhoraram.
#
# ⚠️ Os dois são a MESMA falha, e a regra congelada pelo fundador — "resultado misto
# não pode virar resultado que não veio" — não tem lado: vale igual para o elogio.
#
# 🔴 E NÃO TEM DECLARAÇÃO TAMPOUCO. O estado é do RESULTADO; quem declarou a execução
# foi o lojista. Enquanto o MISTO valia só para "Sim, todas", as outras duas
# ramificações continuavam decidindo por `lucro >= lucro_ant` — a falha original,
# intacta em dois terços do bloco. Neste payload as SEIS combinações são mistas
# (faturamento −22% contra custos melhorando), então o lucro nunca decidiu nada aqui.
#
# A asserção agora cobra as DUAS orações: o estado, que vem dos números, e a oração
# de execução, que vem da declaração e não pode sumir junto.
for executou, lucro, trecho in [
        ("Sim, todas",   "15.000", "não atribui essas variações às ações executadas"),
        ("Sim, todas",   "7.900",  "não atribui essas variações às ações executadas"),
        ("Não executei", "15.000", "não chegou a ser testada e continua de pé"),
        ("Não executei", "7.900",  "não chegou a ser testada e continua de pé"),
        ("Em parte",     "15.000", "terminar o que ficou pela metade"),
        ("Em parte",     "7.900",  "terminar o que ficou pela metade")]:
    b = "\n".join(S._bloco_ciclo(payload(executou, lucro=lucro)))
    caso(f"{executou:12} + lucro {lucro} → misto", "Os resultados foram MISTOS" in b, True)
    caso(f"{executou:12} + lucro {lucro} → oração da declaração", trecho in b, True)

# ⛔ E o que o MISTO não pode fazer: dizer a quem NÃO executou que o NEXO não atribui
# o resultado "às ações executadas" — não houve ação a que atribuir.
b = "\n".join(S._bloco_ciclo(payload("Não executei", lucro="15.000")))
caso("não fala em 'ações executadas' para quem não executou",
     "às ações executadas" in b, False)

print("\n=== 🔴 o par que hoje recebe o MESMO conselho ===")
b_falhou = "\n".join(S._bloco_ciclo(payload("Sim, todas", lucro="7.900")))
b_nao_fez = "\n".join(S._bloco_ciclo(payload("Não executei", lucro="7.900")))
caso("mesmos números, conselhos diferentes", b_falhou == b_nao_fez, False)
# 🔴 Quem tentou passa a ouvir a leitura MISTA — que é o que os números dizem, e que
# preserva causalidade onde "mude a abordagem" não preservava.
caso("quem tentou ouve a leitura mista", "MISTOS" in b_falhou, True)
caso("e ela não atribui o movimento às ações",
     "não atribui essas variações às ações" in b_falhou, True)
caso("quem não tentou ouve 'continua de pé'", "continua de pé" in b_nao_fez, True)

print("\n=== o acoes_quais aparece no relatório (a condição do fundador) ===")
b = "\n".join(S._bloco_ciclo(payload("Em parte", quais="girei a coleção, mas não renegociei")))
caso("o que foi executado é citado", "girei a coleção, mas não renegociei" in b, True)
caso("junto do rótulo", "Executei em parte — girei" in b, True)

print("\n=== sem declaração, NÃO atribui ===")
b = "\n".join(S._bloco_ciclo(payload()))
caso("declara que não atribui", "sem atribuí-lo às recomendações" in b, True)
for t in ["Repetir é a aposta", "mudar a abordagem", "continua de pé"]:
    caso(f"e não escolhe história: {t}", t in b, False)

print("\n=== o que mudou por conta própria entra ===")
b = "\n".join(S._bloco_ciclo(payload("Sim, todas", mudou="troquei de fornecedor")))
caso("cita a mudança declarada", "O que mudou por sua conta: troquei de fornecedor" in b, True)

print("\n=== sem lucro comparável, não inventa leitura ===")
b = "\n".join(S._bloco_ciclo(payload("Sim, todas", lucro="")))
# 🔴 O INVARIANTE É A NÃO ATRIBUIÇÃO, não a frase que a carrega. Sem lucro, faturamento
# e custos continuam comparáveis — a leitura MISTA se forma com o que existe, e ela
# já traz a não atribuição dentro. Exigir a frase antiga seria exigir que o produto
# calasse sobre dois números que ele tem.
caso("declara que não atribui, de um jeito ou de outro",
     ("sem atribuí-lo" in b) or ("não atribui essas variações" in b), True)
# ⛔ E o que continua proibido: escolher a história do sucesso ou do fracasso.
for t in ["Repetir é a aposta", "mudar a abordagem", "resultado não veio"]:
    caso(f"e não escolhe história: {t}", t in b, False)


print("\n=== 🔴 O VERBO SEGUE O MOVIMENTO — NOS DOIS LADOS (14/08) ===")
# A regra estava aplicada só ao lado RUIM: "custo que piorou SUBIU, não recuou". O lado
# BOM herdou o defeito espelhado — um comparável de direção negativa que MELHORA CAI, e
# a frase dizia que ele "avançou".
#
# Pego no teste dirigido da Aromática, ANTES de gastar análise real.
#
# ⚖️ É a lição de 13/08 outra vez: regra boa não tem lado.
b = S._leitura_mista(["faturamento", "custos"], ["lucro"])
caso("custo que melhorou CAIU, não avançou", "custos caíram" in b, True)
caso("⛔ e não diz que ele avançou", "custos avançaram" in b, False)
caso("o que subiu de verdade continua avançando", "faturamento avançou" in b, True)
caso("e o lado ruim continua recuando", "lucro recuou" in b, True)

print("\n  — e o verbo concorda com o NÚMERO GRAMATICAL, não com o tamanho da lista —")
# "custos" e "clientes" são plurais mesmo sozinhos. Saía "enquanto custos subiu".
b2 = S._leitura_mista(["clientes"], ["custos"])
caso("clientes sozinho leva verbo plural", "clientes avançaram" in b2, True)
caso("custos sozinho leva verbo plural", "custos subiram" in b2, True)
caso("⛔ nunca 'custos subiu'", "custos subiu" in b2, False)
b3 = S._leitura_mista(["faturamento"], ["lucro"])
caso("faturamento sozinho é singular", "faturamento avançou" in b3, True)
caso("lucro sozinho é singular", "lucro recuou" in b3, True)

print("\n=== ⛔ O ESTOQUE PERDEU A VALÊNCIA (#102) — direção sim, juízo não ===")
# 🔴 Enquanto `estoque_valor` significava ESTOQUE PARADO, `-1` era honesto: encalhe
# caindo é bom, sem discussão. Agora significa ESTOQUE TOTAL, e a direção deixou de
# decidir sozinha — estoque menor pode ser giro saudável OU risco de ruptura; maior
# pode ser excesso OU preparação para um mês forte.
#
# ⚖️ Direção pode ser publicada; VALÊNCIA EXIGE EVIDÊNCIA ADICIONAL.
caso("⛔ o estoque não tem mais direção declarada",
     "estoque_valor" in S._DIRECAO_COMPARAVEL, False)
caso("e está nomeado como sem valência, não simplesmente esquecido",
     "estoque_valor" in S._SEM_VALENCIA, True)

def classificar(ant, at):
    return S._classificar_ciclo(at, ant)

# Estoque subindo forte, e mais nada mudando: NÃO forma estado misto sozinho.
av, re_ = classificar({"estoque_valor": 20000, "faturamento": 50000},
                      {"estoque_valor": 24000, "faturamento": 50000})
caso("estoque subindo sozinho não entra em nenhum dos lados", (av, re_), ([], []))
# Estoque caindo idem — nem para o lado bom.
av, re_ = classificar({"estoque_valor": 24000}, {"estoque_valor": 22000})
caso("estoque caindo sozinho também não", (av, re_), ([], []))

# ⚠️ E o MISTO não perde nada: forma-se com quem TEM valência definida.
av, re_ = classificar({"faturamento": 50000, "lucro": 10000, "custos": 40000, "estoque_valor": 20000},
                      {"faturamento": 58000, "lucro": 14000, "custos": 44000, "estoque_valor": 24000})
caso("o misto se forma sem precisar do estoque", bool(av and re_), True)
caso("e o estoque não aparece em nenhum lado", "estoque_valor" in av + re_, False)
b4 = S._leitura_mista(av, re_)
caso("a frase não classifica o estoque", "estoque" in b4, False)

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
