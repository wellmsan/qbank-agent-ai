from qbank.llm import get_llm

resposta = get_llm().invoke("Em uma frase: o que é avaliação preguiçosa em Java Streams?")
print(resposta.content)
print(resposta.usage_metadata)   # tokens de entrada/saída