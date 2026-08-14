# A IDENTIDADE DO GIRO. Zero token — só aritmética e histórico local.
#
# Existe por causa do commit 1 do #088: "o que devo comprar menos, comprar mais ou
# parar de comprar?" (veredito do fundador) se responde pela identidade contábil
# saída = estoque INICIAL + compra de mercadoria − estoque FINAL. O inicial é o
# estoque final da análise ANTERIOR, e as duas pontas do tempo têm de usar a MESMA
# fonte — o valor DECLARADO em `estoque_valor`, não a inferência sobre texto livre
# que `_valor_estoque` (M4) ainda aceita para as outras narrativas do produto.
#
# O que este teste trava: a identidade só publica quando as TRÊS pernas fecham; a
# regra da primeira vez (M6) declara a ausência em vez de calcular com o que não
# tem; e a comparação simples do estoque (via CAMPOS_COMPARAVEIS) usa sempre o
# campo declarado, nunca a descrição em texto livre.
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

# 🔴 `base` MUDOU EM 14/08. O giro exige que os DOIS períodos declarem `estoque_base:
# total` — a natureza do número, dita pela versão do app que o coletou. Até então a
# dica do campo pedia "o que está PARADO hoje" e a identidade `inicial + compras −
# final` exige o TOTAL: quem obedeceu a dica mandou encalhe, e o giro do ciclo seguinte
# o consumiria como se fosse o estoque inteiro. O padrão aqui é `True` porque este
# arquivo testa o contrato VIGENTE; a transição tem casos próprios no fim.
def payload(estoque_atual=None, compra=None, estoque_anterior=None, com_anterior=True,
            texto_estoque_atual="descrição qualquer", texto_estoque_anterior="descrição",
            base_atual=True, base_anterior=True):
    atual = "Segmento: Loja / Varejo e Moda\nnome_negocio: Loja da Bia\n"
    atual += "faturamento: 56350\ncustos: 46900\nlucro: 9450\n"
    if compra is not None:
        atual += f"compra_mercadoria: {compra}\n"
    if estoque_atual is not None:
        atual += f"estoque_valor: {estoque_atual}\n"
    if base_atual:
        atual += "estoque_base: total\n"
    atual += f"estoque: {texto_estoque_atual}\n"
    if not com_anterior:
        return atual
    ant = "faturamento: 50000\ncustos: 40000\nlucro: 8000\n"
    if estoque_anterior is not None:
        ant += f"estoque_valor: {estoque_anterior}\n"
    if base_anterior:
        ant += "estoque_base: total\n"
    ant += f"estoque: {texto_estoque_anterior}\n"
    return ("=== ANÁLISE ANTERIOR 1 (período: Julho/2026) ===\n"
            f"DADOS DAQUELA ANÁLISE:\n{ant}"
            "DECISÕES RECOMENDADAS NAQUELA ANÁLISE:\nnada\n"
            "=== DADOS ATUAIS ===\n" + atual)

def giro(dados):
    """A linha do giro sai do RADAR, não dos indicadores — publicação garantida por
    código (M3/#082). Procurar nos indicadores aqui deixaria o teste verde enquanto o
    cliente não veria número nenhum: foi exatamente o que a validação real de 10/08
    pegou, com o teste determinístico passando."""
    _, radar = S.calcular_motor(dados)
    return next((l for l in radar if "Giro do estoque" in l), None)

def indicadores_de(dados):
    ind, _ = S.calcular_motor(dados)
    return ind

print("\n=== regra da primeira vez (M6): sem período anterior com o dado ===")
caso("primeira análise do negócio (sem histórico algum): declara ausência",
     "ainda não calculável" in (giro(payload(estoque_atual=18000, compra=5000, com_anterior=False)) or ""),
     True)
caso("há análise anterior, mas ela não tinha estoque_valor (transição): mesma ausência",
     "ainda não calculável" in (giro(payload(estoque_atual=18000, compra=5000, estoque_anterior=None)) or ""),
     True)
caso("sem estoque_valor no período ATUAL: nem calcula, nem reclama — silêncio",
     giro(payload(estoque_atual=None, compra=5000, estoque_anterior=20000)), None)

print("\n=== a identidade fecha e publica giro + cobertura ===")
# saída = 30.000 (inicial) + 20.000 (compra) − 22.000 (final) = 28.000
# estoque médio = (30.000+22.000)/2 = 26.000 → giro = 28.000/26.000 = 1,0769... ≈ 1,08x
# cobertura = 22.000/28.000 = 0,7857... ≈ 0,8 meses
l = giro(payload(estoque_atual=22000, compra=20000, estoque_anterior=30000))
caso("linha existe", l is not None, True)
caso("saída em reais", "R$ 28.000" in (l or ""), True)
caso("giro de 1,08x", "1,08x" in (l or ""), True)
caso("cobertura de 0,8 meses", "0,8 meses" in (l or ""), True)

print("\n=== as três pernas são exigidas — falta qualquer uma, cala ===")
caso("sem compra_mercadoria no período atual: silêncio (não assume compra=0)",
     giro(payload(estoque_atual=22000, compra=None, estoque_anterior=30000)), None)

print("\n=== os números que não fecham não viram giro negativo ===")
# final (15.000) maior do que inicial+compra explicariam (10.000+1.000=11.000)
caso("saída ≤ 0: números não fecham, cala",
     giro(payload(estoque_atual=15000, compra=1000, estoque_anterior=10000)), None)

