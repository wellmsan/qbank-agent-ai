from functools import lru_cache
from langchain.chat_models import init_chat_model
from .config import settings


@lru_cache
def get_llm(papel: str = "gerador", temperatura: float = 0.0):
    spec = getattr(settings, f"model_{papel}")
    kwargs = {"temperature": temperatura}
    if spec.startswith("ollama:"):
        kwargs["num_ctx"] = 16384   # evita o corte silencioso do contexto
        kwargs["reasoning"] = False   # desliga o "thinking" do qwen3
    return init_chat_model(spec, **kwargs)

def estruturado(schema, papel: str = "gerador"):
    """Saída estruturada com o mecanismo mais confiável de cada provedor.

    - Ollama: json_schema (gramática restringe a geração; não consegue fugir do formato)
    - Anthropic/OpenAI/Google: function_calling (o provedor força a chamada da ferramenta)
    """
    spec = getattr(settings, f"model_{papel}")
    metodo = "json_schema" if spec.startswith("ollama:") else "function_calling"
    return get_llm(papel).with_structured_output(schema, include_raw=True, method=metodo)