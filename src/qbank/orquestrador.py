import operator
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .agente import agente
from .config import settings
from .llm import estruturado
from .retrieval import normalizar, retriever
from .schemas import Plano

import sqlite3
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send, interrupt
from .banco import DATA, banco


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
    candidatas: list[dict]
    reprovadas: list[dict]
    decisoes: list[str]
    salvas: list[int]


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
        "problemas": rev.get("problemas", []), "revisao": rev,
    }]}


def consolidar(estado: EstadoLote) -> dict:
    candidatas, reprovadas, alertas = [], [], []
    for r in sorted(estado.get("resultados", []), key=lambda r: r["indice"]):
        rotulo = f"Questão {r['indice'] + 1} ({r['espec']['subtopico']})"
        q, rev = r["questao"], r["revisao"]
        # Divergência de gabarito como ÚNICO problema objetivo: um humano arbitra
        divergente = (not r["aprovada"] and q is not None and rev.get("divergencia")
                      and len(rev.get("problemas_codigo", [])) == 1)
        if not r["aprovada"] and not divergente:
            alertas.append(f"{rotulo} reprovada após {r['tentativas']} tentativa(s): {r['problemas'][:1]}")
            reprovadas.append(r)
            if settings.humano_revisa_reprovadas and q is not None:
                candidatas.append(q | {"topico": estado["topico"], "dificuldade": r["espec"]["dificuldade"],
                                       "status": "reprovada", "gabarito_revisor": None,
                                       "problemas": r["problemas"]})
            continue
        if any(similaridade(q["enunciado"], c["enunciado"]) > 0.6 for c in candidatas):
            alertas.append(f"{rotulo} descartada: muito parecida com outra do lote.")
            continue
        candidatas.append(q | {"topico": estado["topico"], "dificuldade": r["espec"]["dificuldade"],
                               "status": "divergente" if divergente else "aprovada",
                               "gabarito_revisor": rev["verdadeiras"][0] if divergente else None})
    return {"candidatas": candidatas, "reprovadas": reprovadas, "alertas": alertas}


def construir(checkpointer=None):
    g = StateGraph(EstadoLote)
    g.add_node("planejar", planejar)
    g.add_node("produzir_questao", produzir_questao)
    g.add_node("consolidar", consolidar)
    g.add_node("aprovacao_humana", aprovacao_humana)
    g.add_node("persistir", persistir)
    g.add_edge(START, "planejar")
    g.add_conditional_edges("planejar", distribuir, ["produzir_questao", END])
    g.add_edge("produzir_questao", "consolidar")
    g.add_conditional_edges("consolidar", lambda s: "aprovacao_humana" if s.get("candidatas") else END,
                            ["aprovacao_humana", END])
    g.add_edge("aprovacao_humana", "persistir")
    g.add_edge("persistir", END)
    return g.compile(checkpointer=checkpointer)


def aprovacao_humana(estado: EstadoLote) -> dict:
    # ATENÇÃO: na retomada, este nó roda DE NOVO desde o início, e interrupt() devolve a resposta.
    # Por isso, nada com efeito colateral pode vir antes do interrupt().
    decisoes = interrupt({"candidatas": estado["candidatas"], "alertas": estado.get("alertas", [])})
    return {"decisoes": decisoes}


def persistir(estado: EstadoLote, config: RunnableConfig) -> dict:
    """A ÚNICA escrita no banco do sistema inteiro, e só depois da decisão humana."""
    thread_id = config["configurable"]["thread_id"]
    ids = []
    for q, decisao in zip(estado["candidatas"], estado["decisoes"]):
        if decisao == "c" and q.get("gabarito_revisor") is not None:
            q = q | {"indice_correta": q["gabarito_revisor"]}
        if decisao in ("a", "c"):
            ids.append(banco.salvar(q, thread_id))
    return {"salvas": ids}


def checkpointer_sqlite():
    from langgraph.checkpoint.sqlite import SqliteSaver
    DATA.mkdir(parents=True, exist_ok=True)
    return SqliteSaver(sqlite3.connect(DATA / "checkpoints.sqlite", check_same_thread=False))

orquestrador = construir()