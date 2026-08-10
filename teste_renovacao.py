# A CORRENTE DA RENOVAÇÃO. Zero token — só planilha e datas.
#
# Existe por causa do blocker de 08/08: a recorrência da Eduzz cobrava o cliente e o
# webhook gerava uma chave NOVA numa linha NOVA. A linha dele ficava parada na validade
# do primeiro ciclo, e no dia seguinte ao vencimento o app apagava a licença local e
# mostrava "Licença expirada. Renove em: <página de vendas>". Cliente em dia, cobrança
# em dia, deslogado — e ninguém tinha visto porque nunca houve um pagante.
#
# O que este teste trava: a renovação MOVE A DATA DA LINHA QUE JÁ EXISTE, a chave não
# muda, a folga não se acumula, e quem pagou atrasado não recebe menos do que comprou.
import sys, types
# O console do Windows abre em cp1252 e derruba o teste no primeiro "→".
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
class _Qq:
    def __init__(self,*a,**k): self.config={}
    def __call__(self,*a,**k): return _Qq()
    def __getattr__(self,_): return _Qq()
    def __setitem__(self,k,v): pass
    def __getitem__(self,k): return _Qq()
# `dateutil` e `datetime` NÃO entram na lista: é aritmética de calendário que este
# teste existe para conferir — stub aqui devolveria verde sem provar nada.
for n in ("flask","gspread","google","google.oauth2","google.oauth2.service_account",
          "requests","groq"):
    m=types.ModuleType(n); m.__getattr__=lambda _x:_Qq(); sys.modules.setdefault(n,m)
sys.modules["flask"].Flask=_Qq; sys.modules["flask"].request=_Qq(); sys.modules["flask"].jsonify=_Qq()
sys.modules["google.oauth2.service_account"].Credentials=_Qq
sys.modules["groq"].Groq=_Qq
sys.path.insert(0,r"C:\Users\Ricardo\Desktop\Nexo arquivos antigos\nexo_servidor")
import servidor as S
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

ok = falhou = 0
def caso(t, obtido, esperado):
    global ok, falhou
    b = obtido == esperado
    print(f"{'  OK  ' if b else ' FALHA'} | {t}")
    if not b: print(f"         obtido={obtido!r}\n         esperado={esperado!r}")
    ok, falhou = ok+b, falhou+(not b)

FOLGA = S.FOLGA_RENOVACAO_DIAS
def d(txt): return datetime.strptime(txt, "%Y-%m-%d")

# A planilha como o servidor a lê: linha 1 é cabeçalho.
CABECALHO = ["chave","plano","expiracao","ativo","cliente","data","email"]
def planilha(*linhas): return [CABECALHO] + list(linhas)
def linha(chave="NEXO-AAAA-1111", plano="ativacao", exp="2026-09-15",
          ativo="sim", email="bia@loja.com.br"):
    return [chave, plano, exp, ativo, "Bia", "10/08/2026 09:00", email]

print("\n=== O R$7 é um plano próprio, e não cai no padrão ===")
caso("PLANOS reconhece o valor 7", S.PLANOS.get("7"), ("ativacao", 1, "months"))
caso("e um mês é um mês, como no 47", S.PLANOS["7"][1], S.PLANOS["47"][1])
caso("o nome separa quem entrou por R$7", S.PLANOS["7"][0] != S.PLANOS["47"][0], True)
caso("valor fora da tabela continua caindo em mensal (#019)", S.PLANOS.get("33"), None)

print("\n=== A primeira validade já nasce com folga ===")
esperado = (datetime.now() + relativedelta(months=1) + timedelta(days=FOLGA)).strftime("%Y-%m-%d")
caso("R$7 dá um ciclo mensal", S.calcular_expiracao("7"), esperado)
caso("R$47 dá o mesmo ciclo", S.calcular_expiracao("47"), esperado)
caso("R$297 dá doze meses",
     S.calcular_expiracao("297"),
     (datetime.now() + relativedelta(months=12) + timedelta(days=FOLGA)).strftime("%Y-%m-%d"))
caso("vitalícia não tem data", S.calcular_expiracao("697"), "definitivo")

