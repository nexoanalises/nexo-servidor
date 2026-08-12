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
        "dados": {"falta_declarada": "faltou capa de silicone",
                  "margem_acessorios": "45"},
        "deve_conter": [r"45", r"pertence a|categoria"],
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
        "dados": {"falta_declarada": "faltou capinha", "margem_acessorios": "45"},
        "deve_conter": [],
        "jamais": [
            (r"acessório|categoria|pertence", "falso_relacionamento"),
            (r"45", "conclusao_sem_origem"),
        ],
        "espera_saida": False,
        # A relação existe no mundo — "capinha" é capa. O silêncio aqui é correto E
        # é custo: entra na métrica de abstinência, que é o que torna a governança do
        # vocabulário mensurável em vez de opinativa.
        "abstinencia_legitima": True,
    },
    # ── O MESMO LIMITE, DUAS ANÁLISES — e o que muda é a PERGUNTA do lojista ──
    #
    # ⚖️ estado epistemológico interno ≠ obrigação de publicação em toda análise.
    # O par continua 🔵 não determinável nas duas; o que decide a publicação é ele
    # estar ou não impedindo a decisão que importa HOJE.
    {
        "nome": "celular · limite RELEVANTE — a pergunta é sobre margem",
        "prova": "o limite impede a decisão declarada → publica, e isso é entrega",
        "ambiente": "celular",
        "preocupacao": "margem",
        "dados": {"falta_declarada": "faltou capa de silicone", "margem_acessorios": "45"},
        "deve_conter": [r"não foi possível avaliar", r"não possui margem apurada"],
        "jamais": [
            (r"você deveria ter|não informou|deixou de", "conclusao_sem_origem"),
            (r"pior que|melhor que", "conclusao_sem_origem"),
        ],
        "espera_saida": True,
    },
    {
        "nome": "celular · MESMO limite, pergunta sobre estoque",
        "prova": "não bloqueia a decisão desta análise → registra, não ocupa o relatório",
        "ambiente": "celular",
        "preocupacao": "estoque",
        "dados": {"falta_declarada": "faltou capa de silicone", "margem_acessorios": "45"},
        "deve_conter": [r"45", r"pertence a|categoria"],
        "jamais": [
            # Repetido todo mês sem nada ter mudado, deixaria de ser transparência e
            # viraria refrão institucional.
            (r"não foi possível avaliar", "ruido_institucional"),
            (r"não possui margem apurada", "ruido_institucional"),
        ],
        "espera_saida": True,
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
]
