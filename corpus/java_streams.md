# Java Streams: guia prático

A **Stream API** (introduzida no Java 8, `java.util.stream`) permite processar sequências de elementos de forma declarativa: você descreve *o que* fazer (filtrar, transformar, agregar) e a biblioteca cuida de *como* iterar.

Uma stream **não é uma estrutura de dados**. Ela não armazena elementos: é um pipeline de operações sobre uma fonte (coleção, array, I/O, gerador).

---

## 1. Anatomia de um pipeline

Todo pipeline tem três partes:

```java
List<String> nomes = pessoas.stream()          // 1. fonte
        .filter(p -> p.idade() >= 18)          // 2. operações intermediárias (lazy)
        .map(Pessoa::nome)
        .sorted()
        .toList();                             // 3. operação terminal (dispara a execução)
```

Propriedades fundamentais:

- **Lazy**: nada é executado até a operação terminal ser chamada.
- **Uso único**: depois da operação terminal, a stream é consumida. Reutilizar lança `IllegalStateException`.
- **Não modifica a fonte**: produz um novo resultado.
- **Processamento vertical**: cada elemento atravessa o pipeline inteiro antes do próximo (exceto em operações *stateful* como `sorted`).

```java
Stream.of("a", "b", "c")
      .peek(s -> System.out.println("filter: " + s))
      .map(String::toUpperCase)
      .peek(s -> System.out.println("map: " + s))
      .findFirst();
// filter: a
// map: A        <- parou aqui: findFirst é short-circuit
```

---

## 2. Criando streams

```java
// Coleções
list.stream();
set.parallelStream();
map.entrySet().stream();

// Valores e arrays
Stream.of("a", "b", "c");
Arrays.stream(new int[]{1, 2, 3});          // IntStream
Stream.ofNullable(talvezNulo);              // Java 9: vazia se null
Stream.empty();

// Geradores
Stream.iterate(1, n -> n * 2).limit(10);               // infinita + limit
Stream.iterate(1, n -> n <= 1000, n -> n * 2);         // Java 9: com condição de parada
Stream.generate(UUID::randomUUID).limit(5);

// Faixas numéricas
IntStream.range(0, 10);        // 0..9
IntStream.rangeClosed(1, 10);  // 1..10

// I/O e texto
Files.lines(Path.of("app.log"));    // feche com try-with-resources!
"linha1\nlinha2".lines();           // Java 11
"abc".chars();                      // IntStream
Pattern.compile(",").splitAsStream("a,b,c");

// Builder
Stream.<String>builder().add("x").add("y").build();
```

---

## 3. Operações intermediárias

Retornam uma nova `Stream` e são lazy.

| Operação | O que faz | Observação |
|---|---|---|
| `filter(Predicate)` | Mantém elementos que satisfazem o predicado | stateless |
| `map(Function)` | Transforma cada elemento | stateless |
| `flatMap(Function)` | Transforma cada elemento em uma stream e "achata" | 1 → N |
| `mapMulti(BiConsumer)` | Alternativa imperativa ao `flatMap` (Java 16) | evita criar streams |
| `distinct()` | Remove duplicados (via `equals`/`hashCode`) | stateful |
| `sorted()` / `sorted(Comparator)` | Ordena | stateful, bufferiza tudo |
| `peek(Consumer)` | Executa ação sem alterar | só para debug |
| `limit(n)` / `skip(n)` | Corta / pula elementos | `limit` é short-circuit |
| `takeWhile` / `dropWhile` | Pega/descarta enquanto a condição for verdadeira (Java 9) | ideal em streams ordenadas |
| `boxed()` | `IntStream` → `Stream<Integer>` | |
| `mapToInt/Long/Double/Obj` | Converte entre streams de objeto e primitivas | |
| `gather(Gatherer)` | Operação intermediária customizada (Java 24) | ver seção 9 |

### `map` vs `flatMap`

```java
List<List<Integer>> matriz = List.of(List.of(1, 2), List.of(3, 4));

matriz.stream().map(List::stream);         // Stream<Stream<Integer>>
matriz.stream().flatMap(List::stream);     // Stream<Integer> -> 1, 2, 3, 4

// Exemplo real: todos os itens de todos os pedidos
pedidos.stream()
       .flatMap(p -> p.itens().stream())
       .map(Item::sku)
       .distinct()
       .toList();
```

### `mapMulti` (Java 16)

Útil quando cada elemento gera 0, 1 ou poucos resultados — evita o custo de criar uma stream por elemento:

