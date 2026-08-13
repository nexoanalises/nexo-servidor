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
for executou, lucro, trecho in [
        ("Sim, todas",   "15.000", "Os resultados foram MISTOS"),
        ("Sim, todas",   "7.900",  "Os resultados foram MISTOS"),
        ("Não executei", "15.000", "Vale descobrir o que puxou"),
        ("Não executei", "7.900",  "não chegou a ser testada"),
        ("Em parte",     "15.000", "terminar o que ficou pela metade"),
        ("Em parte",     "7.900",  "o que faltou executar era justamente")]:
    b = "\n".join(S._bloco_ciclo(payload(executou, lucro=lucro)))
    caso(f"{executou:12} + lucro {lucro}", trecho in b, True)

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

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
