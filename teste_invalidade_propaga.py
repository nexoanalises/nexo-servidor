# ENTRADA INCOERENTE CONTAMINA TUDO QUE DEPENDE DELA.
#
# 🔴 O CASO REAL QUE ORIGINOU ESTE ARQUIVO (13/08, "Celular & Cia"). O relatório dizia,
# na MESMA tela:
#
#     Margem líquida: 75% (margem saudável)
#     Números não fecham: faturamento menos custos dá R$ 20.000,
#                         mas o lucro informado é R$ 45.000
#
# E o §2 amplificava: *"O lucro de R$ 45.000 é um ponto positivo, considerando a margem
# saudável."* Depois o §6 recomendava gastar R$ 35.000.
#
# ### O produto avisava que o número estava errado e concluía a partir dele.
#
# O veredito do fundador: diante de números incoerentes o NEXO ou BLOQUEIA e pede
# correção, ou SEGUE só com o que é seguro, invalidando tudo que depende deles. O que
# ele não pode é dizer "não fecham" e usar os mesmos números para afirmar "margem
# saudável". **Aviso ao lado de conclusão é conclusão** — ninguém lê o rodapé antes de
# acreditar no título.
#
# ⚠️ E a trava que este arquivo também guarda é a do EXCESSO: invalidar o que depende
# não é invalidar o que está por perto. Faturamento e custos continuam sendo lidos,
# porque não têm nada a ver com o número que não bateu.
import sys
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class _Qq:
    def __init__(self, *a, **k): self.config = {}
    def __call__(self, *a, **k): return _Qq()
    def __getattr__(self, _): return _Qq()
    def __setitem__(self, k, v): pass
    def __getitem__(self, k): return _Qq()


for n in ("flask", "gspread", "google", "google.oauth2", "google.oauth2.service_account",
          "dateutil", "dateutil.relativedelta", "requests", "groq"):
    m = types.ModuleType(n)
    m.__getattr__ = lambda _x: _Qq()
    sys.modules.setdefault(n, m)
sys.modules["flask"].Flask = _Qq
sys.modules["flask"].request = _Qq()
sys.modules["flask"].jsonify = _Qq()
sys.modules["google.oauth2.service_account"].Credentials = _Qq
sys.modules["dateutil.relativedelta"].relativedelta = _Qq
sys.modules["groq"].Groq = _Qq

import servidor as S  # noqa: E402

ok = falhou = 0


def caso(t, obtido, esperado):
    global ok, falhou
    b = obtido == esperado
    print(f"{'  OK  ' if b else ' FALHA'} | {t}")
    if not b:
        print(f"         obtido={obtido!r}\n         esperado={esperado!r}")
    ok, falhou = ok + b, falhou + (not b)


# O caso EXATO que o fundador congelou.
INCOERENTE = ("nome_negocio: Celular & Cia\nperiodo: Agosto/2026\n"
              "faturamento: 60.000\nmeta: 70.000\ncustos: 40.000\nlucro: 45.000\n")
COERENTE = ("nome_negocio: Celular & Cia\nperiodo: Agosto/2026\n"
            "faturamento: 60.000\nmeta: 70.000\ncustos: 40.000\nlucro: 20.000\n")


def motor(d):
    ind, rad = S.calcular_motor(d)
    return ind, rad, "\n".join(ind + rad)


print("=== 1. a regra reconhece o caso, e não vê fantasma no caso coerente ===")
caso("60.000 − 40.000 ≠ 45.000 é incoerente",
     S._lucro_incoerente(60000, 40000, 45000), True)
caso("60.000 − 40.000 = 20.000 é coerente",
     S._lucro_incoerente(60000, 40000, 20000), False)
caso("diferença dentro de 15% do faturamento NÃO é incoerência",
     S._lucro_incoerente(60000, 40000, 22000), False)
caso("sem custos informados, não há o que conferir",
     S._lucro_incoerente(60000, None, 45000), False)

print("\n=== 2. NADA que dependa do lucro sobrevive ===")
ind, rad, tudo = motor(INCOERENTE)
caso("o alerta de inconsistência é PUBLICADO",
     any("Números não fecham" in l for l in rad), True)
caso("o alerta diz o que ficou de fora",
     any("FORA desta leitura" in l for l in rad), True)
caso("⛔ nenhuma linha diz 'margem saudável'", "margem saudável" in tudo, False)
caso("⛔ nenhuma linha diz 'margem apertada'", "margem apertada" in tudo, False)
caso("⛔ o indicador de margem líquida não é publicado",
     any("Margem líquida" in l for l in ind), False)
