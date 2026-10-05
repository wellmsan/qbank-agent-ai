import sys
import uuid

from langgraph.types import Command

from qbank.banco import banco
from qbank.orquestrador import checkpointer_sqlite, construir

grafo = construir(checkpointer_sqlite())
LETRAS = "ABCDE"


def rodar(entrada, thread_id):
    cfg = {"configurable": {"thread_id": thread_id}}
    for ns, passo in grafo.stream(entrada, cfg, stream_mode="updates", subgraphs=True):
        for no in passo:
            if not ns and no != "__interrupt__":
                print(f"• {no}", flush=True)
    return grafo.get_state(cfg)


def pendente(snap):
    valores = [i.value for t in snap.tasks for i in t.interrupts]
    return valores[0] if valores else None


def decidir(p):
    for a in p.get("alertas", []):
        rotulo = {"aprovada": "✔ aprovada pelo revisor", "divergente": "⚖ DIVERGENTE",
                  "reprovada": "✖ REPROVADA pelo revisor"}[q["status"]]
        print(f"\n[{i}] {rotulo} | {q['enunciado']}")
        if q["status"] == "reprovada":
            for prob in q["problemas"][:3]:
                print(f"     problema: {prob}")
    decisoes = []
    for i, q in enumerate(p["candidatas"]):
        divergente = q["status"] == "divergente"
        print(f"\n[{i}] {'⚖ DIVERGENTE' if divergente else '✔ aprovada pelo revisor'} | {q['enunciado']}")
        for j, alt in enumerate(q["alternativas"]):
            marca = "G" if j == q["indice_correta"] else " "
            marca += "R" if divergente and j == q["gabarito_revisor"] else " "
            print(f"   [{marca}] {LETRAS[j]}) {alt}")
        opcoes = "[a]provar  [r]ejeitar" + ("  [c]orrigir para o gabarito do revisor" if divergente else "")
        decisoes.append(input(f"   {opcoes} > ").strip().lower() or "a")
    return decisoes

def informar(snap, thread_id):
    if pendente(snap):
        print(f"\n⏸ Pausado em {snap.next}. O estado está salvo em data/checkpoints.sqlite.")
        print(f"   python tests/teste_passo7.py retomar {thread_id}")
    else:
        print("\nNenhuma candidata para aprovar.", snap.values.get("alertas"))

cmd = sys.argv[1]
if cmd == "gerar":
    thread_id = uuid.uuid4().hex[:8]
    print(f"thread_id: {thread_id}")
    snap = rodar({"pedido": sys.argv[2]}, thread_id)
    informar(snap, thread_id)
elif cmd == "continuar":
    # Entrada None = "continue do último checkpoint": reexecuta só o nó que falhou
    thread_id = sys.argv[2]
    snap = rodar(None, thread_id)
    informar(snap, thread_id)

elif cmd == "retomar":
    thread_id = sys.argv[2]
    snap = grafo.get_state({"configurable": {"thread_id": thread_id}})
    p = pendente(snap)
    if not p:
        print("Esta thread não está aguardando aprovação.")
        sys.exit()
    snap = rodar(Command(resume=decidir(p)), thread_id)
    print(f"\n✔ Gravadas no banco: {snap.values.get('salvas')}")

elif cmd == "listar":
    for q in banco.listar():
        print(f"#{q['id']} [{q['topico']} | {q['dificuldade']}] {q['enunciado'][:100]}")
