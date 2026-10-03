import time
from qbank.orquestrador import orquestrador

entrada = {"pedido": "4 questões de Java Streams, nível médio, sobre avaliação preguiçosa, "
                     "map vs flatMap, curto-circuito e paralelismo com parallelStream."}

t0 = time.perf_counter()
estado = {}
# subgraphs=True: mostra também os passos de DENTRO de cada subagente
for namespace, passo in orquestrador.stream(entrada, stream_mode="updates", subgraphs=True):
    for no, delta in passo.items():
        quem = f"   [sub {namespace[0].split(':')[-1][:4]}]" if namespace else "•"
        detalhe = ""
        if no == "planejar":
            detalhe = "→ " + " | ".join(e["subtopico"] for e in delta.get("plano", []))
        elif no == "revisor":
            detalhe = "→ " + ("APROVADA" if delta["revisao"]["aprovada"] else "reprovada")
        print(f"{quem} {no} {detalhe}  ({time.perf_counter() - t0:.0f}s)")
        if not namespace and delta:
            estado.update(delta)   # guardamos o estado do grafo principal a partir do próprio stream

print(f"\n{len(estado.get('aprovadas', []))} questão(ões) aprovada(s) em {time.perf_counter() - t0:.0f}s")
for q in estado.get("aprovadas", []):
    print(f"\n[{q['dificuldade']}] {q['enunciado']}")
    for i, a in enumerate(q["alternativas"]):
        print(f"  {'✔' if i == q['indice_correta'] else ' '} {a}")
for alerta in estado.get("alertas", []):
    print(f"⚠ {alerta}")