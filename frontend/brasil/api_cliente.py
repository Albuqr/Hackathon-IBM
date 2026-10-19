"""Adapter HTTP da API /brasil (ADR 0004).

Todo acesso do frontend do Brasil à API passa por aqui: manda o segredo da API e, quando há
usuário logado, a identidade da sessão em X-Brasil-Usuario. Os testes trocam este adapter por
um falso via app.config["BRASIL_API"].
"""
import requests
from token_api import cabecalhos


class ApiHttp:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def __call__(self, metodo: str, caminho: str, usuario: int | None = None, timeout=30, **kw):
        """Chama a API /brasil; devolve (status, json). Falha de rede vira 503 com mensagem legível."""
        h = cabecalhos() | ({"X-Brasil-Usuario": str(usuario)} if usuario is not None else {})
        try:
            r = requests.request(metodo, f"{self.base}/brasil{caminho}", headers=h, timeout=timeout, **kw)
        except requests.RequestException as e:
            return 503, {"detail": f"API indisponível: {e}"}
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, {"detail": f"Resposta inválida da API ({r.status_code})"}

    def bruto(self, caminho: str, timeout=60) -> bytes | None:
        """Conteúdo cru (malha); None se falhar."""
        try:
            r = requests.get(f"{self.base}/brasil{caminho}", headers=cabecalhos(), timeout=timeout)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            return None
