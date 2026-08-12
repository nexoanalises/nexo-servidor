# ETAPAS 1 a 8 — O MOTOR. Ele APURA; não interpreta.
#
# Entra evidência já normalizada e provada pelo Fiscal 0; sai CONCLUSÃO ATÔMICA, com
# origem, verbo autorizado, qualificação obrigatória e operadores de composição.
#
# 🔑 A unidade de geração e de fiscalização é a mesma, e ela NASCE AQUI — antes de
# qualquer texto existir. É isso que dissolve a recursão do Fiscal 10: ninguém precisa
# reconstruir depois o que já nasceu decomposto (#093 §7).
#
# ⛔ O Motor nunca produz causalidade. Não porque haja uma regra proibindo — porque
# nenhum elo do catálogo tem "causal" como força de conclusão, e a conclusão só pode
# ser dita com os verbos do seu elo.

from catalogo import (
    ELOS, INEXISTENTES_NO_PRODUTO, LIMITES_DECLARADOS, OPERADORES, PARES,
)


class Conclusao:
    """Afirmação atômica. É o contrato entre o Motor e a linguagem.

    Tudo o que a redação pode dizer está aqui dentro; tudo o que ela disser a mais é
    conclusão sem origem.
    """

    def __init__(self, cid, par, elo, estado, fatos, valor_derivado=None,
                 qualificacoes=(), urgencia="nao_apurada"):
        self.id = cid
        self.par = par
        self.elo = elo
        self.estado = estado                                  # formada | enfraquecida | contradita
        self.fatos = fatos                                    # {campo: valor} — os únicos números citáveis
        self.valor_derivado = valor_derivado                  # o único número NOVO que pode aparecer
        self.qualificacoes = tuple(qualificacoes)             # texto que a redação é OBRIGADA a preservar
        self.urgencia = urgencia
        self.forca_conclusao = ELOS[elo]["forca_conclusao"]
        self.verbos = ELOS[elo]["verbos"]
        self.operadores = OPERADORES[self.forca_conclusao]

    def numeros_permitidos(self):
        """Os únicos números que podem aparecer na redação desta unidade."""
        nums = [v for v in self.fatos.values() if isinstance(v, (int, float))]
        if self.valor_derivado is not None:
            nums.append(self.valor_derivado)
        return nums

    def __repr__(self):
        return "<%s %s %s>" % (self.id, self.estado, self.par)


class Limite:
    """🔵 NÃO DETERMINÁVEL — e isto é ENTREGA, não lacuna.

    "não encontrei relação" ≠ "não existe informação suficiente no produto para que
    essa relação possa ser conhecida". A primeira é ausência de resultado; a segunda é
    resultado. E o limite é sempre do PRODUTO: o lojista não deixou de responder — o
    produto não pergunta.

    ⚡ O limite carrega TEXTO DECLARADO, não redigido: não passa pelo redator nem pelo
    Fiscal 10, porque não há origem de que ele possa ser infiel. Ele é a frase.

    ⚖️ E `publicar` separa duas coisas que pareciam uma: o estado é registrado SEMPRE;
    a publicação depende de o limite estar impedindo uma conclusão relevante HOJE.
    A ontologia registra tudo; a experiência publica o que acrescenta à decisão.
    """

    def __init__(self, cid, par, texto, publicar, motivo_publicacao):
        self.id, self.par, self.texto = cid, par, texto
        self.publicar = publicar
        self.motivo_publicacao = motivo_publicacao
        self.estado = "nao_determinavel"

    def __repr__(self):
        return "<%s limite %s>" % (self.id, self.par)


class Silencio:
    """⚪ NÃO FORMADA — os dois casos. Nada é publicado; o motivo fica no registro
    interno, para que a abstinência possa ser MEDIDA."""

    def __init__(self, par, caso, motivo):
        self.par, self.caso, self.motivo = par, caso, motivo
        self.estado = "nao_formada"

    def __repr__(self):
        return "<silencio %s (%s)>" % (self.par, self.caso)


def _freios(evidencias):
    """Colhe as qualificações obrigatórias impostas por freios classe D.

    Dois ou mais freios = INTERSEÇÃO DE RESTRIÇÕES (v0.2 etapa 6). Sem ranking, sem
    "o mais forte vence": cada freio ACRESCENTA uma restrição, e a conclusão precisa
    satisfazer todas.
    """
    qualificacoes = []
    for ev in evidencias.values():
        freio = ev.vinculos.get("freio")
        if freio:
            qualificacoes.append(freio["qualificacao"])
    return qualificacoes


