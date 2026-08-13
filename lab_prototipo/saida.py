# ETAPAS 9 e 10 + FISCAL 10 + COMPOSIÇÃO.
#
# A lei que este arquivo serve: NA SAÍDA, LÓGICA NÃO FORNECIDA PELO MECANISMO NÃO PODE
# NASCER NA LINGUAGEM.
#
# 🔑 O FLUXO CORRIGIDO — e note que não há decomposição em lugar nenhum:
#
#     unidade atômica de origem  (C17, vinda do Motor)
#          ↓  redação DAQUELA unidade, uma por vez
#     FISCAL 10 compara redação × origem
#          ↓  unidades aprovadas
#     COMPOSIÇÃO ordena e conecta — com operadores que RECEBEU
#          ↓
#     parágrafo humano
#
# "Esta afirmação tem origem?" deixou de ser checagem: é verdadeira POR CONSTRUÇÃO,
# porque a redação partiu da origem. O que sobra é fidelidade — número, verbo,
# qualificação e excesso.

import re
import unicodedata

from catalogo import (
    LEXICO_LOGICO, MARCADORES_PROVENIENCIA, PALAVRAS_FUNCIONAIS, ROTULOS,
    ROTULO_PUBLICO, formas_aceitas,
)
from motor import Conclusao


def _canon(t):
    t = unicodedata.normalize("NFKD", str(t))
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _numeros(texto):
    """Todo número citado na redação, normalizado para float.

    🔧 BUG QUE A RODADA REAL EXPÔS, e ele cegou o fiscal inteiro: o padrão antigo
    lia `8000.0` como **8000 e 0**, e `77.5` como **77 e 5** — depois acusava o
    modelo de citar números que não existiam. Seis das sete reprovas da primeira
    rodada eram este defeito, não comportamento do modelo.

    A desambiguação do ponto é por FORMA, não por chute:
        1.234  → milhar  (exatamente 3 dígitos depois do ponto)
        77.5   → decimal (1 ou 2 dígitos)
        6.200,50 → vírgula manda: pontos viram milhar
    """
    achados = []
    for m in re.finditer(r"\d[\d.]*(?:,\d+)?", texto):
        bruto = m.group(0).rstrip(".")
        if "," in bruto:
            bruto = bruto.replace(".", "").replace(",", ".")
        elif re.match(r"^\d{1,3}(?:\.\d{3})+$", bruto):
            bruto = bruto.replace(".", "")
        elif not re.match(r"^\d+(?:\.\d{1,2})?$", bruto):
            bruto = bruto.replace(".", "")
        try:
            achados.append(float(bruto))
        except ValueError:
            continue
    return achados


# ─────────────────────────────────────────────────────────────────────────────
# ETAPA 10 — OS REDATORES. Redigem UMA unidade. Não raciocinam.
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v):
    """Formata no padrão brasileiro, com separador de milhar.

    Rodando, "R$ 6200" reprovou o caso ouro que pedia "R$ 6.200" — e a lição não é
    sobre estética: o número que o lojista reconhece é o número que ele confere.
    """
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return "{:,}".format(v).replace(",", ".")
    return "{:,.1f}".format(v).replace(",", "X").replace(".", ",").replace("X", ".")


def redator_gabarito(unidade):
    """Redação determinística a partir da origem. Serve para provar a ESPINHA:
    se o caminho inteiro está de pé, o gabarito atravessa os fiscais."""
    a, b = unidade.par
    verbo = unidade.verbos[0]
    ra, rb = ROTULOS[a][0], ROTULOS[b][0]
    va, vb = unidade.fatos[a], unidade.fatos[b]

    if unidade.forca_conclusao == "proporcao":
        frase = ("o %s de R$ %s %s %s%% do %s de R$ %s"
                 % (ra, _fmt(va), verbo, _fmt(unidade.valor_derivado), rb, _fmt(vb)))
    elif unidade.forca_conclusao == "coocorrencia":
        frase = ("a %s de %s%% %s a %s declarada" % (ra, _fmt(va), verbo, rb))
    elif unidade.forca_conclusao == "pertencimento":
        frase = ("o item da %s declarada %s uma categoria com %s de %s%%"
                 % (ra, verbo, rb, _fmt(vb)))
    else:
        frase = ("%s %s %s" % (ra, verbo, rb))

    for q in unidade.qualificacoes:
        frase = "%s, e %s" % (frase, q)
    return frase


