"""Raio do cadastro: texto, nan e inf viram o padrão (500 km); números válidos passam."""
import pytest


@pytest.mark.parametrize("valor,esperado", [
    ("300", 300.0), ("12.5", 12.5), (500, 500.0),
    ("nan", 500.0), ("NaN", 500.0), ("inf", 500.0), ("-inf", 500.0),
    ("abc", 500.0), ("", 500.0), (None, 500.0),
])
def test_raio_do_cadastro(front, valor, esperado):
    front  # garante o frontend no sys.path (fixture)
    import app
    assert app._raio(valor) == esperado
