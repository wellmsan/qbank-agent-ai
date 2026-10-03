# qbank-agent

Sistema multiagente que gera questões de múltipla escolha **fundamentadas em material didático**. Cada questão é escrita a partir de trechos recuperados do corpus, revisada por um agente que não conhece o gabarito e só é aprovada se passar por checagens determinísticas feitas em código.

Construído com [LangGraph](https://github.com/langchain-ai/langgraph) e [LangChain](https://github.com/langchain-ai/langchain). Funciona com qualquer provedor suportado pelo `init_chat_model` (Anthropic, OpenAI, Google, Ollama), e cada papel do sistema pode usar um modelo diferente.

## Como funciona

```
pedido ──► planejar ──► Send × N ──► [agente] [agente] [agente] ──► consolidar ──► questões aprovadas
            (Plano)                 (em paralelo, contexto isolado)    (dedup + alertas)
```

### Orquestrador (lote)

1. **planejar**: transforma o pedido em um `Plano` com uma especificação por questão (subtópico, dificuldade, objetivo). Só usa subtópicos que existem no sumário do corpus; o que estiver fora vai para `observacoes`.
2. **distribuir**: cria um `Send` por especificação, e cada um roda o agente completo em paralelo.
3. **consolidar**: ordena os resultados, descarta questões reprovadas e quase-duplicatas (similaridade de Jaccard > 0.6 entre enunciados) e reúne os alertas.

### Agente (uma questão)

```
preparar ─► gerador ⇄ ferramentas ─► estruturar ─► revisor ─┬─► END (aprovada ou limite)
               ▲                                            │
               └──────────────── feedback ◄─────────────────┘
```

- **gerador**: LLM com a ferramenta `buscar_material` (BM25 sobre o corpus). Pesquisa e depois escreve um rascunho.
- **estruturar**: converte o rascunho em `ConteudoQuestao` (enunciado, alternativas, gabarito, justificativa, fontes).
- **revisor**: recebe só o enunciado, as alternativas e os trechos-fonte, **sem gabarito**. Julga cada alternativa de forma independente e cita a evidência literal de cada uma que considerar correta.
- **Decisão em código**, não no LLM. A questão só é aprovada se:
  - todas as fontes citadas existem no corpus;
  - a alternativa correta não é muito mais longa que as outras (o que entregaria a resposta);
  - o revisor encontrou **exatamente uma** alternativa verdadeira, e ela coincide com o gabarito;
  - a evidência citada existe literalmente nos trechos-fonte;
  - distratores plausíveis, aderência ao pedido, clareza e nota ≥ 7.
- **feedback**: se reprovada, os problemas voltam ao gerador para correção (até `MAX_REVISOES` vezes).

## Instalação

Requer Python ≥ 3.11.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[anthropic]"     # ou: openai, google, ollama (combináveis: ".[anthropic,ollama]")
```

## Configuração

Crie um `.env` na raiz:

```dotenv
# Formato provedor:modelo (init_chat_model). Default: ollama:qwen3:14b
QBANK_MODEL_GERADOR=anthropic:claude-sonnet-5-5
QBANK_MODEL_REVISOR=anthropic:claude-sonnet-5-5
QBANK_MODEL_ORQUESTRADOR=anthropic:claude-haiku-4-5-20251001

QBANK_MAX_QUESTOES=5          # teto de questões por lote

ANTHROPIC_API_KEY=...
```

Com Ollama, o contexto é fixado em 16k tokens e o modo *thinking* é desligado. A saída estruturada usa `json_schema` (geração restrita por gramática) no Ollama e `function_calling` nos demais provedores.

## Uso

```python
from qbank.orquestrador import orquestrador

estado = orquestrador.invoke({
    "pedido": "4 questões de Java Streams, nível médio, sobre avaliação preguiçosa, "
              "map vs flatMap, curto-circuito e paralelismo."
})

for q in estado["aprovadas"]:
    print(q["enunciado"], q["alternativas"], q["indice_correta"], q["fontes"])
for alerta in estado["alertas"]:
    print("⚠", alerta)
```

Para gerar uma única questão, sem o orquestrador:

```python
from qbank.agent import agente

final = agente.invoke({"pedido": "Questão de nível médio sobre reduce com e sem identidade."})
if final["revisao"]["aprovada"]:
    print(final["questao"])
```

## Corpus

O material fica em `corpus/*.md`. Cada arquivo é dividido nas seções `## `, e cada seção vira um trecho com ID `<arquivo>#<índice>` (base 0; o texto antes do primeiro `##` é ignorado). As questões citam esses IDs em `fontes`.

Para adicionar conteúdo, basta incluir um novo `.md` com seções `##`. O índice BM25 e o sumário usado pelo planejador são reconstruídos na importação.

## Scripts de validação

Os arquivos em `tests/` são scripts executáveis, um por etapa de construção do projeto. **Eles chamam o LLM de verdade**, então consomem tokens ou exigem o Ollama rodando.

| Script | O que verifica |
|---|---|
| `teste_passo1.py` | Conexão com o LLM |
| `teste_passo2.py` | Saída estruturada (`ConteudoQuestao`) |
| `teste_passo3.py` | Loop agêntico manual com tool calling |
| `teste_passo4.py` | Grafo do agente (imprime o diagrama Mermaid e o stream de nós) |
| `teste_passo5_revisor.py` | Revisor isolado contra casos conhecidos (bons e ruins) |
| `teste_passo6.py` | Orquestrador em lote com subagentes paralelos |

```bash
python tests/teste_passo5_revisor.py
```

## Estrutura

```
src/qbank/
├── config.py        # Settings lidas do .env
├── llm.py           # get_llm(papel) e estruturado(schema, papel)
├── retrieval.py     # BM25 sobre corpus/*.md
├── tools.py         # buscar_material
├── schemas.py       # ConteudoQuestao, Questao, Revisao, Plano
├── agent.py         # grafo de uma questão (gerar → revisar → corrigir)
└── orquestrador.py  # grafo do lote (planejar → map → consolidar)
corpus/              # material didático em Markdown
tests/               # scripts de validação por etapa
```
