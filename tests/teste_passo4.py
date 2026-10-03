from qbank.agent import agente
from qbank.retrieval import retriever

print(agente.get_graph().draw_mermaid())   # cole em mermaid.live para ver o grafo

entrada = {"pedido": "Elabore uma questão de nível médio sobre a diferença entre reduce com e sem identidade "
                     "em Java Streams, com um pequeno trecho de código."}

# stream: mostra cada nó executado e o que ele atualizou no estado
for passo in agente.stream(entrada, stream_mode="updates"):
    for no, delta in passo.items():
        detalhe = ""
        if no == "gerador":
            tc = delta["mensagens"][-1].tool_calls
            detalhe = f"→ tools: {[c['args'] for c in tc]}" if tc else "→ terminou"
        elif no == "revisor":
            r = delta["revisao"]
            detalhe = (f"→ {'APROVADA' if r['aprovada'] else 'REPROVADA'} (nota {r['nota']}) "
                       f"verdadeiras={r.get('verdadeiras')}\n      problemas: {r['problemas'][:3]}")
        print(f"• {no} {detalhe}")

final = agente.invoke(entrada)
rev = final.get("revisao") or {}
if rev.get("aprovada"):
    q = final["questao"]
    print(f"\n✔ APROVADA na tentativa {final['tentativas']}: {q['enunciado']}")
    for i, a in enumerate(q["alternativas"]):
        print(f"  {'✔' if i == q['indice_correta'] else ' '} {a}")
else:
    print(f"\n✖ REPROVADA após {final['tentativas']} tentativa(s). Última versão NÃO deve ser usada.")
    print("  motivos:", rev.get("problemas"))

final = agente.invoke(entrada) 
# if final.get("erro"):
#     print("\n✖", final["erro"])
# else:
#     q = final["questao"]
#     print("\n✔", q["enunciado"])
#     for i, a in enumerate(q["alternativas"]):
#         print(f"  {'✔' if i == q['indice_correta'] else ' '} {a}")
#     print("fontes válidas:", all(f in retriever.trechos for f in q["fontes"]))
#     print("mensagens no histórico:", len(final["mensagens"]))