print("\n=== Achar a linha do cliente: é ELA que renova, não uma nova ===")
i, l = S.achar_linha_renovavel(planilha(linha()), "bia@loja.com.br")
caso("acha a linha 2", i, 2)
caso("e devolve a chave que o cliente já instalou", l[0], "NEXO-AAAA-1111")
caso("e-mail com espaço e maiúscula acha igual",
     S.achar_linha_renovavel(planilha(linha()), "  BIA@Loja.com.BR ")[0], 2)
caso("outro e-mail não acha", S.achar_linha_renovavel(planilha(linha()), "outro@x.com")[0], None)
caso("e-mail vazio não acha", S.achar_linha_renovavel(planilha(linha()), "")[0], None)
caso("e-mail None não quebra", S.achar_linha_renovavel(planilha(linha()), None)[0], None)
caso("planilha só com cabeçalho não acha", S.achar_linha_renovavel(planilha(), "bia@loja.com.br")[0], None)
caso("o cabeçalho nunca é linha renovável",
     S.achar_linha_renovavel([["chave","plano","expiracao","ativo","cliente","data","email"]], "email")[0], None)
caso("linha incompleta não derruba a varredura",
     S.achar_linha_renovavel(planilha(["NEXO-XXXX-9999","mensal"], linha()), "bia@loja.com.br")[0], 3)

print("\n=== O que NÃO se renova ===")
caso("licença desativada não renova",
     S.achar_linha_renovavel(planilha(linha(ativo="não")), "bia@loja.com.br")[0], None)
caso("vitalícia não se estende",
     S.achar_linha_renovavel(planilha(linha(exp="definitivo")), "bia@loja.com.br")[0], None)
caso("e vitalícia também não vira mensal por engano",
     S.achar_linha_renovavel(planilha(linha(exp="DEFINITIVO")), "bia@loja.com.br")[1], None)
caso("com duas linhas do mesmo e-mail, vale a última",
     S.achar_linha_renovavel(planilha(linha(), linha(chave="NEXO-BBBB-2222")), "bia@loja.com.br")[1][0],
     "NEXO-BBBB-2222")

print("\n=== A data anda, e o dia da cobrança não foge ===")
# Compra em 10/08 → validade 15/09 (um mês + folga). A recorrência cobra em 10/09.
caso("a renovação em dia devolve o mesmo dia do mês seguinte",
     S.validade_renovada("2026-09-15", 1, hoje=d("2026-09-10")), "2026-10-15")
v = "2026-09-15"
for _ in range(3):
    v = S.validade_renovada(v, 1, hoje=d(v) - timedelta(days=FOLGA))
caso("três ciclos seguidos e a folga NÃO se acumula", v, "2026-12-15")
caso("cobrança antecipada não encurta a validade",
     S.validade_renovada("2026-09-15", 1, hoje=d("2026-09-01")), "2026-10-15")
caso("plano anual estende doze meses",
     S.validade_renovada("2026-09-15", 12, hoje=d("2026-09-10")), "2027-09-15")

print("\n=== Quem paga atrasado recebe o ciclo inteiro, nunca menos ===")
caso("validade vencida conta a partir do pagamento",
     S.validade_renovada("2026-09-15", 1, hoje=d("2026-11-02")), "2026-12-07")
caso("data ilegível na planilha não trava a renovação",
     S.validade_renovada("15/09/2026", 1, hoje=d("2026-09-10")), "2026-10-15")
caso("célula vazia também não trava",
     S.validade_renovada("", 1, hoje=d("2026-09-10")), "2026-10-15")
caso("a validade nova é sempre maior que a antiga",
     S.validade_renovada("2026-09-15", 1, hoje=d("2026-09-10")) > "2026-09-15", True)

print("\n=== A gravação toca UMA célula: a validade. Nunca a chave, nunca o plano ===")
class _Ws:
    def __init__(self): self.escritas = []
    def update_cell(self, l, c, v): self.escritas.append((l, c, v))
ws = _Ws()
S.renovar_validade(ws, 2, "2026-10-15")
caso("uma escrita só", len(ws.escritas), 1)
caso("na linha do cliente, coluna C (expiracao)", ws.escritas[0][:2], (2, 3))
caso("com a data nova", ws.escritas[0][2], "2026-10-15")

print(f"\n{'='*54}\n{ok} OK · {falhou} FALHA(S)\n{'='*54}")
sys.exit(1 if falhou else 0)
