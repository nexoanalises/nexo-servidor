# CATÁLOGO CLOSED-WORLD do protótipo vertical (#094).
#
# Este arquivo é a fronteira do mundo conhecido. O mecanismo avalia APENAS o que está
# declarado aqui — e "relação não declarada" não significa "relação inexistente no
# mundo", significa "fora do conhecimento atual do NEXO Análise" (v0.2 §5).
#
#   "Prefiro uma cegueira conhecida a uma criatividade causal desconhecida."
#
# 🔴 A trava que este arquivo carrega é a mais importante de todas: NENHUM conjunto de
# verbos aqui contém causalidade. Ela não é proibida em lugar nenhum do código — ela
# simplesmente não existe como opção. É a diferença entre barrar uma conclusão e
# torná-la inexpressável (#092), e só a segunda sobrevive a um modelo generativo.

# ─────────────────────────────────────────────────────────────────────────────
# VOCABULÁRIO DO FISCAL 0 — o que o normalizador tem permissão de reconhecer.
#
# Nada aprende sozinho em produção: o modelo pode PROPOR termo novo, nunca PROMOVER
# (#093 §6b). Termo fora daqui → o Fiscal 0 se abstém, e abstenção é falha CORRETA.
# ─────────────────────────────────────────────────────────────────────────────

# Vínculo de pertencimento: item declarado pelo lojista → categoria do produto.
# A chave é a forma JÁ canonizada (minúscula, sem acento); o valor é a categoria.
PERTENCIMENTO = {
    "capa de silicone": "acessorio",
    "capa": "acessorio",
    "pelicula": "acessorio",
    "carregador": "acessorio",
    "fone": "acessorio",
    # "capinha" NÃO está aqui de propósito: é o caso ouro que mede abstinência.
}

# Eventos comerciais que o lojista pode declarar em texto livre e que funcionam como
# FREIO (classe D) — oferecem explicação alternativa e rebaixam a conclusão.
EVENTOS_FREIO = {
    "liquidacao": "você declarou uma liquidação",
    "liquidacao de inverno": "você declarou uma liquidação de inverno",
    "queima de estoque": "você declarou uma queima de estoque",
    "promocao": "você declarou uma promoção",
}

# Declarações de falta. O Fiscal 0 só extrai FATO DE FALTA + ITEM; nunca extrai motivo,
# culpa ou consequência — isso seria significado econômico, e significado econômico é
# do Motor, não do Fiscal 0 (#093 §2, os três níveis de normalização).
MARCADORES_FALTA = ("faltou", "faltaram", "ficou sem", "acabou", "em falta")


# ─────────────────────────────────────────────────────────────────────────────
# NATUREZA DAS EVIDÊNCIAS — vem do contrato, não da inferência.
# ─────────────────────────────────────────────────────────────────────────────

NATUREZA = {
    "descontos_valor":            {"tipo": "monetario", "unidade": "BRL", "temporal": "periodo"},
    "lucro":                      {"tipo": "monetario", "unidade": "BRL", "temporal": "periodo"},
    "acoes_quais":                {"tipo": "texto_livre", "unidade": None, "temporal": "periodo"},
    "confiabilidade_fornecedor":  {"tipo": "percentual", "unidade": "pct", "temporal": "serie"},
    "falta_declarada":            {"tipo": "texto_livre", "unidade": None, "temporal": "periodo"},
    "margem_acessorios":          {"tipo": "percentual", "unidade": "pct", "temporal": "periodo"},
    "capacidade":                 {"tipo": "percentual", "unidade": "pct", "temporal": "periodo"},
    "perdas_validade":            {"tipo": "monetario", "unidade": "BRL", "temporal": "prazo"},
}

# Campos que o produto NÃO POSSUI. A ausência aqui é ESTRUTURAL, não circunstancial —
# e o produto declara o limite em vez de calar (estado 🔵 não determinável).
# ⚠️ O limite é do PRODUTO, nunca do lojista: ele não deixou de responder, o produto
# não pergunta.
INEXISTENTES_NO_PRODUTO = {
    "margem_venda_aparelho": "o produto não possui margem apurada por operação",
    "margem_assistencia":    "o produto não possui margem apurada por operação",
    "recorrencia_cliente":   "o produto não mede retorno de cliente",
}


