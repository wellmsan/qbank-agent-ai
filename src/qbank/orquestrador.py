import operator
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agent import agente
from .config import settings
from .llm import estruturado
from .retrieval import normalizar, retriever
from .schemas import Plano

SYSTEM_ORQUESTRADOR = """Você é o coordenador pedagógico de um banco de questões.
Transforme o pedido em um plano com uma especificação por questão.

Regras:
- Respeite a quantidade e o nível pedidos; se não forem informados, use 3 questões de nível médio.
- No máximo {max_questoes} questões.
- Cada especificação deve cobrir um subtópico DIFERENTE.
- Use APENAS subtópicos presentes no sumário do material abaixo. Se o pedido citar algo fora dele,
  não planeje questão sobre isso e registre em 'observacoes'.

SUMÁRIO DO MATERIAL:
{sumario}"""


def sumario_material() -> str:
    titulos = dict.fromkeys(texto.splitlines()[0].lstrip("# ").strip() for texto in retriever.trechos.values())
    return "\n".join(f"- {t}" for t in titulos)


def similaridade(a: str, b: str) -> float:
    ta, tb = set(normalizar(a)), set(normalizar(b))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


class EstadoLote(TypedDict, total=False):
    pedido: str
    topico: str
    plano: list[dict]
    # Vários subagentes escrevem aqui AO MESMO TEMPO: o reducer operator.add concatena as listas
    resultados: Annotated[list[dict], operator.add]
    aprovadas: list[dict]
    alertas: Annotated[list[str], operator.add]


# ---------------- nós ----------------
def planejar(estado: EstadoLote) -> dict:
    sistema = SYSTEM_ORQUESTRADOR.format(max_questoes=settings.max_questoes, sumario=sumario_material())
    resultado = estruturado(Plano, "orquestrador").invoke([SystemMessage(sistema), HumanMessage(estado["pedido"])])
    plano: Plano | None = resultado["parsed"]
    if plano is None:
        return {"plano": [], "alertas": [f"Planejador falhou: {resultado['parsing_error']}"]}
    especs = [e.model_dump() for e in plano.especificacoes[: settings.max_questoes]]
    alertas = [f"Planejador: {plano.observacoes}"] if plano.observacoes else []
    pedida = min(plano.quantidade_pedida, settings.max_questoes)
    if len(especs) < pedida and not plano.observacoes:
        alertas.append(f"Planejador gerou {len(especs)} de {pedida} questões pedidas sem justificar.")
    subtopicos = [normalizar(e["subtopico"]) for e in especs]
    if len({tuple(s) for s in subtopicos}) < len(subtopicos):
        alertas.append("Planejador repetiu subtópicos.")
    return {"topico": plano.topico, "plano": especs, "alertas": alertas}


def distribuir(estado: EstadoLote):
    """Map: um Send por especificação. Cada Send vira uma execução paralela de produzir_questao."""
    if not estado.get("plano"):
        return END
    return [Send("produzir_questao", {"indice": i, "topico": estado["topico"], "espec": e})
            for i, e in enumerate(estado["plano"])]


def produzir_questao(payload: dict) -> dict:
    """Recebe SÓ o payload do Send: contexto isolado. Roda o agente completo do passo 5."""
    e = payload["espec"]
    pedido = (f"Elabore uma questão de múltipla escolha.\n"
              f"Tópico: {payload['topico']}\nSubtópico: {e['subtopico']}\n"
              f"Dificuldade: {e['dificuldade']}\nObjetivo: {e['objetivo']}")
    final = agente.invoke({"pedido": pedido})
    rev = final.get("revisao") or {}
    return {"resultados": [{
        "indice": payload["indice"], "espec": e, "questao": final.get("questao"),
        "aprovada": bool(rev.get("aprovada")), "tentativas": final.get("tentativas", 0),
        "problemas": rev.get("problemas", []),
    }]}


def consolidar(estado: EstadoLote) -> dict:
    """Reduce: ordena, descarta reprovadas e remove duplicatas DENTRO do lote."""
    aprovadas, alertas = [], []
    for r in sorted(estado.get("resultados", []), key=lambda r: r["indice"]):
        rotulo = f"Questão {r['indice'] + 1} ({r['espec']['subtopico']})"
        if not r["aprovada"]:
            alertas.append(f"{rotulo} reprovada após {r['tentativas']} tentativa(s): {r['problemas'][:1]}")
            continue
        q = r["questao"]
        if any(similaridade(q["enunciado"], a["enunciado"]) > 0.6 for a in aprovadas):
            alertas.append(f"{rotulo} descartada: muito parecida com outra do lote.")
            continue
        aprovadas.append(q | {"topico": estado["topico"], "dificuldade": r["espec"]["dificuldade"]})
    return {"aprovadas": aprovadas, "alertas": alertas}


def construir():
    g = StateGraph(EstadoLote)
    g.add_node("planejar", planejar)
    g.add_node("produzir_questao", produzir_questao)
    g.add_node("consolidar", consolidar)
    g.add_edge(START, "planejar")
    g.add_conditional_edges("planejar", distribuir, ["produzir_questao", END])
    g.add_edge("produzir_questao", "consolidar")   # o consolidar espera TODOS os Sends terminarem
    g.add_edge("consolidar", END)
    return g.compile()


orquestrador = construir()