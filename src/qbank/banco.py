import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parents[2] / "data"


class Banco:
    def __init__(self, caminho: Path = DATA / "banco.sqlite"):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(caminho, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""CREATE TABLE IF NOT EXISTS questoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, topico TEXT, dificuldade TEXT,
            enunciado TEXT, alternativas TEXT, indice_correta INTEGER,
            justificativa TEXT, fontes TEXT, thread_id TEXT, criado_em TEXT)""")

    def salvar(self, q: dict, thread_id: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO questoes (topico, dificuldade, enunciado, alternativas, indice_correta, "
            "justificativa, fontes, thread_id, criado_em) VALUES (?,?,?,?,?,?,?,?,?)",
            (q["topico"], q["dificuldade"], q["enunciado"], json.dumps(q["alternativas"], ensure_ascii=False),
             q["indice_correta"], q["justificativa"], json.dumps(q["fontes"]), thread_id,
             datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def listar(self, limite: int = 20) -> list[dict]:
        linhas = self.conn.execute("SELECT * FROM questoes ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) | {"alternativas": json.loads(r["alternativas"])} for r in linhas]


banco = Banco()