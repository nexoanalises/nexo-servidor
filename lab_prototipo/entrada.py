# ETAPA 0 — NORMALIZAÇÃO SEMÂNTICA + FISCAL 0.
#
# A lei que este arquivo serve: NA ENTRADA, SIGNIFICADO NÃO COMPROVADO NÃO VIRA
# EVIDÊNCIA. Se o texto do lojista entrasse cru, o Motor herdaria uma premissa que
# ninguém apurou — e todo o rigor da saída estaria defendendo um castelo com a porta
# dos fundos aberta.
#
# 🔑 A FRONTEIRA DO FISCAL 0, em três níveis (#093 §2):
#     1. extração literal ......... verificável por FORMA          → é dele
#     2. classificação semântica .. por VOCABULÁRIO APROVADO       → é dele
#     3. relação semântica ........ significado ECONÔMICO entre    → NÃO é dele,
#        evidências                                                  é do Motor
#
# Ele valida SIGNIFICADO LOCAL do conteúdo. Nunca significado econômico.
# Falha do Fiscal 0 = ABSTENÇÃO, nunca chute. Abstenção é falha correta.

import re
import unicodedata

from catalogo import (
    EVENTOS_FREIO, MARCADORES_FALTA, NATUREZA, PERTENCIMENTO,
)


def canonizar(texto):
    """Minúscula, sem acento, espaços colapsados. É extração LITERAL — nível 1."""
    if texto is None:
        return ""
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


class Evidencia:
    """Uma ponta de relação, com FICHA DE PROVENIÊNCIA obrigatória.

    A confiabilidade vem da proveniência, não da natureza (v0.2 §4): calculado não é
    necessariamente mais verdadeiro, textual não é necessariamente mais fraco. Por isso
    a ficha guarda de ONDE veio, e a fórmula de força continua suspensa.
    """

    def __init__(self, campo, valor, proveniencia, origem_texto=None, vinculos=None):
        self.campo = campo
        self.valor = valor
        self.proveniencia = proveniencia          # declarado_numerico | declarado_texto | calculado
        self.origem_texto = origem_texto          # o texto cru de onde saiu, quando saiu de texto
        self.vinculos = vinculos or {}            # ex.: {"categoria": "acessorio"}
        n = NATUREZA.get(campo, {})
        self.tipo = n.get("tipo")
        self.unidade = n.get("unidade")
        self.temporal = n.get("temporal")

    def __repr__(self):
        return "<%s=%r via %s>" % (self.campo, self.valor, self.proveniencia)


class Abstencao:
    """O Fiscal 0 não normalizou. Não é erro do lojista nem do sistema: é o mecanismo
    recusando-se a inventar significado. É contabilizada, porque abstinência precisa
    ser NÚMERO e não virtude declarada (#093 §6c)."""

    def __init__(self, campo, texto, motivo):
        self.campo, self.texto, self.motivo = campo, texto, motivo

    def __repr__(self):
        return "<abstencao %s: %s>" % (self.campo, self.motivo)


def _trecho_original(texto, termo):
    """Devolve o pedaço do texto do lojista que casou com o termo declarado — com o
    acento, a caixa e a grafia dele.

    A canonização acontece só para COMPARAR. O que se guarda é o que ele escreveu:
    "FIZ LIQUIDACAO" fica "LIQUIDACAO" no registro, não vira "liquidação" à revelia.
    """
    alvo, bruto = canonizar(termo), str(texto)
    ci = canonizar(bruto)
    i = ci.find(alvo)
    if i < 0:
        return None
    # canonizar() só rebaixa caixa e remove acento combinante — o índice se preserva
    # posição a posição, então a fatia recorta o original sem deslocamento.
    return bruto[i:i + len(alvo)] if len(ci) == len(bruto) else termo


# ─────────────────────────────────────────────────────────────────────────────
# AS QUATRO PROVAS DO FISCAL 0 (#093 §3)
# ─────────────────────────────────────────────────────────────────────────────

def _prova_proveniencia(campo, bruto):
    """① PROVENIÊNCIA — de qual campo veio, e o campo é conhecido pelo contrato?"""
    if campo not in NATUREZA:
        return None, "campo fora do contrato de naturezas"
    return True, None


def _prova_tipo(campo, bruto):
    """② TIPO — o valor tem a forma que a natureza declarada exige?

    Verificação de FORMA, nível 1. O fiscal não julga se o número é plausível: isso
    seria significado econômico, e não é dele.
    """
    tipo = NATUREZA[campo]["tipo"]
    if tipo in ("monetario", "percentual"):
        if isinstance(bruto, (int, float)):
            return bruto, None
        m = re.search(r"-?\d+(?:[.,]\d+)?", str(bruto or ""))
        if not m:
            return None, "valor sem número extraível para tipo %s" % tipo
        return float(m.group(0).replace(".", "").replace(",", ".")), None
    return str(bruto or "").strip(), None


