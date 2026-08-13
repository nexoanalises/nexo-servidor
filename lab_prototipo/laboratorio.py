# O TERCEIRO REDATOR — MODELO REAL, uma unidade por vez.
#
# É o portão que faltava: até aqui provamos que a arquitetura barra os erros que
# CONSEGUIMOS NOMEAR. Aqui ela encontra linguagem livre.
#
# ⚠️ Este módulo não chama ninguém. Recebe `chamar(prompt)` de fora, porque a chave da
# Groq vive só nas Variables do Railway (#043) e nunca deve existir em máquina local.
# Assim o laboratório roda com modelo real no servidor e com modelo falso aqui, sem
# uma linha diferente entre os dois.
#
# 🔑 O QUE ESTE TESTE PROCURA — as seis perguntas do fundador, e nenhuma delas é
# "o modelo escreve bonito":
#
#     ① introduz fatos que não recebeu?                    → checagem NÚMERO / EXCESSO
#     ② troca um verbo lógico por outro mais forte?        → checagem VERBO
#     ③ transforma coexistência em causalidade?            → VERBO, classe causal
#     ④ perde qualificações obrigatórias?                  → checagem QUALIFICAÇÃO
#     ⑤ acrescenta conselho onde deveria apenas redigir?   → EXCESSO + rótulo conselho
#     ⑥ o Fiscal 10 está matando linguagem humana FIEL?    → reprovas SÓ por excesso
#
# ⑥ é a mais importante e é a razão de não ter mexido na checagem de excesso antes de
# rodar: ajustá-la agora seria arquitetura por antecipação. O laboratório separa as
# reprovas em que o único problema foi cobertura léxica — essas são as candidatas a
# "frase fiel barrada", e é sobre elas, e só sobre elas, que a calibragem se decide.

from casos_ouro import CASOS
from catalogo import FORMAS_DO_VERBO, ROTULO_PUBLICO, formatar
from entrada import normalizar_formulario
from motor import avaliar
from saida import fiscal_10

# Verbos de aconselhamento. Não é uma trava — a reprova, quando acontece, já veio das
# checagens normais. É RÓTULO DE DIAGNÓSTICO: serve para o registro dizer que tipo de
# desvio o modelo teve, em vez de só dizer que teve.
LEXICO_CONSELHO = frozenset("""
deve deveria recomendo recomendamos sugiro sugerimos considere avalie reduza aumente
corte negocie renegocie revise priorize invista foque precisa aconselho ideal melhor
vale conviria procure tente busque
""".split())


def prompt_da_unidade(unidade):
    """ETAPA 10 — o prompt entrega a unidade e NADA mais.

    Sem evidências soltas, sem contexto do formulário, sem outras conclusões. O modelo
    não recebe material para raciocinar porque não é dele que se quer raciocínio: a
    lógica já foi produzida pelo Motor, e a única tarefa é dizê-la em português.
    """
    fatos = "\n".join("  %s: %s" % (rotulo, valor)
                      for rotulo, valor in unidade.publicavel())
    qualif = ("\nQUALIFICAÇÕES QUE A FRASE É OBRIGADA A PRESERVAR, na íntegra:\n"
              + "\n".join("  - %s" % q for q in unidade.qualificacoes)
              if unidade.qualificacoes else "")

    return (
        "Escreva UMA frase em português do Brasil, para o dono de uma loja.\n"
        "\n"
        "FATOS (nenhum outro número existe):\n"
        "%s\n"
        "\n"
        "RELAÇÃO PERMITIDA:\n"
        "  %s\n"
        "\n"
        "VERBOS PERMITIDOS (use exatamente um deles): %s\n"
        "%s\n"
        "\n"
        "REGRAS:\n"
        "- não acrescente nenhum número que não esteja acima;\n"
        "- não afirme causa, consequência, culpa ou previsão;\n"
        "- não qualifique intensidade, gravidade ou importância;\n"
        "- não dê conselho, recomendação ou próximo passo;\n"
        "- não escreva nada além desta única frase."
        % (fatos, _relacao_publicavel(unidade), " · ".join(unidade.verbos), qualif)
    )


def _relacao_publicavel(unidade):
    """A relação autorizada dita em português — e SÓ com vocabulário declarado.

    🔧 Defeito 5. O prompt antigo inventava a própria redação: mandava `proporcao`,
    depois "equivalem a" (forma que a lista não declarava) e "categoria **cuja**
    margem" — e o fiscal barrava tudo isso. Punir o redator por devolver o que EU
    entreguei contaminou três rodadas de medição.

    Agora o prompt usa o verbo canônico do elo e os rótulos do catálogo. Nada aqui
    nasce fora do que já está declarado.
    """
    a, b = unidade.par
    ra = ROTULO_PUBLICO.get(a, a).lower()
    rb = ROTULO_PUBLICO.get(b, b).lower()
    fa = unidade.semantica.get(a, {}).get("publicavel", "")
    fb = unidade.semantica.get(b, {}).get("publicavel", "")
    verbo = _concordar(unidade.verbos[0], ra)

    if unidade.forca_conclusao == "proporcao":
        return "%s %s %s do %s" % (ra, verbo, formatar(unidade.valor_derivado) + "%", rb)
    if unidade.forca_conclusao == "coocorrencia":
        return "%s %s %s de %s" % (fb, _concordar(unidade.verbos[0], fb), ra, fa)
    if unidade.forca_conclusao == "pertencimento":
        return "%s %s uma categoria com %s de %s" % (fa, _concordar(unidade.verbos[0], fa),
                                                     rb, fb)
    return "%s %s %s" % (ra, verbo, rb)


