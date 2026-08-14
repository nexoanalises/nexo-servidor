# A PREOCUPAÇÃO DECLARADA — LENTE DE COLETA, JAMAIS DIAGNÓSTICO. Zero token.
#
# Existe por causa do commit 2 do #088 e das três travas que o fundador fixou:
#   1. obrigatório;
#   2. pertence à ANÁLISE/período, nunca ao perfil permanente;
#   3. serve para ordenar/priorizar a coleta, JAMAIS para determinar antecipadamente
#      o diagnóstico.
#
# A trava 3 é a que este arquivo guarda, e ela é escrita em CÓDIGO de propósito: pedir
# ao modelo que "não conclua pela preocupação do cliente" é instrução, e instrução
# sobre enquadramento falha do mesmo jeito que falhava sobre número (#083). O que se
# garante aqui é o FATO publicado ao lado da declaração — se o lojista aponta estoque
# e o estoque caiu 26,7%, isso sai no Radar por código, mesmo que o modelo escreva um
# diagnóstico de estoque logo abaixo.
import sys, types
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

# 🔴 `estoque_base: total` nas DUAS pontas desde 14/08. Sem ele, `estoque_valor` não é
# comparável entre períodos — a mesma razão que impede o giro. Ver o caso da transição
# no fim do arquivo, que prova a supressão.
def payload(preocupacao=None, atuais=None, anteriores=None, base=True):
    a = {"faturamento": 68000, "custos": 52000, "lucro": 16000,
         "estoque_valor": 22000, "clientes": 440, "compra_mercadoria": 20000}
    b = {"faturamento": 60000, "custos": 48000, "lucro": 12000,
         "estoque_valor": 30000, "clientes": 420, "compra_mercadoria": 18000}
    if base:
        a["estoque_base"] = b["estoque_base"] = "total"
    a.update(atuais or {}); b.update(anteriores or {})
    def bloco(d):
        return "".join(f"{k}: {v}\n" for k, v in d.items())
    atual = "Segmento: Loja / Varejo e Moda\nnome_negocio: Loja da Bia\n" + bloco(a)
    if preocupacao is not None:
        atual += f"preocupacao: {preocupacao}\n"
    return ("=== ANÁLISE ANTERIOR 1 (período: Julho/2026) ===\n"
            f"DADOS DAQUELA ANÁLISE:\n{bloco(b)}"
            "DECISÕES RECOMENDADAS NAQUELA ANÁLISE:\nnada\n"
            "=== DADOS ATUAIS ===\n" + atual)

def linha(dados):
    _, radar = S.calcular_motor(dados)
    return next((l for l in radar if "preocupação declarada" in l), None)

print("\n=== o campo é publicado por CÓDIGO, no radar (M3/#082) ===")
l = linha(payload("Estoque"))
caso("a linha existe", l is not None, True)
caso("nomeia a preocupação declarada", "ESTOQUE" in (l or ""), True)
caso("não fica só nos indicadores",
     any("preocupação declarada" in i for i in S.calcular_motor(payload("Estoque"))[0]), False)

print("\n=== TRAVA 3: a declaração vem com o FATO apurado ao lado ===")
# estoque 30.000 -> 22.000 = caiu 26,7%. O lojista teme estoque; os números discordam.
caso("publica a variação da grandeza que ele apontou", "caiu 26,7%" in (l or ""), True)
caso("e diz, por código, que o diagnóstico segue os números",
     "segue os números apurados, não a preocupação declarada" in (l or ""), True)

print("\n=== cada preocupação olha a SUA grandeza ===")
caso("Vendas  → faturamento (subiu 13,3%)",
     "o faturamento subiu 13,3%" in (linha(payload("Vendas")) or ""), True)
caso("Lucro   → lucro (subiu 33,3%)",
     "o lucro subiu 33,3%" in (linha(payload("Lucro")) or ""), True)
caso("Custos  → custo total (subiu 8,3%)",
     "o custo total subiu 8,3%" in (linha(payload("Custos")) or ""), True)
caso("Clientes→ clientes (subiu 4,8%)",
     "o número de clientes subiu 4,8%" in (linha(payload("Clientes")) or ""), True)

