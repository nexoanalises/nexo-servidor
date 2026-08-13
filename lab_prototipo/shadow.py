# SHADOW MODE — o mecanismo novo observa a análise real e NÃO a toca.
#
#   /analisar → fluxo atual ─────────────────→ relatório do cliente (intocado)
#                   │
#                   └── cópia dos dados → Motor novo → Fiscal 0 → relações
#                                       → decisões → unidades → modelo → Fiscal 10
#                                       → LOG SOMENTE
#
# 🔑 A VIRADA QUE ESTE ARQUIVO SERVE:
#
#     Até a rodada 5 provamos que o mecanismo obedece à sua gramática.
#     Agora precisamos descobrir se essa gramática enxerga o negócio real
#     sem ficar cega.
#
# O laboratório protege regressão. O shadow descobre realidade. São instrumentos
# diferentes e nenhum substitui o outro.
#
# ⛔ TRÊS TRAVAS NÃO NEGOCIÁVEIS:
#   ① nada aqui pode alterar uma palavra do relatório do cliente;
#   ② nada aqui pode derrubar a /analisar — exceção morre no registro;
#   ③ a fase do MODELO custa a mesma cota diária do cliente pagante, então ela
#      nasce DESLIGADA e é amostrada. A espinha determinística custa zero token.
#
# 🔒 PRIVACIDADE: o registro guarda o que o Fiscal 0 NORMALIZOU (evento, item,
# categoria) e o que o Motor derivou — nunca a prosa do lojista. O texto livre dele
# não vai para log nenhum.

from catalogo import PARES
from entrada import normalizar_formulario
from laboratorio import prompt_da_unidade
from motor import avaliar
from saida import fiscal_10

# ─────────────────────────────────────────────────────────────────────────────
# A PONTE COM O FORMULÁRIO REAL — declarada, campo a campo.
#
# 🔴 E ela já revelou o primeiro achado do shadow, antes de qualquer execução:
# o par `falta_declarada ↔ margem_acessorios` do Celular foi desenhado sobre um
# campo que O PRODUTO NÃO TEM. O formulário pergunta `margem_categoria` em TEXTO
# LIVRE ("acessório e conserto deixam margem; o aparelho novo quase não deixa"),
# não um percentual por categoria. A relação de pertencimento, como está declarada
# no catálogo, não tem como se formar em produção.
#
# Isso não se conserta aqui e não se esconde: fica registrado como ausência
# estrutural, e é decisão do fundador se o caminho é apurar a margem por categoria
# ou redesenhar o elo para trabalhar com a declaração textual.
# ─────────────────────────────────────────────────────────────────────────────

MAPA_SEGMENTO = {
    "Loja / Varejo e Moda":  "varejo",
    "Celular e Acessórios":  "celular",
    # Pet Shop, Perfumaria e Multicanal ainda não têm pares declarados no catálogo
    # do protótipo. Ausência conhecida, medida — não improvisada.
}

MAPA_CAMPOS = {
    "varejo": {
        "desconto_valor": "descontos_valor",
        "lucro":          "lucro",
        "acoes_quais":    "acoes_quais",
        "fornecedores":   "confiabilidade_fornecedor",
        "o_que_faltou":   "falta_declarada",
    },
    "celular": {
        "o_que_faltou":   "falta_declarada",
        "acoes_quais":    "acoes_quais",
        "lucro":          "lucro",
    },
}

SEM_CORRESPONDENTE = {
    "celular": {
        "margem_acessorios":
            "o formulário pergunta `margem_categoria` em TEXTO, não percentual por "
            "categoria — o elo de pertencimento não tem como se formar",
    },
}


