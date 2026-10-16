"""Malha territorial do IBGE: 5.570 municípios + 27 UFs (FR-021).

`dados/malha.json` vem de temp/mapa-brasil (IBGE, malha municipal "mínima" e Censo 2022).
Localiza um ponto no município por ponto-no-polígono, com índice em baldes de 1°.
"""
import json
import math
import os
from functools import lru_cache

ARQUIVO = os.path.join(os.path.dirname(__file__), "dados", "malha.json")


def _aneis(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    return polys


def _dentro_anel(lon, lat, anel):
    c = False
    j = len(anel) - 1
    for i in range(len(anel)):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def _dentro(lon, lat, polys):
    return any(_dentro_anel(lon, lat, p[0]) and not any(_dentro_anel(lon, lat, h) for h in p[1:]) for p in polys)


def _caixa(polys):
    pts = [pt for p in polys for pt in p[0]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


class Malha:
    def __init__(self, dados: dict):
        self.dados = dados
        self.municipios = {}
        self._baldes: dict[tuple[int, int], list] = {}
        for f in dados["geojson"]["features"]:
            p = f["properties"]
            polys = _aneis(f["geometry"])
            caixa = _caixa(polys)
            item = (p["id"], polys, caixa)
            self.municipios[p["id"]] = p
            for x in range(math.floor(caixa[0]), math.floor(caixa[2]) + 1):
                for y in range(math.floor(caixa[1]), math.floor(caixa[3]) + 1):
                    self._baldes.setdefault((x, y), []).append(item)

    def municipio_em(self, lat: float, lon: float):
        """Código IBGE do município que contém o ponto, ou None (fora do Brasil)."""
        for cod, polys, (x0, y0, x1, y1) in self._baldes.get((math.floor(lon), math.floor(lat)), []):
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _dentro(lon, lat, polys):
                return cod
        return None

    def no_brasil(self, lat: float, lon: float) -> bool:
        return self.municipio_em(lat, lon) is not None

    def info(self, cod: int) -> dict | None:
        return self.municipios.get(cod)


@lru_cache(maxsize=1)
def carregar() -> Malha:
    with open(ARQUIVO, encoding="utf-8") as fh:
        return Malha(json.load(fh))