print("\n=== a frase concorda em número: o verbo é sempre singular ===")
# "os custos subiu 8,3%" saiu na primeira versão e ia para o Radar do cliente.
for p in ("Vendas", "Lucro", "Estoque", "Clientes", "Custos"):
    l_p = linha(payload(p)) or ""
    caso(f"{p:9} sem erro de concordância",
         "os custos subiu" in l_p or "clientes subiram" in l_p, False)

print("\n=== 'Outro' não inventa grandeza — declara e cala ===")
lo = linha(payload("Outro"))
caso("publica a declaração", "OUTRO" in (lo or ""), True)
caso("sem comparação nenhuma", "subiu" in (lo or "") or "caiu" in (lo or ""), False)
caso("mas mantém a trava do diagnóstico",
     "segue os números apurados" in (lo or ""), True)

print("\n=== sem análise anterior: declara sem comparar ===")
sem_ant = ("Segmento: Loja / Varejo e Moda\nnome_negocio: X\n"
           "faturamento: 68000\ncustos: 52000\nlucro: 16000\npreocupacao: Vendas\n")
l2 = linha(sem_ant)
caso("a linha existe mesmo na primeira análise", l2 is not None, True)
caso("e não afirma variação que não pode calcular",
     "subiu" in (l2 or "") or "caiu" in (l2 or ""), False)

print("\n=== campo vazio ou ausente: silêncio, não linha vazia ===")
caso("ausente → nenhuma linha", linha(payload(None)), None)
caso("vazio → nenhuma linha", linha(payload("")), None)

print("\n=== guarda determinística: variação absurda cala (M5) ===")
# faturamento anterior de R$ 1 faria a variação dar milhões por cento.
caso("delta fora da faixa de sanidade não é publicado",
     "subiu" in (linha(payload("Vendas", anteriores={"faturamento": 1})) or ""), False)
caso("mas a declaração continua publicada",
     "VENDAS" in (linha(payload("Vendas", anteriores={"faturamento": 1})) or ""), True)

print("\n=== variação insignificante não vira ruído ===")
caso("diferença abaixo de 0,1% não é publicada",
     "subiu" in (linha(payload("Vendas", atuais={"faturamento": 60000})) or ""), False)

print("\n=== a linha publicada não é reprovada pelo próprio validador ===")
d = payload("Estoque")
ind, radar = S.calcular_motor(d)
saida = "1. RADAR DO NEGÓCIO\n" + "\n".join(radar) + \
        "\n\n8. METAS ATÉ A PRÓXIMA ANÁLISE\n" + "\n".join(S._bloco_metas(d))
caso("nenhuma violação ATIVA no que o código publica",
     [x["regra"] for x in S.validar_saida(saida, d, ind, radar) if not x.get("observa")], [])

print("\n=== o prompt carrega a trava por escrito ===")
src = open(r"C:\Users\Ricardo\Desktop\Nexo arquivos antigos\nexo_servidor\servidor.py",
           encoding="utf-8").read()
caso("instrução de lente de coleta está no prompt",
     "LENTE DE COLETA, NÃO DIAGNÓSTICO" in src, True)
caso("e proíbe abrir o diagnóstico repetindo a preocupação",
     "PROIBIDO abrir o diagnóstico repetindo a preocupação declarada" in src, True)


print("\n=== ⛔ E A PREOCUPAÇÃO NÃO ESCAPA DA TRAVA DE NATUREZA (14/08) ===")
# O lojista declara ESTOQUE, e esta linha faz exatamente a variação entre os dois
# períodos. Se as naturezas não são comparáveis — a mesma razão que impede o giro —
# ela também não pode sair. Foi a contradição da Rodada 2: o Radar declarava o par
# inutilizável e o §2 publicava "+20%" logo abaixo.
sem = linha(payload("Estoque", base=False))
caso("a linha da preocupação continua existindo", sem is not None, True)
caso("⛔ mas SEM a variação do estoque", "caiu" in (sem or "") or "subiu" in (sem or ""), False)
caso("e ainda declara que o diagnóstico segue os números",
     "segue os números apurados" in (sem or ""), True)
# ⚠️ Outras grandezas não são afetadas: só o estoque tem natureza em transição.
lucro_sem = linha(payload("Lucro", base=False))
caso("preocupação com LUCRO publica a variação normalmente",
     "subiu 33,3%" in (lucro_sem or ""), True)

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
