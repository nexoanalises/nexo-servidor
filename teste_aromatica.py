# AS CINCO CORREÇÕES DO TESTE DA AROMÁTICA (14/08) — Perfumaria, primeira rodada real
# com os campos `validade_*` do #097.
#
# O que a rodada provou de BOM, e vale travar para não regredir: os quatro campos
# atravessaram com as três naturezas certas — item=Perfume, valor=R$ 250, prazo=30
# dias. A coleta estruturada funcionou.
#
# E o que ela reprovou, no veredito do fundador:
#   ① composição de custo virou prova de perda      ("75% dos custos" sob "perder dinheiro")
#   ② estoque parado virou perda realizada          — e a frase era do PRÓPRIO PRODUTO
#   ③ compra virou compra errada                    ("mercadorias não mais necessárias")
#   ④ número virou meta                             (estoque → metade, sem régua)
#   ⑤ dado preciso virou tarefa vaga                ("verificar a validade dos perfumes")
#
# ⚖️ As três primeiras são o MESMO movimento: fato requalificado em juízo sem régua, e
# o mecanismo é o TÍTULO DA SEÇÃO fazendo o trabalho que a evidência deveria fazer. A
# quarta é a mesma disciplina no eixo do alvo. A quinta é o espelho: onde o produto TEM
# a régua e o dado, ele jogou a precisão fora.
#
# Zero token — só Motor, prompt e léxico.
import sys, types, os
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

# Os números reais da Aromática, 14/08.
AROMATICA = ("Segmento: Perfumaria e Cosméticos\nnome_negocio: Aromática\n"
             "periodo: Agosto/2026\nfaturamento: 50.000\nmeta: 60.000\n"
             "custos: 40.000\nlucro: 10.000\ncompra_mercadoria: 30.000\n"
             "recebimento_futuro: 15.000\nestoque_valor: 20.000\nestoque_base: total\n"
             "preocupacao: vendas\nancora_sazonal: Mês forte\n"
             "validade_risco: Sim\nvalidade_item: Perfume\nvalidade_valor: 250,00\n"
             "validade_prazo: Próximos 30 dias\n")

print("\n=== ⑤ A CHAVE NÃO É NOME — e o cliente leu a chave ===")
# 🔴 "A VALIDADE RISCO do Perfume é um alerta de que R$ 250,00 podem ser perdidos."
# `validade_risco` é o nome da chave. Ela viajava crua em DADOS DO NEGÓCIO.
# ⚠️ Segunda vez da MESMA causa: a primeira foi o `baixa_*`, que o modelo leu como
# FALTA e inverteu a decisão do Motorola G17. Renomear tratava o sintoma.
legivel = S._dados_legiveis(AROMATICA)
for chave in ("validade_risco", "validade_item", "validade_valor", "validade_prazo"):
    caso(f"⛔ a chave crua `{chave}` não chega ao modelo", chave in legivel, False)
caso("e o rótulo que o lojista viu na tela chega",
     "Produto próximo do vencimento: Perfume" in legivel, True)
caso("o valor em risco chega nomeado",
     "Valor em risco por vencimento (R$): 250,00" in legivel, True)
caso("o prazo chega nomeado",
     "Prazo do vencimento mais próximo: Próximos 30 dias" in legivel, True)

print("\n  — e as outras dez chaves estruturadas do #097, pela mesma régua —")
OUTRAS = ("falta_ocorreu: Sim\nfalta_categoria: Acessório\nfalta_canal: Loja física\n"
          "falta_item: capa de silicone\nmargem_melhor: Acessórios\nmargem_pior: Aparelhos\n"
          "encalhe_ocorreu: Sim\nencalhe_categoria: Aparelho\nencalhe_item: Motorola G17\n")
leg2 = S._dados_legiveis(OUTRAS)
for chave in ("falta_ocorreu", "falta_categoria", "falta_canal", "falta_item",
              "margem_melhor", "margem_pior", "encalhe_ocorreu", "encalhe_categoria",
              "encalhe_item"):
    caso(f"⛔ `{chave}` não vaza", chave in leg2, False)
