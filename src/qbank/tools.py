from langchain_core.tools import tool
from .retrieval import retriever


@tool
def buscar_material(consulta: str) -> str:
    """Busca trechos do material didático oficial. Use ANTES de escrever a
    questão. Se os trechos não cobrirem o assunto, busque de novo com outros
    termos. Retorna trechos com IDs (ex.: 'java_streams.md#1') para citar."""
    resultados = retriever.buscar(consulta)
    if not resultados:
        return "Nenhum trecho encontrado. Tente sinônimos ou termos mais gerais."
    return "\n\n".join(f'<documento id="{i}">\n{t}\n</documento>' for i, t in resultados)


FERRAMENTAS = {t.name: t for t in [buscar_material]}