caso("⛔ o Radar não traz bandeira de margem",
     any("Margem líquida" in l for l in rad), False)

print("\n=== 3. mas o que NÃO depende do lucro continua vivo ===")
# 🔴 Invalidar o que depende não é invalidar o que está por perto.
caso("o atingimento da meta continua sendo apurado",
     any("Atingimento da meta" in l for l in ind), True)
caso("a composição dos custos continua",
     any("Composição dos custos" in l or "custos" in l.lower() for l in ind + rad), True)

print("\n=== 4. e no caso COERENTE nada foi quebrado ===")
ind_c, rad_c, tudo_c = motor(COERENTE)
caso("a margem volta a ser publicada",
     any("Margem líquida" in l for l in ind_c), True)
caso("com o rótulo do Motor", "margem saudável" in tudo_c, True)
caso("e sem alerta de inconsistência",
     any("Números não fecham" in l for l in rad_c), False)

print("\n=== 5. o §8 não propõe alvo sobre margem inválida ===")
# `_bloco_metas` devolve LISTA de linhas — juntar antes de procurar.
metas_inc = "\n".join(S._bloco_metas("=== DADOS ATUAIS ===\n" + INCOERENTE))
metas_coe = "\n".join(S._bloco_metas("=== DADOS ATUAIS ===\n" + COERENTE))
caso("⛔ nenhum alvo de margem quando o lucro não fecha",
     "Margem líquida" in metas_inc, False)
caso("e o alvo volta quando o lucro fecha", "Margem líquida" in metas_coe, True)

print("\n=== 6. o FISCAL DA SAÍDA reprova o que o modelo escrever mesmo assim ===")
# Instrução no prompt não bastou: na análise real o modelo escreveu "margem saudável"
# com o aviso na tela. Aqui a saída volta para ele.
ind, rad, _ = motor(INCOERENTE)
SAIDA_RUIM = ("1. RADAR DO NEGÓCIO\n" + "\n".join(rad) +
              "\n\n2. DIAGNÓSTICO CENTRAL\n"
              "O lucro de R$ 45.000 é um ponto positivo, considerando a margem saudável.\n")
viol = S.validar_saida(SAIDA_RUIM, INCOERENTE, ind, rad)
tipos = {x["regra"] for x in viol}
caso("a saída é reprovada", any("inválido" in t for t in tipos), True)
# 🔴 E ela REPROVA DE VERDADE: `observa=False` manda a análise de volta ao modelo.
# O projeto tem a convenção de estrear checagem nova como `observa=True`, porque
# retentativa dobra o consumo de um teto diário compartilhado com cliente pagante.
# Aqui a convenção foi rompida DE PROPÓSITO: o falso positivo desta checagem exige
# uma frase que julgue margem/lucro justamente quando o Radar disse que não fecham —
# e o falso NEGATIVO é o produto concluindo sobre número que ele mesmo invalidou.
caso("e a reprova volta para o modelo, não só registra",
     [x["observa"] for x in viol if "inválido" in x["regra"]], [False])

SAIDA_BOA = ("1. RADAR DO NEGÓCIO\n" + "\n".join(rad) +
             "\n\n2. DIAGNÓSTICO CENTRAL\n"
             "O faturamento foi de R$ 60.000, abaixo da meta de R$ 70.000. "
             "Antes de ler o resultado, confira os lançamentos.\n")
viol_boa = S.validar_saida(SAIDA_BOA, INCOERENTE, ind, rad)
tipos_boa = {x["regra"] for x in viol_boa}
caso("a saída que respeita o limite NÃO é reprovada por isso",
     any("inválido" in t for t in tipos_boa), False)

# ⚠️ A linha do Radar é do CÓDIGO e entra literal na saída (M3). Ela cita o problema
# e não pode se autoacusar.
caso("o próprio aviso do Radar não se autoacusa",
     any("inválido" in str(t) for t in
         {x.get("tipo") if isinstance(x, dict) else str(x)
          for x in S.validar_saida("1. RADAR DO NEGÓCIO\n" + "\n".join(rad),
                                   INCOERENTE, ind, rad)}), False)

print("\n=== 7. o prompt carrega a instrução ===")
caso("a proibição está escrita no prompt",
     "ficaram FORA da leitura" in S.montar_prompt(INCOERENTE, "Celular e Acessórios")
     if hasattr(S, "montar_prompt") else True, True)

print("\n" + "=" * 62)
print(f"  {ok} passaram · {falhou} falharam")
print("=" * 62)
sys.exit(1 if falhou else 0)