```java
Stream.of(1, 2, 3, 4)
      .<String>mapMulti((n, downstream) -> {
          if (n % 2 == 0) {
              downstream.accept("par:" + n);
              downstream.accept("dobro:" + n * 2);
          }
      })
      .toList(); // [par:2, dobro:4, par:4, dobro:8]
```

### `takeWhile` / `dropWhile`

```java
Stream.of(1, 2, 3, 10, 4, 5)
      .takeWhile(n -> n < 5)   // [1, 2, 3]  — para no primeiro que falha
      .toList();

Stream.of(1, 2, 3, 10, 4, 5)
      .dropWhile(n -> n < 5)   // [10, 4, 5]
      .toList();
```

Diferente de `filter`, eles **param** de avaliar na primeira falha.

---

## 4. Operações terminais

| Operação | Retorno | Short-circuit? |
|---|---|---|
| `toList()` (Java 16) | `List<T>` imutável | não |
| `collect(Collector)` | qualquer coisa | não |
| `forEach` / `forEachOrdered` | `void` | não |
| `reduce(...)` | `T` / `Optional<T>` | não |
| `count()` | `long` | não* |
| `min` / `max(Comparator)` | `Optional<T>` | não |
| `findFirst()` / `findAny()` | `Optional<T>` | sim |
| `anyMatch` / `allMatch` / `noneMatch` | `boolean` | sim |
| `toArray()` | `Object[]` / `T[]` | não |

\* Desde o Java 9, `count()` pode nem executar o pipeline se o tamanho for conhecido pela fonte (ex.: `list.stream().map(...).count()`). Por isso, nunca dependa de efeitos colaterais em `peek`/`map`.

```java
boolean temAdmin = usuarios.stream().anyMatch(u -> u.perfil() == Perfil.ADMIN);

Optional<Pedido> maisCaro = pedidos.stream()
        .max(Comparator.comparing(Pedido::valor));

String[] arr = nomes.stream().toArray(String[]::new);
```

### `reduce`

```java
int soma = Stream.of(1, 2, 3).reduce(0, Integer::sum);           // identidade + acumulador
Optional<Integer> produto = Stream.of(1, 2, 3).reduce((a, b) -> a * b);

// Forma com combiner (relevante em paralelo e quando os tipos diferem)
int totalCaracteres = nomes.stream()
        .reduce(0, (acc, s) -> acc + s.length(), Integer::sum);
```

Na prática, prefira `mapToInt(...).sum()` ou um `Collector` a `reduce` com tipos diferentes — fica mais legível.

---

## 5. Collectors

`Collectors` é onde a API fica realmente poderosa.

### Coleções

```java
.collect(Collectors.toList());            // mutável (na prática ArrayList, sem garantia)
.toList();                                // imutável, aceita null — preferível no Java 16+
.collect(Collectors.toUnmodifiableList()); // imutável, NÃO aceita null
.collect(Collectors.toSet());
.collect(Collectors.toCollection(TreeSet::new));
```

### `toMap`

```java
// Simples — lança IllegalStateException se houver chave duplicada!
Map<Long, Usuario> porId = usuarios.stream()
        .collect(Collectors.toMap(Usuario::id, Function.identity()));

// Com merge function para resolver duplicatas
Map<String, Integer> estoque = itens.stream()
        .collect(Collectors.toMap(Item::sku, Item::quantidade, Integer::sum));

// Escolhendo a implementação do Map
Map<String, Integer> ordenado = itens.stream()
        .collect(Collectors.toMap(Item::sku, Item::quantidade, Integer::sum, TreeMap::new));
```

> ⚠️ `Collectors.toMap` lança `NullPointerException` se algum **valor** for `null`.

### `groupingBy`

```java
// Map<Status, List<Pedido>>
Map<Status, List<Pedido>> porStatus = pedidos.stream()
        .collect(Collectors.groupingBy(Pedido::status));

// Com downstream collector
Map<Status, Long> contagem = pedidos.stream()
        .collect(Collectors.groupingBy(Pedido::status, Collectors.counting()));

Map<String, BigDecimal> totalPorCliente = pedidos.stream()
        .collect(Collectors.groupingBy(
                Pedido::cliente,
                Collectors.reducing(BigDecimal.ZERO, Pedido::valor, BigDecimal::add)));

Map<String, Set<String>> skusPorCliente = pedidos.stream()
        .collect(Collectors.groupingBy(
                Pedido::cliente,
                TreeMap::new,                                   // mapa ordenado
                Collectors.flatMapping(p -> p.itens().stream().map(Item::sku),
                                       Collectors.toSet())));

// Agrupamento aninhado
Map<String, Map<Status, Long>> matriz = pedidos.stream()
        .collect(Collectors.groupingBy(Pedido::cliente,
                 Collectors.groupingBy(Pedido::status, Collectors.counting())));
```