def redator_adversario(unidade):
    """Escreve DE PROPÓSITO o que a arquitetura existe para impedir.

    Não é um redator ruim: é o teste. Um conjunto ouro que só contém a resposta certa
    não pega a família de erro que este sistema inteiro existe para bloquear — por
    isso cada caso tem duas colunas, o que pode sair e o que JAMAIS pode sair.
    """
    a, b = unidade.par
    ra, rb = ROTULOS[a][0], ROTULOS[b][0]
    va, vb = unidade.fatos[a], unidade.fatos[b]
    if unidade.forca_conclusao == "coocorrencia":
        return "a queda da %s do fornecedor causou a %s de produtos" % (ra, rb)
    if unidade.forca_conclusao == "proporcao":
        # O meu próprio erro da v0.1, reproduzido: verbo causal, número de outra
        # conclusão e uma afirmação que nenhuma etapa entregou.
        return ("a liquidação trouxe 14%% mais clientes e o %s custou 46,7%% do %s; "
                "ela se paga se eles voltarem" % (ra, rb))
    return "a falta de capas derrubou seu lucro em R$ 3.000"


# ─────────────────────────────────────────────────────────────────────────────
# FISCAL 10 — compara redação × origem. Nunca decompõe.
# ─────────────────────────────────────────────────────────────────────────────

class Veredito:
    def __init__(self, unidade, texto):
        self.unidade, self.texto, self.falhas = unidade, texto, []

    @property
    def aprovado(self):
        return not self.falhas

    def reprovar(self, checagem, detalhe):
        self.falhas.append((checagem, detalhe))