print("\n=== cobertura fora da faixa de sanidade também cala ===")
# saída quase zero (200) sobre estoque de 99.900 → cobertura ~500 meses: campo mal
# preenchido, não fato do negócio.
caso("cobertura > 60 meses: cala em vez de publicar absurdo",
     giro(payload(estoque_atual=99900, compra=100, estoque_anterior=100000)), None)

print("\n=== a comparação simples usa o campo DECLARADO, nunca a descrição livre ===")
# estoque_valor diz 12.000; o texto livre, de propósito, cita OUTRA cifra (30.000).
# Se a comparação vazasse para o texto, a leitura de %  bateria diferente.
ind, _ = S.calcular_motor(payload(
    estoque_atual=12000, compra=5000, estoque_anterior=10000,
    texto_estoque_atual="tem uns R$ 30.000 encalhados, seria bom vender",
    texto_estoque_anterior="tinha bem menos, uns R$ 3.000"))
# 🔴 O RÓTULO MUDOU EM 14/08: `estoque_valor` passou a significar estoque TOTAL, e
# chamá-lo de "parado" era o Motor atribuindo ao dado uma natureza que a coleta não
# garantia. Total ≠ encalhado.
comp = next((l for l in ind if l.startswith("Valor do estoque:")), None)
caso("comparação simples existe (via CAMPOS_COMPARAVEIS)", comp is not None, True)
caso("usa o declarado do período anterior (10.000), não o da prosa (3.000)",
     "10.000" in (comp or ""), True)
caso("usa o declarado do período atual (12.000), não o da prosa (30.000)",
     "12.000" in (comp or ""), True)
caso("a cifra da prosa (30.000) não vaza para a linha comparativa",
     "30.000" in (comp or ""), False)

print("\n=== a publicação é GARANTIDA por código, não pedida ao modelo (M3/#082) ===")
d_ok = payload(estoque_atual=22000, compra=20000, estoque_anterior=30000)
ind_ok = indicadores_de(d_ok)
caso("a linha do giro NÃO fica só nos indicadores (contexto que o modelo pode ignorar)",
     any("Giro do estoque" in i for i in ind_ok), False)
caso("ela está no radar, que _garantir_secao publica literalmente na §1",
     "Giro do estoque" in (giro(d_ok) or ""), True)
caso("a declaração de ausência também é publicada, não sussurrada",
     (giro(payload(estoque_atual=18000, compra=5000, com_anterior=False)) or "").startswith("📦"),
     True)

print("\n=== o validador não pode reprovar o que o próprio código publicou ===")
# Os dois defeitos que só a rodada real de 10/08 revelou, e que os testes
# determinísticos anteriores não pegavam porque nenhum deles montava a saída final.
d_ok = payload(estoque_atual=22000, compra=20000, estoque_anterior=30000)
ind_r, radar_r = S.calcular_motor(d_ok)
metas = S._bloco_metas(d_ok)
saida_publicada = "1. RADAR DO NEGÓCIO\n" + "\n".join(radar_r) + \
                  "\n\n8. METAS ATÉ A PRÓXIMA ANÁLISE\n" + "\n".join(metas)
regras = [x["regra"] for x in S.validar_saida(saida_publicada, d_ok, ind_r, radar_r)]

caso("a linha do giro não é acusada de 'cifra de estoque diferente da informada'",
     "cifra de estoque diferente da informada" in regras, False)
caso("a meta de estoque não é acusada de 'meta sem ponto de partida'",
     "meta sem ponto de partida" in regras, False)
caso("nenhuma violação ATIVA no que o código publica — senão a análise cai no fallback",
     [x["regra"] for x in S.validar_saida(saida_publicada, d_ok, ind_r, radar_r)
      if not x.get("observa")], [])

print("\n=== ⛔ a meta de METADE DO ESTOQUE não existe mais ===")
# 🔴 SAIU EM 14/08, por veredito do fundador. "De R$ 22.000 para R$ 11.000 — metade do
# estoque que você informou" tem matemática correta e decisão nenhuma: não há régua
# calibrada que autorize cortar 50% do estoque num ciclo. Dividir por dois não era
# análise, era a única conta possível com um número só.
#
# ⚖️ É a lei da trava ⓑ no outro eixo — indicador sem benchmark não vira juízo; ALVO
# SEM RÉGUA NÃO VIRA META. E era pior que o modelo escrevendo: saía por CÓDIGO, dentro
# da seção que leva o selo "apurado".
caso("nenhuma meta de estoque é fabricada",
     any("stoque" in l for l in metas), False)
caso("e nenhuma linha divide o estoque pela metade",
     any("11.000" in l for l in metas), False)
# ⚠️ O que continua de pé: as metas que NASCEM do dado seguem publicadas.
caso("as metas do dado continuam existindo", len(metas) > 0, True)

print("\n=== estoque_valor entrou em CAMPOS_CRITICOS: preenchimento ilegível avisa ===")
d_ilegivel = payload(estoque_atual="não sei ao certo", compra=5000, estoque_anterior=30000)
_, radar_ilegivel = S.calcular_motor(d_ilegivel)
aviso = next((l for l in radar_ilegivel if "Valor do estoque hoje" in l), None)
caso("aviso de preenchimento aparece no radar", aviso is not None, True)
caso("cita o que o lojista escreveu", "não sei ao certo" in (aviso or ""), True)
caso("e o giro não dispara — não há número para usar",
     giro(d_ilegivel), None)

print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