def _concordar(verbo, sujeito):
    """Escolhe a forma DECLARADA que concorda com o sujeito.

    ⚠️ É gramática, não semântica: as duas formas já estão no catálogo e ambas são
    aceitas pelo Fiscal 10. Isto existe só para o prompt não induzir o modelo a
    escrever errado — um prompt ungramatical produz redação ungramatical.
    """
    formas = sorted(FORMAS_DO_VERBO.get(verbo, (verbo,)))
    plural = sujeito.strip().split()[0].endswith("s") if sujeito.strip() else False
    if len(formas) < 2:
        return verbo
    curta, longa = sorted(formas, key=len)[:2]
    return longa if plural else curta


def _classificar(veredito):
    """Traduz as falhas para as perguntas do fundador."""
    checagens = {c for c, _ in veredito.falhas}
    detalhes = " ".join(d for _, d in veredito.falhas).lower()
    achados = []
    if "numero" in checagens:
        achados.append("①_fato_nao_recebido")
    if "verbo" in checagens and "causal" in detalhes:
        achados.append("③_coexistencia_virou_causa")
    elif "verbo" in checagens:
        achados.append("②_verbo_trocado")
    if "qualificacao" in checagens:
        achados.append("④_qualificacao_perdida")
    if any(p in LEXICO_CONSELHO for p in veredito.texto.lower().split()):
        achados.append("⑤_conselho_dentro_da_unidade")
    # ⑥ — o único problema foi cobertura léxica: candidata a frase FIEL barrada.
    if checagens == {"excesso"}:
        achados.append("⑥_so_excesso_candidata_a_calibragem")
    return achados


def rodar_laboratorio(chamar, casos=None, exigir_cobertura=True):
    """Roda casos ouro contra o modelo real. Devolve REGISTRO — não relatório.

    ⛔ Sem PDF, sem histórico, sem banco, sem tocar o app. A saída existe para ser
    lida por nós, não entregue a cliente nenhum.
    """
    casos = casos if casos is not None else CASOS
    registro = {"unidades": [], "totais": {}, "erros": []}
    contagem = {}

    for caso in casos:
        evidencias, abstencoes = normalizar_formulario(caso["dados"])
        conclusoes, _limites, _sil = avaliar(
            caso["ambiente"], evidencias, abstencoes, caso.get("preocupacao"))

        for unidade in conclusoes:
            prompt = prompt_da_unidade(unidade)
            try:
                texto = (chamar(prompt) or "").strip()
            except Exception as e:                      # noqa: BLE001 — registra, não derruba
                registro["erros"].append({"caso": caso["nome"], "unidade": unidade.id,
                                          "erro": "%s: %s" % (type(e).__name__, e)})
                continue

            v = fiscal_10(unidade, texto, exigir_cobertura=exigir_cobertura)
            achados = [] if v.aprovado else _classificar(v)
            for a in achados:
                contagem[a] = contagem.get(a, 0) + 1

            registro["unidades"].append({
                "caso": caso["nome"],
                "unidade": unidade.id,
                "elo": unidade.elo,
                "forca_conclusao": unidade.forca_conclusao,
                "verbos_autorizados": list(unidade.verbos),
                "numeros_permitidos": unidade.numeros_permitidos(),
                "termos_permitidos": sorted(unidade.termos_permitidos()),
                "qualificacoes": list(unidade.qualificacoes),
                "prompt": prompt,
                "redacao": texto,
                "aprovado": v.aprovado,
                "falhas": [{"checagem": c, "detalhe": d} for c, d in v.falhas],
                "achados": achados,
            })

    us = registro["unidades"]
    aprovadas = sum(1 for u in us if u["aprovado"])
    registro["totais"] = {
        "unidades": len(us),
        "aprovadas": aprovadas,
        "reprovadas": len(us) - aprovadas,
        "por_achado": contagem,
        # A leitura que decide a calibragem: destas reprovas, quantas foram só por
        # cobertura léxica — ou seja, quantas podem ser linguagem fiel barrada.
        "candidatas_a_calibragem": contagem.get("⑥_so_excesso_candidata_a_calibragem", 0),
    }
    return registro


def imprimir(registro):
    """Formato de leitura humana do registro. Usado no terminal e no log do Railway."""
    linhas = ["═" * 78, "LABORATÓRIO · MODELO REAL, UMA UNIDADE POR VEZ", "═" * 78]
    for u in registro["unidades"]:
        linhas.append("\n%s %s · %s [%s]"
                      % ("✅" if u["aprovado"] else "⛔", u["unidade"], u["caso"], u["elo"]))
        linhas.append("   redação: %s" % u["redacao"])
        for f in u["falhas"]:
            linhas.append("   └─ [%s] %s" % (f["checagem"], f["detalhe"]))
        if u["achados"]:
            linhas.append("   🔎 %s" % " · ".join(u["achados"]))
    t = registro["totais"]
    linhas += ["\n" + "═" * 78, "TOTAIS", "═" * 78,
               "  unidades ................. %d" % t.get("unidades", 0),
               "  aprovadas pelo Fiscal 10 . %d" % t.get("aprovadas", 0),
               "  reprovadas ............... %d" % t.get("reprovadas", 0)]
    for achado, n in sorted(t.get("por_achado", {}).items()):
        linhas.append("  %-40s %d" % (achado, n))
    if registro["erros"]:
        linhas.append("  ⚠️ erros de chamada ....... %d" % len(registro["erros"]))
    return "\n".join(linhas)
