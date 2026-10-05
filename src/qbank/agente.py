import json
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .llm import estruturado, get_llm
from .retrieval import normalizar, retriever
from .schemas import ConteudoQuestao, Revisao
from .tools import FERRAMENTAS

MAX_ITERACOES = 5
MAX_REVISOES = 1  # NOVO: quantas vezes o gerador pode refazer

SYSTEM = ("Você elabora questões de múltipla escolha. Use buscar_material para encontrar "
          "o conteúdo antes de escrever. Toda afirmação deve vir dos trechos. Quando tiver "
          "material suficiente, responda com um rascunho curto, sem chamar ferramentas.")

SYSTEM_REVISOR = (
    "Você é um revisor rigoroso de itens de avaliação. Você NÃO conhece o gabarito. "
    "Analise cada alternativa de forma independente, usando apenas os trechos-fonte: "
    "pode haver mais de uma correta, ou nenhuma. Se a nota for menor que 7, liste os problemas.")


class Estado(TypedDict, total=False):
    pedido: str
    mensagens: Annotated[list[AnyMessage], add_messages]
    iteracoes: int
    questao: dict | None
    erro: str | None
    revisao: dict | None  # NOVO
    tentativas: int       # NOVO


def preparar(estado: Estado) -> dict:
    return {"mensagens": [SystemMessage(SYSTEM), HumanMessage(estado["pedido"])],
            "iteracoes": 0, "tentativas": 0}


def gerador(estado: Estado) -> dict:
    llm = get_llm().bind_tools(list(FERRAMENTAS.values()))
    resposta = llm.invoke(estado["mensagens"])
    return {"mensagens": [resposta], "iteracoes": estado["iteracoes"] + 1}


def ferramentas(estado: Estado) -> dict:
    saidas = []
    for chamada in estado["mensagens"][-1].tool_calls:
        try:
            saida = FERRAMENTAS[chamada["name"]].invoke(chamada["args"])
        except Exception as e:
            saida = f"ERRO: {e}. Revise os argumentos."
        saidas.append(ToolMessage(saida, tool_call_id=chamada["id"]))
    return {"mensagens": saidas}


def estruturar(estado: Estado) -> dict:
    novas = []
    for chamada in getattr(estado["mensagens"][-1], "tool_calls", None) or []:
        novas.append(ToolMessage("Não executado: limite de iterações atingido.", tool_call_id=chamada["id"]))
    pedido = HumanMessage("Agora entregue a versão final no formato estruturado. "
                          "Em 'fontes', use só IDs de trechos que você recebeu.")
    resultado = estruturado(ConteudoQuestao).invoke(estado["mensagens"] + novas + [pedido])

    if resultado["parsed"] is None:
        erro = resultado["parsing_error"] or f"sem saída estruturada: {str(resultado['raw'].content)[:200]}"
        return {"mensagens": novas, "questao": None, "erro": str(erro)}
    q = resultado["parsed"].model_dump()
    q["fontes"] = [retriever.resolver_fonte(f) for f in q["fontes"]]
    return {"mensagens": novas, "questao": q, "erro": None}


# NOVO ------------------------------------------------------------
def checagens_deterministicas(q: dict) -> list[str]:
    problemas = []
    inexistentes = [f for f in q["fontes"] if f not in retriever.trechos]
    if inexistentes:
        problemas.append(f"Fontes inexistentes (inventadas): {inexistentes}")
    correta = len(q["alternativas"][q["indice_correta"]])
    outras = [len(a) for i, a in enumerate(q["alternativas"]) if i != q["indice_correta"]]
    if correta > 1.5 * (sum(outras) / len(outras)):
        problemas.append("A alternativa correta é bem mais longa que as outras, o que entrega a resposta.")
    return problemas


