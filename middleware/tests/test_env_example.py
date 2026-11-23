"""Evita deriva: toda variável CRISIS_* lida no código do núcleo precisa estar no .env.example."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def test_variaveis_crisis_estao_no_env_example():
    exemplo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    usadas = set()
    for arq in (RAIZ / "middleware").glob("*.py"):
        usadas |= set(re.findall(r"\"(CRISIS_[A-Z_]+)\"", arq.read_text(encoding="utf-8")))
    assert usadas, "nenhuma variável CRISIS_* encontrada (regex quebrou?)"
    faltando = [v for v in sorted(usadas) if not re.search(rf"^{v}=", exemplo, re.M)]
    assert not faltando, f"faltam no .env.example: {faltando}"
