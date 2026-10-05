# qbank-agent

Sistema multiagente que gera questões de múltipla escolha **fundamentadas em material didático**. Cada questão é escrita a partir de trechos recuperados do corpus, revisada por um agente que não conhece o gabarito e só é aprovada se passar por checagens determinísticas feitas em código. Antes de ir para o banco, o lote passa por **aprovação humana** (human-in-the-loop), com o estado do grafo persistido em SQLite para que a execução possa ser pausada e retomada.

Construído com [LangGraph](https://github.com/langchain-ai/langgraph) e [LangChain](https://github.com/langchain-ai/langchain). Funciona com qualquer provedor suportado pelo `init_chat_model` (Anthropic, OpenAI, Google, Ollama), e cada papel do sistema pode usar um modelo diferente.

## Como funciona

```
pedido ──► planejar ──► Send × N ──► [agente] [agente] [agente] ──► consolidar ──► aprovacao_humana ──► persistir
            (Plano)                 (em paralelo, contexto isolado)    (candidatas)    (interrupt ⏸)       (banco.sqlite)
```

### Orquestrador (lote)

1. **planejar**: transforma o pedido em um `Plano` com uma especificação por questão (subtópico, dificuldade, objetivo). Só usa subtópicos que existem no sumário do corpus; o que estiver fora vai para `observacoes`.
2. **distribuir**: cria um `Send` por especificação, e cada um roda o agente completo em paralelo.
3. **consolidar**: ordena os resultados, descarta reprovadas e quase-duplicatas (similaridade de Jaccard > 0.6 entre enunciados) e monta a lista de `candidatas`, cada uma com um `status`:
   - `aprovada`: passou no revisor;
   - `divergente`: o **único** problema objetivo é o revisor ter resolvido a questão com outra alternativa (`gabarito_revisor`). Em vez de descartar, deixa um humano arbitrar;
   - `reprovada`: só aparece se `QBANK_HUMANO_REVISA_REPROVADAS=1`, junto com os problemas apontados.

   Sem candidatas, o grafo termina aqui.
4. **aprovacao_humana**: chama `interrupt()` com as candidatas e os alertas. O grafo **pausa**, o estado fica salvo no checkpointer e a execução é retomada com `Command(resume=decisoes)`, uma decisão por candidata: `a` (aprovar), `r` (rejeitar) ou `c` (corrigir o gabarito para o do revisor, só para divergentes). Na retomada o nó roda de novo desde o início, por isso nada com efeito colateral vem antes do `interrupt()`.
5. **persistir**: a **única escrita no banco** do sistema inteiro, e só depois da decisão humana. Grava as aprovadas/corrigidas em `data/banco.sqlite` com o `thread_id` do lote, para rastreabilidade.

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
  - o revisor encontrou **exatamente uma** alternativa verdadeira, e ela coincide com o gabarito (se for a única divergência, a questão segue como `divergente` para arbitragem humana);
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
QBANK_HUMANO_REVISA_REPROVADAS=0  # 1 = também mostra as reprovadas na aprovação humana

ANTHROPIC_API_KEY=...
```

Com Ollama, o contexto é fixado em 16k tokens e o modo *thinking* é desligado. A saída estruturada usa `json_schema` (geração restrita por gramática) no Ollama e `function_calling` nos demais provedores.

## Uso

### Linha de comando (fluxo com aprovação humana)

```bash
# 1. Gera o lote e pausa na aprovação humana; imprime o thread_id
python tests/teste_passo7.py gerar "4 questões de Java Streams, nível médio, sobre avaliação preguiçosa, map vs flatMap, curto-circuito e paralelismo."

# 2. Em outro momento (até em outro processo), revisa as candidatas e decide
python tests/teste_passo7.py retomar <thread_id>

# Se a execução falhar no meio (ex.: erro do provedor), continua do último checkpoint
python tests/teste_passo7.py continuar <thread_id>

# Lista as últimas questões gravadas no banco
python tests/teste_passo7.py listar
```

Na revisão, cada alternativa é marcada com `G` (gabarito do gerador) e, nas divergentes, `R` (resposta do revisor).

### Python

`interrupt()` exige um checkpointer, então use `construir(checkpointer_sqlite())` (o `orquestrador` exportado no módulo é compilado sem checkpointer):

```python
from langgraph.types import Command
from qbank.orquestrador import checkpointer_sqlite, construir

grafo = construir(checkpointer_sqlite())
cfg = {"configurable": {"thread_id": "lote-001"}}

grafo.invoke({"pedido": "3 questões de Java Streams, nível médio."}, cfg)

snap = grafo.get_state(cfg)
if snap.next:  # pausado em aprovacao_humana
    pendente = snap.tasks[0].interrupts[0].value
    for q in pendente["candidatas"]:
        print(q["status"], q["enunciado"])
    estado = grafo.invoke(Command(resume=["a"] * len(pendente["candidatas"])), cfg)
    print("Gravadas:", estado["salvas"])
```

Para gerar uma única questão, sem o orquestrador:

```python
from qbank.agente import agente

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
| `teste_passo7.py` | Aprovação humana com `interrupt`, checkpoints em SQLite e persistência (`gerar`, `retomar`, `continuar`, `listar`) |

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
├── agente.py        # grafo de uma questão (gerar → revisar → corrigir)
├── orquestrador.py  # grafo do lote (planejar → map → consolidar → aprovação humana → persistir)
└── banco.py         # banco de questões aprovadas (SQLite)
corpus/              # material didático em Markdown
data/                # banco.sqlite (questões) e checkpoints.sqlite (estado dos grafos)
tests/               # scripts de validação por etapa
```