def revisor(estado: Estado) -> dict:
    tentativas = estado.get("tentativas", 0) + 1
    q = estado.get("questao")
    if q is None: 
        return {"tentativas": tentativas,
                "revisao": {"aprovada": False, "nota": 0, "problemas": [f"Saída inválida: {estado['erro']}"],
                            "sugestoes": "Respeite o formato pedido."}}

    problemas_codigo = checagens_deterministicas(q)
    trechos = "\n\n".join(f'<documento id="{f}">\n{retriever.trechos[f]}\n</documento>'
                          for f in q["fontes"] if f in retriever.trechos)
    questao_cega = {"enunciado": q["enunciado"],                       # SEM gabarito e SEM justificativa
                    "alternativas": {i: a for i, a in enumerate(q["alternativas"])}}
    entrada = (f"PEDIDO ORIGINAL: {estado['pedido']}\n\n"
               f"QUESTÃO:\n{json.dumps(questao_cega, ensure_ascii=False, indent=2)}\n\n"
               f"TRECHOS-FONTE:\n{trechos or '(nenhum trecho válido)'}")

    resultado = estruturado(Revisao, "revisor").invoke(
        [SystemMessage(SYSTEM_REVISOR), HumanMessage(entrada)])
    rev: Revisao | None = resultado["parsed"]
    if rev is None:
        motivo = resultado["parsing_error"] or f"respondeu em texto: {str(resultado['raw'].content)[:200]}"
        return {"tentativas": tentativas,
                "revisao": {"aprovada": False, "nota": 0,
                            "problemas": problemas_codigo + [f"REVISOR FALHOU: {motivo}"], "sugestoes": ""}}

    verdadeiras = sorted(a.indice for a in rev.analise_alternativas if a.verdadeira)
    divergencia = False
    if len(verdadeiras) != 1:
        problemas_codigo.append(f"O revisor considerou {len(verdadeiras)} alternativas corretas "
                                f"({verdadeiras}); deve haver exatamente uma.")
    elif verdadeiras[0] != q["indice_correta"]:
        divergencia = True
        problemas_codigo.append(f"O gabarito marca a {q['indice_correta']}, mas o revisor resolveu "
                                f"como {verdadeiras[0]}.")

    # Fundamentação verificável: a evidência citada precisa existir nos trechos
    texto_fontes = " ".join(normalizar(" ".join(retriever.trechos[f] for f in q["fontes"] if f in retriever.trechos)))
    for a in rev.analise_alternativas:
        if a.verdadeira:
            ev = " ".join(normalizar(a.evidencia))
            if len(ev.split()) < 4 or ev not in texto_fontes:
                problemas_codigo.append(f"A alternativa {a.indice} foi julgada correta sem citação literal "
                                        f"dos trechos-fonte: não há fundamento no material.")

    aprovada = (not problemas_codigo and rev.distratores_plausiveis and rev.aderente_ao_pedido
                and rev.clareza and rev.nota >= 7)
    
    revisao = rev.model_dump() | {"aprovada": aprovada, "verdadeiras": verdadeiras,
                                  "divergencia": divergencia, "problemas_codigo": list(problemas_codigo),
                                  "problemas": problemas_codigo + rev.problemas}

    return {"revisao": revisao, "tentativas": tentativas}


def feedback(estado: Estado) -> dict:
    rev = estado["revisao"]
    anterior = json.dumps(estado["questao"], ensure_ascii=False, indent=2) if estado.get("questao") else "(inválida)"
    texto = ("O revisor REPROVOU sua versão anterior.\n\n"
             f"Versão anterior:\n{anterior}\n\n"
             "Problemas:\n" + "\n".join(f"- {p}" for p in rev["problemas"]) +
             f"\n\nSugestões: {rev.get('sugestoes', '')}\n\n"
             "Corrija APENAS os problemas apontados e mantenha o que estiver certo; não reescreva do zero. "
             "Se houver divergência sobre qual alternativa é a correta, releia o trecho-fonte e decida "
             "com base nele, ajustando o gabarito ou a alternativa. "
             "Construa a alternativa correta a partir de uma afirmação explícita do trecho.")
    return {"mensagens": [HumanMessage(texto)], "iteracoes": 0}
# -----------------------------------------------------------------


def rota_gerador(estado: Estado) -> str:
    if estado["mensagens"][-1].tool_calls and estado["iteracoes"] < MAX_ITERACOES:
        return "ferramentas"
    return "estruturar"


def rota_revisor(estado: Estado) -> str:  # NOVO
    if estado["revisao"]["aprovada"]:
        return END
    return "feedback" if estado["tentativas"] <= MAX_REVISOES else END


def construir():
    g = StateGraph(Estado)
    for nome, fn in [("preparar", preparar), ("gerador", gerador), ("ferramentas", ferramentas),
                     ("estruturar", estruturar), ("revisor", revisor), ("feedback", feedback)]:
        g.add_node(nome, fn)
    g.add_edge(START, "preparar")
    g.add_edge("preparar", "gerador")
    g.add_conditional_edges("gerador", rota_gerador, ["ferramentas", "estruturar"])
    g.add_edge("ferramentas", "gerador")
    g.add_edge("estruturar", "revisor")                                      # NOVO
    g.add_conditional_edges("revisor", rota_revisor, ["feedback", END])      # NOVO
    g.add_edge("feedback", "gerador")                                        # NOVO: o loop de reflexão
    return g.compile()


agente = construir()