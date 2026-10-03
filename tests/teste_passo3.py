from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from qbank.llm import get_llm
from qbank.schemas import ConteudoQuestao
from qbank.tools import FERRAMENTAS

MAX_ITERACOES = 5

mensagens = [
    SystemMessage("Você elabora questões de múltipla escolha. Use buscar_material para "
                  "encontrar o conteúdo antes de escrever. Toda afirmação deve vir dos trechos. "
                  "Quando tiver material suficiente, responda com um rascunho curto, sem chamar ferramentas."),
    HumanMessage("Elabore uma questão de nível médio sobre avaliação preguiçosa em Java Streams."),
]
llm = get_llm().bind_tools(list(FERRAMENTAS.values()))

# ---------------- O LOOP AGÊNTICO ----------------
for iteracao in range(1, MAX_ITERACOES + 1):
    resposta = llm.invoke(mensagens)
    mensagens.append(resposta)

    if not resposta.tool_calls:
        if "tool_call" in str(resposta.content) or '"arguments"' in str(resposta.content):
            print(f"[{iteracao}] ⚠ o modelo escreveu uma tool call como TEXTO: "
                  "o provedor/modelo não está fazendo tool calling nativo")
        else:
            print(f"[{iteracao}] modelo terminou: {resposta.content[:150]}")
        break

    for chamada in resposta.tool_calls:              # executar o que o modelo pediu
        print(f"[{iteracao}] tool: {chamada['name']}({chamada['args']})")
        try:
            saida = FERRAMENTAS[chamada["name"]].invoke(chamada["args"])
        except Exception as e:                       # erro vira mensagem: o modelo pode se corrigir
            saida = f"ERRO: {e}"
        mensagens.append(ToolMessage(saida, tool_call_id=chamada["id"]))
else:
    print("critério de parada 2: limite de iterações atingido")   # (ver observação abaixo)

# ---------------- EXTRAÇÃO ESTRUTURADA ----------------
mensagens.append(HumanMessage("Agora entregue a versão final no formato estruturado. "
                              "Em 'fontes', use só IDs de trechos que você recebeu."))
resultado = get_llm().with_structured_output(
    ConteudoQuestao, include_raw=True, method="function_calling").invoke(mensagens)

if resultado["parsing_error"]:
    print("\n✖", resultado["parsing_error"])
else:
    q = resultado["parsed"]
if q is None:
    print("\n✖ Sem saída estruturada.")
    print("erro de validação:", resultado["parsing_error"])
    print("o modelo respondeu:", str(resultado["raw"].content)[:300])
else:
    print("\n✔", q.model_dump_json(indent=2))
    validas = [f for f in q.fontes if f in FERRAMENTAS["buscar_material"].func.__globals__["retriever"].trechos]
    print("fontes realmente existentes:", validas, "de", q.fontes)