caso("o item declarado sobrevive à troca (é dado, não chave)",
     "Motorola G17" in leg2 and "capa de silicone" in leg2, True)

print("\n  — o marcador de contrato NÃO é dado de negócio e não vai ao modelo —")
caso("⛔ `estoque_base` não chega ao modelo", "estoque_base" in legivel, False)
caso("e nem o valor dele solto", "\ntotal\n" in legivel, False)

print("\n  — ⚠️ e o payload de verdade continua INTACTO para todo parser —")
# Trocar o `dados` quebraria a precedência do #097, que existe justamente para
# distinguir chave estruturada de campo legado.
caso("o Motor continua lendo a chave original",
     S._atuais(AROMATICA).get("estoque_valor"), 20000.0)
caso("e `_texto_do_campo` também",
     S._texto_do_campo(AROMATICA, "validade_item").strip(), "Perfume")

print("\n=== ② ESTOQUE PARADO NÃO É PERDA REALIZADA ===")
# 🔴 A FRASE ERA DO PRODUTO, não do modelo. O relatório publicou "o estoque parado de
# R$ 20.000 também é um dinheiro que já foi gasto e não voltou" — VERBATIM do bloco de
# instrução da própria seção. Fiscal nenhum pegaria: o modelo estava obedecendo.
# ⚠️ A BUSCA É NAS STRINGS, NÃO NO ARQUIVO. Procurar no fonte cru acusaria o próprio
# comentário que explica a remoção — e, pior, deixaria passar texto de prompt quebrado
# em várias linhas pela concatenação, que é como quase todo bloco daqui é escrito.
# O que vai ao modelo é o valor das strings; é nele que se confere.
import ast
_FONTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor.py")
fonte = open(_FONTE, encoding="utf-8").read()
LITERAIS = " ".join(
    n.value for n in ast.walk(ast.parse(fonte))
    if isinstance(n, ast.Constant) and isinstance(n.value, str))

caso("⛔ a frase saiu de TODA string do módulo",
     "já foi gasto e não voltou" in LITERAIS, False)
caso("e o lugar dela agora diz capital imobilizado",
     "capital imobilizado" in LITERAIS, True)
caso("nomeando o que É perda de verdade",
     "perda é o que venceu, estragou" in LITERAIS.lower(), True)

print("\n  — e o fiscal de retaguarda, para quando o modelo chegar lá sozinho —")
for frase, esp in [
    ("O estoque parado de R$ 20.000 também é um dinheiro que já foi gasto e não voltou.", True),
    ("Gerir o estoque parado de R$ 20.000 para evitar mais perdas.", True),
    ("O estoque encalhado de R$ 12.000 é prejuízo.", True),
    # ⚠️ O contraste que o produto PRECISA saber fazer: perda que é real passa.
    ("A validade do Perfume representa R$ 250 de perda nos próximos 30 dias.", False),
    ("Houve perda por avaria de R$ 300 no período.", False),
    ("O estoque total é de R$ 20.000, equivalente a 2 meses de venda.", False),
]:
    caso(f"{'pega' if esp else 'passa'}: {frase[:52]}",
         bool(S._ESTOQUE_COMO_PERDA.search(frase)), esp)

