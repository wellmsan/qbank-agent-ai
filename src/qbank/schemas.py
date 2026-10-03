from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator

Dificuldade = Literal["facil", "media", "dificil"]


class ConteudoQuestao(BaseModel):
    """O que o MODELO produz: só o conteúdo pedagógico."""

    enunciado: str = Field(min_length=20, description="Enunciado claro, sem ambiguidade")
    alternativas: list[str] = Field(min_length=4, max_length=5, description="Alternativas com tamanho e estrutura parecidos")
    indice_correta: int = Field(description="Índice (0-based) da ÚNICA alternativa correta")
    justificativa: str = Field(description="Por que a correta está certa e cada outra está errada")
    fontes: list[str] = Field(min_length=1, description="IDs dos trechos usados, ex.: 'java_streams.md#1'")


class Questao(ConteudoQuestao):
    """O que o SISTEMA armazena: conteúdo + metadados preenchidos pelo código."""

    topico: str
    dificuldade: Dificuldade
    enunciado: str = Field(min_length=20)
    alternativas: list[str] = Field(min_length=4, max_length=5)
    indice_correta: int = Field(description="Índice (0-based) da alternativa correta")
    justificativa: str = Field(description="Por que a correta está certa e as outras erradas")

    @field_validator("alternativas")
    @classmethod
    def alternativas_distintas(cls, v: list[str]) -> list[str]:
        normalizadas = [a.strip().lower() for a in v]
        if len(set(normalizadas)) != len(normalizadas):
            raise ValueError("alternativas repetidas")
        for a in v:
            if len(a.strip()) < 2 or a.strip().startswith(":") or "_index" in a or '"' in a:
                raise ValueError(f"alternativa malformada: {a!r}")
        import re
        if any(re.match(r"^\s*[A-Ea-e][\)\.\-:]\s", a) for a in v):
            raise ValueError("não prefixe as alternativas com letras (A, B...); a numeração é do sistema")
        return v

    @model_validator(mode="after")
    def indice_valido(self) -> "Questao":
        if not 0 <= self.indice_correta < len(self.alternativas):
            raise ValueError("indice_correta fora do intervalo")
        return self

class AnaliseAlternativa(BaseModel):
    indice: int
    verdadeira: bool = Field(description="Considerando SÓ os trechos-fonte, esta alternativa responde corretamente ao enunciado?")
    evidencia: str = Field(default="", description="Se verdadeira: copie LITERALMENTE a frase do trecho que a sustenta. Se falsa: deixe vazio.")
    motivo: str = Field(description="Por que é verdadeira ou falsa")


class Revisao(BaseModel):
    analise_alternativas: list[AnaliseAlternativa] = Field(
        description="Analise CADA alternativa individualmente, na ordem. Pode haver mais de uma verdadeira, ou nenhuma.")
    distratores_plausiveis: bool = Field(description="As falsas são plausíveis para quem não domina o tema, e diferentes entre si?")
    aderente_ao_pedido: bool = Field(description="A questão trata do assunto e do nível pedidos?")
    clareza: bool = Field(description="O enunciado é uma pergunta clara, sem ambiguidade?")
    nota: int = Field(ge=0, le=10)
    problemas: list[str] = Field(default_factory=list, description="Problemas concretos; obrigatório se a nota for menor que 7")
    sugestoes: str = Field(default="", description="Como corrigir, de forma acionável")

class EspecQuestao(BaseModel):
    subtopico: str = Field(description="Assunto específico, em palavras (ex.: 'map versus flatMap'), escolhido do sumário")
    dificuldade: Dificuldade
    objetivo: str = Field(description="Habilidade avaliada: aplicar, diferenciar, prever saída de código...")


class Plano(BaseModel):
    quantidade_pedida: int = Field(description="Quantas questões o pedido solicita (3 se não for informado)")
    topico: str = Field(description="Tópico geral do lote, ex.: 'Java Streams'")
    especificacoes: list[EspecQuestao] = Field(
        description="Exatamente 'quantidade_pedida' itens, menos os que o material não cobre; cada um com subtópico DIFERENTE")
    observacoes: str = Field(default="", description="Partes do pedido que o material não cobre")