def _fmt_br(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return "{:,}".format(v).replace(",", ".")
    return "{:,.1f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def observar(segmento, brutos, relatorio="", chamar=None, preocupacao=None):
    """Roda o mecanismo novo sobre os MESMOS dados e devolve o registro.

    `chamar` é opcional: sem ele, roda só a espinha determinística — custo zero de
    cota, e ainda assim responde relações formadas, abstinências, limites e recall.
    """
    ambiente = MAPA_SEGMENTO.get(segmento)
    reg = {"segmento": segmento, "ambiente": ambiente, "unidades": [],
           "abstencoes": [], "silencios": [], "limites": [], "erros": [],
           "campos_ausentes_no_produto": [], "divergencias": []}

    if not ambiente:
        reg["motivo"] = "segmento sem pares declarados no catálogo"
        return reg

    for campo, motivo in SEM_CORRESPONDENTE.get(ambiente, {}).items():
        reg["campos_ausentes_no_produto"].append({"campo": campo, "motivo": motivo})

    mapa = MAPA_CAMPOS[ambiente]
    traduzidos = {destino: brutos[origem]
                  for origem, destino in mapa.items()
                  if brutos.get(origem) not in (None, "")}
    reg["campos_lidos"] = sorted(traduzidos)

    evidencias, abstencoes = normalizar_formulario(traduzidos)
    conclusoes, limites, silencios = avaliar(
        ambiente, evidencias, abstencoes, preocupacao)

    reg["abstencoes"] = [{"campo": a.campo, "motivo": a.motivo} for a in abstencoes]
    reg["silencios"] = [{"par": list(s.par), "caso": s.caso} for s in silencios]
    reg["limites"] = [{"par": list(l.par), "publicaria": l.publicar,
                       "motivo": l.motivo_publicacao} for l in limites]
    reg["pares_declarados"] = len(PARES.get(ambiente, []))

    for u in conclusoes:
        item = {"id": u.id, "par": list(u.par), "elo": u.elo, "estado": u.estado,
                "forca_conclusao": u.forca_conclusao,
                "valor_derivado": u.valor_derivado,
                "qualificacoes": list(u.qualificacoes)}

        # DIVERGÊNCIA — o Motor novo derivou um número que o relatório atual não cita?
        # É o sinal mais barato e mais direto de "o atual disse X, o novo sustentaria Y".
        if u.valor_derivado is not None and relatorio:
            n = _fmt_br(u.valor_derivado)
            if n and n not in relatorio:
                reg["divergencias"].append(
                    {"id": u.id, "derivado": n,
                     "obs": "o Motor novo derivou este valor; o relatório atual não o cita"})

        if chamar is not None:
            try:
                texto = (chamar(prompt_da_unidade(u)) or "").strip()
                v = fiscal_10(u, texto)
                item["redacao"] = texto
                item["aprovado"] = v.aprovado
                item["falhas"] = [{"checagem": c, "detalhe": d} for c, d in v.falhas]
                item["termos_novos"] = v.termos_novos
            except Exception as e:                    # noqa: BLE001 — nunca derruba
                reg["erros"].append({"id": u.id, "erro": "%s: %s" % (type(e).__name__, e)})
        reg["unidades"].append(item)

    return reg


def resumo(reg):
    """Linha única para o log do Railway — o que dá para ler numa varredura."""
    if not reg.get("ambiente"):
        return "SHADOW|%s|sem-catalogo" % reg.get("segmento", "?")
    us = reg["unidades"]
    aprov = sum(1 for u in us if u.get("aprovado"))
    com_modelo = sum(1 for u in us if "aprovado" in u)
    return ("SHADOW|%s|pares=%d|unidades=%d|aprovadas=%d/%d|silencios=%d"
            "|abstencoes=%d|limites_pub=%d|divergencias=%d|erros=%d"
            % (reg["ambiente"], reg.get("pares_declarados", 0), len(us),
               aprov, com_modelo, len(reg["silencios"]), len(reg["abstencoes"]),
               sum(1 for l in reg["limites"] if l["publicaria"]),
               len(reg["divergencias"]), len(reg["erros"])))


def detalhe(reg):
    """Bloco legível abaixo do resumo. Só conteúdo NORMALIZADO — nunca a prosa."""
    if not reg.get("ambiente"):
        return ["  motivo: %s" % reg.get("motivo", "")]
    linhas = ["  campos lidos: %s" % (", ".join(reg.get("campos_lidos", [])) or "—")]
    for c in reg["campos_ausentes_no_produto"]:
        linhas.append("  🔴 campo ausente no produto · %s — %s" % (c["campo"], c["motivo"]))
    for a in reg["abstencoes"]:
        linhas.append("  ⏸️  Fiscal 0 absteve-se · %s — %s" % (a["campo"], a["motivo"]))
    for s in reg["silencios"]:
        linhas.append("  ⚪ silêncio · %s ↔ %s (%s)" % (s["par"][0], s["par"][1], s["caso"]))
    for l in reg["limites"]:
        linhas.append("  %s limite · %s ↔ %s — %s"
                      % ("🔵" if l["publicaria"] else "🗄️", l["par"][0], l["par"][1],
                         l["motivo"]))
    for u in reg["unidades"]:
        linhas.append("  ▸ %s %s ↔ %s [%s/%s] derivado=%s"
                      % (u["id"], u["par"][0], u["par"][1], u["elo"], u["estado"],
                         u["valor_derivado"]))
        if u.get("qualificacoes"):
            linhas.append("      qualificações: %s" % " · ".join(u["qualificacoes"]))
        if "aprovado" in u:
            linhas.append("      %s %s" % ("✅" if u["aprovado"] else "⛔", u.get("redacao", "")))
            for f in u.get("falhas", ()):
                linhas.append("      └─ [%s] %s" % (f["checagem"], f["detalhe"]))
            if u.get("termos_novos"):
                linhas.append("      · novidade lexical: %s" % ", ".join(u["termos_novos"]))
    for d in reg["divergencias"]:
        linhas.append("  ⚖️ divergência · %s derivou %s e o relatório atual não cita"
                      % (d["id"], d["derivado"]))
    for e in reg["erros"]:
        linhas.append("  ⚠️ erro · %s: %s" % (e["id"], e["erro"]))
    return linhas