print("\n=== ① COMPOSIÇÃO DE CUSTO NÃO É PROVA DE PERDA ===")
# 🔴 "O dinheiro está saindo com a compra de mercadoria, que representou 75% dos
# custos." Compra ser a maior fatia do custo é o NORMAL do comércio — é assim que a
# loja tem o que vender. 75% diz PARA ONDE o dinheiro foi, não que foi mal gasto.
for frase, esp in [
    ("O dinheiro está saindo com a compra de mercadoria, que representou 75% dos custos.", True),
    ("A aquisição de mercadoria correspondeu a 60% dos custos do período.", True),
    # ⚠️ Evidência LEGÍTIMA de excesso continua passando — senão a trava calaria o
    # que o produto tem de dizer.
    ("A compra subiu 40% enquanto a venda subiu 5%.", False),
    ("Composição dos custos: R$ 30.000 foi compra de mercadoria e R$ 10.000 é custo fixo.", False),
]:
    caso(f"{'pega' if esp else 'passa'}: {frase[:52]}",
         bool(S._COMPOSICAO_COMO_PERDA.search(frase)), esp)

print("\n  — e o prompt passou a dizer isso onde a frase nascia —")
caso("o bloco da seção declara que composição não é perda",
     "COMPOSIÇÃO NÃO É PERDA" in LITERAIS, True)
caso("e nomeia o que AUTORIZA a linha (comprou mais do que vendeu)",
     "comprou mais do que vendeu" in LITERAIS, True)

print("\n=== ③ COMPRA JULGADA — a negação analítica conta igual ===")
# 🔴 O léxico cobria `desnecessárias` e deixava passar "que NÃO SÃO MAIS NECESSÁRIAS".
# Mesmo juízo, negação solta em vez de prefixada. Medido contra a frase real.
for frase, esp in [
    ("Revisar a estratégia de compras para evitar aquisição de mercadorias que não são mais necessárias", True),
    ("comprar mercadorias que não eram necessárias", True),
    ("evitar a compra de itens desnecessários", True),
    ("A compra de R$ 38.000 indica que o investimento em estoque pode não ter sido totalmente eficaz", True),
    ("Renegociar prazo de compra com o fornecedor", False),
    ("Comprou R$ 40.000 e saiu R$ 34.000 no período", False),
]:
    caso(f"{'bloqueia' if esp else 'passa'}: {frase[:52]}",
         bool(S._COMPRA_JULGADA.search(frase)), esp)

print("\n=== 🔴 `[^.]` NÃO ATRAVESSA DINHEIRO — a cegueira de TODAS as travas ===")
# `[^.]{0,80}` parece dizer "sem sair da frase" e para no PRIMEIRO ponto — inclusive o
# separador de milhar. Toda trava escrita assim ficava cega justamente nas frases com
# CIFRA, que são as que este produto escreve.
# ⚠️ Mesma classe do `\b` que virou byte 0x08 em 13/08: trava instalada, documentada,
# com teste passando — e morta na frase que importava.
caso("⛔ nenhum léxico do validador usa mais `[^.]{`",
     "[^.]{" in open(_FONTE, encoding="utf-8").read().split("_APURADO_VARIA = re.compile")[1], False)
for frase, rx, esp in [
    ("O faturamento de R$ 54.800 caiu em relação ao período anterior", "_APURADO_VARIA", True),
    ("A margem de 20,5% melhorou", "_APURADO_VARIA", True),
    ("A falta da capa de R$ 1.200 impactou as vendas", "_FALTA_IMPACTO", True),
]:
    caso(f"{rx} atravessa a cifra: {frase[:44]}",
         bool(getattr(S, rx).search(frase)), esp)

print("\n=== ④ ALVO SEM RÉGUA NÃO VIRA META ===")
# 🔴 "Estoque parado: de R$ 20.000 para R$ 10.000 — metade do estoque que você
# informou." Matemática correta, decisão nenhuma: não existe régua calibrada que
# autorize cortar 50% do estoque num ciclo. E saía por CÓDIGO, dentro da seção que
# leva o selo "apurado" — pior que o modelo escrevendo.
metas = S._bloco_metas(AROMATICA)
texto_metas = "\n".join(metas)
caso("⛔ nenhuma meta de estoque é fabricada", "stoque" in texto_metas, False)
# ⚠️ Não se procura "10.000" solto: o lucro da Aromática É 10.000 e a meta dele é
# legítima. O que não pode existir é uma meta DE ESTOQUE, de qualquer valor.
caso("⛔ e nenhuma linha diz de onde para onde o estoque deveria ir",
     any("stoque" in l for l in metas), False)