Downstream collectors úteis: `counting`, `summingInt/Long/Double`, `averagingX`, `summarizingX`, `mapping`, `filtering` (Java 9), `flatMapping` (Java 9), `minBy`/`maxBy`, `reducing`, `collectingAndThen`.

### `partitioningBy`

Sempre gera um `Map<Boolean, ...>` com as chaves `true` e `false`:

```java
Map<Boolean, List<Aluno>> aprovados = alunos.stream()
        .collect(Collectors.partitioningBy(a -> a.nota() >= 7));
```

### `joining`

```java
String csv = nomes.stream().collect(Collectors.joining(", ", "[", "]"));
// [Ana, Bruno, Carla]
```

### `teeing` (Java 12)

Combina dois collectors em uma única passada:

```java
record Faixa(int min, int max) {}

Faixa faixa = numeros.stream()
        .collect(Collectors.teeing(
                Collectors.minBy(Integer::compare),
                Collectors.maxBy(Integer::compare),
                (min, max) -> new Faixa(min.orElseThrow(), max.orElseThrow())));
```

### `collectingAndThen`

```java
Pedido maisRecente = pedidos.stream()
        .collect(Collectors.collectingAndThen(
                Collectors.maxBy(Comparator.comparing(Pedido::criadoEm)),
                Optional::orElseThrow));
```

---

## 6. Streams primitivas

`IntStream`, `LongStream` e `DoubleStream` evitam boxing/unboxing e oferecem operações numéricas prontas.

```java
int total = itens.stream().mapToInt(Item::quantidade).sum();

OptionalDouble media = alunos.stream().mapToDouble(Aluno::nota).average();

IntSummaryStatistics stats = itens.stream()
        .mapToInt(Item::quantidade)
        .summaryStatistics();
stats.getMin(); stats.getMax(); stats.getAverage(); stats.getSum(); stats.getCount();
```

Em pipelines numéricos grandes, trocar `Stream<Integer>` por `IntStream` costuma ser o ganho de performance mais barato.

---

## 7. Optional e streams

```java
Optional<Usuario> u = repo.findById(id);

u.stream()                         // Java 9: Optional -> Stream de 0 ou 1 elemento
 .map(Usuario::email)
 .toList();

// Achatar uma lista de Optionals
List<Endereco> enderecos = usuarios.stream()
        .map(Usuario::endereco)    // Stream<Optional<Endereco>>
        .flatMap(Optional::stream) // Stream<Endereco>
        .toList();
```

---

## 8. Parallel streams

```java
long primos = LongStream.rangeClosed(2, 10_000_000)
        .parallel()
        .filter(Primos::ehPrimo)
        .count();
```

Usam o `ForkJoinPool.commonPool()` por padrão. Valem a pena quando:

- o volume de dados é grande **e** o trabalho por elemento é CPU-bound;
- a fonte se divide bem (`ArrayList`, arrays, `IntStream.range` são ótimos; `LinkedList` e `Stream.iterate` são ruins);
- as operações são stateless e sem efeitos colaterais.

Evite quando:

- há I/O bloqueante (chamadas HTTP, banco) — você trava o common pool da JVM inteira (num servidor Spring, isso afeta outras requisições). Para I/O, use virtual threads (Java 21) ou um executor dedicado;
- a ordem importa (`forEachOrdered`, `findFirst`, `limit` em parallel ficam caros);
- o dataset é pequeno — o overhead de split/merge supera o ganho.

**Sempre meça** (JMH) antes de paralelizar.

---

## 9. Gatherers (Java 24)

`Stream::gather` (JEP 485, final no Java 24) permite criar operações intermediárias customizadas — algo que antes só era possível para terminais via `Collector`.

```java
import java.util.stream.Gatherers;

// Janelas fixas
Stream.of(1, 2, 3, 4, 5).gather(Gatherers.windowFixed(2)).toList();
// [[1, 2], [3, 4], [5]]

// Janelas deslizantes
Stream.of(1, 2, 3, 4).gather(Gatherers.windowSliding(3)).toList();
// [[1, 2, 3], [2, 3, 4]]

// Acumulado (prefix sum)
Stream.of(1, 2, 3, 4).gather(Gatherers.scan(() -> 0, Integer::sum)).toList();
// [1, 3, 6, 10]

// Map concorrente com limite de paralelismo (usa virtual threads)
urls.stream()
    .gather(Gatherers.mapConcurrent(10, this::baixar))
    .toList();
```

