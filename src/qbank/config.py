import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    model_gerador: str = os.getenv("QBANK_MODEL_GERADOR", "ollama:qwen3:14b")
    model_revisor: str = os.getenv("QBANK_MODEL_REVISOR", "ollama:qwen3:14b")
    model_orquestrador: str = os.getenv("QBANK_MODEL_ORQUESTRADOR", "ollama:qwen3:14b")
    max_questoes: int = int(os.getenv("QBANK_MAX_QUESTOES", "5"))
    humano_revisa_reprovadas: bool = os.getenv("QBANK_HUMANO_REVISA_REPROVADAS", "0") == "1"


settings = Settings()