# ─────────────────────────────────────────────────────────────────────────────
# ELOS LEGÍTIMOS — extraídos dos cinco mapas, não inventados (TAXONOMIA §1).
#
# Cada elo carrega o TETO da conclusão: a força de conclusão que ele autoriza e os
# verbos com que ela pode ser dita. O teto é do elo, não do redator.
# ─────────────────────────────────────────────────────────────────────────────

ELOS = {
    "mesma_unidade_periodo": {
        "descricao": "mesma unidade e mesmo período",
        "forca_conclusao": "proporcao",
        "verbos": ("representa", "equivale a", "corresponde a"),
    },
    "mesma_grandeza_angulos": {
        "descricao": "mesma grandeza sob ângulos diferentes",
        "forca_conclusao": "comparacao_ritmo",
        "verbos": ("avança mais devagar que", "acompanha", "diverge de"),
    },
    "nomeia_classifica": {
        "descricao": "uma nomeia ou classifica entidade da outra",
        "forca_conclusao": "pertencimento",
        "verbos": ("pertence a", "está na categoria", "classifica-se como"),
    },
    "coocorrencia_plausivel": {
        "descricao": "coocorrência + plausibilidade econômica conhecida",
        "forca_conclusao": "coocorrencia",
        "verbos": ("ocorreu no mesmo período que", "coincidiu com", "aconteceu junto com"),
    },
    "qualifica_risco": {
        "descricao": "uma qualifica o risco da outra",
        "forca_conclusao": "endereco",
        "verbos": ("incide sobre", "diz respeito a"),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# PARES DECLARADOS POR AMBIENTE — o mecanismo avalia SÓ estes.
#
# `toca` são os TÓPICOS DE DECISÃO que o par coloca em avaliação quando a relação se
# forma. É por aqui que a evidência ganha voz sobre a publicação de um limite: se a
# análise formou uma relação que toca `margem`, a decisão de margem está na mesa —
# tenha o lojista marcado "margem" ou não.
#
# `capacidade ↔ perdas_validade` não aparece aqui, e é de propósito: estão no mesmo
# formulário, no mesmo período, e não têm relação nenhuma. O par não é reprovado
# depois — ele NÃO EXISTE (v0.1 §0).
# ─────────────────────────────────────────────────────────────────────────────

PARES = {
    "varejo": [
        {"par": ("descontos_valor", "lucro"),
         "elo": "mesma_unidade_periodo",
         "classe": "custo_sobre_resultado",
         "operacao": "proporcao",
         "toca": {"rentabilidade"}},

        {"par": ("confiabilidade_fornecedor", "falta_declarada"),
         "elo": "coocorrencia_plausivel",
         "classe": "cadeia_fornecimento",
         "operacao": "coocorrencia",
         "toca": {"fornecimento"}},
    ],
    "celular": [
        {"par": ("falta_declarada", "margem_acessorios"),
         "elo": "nomeia_classifica",
         "classe": "ruptura_por_categoria",
         "operacao": "pertencimento",
         # A ruptura por categoria fala de margem: quando ela se forma, a decisão de
         # margem entra em avaliação — e é isso que dá voz à evidência.
         "toca": {"margem", "ruptura"},
         # 🆕 v0.2 etapa 3: o elo precisa ser DECLARADO **e** SATISFEITO. Aqui só se
         # satisfaz se a etapa 0 tiver produzido o vínculo item ∈ categoria.
         "exige_vinculo": ("falta_declarada", "acessorio")},

        {"par": ("margem_venda_aparelho", "margem_assistencia"),
         "elo": "mesma_grandeza_angulos",
         "classe": "margem_por_operacao",
         "operacao": "comparacao_ritmo",
         "toca": {"margem"}},
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# LIMITES DECLARADOS — 🔵 não determinável.
#
# 🔑 O protótipo rodando revelou que eu tinha errado a natureza disto: mandei o limite
# ser REDIGIDO e o Fiscal 10 o reprovou — inclusive pela palavra "porque", que na frase
# do fundador não é raciocínio causal sobre os dados do lojista, é o produto explicando
# o próprio limite.
#
# A correção não é afrouxar o fiscal. É reconhecer que o limite NÃO É TEXTO GERADO:
# é texto DECLARADO. Não passa pelo redator nem pelo Fiscal 10 porque não existe nada
# de que ele possa ser infiel — ele não foi produzido a partir de uma conclusão, ele
# É a frase. Mesmo movimento de sempre: em vez de fiscalizar melhor, remover o que não
# precisava ser fiscalizado.
#
# ⚠️ E o limite é do PRODUTO, nunca do lojista: a frase jamais insinua que ele deveria
# ter informado algo. Ele não deixou de responder — o produto não pergunta.
# ─────────────────────────────────────────────────────────────────────────────

# ⚖️ E A PUBLICAÇÃO NÃO SEGUE A EXISTÊNCIA — segue a RELEVÂNCIA DECISÓRIA:
#
#     estado epistemológico interno  ≠  obrigação de publicação em toda análise
#
# ### Um limite estrutural é publicado quando IMPEDE UMA CONCLUSÃO RELEVANTE naquela
# ### análise — não simplesmente porque existe.
#
# Internamente `não determinável` é registrado SEMPRE; externamente ele só ocupa o
# relatório quando explica por que uma decisão que importa hoje não pode ser tomada.
# Repetido todo mês sem nada ter mudado, deixaria de ser transparência e viraria
# refrão institucional — um relatório que passa o tempo contando o que não sabe.
#
# ⚠️ E a regra NÃO é "mostrar uma vez e nunca mais": é relevância, não contagem. Se a
# mesma pergunta voltar em outro mês, o limite volta com ela.
#
# 🔴 O PORTÃO NÃO É A `preocupacao`, E ISSO FOI CORREÇÃO DO FUNDADOR:
#
#     A preocupação declarada é LENTE, não VEREDITO.
#
# Se o lojista marca `estoque` e a evidência ativa uma decisão de margem, um limite que
# bloqueia justamente essa decisão PRECISA poder aparecer. Senão a preocupação passaria
# a SUPRIMIR uma conclusão que a evidência tornou relevante — e o produto ficaria refém
# do que o lojista achava que era o problema dele.
#
#     ### O cliente pode dizer "estoque". A evidência pode dizer "margem".
#
# `bloqueia` .......... tópicos de decisão que este limite impede. Portão PRINCIPAL:
#                       publica quando um deles está EM AVALIAÇÃO no Motor.
# `relevante_para` .... a preocupação declarada AUMENTA a relevância editorial —
#                       nunca é o único portão, e nunca fecha o outro.
#
# Nada aqui é inferido do texto: relevância adivinhada seria a mesma invenção que o
# resto da arquitetura impede, só que na camada de edição.

LIMITES_DECLARADOS = {
    ("margem_venda_aparelho", "margem_assistencia"): {
        "texto": "Não foi possível avaliar a margem entre venda de aparelhos e "
                 "assistência porque o produto não possui margem apurada para essas "
                 "duas operações.",
        "bloqueia": {"margem"},
        "relevante_para": {"margem", "rentabilidade", "onde_investir"},
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# OPERADORES DE COMPOSIÇÃO — o buraco que o terceiro ataque encontrou, fechado aqui.
#
# A composição acontece DEPOIS do último fiscal. A saída não foi abrir um Fiscal 11
# (ele teria de ler o parágrafo e reconstruir a lógica, recriando a recursão que o §5
# dissolveu): a composição RECEBE os operadores autorizados e é estruturalmente
# incapaz de usar outro.
#
# 🔴 Note o que NÃO existe em nenhuma linha abaixo: "porque", "por isso", "levou a",
# "resultou em", "trouxe". Não há blacklist — o modelo contornaria com sinônimo. Há
# ausência: o conector causal nunca entra no conjunto de opções.
# ─────────────────────────────────────────────────────────────────────────────

OPERADORES = {
    "proporcao":         ("e", "no mesmo período", "sendo que"),
    "comparacao_ritmo":  ("e", "enquanto"),
    "coocorrencia":      ("e", "no mesmo período", "ao mesmo tempo", "enquanto"),
    "pertencimento":     ("e", "que"),
    "endereco":          ("e", "sendo que"),
}


# ─────────────────────────────────────────────────────────────────────────────
# LÉXICO LÓGICO GLOBAL — o universo de expressões que o Fiscal 10 sabe classificar.
#
# Ele NÃO é uma lista de proibições: é o conjunto que o fiscal reconhece. Toda
# expressão lógica encontrada numa redação precisa estar entre as AUTORIZADAS daquela
# unidade. Expressão que o fiscal não sabe classificar → ele se abstém → reprova.
# Abster para o lado seguro é o mesmo movimento do Fiscal 0.
# ─────────────────────────────────────────────────────────────────────────────

# Rótulo PUBLICÁVEL — como o campo se chama para o lojista.
#
# 🔧 A rodada real mostrou que eu entregava ao redator a representação INTERNA do
# Motor: `descontos_valor = 6200.0`. O modelo devolveu "o descontos_valor de 6200.0" —
# e eu o reprovava por devolver justamente o que eu tinha mandado.
#
#     O redator recebe a representação PUBLICÁVEL da unidade.
#     O Motor segue com IDs e nomes canônicos por baixo.
ROTULO_PUBLICO = {
    "descontos_valor":           "Descontos concedidos",
    "lucro":                     "Lucro",
    "acoes_quais":               "Ações declaradas",
    "confiabilidade_fornecedor": "Confiabilidade dos fornecedores",
    "falta_declarada":           "Falta declarada",
    "margem_acessorios":         "Margem de acessórios",
    "capacidade":                "Capacidade",
    "perdas_validade":           "Perdas por validade",
    "margem_venda_aparelho":     "Margem na venda de aparelhos",
    "margem_assistencia":        "Margem na assistência",
}


def formatar(valor, campo=None):
    """Formata número no padrão brasileiro, com a unidade do campo quando houver.

    🔧 O float americano `6200.0` chegava cru ao redator. Aqui ele vira `R$ 6.200`.
    """
    if not isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    if isinstance(valor, int):
        n = "{:,}".format(valor).replace(",", ".")
    else:
        n = "{:,.1f}".format(valor).replace(",", "X").replace(".", ",").replace("X", ".")
    unidade = NATUREZA.get(campo, {}).get("unidade")
    if unidade == "BRL":
        return "R$ %s" % n
    if unidade == "pct":
        return "%s%%" % n
    return n


# Rótulos humanos dos campos. É vocabulário DECLARADO: a redação só pode nomear a
# evidência com o rótulo que o catálogo dá a ela.
ROTULOS = {
    "descontos_valor":           ("desconto", "descontos"),
    "lucro":                     ("lucro",),
    "acoes_quais":               ("ação", "ações"),
    "confiabilidade_fornecedor": ("confiabilidade", "fornecedor", "fornecedores"),
    "falta_declarada":           ("falta", "faltou"),
    "margem_acessorios":         ("margem", "acessório", "acessórios", "categoria"),
    "capacidade":                ("capacidade",),
    "perdas_validade":           ("perda", "perdas", "validade"),
    "margem_venda_aparelho":     ("margem", "venda", "aparelho", "aparelhos"),
    "margem_assistencia":        ("margem", "assistência"),
}

# Marcadores de PROVENIÊNCIA. A redação pode dizer de onde a evidência veio, porque a
# proveniência é parte da unidade — o Fiscal 0 a exige na ficha. Foi o protótipo
# rodando que mostrou a falta: "a falta DECLARADA" era reprovada por excesso, e
# "declarada" não é invenção, é a origem do dado dita em português.
MARCADORES_PROVENIENCIA = frozenset("""
declarado declarada declarados declaradas apurado apurada apurados apuradas
calculado calculada calculados calculadas informado informada
""".split())

# Palavras funcionais — artigos, preposições, conectivos neutros. Não carregam
# lógica; existem para a frase ser lida por um humano. Declaradas, como tudo aqui.
PALAVRAS_FUNCIONAIS = frozenset("""
a o as os um uma uns umas de do da dos das em no na nos nas por para com sem sobre
entre ao aos à às e ou que se é foi era são eram ser está estão houve há seu sua
seus suas este esta esse essa isso mais menos até desde não período mesmo mesma
juntos junta juntas r$ reais % pontos percentuais você lojista item itens
""".split())

# ⚠️ O DEFEITO 6, e ele é a raiz dos falsos positivos da rodada 2: o fiscal exigia a
# FORMA do verbo, não o VERBO. O modelo escreveu "os descontos **equivalem a** 77,5%
# do lucro" — que é `equivale a` com concordância de plural — e foi reprovado por
# "nenhum verbo autorizado aparece". Exigir o singular com sujeito plural obrigaria o
# produto a escrever português errado.
#
#     ### Conjugar não é trocar de verbo.
#
# A saída NÃO é stemming nem heurística de radical: continuaria sendo adivinhação, e
# poderia casar palavra sem parentesco. As formas são DECLARADAS, como todo o resto —
# terceira pessoa do singular e do plural, que é como um fato se enuncia.

EXPRESSOES_LOGICAS = {
    # canônica ................ (classe, formas aceitas)
    "representa":                   ("proporcao", ("representa", "representam")),
    "equivale a":                   ("proporcao", ("equivale a", "equivalem a")),
    "corresponde a":                ("proporcao", ("corresponde a", "correspondem a")),

    "avança mais devagar que":      ("comparacao_ritmo", ("avança mais devagar que",
                                                          "avançam mais devagar que")),
    "acompanha":                    ("comparacao_ritmo", ("acompanha", "acompanham")),
    "diverge de":                   ("comparacao_ritmo", ("diverge de", "divergem de")),

    "pertence a":                   ("pertencimento", ("pertence a", "pertencem a")),
    "está na categoria":            ("pertencimento", ("está na categoria",
                                                       "estão na categoria")),
    "classifica-se como":           ("pertencimento", ("classifica-se como",
                                                       "classificam-se como")),

    "ocorreu no mesmo período que": ("coocorrencia", ("ocorreu no mesmo período que",
                                                      "ocorreram no mesmo período que")),
    "coincidiu com":                ("coocorrencia", ("coincidiu com", "coincidiram com")),
    "aconteceu junto com":          ("coocorrencia", ("aconteceu junto com",
                                                      "aconteceram junto com")),

    "incide sobre":                 ("endereco", ("incide sobre", "incidem sobre")),
    "diz respeito a":               ("endereco", ("diz respeito a", "dizem respeito a")),

    # ⛔ CAUSALIDADE — reconhecida para poder ser REPROVADA, jamais autorizada.
    # Nenhum elo tem força de conclusão "causal", então nenhuma unidade pode
    # autorizá-las: aparecer é reprovar. E aqui as formas servem ao DIAGNÓSTICO —
    # a segurança não depende desta lista estar completa, porque expressão que o
    # fiscal não reconhece já cai na checagem de excesso, que se abstém para o
    # lado seguro.
    "causou":       ("causal", ("causou", "causaram")),
    "provocou":     ("causal", ("provocou", "provocaram")),
    "gerou":        ("causal", ("gerou", "geraram")),
    "levou a":      ("causal", ("levou a", "levaram a")),
    "resultou em":  ("causal", ("resultou em", "resultaram em")),
    "trouxe":       ("causal", ("trouxe", "trouxeram")),
    "fez com que":  ("causal", ("fez com que", "fizeram com que")),
    "impactou":     ("causal", ("impactou", "impactaram")),
    "se paga":      ("causal", ("se paga", "se pagam")),
    "porque":       ("causal", ("porque",)),
    "por isso":     ("causal", ("por isso",)),
    "por causa":    ("causal", ("por causa",)),
    "graças a":     ("causal", ("graças a",)),
    "devido a":     ("causal", ("devido a",)),
    "em função de": ("causal", ("em função de",)),
}

# Derivados — declaração única acima, nenhuma lista paralela para envelhecer sozinha.
LEXICO_LOGICO = {forma: classe
                 for _c, (classe, formas) in EXPRESSOES_LOGICAS.items()
                 for forma in formas}

FORMAS_DO_VERBO = {canonica: formas
                   for canonica, (_cl, formas) in EXPRESSOES_LOGICAS.items()}


def formas_aceitas(verbos):
    """Todas as formas declaradas dos verbos autorizados de uma unidade."""
    aceitas = set()
    for v in verbos:
        aceitas.update(FORMAS_DO_VERBO.get(v, (v,)))
    return aceitas


# ─────────────────────────────────────────────────────────────────────────────
# LÉXICO SEMÂNTICO — o que a checagem ④ passa a fiscalizar.
#
# 🔑 A CALIBRAGEM QUE A RODADA 4 JUSTIFICOU, e ela troca a pergunta do fiscal:
#
#     ❌ antes:  "existe alguma palavra que não estava declarada?"   → excesso LEXICAL
#     ✅ agora:  "foi introduzido CONTEÚDO que ninguém autorizou?"   → excesso SEMÂNTICO
#
#     ### Palavra nova ≠ conteúdo novo.
#
# `totalizam` em "os descontos, que totalizam R$ 6.200" não acrescenta fato, número,
# intensidade, conceito, causa nem conselho: é realização linguística de um valor que
# a unidade já carrega. Reprovar isso transforma o redator num template ruim — e aí
# não haveria razão para manter um modelo generativo na etapa 10.
#
# ⚠️ E ISTO NÃO É A BLACKLIST QUE O #092 REJEITOU. Aquela listava FRASES PROIBIDAS de
# uma ideia — e um sinônimo a contornava. Esta é um inventário de CLASSES DE CONTEÚDO
# que exigem autorização: um sinônimo de "significativa" pertence à mesma classe e cai
# na mesma regra. A autorização vem da unidade, não da lista.
#
# 🔻 E O PREÇO, declarado: sem a cobertura total, um termo causal que não esteja
# declarado em lugar nenhum deixa de ser barrado por ④ (a ② segue barrando os
# declarados). Por isso a novidade lexical não desaparece — ela passa a ser MEDIDA:
# o registro devolve `termos_novos`, e é por ali que a governança do vocabulário
# (#093 §6b) decide o que promover. Mede-se o que se deixou de barrar.

_CLASSES_SEMANTICAS = {
    # ① INTENSIDADE E MATERIALIDADE — grau que o Motor não apurou
    "intensidade": """
        significativa significativo significativas significativos expressiva expressivo
        considerável considerable substancial substancial grande grandes enorme enormes
        alta alto altas altos elevada elevado elevadas elevados baixa baixo baixas baixos
        pequena pequeno pequenas pequenos mínima mínimo forte fortes fraca fraco
        preocupante preocupantes crítica crítico críticas críticos grave graves séria sério
        relevante relevantes importante importantes principal principais maior menor
        excessiva excessivo exagerada exagerado ótima ótimo excelente ruim péssima péssimo
        saudável saudáveis ideal apenas somente só bastante muito pouco demais
    """,
    # ② CONCEITO ECONÔMICO — outro conceito, ainda que o número esteja certo
    "conceito_economico": """
        margem margens lucro lucros prejuízo prejuízos receita receitas faturamento
        custo custos despesa despesas rentabilidade giro ticket capital caixa fluxo
        estoque estoques ruptura rupturas inadimplência sazonalidade demanda
        concorrência concorrente precificação preço preços desconto descontos
        confiabilidade falta faltas acessório acessórios categoria categorias
        fornecedor fornecedores validade capacidade
    """,
    # ③ CONSELHO E MODALIDADE — decisão que a etapa 10 não tem
    "conselho": """
        deve deveria devem deveriam precisa precisam necessário necessária recomenda
        recomendo recomendamos recomendável sugere sugiro sugerimos considere avalie
        reduza aumente corte negocie renegocie revise priorize invista foque
        convém cabe urgente imediato aconselho procure tente busque
    """,
    # ④ PREVISÃO — o futuro nunca foi apurado
    "previsao": """
        tende tendem tenderá projeta projetam espera-se estimativa estimado previsão
        provavelmente possivelmente futuro futura próxima próximo continuará
    """,
}

LEXICO_SEMANTICO = {t: classe
                    for classe, blob in _CLASSES_SEMANTICAS.items()
                    for t in blob.split()}

# Marcadores que sustentam a ATRIBUIÇÃO AO LOJISTA numa qualificação. O que a
# qualificação protege não é a frase: é que o evento continue sendo declaração DELE,
# nunca fato apurado pelo NEXO.
MARCADORES_ATRIBUICAO = ("declarou", "declarado", "declarada", "declarados", "declaradas")
