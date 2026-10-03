from qbank.agent import revisor

CASOS = {
    "gabarito_trocado (passo 2)": {
        "esperado": False,
        "questao": {
            "enunciado": "Em relação à avaliação preguiçosa (lazy evaluation) em Java Streams, qual das alternativas a seguir é correta?",
            "alternativas": [
                "Avaliação preguiçosa é realizada quando o stream é criado.",
                "Avaliação preguiçosa é realizada durante a execução do método terminal de um stream.",
                "Avaliação preguiçosa ocorre sempre que uma operação intermediária é executada em um stream.",
                "Operações como filter(), map() e outros são exemplos de avaliação preguiçosa no Java Stream."],
            "indice_correta": 3,
            "justificativa": "As operações intermediárias são executadas apenas quando uma operação terminal ocorre.",
            "fontes": ["java_streams.md#1"]}},
    "tres_corretas (llama3.1)": {
        "esperado": False,
        "questao": {
            "enunciado": "Avaliação preguiçosa em Java Streams.",
            "alternativas": [
                "map transforma cada elemento em exatamente um elemento.",
                "flatMap transforma cada elemento em vários elementos.",
                "findFirst, findAny, anyMatch, allMatch e noneMatch podem encerrar o processamento antes de percorrer todos os elementos.",
                "limit pode ser usado para limitar o número de elementos a serem processados."],
            "indice_correta": 2,
            "justificativa": "Porque findFirst e outras podem encerrar o processamento antes.",
            "fontes": ["java_streams.md#2", "java_streams.md#1"]}},
    "boa (qwen3)": {
        "esperado": True,
        "questao": {
            "enunciado": "Sobre a avaliação preguiçosa em Java Streams, qual afirmação está correta quando se usa uma operação de curto-circuito, como anyMatch?",
            "alternativas": [
                "Todos os elementos do stream são processados, independentemente da condição.",
                "O processamento para imediatamente após encontrar o primeiro elemento que satisfaz a condição.",
                "A avaliação preguiçosa não afeta o comportamento de operações de curto-circuito.",
                "O stream é convertido em uma coleção completa antes de aplicar a condição."],
            "indice_correta": 1,
            "justificativa": "Operações de curto-circuito param assim que encontram um elemento que satisfaz a condição.",
            "fontes": ["java_streams.md#2"]}},
}

acertos = 0
for nome, caso in CASOS.items():
    rev = revisor({"pedido": "Questão de nível médio sobre avaliação preguiçosa em Java Streams",
                   "questao": caso["questao"], "tentativas": 0})["revisao"]
    falhou = any("REVISOR FALHOU" in p for p in rev["problemas"])
    ok = rev["aprovada"] == caso["esperado"] and not falhou
    acertos += ok
    print(f"{'✔' if ok else '✖'} {nome}: aprovada={rev['aprovada']} nota={rev['nota']}")
    for p in rev["problemas"]:
        print(f"     - {p}")
print(f"\nO revisor acertou {acertos}/{len(CASOS)}")