Gatherers prontos: `fold`, `scan`, `windowFixed`, `windowSliding`, `mapConcurrent`. Também é possível implementar a interface `Gatherer` para casos próprios (ex.: deduplicar por chave, batching).

---

## 10. Armadilhas comuns

**Reutilizar a stream**
```java
Stream<String> s = lista.stream();
s.count();
s.toList(); // IllegalStateException: stream has already been operated upon or closed
```
Se precisa reutilizar, guarde um `Supplier<Stream<T>>`.

**Efeitos colaterais em lambdas**
```java
// ❌ Não faça
List<String> resultado = new ArrayList<>();
lista.stream().filter(...).forEach(resultado::add); // quebra em parallel

// ✅ Faça
List<String> resultado = lista.stream().filter(...).toList();
```

**`peek` com lógica de negócio** — `peek` pode não ser executado (ver `count()` na seção 4). Use só para debug.

**`toList()` é imutável**
```java
var lista = stream.toList();
lista.add("x"); // UnsupportedOperationException
```

**Chaves duplicadas e valores nulos em `toMap`** — sempre considere a merge function.

**Exceções checadas** — lambdas de `Function`/`Predicate` não podem lançar checked exceptions. Opções: extrair um método que embrulha em `UncheckedIOException`, ou fazer a parte que lança fora da stream.

```java
List<String> conteudos = paths.stream()
        .map(this::lerArquivo)
        .toList();

private String lerArquivo(Path p) {
    try {
        return Files.readString(p);
    } catch (IOException e) {
        throw new UncheckedIOException(e);
    }
}
```

**Fechar streams de I/O** — `Files.lines`, `Files.list`, `Files.walk` seguram recursos:
```java
try (Stream<String> linhas = Files.lines(path)) {
    return linhas.filter(l -> l.contains("ERROR")).count();
}
```

**Ordem das operações importa para performance**
```java
// ❌ ordena tudo e depois filtra
lista.stream().sorted().filter(this::caro).toList();
// ✅ filtra primeiro, ordena menos
lista.stream().filter(this::caro).sorted().toList();
```

**Stream infinita sem short-circuit**
```java
Stream.iterate(1, n -> n + 1).filter(n -> n > 0).toList(); // nunca termina
```

---

## 11. Boas práticas

- Uma operação por linha: facilita leitura, diffs e breakpoints.
- Prefira **method references** quando deixarem o código mais claro (`Pessoa::nome`), mas não force.
- Extraia lambdas grandes para métodos com nome descritivo — `filter(this::ehElegivelParaDesconto)` se lê como prosa.
- Use `toList()` (Java 16+) em vez de `collect(Collectors.toList())`.
- Use streams primitivas para cálculos numéricos.
- Não transforme tudo em stream: loops com `break`, múltiplos acumuladores ou mutação de estado complexo costumam ficar mais claros com `for`.
- Não use `parallel()` por padrão; meça.
- Retornar `Stream<T>` de um método é válido, mas lembre que o chamador só pode consumi-la uma vez — em APIs públicas, `List<T>` costuma ser mais seguro.

---

## 12. Cola rápida

```java
// Filtrar e transformar
lista.stream().filter(x -> ...).map(X::y).toList();

// Contar por categoria
.collect(groupingBy(X::categoria, counting()));

// Somar por categoria
.collect(groupingBy(X::categoria, summingInt(X::valor)));

// Indexar por id
.collect(toMap(X::id, identity()));

// Primeiro que satisfaz
.filter(...).findFirst().orElseThrow();

// Existe algum?
.anyMatch(...);

// Top N
.sorted(comparing(X::score).reversed()).limit(n).toList();

// Achatar
.flatMap(x -> x.filhos().stream());

// String concatenada
.map(X::nome).collect(joining(", "));

// Estatísticas
.mapToInt(X::valor).summaryStatistics();
```

---

## Linha do tempo da API

| Versão | Novidades |
|---|---|
| Java 8 | Stream API, `Collectors`, streams primitivas, `Optional` |
| Java 9 | `takeWhile`, `dropWhile`, `iterate` com predicado, `ofNullable`, `Optional.stream()`, `Collectors.filtering/flatMapping` |
| Java 10 | `Collectors.toUnmodifiableList/Set/Map` |
| Java 11 | `String.lines()`, `Predicate.not` |
| Java 12 | `Collectors.teeing` |
| Java 16 | `Stream.toList()`, `mapMulti` |
| Java 24 | `Stream.gather` e `Gatherers` (JEP 485) |