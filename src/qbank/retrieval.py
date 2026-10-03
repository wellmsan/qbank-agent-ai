import re
import unicodedata
from pathlib import Path
from rank_bm25 import BM25Okapi

CORPUS = Path(__file__).resolve().parents[2] / "corpus"


def normalizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^\w\s]", " ", texto).split()


class Retriever:
    def __init__(self):
        self.trechos: dict[str, str] = {}
        for arq in sorted(CORPUS.glob("*.md")):
            secoes = re.split(r"(?m)^(?=## )", arq.read_text(encoding="utf-8"))
            for i, secao in enumerate(s for s in secoes if s.strip().startswith("## ")):
                self.trechos[f"{arq.name}#{i}"] = secao.strip()
        self.ids = list(self.trechos)
        self.bm25 = BM25Okapi([normalizar(self.trechos[i]) for i in self.ids])

    def buscar(self, consulta: str, k: int = 3) -> list[tuple[str, str]]:
        scores = self.bm25.get_scores(normalizar(consulta))
        ordem = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
        return [(self.ids[i], self.trechos[self.ids[i]]) for i in ordem if scores[i] > 0]


retriever = Retriever()