def _prova_vocabulario(campo, valor):
    """③ VOCABULÁRIO — todo significado atribuído a texto livre vem de termo APROVADO.

    Aqui mora a diferença entre normalizar e adivinhar. "capa de silicone" vira
    `∈ acessorio` porque o vínculo está declarado. "capinha" não vira nada — e o
    silêncio resultante é o comportamento correto, não uma lacuna a tapar.
    """
    if NATUREZA[campo]["tipo"] != "texto_livre":
        return {}, None

    c = canonizar(valor)
    if not c:
        return {}, "texto vazio"

    vinculos = {}

    # Evento comercial → freio classe D. Extrai o EVENTO, nunca o efeito do evento.
    #
    # ⚠️ Do mais específico para o mais genérico: rodando, "liquidação de inverno" foi
    # reconhecida como "liquidação" e a qualificação obrigatória saiu mais pobre do que
    # o lojista disse. Perder especificidade na normalização é perder para sempre.
    #
    # 🔑 NORMALIZAR NÃO É EMPOBRECER. A proveniência guarda o `trecho` exatamente como
    # o lojista escreveu, e a generalização só existe onde a apuração precisa dela: o
    # Motor casa pelo termo canônico, a auditoria confere contra a frase original.
    for termo in sorted(EVENTOS_FREIO, key=len, reverse=True):
        if canonizar(termo) in c:
            vinculos["freio"] = {
                "termo": termo,
                "qualificacao": EVENTOS_FREIO[termo],
                "trecho": _trecho_original(valor, termo),
            }
            break

    # Declaração de falta → extrai FATO e, quando o vocabulário permite, o ITEM.
    # Nunca motivo, culpa ou consequência — isso seria significado econômico.
    #
    # ⚠️ O fato de falta e a categoria do item são DOIS níveis diferentes, e separá-los
    # é o que faz a abstinência ser cirúrgica em vez de cega: "faltou produto" sustenta
    # coocorrência com fornecedor sem sustentar pertencimento a categoria nenhuma.
    if any(m in c for m in MARCADORES_FALTA):
        vinculos["fato"] = "falta"
        for termo in sorted(PERTENCIMENTO, key=len, reverse=True):
            if canonizar(termo) in c:
                vinculos["item"] = termo
                vinculos["categoria"] = PERTENCIMENTO[termo]
                # 🔑 O trecho ATÔMICO da entidade, como o lojista escreveu. É o que
                # autoriza a redação a dizer "capa de silicone" — e é só isso: o
                # campo bruto inteiro NUNCA entra como licença de redação, senão a
                # proveniência viraria túnel para reintroduzir lógica não autorizada.
                vinculos["trecho_item"] = _trecho_original(valor, termo)
                break

    if not vinculos:
        return {}, "nenhum termo do vocabulário aprovado reconhecido no texto"
    return vinculos, None


def _prova_suporte(campo, valor, vinculos):
    """④ SUPORTE — o que foi extraído está literalmente sustentado no texto de origem?

    Impede a normalização de acrescentar o que o lojista não disse. É a última prova
    justamente porque é a que pega invenção sutil.
    """
    if NATUREZA[campo]["tipo"] != "texto_livre":
        return True, None
    c = canonizar(valor)
    item = vinculos.get("item")
    if item and canonizar(item) not in c:
        return None, "item extraído não aparece no texto de origem"
    freio = vinculos.get("freio")
    if freio and canonizar(freio["termo"]) not in c:
        return None, "freio extraído não aparece no texto de origem"
    return True, None


def normalizar(campo, bruto):
    """ETAPA 0 completa. Devolve `Evidencia` ou `Abstencao` — nunca um palpite."""
    ok, motivo = _prova_proveniencia(campo, bruto)
    if not ok:
        return Abstencao(campo, bruto, motivo)

    if bruto is None or (isinstance(bruto, str) and not bruto.strip()):
        return Abstencao(campo, bruto, "campo não veio nesta análise")

    valor, motivo = _prova_tipo(campo, bruto)
    if motivo:
        return Abstencao(campo, bruto, motivo)

    vinculos, motivo = _prova_vocabulario(campo, valor)
    if motivo:
        return Abstencao(campo, bruto, motivo)

    ok, motivo = _prova_suporte(campo, valor, vinculos)
    if not ok:
        return Abstencao(campo, bruto, motivo)

    prov = ("declarado_texto" if NATUREZA[campo]["tipo"] == "texto_livre"
            else "declarado_numerico")
    return Evidencia(campo, valor, prov, origem_texto=str(bruto), vinculos=vinculos)


def normalizar_formulario(dados):
    """Roda a etapa 0 sobre o formulário inteiro. Devolve (evidencias, abstencoes)."""
    evidencias, abstencoes = {}, []
    for campo, bruto in dados.items():
        r = normalizar(campo, bruto)
        if isinstance(r, Abstencao):
            abstencoes.append(r)
        else:
            evidencias[campo] = r
    return evidencias, abstencoes
