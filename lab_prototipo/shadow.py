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
        "o_que_faltou":     "falta_declarada",
        # 🔴 O ALINHAMENTO QUE O SHADOW EXIGIU (#095): o campo real é este, em texto.
        "margem_categoria": "margem_categoria",
        "acoes_quais":      "acoes_quais",
        "lucro":            "lucro",
    },
}

# 🟢 RESOLVIDO. O par do Celular passou a usar `margem_categoria` — o campo que o
# formulário realmente coleta. Era divergência entre o protótipo e o contrato real,
# não necessidade nova do produto: NENHUM campo foi criado.
SEM_CORRESPONDENTE = {}


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


# ─────────────────────────────────────────────────────────────────────────────
# JANELA DE OBSERVAÇÃO — o registro SANEADO que a /laboratorio devolve.
#
# ⚠️ E o nome importa: é **janela**, não registro oficial. Vive em memória, some em
# restart ou deploy, e se o Railway rodar mais de uma instância ela vê só as análises
# que passaram pelo processo que respondeu. Para a fase de shadow isso basta —
# acrescentar banco ou Redis agora seria infraestrutura demais antes de sabermos se
# o shadow produz informação útil.
#
# 🔒 O QUE NUNCA ENTRA: prosa do lojista, payload do formulário, nome de negócio.
# Nem em trecho. O `trecho` atômico — "acessórios deixam boa margem" — é literalmente
# a frase dele, então a janela guarda a CLASSE (margem_alta) e a categoria, não o
# texto. E a redação do modelo fica de fora: o que sobrevive é o veredito e a falha,
# que nomeiam o termo problemático sem carregar a frase inteira.
#
# O detalhe completo continua no log do Railway, para quem tiver acesso a ele.
# ─────────────────────────────────────────────────────────────────────────────

def sanear(reg):
    """Devolve a versão da observação que pode sair pela rota. Só isto sai."""
    limpo = {
        "ambiente": reg.get("ambiente"),
        "segmento_conhecido": bool(reg.get("ambiente")),
        "pares_declarados": reg.get("pares_declarados", 0),
        "campos_lidos": reg.get("campos_lidos", []),
        "abstencoes": [a["campo"] for a in reg.get("abstencoes", [])],
        "silencios": [{"par": s["par"], "caso": s["caso"]}
                      for s in reg.get("silencios", [])],
        "limites": [{"par": l["par"], "publicaria": l["publicaria"],
                     "motivo": l["motivo"]} for l in reg.get("limites", [])],
        "divergencias": [{"id": d["id"], "derivado": d["derivado"]}
                         for d in reg.get("divergencias", [])],
        "erros": len(reg.get("erros", [])),
        "unidades": [],
    }
    for u in reg.get("unidades", []):
        item = {"id": u["id"], "par": u["par"], "elo": u["elo"],
                "estado": u["estado"], "forca_conclusao": u["forca_conclusao"],
                "valor_derivado": u["valor_derivado"],
                "tem_qualificacao": bool(u.get("qualificacoes"))}
        if "aprovado" in u:
            item["aprovado"] = u["aprovado"]
            item["falhas"] = [f["checagem"] for f in u.get("falhas", ())]
            item["termos_novos"] = u.get("termos_novos", [])
        limpo["unidades"].append(item)
    return limpo


def agregar(janela):
    """Métricas da janela inteira — é por elas que o portão do #095 se lê."""
    t = {"observacoes": len(janela), "por_ambiente": {}, "unidades": 0,
         "aprovadas": 0, "reprovadas": 0, "silencios": 0, "abstencoes": 0,
         "limites_publicados": 0, "limites_registrados": 0, "divergencias": 0,
         "erros": 0, "sem_catalogo": 0, "termos_novos": {}}
    for reg in janela:
        amb = reg.get("ambiente") or "(sem catálogo)"
        t["por_ambiente"][amb] = t["por_ambiente"].get(amb, 0) + 1
        if not reg.get("segmento_conhecido"):
            t["sem_catalogo"] += 1
        t["silencios"] += len(reg.get("silencios", []))
        t["abstencoes"] += len(reg.get("abstencoes", []))
        t["divergencias"] += len(reg.get("divergencias", []))
        t["erros"] += reg.get("erros", 0)
        for l in reg.get("limites", []):
            t["limites_publicados" if l["publicaria"] else "limites_registrados"] += 1
        for u in reg.get("unidades", []):
            t["unidades"] += 1
            if "aprovado" in u:
                t["aprovadas" if u["aprovado"] else "reprovadas"] += 1
            for termo in u.get("termos_novos", ()):
                t["termos_novos"][termo] = t["termos_novos"].get(termo, 0) + 1
    t["termos_novos"] = dict(sorted(t["termos_novos"].items(), key=lambda kv: -kv[1]))
    return t