caso("as metas que NASCEM do dado continuam de pé",
     "60.000" in texto_metas, True)          # o faturamento, que é a meta declarada

print("\n=== ⑤ A AÇÃO NÃO PODE EMPOBRECER O QUE O FORMULÁRIO CONQUISTOU ===")
# 🔴 O lojista declarou item + valor + prazo, e a ação saiu "verificar a validade dos
# perfumes". O produto pediu que ele conferisse o que ele acabou de informar.
caso("o prompt proíbe mandar VERIFICAR o que já foi informado",
     "NÃO peça ao lojista para VERIFICAR" in LITERAIS, True)
# ⚠️ A frase-modelo é escrita em duas linhas concatenadas no fonte; só junta em
# tempo de execução. Conferir no arquivo daria falso negativo.
caso("e mostra a forma certa, com os três componentes",
     "priorizar o Perfume com R$ 250 em risco de validade nos próximos 30 dias" in LITERAIS, True)

print("\n=== 🔒 A NATUREZA DO ESTOQUE — total ≠ encalhado ===")
# ⚖️ Veredito do fundador: a dica pedia "o que está PARADO hoje" e a identidade do giro
# exige o TOTAL. A dica, por ser mais específica que o rótulo, é a que o lojista
# obedece. Dado coletado assim NÃO pode sustentar giro.
caso("declarado `total` é reconhecido", S._base_estoque("estoque_base: total\n"), True)
caso("ausente NÃO vira 'provavelmente total'", S._base_estoque("estoque_valor: 20.000\n"), False)
caso("qualquer outro valor também não", S._base_estoque("estoque_base: parado\n"), False)

def ciclo(base_ant, base_at):
    ant = "faturamento: 50.000\ncustos: 40.000\nlucro: 10.000\nestoque_valor: 18.000\n"
    if base_ant: ant += "estoque_base: total\n"
    at = ("faturamento: 55.000\ncustos: 42.000\nlucro: 13.000\nestoque_valor: 20.000\n"
          "compra_mercadoria: 30.000\n")
    if base_at: at += "estoque_base: total\n"
    d = ("=== ANÁLISE ANTERIOR 1 (período: Julho/2026) ===\nDADOS DAQUELA ANÁLISE:\n" + ant +
         "DECISÕES RECOMENDADAS NAQUELA ANÁLISE:\nnada\n=== DADOS ATUAIS ===\n" + at)
    _, radar = S.calcular_motor(d)
    return next((l for l in radar if "Giro do estoque" in l), None)

caso("com o critério nos DOIS períodos: o giro sai",
     "R$" in (ciclo(True, True) or ""), True)
# ⛔ A trava é retroativa por construção: análise gravada antes desta versão não traz o
# marcador, então o giro se abstém até haver duas sob o contrato novo.
caso("critério só no atual (histórico velho): abstém",
     "ainda não calculável" in (ciclo(False, True) or ""), True)
caso("critério só no anterior (app não atualizado): abstém",
     "ainda não calculável" in (ciclo(True, False) or ""), True)
caso("e a abstenção DIZ o motivo, sem adivinhar qual das pontas falhou",
     "mesmo critério" in (ciclo(False, True) or ""), True)

print("\n  — e o produto para de chamar o estoque total de 'parado' —")
ind_a, rad_a = S.calcular_motor(AROMATICA)
tudo = "\n".join(ind_a + rad_a)
caso("⛔ o rótulo 'Estoque parado' não sai mais do Motor", "Estoque parado" in tudo, False)
caso("⛔ nem em minúscula, na linha da preocupação", "o estoque parado" in tudo, False)

print(f"\n{'='*62}\n  {ok} passaram · {falhou} falharam\n{'='*62}")
sys.exit(1 if falhou else 0)