def _elo_satisfeito(decl, evidencias):
    """ETAPA 3 — o elo precisa ser DECLARADO **e** SATISFEITO pelos valores desta
    análise. Declarado mas não satisfeito → não formada."""
    exige = decl.get("exige_vinculo")
    if not exige:
        return True
    campo, categoria = exige
    ev = evidencias.get(campo)
    return bool(ev and ev.vinculos.get("categoria") == categoria)


def _urgencia(decl, evidencias):
    """ETAPA 5 — urgência derivada de natureza temporal normalizada.
    ⛔ Sem natureza temporal, `nao_apurada`. Nunca "média"."""
    temporais = {evidencias[c].temporal for c in decl["par"] if c in evidencias}
    if "prazo" in temporais:
        return "prazo_curto"
    if temporais == {"periodo"}:
        return "estado_estavel"
    return "nao_apurada"


def _derivar(decl, evidencias):
    """A única aritmética do protótipo, e ela é do elo — não do redator."""
    a, b = decl["par"]
    if decl["operacao"] == "proporcao":
        va, vb = evidencias[a].valor, evidencias[b].valor
        if not vb:
            return None
        return round(va / vb * 100, 1)
    return None


def avaliar(ambiente, evidencias, abstencoes=(), preocupacao=None):
    """ETAPAS 1–8. Devolve (conclusoes, limites, silencios).

    `conclusoes` atravessam a fronteira para a linguagem — serão redigidas e
    fiscalizadas. `limites` já SÃO texto declarado e vão direto para a composição,
    e cada um decide sozinho se ocupa o relatório: `preocupacao` é o que o lojista
    declarou estar querendo decidir, e é o único critério de publicação.
    """
    conclusoes, limites, silencios = [], [], []
    campos_abstidos = {a.campo for a in abstencoes}

    for i, decl in enumerate(PARES.get(ambiente, []), start=1):
        cid = "C%02d" % (i * 7)          # id estável e legível no relatório de falhas
        a, b = decl["par"]

        # ETAPA 4 · ordem corrigida na v0.2: estrutural ANTES de circunstancial.
        estruturais = [c for c in (a, b) if c in INEXISTENTES_NO_PRODUTO]
        if estruturais:
            declarado = LIMITES_DECLARADOS.get(decl["par"])
            if declarado:
                relevante = preocupacao in declarado["relevante_para"]
                limites.append(Limite(
                    cid, decl["par"], declarado["texto"], publicar=relevante,
                    motivo_publicacao=("impede a decisão declarada (%s)" % preocupacao
                                       if relevante else
                                       "registrado: não bloqueia a decisão desta análise"),
                ))
            else:
                # Sem frase declarada, o produto NÃO improvisa a declaração do próprio
                # limite: cala. Declarar um limite com texto inventado seria a mesma
                # invenção que o resto da arquitetura impede, só que mais educada.
                silencios.append(Silencio(decl["par"], "C_limite_sem_frase_declarada",
                                          INEXISTENTES_NO_PRODUTO[estruturais[0]]))
            continue

        faltando = [c for c in (a, b) if c not in evidencias]
        if faltando:
            # Caso B da taxonomia — ausência CIRCUNSTANCIAL: a ponta existe no
            # produto e não veio nesta análise. Distingue-se se ela não veio em
            # branco ou se veio e o Fiscal 0 se absteve, porque só a segunda conta
            # como preço da disciplina na métrica de abstinência.
            caso = ("B_fiscal0_absteve" if faltando[0] in campos_abstidos
                    else "B_dado_ausente")
            silencios.append(Silencio(decl["par"], caso,
                                      "ponta ausente nesta análise: %s" % faltando[0]))
            continue

        if not _elo_satisfeito(decl, evidencias):
            silencios.append(Silencio(decl["par"], "A_elo_nao_satisfeito",
                                      "elo declarado, não satisfeito pelos valores"))
            continue

        qualificacoes = _freios(evidencias)
        estado = "enfraquecida" if qualificacoes else "formada"

        conclusoes.append(Conclusao(
            cid, decl["par"], decl["elo"], estado,
            fatos={a: evidencias[a].valor, b: evidencias[b].valor},
            valor_derivado=_derivar(decl, evidencias),
            qualificacoes=qualificacoes,
            urgencia=_urgencia(decl, evidencias),
        ))

    return conclusoes, limites, silencios
