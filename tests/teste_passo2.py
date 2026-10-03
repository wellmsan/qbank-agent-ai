from qbank.llm import get_llm
from qbank.schemas import ConteudoQuestao

llm = get_llm().with_structured_output(ConteudoQuestao, include_raw=True, method="function_calling")

resultado = llm.invoke(
    "Crie uma questão de múltipla escolha, nível médio, sobre avaliação "
    "preguiçosa em Java Streams. Use 4 alternativas."
)

raw = resultado["raw"]
print("--- RAW ---")
print(raw.tool_calls or raw.content)

if resultado["parsing_error"]:
    print("\n✖ Saída recusada pela validação:")
    print(resultado["parsing_error"])
else:
    questao: ConteudoQuestao = resultado["parsed"]
    print("\n✔ Questão válida:")
    print(questao.model_dump_json(indent=2))