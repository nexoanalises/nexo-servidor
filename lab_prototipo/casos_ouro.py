# CONJUNTO OURO — e ele tem DUAS colunas, não uma.
#
# Cada entrada declara o que PODE sair e o que JAMAIS pode sair. Um conjunto ouro só
# com a resposta certa não pega a família de erro que este sistema inteiro existe para
# impedir: ele aprovaria uma saída elegante e causalmente inventada.
#
#   fornecedor caiu + faltou produto
#     ✅ "a confiabilidade caiu e houve falta no mesmo período"
#     ⛔ "o fornecedor causou a falta"
#
# Cada proibição vem etiquetada com a MÉTRICA que ela alimenta, para que a falha diga
# de que tipo ela é — e a regra do #094 possa ser aplicada: falha local corrige
# implementação, falha estrutural reabre arquitetura.

CASOS = [

    # ── CLASSE 1 · relação NUMÉRICA simples ──────────────────────────────────
    {
        "nome": "varejo · desconto ↔ lucro",
        "prova": "relação numérica: proporção entre duas cifras de mesma unidade",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "R$ 6.200,00", "lucro": "8000"},
        "deve_conter": [r"6\.200", r"8\.000", r"77,5", r"representa"],
        "jamais": [
            (r"caus|porque|por isso|resultou|levou a|trouxe", "conclusao_sem_origem"),
            (r"46,7", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "varejo · desconto ↔ lucro COM FREIO",
        "prova": "o freio rebaixa a CONCLUSÃO sem tocar a evidência",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "6200", "lucro": "8000",
                  "acoes_quais": "fiz liquidação de inverno pra girar estoque"},
        "deve_conter": [r"77,5", r"você declarou uma liquidação de inverno"],
        "jamais": [
            (r"errou o preço|precificou errado", "conclusao_sem_origem"),
            (r"caus|trouxe|se paga", "conclusao_sem_origem"),
            (r"\b14\b", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },

    # ── CLASSE 2 · COOCORRÊNCIA sem causalidade ──────────────────────────────
    {
        "nome": "varejo · fornecedor ↔ falta",
        "prova": "coocorrência: evidência forte, conclusão limitada",
        "ambiente": "varejo",
        "dados": {"confiabilidade_fornecedor": "70",
                  "falta_declarada": "faltou produto na segunda quinzena"},
        "deve_conter": [r"70", r"ocorreu no mesmo período que|coincidiu"],
        "jamais": [
            (r"causou|por causa|porque|resultou em|levou a|provocou|gerou", "conclusao_sem_origem"),
            (r"culpa|responsáv", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },

    # ── CLASSE 3 · normalização SEMÂNTICA + pertencimento ────────────────────
    {
        "nome": "celular · capa ↔ acessório",
        "prova": "o elo só se forma se a etapa 0 tiver produzido o vínculo item ∈ categoria",
        "ambiente": "celular",
        # 🔴 ALINHADO AO CONTRATO REAL (#095): o formulário nunca perguntou margem
        # em percentual. Pergunta `margem_categoria` em TEXTO — e o mapa do Celular
        # sempre apontou para a relação heterogênea, texto ↔ texto por pertencimento.
        "dados": {"falta_declarada": "faltou capa de silicone",
                  "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [r"pertence a categoria", r"você declarou ter boa margem"],
        "jamais": [
            # ⚠️ A primeira versão desta linha era /caus|porque|derrub|impact/ e
            # reprovou a frase do PRÓPRIO fundador para o limite — que usa "porque"
            # para o produto explicar a si mesmo, não para atribuir causa aos dados
            # do lojista. O instrumento de medida tinha caído na armadilha que a
            # arquitetura evita: blacklist de palavra em vez de critério lógico.
            (r"causou|por causa|resultou em|levou a|trouxe|derrub|impact",
             "conclusao_sem_origem"),
            (r"maior margem|item mais lucrativo", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },

    # ── ADVERSARIAIS ─────────────────────────────────────────────────────────
    {
        "nome": "celular · 'capinha' — termo FORA do vocabulário",
        "prova": "abstinência cirúrgica: o fato de falta entra, o pertencimento não",
        "ambiente": "celular",
        "dados": {"falta_declarada": "faltou capinha", "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [],
        "jamais": [
            (r"acessório|categoria|pertence", "falso_relacionamento"),
            (r"boa margem", "conclusao_sem_origem"),
        ],
        "espera_saida": False,
        # A relação existe no mundo — "capinha" é capa. O silêncio aqui é correto E
        # é custo: entra na métrica de abstinência, que é o que torna a governança do
        # vocabulário mensurável em vez de opinativa.
        "abstinencia_legitima": True,
    },
    # ── O MESMO LIMITE, TRÊS ANÁLISES — e quem decide é a EVIDÊNCIA ──────────
    #
    # ⚖️ estado epistemológico interno ≠ obrigação de publicação em toda análise.
    # O par continua 🔵 não determinável nas três; o que muda é se ele está bloqueando
    # uma decisão que a análise de fato colocou em avaliação.
    #
    # 🔴 E a preocupação declarada é LENTE, NÃO VEREDITO: ela pode aumentar a
    # relevância editorial, nunca pode suprimir o que a evidência tornou relevante.
    {
        "nome": "celular · limite bloqueia decisão EM AVALIAÇÃO",
        "prova": "a relação formada tocou margem → o limite impede a decisão → publica",
        "ambiente": "celular",
        "preocupacao": "margem",
        "dados": {"falta_declarada": "faltou capa de silicone", "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [r"não foi possível avaliar", r"não possui margem apurada"],
        "jamais": [
            (r"você deveria ter|não informou|deixou de", "conclusao_sem_origem"),
            (r"pior que|melhor que", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "celular · o lojista disse ESTOQUE, a evidência disse MARGEM",
        "prova": "a preocupação não suprime: o limite sai porque a evidência o tornou relevante",
        "ambiente": "celular",
        "preocupacao": "estoque",
        "dados": {"falta_declarada": "faltou capa de silicone", "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        # ⚡ O caso que a correção do fundador criou. Com a preocupação como único
        # portão, esta linha estaria ausente — e o produto teria calado uma ausência
        # estrutural que impedia justamente a decisão que os dados levantaram.
        "deve_conter": [r"pertence a categoria", r"você declarou ter boa margem",
                        r"não foi possível avaliar"],
        "jamais": [
            (r"causou|por causa|resultou em|levou a", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "celular · nada em avaliação → o limite não ocupa o relatório",
        "prova": "sem relação formada, nenhum tópico está na mesa: registra e cala",
        "ambiente": "celular",
        "preocupacao": "estoque",
        "dados": {"falta_declarada": "faltou capinha", "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [],
        "jamais": [
            # Repetido todo mês sem nada ter mudado, deixaria de ser transparência e
            # viraria refrão institucional.
            (r"não foi possível avaliar", "ruido_institucional"),
            (r"não possui margem apurada", "ruido_institucional"),
        ],
        "espera_saida": False,
    },
    {
        "nome": "celular · faltou APARELHO, e a boa margem é do acessório",
        "prova": "o encontro é por CATEGORIA: cada uma carrega a sua própria declaração",
        "ambiente": "celular",
        "preocupacao": "margem",
        "dados": {"falta_declarada": "faltou aparelho",
                  "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [r"margem baixa"],
        "jamais": [
            # ⛔ A margem do acessório não pode migrar para o aparelho.
            (r"boa margem", "falso_relacionamento"),
            (r"causou|deixou de vender|perdeu", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "celular · margem declarada SEM categoria reconhecível",
        "prova": "qualificador solto não vira margem de ninguém",
        "ambiente": "celular",
        "preocupacao": "margem",
        "dados": {"falta_declarada": "faltou capa de silicone",
                  "margem_categoria": "esse ano a margem melhorou bastante"},
        "deve_conter": [],
        "jamais": [(r"pertence|boa margem|categoria acess", "falso_relacionamento")],
        "espera_saida": False,
    },
    {
        "nome": "varejo · par NÃO DECLARADO no catálogo",
        "prova": "closed-world: capacidade ↔ perdas_validade não é reprovado — não existe",
        "ambiente": "varejo",
        "dados": {"capacidade": "76", "perdas_validade": "4200"},
        "deve_conter": [],
        "jamais": [
            (r"76", "falso_relacionamento"),
            (r"4\.?200", "falso_relacionamento"),
            (r"capacidade", "falso_relacionamento"),
        ],
        "espera_saida": False,
    },
    {
        "nome": "varejo · uma ponta em branco",
        "prova": "⚪ não formada, caso B — silêncio, não declaração de lacuna",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "6200", "lucro": ""},
        "deve_conter": [],
        "jamais": [
            (r"não informou|faltou preencher|campo vazio|em branco", "conclusao_sem_origem"),
            (r"6\.?200", "conclusao_sem_origem"),
        ],
        "espera_saida": False,
    },
    {
        "nome": "varejo · texto do lojista mal escrito",
        "prova": "a etapa 0 aguenta acento errado e caixa alta sem mudar o veredito",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "R$6.200", "lucro": "R$ 8.000,00",
                  "acoes_quais": "FIZ LIQUIDACAO pq o estoque tava parado"},
        "deve_conter": [r"77,5", r"você declarou uma liquidação"],
        "jamais": [(r"caus|porque|pq o|parado", "conclusao_sem_origem")],
        "espera_saida": True,
    },

    # ═════════════════════════════════════════════════════════════════════════
    # AMPLIAÇÃO — sondas de risco, todas dentro do vocabulário já declarado.
    # Nenhum par novo, nenhum elo novo: o que muda é o que o lojista escreve e
    # o que os números fazem nas bordas.
    # ═════════════════════════════════════════════════════════════════════════

    {
        "nome": "varejo · o LOJISTA escreve a causa no texto",
        "prova": "a causalidade dita pelo cliente não vira premissa do Motor",
        "ambiente": "varejo",
        "dados": {"confiabilidade_fornecedor": "70",
                  "falta_declarada": "faltou produto porque o fornecedor atrasou a entrega"},
        # ⚡ A sonda mais importante da ampliação: o texto do lojista CONTÉM a
        # causa. O Fiscal 0 extrai o fato de falta e nada mais — atribuir causa é
        # significado econômico, e significado econômico não é dele.
        "deve_conter": [r"70"],
        "jamais": [
            (r"porque|atrasou|atraso", "conclusao_sem_origem"),
            (r"causou|por causa|responsáv|culpa", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "varejo · DOIS freios no mesmo campo",
        "prova": "dois ou mais freios = interseção de restrições, sem ranking (v0.2 §6)",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "6200", "lucro": "8000",
                  "acoes_quais": "fiz liquidação de inverno e queima de estoque"},
        "deve_conter": [r"77,5", r"liquidação de inverno", r"queima de estoque"],
        "jamais": [(r"causou|por isso|resultou", "conclusao_sem_origem")],
        "espera_saida": True,
    },
    {
        "nome": "celular · película — outro item do vocabulário",
        "prova": "o pertencimento não é caso especial da capa",
        "ambiente": "celular",
        "dados": {"falta_declarada": "faltou película", "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [r"pertence a categoria", r"você declarou ter boa margem"],
        "jamais": [(r"capa|silicone", "conclusao_sem_origem")],
        "espera_saida": True,
    },
    {
        "nome": "celular · 'CAPA DE SILICONI' — erro de grafia no item",
        "prova": "degradação graciosa: casa pelo termo declarado mais amplo",
        "ambiente": "celular",
        "dados": {"falta_declarada": "FALTOU CAPA DE SILICONI", "margem_categoria": "acessórios deixam boa margem; aparelho novo quase não deixa"},
        "deve_conter": [r"pertence a categoria"],
        "jamais": [(r"siliconi", "conclusao_sem_origem")],
        "espera_saida": True,
    },
    {
        "nome": "varejo · LUCRO ZERO — a proporção não existe",
        "prova": "sem valor derivado, a conclusão que o elo autoriza não existe: silêncio",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "6200", "lucro": "0"},
        "deve_conter": [],
        "jamais": [
            (r"None|nan|infinit", "conclusao_sem_origem"),
            (r"6\.?200", "conclusao_sem_origem"),
        ],
        "espera_saida": False,
    },
    {
        "nome": "varejo · centavos",
        "prova": "a aritmética do elo não arredonda para um número mais bonito",
        "ambiente": "varejo",
        "dados": {"descontos_valor": "R$ 6.234,56", "lucro": "R$ 8.000,00"},
        "deve_conter": [r"6\.234", r"77,9"],
        "jamais": [(r"77,5|78", "conclusao_sem_origem")],
        "espera_saida": True,
    },
    {
        "nome": "varejo · número solto dentro do texto livre",
        "prova": "número que o lojista cita de passagem não vira fato citável",
        "ambiente": "varejo",
        "dados": {"confiabilidade_fornecedor": "70",
                  "falta_declarada": "faltou produto, perdi uns 300 reais acho"},
        "deve_conter": [r"70"],
        "jamais": [(r"300", "conclusao_sem_origem")],
        "espera_saida": True,
    },
    {
        "nome": "varejo · confiabilidade em 100%",
        "prova": "a borda superior não muda a força da conclusão: segue coocorrência",
        "ambiente": "varejo",
        "dados": {"confiabilidade_fornecedor": "100",
                  "falta_declarada": "faltou produto"},
        "deve_conter": [r"100"],
        "jamais": [
            (r"excelente|ótim|perfeit|confiável", "conclusao_sem_origem"),
            (r"apesar|mesmo assim|ainda assim", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "celular · item conhecido, margem ausente",
        "prova": "⚪ não formada, caso B — uma ponta não veio",
        "ambiente": "celular",
        "dados": {"falta_declarada": "faltou carregador"},
        "deve_conter": [],
        "jamais": [(r"categoria|pertence|boa margem", "falso_relacionamento")],
        "espera_saida": False,
    },
]
