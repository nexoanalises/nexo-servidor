# Testes da análise ESTRUTURADA (#083 / inversão HTML). Zero token.
import sys, types
class _Qq:
    def __init__(self, *a, **k): self.config = {}
    def __call__(self, *a, **k): return _Qq()
    def __getattr__(self, _): return _Qq()
    def __setitem__(self, k, v): pass
    def __getitem__(self, k): return _Qq()
for n in ("flask","gspread","google","google.oauth2","google.oauth2.service_account",
          "dateutil","dateutil.relativedelta","requests","groq"):
    m = types.ModuleType(n); m.__getattr__ = lambda _x: _Qq(); sys.modules.setdefault(n, m)
sys.modules["flask"].Flask=_Qq; sys.modules["flask"].request=_Qq(); sys.modules["flask"].jsonify=_Qq()
sys.modules["google.oauth2.service_account"].Credentials=_Qq
sys.modules["dateutil.relativedelta"].relativedelta=_Qq; sys.modules["groq"].Groq=_Qq
sys.path.insert(0, r"C:\Users\Ricardo\Desktop\Nexo arquivos antigos\nexo_servidor")
import servidor as S

ok = falhou = 0
def caso(t, obtido, esperado):
    global ok, falhou
    b = obtido == esperado
    print(f"{'  OK  ' if b else ' FALHA'} | {t}")
    if not b: print(f"         obtido={obtido!r}\n         esperado={esperado!r}")
    ok, falhou = ok+b, falhou+(not b)

R, A, V = "\U0001F534", "\U0001F7E2", "\U0001F7E1"
SAIDA = f"""\U0001F4CC 1. RADAR DO NEGOCIO
{A} Margem liquida: 14,4%
{R} Custos: R$ 46.900

\U0001F9ED 2. DIAGNOSTICO CENTRAL
Voce vendeu mais e o lucro nao acompanhou.

\U0001F527 7. ACOES IMEDIATAS
1. Definir o preco de saida da colecao de outono, peca a peca.
2. Suspender a compra da proxima colecao.

\U0001F9ED 8. METAS ATE A PROXIMA ANALISE
De R$ 7.900 para R$ 10.000 em lucro."""

print("\n=== _em_secoes — prosa vira estrutura UMA vez ===")
sec = S._em_secoes(SAIDA)
caso("achou 4 secoes", len(sec), 4)
caso("numeros certos", [s["n"] for s in sec], [1, 2, 7, 8])
caso("acao numerada NAO virou secao",
     len([l for l in sec[2]["linhas"] if "Definir o preco" in l["texto"]]), 1)
caso("acoes ficaram as duas", len(sec[2]["linhas"]), 2)

print("\n=== bandeira vira DADO, nao emoji na frase ===")
l0, l1 = sec[0]["linhas"]
caso("verde -> ok", (l0["bandeira"], l0["texto"]), ("ok", "Margem liquida: 14,4%"))
caso("vermelho -> risco", (l1["bandeira"], l1["texto"]), ("risco", "Custos: R$ 46.900"))
caso("sem emoji sobrando no texto", any(e in l0["texto"] for e in (R, A, V)), False)

print("\n=== _substituir_secao — o miolo do modelo e descartado ===")
S._substituir_secao(sec, "METAS", ["• Faturamento: de R$ 54.800 para R$ 55.000 — a meta que voce definiu."])
caso("metas inventadas sumiram",
     any("10.000" in l["texto"] for l in sec[3]["linhas"]), False)
caso("origem marcada como codigo", sec[3]["origem"], "codigo")
caso("secao nao tocada segue 'modelo'", sec[1]["origem"], "modelo")
caso("bullet reconhecido", sec[3]["linhas"][0]["tipo"], "bullet")
caso("bullet sem o marcador no texto", sec[3]["linhas"][0]["texto"].startswith("•"), False)

print("\n=== _texto_de_secoes — compatibilidade com a 1.0.2.0 instalada ===")
txt = S._texto_de_secoes(sec)
caso("cabecalho numerado volta", "1. RADAR DO NEGOCIO" in txt, True)
caso("bandeira volta como emoji", f"{A} Margem liquida" in txt, True)
caso("bullet volta com marcador", "• Faturamento:" in txt, True)
caso("meta do codigo esta no texto", "R$ 55.000" in txt, True)
caso("meta inventada nao voltou", "10.000" in txt, False)

print("\n=== ida e volta nao perde nada ===")
caso("re-parsear o texto achatado da a mesma estrutura",
     [(s["n"], s["titulo"], len(s["linhas"])) for s in S._em_secoes(txt)],
     [(s["n"], s["titulo"], len(s["linhas"])) for s in sec])

print("\n=== bordas ===")
caso("texto vazio", S._em_secoes(""), [])
caso("sem titulo nenhum vira preambulo",
     [s["n"] for s in S._em_secoes("uma frase solta")], [None])
caso("substituir titulo inexistente", S._substituir_secao(sec, "CICLO ANTERIOR", ["x"]), False)
caso("substituir com corpo vazio", S._substituir_secao(sec, "RADAR", []), False)

# ── Fallback parcial: o que o codigo garantiu NAO se joga fora ────────────────
print("\n=== fallback parcial (medido em producao 12:43) ===")
sec_fb = S._em_secoes(SAIDA)
S._substituir_secao(sec_fb, "RADAR", ["\U0001F7E2 Margem liquida: 14,4%"])
S._substituir_secao(sec_fb, "METAS", ["• Faturamento: de R$ 54.800 para R$ 55.000."])
apuradas = [s for s in sec_fb if s["origem"] == "codigo"]
caso("sobram exatamente as secoes apuradas", len(apuradas), 2)
caso("Radar sobrevive", any("RADAR" in (s["titulo"] or "") for s in apuradas), True)
caso("Metas sobrevivem", any("METAS" in (s["titulo"] or "") for s in apuradas), True)
caso("prosa do modelo nao sobrevive",
     any("DIAGNOSTICO" in (s["titulo"] or "") for s in apuradas), False)
txt_fb = S._texto_de_secoes(apuradas)
caso("cliente recebe numero, nao uma frase seca", "R$ 55.000" in txt_fb, True)
print(f"\n{'='*54}\n  {ok} passaram · {falhou} falharam\n{'='*54}")
sys.exit(1 if falhou else 0)