def fiscal_10(unidade, texto, exigir_cobertura=True):
    v = Veredito(unidade, texto)
    c = _canon(texto)

    # ① NÚMERO — todo número citado existe na origem?
    permitidos = unidade.numeros_permitidos()
    for n in _numeros(texto):
        if not any(abs(n - p) < 0.05 for p in permitidos):
            v.reprovar("numero", "%s não existe na origem %s" % (_fmt(n), unidade.id))

    # ② VERBO — toda expressão lógica reconhecida está entre as autorizadas?
    #
    # 🔧 As formas DECLARADAS do verbo, não só a canônica: "equivalem a" é "equivale a"
    # com concordância, e conjugar não é trocar de verbo. O conjunto continua fechado —
    # o que mudou é que ele passou a conter o português, não só o infinitivo de fichário.
    autorizados = {_canon(x) for x in formas_aceitas(unidade.verbos)}
    for expr, classe in LEXICO_LOGICO.items():
        if _canon(expr) in c and _canon(expr) not in autorizados:
            v.reprovar("verbo", "expressão %r (classe %s) não autorizada em %s"
                       % (expr, classe, unidade.id))

    if isinstance(unidade, Conclusao) and not any(a in c for a in autorizados):
        v.reprovar("verbo", "nenhum verbo autorizado de %s aparece na redação" % unidade.id)

    # ③ QUALIFICAÇÃO — o freio foi preservado?
    for q in unidade.qualificacoes:
        if _canon(q) not in c:
            v.reprovar("qualificacao", "qualificação obrigatória ausente: %r" % q)

    # ④ EXCESSO — a frase afirma algo além da origem?
    #
    # Aqui o fiscal se abstém para o lado seguro, exatamente como o Fiscal 0: palavra
    # que ele não sabe atribuir a nada declarado é palavra que pode estar carregando
    # significado que ninguém apurou. É a checagem mais severa do protótipo, e é a que
    # tem mais chance de revelar, RODANDO, se ela é severa demais.
    if exigir_cobertura:
        conhecidas = set(PALAVRAS_FUNCIONAIS)
        for campo in unidade.par:
            conhecidas |= {_canon(r) for r in ROTULOS.get(campo, ())}
            # 🔧 Defeito 5: o rótulo PUBLICÁVEL é vocabulário declarado do catálogo,
            # tanto quanto ROTULOS. Sem isto o fiscal barrava "concedidos" — palavra
            # que sai de `ROTULO_PUBLICO["descontos_valor"] = "Descontos concedidos"`.
            # Eu entregava o rótulo ao redator e depois o punia por usá-lo.
            conhecidas |= {_canon(p) for p in ROTULO_PUBLICO.get(campo, "").split()}
        conhecidas |= MARCADORES_PROVENIENCIA
        # 🔧 O valor semântico normalizado e o trecho atômico da proveniência. Sem
        # isto o fiscal punia "capa de silicone" — que está na origem do fato.
        # ⛔ O campo bruto inteiro continua FORA: proveniência não é licença.
        conhecidas |= {_canon(t) for t in getattr(unidade, "termos_permitidos", set)()}
        for expr in autorizados:
            conhecidas |= set(expr.split())
        for q in unidade.qualificacoes:
            conhecidas |= {_canon(p) for p in q.split()}
        conhecidas = {_canon(p) for p in conhecidas}

        desconhecidas = []
        for tok in re.findall(r"[a-zA-ZÀ-ÿ$%]+", texto):
            t = _canon(tok)
            if t and t not in conhecidas and not t.isdigit():
                desconhecidas.append(tok)
        if desconhecidas:
            v.reprovar("excesso", "termos fora do declarado: %s"
                       % ", ".join(sorted(set(desconhecidas))))
    return v


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSIÇÃO — recebe os operadores autorizados; não os escolhe.
# ─────────────────────────────────────────────────────────────────────────────

def compor(vereditos_aprovados, limites=()):
    """Ordena e conecta. Não pode criar OPERADOR LÓGICO NOVO.

    Os `limites` entram como frases próprias, ao final: são texto DECLARADO e não se
    costuram a conclusão nenhuma — costurá-los sugeriria uma relação entre o limite do
    produto e o que foi apurado, que é exatamente o tipo de vínculo que ninguém apurou.

    ⚡ Não há checagem de causalidade aqui, e é de propósito: o conector causal nunca
    entra no conjunto de opções. A composição só enxerga `operadores_comuns` — a
    interseção dos operadores das unidades que está costurando. Se a interseção for
    vazia, ela não força a costura: separa em frases.
    """
    declaradas = [l.texto for l in limites]
    if not vereditos_aprovados:
        return " ".join(declaradas)

    partes = [v.texto for v in vereditos_aprovados]
    op_comuns = set(vereditos_aprovados[0].unidade.operadores)
    for v in vereditos_aprovados[1:]:
        op_comuns &= set(v.unidade.operadores)

    if len(partes) == 1:
        texto = partes[0]
    elif op_comuns:
        # Ordem estável: o operador vem do conjunto RECEBIDO, nunca de escolha livre.
        op = sorted(op_comuns)[0]
        texto = (", %s " % op).join(partes[:-1]) + ", %s %s" % (op, partes[-1])
    else:
        texto = ". ".join(p[0].upper() + p[1:] for p in partes)

    texto = texto.strip()
    texto = texto[0].upper() + texto[1:] + ("" if texto.endswith(".") else ".")
    return " ".join([texto] + declaradas)


def operadores_disponiveis(vereditos_aprovados):
    """Exposto para o relatório: mostra que a costura recebeu um conjunto FECHADO."""
    if not vereditos_aprovados:
        return []
    comuns = set(vereditos_aprovados[0].unidade.operadores)
    for v in vereditos_aprovados[1:]:
        comuns &= set(v.unidade.operadores)
    return sorted(comuns)
